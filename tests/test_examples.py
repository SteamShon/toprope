"""The refund example the README walks through (examples/refunds) gives the output it shows."""
import json
from pathlib import Path

from toprope.adapters.cli import main
from toprope.check import change_check
from toprope.decl import load_domain
from toprope.store import open_store

EX = Path(__file__).resolve().parents[1] / "examples/refunds"


def run(capsys, store, *args):
    argv = ["--domain", str(EX / "refunds.domain.yaml"), "--store", store, "--seed",
            "--identity", f"static:{EX / 'tokens.yaml'}", "--token", "t-sam", *args]
    try:
        main(argv)
    except SystemExit:
        pass
    return json.loads(capsys.readouterr().out)


def test_a_refund_after_day_7_is_refused_with_the_declared_reason(capsys, tmp_path):
    out = run(capsys, f"sqlite:{tmp_path / 'e.db'}", "refund_order", "O-8")
    assert out["status"] == "denied"
    assert out["code"] == "within-window"
    assert out["reason"] == "Refunds are allowed within 7 days of purchase."


def test_a_refund_within_the_window_runs(capsys, tmp_path):
    out = run(capsys, f"sqlite:{tmp_path / 'e.db'}", "refund_order", "O-3")
    assert out["status"] == "ok" and out["state"]["status"] == "refunded"


def test_changing_the_window_gets_the_impact_report_the_readme_shows(capsys, tmp_path):
    store = f"sqlite:{tmp_path / 'e.db'}"
    run(capsys, store, "refund_order", "O-3")
    report = change_check(load_domain(EX / "refunds.30-days.domain.yaml"),
                          load_domain(EX / "refunds.domain.yaml"), events=open_store(store))
    assert report.ok
    assert report.diff["to_review"] == ["precondition:refund_order.within-window"]
    assert report.impact["summary"] == ("changes 1 precondition(s); affects 4 cell test(s), "
                                        "1 precondition test(s), exploration; replays past refund_order")
    assert report.checks["log_replay"].ran


# -- examples/paid-media: an agent proposes ad budget changes; a person approves -------------
PM = Path(__file__).resolve().parents[1] / "examples/paid-media"


def pm(capsys, store, token, *args, seed=False):
    argv = ["--domain", str(PM / "paid-media.domain.yaml"), "--store", store,
            "--identity", f"static:{PM / 'tokens.yaml'}", "--token", token, *(["--seed"] if seed else []), *args]
    try:
        main(argv)
    except SystemExit:
        pass
    return json.loads(capsys.readouterr().out)


def test_paid_media_walkthrough_gives_the_readme_output(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-holdout", "--daily-budget", "1200",
             "--reason", "best CPA", seed=True)
    assert (out["status"], out["code"]) == ("denied", "not-a-holdout")
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-search", "--daily-budget", "2500", "--reason", "best CPA")
    assert (out["status"], out["code"]) == ("denied", "step-limit")
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-search", "--daily-budget", "1400", "--reason", "best CPA")
    assert out["status"] == "ok" and out["state"]["change"] == "proposed"
    out = pm(capsys, s, "t-bot", "approve_budget_change", "C-search")
    assert out["status"] == "denied" and out["reason"] == "Only a person can approve_budget_change."
    out = pm(capsys, s, "t-ana", "approve_budget_change", "C-search")
    assert out["status"] == "ok" and out["state"]["daily_budget"] == 1400


def test_paid_media_a_person_cannot_approve_their_own_proposal(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    pm(capsys, s, "t-eli", "propose_budget_change", "C-search", "--daily-budget", "1200", "--reason", "x", seed=True)
    out = pm(capsys, s, "t-eli", "approve_budget_change", "C-search")
    assert (out["status"], out["code"]) == ("denied", "not-the-proposer")


def test_paid_media_raising_the_step_limit_gets_an_impact_report():
    r = change_check(load_domain(PM / "paid-media.step-1000.domain.yaml"), load_domain(PM / "paid-media.domain.yaml"))
    assert r.ok and r.diff["to_review"] == ["precondition:propose_budget_change.step-limit"]
    assert r.impact["summary"] == ("changes 1 precondition(s); affects 4 cell test(s), "
                                   "14 param test(s), 3 precondition test(s), exploration; replays past propose_budget_change")


def test_paid_media_an_approval_records_the_rationale_given(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    pm(capsys, s, "t-bot", "propose_budget_change", "C-search", "--daily-budget", "1400", "--reason", "x", seed=True)
    pm(capsys, s, "t-ana", "approve_budget_change", "C-search", "--rationale", "CPA held for two weeks")
    events = open_store(s).read("C-search")
    decision = next(e for e in events if e.type == "DecisionRecorded")
    assert decision.payload["rationale"] == "CPA held for two weeks"


def test_paid_media_an_approval_without_a_rationale_records_none(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    pm(capsys, s, "t-bot", "propose_budget_change", "C-search", "--daily-budget", "1400", "--reason", "x", seed=True)
    pm(capsys, s, "t-ana", "approve_budget_change", "C-search")
    decision = next(e for e in open_store(s).read("C-search") if e.type == "DecisionRecorded")
    assert "rationale" not in decision.payload and "rationale" not in decision.payload["params"]


def test_paid_media_a_person_cannot_approve_what_their_own_agent_proposed(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-search", "--daily-budget", "1400", "--reason", "x", seed=True)
    assert out["state"]["proposed_by"] == "eli"                    # the agent's principal, not the agent
    out = pm(capsys, s, "t-eli", "approve_budget_change", "C-search")
    assert (out["status"], out["code"]) == ("denied", "not-the-proposer")


def test_paid_media_an_exception_allows_one_change_and_is_a_persons_decision(capsys, tmp_path):
    s = f"sqlite:{tmp_path / 'e.db'}"
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-holdout", "--daily-budget", "1200", "--reason", "x", seed=True)
    assert (out["status"], out["code"]) == ("denied", "not-a-holdout")
    out = pm(capsys, s, "t-bot", "grant_exception", "C-holdout")
    assert out["status"] == "denied" and out["reason"] == "Only a person can grant_exception."
    out = pm(capsys, s, "t-ana", "grant_exception", "C-holdout", "--rationale", "the test ended early")
    assert out["status"] == "ok" and out["state"]["exception_approved"] is True
    assert pm(capsys, s, "t-bot", "propose_budget_change", "C-holdout", "--daily-budget", "1200",
              "--reason", "x")["status"] == "ok"
    out = pm(capsys, s, "t-ana", "approve_budget_change", "C-holdout")
    assert out["state"]["daily_budget"] == 1200 and out["state"]["exception_approved"] is False   # used up
    out = pm(capsys, s, "t-bot", "propose_budget_change", "C-holdout", "--daily-budget", "1300", "--reason", "x")
    assert (out["status"], out["code"]) == ("denied", "not-a-holdout")
    decisions = [e.payload for e in open_store(s).read("C-holdout") if e.type == "DecisionRecorded"]
    assert [d["action"] for d in decisions] == ["grant_exception", "approve_budget_change"]
    assert decisions[0]["rationale"] == "the test ended early"
