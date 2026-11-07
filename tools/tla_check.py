"""Model-check declarations with TLC (ADR-0043). Run by .github/workflows/tla.yml.

    python tools/tla_check.py --jar tla2tools.jar [--out DIR] DECLARATION[=breaks:INVARIANT]...

For each declaration: export its model level (`toprope.tla`), run TLC on it with one worker,
and report the distinct states, the actions left out, and TLC's verdict. A run fails when TLC
cannot check the model (a parse or semantic error, exit status other than 0 or 12), or when it
reaches the state bound: a bound reached is never a pass. `DECLARATION=breaks:INVARIANT` names a
seeded break: that run fails unless TLC finds the invariant broken, so the job shows it can fail.

An invariant violation (TLC exit status 12) is replayed on the interpreter (`toprope.tla.replay`,
ADR-0043, Decision 3): a break the harness already reports passes here (the harness fails on it);
a harness gap or a model mismatch fails. A seeded break passes only when TLC finds it and the
replay reproduces it.
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
    d = out / decl.name.removesuffix(".domain.yaml")       # several declarations can share a domain name
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
    judged = None
    if r.returncode == VIOLATION:
        from toprope.tla.replay import harness_broken, judge, parse_trace
        decl_d = load_domain(decl)
        inv, steps = parse_trace(r.stdout)
        judged = judge(decl_d, inv, steps, harness_broken(decl_d))
    return {"declaration": str(decl), "module": e.name, "dir": d.name, "replay": judged, "verdict": verdict, "distinct_states": distinct,
            "broken": broken, "steps": len(e.steps), "left_out": e.left_out,
            "trace": str(trace) if trace.exists() else None}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jar", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("tla-out"))
    ap.add_argument("declarations", nargs="+")
    a = ap.parse_args(argv)
    results = []
    for spec in a.declarations:
        path, _, expect = spec.partition("=breaks:")
        r = run(Path(path), a.jar.resolve(), a.out.resolve())
        rep = r["replay"]
        if expect:
            r["expected_break"] = expect
            if expect not in r["broken"]:
                r["verdict"] = f"seeded break not found: {expect} (TLC: {r['verdict']})"
            elif rep["verdict"] == "model mismatch":
                r["verdict"] = f"seeded break not reproduced: {rep['why']}"
            else:
                r["verdict"] = f"seeded break found and reproduced ({rep['verdict']})"
        elif rep is not None:
            r["verdict"] = f"violation: {rep['verdict']}" + (f" ({rep['why']})" if rep.get("why") else "")
        results.append(r)
    for r in results:
        print(f"{r['declaration']}: {r['verdict']}; {r['distinct_states']} distinct states; "
              f"{r['steps']} step(s) modeled" + (f"; broken: {', '.join(r['broken'])}" if r["broken"] else ""))
        for k, v in sorted(r["left_out"].items()):
            print(f"  left out {k}: {v}")
        for st in (r["replay"] or {}).get("steps", []):
            print(f"  replayed {st['role']} {st['action']} {st['target']} {st['params']}: "
                  f"{st['status']} {st['code'] or ''}")
    (a.out / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    passing = ("checked", "violation: known")
    bad = [r for r in results if not (r["verdict"] in passing or r["verdict"].startswith("seeded break found"))]
    for r in bad:
        print(f"error: {r['declaration']}: {r['verdict']} (see {a.out}/{r['dir']}/tlc.out)", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
