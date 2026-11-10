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
    assert entry["kind"] == "usage" and entry["argv"][-1] == "refund_order"
    assert "the following arguments are required: target" in entry["message"]     # argparse's own words


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
    p = record_failure(tmp_path, ["--token", "s3cret", "--token=s3cret", "--tok", "s3cret", "--to=s3cret", "x"],
                       "usage", "m")
    entry = json.loads(p.read_text())
    assert "s3cret" not in p.read_text()
    assert entry["argv"] == ["--token", "***", "--token=***", "--tok", "***", "--to=***", "x"]


def test_a_shortened_token_option_is_not_accepted(tmp_path, capsys):
    f = tmp_path / "failures"
    assert run("--failures", str(f), "--domain", str(REFUNDS / "refunds.domain.yaml"), "--tok", "s3cret",
               "refund_order", "O-3") == 2
    assert "s3cret" not in (f / next(f.iterdir()).name).read_text()


def test_failures_come_from_toprope_yaml_whatever_composition_is_named(tmp_path, monkeypatch, capsys):
    (tmp_path / "toprope.yaml").write_text("failures: out\n")
    monkeypatch.chdir(tmp_path)
    run("--composition", str(ROOT / "domains/toprope-self.composition.yaml"), "--kernel-root", str(ROOT),
        "aprove_commit", "x")
    [entry] = recorded(tmp_path / "out")
    assert entry["kind"] == "refused" and "no member" in entry["message"]


def test_a_bad_config_or_a_usage_error_before_the_command_is_recorded(tmp_path, monkeypatch, capsys):
    (tmp_path / "toprope.yaml").write_text("failures: out\ncompositon: x\n")
    monkeypatch.chdir(tmp_path)
    run("get", "x")
    run("--no-config", "--failures", "out2", "--domain", str(REFUNDS / "refunds.domain.yaml"), "--store")
    assert "unknown key(s) compositon" in recorded(tmp_path / "out")[0]["message"]
    assert recorded(tmp_path / "out2")[0]["kind"] == "usage"


def test_a_crash_before_the_gate_is_recorded_and_one_after_it_is_not(tmp_path, monkeypatch, capsys):
    import toprope.adapters.cli as cli
    f = tmp_path / "failures"
    base = ("--failures", str(f), "--domain", str(REFUNDS / "refunds.domain.yaml"), "--store",
            f"sqlite:{tmp_path / 'e.db'}", "--seed", "--identity", f"static:{REFUNDS / 'tokens.yaml'}",
            "--token", "t-sam")
    monkeypatch.setattr(cli, "_execution", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        main([*base, "refund_order", "O-3"])
    assert recorded(f)[0]["kind"] == "crash" and "OSError: disk" in recorded(f)[0]["message"]
    monkeypatch.undo()
    monkeypatch.setattr(cli, "followed", lambda *a: (_ for _ in ()).throw(RuntimeError("after")))
    with pytest.raises(RuntimeError, match="after"):
        main([*base, "refund_order", "O-3"])
    assert len(recorded(f)) == 1                       # the crash after the gate is not added


def test_a_record_that_cannot_be_written_never_hides_the_failure(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert record_failure(blocker / "sub", ["x"], "usage", "m") is None
    assert "not recorded" in capsys.readouterr().err


def test_two_failures_write_two_files(tmp_path):
    a = record_failure(tmp_path, ["x"], "usage", "m")
    b = record_failure(tmp_path, ["x"], "usage", "m")
    assert a != b and len(list(tmp_path.glob("*.json"))) == 2


def test_the_repository_records_its_failures_under_toprope(monkeypatch):
    from toprope.adapters.cli import failures_dir
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("TOPROPE_FAILURES", raising=False)
    assert failures_dir(["get", "x"]) == ".toprope/failures"
