"""Run M1 Phase B (ADR-0040): the frozen change requests, in order, on one arm.

Run it yourself, from `experiments/m1`, in an ordinary terminal (not inside an agent session,
which can read the repository):

  uv run python -m phase_b render --model M                      the NL arm's materials
  uv run python -m phase_b sandbox                                the Toprope arm's materials
  uv run python -m phase_b arm nl --model M --seqs 1-2           the dry run, on one arm
  uv run python -m phase_b arm nl --model M                      every change; resumes a stopped run
  uv run python -m phase_b status                                 how far each arm got

Paths default to the repository's (`experiments/m1/arms/ARM`, `experiments/m1/runs/phase-b`).
Each conversation is a fresh
`claude -p` on your own Claude Code login (`--backend cli`, the default). A progress line shows
the arm, the change, the role and the turn; every conversation is written as it happens to
`seq-NN/<role>.jsonl`, so `tail -f` follows it.

Stopping is safe: Ctrl-C, or your usage limit, stops the run and keeps every finished change.
Run the same command again to continue: finished changes are skipped, and a change left half
done runs again from what was last deployed.

Before an arm runs, the frozen instruments are verified (`instruments.py verify --run`).
Only the change requests are read from the instruments: the change key and the binding are
opened by the scorer, after every arm has run (ADR-0040 §8).

The run writes, under OUT/ARM:
  manifest.json      the instruments' and materials' hashes, the prompts' hashes, the model
                     under test, the harness commit, each session's start and stop, the tokens
  seq-NN/record.json one change: the edit, the findings, the deploy, the times, the tokens
  seq-NN/*.jsonl     every conversation
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .arms import PROMPTS, nl_arm, render_skill, structured_arm
from .backend import ApiBackend, Backend, CliBackend, UsageLimit, user_memory
from .model import AnthropicModel, Budget, BudgetExceeded
from .probes import build_worlds, load_probes
from .toprope_arm import build_sandbox, export_toolchain, toprope_arm

ROOT = Path(__file__).resolve().parents[3]
M1 = ROOT / "experiments/m1"
INSTRUMENTS = M1 / "instruments"
ARMS = {"nl": nl_arm, "structured": structured_arm, "toprope": toprope_arm}
DEFAULT_OUT = M1 / "runs/phase-b"


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def in_order(all_: list[int], done: list[int], chosen: list[int]) -> list[int]:
    """The chosen changes not yet done, which must be the next ones in the frozen order: the
    sequence is cumulative, so none may be skipped or run early."""
    todo = [s for s in all_ if s in set(chosen) and s not in set(done)]
    expected = [s for s in all_ if s not in set(done)][:len(todo)]
    if todo != expected:
        raise SystemExit(f"changes run in order: next is {expected[:1] or 'nothing'}, asked for {todo}")
    return todo


def run_arm(arm: Any, out: Path, requests: list[dict[str, Any]], backend: Backend, model_id: str,
            instruments: Path = INSTRUMENTS, extra: dict[str, Any] | None = None,
            total: int | None = None, worlds: Path | None = None) -> dict[str, Any]:
    """Every request in order: edit, check, deploy (flagged or not), then the probes (with
    `worlds`, their starting states). Finished changes are skipped;
    a stop (the usage limit, the cost cap, Ctrl-C, an error) keeps them, and is recorded."""
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "manifest.json"
    frozen = {f: m["sha256"] for f, m in json.loads((instruments / "FROZEN.json").read_text())["files"].items()}
    prompts = _hashes(sorted(PROMPTS.glob("*.md")))
    extra = extra or {}
    if mpath.exists():
        manifest = json.loads(mpath.read_text())
        for k, now in (("model", model_id), ("materials", arm.materials_hash()), ("instruments", frozen),
                       ("prompts", prompts), *extra.items()):
            if manifest.get(k) != now:
                raise SystemExit(f"cannot resume {out}: its {k} differs from this run's")
    else:
        manifest = {"arm": arm.name, "model": model_id, "instruments": frozen, "materials": arm.materials_hash(),
                    "prompts": prompts, "of": total or len(requests), "done": [], "sessions": [], **extra}
    session: dict[str, Any] = {"started_at": _now(), "harness_commit": harness_commit(),
                               "seqs": [r["seq"] for r in requests], "stopped": None, **extra}
    manifest["sessions"].append(session)
    write = lambda: mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    write()
    try:
        for i, req in enumerate(requests, 1):
            if req["seq"] in manifest["done"]:
                continue
            d = out / f"seq-{req['seq']:02d}"
            shutil.rmtree(d, ignore_errors=True)                    # a change left half done
            stage = {"step": ""}
            backend.progress = lambda s, r=req, i=i, st=stage: _progress(arm.name, i, len(requests), r["seq"], st["step"], s)
            before = backend.report()
            stage["step"] = "edit"
            edit = arm.edit(req, d)
            stage["step"] = "check"
            check = arm.check(req, d)
            stage["step"] = "deploy"
            deploy = arm.deploy(req, d)
            probes, probe_seconds = None, 0.0
            if worlds is not None:
                stage["step"] = "probes"
                tp = time.monotonic()
                probes = arm.probe(req, d, worlds, load_probes(instruments))
                probe_seconds = time.monotonic() - tp
            after = backend.report()
            record = {"seq": req["seq"], "intent": req["intent"], "edit": edit.data, "check": check.data,
                      "deploy": deploy.data, "probes": probes,
                      "seconds": {"edit": edit.seconds, "check": check.seconds, "deploy": deploy.seconds,
                                  "edit_to_checked": edit.seconds + check.seconds, "probes": probe_seconds},
                      "tokens": {k: after["tokens"][k] - before["tokens"][k] for k in after["tokens"]},
                      "usd_estimate": round(after["usd_estimate"] - before["usd_estimate"], 4)}
            (d / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
            manifest["done"].append(req["seq"])
            _line(f"{arm.name} · change {req['seq']} done · {len(check.data.get('findings', []))} finding(s) · "
                  f"{record['seconds']['edit_to_checked']:.0f}s", end="\n")
            write()
    except (UsageLimit, BudgetExceeded) as e:
        session["stopped"] = f"{type(e).__name__}: {str(e)[:300]}"
    except KeyboardInterrupt:
        session["stopped"] = "interrupted"
    except BaseException as e:
        session["stopped"] = f"error: {type(e).__name__}: {str(e)[:300]}"
        raise
    finally:
        session["finished_at"] = _now()
        session["usage"] = backend.report()
        write()
    return manifest


def probe_worlds(out: Path) -> Path:
    """The probes' starting states, built once per run directory and shared by every arm."""
    worlds = out / "worlds"
    if not worlds.is_dir():
        _line("building the probes' starting states (once per run directory) ...", end="\n")
        tmp = out / "worlds.building"
        shutil.rmtree(tmp, ignore_errors=True)
        build_worlds(ROOT, export_toolchain(ROOT, tmp / "_toolchain"), tmp / "worlds")
        (tmp / "worlds").rename(worlds)
        shutil.rmtree(tmp)
    return worlds


def _worlds_hash(worlds: Path) -> str:
    """What the probes start from, by each world's state and situation (its logs carry times)."""
    h = hashlib.sha256()
    for f in sorted([*worlds.glob("*/state.json"), *worlds.glob("*/situation.json")]):
        h.update(str(f.relative_to(worlds)).encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def _line(text: str, end: str = "") -> None:
    sys.stderr.write("\r\033[K" + text + end)
    sys.stderr.flush()


def _progress(arm: str, i: int, n: int, seq: int, step: str, what: str) -> None:
    _line(f"{arm} · {i}/{n} (change {seq}) · {step} · {what}")


def status(out: Path) -> list[dict[str, Any]]:
    rows = []
    for m in sorted(out.glob("*/manifest.json")):
        man = json.loads(m.read_text())
        last = (man.get("sessions") or [{}])[-1]
        tokens = sum(sum((s.get("usage") or {}).get("tokens", {}).values()) for s in man.get("sessions", []))
        rows.append({"arm": man["arm"], "done": len(man["done"]), "of": man.get("of"),
                     "last_stopped": last.get("stopped"), "sessions": len(man.get("sessions", [])),
                     "tokens": tokens})
    return rows


def make_backend(args: argparse.Namespace) -> Backend:
    if args.backend == "api":
        budget = Budget.from_env()
        return ApiBackend(AnthropicModel(args.model, os.environ.get("ANTHROPIC_API_KEY", ""), budget),
                          budget)
    mem = user_memory()
    if mem and not args.allow_user_memory:
        raise SystemExit(f"{mem} would be added to every conversation. Move it aside for the run, or pass "
                         "--allow-user-memory (the manifest then records its hash).")
    return CliBackend(args.model)


def main(argv: list[str] | None = None, backend: Backend | None = None) -> None:
    ap = argparse.ArgumentParser(prog="phase_b", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="", help="the model under test, the same for every arm (ADR-0040 §7)")
    common.add_argument("--backend", choices=["cli", "api"], default="cli",
                        help="cli: your Claude Code login (default); api: ANTHROPIC_API_KEY")
    common.add_argument("--allow-user-memory", action="store_true",
                        help="run although ~/.claude/CLAUDE.md exists (recorded)")
    r = sub.add_parser("render", parents=[common], help="render the NL arm's materials from the declarations")
    r.add_argument("--declarations", type=Path, default=M1 / "arms/structured")
    r.add_argument("--out", type=Path, default=M1 / "arms/nl")
    a = sub.add_parser("arm", parents=[common], help="run the change requests on one arm")
    a.add_argument("arm", choices=sorted(ARMS))
    a.add_argument("--materials", type=Path, help="default: experiments/m1/arms/ARM")
    a.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the run directory")
    a.add_argument("--seqs", help="e.g. 1-2 for the dry run (default: all)")
    a.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    a.add_argument("--no-probes", action="store_true",
                   help="skip the probes (not for a real run: ADR-0040 §6 runs all of them after every change)")
    sb = sub.add_parser("sandbox", help="build the Toprope arm's materials from this repository")
    sb.add_argument("--out", type=Path, default=M1 / "arms/toprope")
    s = sub.add_parser("status", help="how far each arm got")
    s.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps(status(args.out), indent=2))
        return
    if args.cmd == "sandbox":
        print(json.dumps({"built": str(build_sandbox(ROOT, args.out))}))
        return
    if backend is None:
        backend = make_backend(args)
    mem = user_memory()
    extra: dict[str, Any] = {"backend": args.backend, "user_memory": hashlib.sha256(mem.read_bytes()).hexdigest()
                             if mem and args.allow_user_memory else None}
    if args.cmd == "render":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        render_skill(args.declarations, args.out, backend, args.out.parent / f"{args.out.name}.render.jsonl")
        print(json.dumps({"rendered": str(args.out), "usage": backend.report(), **extra}))
        return
    errs = verify_instruments(args.instruments)
    if errs:
        raise SystemExit("the instruments do not verify; nothing runs:\n" + "\n".join(errs))
    reqs = change_requests(args.instruments)
    all_ = [r["seq"] for r in reqs]
    work = args.out / args.arm
    resume = (work / "manifest.json").exists()
    done = json.loads((work / "manifest.json").read_text())["done"] if resume else []
    chosen = set(in_order(all_, done, seqs(args.seqs, all_)))
    t = time.monotonic()
    worlds = None if args.no_probes else probe_worlds(args.out)
    extra["probes"] = None if worlds is None else _worlds_hash(worlds)
    arm = ARMS[args.arm](args.materials or M1 / "arms" / args.arm, work, backend, resume)
    m = run_arm(arm, work, [r for r in reqs if r["seq"] in chosen], backend, args.model or "unnamed",
                args.instruments, extra, total=len(reqs), worlds=worlds)
    stopped = m["sessions"][-1]["stopped"]
    print(json.dumps({"arm": args.arm, "done": m["done"], "stopped": stopped, "usage": backend.report(),
                      "seconds": round(time.monotonic() - t, 1)}))
    if stopped:
        print("Stopped; run the same command again to continue.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
