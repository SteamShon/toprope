"""Regression tests for the findings of the second umbrella → develop review."""
import copy

import yaml
from test_decl import schema_doc_domain

from toprope.decl import Domain, diff_interface, interface, review_diff, review_elements


def dom(raw):
    return Domain.model_validate(raw)


# 1. a `status` inside user data is data, not provenance --------------------------------------------
def test_status_in_effects_and_fixtures_is_a_change():
    base = schema_doc_domain()
    raw = copy.deepcopy(base)
    raw["actions"]["launch_experiment"]["effects"].append({"set": {"target.status": "running", "status": "x"}})
    fx = next(f for f in raw["world"]["fixtures"] if "Experiment" in f)
    fx["Experiment"]["status"] = "approved"
    r = review_diff(review_elements(dom(base)), review_elements(dom(raw)))
    assert "action:launch_experiment" in r.changed and any(k.startswith("fixture:Experiment.") for k in r.changed)
    assert "action:launch_experiment" not in diff_interface(interface(dom(base)), interface(dom(raw))).text_only
    prov = copy.deepcopy(base)                                       # provenance itself still is not a change
    prov["actions"]["launch_experiment"]["status"] = "confirmed"
    assert review_diff(review_elements(dom(base)), review_elements(dom(prov))).to_review == []


# 2. log replay re-decides kernel replies as `external:kernel` ------------------------------------
def test_past_kernel_replies_replay_with_the_kernel_role():
    from test_kernel_effects import DOMAIN, ex

    from toprope.check import log_replay
    from toprope.kernel.services import RecordingKernel
    e = ex(RecordingKernel({"validate": {"ok": True, "errors": 0}, "run_harness": {"ok": True, "findings": 0}}))
    assert e.submit("t", "check_version", "V1", idempotency_key="k1").ok
    d = dom(DOMAIN)
    r = log_replay(d, d, e.store)
    assert "3 of 3" in r.note and [p for p in r.problems if p.severity == "error"] == []


# 3. a private key across a chunk boundary is redacted ------------------------------------------------
def test_a_private_key_across_chunks_is_redacted(tmp_path):
    from toprope.sources import CODE_CHUNK_LINES, SourceSpec, read
    lines = [f"x = {i}" for i in range(CODE_CHUNK_LINES - 5)]
    lines += ["-----BEGIN RSA PRIVATE KEY-----"] + ["QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVo=" for _ in range(10)]
    lines += ["-----END RSA PRIVATE KEY-----", "y = 1"]
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "k.py").write_text("\n".join(lines) + "\n")
    chunks = read(SourceSpec(id="repo", kind="repository", path="repo"), tmp_path)
    text = "\n".join(c.text for c in chunks)
    assert "QUJDREVG" not in text and "BEGIN RSA" not in text
    assert sum(c.redactions.get("private-key", 0) for c in chunks) >= 1
    assert chunks[-1].ref.endswith(f"-L{len(lines)}")                # line refs still right


# 4. before any approval, a commit is checked against its parent --------------------------------------
def test_a_commit_before_any_approval_is_checked_against_its_parent(tmp_path):
    from toprope.check import check_commit
    from toprope.commits import CommitStore
    st = CommitStore(tmp_path / "c")
    p = tmp_path / "d.yaml"
    p.write_text(yaml.safe_dump(schema_doc_domain(), sort_keys=False))
    c0, _ = st.commit(p)
    raw = schema_doc_domain()
    raw["transitions"]["Experiment"]["matrix"]["approved"]["launch_experiment"] = {"deny": "No."}
    p.write_text(yaml.safe_dump(raw, sort_keys=False))
    c1, _ = st.commit(p)
    r = check_commit(st, "example", c1.id, examples=5)
    assert r.diff["from"] == c0.id and not r.checks["semantic"].ok


# 6. amending and freezing never print the sealed key mix ---------------------------------------------
def test_freeze_and_amend_are_sealed(tmp_path, capsys):
    from test_instruments import filled, instruments
    d = filled(tmp_path)
    (d / "gold-scenarios.yaml").unlink()
    for f in ("probe-suite", "verdict-rules", "change-requests", "change-key"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    instruments.freeze(d)
    p = d / "probe-suite.yaml"
    p.write_text(p.read_text() + "\n# amended\n")
    assert instruments.amend(d, "probe-suite", "a comment") == []
    assert "key mix" not in capsys.readouterr().out


# 7. a gold file that exists must be frozen before a run -------------------------------------------------
def test_verify_requires_an_existing_gold_file_frozen(tmp_path):
    from test_instruments import filled, instruments
    d = filled(tmp_path)
    gold = (d / "gold-scenarios.yaml").read_text()
    (d / "gold-scenarios.yaml").unlink()
    for f in ("probe-suite", "verdict-rules"):
        p = d / f"{f}.yaml"
        p.write_text(p.read_text().replace("status: draft", "status: frozen"))
    for f in ("change-requests", "change-key"):
        (d / f"{f}.yaml").unlink()
    assert instruments.freeze(d) == []
    (d / "gold-scenarios.yaml").write_text(gold)
    assert "gold-scenarios.yaml is not frozen" in instruments.verify(d)


# 8. approving a commit that a merge already approved is a no-op ----------------------------------------
def test_approving_a_merged_commit_again_is_a_no_op(tmp_path):
    from toprope.commits import CommitStore
    st = CommitStore(tmp_path / "c")
    base = schema_doc_domain()

    def on(raw, branch):
        p = tmp_path / f"{branch}.yaml"
        p.write_text(yaml.safe_dump(raw, sort_keys=False))
        return st.commit(p, branch=branch)[0]
    c0 = on(base, "work")
    st.approve("example", c0.id, "ana")
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    a["glossary"]["a"] = "A."
    b["glossary"]["b"] = "B."
    ca, cb = on(a, "a"), on(b, "b")
    st.approve("example", ca.id, "ana")
    assert st.approve("example", cb.id, "ana").parents == [ca.id, cb.id]
    assert st.approve("example", cb.id, "ana") is None
