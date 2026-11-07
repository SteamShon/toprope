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
import subprocess  # noqa: F401  (tests replace TLC's run through it)
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from toprope.decl import load_domain
from toprope.tla.tlc import PASSING, model_check


def run(decl: Path, jar: Path, out: Path) -> dict:
    # several declarations can share a domain name: one directory per file
    r = model_check(load_domain(decl), jar, out, decl.name.removesuffix(".domain.yaml"))
    return {"declaration": str(decl), **r}


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
        else:
            r["verdict"] = r["judged"]
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
    bad = [r for r in results if not (r["verdict"] in PASSING or r["verdict"].startswith("seeded break found"))]
    for r in bad:
        print(f"error: {r['declaration']}: {r['verdict']} (see {a.out}/{r['dir']}/tlc.out)", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
