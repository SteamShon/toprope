"""M2 trades on a paper account only (ADR-0054 §1, `docs/experiments/M2-spec.md` §1).

  python experiments/tools/m2_paper.py check BINDING
  python experiments/tools/m2_paper.py serve -- <toprope-proxy arguments, with --binding BINDING>

`serve` runs the check, then `toprope-proxy` with the same arguments; M2's proxy is started this way
and no other. The check refuses unless all of these hold:
- the upstream is a command that runs Alpaca's MCP server (`alpaca-mcp-server`), not a URL;
- the binding's `env` sets `ALPACA_PAPER_TRADE: "true"`, and nothing passes it in from outside;
- the keys come through `pass_env` (never written in the binding), and the key ID in the
  environment is a paper key (Alpaca's paper key IDs start with `PK`; live ones with `AK`);
- no variable the server gets points at Alpaca's live API (`api.alpaca.markets`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

SERVER = "alpaca-mcp-server"
FLAG = "ALPACA_PAPER_TRADE"
KEYS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
PAPER_PREFIX = "PK"
LIVE_HOST = "api.alpaca.markets"
PAPER_HOST = "paper-api.alpaca.markets"


def problems(upstream: dict[str, Any], environ: Any) -> list[str]:
    out = []
    if "command" not in upstream:
        return ["the upstream is not a command. Fix: run `alpaca-mcp-server` as the binding's `upstream.command`"]
    if not any(str(x).split("==")[0].split("@")[0] == SERVER for x in upstream["command"]):
        out.append(f"the upstream command does not run `{SERVER}`. Fix: run Alpaca's official MCP server, "
                   f"e.g. `command: [uvx, {SERVER}]`")
    env = {str(k): str(v) for k, v in (upstream.get("env") or {}).items()}
    passed = [str(n) for n in upstream.get("pass_env") or []]
    if env.get(FLAG, "").lower() != "true":
        out.append(f"the binding does not set `{FLAG}: \"true\"`. Fix: add it under `upstream.env`")
    if FLAG in passed:
        out.append(f"`{FLAG}` is passed in from the environment, which could turn paper off. "
                   f"Fix: remove it from `pass_env`; the binding sets it")
    for k in KEYS:
        if k in env:
            out.append(f"the binding writes `{k}` itself. Fix: move it to `pass_env`, and set it in the "
                       "proxy's environment")
        elif k not in passed:
            out.append(f"the server gets no `{k}`. Fix: add it to `upstream.pass_env`")
    key = environ.get(KEYS[0], "")
    if KEYS[0] in passed and not key.startswith(PAPER_PREFIX):
        out.append(f"`{KEYS[0]}` in the environment is not a paper key (it does not start with `{PAPER_PREFIX}`). "
                   "Fix: use the key ID of the Alpaca paper account")
    values = list(env.items()) + [(n, environ.get(n, "")) for n in passed]
    for name, value in values:
        if LIVE_HOST in value and PAPER_HOST not in value:
            out.append(f"`{name}` points at Alpaca's live API. Fix: remove it, or point it at `{PAPER_HOST}`")
    return out


def check(binding: str | Path, environ: Any = None) -> list[str]:
    from toprope.proxy import Binding
    return problems(Binding.load(binding).upstream, os.environ if environ is None else environ)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["check"] and len(argv) == 2:
        found = check(argv[1])
    elif argv[:2] == ["serve", "--"] and "--binding" in argv:
        found = check(argv[argv.index("--binding") + 1])
    else:
        raise SystemExit(__doc__)
    for p in found:
        print(f"error: {p}", file=sys.stderr)
    if found:
        raise SystemExit(1)
    if argv[0] == "check":
        print("paper only: the binding passes")
        return
    from toprope.proxy.cli import main as proxy
    proxy(argv[2:])


if __name__ == "__main__":
    main()
