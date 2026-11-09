"""A command that fails before the gate is recorded, one file each (ADR-0049, D1b)."""
import json
from pathlib import Path

import pytest

from toprope.adapters.cli import main, record_failure

ROOT = Path(__file__).resolve().parents[1]
REFUNDS = ROOT / "examples/refunds"


def recorded(d):
    return [json.loads(p.read_text()) for p in sorted(Path(d).glob("*.json"))]


def run(*argv):
    with pytest.raises(SystemExit) as e:
        main(list(argv))
    return e.value.code


def test_a_usage_error_is_recorded(tmp_path, capsys):
    f = tmp_path / "failures"
    assert run("--failures", str(f), "--domain", str(REFUNDS / "refunds.domain.yaml"), "refund_order") == 2
    [entry] = recorded(f)
    assert entry["kind"] == "usage" and entry["argv"][-1] == "refund_order" and entry["has_fix"] is False


def test_a_refused_option_is_recorded_with_its_message_and_fix(tmp_path, capsys):
    f = tmp_path / "failures"
    code = run("--failures", str(f), "--composition", str(ROOT / "domains/toprope-self.composition.yaml"),
               "--kernel-root", str(ROOT), "aprove_commit", "x")
    [entry] = recorded(f)
    assert entry["kind"] == "refused" and entry["message"] == code and entry["has_fix"] is True


def test_a_denial_at_the_gate_is_not_a_failure_here(tmp_path, capsys):
    f = tmp_path / "failures"
    assert run("--failures", str(f), "--domain", str(REFUNDS / "refunds.domain.yaml"), "--store",
               f"sqlite:{tmp_path / 'e.db'}", "--seed", "--identity", f"static:{REFUNDS / 'tokens.yaml'}",
               "--token", "t-sam", "refund_order", "O-8") == 1
    assert recorded(f) == []           # the gate records its own refusals


def test_without_a_directory_nothing_is_recorded(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    run("--domain", str(REFUNDS / "refunds.domain.yaml"), "refund_order")
    assert list(tmp_path.rglob("*.json")) == []


def test_a_token_is_never_recorded(tmp_path):
    p = record_failure(tmp_path, ["--token", "s3cret", "--token=s3cret", "x"], "usage", "m")
    entry = json.loads(p.read_text())
    assert "s3cret" not in p.read_text()
    assert entry["argv"] == ["--token", "***", "--token=***", "x"]


def test_two_failures_write_two_files(tmp_path):
    a = record_failure(tmp_path, ["x"], "usage", "m")
    b = record_failure(tmp_path, ["x"], "usage", "m")
    assert a != b and len(list(tmp_path.glob("*.json"))) == 2


def test_the_repository_records_its_failures_under_toprope():
    import yaml
    assert yaml.safe_load((ROOT / "toprope.yaml").read_text())["failures"] == ".toprope/failures"
