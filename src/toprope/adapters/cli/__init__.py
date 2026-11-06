"""`toprope-run`: a command line generated from a declaration (ADR-0036).

The same actions as the generated MCP server (one subcommand per action), through the same
Execution, so the same rules apply: the matrix, actor rules, preconditions, invariants,
`requires: human`, kernel effects and handoffs.

  toprope-run --domain d.domain.yaml --store sqlite:events.db --identity static:ids.yaml --help
  toprope-run --domain d.domain.yaml ... approve_experiment E-1 --note "ok"
  toprope-run --composition self.composition.yaml --member authoring --store-dir .toprope/run ... deliver C2 --environment local
  toprope-run ... get ID | history ID | allowed ID | guide

The caller comes from TOPROPE_TOKEN (or --token), resolved by the identity, as for the server.
Exit status 1 when the command is denied or rejected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import Any

from ...decl import load_domain, validate_domain
from ...decl.models import Domain
from ...exec import Execution

READS = ("get", "history", "allowed", "guide")


def _base_parser(add_help: bool) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-run", description=__doc__, add_help=add_help,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", help="one declaration (or --composition with --member)")
    ap.add_argument("--composition", help="a *.composition.yaml: every member wired in this process")
    ap.add_argument("--member", help="with --composition: the member whose actions these are")
    ap.add_argument("--store", default="memory", help="with --domain: the event store (sqlite:FILE, postgres:DSN)")
    ap.add_argument("--store-dir", help="with --composition: one SQLite store per member, <dir>/<member>.db")
    ap.add_argument("--identity", help="static:FILE or jwt (as for toprope-server)")
    ap.add_argument("--token", help="your credential (default: TOPROPE_TOKEN)")
    ap.add_argument("--kernel-root", help="run declared kernel-service effects on files under this directory")
    ap.add_argument("--workspace", help="authoring workspace, for the source services")
    ap.add_argument("--env", help="local deploy environment, for the preview and deploy services")
    ap.add_argument("--seed", action="store_true", help="load the declaration's example fixtures first")
    ap.add_argument("--key", help="idempotency key (default: a new one); reuse it to retry safely")
    return ap


def _param_option(sub: argparse.ArgumentParser, name: str, spec: Any) -> None:
    conv = {"integer": int, "number": float}.get(spec.type or "", str)
    kw: dict[str, Any] = {"dest": f"p_{name}", "required": not spec.optional}
    if spec.type == "boolean":
        kw["type"] = lambda v: {"true": True, "false": False}[v.lower()]
        kw["metavar"] = "true|false"
    else:
        kw["type"] = conv
    if spec.enum:
        kw["choices"] = spec.enum
    if spec.many:
        kw["nargs"] = "+"
    what = spec.type or ("one of " + ", ".join(spec.enum) if spec.enum else f"the id of a {spec.ref}")
    sub.add_argument(f"--{name.replace('_', '-')}", help=what, **kw)


def action_help(d: Domain, name: str) -> str:
    """Who may take the action, and when, from the declaration's own words."""
    from ..mcp import describe_action
    return describe_action(d, name, d.actions[name])


def build_parser(d: Domain) -> argparse.ArgumentParser:
    ap = _base_parser(add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="ACTION")
    for name, a in d.actions.items():
        target = "the new object's id" if a.creates else f"the {a.target}'s id"
        p = sub.add_parser(name, help=(a.description or "").split("\n")[0], description=action_help(d, name))
        p.add_argument("target", help=target)
        for pname, spec in a.params.items():
            _param_option(p, pname, spec)
    for cmd, what in (("get", "an object's current state"), ("history", "an object's events"),
                      ("allowed", "the actions you may take on an object now")):
        sub.add_parser(cmd, help=what).add_argument("target")
    sub.add_parser("guide", help="the domain guide: how this domain works and who does what")
    return ap


def _execution(args: Any, d: Domain) -> Execution:
    from ..mcp.cli import _kernel, _member, open_identity, open_store
    if not args.identity:
        raise SystemExit("--identity is required for this command")
    identity = open_identity(args.identity)
    services = _kernel(args)
    if args.composition:
        args.no_seed = not args.seed
        return _member(args, identity, services)
    ex = Execution(d, open_store(args.store), identity, services=services)
    if args.seed:
        ex.seed_world()
    return ex


def _domain(args: Any) -> Domain:
    if bool(args.domain) == bool(args.composition) or bool(args.composition) != bool(args.member):
        raise SystemExit("give --domain, or --composition with --member")
    if args.domain:
        d = load_domain(args.domain)
    else:
        from ...compose import load_composition
        d = load_composition(args.composition).domains[args.member]
    errors = [i for i in validate_domain(d) if i.severity == "error"]
    if errors:
        for i in errors:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    return d


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    pre, _ = _base_parser(add_help=False).parse_known_args(argv)
    if not (pre.domain or pre.composition):
        _base_parser(add_help=True).parse_args(argv or ["--help"])
        raise SystemExit("give --domain, or --composition with --member")
    d = _domain(pre)
    args = build_parser(d).parse_args(argv)
    if args.cmd == "guide":
        from ...worldmap.guide import build_domain_guide
        print(build_domain_guide(d), end="")
        return
    ex = _execution(args, d)
    token = args.token or os.environ.get("TOPROPE_TOKEN")
    if args.cmd in READS:
        out: Any
        if args.cmd == "get":
            out = ex.state(args.target)
        elif args.cmd == "history":
            out = [{"type": e.type, "at": str(e.at), "actor": e.actor, "payload": e.payload} for e in ex.history(args.target)]
        else:
            caller = ex.identity.resolve(token)
            if caller is None:
                raise SystemExit("TOPROPE_TOKEN (or --token) does not resolve to a caller")
            out = ex.allowed_actions(args.target, caller)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return
    params = {name: getattr(args, f"p_{name}") for name in d.actions[args.cmd].params
              if getattr(args, f"p_{name}", None) is not None}
    from ..mcp import outcome_json
    o = ex.submit(token, args.cmd, args.target, params, idempotency_key=args.key or str(uuid.uuid4()))
    print(json.dumps(outcome_json(o), indent=2, ensure_ascii=False, default=str))
    if not o.ok:
        raise SystemExit(1)


__all__ = ["build_parser", "main"]
