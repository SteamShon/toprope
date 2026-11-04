"""`toprope-deploy`: the local deploy adapter (ADR-0022).

  toprope-deploy --env .toprope/envs/local preview my.domain.yaml
  toprope-deploy --env .toprope/envs/local deploy BUILD_ID --approver ana
  toprope-deploy --env .toprope/envs/local status

`deploy` enforces the fixed floor: an untainted build, a passing harness, a person
approving, and no stranded objects. Serve the deployed version with
`toprope-server $(toprope-deploy --env ENV server-args) --identity ...`.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from ..types import Actor
from . import DeployRefused, LocalEnvironment


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="toprope-deploy", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("declaration")
    d = sub.add_parser("deploy")
    d.add_argument("build")
    d.add_argument("--approver", required=True, help="the person approving (your id)")
    sub.add_parser("status")
    sub.add_parser("server-args")
    args = ap.parse_args(argv)
    env = LocalEnvironment(args.env)
    try:
        if args.cmd == "preview":
            b = env.preview(args.declaration)
            print(json.dumps(asdict(b), indent=2))
            raise SystemExit(0 if b.harness_ok else 1)
        if args.cmd == "deploy":
            print(json.dumps(env.deploy(args.build, Actor(args.approver, "person")), indent=2))
        elif args.cmd == "status":
            print(json.dumps({"current": env.current(), "history": env.history()[-10:]}, indent=2))
        else:
            print(" ".join(env.server_args()))
    except DeployRefused as e:
        raise SystemExit(f"refused ({e.rule}): {e.reason}") from None


if __name__ == "__main__":
    main()
