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


def test_cli(tmp_path):
    st = CommitStore(tmp_path / "commits")
    c, _ = st.commit(write(tmp_path, schema_doc_domain()))
    run = lambda *a: subprocess.run(["uv", "run", "--quiet", "toprope-deploy", "--env", str(tmp_path / "env"),  # noqa: E731
                                     "--commits", str(tmp_path / "commits"), *a],
                                    capture_output=True, text=True, timeout=120)
    assert run("preview", "example", c.id).returncode == 0
    unapproved = run("deploy", "example", c.id, "--approver", "ana")
    assert unapproved.returncode != 0 and "refused (unapproved)" in unapproved.stderr
    st.approve("example", c.id, "ana")
    assert run("deploy", "example", c.id, "--approver", "ana").returncode == 0
    assert json.loads(run("status").stdout)["current"]["commit"] == c.id
    unknown = run("deploy", "example", "9-nope", "--approver", "ana")
    assert unknown.returncode != 0 and "no commit" in unknown.stderr


def test_a_terminal_state_without_a_matrix_row_is_not_stranded(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    m = ReferenceModel(Domain.model_validate(schema_doc_domain()), SQLiteEventStore(str(env.store_path)))
    m.seed("Experiment", {"id": "E-done", "status": "decided", "planned_days": 1, "guardrails": []})
    raw = schema_doc_domain()
    del raw["transitions"]["Experiment"]["matrix"]["decided"]         # still a valid state, just no row
    st, env, c, b = committed(tmp_path, raw)
    assert env.stranded(Domain.model_validate(raw)) == []
