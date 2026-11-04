"""`toprope-server`: serve a declaration over MCP (stdio or streamable HTTP).

  toprope-server --domain d.domain.yaml --store sqlite:events.db --identity static:tokens.yaml
  toprope-server --domain d.domain.yaml --store postgres:"host=... dbname=..." --identity jwt \
                 --transport http --port 8765

Identity:
  static:FILE   YAML {token: {id, kind, roles, on_behalf_of: {id, roles}, grant: {id, actions, targets}}}
  jwt           TOPROPE_JWT_KEY (secret or public key), TOPROPE_JWT_ALG, TOPROPE_JWT_AUDIENCE, TOPROPE_JWT_ISSUER
Credentials:
  stdio  one caller per process: TOPROPE_TOKEN
  http   per request: Authorization: Bearer <token>
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from ...decl import load_domain, load_yaml, validate_domain
from ...exec import Execution
from ...identity import Caller, Identity, StaticIdentity
from ...store import EventStore, MemoryEventStore
from ...types import Actor, Grant


def open_store(spec: str) -> EventStore:
    if spec == "memory":
        return MemoryEventStore()
    kind, _, arg = spec.partition(":")
    if kind == "sqlite":
        from ...store.sqlite import SQLiteEventStore
        return SQLiteEventStore(arg)
    if kind == "postgres":
        from ...store.postgres import PostgresEventStore
        return PostgresEventStore(arg)
    raise SystemExit(f"unknown store {spec!r}: use memory, sqlite:PATH or postgres:DSN")


def _actor(d: dict[str, Any], kind: str | None = None) -> Actor:
    return Actor(str(d["id"]), kind or d.get("kind", "person"), tuple(d.get("roles", [])))


def open_identity(spec: str) -> Identity:
    if spec.startswith("static:"):
        with open(spec[7:]) as f:
            table = load_yaml(f.read()) or {}
        callers = {}
        for token, c in table.items():
            g = c.get("grant")
            callers[str(token)] = Caller(
                _actor(c), _actor(c["on_behalf_of"], "person") if c.get("on_behalf_of") else None,
                Grant(str(g["id"]), frozenset(g.get("actions", [])),
                      None if g.get("targets") is None else frozenset(g["targets"])) if g else None)
        return StaticIdentity(callers)
    if spec == "jwt":
        from ...identity.jwt import JWTIdentity
        return JWTIdentity(os.environ["TOPROPE_JWT_KEY"], algorithms=[os.environ.get("TOPROPE_JWT_ALG", "HS256")],
                           audience=os.environ.get("TOPROPE_JWT_AUDIENCE"), issuer=os.environ.get("TOPROPE_JWT_ISSUER"))
    raise SystemExit(f"unknown identity {spec!r}: use static:FILE or jwt")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-server", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--store", default="memory")
    ap.add_argument("--identity", required=True)
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-seed", action="store_true", help="do not load the declaration's fixtures")
    args = ap.parse_args(argv)

    domain = load_domain(args.domain)
    errors = [i for i in validate_domain(domain) if i.severity == "error"]
    if errors:
        for i in errors:
            print(f"error {i.code} at {i.where}: {i.message}", file=sys.stderr)
        raise SystemExit(1)
    ex = Execution(domain, open_store(args.store), open_identity(args.identity))
    if not args.no_seed:
        ex.seed_world()

    from . import build_server
    if args.transport == "stdio":
        token = os.environ.get("TOPROPE_TOKEN")
        build_server(ex, lambda: token).run("stdio")
    else:
        from .http import run_http
        run_http(ex, args.host, args.port)


if __name__ == "__main__":
    main()
