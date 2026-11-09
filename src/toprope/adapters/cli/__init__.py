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

A `toprope.yaml` in the current directory (or `--config FILE`) gives the options a composition
needs, so a command is just the action (ADR-0049, C3):

  composition: domains/toprope-self.composition.yaml
  kernel_root: .
  workspace: toprope.authoring.workspace.yaml
  env: .toprope/env

  toprope-run approve_commit authoring 7-92bc...     # the member is the one with that action

An option on the command line wins over the file. A `--domain` or `--composition` on the command
line ignores the file, as does `--no-config`: the file's paths belong to its own composition.
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
from ...errors import fixed
from ...identity import Caller, Identity

READS = ("get", "history", "allowed", "whoami", "guide")
CONFIG = "toprope.yaml"
# The keys `toprope.yaml` may set, and the option each one stands for.
CONFIG_KEYS = {"composition": "--composition", "member": "--member", "kernel_root": "--kernel-root",
               "workspace": "--workspace", "env": "--env", "store_dir": "--store-dir",
               "identity": "--identity", "failures": "--failures"}


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
                    "toprope.identity.yaml; the default when that file is here), github[:FILE] (the "
                    "approver of a GitHub run, ADR-0039), static:FILE or jwt")
    ap.add_argument("--token", help="your credential (default: TOPROPE_TOKEN)")
    ap.add_argument("--kernel-root", help="run declared kernel-service effects on files under this directory")
    ap.add_argument("--workspace", help="authoring workspace, for the source services")
    ap.add_argument("--env", help="local deploy environment, for the preview and deploy services")
    ap.add_argument("--seed", action="store_true", help="load the declaration's example fixtures first")
    ap.add_argument("--key", help="idempotency key (default: a new one); reuse it to retry safely")
    ap.add_argument("--working-copy", action="store_true", help="with --composition and --kernel-root: run "
                    "each member from its working-copy file, not from its deployed commit (ADR-0045)")
    ap.add_argument("--config", help=f"the options file (default: {CONFIG} in the current directory, if any)")
    ap.add_argument("--no-config", action="store_true", help=f"ignore {CONFIG}")
    ap.add_argument("--failures", help="a directory where a command that fails before the gate is recorded, "
                    "one file per failure (ADR-0049, D1b)")
    return ap


def read_config(path: Path) -> dict[str, str]:
    """`toprope.yaml`: option defaults for a composition. Every error names the fix."""
    import yaml
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except OSError as e:
        raise SystemExit(fixed(f"{path}: cannot read it ({e.strerror})", "give --config FILE, or --no-config")) from None
    except yaml.YAMLError as e:
        raise SystemExit(fixed(f"{path}: not valid YAML ({e})", "fix the file, or give --no-config")) from None
    if not isinstance(data, dict):
        raise SystemExit(fixed(f"{path}: expected a mapping such as `composition: x.composition.yaml`",
                               "fix the file, or give --no-config"))
    unknown = sorted(set(data) - set(CONFIG_KEYS))
    if unknown:
        raise SystemExit(fixed(f"{path}: unknown key(s) {', '.join(unknown)}",
                               f"use only the keys {', '.join(CONFIG_KEYS)}"))
    base = path.parent
    out = {}
    for key, value in data.items():
        if not isinstance(value, (str, int, float)):
            raise SystemExit(fixed(f"{path}: `{key}` must be a single value", "give one value, such as a path"))
        value = str(value)
        # A path in the file is relative to the file, so the file works from anywhere.
        if key in ("composition", "kernel_root", "workspace", "env", "store_dir", "failures"):
            value = str((base / value)) if not Path(value).is_absolute() else value
        elif key == "identity" and value.split(":", 1)[0] in ("git", "github", "static"):
            kind, _, file = value.partition(":")
            if kind in ("git", "github") and not file:
                file = "toprope.identity.yaml"      # the default file, next to this one
            if file:
                value = f"{kind}:{file if Path(file).is_absolute() else base / file}"
        out[key] = value
    return out


def with_config(argv: list[str]) -> list[str]:
    """The command line with `toprope.yaml`'s options added where the command line has none."""
    pre, _ = _base_parser(add_help=False).parse_known_args(argv)
    if pre.domain or pre.composition or pre.no_config:
        return argv
    path = Path(pre.config) if pre.config else Path(CONFIG)
    if not path.is_file():
        if pre.config:
            raise SystemExit(fixed(f"{path}: no such file", f"give the path of a {CONFIG}, or leave --config out"))
        return argv
    added = []
    for key, value in read_config(path).items():
        if getattr(pre, key) in (None, False):
            added += [CONFIG_KEYS[key], value]
    return added + argv


def infer_member(argv: list[str]) -> list[str]:
    """With a composition and no --member: the member whose actions include the command."""
    pre, rest = _base_parser(add_help=False).parse_known_args(argv)
    if not pre.composition or pre.member:
        return argv
    cmd = next((a for a in rest if not a.startswith("-")), None)
    from ...compose import load_composition
    from ..mcp.cli import running_commits
    try:
        c = load_composition(pre.composition, running_commits(pre))
    except (OSError, ValueError) as e:
        raise SystemExit(f"error {e}") from None
    if cmd is None:
        members = ", ".join(sorted(c.domains))
        if not ({"-h", "--help"} & set(argv)):
            raise SystemExit(fixed("no action given", f"give an action, or --member (one of {members}) "
                                     "with --help to list its actions"))
        _base_parser(add_help=True).print_help()
        print(f"\nmembers of {pre.composition}: {members}; `--member <member> --help` lists its actions")
        raise SystemExit(0)
    members = sorted(n for n, d in c.domains.items() if cmd in d.actions)
    if len(members) == 1:
        return ["--member", members[0], *argv]
    if cmd in READS:
        raise SystemExit(fixed(f"{cmd} reads one member", f"give --member, one of {', '.join(sorted(c.domains))}"))
    if members:
        raise SystemExit(fixed(f"{cmd} is an action of {', '.join(members)}", "give --member"))
    raise SystemExit(fixed(f"{cmd}: no member of {pre.composition} has this action",
                           "check the spelling; `toprope-run --member <member> --help` lists the actions"))


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
        raise SystemExit(fixed("--identity is required for this command", f"give --identity, or put {FILE} here"))
    if spec == "git" or spec.startswith("git:"):
        try:
            return GitIdentity(spec[4:] or FILE, once=True)        # one command per process
        except (OSError, ValueError) as e:
            raise SystemExit(f"identity file: {e}") from None
    if spec == "github" or spec.startswith("github:"):      # the approver of a GitHub run (ADR-0039)
        from ...identity.github import GitHubApprovalIdentity
        try:
            return GitHubApprovalIdentity(spec[7:] or FILE)
        except (OSError, ValueError) as e:
            raise SystemExit(f"identity file: {e}") from None
    return open_identity(spec)


def _caller(identity: Identity, token: str | None) -> Caller:
    caller = identity.resolve(token)
    if caller is None:
        explain = getattr(identity, "explain", None)    # the local identities say why
        raise SystemExit(explain() if explain else "TOPROPE_TOKEN (or --token) does not resolve to a caller")
    return caller


def _confirm_on_terminal(identity: Identity, caller: Caller, action: str, target: str) -> None:
    """A git identity is self-asserted, so an action that requires a person is confirmed on a
    terminal: a process without one (an agent's ordinary shell, a script) cannot take it as you.
    It is a guard against mistakes, not a security boundary: a process can fake a terminal."""
    from ...identity.git import GitIdentity
    if not isinstance(identity, GitIdentity) or caller.actor.kind != "person":
        return
    if not sys.stdin.isatty():
        raise SystemExit(fixed(f"{action} requires a person", "run it yourself on a terminal, or through a human "
                                "request (tools/human_request.py)"))
    if input(f"{action} {target} as {caller.actor.id}? [y/N] ").strip().lower() != "y":
        raise SystemExit(fixed("not taken", "answer `y` to take it"))


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
    """What the command set off (`Outbox.followed`), as `then` shows it."""
    from ...handoff import Outbox
    return [{k: v for k, v in e.items() if k not in ("resolution", "reply_status")}
            for e in Outbox(ex).followed(target, before)]


def _domain(args: Any) -> Domain:
    if bool(args.domain) == bool(args.composition) or bool(args.composition) != bool(args.member):
        raise SystemExit(fixed("no declaration given", "give --domain, or --composition with --member, "
                                    f"or put a {CONFIG} here"))
    if args.domain:
        d = load_domain(args.domain)
    else:
        from ...compose import load_composition
        from ..mcp.cli import running_commits
        d = load_composition(args.composition, running_commits(args)).domains[args.member]
    errors = [i for i in validate_domain(d) if i.severity == "error"]
    if errors:
        for i in errors:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(fixed(f"the declaration has {len(errors)} error(s), listed above",
                               "fix them, then run `toprope-harness --domain <file>` to check"))
    return d


SECRET_OPTIONS = ("--token",)


def record_failure(directory: str | Path, argv: list[str], kind: str, message: str) -> Path:
    """One file per failed command, so two branches never write the same file. The command line
    is kept without secrets; who ran it is the git email, when there is one."""
    import datetime
    import subprocess
    shown, skip = [], False
    for a in argv:
        if skip:
            shown.append("***")
            skip = False
        elif a in SECRET_OPTIONS:
            shown.append(a)
            skip = True
        elif any(a.startswith(o + "=") for o in SECRET_OPTIONS):
            shown.append(a.split("=", 1)[0] + "=***")
        else:
            shown.append(a)
    try:
        who = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True,
                             timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        who = None
    now = datetime.datetime.now(datetime.timezone.utc)
    entry = {"at": now.isoformat(timespec="seconds"), "by": who, "argv": shown, "kind": kind,
             "message": message, "has_fix": "Fix: " in message}
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n")
    return path


def main(argv: list[str] | None = None) -> None:
    """Run one command. A command that fails before the gate (a usage error, a refused option,
    a crash) is recorded under `--failures` (or `failures:` in toprope.yaml), so F1 counts it."""
    raw = list(sys.argv[1:] if argv is None else argv)
    failures = None
    try:
        args = with_config(raw)
        failures = _base_parser(add_help=False).parse_known_args(args)[0].failures
        _main(infer_member(args))
    except SystemExit as e:
        if failures and e.code not in (None, 0, 1):        # 1: denied or rejected at the gate, recorded there
            record_failure(failures, raw, "usage" if e.code == 2 else "refused",
                           "argparse usage error" if e.code == 2 else str(e.code))
        raise
    except Exception as e:                                  # noqa: BLE001 - a crash is a failure too
        if failures:
            record_failure(failures, raw, "crash", f"{type(e).__name__}: {e}")
        raise


def _main(argv: list[str]) -> None:
    pre, _ = _base_parser(add_help=False).parse_known_args(argv)
    if not (pre.domain or pre.composition):
        _base_parser(add_help=True).parse_args(argv or ["--help"])
        raise SystemExit(fixed("no declaration given", "give --domain, or --composition with --member, "
                                    f"or put a {CONFIG} here"))
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
    from ...identity.github import GitHubApprovalIdentity
    if isinstance(ex.identity, (GitIdentity, GitHubApprovalIdentity)):
        caller = _caller(ex.identity, token)          # says why the caller is not listed
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
