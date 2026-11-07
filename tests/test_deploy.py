import json
import subprocess

import pytest
import yaml

from test_decl import schema_doc_domain
from toprope.commits import CommitStore
from toprope.decl import Domain
from toprope.deploy import DeployRefused, LocalEnvironment
from toprope.semantics import Actor, ReferenceModel
from toprope.store.sqlite import SQLiteEventStore

ANA = Actor("ana", "person", ("approver",))


def write(tmp_path, raw, name="d.domain.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


def committed(tmp_path, raw, approve=True, examples=0):
    """Commit a declaration, approve it, and preview it: everything before a deploy."""
    st = CommitStore(tmp_path / "commits")
    c, _ = st.commit(write(tmp_path, raw))
    if approve:
        st.approve(raw["domain"], c.id, "ana")
    env = LocalEnvironment(tmp_path / "env")
    b = env.preview_commit(st, raw["domain"], c.id, examples=examples)
    return st, env, c, b


def test_preview_then_deploy(tmp_path):
    st, env, c, b = committed(tmp_path, schema_doc_domain(), examples=20)
    assert b.harness_ok and b.domain == "example"
    out = tmp_path / "env" / "builds" / b.id
    assert json.loads((out / "harness.json").read_text())["ok"] is True
    assert json.loads((out / "world-map.json").read_text())["format"] == "toprope.world-map/1"
    cur = env.deploy_commit(st, "example", c.id, ANA)
    assert env.current()["commit"] == c.id and cur["approver"] == {"id": "ana", "kind": "person"}
    assert env.server_args()[:2] == ["--domain", str(out / "domain.yaml")]
    assert [h["result"] for h in env.history()] == ["deployed"]


def test_there_is_no_way_around_the_commit_floor(tmp_path):
    """ADR-0029: an environment moves only to an approved commit; there is no build-only path."""
    st, env, c, b = committed(tmp_path, schema_doc_domain(), approve=False)
    assert not hasattr(env, "deploy")
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c.id, ANA)
    assert e.value.rule == "unapproved" and env.current() is None


def test_floor_a_person_approves(tmp_path):
    st, env, c, b = committed(tmp_path, schema_doc_domain())
    for who in (Actor("bot", "agent", ("approver",)), Actor("system", "system", ("system",))):
        with pytest.raises(DeployRefused) as e:
            env.deploy_commit(st, "example", c.id, who)
        assert e.value.rule == "approver"
    assert env.current() is None and [h["rule"] for h in env.history()] == ["approver", "approver"]


def test_floor_a_failing_harness_is_never_deployed(tmp_path):
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"   # breaks an invariant
    st, env, c, b = committed(tmp_path, raw)
    assert not b.harness_ok
    with pytest.raises(DeployRefused, match="harness"):
        env.deploy_commit(st, "example", c.id, ANA)


def test_floor_a_tainted_build_is_refused(tmp_path, monkeypatch):
    st, env, c, b = committed(tmp_path, schema_doc_domain())
    decl = tmp_path / "env" / "builds" / b.id / "domain.yaml"
    original = decl.read_text()
    decl.write_text(original + "\n# edited after preview\n")
    with pytest.raises(DeployRefused, match="changed after preview"):
        env.deploy_commit(st, "example", c.id, ANA)
    decl.write_text(original)
    import toprope.deploy as dep
    monkeypatch.setattr(dep, "toolchain_hash", lambda: "another-toolchain")
    with pytest.raises(DeployRefused, match="toolchain"):
        env.deploy_commit(st, "example", c.id, ANA)


def test_floor_no_stranded_objects(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    m = ReferenceModel(Domain.model_validate(schema_doc_domain()), SQLiteEventStore(str(env.store_path)))
    m.seed("Experiment", {"id": "E-live", "status": "ended", "planned_days": 1, "guardrails": []})
    raw = schema_doc_domain()
    del raw["transitions"]["Experiment"]["matrix"]["ended"]          # the new version drops a state in use:
    raw["objects"]["Experiment"]["properties"]["status"]["enum"].remove("ended")   # its row and its value
    st, env, c, b = committed(tmp_path, raw)
    assert b.harness_ok
    with pytest.raises(DeployRefused) as e:
        env.deploy_commit(st, "example", c.id, ANA)
    assert e.value.rule == "stranded" and "E-live" in e.value.reason


def test_preview_deploy_through_the_kernel_and_the_deployed_command(tmp_path):
    from toprope.kernel.services import LocalKernel
    st = CommitStore(tmp_path / "commits")
    c, _ = st.commit(write(tmp_path, schema_doc_domain()))
    k = LocalKernel(tmp_path, environment=LocalEnvironment(tmp_path / "env"), harness_examples=5, commits=st)
    ana = {"id": "ana", "kind": "person"}
    assert k.call("preview", {"domain": "example", "commit": c.id})["harness_ok"] is True
    unapproved = k.call("deploy", {"domain": "example", "commit": c.id, "approver": "ana"}, caller=ana)
    assert unapproved["deployed"] is False and unapproved["error"].startswith("unapproved")
    st.approve("example", c.id, "ana")
    assert k.call("deploy", {"domain": "example", "commit": c.id, "approver": "ana"}, caller=ana)["deployed"] is True
    r = subprocess.run(["uv", "run", "--quiet", "toprope-commits", "deployed", "--env", str(tmp_path / "env")],
                       capture_output=True, text=True, timeout=120)
    out = json.loads(r.stdout)
    assert out["current"]["commit"] == c.id and out["server_args"] and out["history"]
    unknown = k.call("deploy", {"domain": "example", "commit": "9-nope", "approver": "ana"}, caller=ana)
    assert not unknown["ok"] and "no commit" in unknown["error"]


def test_a_terminal_state_without_a_matrix_row_is_not_stranded(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    m = ReferenceModel(Domain.model_validate(schema_doc_domain()), SQLiteEventStore(str(env.store_path)))
    m.seed("Experiment", {"id": "E-done", "status": "decided", "planned_days": 1, "guardrails": []})
    raw = schema_doc_domain()
    del raw["transitions"]["Experiment"]["matrix"]["decided"]         # still a valid state, just no row
    st, env, c, b = committed(tmp_path, raw)
    assert env.stranded(Domain.model_validate(raw)) == []


def test_probes_check_the_deployed_commit_in_use(tmp_path):
    """`verify` acts on what the probes found, not on a checkbox: the environment runs this
    commit's build, its scenarios pass there, and the objects in use meet every invariant."""
    from test_change_check import in_flight_example                   # a running experiment can still end
    raw = in_flight_example()
    st, env, c, b = committed(tmp_path, raw)
    before = env.probe_commit(st, "example", c.id)                      # nothing deployed yet
    assert before["passed"] is False and "not what this environment runs" in before["summary"]
    env.deploy_commit(st, "example", c.id, ANA)
    ok = env.probe_commit(st, "example", c.id)
    n = len(raw["scenarios"])
    assert ok == {"passed": True, "summary": f"passed: {n} of {n} scenario(s) pass; no store yet"}
    assert st.check_status("example", c.id)["probes"]["ok"] is True
    m = ReferenceModel(Domain.model_validate(raw), SQLiteEventStore(str(env.store_path)))
    m.seed("Experiment", {"id": "E-bad", "status": "running", "planned_days": 1, "guardrails": []})  # no started_at
    bad = env.probe_commit(st, "example", c.id)
    assert bad["passed"] is False and bad["summary"].startswith("E-bad: breaks ")
    assert st.check_status("example", c.id)["probes"]["ok"] is False


def test_a_finished_object_that_breaks_a_new_rule_only_warns_the_probes(tmp_path):
    """As in log replay: a new invariant does not rewrite finished history (Delivery's verified
    requests from before its probes). The probes read the domain's own log when given one."""
    from toprope.store import MemoryEventStore
    st, env, c, b = committed(tmp_path, schema_doc_domain())
    env.deploy_commit(st, "example", c.id, ANA)
    own = MemoryEventStore()
    ReferenceModel(Domain.model_validate(schema_doc_domain()), own).seed(
        "Experiment", {"id": "E-old", "status": "decided", "planned_days": 1, "guardrails": []})  # no approver
    out = env.probe_commit(st, "example", c.id, events=own)
    assert out["passed"] is True and out["summary"].endswith("6 object(s) checked; 2 warning(s) on finished objects")  # the world, and E-old breaks both rules


def test_probe_through_the_kernel(tmp_path):
    from toprope.kernel import CATALOG
    from toprope.kernel.services import LocalKernel
    st, env, c, b = committed(tmp_path, schema_doc_domain())
    env.deploy_commit(st, "example", c.id, ANA)
    k = LocalKernel(tmp_path, environment=env, commits=st)
    assert set(CATALOG["probe"].result) == {"passed", "summary"}
    assert k.call("probe", {"domain": "example", "commit": c.id})["passed"] is True
    from test_change_check import history, in_flight_example
    k.domain_events["example"] = history(in_flight_example())          # its own log: E-onboarding runs
    out = k.call("probe", {"domain": "example", "commit": c.id})
    assert out["passed"] is True and "5 object(s) checked" in out["summary"]    # read, not "no store yet"
