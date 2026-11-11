"""`toprope-harness`: run the generated harness on a declaration.

  toprope-harness --domain d.domain.yaml [--levels model,execution,mcp] [--json report.json]
  toprope-harness --domain authoring.domain.yaml --receiver delivery.domain.yaml@1

A domain with handoffs is checked against each receiver's published interface first; an
unknown receiver is an error, so every handoff's contract is checked before the harness runs.

  toprope-harness --composition self.composition.yaml   (members, wiring, then each member)
  toprope-harness --domain d.domain.yaml --mutants       (can the harness fail? see below)
  toprope-harness --domain d.domain.yaml --tla DIR       (the model level for TLC, ADR-0043)

Exit status 1 if there is any finding (a failing cell test, an invariant violation, a parity,
replay or race failure, a failing flow, or an exploration counterexample).

With --mutants, the harness runs once per seeded break of the declaration, given to the
execution level only: a skipped precondition, a dropped role, a skipped effect, or a cell
refused, retargeted or allowed. Each must be caught. Exit status 1 if any survives: it is a
break the harness cannot see.
"""

from __future__ import annotations

import argparse
import json
import sys

from ..decl import load_domain, validate_domain
from .run import DEFAULT_LEVELS, run_harness


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-harness", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", help="one declaration (or use --composition)")
    ap.add_argument("--composition", help="a *.composition.yaml: check members and wiring (ADR-0026), "
                                          "then run the harness on every member")
    ap.add_argument("--levels", default=",".join(DEFAULT_LEVELS), help="comma-separated: model, execution, mcp")
    ap.add_argument("--examples", type=int, default=200, help="exploration examples (0 disables)")
    ap.add_argument("--depth", type=int, default=5, help="exploration depth")
    ap.add_argument("--json", help="write the full report as JSON to this path")
    ap.add_argument("--regen-check", action="store_true",
                    help="with --composition: the regeneration check (ADR-0028): serve from declarations, run, "
                         "regenerate, compare, and run every kernel call end to end")
    ap.add_argument("--tla", metavar="DIR",
                    help="with --domain: write the model level as a TLA+ module and TLC config (ADR-0043), "
                         "with the actions left out of the model")
    ap.add_argument("--mutants", action="store_true",
                    help="with --domain: check that the harness catches each seeded break (exit 1 if one survives)")
    ap.add_argument("--receiver", action="append", default=[], metavar="FILE[@MAJOR]",
                    help="a receiving domain's declaration, with its published interface major "
                         "(default 1): checks this domain's handoffs against it (ADR-0024)")
    return ap


def main(argv: list[str] | None = None) -> None:
    ap = build_parser()
    args = ap.parse_args(argv)

    if bool(args.domain) == bool(args.composition):
        ap.error("give exactly one of --domain or --composition")
    if args.composition:
        _composition(args)
        return
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
            path, at, major = spec.rpartition("@")
            if not at or not major.isdigit():
                path, major = spec, "1"     # no "@MAJOR" suffix: the default major
            try:
                r = load_domain(path)
            except (OSError, ValueError) as e:
                print(f"error receiver {spec}: {e}", file=sys.stderr)
                raise SystemExit(1) from None
            published[r.domain] = (r, int(major))
        contract = check_handoffs(d, published)
        if contract:
            for i in contract:
                print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
            raise SystemExit(1)
    if args.tla:
        from ..tla import export, write
        e = export(d)
        write(e, args.tla)
        print(f"wrote {args.tla}/{e.name}.tla: {len(e.steps)} step(s); left out: "
              + (", ".join(f"{k} ({v})" for k, v in sorted(e.left_out.items())) or "nothing"))
        raise SystemExit(0)
    if args.mutants:
        from .mutants import run_mutants
        out = run_mutants(d)
        print(f"mutants: {len(out['killed'])} of {out['total']} caught")
        for m in out["survived"]:
            print(f"  survived {m['mutant']}: {m['break']}")
        if args.json:
            with open(args.json, "w") as f:
                json.dump(out, f, indent=2, default=str)
        raise SystemExit(0 if not out["survived"] else 1)
    levels = tuple(x.strip() for x in args.levels.split(",") if x.strip())
    report = run_harness(d, levels=levels, explore_examples=args.examples, explore_depth=args.depth)
    print(report.summary())
    unready = [i for i in validate_domain(d) if i.code == "unassigned-actor"]
    if unready:                    # it passes, but tests nothing anyone may do yet (an imported draft)
        print(f"not ready: {len(unready)} of {len(d.actions)} action(s) no one may take yet")
        for i in unready:
            print(f"  warning [{i.code}] {i.where}: {i.message}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report.to_json(), f, indent=2, default=str)
    raise SystemExit(0 if report.ok else 1)



def _composition(args) -> None:
    if args.regen_check:
        from .regen import regen_check
        levels = tuple(x.strip() for x in args.levels.split(",") if x.strip())
        out = regen_check(args.composition, levels=levels, examples=args.examples)
        print(json.dumps(out, indent=2, default=str))
        if args.json:
            with open(args.json, "w") as f:
                json.dump(out, f, indent=2, default=str)
        raise SystemExit(0 if out["ok"] else 1)
    from ..compose import check_composition, load_composition
    try:
        c = load_composition(args.composition)
    except ValueError as e:
        print(f"error {e}", file=sys.stderr)
        raise SystemExit(1) from None
    issues = check_composition(c)
    if issues:
        for i in issues:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    levels = tuple(x.strip() for x in args.levels.split(",") if x.strip())
    ok, reports = True, {}
    for name, d in sorted(c.domains.items()):
        r = run_harness(d, levels=levels, explore_examples=args.examples, explore_depth=args.depth)
        print(f"== {name}\n{r.summary()}")
        ok &= r.ok
        reports[name] = r.to_json()
    if args.json:
        with open(args.json, "w") as f:
            json.dump(reports, f, indent=2, default=str)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
