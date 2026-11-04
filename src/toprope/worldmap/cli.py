"""`toprope-worldmap`: compile a declaration's world map (ADR-0020).

  toprope-worldmap --domain d.domain.yaml --out world-map.json [--harness] [--mermaid DIR]

With --harness, the harness runs first and its per-edge results are part of the map.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..decl import load_domain, validate_domain
from . import build_world_map, to_mermaid


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-worldmap", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--out", default="world-map.json")
    ap.add_argument("--harness", action="store_true", help="run the harness and include its results")
    ap.add_argument("--harness-report", help="use an existing harness report JSON instead")
    ap.add_argument("--mermaid", help="also write structure.mmd and <Object>.states.mmd here")
    args = ap.parse_args(argv)

    d = load_domain(args.domain)
    errors = [i for i in validate_domain(d) if i.severity == "error"]
    if errors:
        for i in errors:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    report = None
    if args.harness_report:
        report = json.loads(Path(args.harness_report).read_text())
    elif args.harness:
        from ..harness import run_harness
        report = run_harness(d).to_json()
    wmap = build_world_map(d, report)
    Path(args.out).write_text(json.dumps(wmap, indent=2, sort_keys=True) + "\n")
    if args.mermaid:
        out = Path(args.mermaid)
        out.mkdir(parents=True, exist_ok=True)
        mm = to_mermaid(wmap)
        (out / "structure.mmd").write_text(mm["structure"] + "\n")
        for obj, text in mm["states"].items():
            (out / f"{obj}.states.mmd").write_text(text + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
