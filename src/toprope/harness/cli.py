"""`toprope-harness`: run the generated harness on a declaration.

  toprope-harness --domain d.domain.yaml [--levels model,execution,mcp] [--json report.json]
  toprope-harness --domain authoring.domain.yaml --receiver delivery.domain.yaml@1

A domain with handoffs is checked against each receiver's published interface first; an
unknown receiver is an error, so every handoff's contract is checked before the harness runs.

Exit status 1 if there is any finding (a failing cell test, an invariant violation, a parity,
replay or race failure, a failing flow, or an exploration counterexample).
"""

from __future__ import annotations

import argparse
import json
import sys

from ..decl import load_domain, validate_domain
from .run import DEFAULT_LEVELS, run_harness


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--levels", default=",".join(DEFAULT_LEVELS))
    ap.add_argument("--examples", type=int, default=200, help="exploration examples (0 disables)")
    ap.add_argument("--depth", type=int, default=5, help="exploration depth")
    ap.add_argument("--json", help="write the full report as JSON to this path")
    ap.add_argument("--receiver", action="append", default=[], metavar="FILE[@MAJOR]",
                    help="a receiving domain's declaration, with its published interface major "
                         "(default 1): checks this domain's handoffs against it (ADR-0024)")
    args = ap.parse_args(argv)

    d = load_domain(args.domain)
    errors = [i for i in validate_domain(d) if i.severity == "error"]
    if errors:
        for i in errors:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    if d.handoffs or args.receiver:
        from ..decl import check_handoffs
        published = {}
        for spec in args.receiver:
            path, _, major = spec.partition("@")
            r = load_domain(path)
            published[r.domain] = (r, int(major or 1))
        contract = check_handoffs(d, published)
        if contract:
            for i in contract:
                print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
            raise SystemExit(1)
    levels = tuple(x.strip() for x in args.levels.split(",") if x.strip())
    report = run_harness(d, levels=levels, explore_examples=args.examples, explore_depth=args.depth)
    print(report.summary())
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report.to_json(), f, indent=2, default=str)
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
