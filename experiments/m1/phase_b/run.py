"""Run M1 Phase B (ADR-0040): the frozen change requests, in order, on one arm.

  python -m phase_b.run render --declarations DIR --out DIR      the NL arm's materials
  python -m phase_b.run arm ARM --materials DIR --out RUN_DIR [--seqs 1-2]

(from `experiments/m1`, or with it on PYTHONPATH). Before an arm runs, the frozen instruments
are verified (`instruments.py verify --run`); a run refuses to start otherwise.

The run writes, under RUN_DIR/ARM:
  manifest.json      what ran: the instruments' and materials' hashes, the prompts' hashes, the
                     model under test, the harness commit, the cost
  seq-NN/record.json one change: the edit, the findings, the deploy, the times and the cost
  seq-NN/*.jsonl     every conversation, request by request

Only the change requests are read from the instruments. The change key and the binding are not
opened here: the scorer opens them, after every arm has run (ADR-0040 §8).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .arms import PROMPTS, TextArm, nl_arm, render_skill, structured_arm
from .model import AnthropicModel, Budget, BudgetExceeded, Model

ROOT = Path(__file__).resolve().parents[3]
INSTRUMENTS = ROOT / "experiments/m1/instruments"
ARMS = {"nl": nl_arm, "structured": structured_arm}


def verify_instruments(d: Path = INSTRUMENTS) -> list[str]:
    spec = importlib.util.spec_from_file_location("instruments", ROOT / "experiments/tools/instruments.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                     # type: ignore[union-attr]
    return mod.verify(d, run=True)


def change_requests(d: Path = INSTRUMENTS) -> list[dict[str, Any]]:
    doc = yaml.safe_load((d / "change-requests.yaml").read_text())
    return sorted(doc["requests"], key=lambda r: r["seq"])


def seqs(spec: str | None, all_: list[int]) -> list[int]:
    if not spec:
        return all_
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    unknown = sorted(set(out) - set(all_))
    if unknown:
        raise SystemExit(f"no change requests {unknown}")
    return out


def harness_commit() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return r.stdout.strip() or "unknown"


def _hashes(paths: list[Path]) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def run_arm(arm: TextArm, out: Path, requests: list[dict[str, Any]], budget: Budget | None,
            model_id: str, instruments: Path = INSTRUMENTS) -> dict[str, Any]:
    """Every request in order: edit, check, deploy (flagged or not). Stops at the cost cap."""
    out.mkdir(parents=True, exist_ok=True)
    frozen = json.loads((instruments / "FROZEN.json").read_text())["files"]
    manifest: dict[str, Any] = {
        "arm": arm.name, "started_at": datetime.now(UTC).isoformat(), "model": model_id,
        "harness_commit": harness_commit(), "instruments": {f: m["sha256"] for f, m in frozen.items()},
        "materials": arm.materials_hash(), "prompts": _hashes(sorted(PROMPTS.glob("*.md"))),
        "seqs": [r["seq"] for r in requests], "done": [], "stopped": None}
    write = lambda: (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write()
    for req in requests:
        d = out / f"seq-{req['seq']:02d}"
        spent = budget.cost() if budget else 0.0
        try:
            edit = arm.edit(req, d)
            check = arm.check(req, d)
            deploy = arm.deploy(req, d)
        except BudgetExceeded as e:
            manifest["stopped"] = f"budget: {e} (at change {req['seq']})"
            break
        record = {"seq": req["seq"], "intent": req["intent"], "edit": edit.data, "check": check.data,
                  "deploy": deploy.data,
                  "seconds": {"edit": edit.seconds, "check": check.seconds, "deploy": deploy.seconds,
                              "edit_to_checked": edit.seconds + check.seconds},
                  "usd": round((budget.cost() if budget else 0.0) - spent, 4)}
        (d / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
        manifest["done"].append(req["seq"])
        write()
    manifest["finished_at"] = datetime.now(UTC).isoformat()
    manifest["cost"] = budget.report() if budget else None
    write()
    return manifest


def main(argv: list[str] | None = None, model: Model | None = None, budget: Budget | None = None) -> None:
    ap = argparse.ArgumentParser(prog="phase_b.run", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="render the NL arm's materials from the declarations")
    r.add_argument("--declarations", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path)
    a = sub.add_parser("arm", help="run the change requests on one arm")
    a.add_argument("arm", choices=sorted(ARMS))
    a.add_argument("--materials", required=True, type=Path)
    a.add_argument("--out", required=True, type=Path, help="the run directory")
    a.add_argument("--seqs", help="e.g. 1-2 for the dry run (default: all)")
    a.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    args = ap.parse_args(argv)

    if model is None:
        budget = Budget.from_env()
        model = AnthropicModel.from_env(budget)
    model_id = os.environ.get("M1_MODEL", "fake")
    if args.cmd == "render":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        render_skill(args.declarations, args.out, model, args.out.parent / f"{args.out.name}.render.jsonl")
        print(json.dumps({"rendered": str(args.out), "cost": budget.report() if budget else None}))
        return
    errs = verify_instruments(args.instruments)
    if errs:
        raise SystemExit("the instruments do not verify; nothing runs:\n" + "\n".join(errs))
    reqs = change_requests(args.instruments)
    chosen = set(seqs(args.seqs, [r["seq"] for r in reqs]))
    t = time.monotonic()
    arm = ARMS[args.arm](args.materials, args.out / args.arm, model)
    m = run_arm(arm, args.out / args.arm, [r for r in reqs if r["seq"] in chosen], budget, model_id,
                args.instruments)
    print(json.dumps({"arm": args.arm, "done": m["done"], "stopped": m["stopped"], "cost": m["cost"],
                      "seconds": round(time.monotonic() - t, 1)}))
    if m["stopped"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
