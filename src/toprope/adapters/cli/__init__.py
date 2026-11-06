"""`toprope-run`: a command line generated from a declaration (ADR-0036).

The same actions as the generated MCP server (one subcommand per action), through the same
Execution, so the same rules apply: the matrix, actor rules, preconditions, invariants,
`requires: human`, kernel effects and handoffs.

  toprope-run --domain d.domain.yaml --store sqlite:events.db --identity static:ids.yaml --help
  toprope-run --domain d.domain.yaml ... approve_experiment E-1 --note "ok"
  toprope-run --composition self.composition.yaml --member authoring --store-dir .toprope/run ... deliver C2 --environment local
  toprope-run ... get ID | history ID | allowed ID | whoami | guide

Who you are: with `--identity git` (the default when `toprope.identity.yaml` is in the current
directory and no token is given), your repository's git email, looked up in that file
(ADR-0037). An action that requires a person asks you to confirm on your terminal, so an agent's
ordinary shell cannot take it as you. With `static:FILE` or `jwt`, the caller comes from TOPROPE_TOKEN (or --token), as for the server.
Exit status 1 when the command is denied or rejected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from ...decl import load_domain, validate_domain
from ...decl.models import Domain
from ...exec import Execution
from ...identity import Caller, Identity

READS = ("get", "history", "allowed", "whoami", "guide")


def _base_parser(add_help: bool) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-run", description=__doc__, add_help=add_help,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", help="one declaration (or --composition with --member)")
    ap.add_argument("--composition", help="a *.composition.yaml: every member wired in this process")
    ap.add_argument("--member", help="with --composition: the member whose actions these are")
    ap.add_argument("--store", default=None, help="with --domain: the event store (memory, the default; sqlite:FILE, "
                    "postgres:DSN, jsonl:DIR); with --composition, memory keeps nothing")
    ap.add_argument("--store-dir", help="with --composition: one SQLite store per member, <dir>/<member>.db "
                    "(default: each member's event log, <its directory>/events, kept in git)")
    ap.add_argument("--identity", help="git[:FILE] (your git email, looked up in FILE, default "
                    "toprope.identity.yaml; the default when that file is here), static:FILE or jwt")
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
    sub.add_parser("whoami", help="who you are here, and your roles")
    sub.add_parser("guide", help="the domain guide: how this domain works and who does what")
    return ap


def _identity(spec: str | None, token: str | None = None) -> Identity:
    from ...identity.git import FILE, GitIdentity
    from ..mcp.cli import open_identity
    if spec is None and token is None and Path(FILE).is_file():     # a given token is never ignored
        spec = "git"
    if not spec:
        raise SystemExit(f"--identity is required for this command (or put {FILE} here)")
    if spec == "git" or spec.startswith("git:"):
        try:
            return GitIdentity(spec[4:] or FILE)
        except (OSError, ValueError) as e:
            raise SystemExit(f"identity file: {e}") from None
    return open_identity(spec)


def _caller(identity: Identity, token: str | None) -> Caller:
    from ...identity.git import GitIdentity
    caller = identity.resolve(token)
    if caller is None:
        raise SystemExit(identity.explain() if isinstance(identity, GitIdentity)
                         else "TOPROPE_TOKEN (or --token) does not resolve to a caller")
    return caller


def _confirm_on_terminal(identity: Identity, caller: Caller, action: str, target: str) -> None:
    """A git identity is self-asserted, so an action that requires a person is confirmed on a
    terminal: a process without one (an agent's ordinary shell, a script) cannot take it as you.
    It is a guard against mistakes, not a security boundary: a process can fake a terminal."""
    from ...identity.git import GitIdentity
    if not isinstance(identity, GitIdentity) or caller.actor.kind != "person":
        return
    if not sys.stdin.isatty():
        raise SystemExit(f"{action} requires a person: run it yourself on a terminal")
    if input(f"{action} {target} as {caller.actor.id}? [y/N] ").strip().lower() != "y":
        raise SystemExit("not taken")


def _execution(args: Any, d: Domain) -> Execution:
    from ..mcp.cli import _kernel, _member, open_store
    identity = _identity(args.identity, args.token or os.environ.get("TOPROPE_TOKEN"))
    services = _kernel(args)
    if args.composition:
        args.no_seed = not args.seed
        return _member(args, identity, services)
    ex = Execution(d, open_store(args.store or "memory"), identity, services=services)
    if args.seed:
        ex.seed_world()
    return ex


def followed(ex: Execution, d: Domain, target: str, before: int) -> list[dict[str, Any]]:
    """What the command set off: each kernel call with its reply (and the object a creating reply
    made, such as the new Commit), and each handoff, so you know what to do next."""
    from ...handoff import Outbox, effect_id, handoff_id
    out: list[dict[str, Any]] = []
    for e in ex.store.read(target)[before:]:
        if e.type == "EffectRequested":
            res = Outbox(ex).resolution(effect_id(e), "effect")
            entry: dict[str, Any] = {"kernel": e.payload["service"], "reply": e.payload["reply"]}
            if res is None:
                entry["status"] = "pending"
            else:
                result = res.payload.get("result") or {}
                reply = d.actions.get(e.payload["reply"])
                # the service's own failure first: a failed call still replies (ADR-0028)
                entry["status"] = "failed" if result.get("ok") is False else res.payload.get("status") or res.type
                entry["object"] = result.get("id") if reply is not None and reply.creates else res.payload.get("object")
                if result.get("error") or res.payload.get("reason"):
                    entry["error"] = result.get("error") or res.payload.get("reason")
            out.append(entry)
        elif e.type == "HandoffRequested":
            res = Outbox(ex).resolution(handoff_id(e), "handoff")
            to = e.payload.get("to") or {}
            out.append({"handoff": e.payload.get("handoff"), "to": f"{to.get('domain')}.{to.get('action')}",
                        "object": e.payload.get("target"), "status": res.type if res else "pending"})
    return out


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
        elif args.cmd == "whoami":
            c = _caller(ex.identity, token)
            out = {"id": c.actor.id, "kind": c.actor.kind, "roles": list(c.actor.roles)}
            if c.on_behalf_of is not None and c.grant is not None:
                out |= {"on_behalf_of": c.on_behalf_of.id, "grant": sorted(c.grant.actions)}
        else:
            out = ex.allowed_actions(args.target, _caller(ex.identity, token))
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return
    params = {name: getattr(args, f"p_{name}") for name in d.actions[args.cmd].params
              if getattr(args, f"p_{name}", None) is not None}
    from ...identity.git import GitIdentity
    if isinstance(ex.identity, GitIdentity):
        caller = _caller(ex.identity, token)          # says why the git email is not listed
        if d.actions[args.cmd].requires == "human":
            _confirm_on_terminal(ex.identity, caller, args.cmd, args.target)
    from ..mcp import outcome_json
    before = ex.store.version(args.target)
    o = ex.submit(token, args.cmd, args.target, params, idempotency_key=args.key or str(uuid.uuid4()))
    out = outcome_json(o)
    if o.ok and (follow := followed(ex, d, args.target, before)):
        out["then"] = follow
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    if not o.ok:
        raise SystemExit(1)


__all__ = ["build_parser", "main"]
