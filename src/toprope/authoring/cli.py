"""`toprope-author`: the domain owner's authoring commands.

  toprope-author init [DIR]                 write a starter toprope.workspace.yaml
  toprope-author serve [--workspace DIR]    the authoring MCP over stdio (for your agent)
  toprope-author questions [--workspace DIR] [--stage NAME]
  toprope-author progress [--workspace DIR]
  toprope-author fetch [SOURCE_ID] [--workspace DIR]   fetch link sources into snapshots
  toprope-author skip STAGE --reason TEXT             an optional stage has nothing
  toprope-author commit [-m MESSAGE]                  compile the working copy into a commit (ADR-0029)
  toprope-author diff [FROM] TO                       what changed directly between two commits
  toprope-author approve COMMIT --as NAME [--yes]     tag a commit as approved (only you)
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
  # - {id: wiki, kind: records, url: "https://example.com/process"}   # a link: run `toprope-author fetch`
# Snapshots of links are kept in .toprope/snapshots/: keep .toprope/ out of version control.
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
    for name in ("serve", "questions", "check", "progress", "fetch", "skip"):
        p = sub.add_parser(name)
        p.add_argument("--workspace", default=".")
        if name == "questions":
            p.add_argument("--stage")
        if name == "fetch":
            p.add_argument("source", nargs="?")
        if name == "skip":
            p.add_argument("stage")
            p.add_argument("--reason", required=True)
    cm = sub.add_parser("commit")
    cm.add_argument("--workspace", default=".")
    cm.add_argument("-m", "--message", default="")
    df = sub.add_parser("diff")
    df.add_argument("commits", nargs="+", help="[FROM] TO")
    df.add_argument("--workspace", default=".")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("commit")
    ap_.add_argument("--as", dest="who", required=True, help="your name: the approver")
    ap_.add_argument("--workspace", default=".")
    ap_.add_argument("--yes", action="store_true")
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
            print(json.dumps(ws.questions(stage=args.stage), indent=2, ensure_ascii=False))
        elif args.cmd == "progress":
            p = ws.progress()
            for st in p["stages"]:
                counts = ", ".join(f"{k} {v}" for k, v in st.items() if k not in ("stage", "title", "status"))
                print(f"{st['status']:>8}  {st['title']:<20} {counts}")
        elif args.cmd == "fetch":
            print(json.dumps(ws.fetch(args.source), indent=2))
        elif args.cmd == "skip":
            print(json.dumps(ws.skip_stage(args.stage, args.reason), indent=2, ensure_ascii=False))
        elif args.cmd == "check":
            out = ws.check()
            print(json.dumps(out, indent=2, ensure_ascii=False))
            raise SystemExit(0 if out.get("parses") and out.get("harness", {}).get("ok", False) else 1)
        elif args.cmd == "commit":
            print(json.dumps(ws.commit(args.message), indent=2))
        elif args.cmd == "diff":
            frm, to = (None, args.commits[0]) if len(args.commits) == 1 else args.commits[:2]
            print(json.dumps(ws.commits.diff(ws.draft()["domain"], frm, to), indent=2))
        elif args.cmd == "approve":
            if not args.yes:
                if not sys.stdin.isatty():
                    raise SystemExit("approve needs your terminal (or --yes when you run it yourself)")
                if input(f"Approve {args.commit} as {args.who}? [y/N] ").strip().lower() != "y":
                    raise SystemExit("not approved")
            print(json.dumps(ws.approve_commit(args.commit, via="cli", who=args.who), indent=2))
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
