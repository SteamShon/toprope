"""The self domains run end to end on the generated tools (ADR-0037 §3.4), and the regeneration
check (ADR-0028) passes on them."""
import json
import os
import subprocess
from pathlib import Path

import yaml
from test_kernel_effects import write_composition

from toprope.harness.regen import regen_check
from toprope.kernel.services import LocalKernel

ROOT = Path(__file__).resolve().parent.parent
SELF = ROOT / "domains/toprope-self.composition.yaml"


def test_the_self_composition_passes_the_regeneration_check():
    out = regen_check(SELF, levels=("model",), examples=5)
    bad = [e for e in out["effects"] if not e["ok"]]
    assert out["ok"] and out["same_after_regenerating"] and not bad, bad


def test_a_commit_tells_its_domain_branch_and_author(tmp_path):
    from test_decl import schema_doc_domain
    (tmp_path / "shop.domain.yaml").write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    k = LocalKernel(tmp_path, harness_examples=5)
    out = k.call("commit", {"declaration": "shop.domain.yaml"}, caller={"id": "ana", "kind": "person"})
    assert (out["domain"], out["branch"], out["author"]) == ("example", "work", "ana")


def run(*a, cwd):
    return subprocess.run(["uv", "run", "--quiet", "--project", str(ROOT), "toprope-run", *a], cwd=cwd,
                          capture_output=True, text=True, timeout=120, check=False,
                          env={**os.environ, "TOPROPE_TOKEN": "t-owen"})


def per_domain(tmp_path):
    """The composition from test_kernel_effects, with each member under its own directory."""
    p = write_composition(tmp_path)
    raw = yaml.safe_load(p.read_text())
    for name, m in raw["members"].items():
        (tmp_path / name).mkdir()
        (tmp_path / m["declaration"]).rename(tmp_path / name / m["declaration"])
        m["declaration"] = f"{name}/{m['declaration']}"
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({"t-owen": {"id": "owen", "roles": ["owner"]}}))
    return p


def test_each_member_keeps_its_own_event_log_next_to_its_declaration(tmp_path):
    p = per_domain(tmp_path)
    base = ["--composition", str(p), "--member", "authoring", "--identity", f"static:{tmp_path / 'ids.yaml'}"]
    first = run(*base, "--seed", "approve_version", "V1", cwd=tmp_path)
    assert first.returncode == 1 and json.loads(first.stdout)["code"] == "checked-clean"
    again = run(*base, "history", "V1", cwd=tmp_path)                 # a new process reads the same log
    assert "DomainVersionApproveVersion" not in again.stdout and json.loads(again.stdout)
    assert (tmp_path / "authoring/events/events.jsonl").is_file()
    assert not (tmp_path / "events").exists() and not (tmp_path / "delivery/events/events.jsonl").exists()
    gone = run(*base, "--store", "memory", "get", "V1", cwd=tmp_path)
    assert json.loads(gone.stdout) is None


def test_members_in_one_directory_are_refused_rather_than_mixed(tmp_path):
    p = write_composition(tmp_path)
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({"t-owen": {"id": "owen", "roles": ["owner"]}}))
    out = run("--composition", str(p), "--member", "authoring", "--identity", f"static:{tmp_path / 'ids.yaml'}",
              "get", "V1", cwd=tmp_path)
    assert out.returncode == 1 and "event logs would mix" in out.stderr
