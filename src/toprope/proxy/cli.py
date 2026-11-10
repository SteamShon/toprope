"""`toprope-proxy`: a declaration's rules in front of an existing MCP server (ADR-0052).

    TOPROPE_TOKEN=t-sam toprope-proxy --domain shop.domain.yaml --binding binding.yaml \\
        --identity static:tokens.yaml --store sqlite:shop.db --audit audit.jsonl

An agent connects to this command (stdio) instead of the server the binding names. It is offered
the bound tools only; each gated call is checked against the declaration before it is sent, and
recorded. The proxy refuses to start when the binding and the declaration disagree.

Binding (YAML): `upstream: {command: [...]}` or `{url: ...}`; `tools: {<tool>: {action, target |
new_id, params, result} | {read: true}}`. See `toprope.proxy`.
"""
from __future__ import annotations

import argparse
import os
import sys

from ..errors import fixed


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-proxy", description=__doc__, allow_abbrev=False,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", required=True, help="the declaration whose rules gate the calls")
    ap.add_argument("--binding", required=True, help="the binding: the upstream server and which tool is which action")
    ap.add_argument("--identity", required=True, help="static:FILE (token -> caller) or jwt, as for toprope-server")
    ap.add_argument("--store", default="memory", help="memory (default), sqlite:FILE, postgres:DSN or jsonl:DIR")
    ap.add_argument("--audit", help="append every call, gated or read, to this JSONL file")
    ap.add_argument("--no-seed", action="store_true", help="do not load the declaration's example fixtures")
    return ap


def main(argv: list[str] | None = None) -> None:
    from ..adapters.mcp.cli import open_identity, open_store
    from ..decl import load_domain
    from ..exec import Execution
    from . import Binding, Upstream, UpstreamServices, build_proxy, check, register

    a = build_parser().parse_args(argv)
    binding = Binding.load(a.binding)
    domain = load_domain(a.domain)
    identity = open_identity(a.identity)
    token = os.environ.get("TOPROPE_TOKEN")
    if identity.resolve(token) is None:
        raise SystemExit(fixed("TOPROPE_TOKEN is missing or does not resolve to a caller",
                               "set TOPROPE_TOKEN to a token in the identity file"))
    upstream = Upstream.open(binding.upstream)
    problems = register(binding, upstream.tools())
    problems += check(domain, binding)
    if problems:
        upstream.close()
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        raise SystemExit(1)
    ex = Execution(domain, open_store(a.store), identity, services=UpstreamServices(upstream))
    if not a.no_seed:
        ex.seed_world()
    try:
        build_proxy(ex, binding, upstream, lambda: token, audit=a.audit).run("stdio")
    finally:
        upstream.close()


__all__ = ["build_parser", "main"]
