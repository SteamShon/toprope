"""M2 trades on a paper account only (ADR-0054 §1, `docs/experiments/M2-spec.md` §1).

  python experiments/tools/m2_paper.py check BINDING
  python experiments/tools/m2_paper.py serve -- <toprope-proxy arguments, with --binding BINDING>

`serve` reads the forwarded arguments with `toprope-proxy`'s own parser. It checks the binding the
proxy will load, and only then runs the proxy. M2's proxy is started this way and no other way.
The check refuses unless all of these hold:
- the upstream command is exactly `[uvx, alpaca-mcp-server==X.Y.Z]`: Alpaca's official server,
  pinned, with nothing that runs other code;
- the binding's `env` holds exactly `ALPACA_PAPER_TRADE: "true"`;
- `pass_env` holds exactly the two keys, so no key is written in the binding and nothing can turn
  paper trading off;
- the key ID in the environment is a paper one (it starts with `PK`). This is a second guard; the
  flag above is the first.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

PINNED = re.compile(r"alpaca-mcp-server==\d+\.\d+\.\d+")
FLAG = "ALPACA_PAPER_TRADE"
KEYS = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
PAPER_PREFIX = "PK"
SHAPE = ('`upstream: {command: [uvx, alpaca-mcp-server==X.Y.Z], env: {ALPACA_PAPER_TRADE: "true"}, '
         'pass_env: [ALPACA_API_KEY, ALPACA_SECRET_KEY]}`')


def problems(upstream: dict[str, Any], environ: Any) -> list[str]:
    if "command" not in upstream:
        return [f"the upstream is not a command. Fix: use {SHAPE}"]
    out = []
    cmd = [str(x) for x in upstream["command"]]
    if len(cmd) != 2 or cmd[0] != "uvx" or not PINNED.fullmatch(cmd[1]):
        out.append(f"the upstream command is {cmd}, not Alpaca's server pinned to a version. Fix: use {SHAPE}")
    env = {str(k): str(v) for k, v in (upstream.get("env") or {}).items()}
    if env != {FLAG: "true"}:
        out.append(f"the binding's `env` is {sorted(env)} with `{FLAG}` = {env.get(FLAG)!r}, not exactly "
                   f"`{FLAG}: \"true\"`. Fix: use {SHAPE}")
    passed = [str(n) for n in upstream.get("pass_env") or []]
    if sorted(passed) != sorted(KEYS):
        out.append(f"`pass_env` is {passed}, not exactly the two keys. Fix: use {SHAPE}")
    if not str(environ.get(KEYS[0], "")).startswith(PAPER_PREFIX):
        out.append(f"`{KEYS[0]}` in the environment is not a paper key (it does not start with `{PAPER_PREFIX}`). "
                   "Fix: use the key ID of the Alpaca paper account")
    return out


def check(binding: str | Path, environ: Any = None) -> list[str]:
    from toprope.proxy import Binding
    return problems(Binding.load(binding).upstream, os.environ if environ is None else environ)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["check"] and len(argv) == 2:
        binding = argv[1]
    elif argv[:2] == ["serve", "--"]:
        from toprope.proxy.cli import build_parser
        binding = build_parser().parse_args(argv[2:]).binding      # the binding the proxy will load
    else:
        raise SystemExit(__doc__)
    found = check(binding)
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
