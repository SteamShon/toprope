"""`toprope-proxy`: a declaration's rules in front of an existing MCP server (ADR-0052).

    TOPROPE_TOKEN=t-sam toprope-proxy --domain shop.domain.yaml --binding binding.yaml \\
        --identity static:tokens.yaml --store sqlite:shop.db --audit audit.jsonl

An agent connects to this command (stdio) instead of the server the binding names. It is offered
the bound tools only; each gated call is checked against the declaration before it is sent, and
recorded. The proxy refuses to start when the binding and the declaration disagree.

Binding (YAML): `upstream: {command: [...]}` or `{url: ...}`; `tools: {<tool>: {action, target |
new_id, params, result} | {read: true}}`. See `toprope.proxy`. `toprope-import mcp` drafts one
from the server's tool list, marked `status: proposed`; a person confirms it (ADR-0052 §7):

    toprope-proxy --check --domain shop.domain.yaml --binding binding.yaml        # agree? then exit
    TOPROPE_TOKEN=t-dana toprope-proxy --confirm-binding --domain shop.domain.yaml \
        --binding binding.yaml --identity static:tokens.yaml
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
    ap.add_argument("--identity", help="static:FILE (token -> caller), jwt or git, as for toprope-server")
    ap.add_argument("--store", help="sqlite:FILE or jsonl:DIR: the gate's record, shared with a lock by "
                                    "every proxy on it")
    ap.add_argument("--audit", help="append every call, gated or read, to this JSONL file")
    ap.add_argument("--no-seed", action="store_true", help="do not load the declaration's example fixtures")
    ap.add_argument("--check", action="store_true", help="check that the binding, the server's tools and the "
                    "declaration agree, as at start, and exit")
    ap.add_argument("--confirm-binding", action="store_true", help="as a person: check the drafted binding as at "
                    "start, then mark it confirmed, naming you")
    return ap


def _problems(binding, domain, upstream) -> list[str]:
    from . import check, register
    return register(binding, upstream.tools(), domain) + check(domain, binding)


def _confirm(a, binding, domain) -> None:
    """A person confirms a drafted binding: only one the proxy would start with, as themselves."""
    import re
    from dataclasses import replace
    from datetime import UTC, datetime
    from pathlib import Path

    from ..adapters.cli import _confirm_on_terminal
    from ..adapters.mcp.cli import open_identity
    from . import Upstream
    if not a.identity:
        raise SystemExit(fixed("--confirm-binding needs --identity", "give the identity that says who you are"))
    identity = open_identity(a.identity)
    caller = identity.resolve(os.environ.get("TOPROPE_TOKEN"))
    if caller is None:
        raise SystemExit(fixed("TOPROPE_TOKEN is missing or does not resolve to a caller",
                               "set TOPROPE_TOKEN to your token in the identity file"))
    if caller.actor.kind != "person":
        raise SystemExit(fixed(f"{caller.actor.id} is an agent; only a person confirms a binding (ADR-0041)",
                               "ask the person the agent acts for to run it"))
    text = Path(a.binding).read_text()
    if binding.status != "proposed":
        print(f"{a.binding} is already confirmed")
        return
    upstream = Upstream.open(binding.upstream)
    try:
        problems = _problems(replace(binding, status="confirmed"), domain, upstream)
    finally:
        upstream.close()
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        raise SystemExit(fixed(f"{a.binding} would not start, so it was not confirmed", "fix what is listed, then "
                               "confirm it again"))
    _confirm_on_terminal(identity, caller, "confirm-binding", a.binding, text)
    at = datetime.now(UTC).isoformat(timespec="seconds")
    new, n = re.subn(r"(?m)^status:\s*proposed\s*$",
                     f"status: confirmed\nconfirmed_by: {caller.actor.id!r}\nconfirmed_at: {at!r}", text, count=1)
    if not n:
        raise SystemExit(fixed(f"{a.binding} says `status: proposed` in a form this cannot rewrite",
                               "write `status: proposed` on its own line, then confirm again"))
    Path(a.binding).write_text(new)
    print(f"confirmed {a.binding} as {caller.actor.id}")


def main(argv: list[str] | None = None) -> None:
    from ..adapters.mcp.cli import open_identity, open_store
    from ..decl import load_domain
    from ..exec import Execution
    from . import (
        Binding,
        StoreLock,
        Upstream,
        UpstreamServices,
        build_proxy,
    )

    a = build_parser().parse_args(argv)
    if a.confirm_binding or a.check:
        binding, domain = Binding.load(a.binding), load_domain(a.domain)
        if a.confirm_binding:
            _confirm(a, binding, domain)
            return
        upstream = Upstream.open(binding.upstream)
        try:
            problems = _problems(binding, domain, upstream)
        finally:
            upstream.close()
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        if problems:
            raise SystemExit(1)
        gated = sum(1 for t in binding.tools.values() if not t.read)
        print(f"ok: {a.binding}, the server's tools and {a.domain} agree; {gated} tool(s) gated, "
              f"{len(binding.tools) - gated} read through")
        return
    if not (a.store and a.identity):
        raise SystemExit(fixed("the proxy needs --store and --identity to serve",
                               "give both, or --check to only check the binding"))
    lock = StoreLock(a.store)                      # before anything starts: a store it cannot share is refused
    binding = Binding.load(a.binding)
    domain = load_domain(a.domain)
    identity = open_identity(a.identity)
    token = os.environ.get("TOPROPE_TOKEN")
    if identity.resolve(token) is None:
        raise SystemExit(fixed("TOPROPE_TOKEN is missing or does not resolve to a caller",
                               "set TOPROPE_TOKEN to a token in the identity file"))
    upstream = Upstream.open(binding.upstream)
    problems = _problems(binding, domain, upstream)
    if problems:
        upstream.close()
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        raise SystemExit(1)
    ex = Execution(domain, open_store(a.store), identity, services=UpstreamServices(upstream))
    if not a.no_seed:
        ex.seed_world()
    try:
        build_proxy(ex, binding, upstream, lambda: token, audit=a.audit, lock=lock).run("stdio")
    finally:
        upstream.close()


__all__ = ["build_parser", "main"]
