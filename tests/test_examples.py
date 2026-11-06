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
