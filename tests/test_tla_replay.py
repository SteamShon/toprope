"""Replaying a TLC counterexample on the interpreter, and the `tla` job's verdicts (ADR-0043,
Decision 3). TLC itself runs only in the `tla` job; here its output is given as text."""
import subprocess
import sys
from pathlib import Path

import pytest

from toprope.decl import load_domain
from toprope.tla.replay import GAP, KNOWN, MISMATCH, Step, harness_broken, judge, parse_trace, parse_value

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tla_check  # noqa: E402

PAID = ROOT / "examples/paid-media/paid-media.domain.yaml"
SEEDED = ROOT / "tests/tla/paid-media.no-holdout-guard.domain.yaml"

# TLC's trace for the seeded break, as TLC prints it: a value may wrap across lines.
TRACE = '''Error: Invariant Inv_holdouts_never_change is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ last = <<"init">>
/\\ obj = ("C-holdout" :> [id |-> <<"s", "C-holdout">>, change |-> <<"s", "none">>, daily_budget |-> <<"i", 800>>, exception_approved |-> <<"n">>, holdout |-> <<"b", TRUE>>, name |-> <<"s", "Search, holdout">>, proposed_budget |-> <<"n">>, proposed_by |-> <<"n">>])

State 2: <Step_propose_budget_change_analyst line 68, col 39 to line 77, col 120 of module Toprope_paid_media>
/\\ last = << "propose_budget_change",
   "analyst",
   "C-holdout",
   <<<<"daily_budget", <<"i", 1>>>>, <<"reason", <<"s", "x">>>>>> >>
/\\ obj = ("C-holdout" :> [id |-> <<"s", "C-holdout">>, change |-> <<"s", "proposed">>, daily_budget |-> <<"i", 800>>, exception_approved |-> <<"n">>, holdout |-> <<"b", TRUE>>, name |-> <<"s", "Search, holdout">>, proposed_budget |-> <<"i", 1>>, proposed_by |-> <<"s", "analyst-1">>])

34 states generated, 34 distinct states found, 31 states left on queue.
'''


def test_tlc_values_and_the_trace_are_read():
    assert parse_value('<<"a", 3, TRUE, <<>>, <<-1>>>>') == ("a", 3, True, (), (-1,))
    assert parse_value('"say \\"hi\\""') == 'say "hi"'
    with pytest.raises(ValueError):
        parse_value("[x |-> 1]")                                       # records are not in `last`
    inv, steps = parse_trace(TRACE)
    assert inv == "Inv_holdouts_never_change"
    assert steps == [Step("propose_budget_change", "analyst", "C-holdout", {"daily_budget": 1, "reason": "x"})]
    assert parse_value('<<"s", "u:' + "é".encode().hex() + '">>') and \
        parse_trace(TRACE.replace('<<"s", "x">>', '<<"s", "u:' + "é".encode().hex() + '">>'))[1][0].params["reason"] == "é"


def test_a_reproduced_break_is_known_or_a_harness_gap_and_anything_else_a_mismatch():
    seeded, example = load_domain(SEEDED), load_domain(PAID)
    inv, steps = parse_trace(TRACE)
    assert "holdouts-never-change" in harness_broken(seeded)
    assert judge(seeded, inv, steps, harness_broken(seeded))["verdict"] == KNOWN
    assert judge(seeded, inv, steps, set())["verdict"] == GAP          # had the harness not found it
    wrong = judge(example, inv, steps, set())                          # the example keeps its precondition
    assert wrong["verdict"] == MISMATCH and "not-a-holdout" in wrong["why"]
    assert judge(seeded, "Inv_nothing", steps, set())["verdict"] == MISMATCH


@pytest.fixture
def fake_tlc(monkeypatch):
    """`tools/tla_check.py` with TLC's run replaced: (exit status, stdout) per declaration stem."""
    outputs = {}
    real = subprocess.run

    def run(cmd, cwd=None, **kw):
        if cmd[0] != "java":
            return real(cmd, cwd=cwd, **kw)
        code, out = outputs[Path(cwd).name]
        return subprocess.CompletedProcess(cmd, code, out, "")
    monkeypatch.setattr(tla_check.subprocess, "run", run)
    return outputs


def test_the_job_passes_a_checked_model_and_a_reproduced_seeded_break(tmp_path, fake_tlc, capsys):
    fake_tlc["paid-media"] = (0, "133686 distinct states found, 0 states left on queue.\n")
    fake_tlc["paid-media.no-holdout-guard"] = (12, TRACE)
    assert tla_check.main(["--jar", "x.jar", "--out", str(tmp_path), str(PAID),
                           f"{SEEDED}=breaks:Inv_holdouts_never_change"]) == 0
    out = capsys.readouterr().out
    assert "paid-media.domain.yaml: checked; 133686 distinct states" in out
    assert "seeded break found and reproduced (known)" in out


@pytest.mark.parametrize("stem,code,text,decl,why", [
    ("paid-media", 12, TRACE, PAID, "violation: model mismatch"),          # TLC's path is not the interpreter's
    ("paid-media", 255, "Parse error\n", PAID, "error (exit 255)"),
    ("paid-media", 0, "1000000 distinct states found\n", PAID, "not checked: the state bound was reached"),
    ("paid-media.no-holdout-guard", 0, "37 distinct states found\n", SEEDED, "seeded break not found"),
])
def test_the_job_fails_what_it_cannot_trust(tmp_path, fake_tlc, capsys, stem, code, text, decl, why):
    fake_tlc[stem] = (code, text)
    spec = f"{decl}=breaks:Inv_holdouts_never_change" if decl == SEEDED else str(decl)
    assert tla_check.main(["--jar", "x.jar", "--out", str(tmp_path), spec]) == 1
    assert why in capsys.readouterr().err


CREATED = ROOT / "tests/tla/delivery.created-deployed.domain.yaml"
CREATE_TRACE = '''Error: Invariant Inv_deployed_builds_passed_their_harness is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ last = <<"init">>
/\\ obj = <<>>

State 2: <Create_request_delivery_system line 80, col 1 to line 86, col 9 of module Toprope_delivery>
/\\ last = << "request_delivery",
   "system",
   "new-DeliveryRequest",
   << <<"domain_id", <<"s", "x">>>>, <<"commit", <<"s", "x">>>>, <<"interface", <<"s", "x">>>>,
      <<"environment", <<"s", "x">>>>, <<"approver", <<"s", "x">>>> >> >>
/\\ obj = <<>>
'''


def test_a_break_made_by_creation_is_replayed_too():
    """The seeded creation break (the `tla` job requires TLC to find it): replay takes the
    creating step as the `system` actor a handoff is, and the invariant guard refuses it."""
    seeded, plain = load_domain(CREATED), load_domain(ROOT / "domains/delivery/delivery.domain.yaml")
    inv, steps = parse_trace(CREATE_TRACE)
    assert inv == "Inv_deployed_builds_passed_their_harness"
    assert judge(seeded, inv, steps, harness_broken(seeded))["verdict"] in (KNOWN, GAP)
    assert judge(plain, inv, steps, set())["verdict"] == MISMATCH    # without the seeded effect
    workflow = (ROOT / ".github/workflows/tla.yml").read_text()
    assert "delivery.created-deployed.domain.yaml=breaks:Inv_deployed_builds_passed_their_harness" in workflow


ORIGINLESS = ROOT / "tests/tla/authoring.origin-optional.domain.yaml"
LINK_TRACE = '''Error: Invariant Inv_elements_cite_a_source is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ last = <<"init">>
/\\ obj = <<>>

State 2: <Create_propose_element_owner line 300, col 1 to line 306, col 9 of module Toprope_authoring>
/\\ last = << "propose_element",
   "owner",
   "new-Element",
   << <<"path", <<"s", "x">>>>, <<"cites", <<"s", "x">>>>, <<"value", <<"s", "x">>>> >> >>
/\\ obj = <<>>
'''


def test_a_break_read_through_a_link_is_replayed_too():
    """The seeded link break: an Element created citing no Source breaks elements-cite-a-source,
    whose check follows the `origin` link. Replay reproduces it; Authoring itself refuses the
    step, since its `origin` is required."""
    seeded, plain = load_domain(ORIGINLESS), load_domain(ROOT / "domains/authoring/authoring.domain.yaml")
    inv, steps = parse_trace(LINK_TRACE)
    assert judge(seeded, inv, steps, harness_broken(seeded))["verdict"] in (KNOWN, GAP)
    assert judge(plain, inv, steps, set())["verdict"] == MISMATCH
    workflow = (ROOT / ".github/workflows/tla.yml").read_text()
    assert "authoring.origin-optional.domain.yaml=breaks:Inv_elements_cite_a_source" in workflow


STALE = ROOT / "tests/tla/example.stale-draft.domain.yaml"
TIME_TRACE = '''Error: Invariant Inv_approved_while_fresh is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
/\\ last = <<"init">>
/\\ obj = <<>>

State 2: <Step_approve_experiment_approver line 90, col 1 to line 96, col 9 of module Toprope_example>
/\\ last = <<"approve_experiment", "approver", "E-onboarding", <<>>>>
/\\ obj = <<>>
'''


def test_a_break_through_time_is_replayed_on_the_same_clock():
    """The seeded time break: a draft stamped 60 days before the clock is approved, and
    approved-while-fresh (days_since <= 30) breaks. Replay runs on the harness's clock, as the
    model does, so it reproduces it; without the stamp, it does not."""
    import yaml
    inv, steps = parse_trace(TIME_TRACE)
    seeded = load_domain(STALE)
    assert judge(seeded, inv, steps, harness_broken(seeded))["verdict"] in (KNOWN, GAP)
    raw = yaml.safe_load(STALE.read_text())
    for fx in raw["world"]["fixtures"]:
        for data in fx.values():
            data.pop("drafted_at", None)
    from toprope.decl import Domain
    assert judge(Domain.model_validate(raw), inv, steps, set())["verdict"] == MISMATCH
    workflow = (ROOT / ".github/workflows/tla.yml").read_text()
    assert "example.stale-draft.domain.yaml=breaks:Inv_approved_while_fresh" in workflow
