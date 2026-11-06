"""`toprope-server`: serve a declaration over MCP (stdio or streamable HTTP).

  toprope-server --domain d.domain.yaml --store sqlite:events.db --identity static:tokens.yaml
  toprope-server --domain d.domain.yaml --store postgres:"host=... dbname=..." --identity jwt \
                 --transport http --port 8765

Identity:
  static:FILE   YAML {token: {id, kind, roles, on_behalf_of: {id, roles}, grant: {id, actions, targets}}}
  jwt           TOPROPE_JWT_KEY (secret or public key) and TOPROPE_JWT_AUDIENCE are required;
                TOPROPE_JWT_ALG (default HS256), TOPROPE_JWT_ISSUER (verified and advertised when set)
Credentials:
  stdio  one caller per process: TOPROPE_TOKEN (must resolve at startup)
  http   per request: Authorization: Bearer <token>
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from ...decl import load_domain, load_yaml, validate_domain
from ...exec import Execution
from ...identity import Caller, Identity, StaticIdentity, str_list
from ...store import EventStore
from ...store import open_store as _open_store
from ...types import Actor, Grant


def open_store(spec: str) -> EventStore:
    try:
        return _open_store(spec)
    except ValueError as e:
        raise SystemExit(str(e)) from None


def _actor(d: dict[str, Any], kind: str | None = None) -> Actor:
    if not isinstance(d.get("id"), str):
        raise ValueError("id must be a string")
    return Actor(d["id"], kind or d.get("kind", "person"), str_list(d.get("roles", []), "roles"))


def open_identity(spec: str) -> Identity:
    if spec.startswith("static:"):
        with open(spec[7:]) as f:
            table = load_yaml(f.read()) or {}
        callers = {}
        for token, c in table.items():
            try:
                g = c.get("grant")
                callers[str(token)] = Caller(
                    _actor(c), _actor(c["on_behalf_of"], "person") if c.get("on_behalf_of") else None,
                    Grant(str(g["id"]), frozenset(str_list(g.get("actions", []), "grant.actions")),
                          None if g.get("targets") is None else frozenset(str_list(g["targets"], "grant.targets")))
                    if g else None)
            except (AttributeError, KeyError, TypeError, ValueError) as e:
                raise SystemExit(f"{spec[7:]}: caller for token {str(token)[:4]}…: {e}") from None
        return StaticIdentity(callers)
    if spec == "jwt":
        from ...identity.jwt import JWTIdentity
        try:
            return JWTIdentity(os.environ.get("TOPROPE_JWT_KEY", ""),
                               algorithms=[os.environ.get("TOPROPE_JWT_ALG", "HS256")],
                               audience=os.environ.get("TOPROPE_JWT_AUDIENCE", ""),
                               issuer=os.environ.get("TOPROPE_JWT_ISSUER"))
        except ValueError as e:
            raise SystemExit(f"jwt identity: {e} (TOPROPE_JWT_KEY, TOPROPE_JWT_AUDIENCE, TOPROPE_JWT_ALG)") from None
    raise SystemExit(f"unknown identity {spec!r}: use static:FILE or jwt")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-server", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", help="one declaration (or --composition with --member)")
    ap.add_argument("--composition", help="a *.composition.yaml (ADR-0026): every member runs in this process, "
                                          "wired; --member is the one served")
    ap.add_argument("--member", help="with --composition: the member domain to serve")
    ap.add_argument("--store-dir", help="with --composition: one SQLite store per member, <dir>/<member>.db "
                                        "(default: each member's event log, <its directory>/events)")
    ap.add_argument("--kernel-root", help="run declared kernel-service effects (ADR-0028) on files under this "
                                          "directory; without it, kernel calls stay pending")
    ap.add_argument("--workspace", help="authoring workspace, for the read_source and fetch_source services")
    ap.add_argument("--env", help="local deploy environment, for the preview and deploy services")
    ap.add_argument("--store", default=None, help="with --domain: memory (default), sqlite:FILE, postgres:DSN or "
                                               "jsonl:DIR; with --composition, memory keeps nothing")
    ap.add_argument("--identity", required=True)
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--public-url", help="URL clients use to reach this server (default http://HOST:PORT)")
    ap.add_argument("--no-seed", action="store_true", help="do not load the declaration's fixtures")
    ap.add_argument("--harness-report", help="harness report JSON (toprope-harness --json) shown in the world map")
    args = ap.parse_args(argv)

    if bool(args.domain) == bool(args.composition) or bool(args.composition) != bool(args.member):
        ap.error("give --domain, or --composition with --member")
    services = _kernel(args)
    identity = open_identity(args.identity)
    if args.composition:
        ex = _member(args, identity, services)
    else:
        domain = load_domain(args.domain)
        errors = [i for i in validate_domain(domain) if i.severity == "error"]
        if errors:
            for i in errors:
                print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
            raise SystemExit(1)
        ex = Execution(domain, open_store(args.store or "memory"), identity, services=services)
        if not args.no_seed:
            ex.seed_world()

    import json
    harness = None
    if args.harness_report:
        with open(args.harness_report) as f:
            harness = json.load(f)
    from . import build_server
    if args.transport == "stdio":
        token = os.environ.get("TOPROPE_TOKEN")
        if ex.identity.resolve(token) is None:
            print("error: TOPROPE_TOKEN is missing or does not resolve to a caller", file=sys.stderr)
            raise SystemExit(1)
        build_server(ex, lambda: token, harness=harness).run("stdio")
    else:
        from .http import run_http
        issuer = os.environ.get("TOPROPE_JWT_ISSUER") if args.identity == "jwt" else None
        run_http(ex, args.host, args.port, args.public_url, issuer, harness=harness)


def _kernel(args):
    if not args.kernel_root:
        return None
    from ...kernel.services import LocalKernel
    ws = env = None
    if args.workspace:
        from ...workspace import Workspace
        ws = Workspace(args.workspace)
    if args.env:
        from ...deploy import LocalEnvironment
        env = LocalEnvironment(args.env)
    return LocalKernel(args.kernel_root, workspace=ws, environment=env)


def member_events(c, name: str):
    """A member's event log: `<the member declaration's directory>/events` (ADR-0037)."""
    return (c.root / c.spec.members[name].declaration).parent / "events"


def _member(args, identity, services):
    """Every member of the composition, wired in this process; one store per member, so
    several processes (one per served member) share state through the same files."""
    from pathlib import Path

    from ...compose import assemble, check_composition, load_composition
    try:
        c = load_composition(args.composition)
    except ValueError as e:
        raise SystemExit(f"error {e}") from None
    issues = check_composition(c)
    if issues:
        for i in issues:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    if args.member not in c.domains:
        raise SystemExit(f"error: no member {args.member!r} in {sorted(c.domains)}")
    store = getattr(args, "store", None)
    if store not in (None, "memory"):
        raise SystemExit("error: with --composition, give --store-dir DIR or --store memory (or neither, "
                         "for each member's own event log)")
    if args.store_dir:
        Path(args.store_dir).mkdir(parents=True, exist_ok=True)
        stores = {n: open_store(f"sqlite:{Path(args.store_dir) / (n + '.db')}") for n in c.domains}
    elif store == "memory":
        stores = {n: open_store("memory") for n in c.domains}
    else:   # each member's own event log, next to its declaration and kept in git (ADR-0037)
        logs = {n: member_events(c, n).resolve() for n in c.domains}
        if len(set(logs.values())) < len(logs):
            raise SystemExit("error: members share a directory, so their event logs would mix; keep each "
                             "member under its own directory (domains/<domain>/), or give --store-dir")
        if not args.no_seed:   # the examples are not records: they never go into a log kept in git
            if getattr(args, "seed", False):
                raise SystemExit("error: --seed loads example objects; use it with --store memory or --store-dir")
            args.no_seed = True
        stores = {n: open_store(f"jsonl:{p}") for n, p in logs.items()}
    exs = assemble(c, stores, identity, services=services)
    if not args.no_seed:
        for ex in exs.values():
            ex.seed_world()
    return exs[args.member]


if __name__ == "__main__":
    main()
