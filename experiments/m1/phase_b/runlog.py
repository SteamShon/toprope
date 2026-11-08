"""The decision log (run protocol §4): one append-only TSV for every run of every arm.

Each row is `ts, arm, change, run, what, evidence, result`. `evidence` is a pointer (a path
relative to the log's directory, or a commit), never prose. A wrong row is never edited: a
later row supersedes it (`what` = `superseded`, naming what it replaces).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

COLUMNS = ("ts", "arm", "change", "run", "what", "evidence", "result")
NAME = "phase-b-runs.tsv"


def log_path(run_dir: Path) -> Path:
    """Beside the run directory: `experiments/m1/runs/phase-b-runs.tsv` for the default one."""
    return run_dir.parent / NAME


def _cell(v: object) -> str:
    return " ".join(str("" if v is None else v).split())        # no tab or newline inside a cell


class RunLog:
    def __init__(self, path: Path):
        self.path = path

    def pointer(self, p: Path | str) -> str:
        p = Path(p)
        try:
            return str(p.resolve().relative_to(self.path.parent.resolve()))
        except ValueError:
            return str(p)

    def append(self, arm: str, change: int | str, run: int | str, what: str, evidence: Path | str | None,
               result: object) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists()
        row = (datetime.now(UTC).isoformat(timespec="seconds"), arm, change, run, what,
               self.pointer(evidence) if isinstance(evidence, Path) else (evidence or ""), result)
        with self.path.open("a") as f:
            if new:
                f.write("\t".join(COLUMNS) + "\n")
            f.write("\t".join(_cell(x) for x in row) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().splitlines()
        return [dict(zip(COLUMNS, line.split("\t"), strict=True)) for line in lines[1:] if line]
