"""`toprope-author`: the domain owner's authoring commands.

  toprope-author init [DIR]                 write a starter toprope.workspace.yaml
  toprope-author serve [--workspace DIR]    the authoring MCP over stdio (for your agent)
  toprope-author questions [--workspace DIR] [--stage NAME]
  toprope-author progress [--workspace DIR]
  toprope-author fetch [SOURCE_ID] [--workspace DIR]   fetch link sources into snapshots
  toprope-author skip STAGE --reason TEXT             an optional stage has nothing
  toprope-author commit [-m MESSAGE] [--branch B] [--merge C] [--as NAME]
                                                      compile the working copy into a commit on a
                                                      branch (ADR-0029, ADR-0033; default `work`)
  toprope-author diff [FROM] TO                       what changed directly between two commits
  toprope-author merge [--branch B]                   bring main into the working copy; lists conflicts
  toprope-author branches                             every branch and the commit it points to
  toprope-author log ELEMENT [--at COMMIT]            an element's history (ADR-0032), e.g. action:launch
  toprope-author change-check [COMMIT] [--since C] [--env DIR] [--examples N] [--no-cache] [--full]
                                                      the change check (ADR-0009), incremental (ADR-0013),
                                                      recorded on the commit; exits 1 when it fails
  toprope-author checkout COMMIT [--force]            load a commit into the working copy (a revert,
                                                      once committed)
  toprope-author approve COMMIT [--as NAME] [--yes]     merge a commit into main and tag it (only you)
  toprope-author confirm (PATH... | --all-proposed) [--workspace DIR] [--yes] [--as NAME]   only you confirm (recorded as your git identity)
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
    cm.add_argument("--branch", default="work")
    cm.add_argument("--merge", default=None, help="the commit whose conflicts this working copy resolves")
    cm.add_argument("--as", dest="author", default="", help="your name: the commit's author")
    lg = sub.add_parser("log")
    lg.add_argument("element")
    lg.add_argument("--at", default=None)
    lg.add_argument("--workspace", default=".")
    ck = sub.add_parser("change-check")
    ck.add_argument("commit", nargs="?")
    ck.add_argument("--branch", default="work")
    ck.add_argument("--since", default=None, help="the base commit (default: the merge base with main)")
    ck.add_argument("--env", default=None, help="a deploy environment, for log replay and in-flight objects")
    ck.add_argument("--examples", type=int, default=50)
    ck.add_argument("--no-cache", action="store_true", help="run every test; reuse no result")
    ck.add_argument("--full", action="store_true", help="also run uncached and list selection misses")
    ck.add_argument("--workspace", default=".")
    co = sub.add_parser("checkout")
    co.add_argument("commit")
    co.add_argument("--force", action="store_true", help="discard changes no commit holds")
    co.add_argument("--workspace", default=".")
    mg = sub.add_parser("merge")
    mg.add_argument("--branch", default="work")
    mg.add_argument("--workspace", default=".")
    br = sub.add_parser("branches")
    br.add_argument("--workspace", default=".")
    df = sub.add_parser("diff")
    df.add_argument("commits", nargs="+", help="[FROM] TO")
    df.add_argument("--workspace", default=".")
    ap_ = sub.add_parser("approve")
    ap_.add_argument("commit")
    ap_.add_argument("--as", dest="who", default=None, help="your name: the approver (default: your git identity)")
    ap_.add_argument("--workspace", default=".")
    ap_.add_argument("--yes", action="store_true")
    c = sub.add_parser("confirm")
    c.add_argument("paths", nargs="*")
    c.add_argument("--all-proposed", action="store_true",
                   help="confirm every element still proposed (they are listed first; you still answer y/N)")
    c.add_argument("--workspace", default=".")
    c.add_argument("--yes", action="store_true", help="do not prompt (you are confirming as the owner)")
    c.add_argument("--as", dest="who", default=None, help="your name (default: your git user.name <user.email>)")
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
            print(json.dumps(ws.commit(args.message, branch=args.branch, merge=args.merge, author=args.author), indent=2))
        elif args.cmd == "log":
            print(json.dumps(ws.element_log(args.element, args.at), indent=2, ensure_ascii=False))
        elif args.cmd == "change-check":
            out = ws.change_check(args.commit, branch=args.branch, since=args.since, env=args.env,
                                  examples=args.examples, cache=not args.no_cache, full=args.full)
            print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
            if not out["ok"] or out.get("selection_misses"):
                raise SystemExit(1)
        elif args.cmd == "checkout":
            print(json.dumps(ws.checkout(args.commit, force=args.force), indent=2))
        elif args.cmd == "merge":
            print(json.dumps(ws.merge_main(args.branch), indent=2, default=str))
        elif args.cmd == "branches":
            print(json.dumps(ws.commits.refs(ws.draft()["domain"]), indent=2))
        elif args.cmd == "diff":
            frm, to = (None, args.commits[0]) if len(args.commits) == 1 else args.commits[:2]
            print(json.dumps(ws.commits.diff(ws.draft()["domain"], frm, to), indent=2))
        elif args.cmd == "approve":
            args.who = args.who or ws.identity()
            if not args.who:
                raise SystemExit("approve needs --as NAME: no git identity or login name found")
            if not args.yes:
                if not sys.stdin.isatty():
                    raise SystemExit("approve needs your terminal (or --yes when you run it yourself)")
                if input(f"Approve {args.commit} as {args.who}? [y/N] ").strip().lower() != "y":
                    raise SystemExit("not approved")
            print(json.dumps(ws.approve_commit(args.commit, via="cli", who=args.who), indent=2))
        elif args.cmd == "confirm":
            if args.all_proposed:
                args.paths = ws._proposed(ws.draft())
                if not args.paths:
                    raise SystemExit("nothing is proposed: everything is confirmed")
            elif not args.paths:
                raise SystemExit("name the elements to confirm, or use --all-proposed")
            if args.yes:
                print("Confirming:\n" + "\n".join(f"  {p}" for p in args.paths), file=sys.stderr)
            if not args.yes:
                if not sys.stdin.isatty():
                    raise SystemExit("confirm needs your terminal (or --yes when you run it yourself)")
                print("Confirm as right:\n" + "\n".join(f"  {p}" for p in args.paths))
                if input("[y/N] ").strip().lower() != "y":
                    raise SystemExit("not confirmed")
            print(json.dumps(ws.confirm(args.paths, via="cli", who=args.who), indent=2))
    except AuthoringError as e:
        raise SystemExit(f"error: {e}") from None


if __name__ == "__main__":
    main()
