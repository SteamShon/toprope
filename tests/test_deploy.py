import json
import subprocess

import pytest
import yaml

from test_decl import schema_doc_domain
from toprope.decl import Domain
from toprope.deploy import DeployRefused, LocalEnvironment
from toprope.semantics import Actor, ReferenceModel
from toprope.store.sqlite import SQLiteEventStore

ANA = Actor("ana", "person", ("approver",))


def write(tmp_path, raw, name="d.domain.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    return p


def test_preview_then_deploy(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    b = env.preview(write(tmp_path, schema_doc_domain()), examples=20)
    assert b.harness_ok and b.domain == "example"
    out = tmp_path / "env" / "builds" / b.id
    assert json.loads((out / "harness.json").read_text())["ok"] is True
    assert json.loads((out / "world-map.json").read_text())["format"] == "toprope.world-map/1"
    cur = env.deploy(b.id, ANA)
    assert env.current()["build"] == b.id and cur["approver"] == {"id": "ana", "kind": "person"}
    assert env.server_args()[:2] == ["--domain", str(out / "domain.yaml")]
    assert [h["result"] for h in env.history()] == ["deployed"]


def test_floor_a_person_approves(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    b = env.preview(write(tmp_path, schema_doc_domain()), examples=0)
    for who in (Actor("bot", "agent", ("approver",)), Actor("system", "system", ("system",))):
        with pytest.raises(DeployRefused) as e:
            env.deploy(b.id, who)
        assert e.value.rule == "approver"
    assert env.current() is None and [h["rule"] for h in env.history()] == ["approver", "approver"]


def test_floor_a_failing_harness_is_never_deployed(tmp_path):
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["draft"]["launch_experiment"] = "running"   # breaks an invariant
    env = LocalEnvironment(tmp_path / "env")
    b = env.preview(write(tmp_path, raw), examples=0)
    assert not b.harness_ok
    with pytest.raises(DeployRefused, match="harness"):
        env.deploy(b.id, ANA)


def test_floor_a_tainted_build_is_refused(tmp_path, monkeypatch):
    env = LocalEnvironment(tmp_path / "env")
    b = env.preview(write(tmp_path, schema_doc_domain()), examples=0)
    decl = tmp_path / "env" / "builds" / b.id / "domain.yaml"
    decl.write_text(decl.read_text() + "\n# edited after preview\n")
    with pytest.raises(DeployRefused, match="changed after preview"):
        env.deploy(b.id, ANA)
    b2 = env.preview(write(tmp_path, schema_doc_domain(), "e.domain.yaml"), examples=0)
    import toprope.deploy as dep
    monkeypatch.setattr(dep, "toolchain_hash", lambda: "another-toolchain")
    with pytest.raises(DeployRefused, match="toolchain"):
        env.deploy(b2.id, ANA)


def test_floor_no_stranded_objects(tmp_path):
    env = LocalEnvironment(tmp_path / "env")
    m = ReferenceModel(Domain.model_validate(schema_doc_domain()), SQLiteEventStore(str(env.store_path)))
    m.seed("Experiment", {"id": "E-live", "status": "ended", "planned_days": 1, "guardrails": []})
    raw = schema_doc_domain()
    del raw["transitions"]["Experiment"]["matrix"]["ended"]          # the new version drops a state in use
    b = env.preview(write(tmp_path, raw), examples=0)
    assert b.harness_ok
    with pytest.raises(DeployRefused) as e:
        env.deploy(b.id, ANA)
    assert e.value.rule == "stranded" and "E-live" in e.value.reason


def test_cli(tmp_path):
    p = write(tmp_path, schema_doc_domain())
    run = lambda *a: subprocess.run(["uv", "run", "--quiet", "toprope-deploy", "--env", str(tmp_path / "env"), *a],  # noqa: E731
                                    capture_output=True, text=True, timeout=120)
    pv = run("preview", str(p))
    assert pv.returncode == 0, pv.stderr
    bid = json.loads(pv.stdout)["id"]
    bad = run("deploy", "nope", "--approver", "ana")
    assert bad.returncode != 0 and "refused (no-build)" in bad.stderr
    assert run("deploy", bid, "--approver", "ana").returncode == 0
    assert json.loads(run("status").stdout)["current"]["build"] == bid
