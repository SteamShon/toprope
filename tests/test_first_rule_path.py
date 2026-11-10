"""ADR-0053's named path for F2, end to end, on a workflow of its own (travel bookings):
`toprope-init` (a template, or a sentence) -> the person's own rule, by command -> `toprope-try`
shows it -> `toprope-run` enforces it on the domain's store. Only commands touch the files: the
test checks before each command that nothing changed since the last one, and never writes a file.
"""
import hashlib
import json
from pathlib import Path

import pytest

from toprope.adapters.cli import main as run
from toprope.adapters.cli.rule import add_main, rename_main, rule_main
from toprope.adapters.cli.start import init_main, try_main


class Commands:
    """Runs commands, and fails if any file under `root` changes between two of them."""

    def __init__(self, root: Path, monkeypatch, capsys):
        self.root, self.mp, self.capsys = root, monkeypatch, capsys
        self.seen = self._files()

    def _files(self) -> dict[str, str]:
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(self.root.rglob("*")) if p.is_file() and ".toprope" not in p.parts}

    def __call__(self, command, *argv: str, cwd: Path | None = None, refused: bool = False,
                 refused_with: str | None = None) -> str:
        assert self._files() == self.seen, "a file changed outside a command"
        if cwd is not None:
            self.mp.chdir(cwd)
        if refused_with:
            with pytest.raises(SystemExit, match=refused_with):
                command(list(argv))
        elif refused:
            with pytest.raises(SystemExit) as e:
                command(list(argv))
            assert e.value.code == 1
        else:
            command(list(argv))
        self.seen = self._files()
        return self.capsys.readouterr().out


def enforced_on_the_store(do: Commands, where: Path, field: str, approve: str, rule: str) -> None:
    out = do(run, "submit_request" if approve == "approve_trip" else "submit_trip_request", "R-wiki",
             f"--{field}", "2500", "--token", "t-mia", cwd=where)
    assert json.loads(out)["state"][field] == 2500
    denied = json.loads(do(run, approve, "R-wiki", "--token", "t-max", refused=True))
    assert denied["code"] == rule
    assert denied["reason"] == f"When {field} > 2000, only director may {approve.replace('_', ' ')}."
    ok = json.loads(do(run, approve, "R-wiki", "--token", "t-kim"))       # the director the rule added
    assert ok["status"] == "ok" and ok["state"]["status"] == "approved"


def test_from_a_template_to_an_own_rule_enforced_on_the_store(tmp_path, monkeypatch, capsys):
    do = Commands(tmp_path, monkeypatch, capsys)
    do(init_main, "trips", "--template", "approval", "--dir", str(tmp_path))
    where = tmp_path / "trips"
    do(rename_main, "AccessRequest", "Trip", "--dir", str(where))
    do(rename_main, "approve_request", "approve_trip", "--dir", str(where))
    do(add_main, "--dir", str(where), "field", "cost", "--set-by", "submit_request", "--default", "0")
    do(rule_main, "--dir", str(where), "threshold", "--action", "approve_trip", "--when", "cost > 2,000",
       "--needs", "director")
    shown = do(try_main, "--dir", str(where))                            # exits 0: the story ends as told
    assert "-> denied: When cost > 2000, only director may approve trip." in shown
    enforced_on_the_store(do, where, "cost", "approve_trip", "cost-over-2000-needs-director")


def test_from_a_sentence_to_an_own_rule_enforced_on_the_store(tmp_path, monkeypatch, capsys):
    do = Commands(tmp_path, monkeypatch, capsys)
    said = do(init_main, "A traveller files a trip request; a manager approves or rejects it. "
                         "A request over 2,000 needs a director.", "--name", "trips", "--dir", str(tmp_path))
    assert "rules drafted from your sentence" in said
    where = tmp_path / "trips"
    assert "amount-over-2000-needs-director  (approve_trip_request)" in do(rule_main, "--dir", str(where), "list")
    do(rule_main, "--dir", str(where), "confirm", refused_with="needs a person at a terminal")  # not by a script
    shown = do(try_main, "--dir", str(where))
    assert "-> denied: When amount > 2000, only director may approve trip request." in shown
    enforced_on_the_store(do, where, "amount", "approve_trip_request", "amount-over-2000-needs-director")
