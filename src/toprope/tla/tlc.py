"""Run TLC on a declaration's model level and judge the result (ADR-0043). Used by the `tla`
job (`tools/tla_check.py`) and by the change check when a TLC jar is configured."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from ..decl import Domain
from . import BOUND, export, write

OK, VIOLATION = 0, 12          # TLC's exit statuses: no error; a safety (invariant) violation
PASSING = ("checked", "violation: known")   # a known break: the harness already fails on it


def model_check(d: Domain, jar: Path, out: Path, stem: str) -> dict[str, Any]:
    """Export `d`, run TLC on it with one worker in `out/stem`, and replay a violation on the
    interpreter. `verdict` is TLC's; `judged` adds the replay's (see PASSING)."""
    e = export(d)
    dirp = Path(out) / stem
    write(e, dirp)
    trace = dirp / f"{e.name}.trace.json"
    cmd = ["java", "-XX:+UseParallelGC", "-cp", str(jar), "tlc2.TLC", "-workers", "1", "-metadir",
           str(dirp / "states"), "-dumpTrace", "json", str(trace), "-config", f"{e.name}.cfg", f"{e.name}.tla"]
    r = subprocess.run(cmd, cwd=dirp, capture_output=True, text=True, check=False)
    (dirp / "tlc.out").write_text(r.stdout + r.stderr)
    m = re.findall(r"(\d+) distinct states found", r.stdout)
    distinct = int(m[-1]) if m else None
    broken = re.findall(r"Invariant (\S+) is violated", r.stdout)
    verdict = ("checked" if r.returncode == OK else "violation" if r.returncode == VIOLATION
               else f"error (exit {r.returncode})")
    if distinct is not None and distinct >= BOUND - 1:
        verdict = "not checked: the state bound was reached"
    replay = None
    if r.returncode == VIOLATION:
        from .replay import harness_broken, judge, parse_trace
        inv, steps = parse_trace(r.stdout)
        replay = judge(d, inv, steps, harness_broken(d))
    judged = verdict if replay is None else \
        f"violation: {replay['verdict']}" + (f" ({replay['why']})" if replay.get("why") else "")
    return {"module": e.name, "dir": stem, "replay": replay, "verdict": verdict, "judged": judged,
            "distinct_states": distinct, "broken": broken, "steps": len(e.steps), "left_out": e.left_out,
            "trace": str(trace) if trace.exists() else None}
