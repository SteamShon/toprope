"""Model-check declarations with TLC (ADR-0043). Run by .github/workflows/tla.yml.

    python tools/tla_check.py --jar tla2tools.jar [--out DIR] DECLARATION...

For each declaration: export its model level (`toprope.tla`), run TLC on it with one worker,
and report the distinct states, the actions left out, and TLC's verdict. A run fails when TLC
cannot check the model (a parse or semantic error, exit status other than 0 or 12), or when it
reaches the state bound: a bound reached is never a pass.

An invariant violation (TLC exit status 12) is not judged here: replaying the counterexample on
the interpreter decides whether it is a harness gap, a model mismatch or a break the harness
already reports (ADR-0043, Decision 3). TLC writes it as JSON to `<out>/<module>.trace.json`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK, VIOLATION = 0, 12          # TLC's exit statuses: no error; a safety (invariant) violation


def run(decl: Path, jar: Path, out: Path) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from toprope.decl import load_domain
    from toprope.tla import BOUND, export, write
    e = export(load_domain(decl))
    d = out / e.name
    write(e, d)
    trace = d / f"{e.name}.trace.json"
    cmd = ["java", "-XX:+UseParallelGC", "-cp", str(jar), "tlc2.TLC", "-workers", "1", "-metadir",
           str(d / "states"), "-dumpTrace", "json", str(trace), "-config", f"{e.name}.cfg", f"{e.name}.tla"]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
    (d / "tlc.out").write_text(r.stdout + r.stderr)
    m = re.findall(r"(\d+) distinct states found", r.stdout)
    distinct = int(m[-1]) if m else None
    broken = re.findall(r"Invariant (\S+) is violated", r.stdout)
    verdict = ("checked" if r.returncode == OK else "violation" if r.returncode == VIOLATION
               else f"error (exit {r.returncode})")
    if distinct is not None and distinct >= BOUND - 1:
        verdict = "not checked: the state bound was reached"
    return {"declaration": str(decl), "module": e.name, "verdict": verdict, "distinct_states": distinct,
            "broken": broken, "steps": len(e.steps), "left_out": e.left_out,
            "trace": str(trace) if trace.exists() else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jar", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("tla-out"))
    ap.add_argument("declarations", nargs="+", type=Path)
    a = ap.parse_args(argv)
    results = [run(p, a.jar.resolve(), a.out.resolve()) for p in a.declarations]
    for r in results:
        print(f"{r['declaration']}: {r['verdict']}; {r['distinct_states']} distinct states; "
              f"{r['steps']} step(s) modeled" + (f"; broken: {', '.join(r['broken'])}" if r["broken"] else ""))
        for k, v in sorted(r["left_out"].items()):
            print(f"  left out {k}: {v}")
    (a.out / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    bad = [r for r in results if r["verdict"] not in ("checked", "violation")]
    for r in bad:
        print(f"error: {r['declaration']}: {r['verdict']} (see {a.out}/{r['module']}/tlc.out)", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
