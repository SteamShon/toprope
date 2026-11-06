"""`toprope-commits`: read a domain's commit store and a deploy environment (ADR-0029, ADR-0032).

Read only. Everything that changes a working copy, a commit, `main` or an environment is a
declared action of the Authoring or Delivery domain, taken with `toprope-run` (ADR-0037).

  toprope-commits branches DOMAIN                   every branch and the commit it points to
  toprope-commits log DOMAIN ELEMENT [--at COMMIT]  an element's history, e.g. action:launch
  toprope-commits diff DOMAIN [FROM] TO             what changed directly between two commits
  toprope-commits checks DOMAIN COMMIT              the newest record of each check on a commit
  toprope-commits deployed --env DIR                what an environment runs, its recent history,
                                                    and the arguments to serve it with toprope-server
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from . import CommitError, CommitStore


DOMAIN = "the domain's name, as its declaration's `domain:` says"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="toprope-commits", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commits", default=".toprope/commits", help="the commit store")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")
    sub.add_parser("branches", help="every branch and the commit it points to").add_argument("domain", help=DOMAIN)
    lg = sub.add_parser("log", help="an element's history (ADR-0032)")
    lg.add_argument("domain", help=DOMAIN)
    lg.add_argument("element", help="an element key, e.g. action:launch_experiment")
    lg.add_argument("--at", default=None, help="read from this commit (default: main, else the work head)")
    df = sub.add_parser("diff", help="what changed directly between two commits")
    df.add_argument("domain", help=DOMAIN)
    df.add_argument("ids", nargs="+", metavar="[FROM] TO", help="two commits, or one: what it has since nothing")
    ck = sub.add_parser("checks", help="the newest record of each check on a commit")
    ck.add_argument("domain", help=DOMAIN)
    ck.add_argument("commit", help="a commit id, e.g. 4-b0c8834e25d9bbc7")
    dp = sub.add_parser("deployed", help="what a deploy environment runs")
    dp.add_argument("--env", required=True, help="the environment directory, e.g. .toprope/env")
    return ap


def run(args: argparse.Namespace) -> Any:
    if args.cmd == "deployed":
        from ..deploy import DeployRefused, LocalEnvironment
        env = LocalEnvironment(args.env)
        try:
            serve = env.server_args()
        except DeployRefused:
            serve = None
        return {"current": env.current(), "history": env.history()[-10:], "server_args": serve}
    st = CommitStore(args.commits)
    if not st.log(args.domain):
        raise CommitError(f"no commits for domain {args.domain!r} in {args.commits}")
    if args.cmd == "checks":
        st.get(args.domain, args.commit)                 # an unknown commit is an error, not {}
    if args.cmd == "branches":
        return st.refs(args.domain)
    if args.cmd == "log":
        return st.element_log(args.domain, args.element, args.at)
    if args.cmd == "diff":
        if len(args.ids) > 2:
            raise CommitError("diff takes [FROM] TO")
        frm, to = (None, args.ids[0]) if len(args.ids) == 1 else args.ids
        return st.diff(args.domain, frm, to)
    return st.check_status(args.domain, args.commit)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        out = run(args)
    except CommitError as e:
        raise SystemExit(f"error: {e}") from None
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
