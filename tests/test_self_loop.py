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


def test_the_whole_loop_runs_on_the_generated_command_line(tmp_path):
    """interview → commit → check → approve → deliver → preview → deploy → verify, from the
    repository's own declarations and the kernel, through `toprope-run` only (ADR-0037 §3.4)."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    for f in filter(None, files):
        src, dst = ROOT / f.decode(), tmp_path / f.decode()
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
    me = "steamshon <steamshon@apache.org>"
    (tmp_path / "ids.yaml").write_text(yaml.safe_dump({"t-owen": {"id": me, "roles": ["owner", "approver"]}}))
    base = ["--composition", "domains/toprope-self.composition.yaml", "--kernel-root", ".", "--workspace",
            "toprope.authoring.workspace.yaml", "--env", ".toprope/env", "--identity", "static:ids.yaml"]

    def step(member, *a):
        r = run(*base, "--member", member, *a, cwd=tmp_path)
        assert r.returncode == 0, (a, r.stdout, r.stderr)
        out = json.loads(r.stdout)
        assert all(t["status"] in ("ok", "HandoffDelivered") and "error" not in t for t in out.get("then", [])), out
        return out

    def get(member, oid):
        return json.loads(run(*base, "--member", member, "get", oid, cwd=tmp_path).stdout)

    a = "authoring"
    step(a, "open_draft", a, "--domain-id", a, "--declaration", "domains/authoring/authoring.domain.yaml",
         "--branch", "work")
    step(a, "next_questions", a)
    step(a, "add_source", "S-adr", "--kind", "records", "--path", "docs/adr")
    step(a, "ask_question", "Q-1", "--stage", "actions", "--text", "What is a draft?")
    step(a, "answer_question", "A-1", "--question", "Q-1", "--words", "The working copy of a declaration.",
         "--decisions", "[]")
    ref = get(a, "A-1")["ref"]
    assert ref.startswith("interview:domains/authoring/interview.jsonl#L")
    rule = {"id": "drafts-name-their-declaration", "on": "Draft", "check": "exists(target.declaration)",
            "reason": "A draft is the working copy of one declaration."}
    step(a, "propose_element", "E-1", "--path", f"invariants.{rule['id']}", "--origin", "S-adr", "--cites", ref,
         "--value", json.dumps(rule))
    assert get(a, "E-1")["issues"] == 0
    step(a, "confirm_element", "E-1")
    decl = yaml.safe_load((tmp_path / "domains/authoring/authoring.domain.yaml").read_text())
    (added,) = [i for i in decl["invariants"] if i["id"] == rule["id"]]                 # the working copy changed
    assert added["status"] == "confirmed" and added["source"]["ref"] == ref
    log = [json.loads(x) for x in (tmp_path / "domains/authoring/interview.jsonl").read_text().splitlines()]
    assert log[-1] | {"at": None} == {"at": None, "kind": "confirm", "paths": [f"invariants.{rule['id']}"],
                                      "via": "kernel", "who": me}
    (commit,) = [t["object"] for t in step(a, "commit_draft", a)["then"]]
    assert get(a, commit)["domain_id"] == a and get(a, commit)["author"] == me
    step(a, "check_commit", commit)
    assert get(a, commit)["checks_passed"] is True
    step(a, "approve_commit", commit)
    assert get(a, commit)["main"] == commit
    (handoff,) = step(a, "deliver", commit, "--environment", "local")["then"]
    request = handoff["object"]
    step("delivery", "preview", request)
    assert get("delivery", request)["harness_ok"] is True
    step("delivery", "deploy", request)
    step("delivery", "verify", request, "--verified", "true")
    assert get("delivery", request)["stage"] == "verified"
    for d in ("authoring", "delivery"):                         # each domain's own log, for git
        assert (tmp_path / f"domains/{d}/events/events.jsonl").stat().st_size > 0
    approvals = (tmp_path / ".toprope/commits/authoring/approvals.jsonl").read_text().splitlines()
    assert json.loads(approvals[-1]) | {"at": None} == {"approver": me, "at": None, "commit": commit}


def test_the_command_line_shows_what_a_command_set_off(tmp_path):
    p = per_domain(tmp_path)
    base = ["--composition", str(p), "--member", "authoring", "--identity", f"static:{tmp_path / 'ids.yaml'}",
            "--kernel-root", str(tmp_path)]
    ok = json.loads(run(*base, "--seed", "check_version", "V1", cwd=tmp_path).stdout)
    assert [(t["kernel"], t["status"], t["object"]) for t in ok["then"]] == [
        ("validate", "ok", "V1"), ("run_harness", "ok", "V1")]
    (tmp_path / "shop.domain.yaml").unlink()                       # the service fails, and still replies
    failed = json.loads(run(*base, "check_version", "V1", cwd=tmp_path).stdout)
    assert {t["status"] for t in failed["then"]} == {"failed"} and all("shop.domain.yaml" in t["error"]
                                                                      for t in failed["then"])
