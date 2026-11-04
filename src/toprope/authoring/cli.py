"""`toprope-author`: the domain owner's authoring commands.

  toprope-author init [DIR]                 write a starter toprope.workspace.yaml
  toprope-author serve [--workspace DIR]    the authoring MCP over stdio (for your agent)
  toprope-author questions [--workspace DIR]
  toprope-author confirm PATH... [--workspace DIR] [--yes]   only you confirm
  toprope-author check [--workspace DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import CONFIG, AuthoringError, Workspace

STARTER = """\
# Toprope authoring workspace (ADR-0014). Paths are relative to this file.
domain: drafts/my.domain.yaml
interview_log: interview/log.jsonl
usage_log: interview/sources-used.jsonl
# budget_minutes: 240            # the interview's time budget (stop rule)
# event_store: sqlite:events.db  # attempts recorded here raise question priority
sources:
  - {id: repo, kind: repository, path: src}
  - {id: docs, kind: records, path: docs}
  # - {id: sessions, kind: transcripts, path: notes/sessions, local_only: true}
  - {id: interview, kind: interview-log, path: interview/log.jsonl}
# redact:                        # extra patterns, on top of secrets and personal data
#   - {name: internal-host, pattern: "[a-z0-9-]+\\\\.corp\\\\.example"}
# exclude: ["private/**"]        # never read (held-out instruments are always excluded)
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-author", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("dir", nargs="?", default=".")
    for name in ("serve", "questions", "check"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", default=".")
    c = sub.add_parser("confirm")
    c.add_argument("paths", nargs="+")
    c.add_argument("--workspace", default=".")
    c.add_argument("--yes", action="store_true", help="do not prompt (you are confirming as the owner)")
    args = ap.parse_args(argv)

    if args.cmd == "init":
        target = Path(args.dir) / CONFIG
        if target.exists():
            raise SystemExit(f"{target} exists")
        target.write_text(STARTER)
        print(f"wrote {target}")
        return
    try:
        ws = Workspace(args.workspace)
        if args.cmd == "serve":
            from .mcp import build_authoring_server
            build_authoring_server(ws).run("stdio")
        elif args.cmd == "questions":
            print(json.dumps(ws.questions(), indent=2, ensure_ascii=False))
        elif args.cmd == "check":
            out = ws.check()
            print(json.dumps(out, indent=2, ensure_ascii=False))
            raise SystemExit(0 if out.get("parses") and out.get("harness", {}).get("ok", False) else 1)
        elif args.cmd == "confirm":
            if not args.yes:
                if not sys.stdin.isatty():
                    raise SystemExit("confirm needs your terminal (or --yes when you run it yourself)")
                print("Confirm as right:\n" + "\n".join(f"  {p}" for p in args.paths))
                if input("[y/N] ").strip().lower() != "y":
                    raise SystemExit("not confirmed")
            print(json.dumps(ws.confirm(args.paths, via="cli"), indent=2))
    except AuthoringError as e:
        raise SystemExit(f"error: {e}") from None


if __name__ == "__main__":
    main()
