"""Run M1 Phase B (ADR-0040, ADR-0047): the frozen change requests, in order, on one arm.

A session connected through Remote Control to the repository's folder on the researcher's
computer runs these, from `experiments/m1`, following `phase_b/RUNBOOK.md` (ADR-0047). It never
opens the key, the binding or the blind labels, and never takes a role:

  uv run python -m phase_b freeze-prompts                         freeze the agents' prompts (researcher's go)
  uv run python -m phase_b render --model M                      the NL arm's materials
  uv run python -m phase_b materials                              the structured and Toprope arms' materials
  uv run python -m phase_b arm nl --model M --seqs 1-2           the dry run, on one arm
  uv run python -m phase_b arm nl --model M                      every change; resumes a stopped run
  uv run python -m phase_b status                                 how far each arm got
  uv run python -m phase_b grade --model M                        propose the grades (opens the key)
  uv run python -m phase_b grade --model M --into scoring-2       the second sitting (the M1 recheck)
  uv run python -m phase_b compare-gradings                       the grader's noise between the two
  uv run python -m phase_b rescript --scoring S                   take back script labels the rule no longer gives
  uv run python -m phase_b check-probe-tools --model M            do a Toprope probe's domain servers connect?
  uv run python -m phase_b to-decide                              what the researcher must decide
  uv run python -m phase_b score                                  the metrics, from confirmed.yaml

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

Each change follows the frozen run protocol: five reviews (`--reviews`), three runs of the probes
(`--probe-runs`), and in the Toprope arm one derandomized check, run again uncached on the first
three changes, and five timed repeats (`--timed`). Every row goes to the decision log
`OUT/../phase-b-runs.tsv`. Nothing an agent sees names the experiment (`blind.py`).

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
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .arms import PROMPTS, nl_arm, render_skill, structured_arm, tree_hash
from .baseline import BASELINE, baseline_root
from .backend import ApiBackend, Backend, CliBackend, UsageLimit, user_memory
from .model import AnthropicModel, Budget, BudgetExceeded
from .probes import build_worlds, load_probes
from .runlog import RunLog, log_path
from .score import grade as grade_run
from .score import score as score_run
from .toprope_arm import build_sandbox, export_toolchain, toprope_arm

ROOT = Path(__file__).resolve().parents[3]
M1 = ROOT / "experiments/m1"
INSTRUMENTS = M1 / "instruments"
ARMS = {"nl": nl_arm, "structured": structured_arm, "toprope": toprope_arm}
DEFAULT_OUT = M1 / "runs/phase-b"


def arm_prompts() -> list[Path]:
    """The prompts the agents in an arm get (the grader's are not among them)."""
    return sorted(p for p in PROMPTS.glob("*.md") if not p.name.startswith("grade_"))


def prompts_hash() -> str:
    h = hashlib.sha256()
    for p in arm_prompts():
        h.update(p.name.encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def verify_instruments(d: Path = INSTRUMENTS) -> list[str]:
    spec = importlib.util.spec_from_file_location("instruments", ROOT / "experiments/tools/instruments.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                     # type: ignore[union-attr]
    errs = mod.verify(d, run=True)
    # The run protocol (§1) freezes each arm's prompt with it: the prompts' hash is in FROZEN.json.
    frozen = json.loads((d / "FROZEN.json").read_text()).get("prompts") if (d / "FROZEN.json").exists() else None
    if not frozen:
        errs.append("the agents' prompts are not frozen: the researcher runs `python -m phase_b freeze-prompts`")
    elif frozen["sha256"] != prompts_hash():
        errs.append("the agents' prompts changed after freezing (phase_b/prompts): amend them with "
                    "`python -m phase_b freeze-prompts --reason TEXT`, or restore them")
    return errs


def freeze_prompts(d: Path, reason: str = "") -> dict[str, Any]:
    """Record the agents' prompts' hash in FROZEN.json (the researcher's step, run protocol §1).
    A frozen hash changes only with a reason, and the old one stays in its history."""
    mp = d / "FROZEN.json"
    manifest = json.loads(mp.read_text())
    if "run-protocol.md" not in manifest.get("files", {}):
        raise SystemExit("freeze the run protocol first (instruments.py freeze-protocol)")
    now = {"sha256": prompts_hash(), "files": [p.name for p in arm_prompts()], "frozen_at": _now()}
    old = manifest.get("prompts")
    if old:
        if old["sha256"] == now["sha256"]:
            raise SystemExit("the prompts are frozen as they are; nothing to change")
        if not reason.strip():
            raise SystemExit("the prompts are frozen with another hash: give --reason to amend them")
        now["history"] = old.get("history", []) + [{"sha256": old["sha256"], "frozen_at": old["frozen_at"],
                                                    "replaced_at": now["frozen_at"], "reason": reason.strip()}]
    manifest["prompts"] = now
    mp.write_text(json.dumps(manifest, indent=2) + "\n")
    return now


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


def probe_runs(arm: Any, req: dict[str, Any], d: Path, worlds: Path, probes: list[dict[str, Any]], jobs: int,
               runs: int) -> list[dict[str, Any]]:
    """Run protocol §3: every probe `runs` times after a change, each run on fresh copies of the
    starting states, in its own directory."""
    out = []
    for k in range(1, runs + 1):
        where = f"probes/run-{k}"
        out.append({"run": k, "dir": where, "results": arm.probe(req, d / where, worlds, probes, jobs=jobs)})
    return out


def run_arm(arm: Any, out: Path, requests: list[dict[str, Any]], backend: Backend, model_id: str,
            instruments: Path = INSTRUMENTS, extra: dict[str, Any] | None = None,
            total: int | None = None, worlds: Path | None = None, jobs: int = 1,
            runs_of_probes: int = 3, redo_baseline_probes: bool = False) -> dict[str, Any]:
    """Every request in order: edit, check, deploy (flagged or not), then the probes (with
    `worlds`, their starting states). Finished changes are skipped;
    a stop (the usage limit, the cost cap, Ctrl-C, an error) keeps them, and is recorded."""
    out.mkdir(parents=True, exist_ok=True)
    mpath = out / "manifest.json"
    frozen = {f: m["sha256"] for f, m in json.loads((instruments / "FROZEN.json").read_text())["files"].items()}
    prompts = _hashes(sorted(p for p in PROMPTS.glob("*.md") if not p.name.startswith("grade_")))  # the run's
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
                               "seqs": [r["seq"] for r in requests], "stopped": None, "jobs": jobs, **extra}
    manifest["sessions"].append(session)
    write = lambda: mpath.write_text(json.dumps(manifest, indent=2) + "\n")
    write()
    log = RunLog(log_path(out.parent))
    log.append(arm.name, "", "", "session-start", mpath, f"harness {session['harness_commit']}; model {model_id}")
    try:
        if redo_baseline_probes and manifest.get("baseline_probes"):
            from .toprope_arm import _aside
            if (out / "seq-00").exists():
                aside = _aside(out / "seq-00", "redone")
                (out / "seq-00").rename(aside)
                log.append(arm.name, 0, "", "superseded", aside, "the probes before any change run again")
            manifest["baseline_probes"] = False
            write()
        if worlds is not None and not manifest.get("baseline_probes"):
            # The probes before any change: a probe that passes here and fails after a change
            # points at that change (the scorer's "found after deploy").
            d0 = out / "seq-00"
            shutil.rmtree(d0, ignore_errors=True)
            backend.progress = lambda s: _line(f"{arm.name} · before any change · probes · {s}")
            tp = time.monotonic()
            probes0 = probe_runs(arm, {"seq": 0, "intent": "(before any change)"}, d0, worlds,
                                 load_probes(instruments), jobs, runs_of_probes)
            d0.mkdir(parents=True, exist_ok=True)
            for pr in probes0:
                _log_probes(log, arm.name, 0, pr["run"], d0 / pr["dir"], pr["results"])
            (d0 / "record.json").write_text(json.dumps({"seq": 0, "probes": probes0,
                                                        "seconds": {"probes": time.monotonic() - tp},
                                                        "tokens": (backend.report() or {}).get("tokens")},
                                                       indent=2, ensure_ascii=False) + "\n")
            manifest["baseline_probes"] = True
            write()
        for i, req in enumerate(requests, 1):
            if req["seq"] in manifest["done"]:
                continue
            d = out / f"seq-{req['seq']:02d}"
            if d.exists():                                         # a change left half done
                log.append(arm.name, req["seq"], 1, "superseded", d, "a stopped attempt: the change runs again")
            shutil.rmtree(d, ignore_errors=True)
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
                probes = probe_runs(arm, req, d, worlds, load_probes(instruments), jobs, runs_of_probes)
                probe_seconds = time.monotonic() - tp
            after = backend.report()
            record = {"seq": req["seq"], "intent": req["intent"], "edit": edit.data, "check": check.data,
                      "deploy": deploy.data, "probes": probes,
                      "seconds": {"edit": edit.seconds, "check": check.seconds, "deploy": deploy.seconds,
                                  "edit_to_checked": edit.seconds + check.seconds, "probes": probe_seconds},
                      "tokens": {k: after["tokens"][k] - before["tokens"][k] for k in after["tokens"]},
                      "usd_estimate": round(after["usd_estimate"] - before["usd_estimate"], 4)}
            (d / "record.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
            _log_change(log, arm.name, req["seq"], d, record)
            manifest["done"].append(req["seq"])
            n = sum(len(r.get("findings", [])) for r in check.data.get("runs", []))
            _line(f"{arm.name} · change {req['seq']} done · {n} finding(s) · "
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
        log.append(arm.name, "", "", "session-stop", mpath, session["stopped"] or "finished")
    return manifest


def _log_change(log: RunLog, arm: str, seq: int, d: Path, record: dict[str, Any]) -> None:
    """One change's rows in the decision log: what ran, where its evidence is, what came of it."""
    edit, check, deploy = record["edit"], record["check"], record["deploy"]
    log.append(arm, seq, 1, "edit", d / "edit.jsonl" if (d / "edit.jsonl").exists() else d / "record.json",
               "changed" if edit.get("changed", edit.get("diff")) else "unchanged")
    if arm == "toprope":
        commits = check.get("commits") or {}
        result = "; ".join(f"{dom} {c['commit']} {'passed' if c['passed'] else 'failed'}"
                           for dom, c in sorted(commits.items())) or "no commit"
        log.append(arm, seq, 1, "check", d / "record.json",
                   f"{result}; {len(check.get('findings', []))} finding(s)")
        if "repeat" in check:
            log.append(arm, seq, 2, "check repeat", d / "record.json",
                       "same findings" if check["repeat"]["same"] else "different findings")
        for k, t in enumerate(check.get("timed") or [], 1):
            log.append(arm, seq, k, "timed", d / "record.json", f"{t['seconds']:.1f}s; limiter {t['limiter']}")
    else:
        for r in check.get("runs") or []:
            log.append(arm, seq, r["run"], "review", d / r["transcript"],
                       f"error: {r['error']}" if r.get("error") else f"{len(r.get('findings', []))} finding(s)")
    log.append(arm, seq, 1, "deploy", d / "record.json", "deployed" if deploy.get("deployed") else "not deployed")
    for pr in record.get("probes") or []:
        _log_probes(log, arm, seq, pr["run"], d / pr["dir"], pr["results"])


def _log_probes(log: RunLog, arm: str, seq: int, run: int, where: Path, probes: list[dict[str, Any]]) -> None:
    for p in probes:
        log.append(arm, seq, run, f"probe {p['probe']}", where / p.get("transcript", f"{p['probe']}.jsonl"),
                   f"error: {p['error']}" if p.get("error") else "ran (graded later)")


def recheck_toprope(out: Path) -> dict[str, Any]:
    """The Toprope arm's flags, taken again from the commits its run stored (the checks are
    deterministic, so nothing is run by a model). Each commit is checked against the base the
    kernel recorded, on the member's own event history up to the moment of that check, and each
    flag says whether its base had it already. The first flags stay under `check.original`; the
    decision log gets a `recheck` row per change."""
    from .toprope_arm import checked_at, flags
    work = out / "toprope"
    root = work / "sandbox"
    log = RunLog(log_path(out))
    done: dict[int, int] = {}
    for f in sorted(work.glob("seq-*/record.json")):
        rec = json.loads(f.read_text())
        check = rec.get("check") or {}
        if rec["seq"] <= 0 or not check.get("commits"):
            continue
        found: list[dict[str, Any]] = []
        for d, c in sorted(check["commits"].items()):
            found += flags(root, d, c["commit"], upto=checked_at(root, d, c["commit"]))[0]
        check.setdefault("original", {"findings": check.get("findings"), "runs": check.get("runs")})
        check["findings"] = found
        check["runs"] = [{"run": 1, "findings": found}]
        check["recheck"] = {"at": _now(), "harness_commit": harness_commit(),
                            "why": "flags taken on the kernel's inputs (its base and the member's own history)"}
        f.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
        log.append("toprope", rec["seq"], 1, "recheck", f,
                   f"{len(found)} flag(s), {sum(not x['carried'] for x in found)} new with the change "
                   f"(first: {len(check['original']['findings'] or [])})")
        done[rec["seq"]] = len(found)
    return {"rechecked": done}


def worlds_complete(worlds: Path) -> bool:
    """Every probe's starting state is there: its state and its situation."""
    from .probes import PROBES
    return all((worlds / p / "state.json").is_file() and (worlds / p / "situation.json").is_file() for p in PROBES)


def probe_worlds(out: Path) -> Path:
    """The probes' starting states, built once per run directory and shared by every arm."""
    worlds = out / "worlds"
    if worlds.is_dir() and not worlds_complete(worlds):
        # A directory with no starting states in it (only caches git ignores, left when an older
        # run was moved away; or a build that stopped): kept aside, and built again.
        from .toprope_arm import _aside
        aside = _aside(worlds, "incomplete")
        worlds.rename(aside)
        _line(f"{worlds} had no complete starting states: moved to {aside.name}, building them again", end="\n")
    if not worlds.is_dir():
        _line("building the probes' starting states (once per run directory) ...", end="\n")
        out.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="worlds.building-", dir=out))      # one per process: no race
        try:
            base = baseline_root(ROOT)
            build_worlds(base, export_toolchain(base, tmp / "_toolchain"), tmp / "worlds")
            try:
                (tmp / "worlds").rename(worlds)
            except OSError:                                # another arm finished first: use its worlds
                if not worlds.is_dir():
                    raise
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return worlds


def check_probe_tools(backend: Backend, worlds: Path, toolchain: Path | None = None,
                      where: Path | None = None) -> dict[str, Any]:
    """One conversation with a Toprope probe's servers, on a copy of P07's starting state, set up as
    `run_probe` does: inside `where` (the run directory), with `toolchain`'s declarations (the arm's
    deployed ones) over the world's. Reports the tools it got, each server's status, and each
    server's own stderr."""
    from .agent import Transcript
    from .probes import DOMAINS, servers
    from .toolserver import ToolSpec
    if where is not None:
        where.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="probe-tools-", dir=where) as tmp:
        root = Path(tmp) / "P07"
        shutil.copytree(worlds / "P07", root)
        for d in DOMAINS if toolchain is not None else ():
            shutil.copy(toolchain / d / f"{d}.domain.yaml", root / "toolchain" / d / f"{d}.domain.yaml")
        t = Transcript(Path(tmp) / "t.jsonl")
        from .probes import server_logs
        logs = Path(tmp) / "logs"
        spec = ToolSpec("probe", str(root), json.dumps({"objects": False, "servers": servers(root, logs),
                                                       "server_logs": server_logs(logs)}))
        try:
            backend.converse("You check which tools you have.", "Name three of your tools, then stop.", spec, t,
                             max_turns=2)
            error = None
        except Exception as e:                        # what the run would have recorded
            error = f"{type(e).__name__}: {e}"
        rows = [json.loads(x) for x in t.path.read_text().splitlines()]
        init = next((r for r in rows if r["kind"] in ("init", "refused")), {})
        server_err = {m: Path(f).read_text()[-1500:] for m, f in server_logs(logs).items() if Path(f).exists()}
    return {"connected": error is None, "error": error, "tools": len(init.get("tools") or []),
            "mcp_servers": init.get("mcp_servers"), "stderr": init.get("stderr"), "server_stderr": server_err}


def baseline() -> dict[str, str]:
    """The self-domain commits everything starts from (ADR-0040 §3), whatever the repository's
    self domains are now: `baseline.BASELINE`, checked at `baseline.BASELINE_REVS`."""
    baseline_root(ROOT)
    return dict(BASELINE)


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
        if ".stale-" in m.parent.name:          # a run moved aside (`<arm>.stale-N`) is not the arm's
            continue
        man = json.loads(m.read_text())
        last = (man.get("sessions") or [{}])[-1]
        tokens = sum(sum((s.get("usage") or {}).get("tokens", {}).values()) for s in man.get("sessions", []))
        rows.append({"arm": man["arm"], "done": len(man["done"]), "of": man.get("of"),
                     "last_stopped": last.get("stopped"), "sessions": len(man.get("sessions", [])),
                     "tokens": tokens})
    return rows


def _stamp(nl: Path) -> Path:
    """Beside the NL skill (not in it, so the arm never sees it): the hash of the declarations
    it was rendered from."""
    return nl.parent / f"{nl.name}.rendered-from"


def rendered_from_other(nl: Path, structured: Path) -> str | None:
    """Why the NL skill cannot run, if it was not rendered from the structured arm's declarations
    as they are now (the arms must carry the same rules, ADR-0040 §3)."""
    if not nl.is_dir():
        return f"no NL skill at {nl}: render it (`python -m phase_b render --model M`), then review it"
    stamp = _stamp(nl)
    if not stamp.is_file() or stamp.read_text().strip() != tree_hash(structured):
        return (f"the NL skill at {nl} was not rendered from {structured} as it is now: delete it, render it "
                "again (`python -m phase_b render --model M`), and review it side by side")
    return None


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
    a.add_argument("--jobs", type=int, default=4,
                   help="probes run at once after each change (default 4); they are independent")
    a.add_argument("--reviews", type=int, default=5,
                   help="reviews per change in the NL and structured arms (run protocol §3: 5)")
    a.add_argument("--probe-runs", type=int, default=3, help="runs of the probes after each change (§3: 3)")
    a.add_argument("--redo-baseline-probes", action="store_true",
                   help="run the probes before any change again (their seq-00 moved aside): a harness fault "
                        "spoilt them (the M1 recheck's Toprope probes ran without their domain tools)")
    a.add_argument("--timed", type=int, default=5, help="timed repeats of the Toprope checks per change (§3: 5)")
    a.add_argument("--no-probes", action="store_true",
                   help="skip the probes (not for a real run: ADR-0040 §6 runs all of them after every change)")
    sb = sub.add_parser("materials", help="build the structured-spec and Toprope arms' materials from the "
                        "approved self-domain commits (the NL arm's comes from `render`)")
    sb.add_argument("--out", type=Path, default=M1 / "arms", help="writes OUT/structured and OUT/toprope")
    fp = sub.add_parser("freeze-prompts", help="researcher only: freeze the agents' prompts' hash in FROZEN.json "
                        "(run protocol §1); with --reason, amend a frozen one")
    fp.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    fp.add_argument("--reason", default="")
    cb = sub.add_parser("combine-toprope", parents=[common], help="the Toprope arm with its LLM review: review the "
                        "Toprope arm's own edits five times and add the compiler's flags (phase_b/combined.py)")
    cb.add_argument("--out", type=Path, default=DEFAULT_OUT, help="the run to read")
    cb.add_argument("--to", type=Path, default=M1 / "runs/phase-b-combined", help="the run directory it writes")
    cb.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    rc = sub.add_parser("recheck-toprope", help="take the Toprope arm's flags again from its stored commits, on "
                        "the kernel's inputs (#169); keeps the first ones under check.original")
    rc.add_argument("--out", type=Path, default=DEFAULT_OUT)
    td = sub.add_parser("to-decide", help="what the researcher must decide in the grades (ADR-0047 §3)")
    td.add_argument("--out", type=Path, default=DEFAULT_OUT)
    s = sub.add_parser("status", help="how far each arm got")
    s.add_argument("--out", type=Path, default=DEFAULT_OUT)
    g = sub.add_parser("grade", parents=[common], help="propose a label for every finding, edit and probe "
                       "(opens the key: only once every arm has run every change)")
    g.add_argument("--out", type=Path, default=DEFAULT_OUT)
    g.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    g.add_argument("--partial", action="store_true", help="grade an incomplete run (tests; never for the report)")
    g.add_argument("--into", default="scoring", help="the scoring directory: `scoring-2` for the second sitting")
    g.add_argument("--grader", choices=["single", "checklist"], default="single",
                   help="single: one pass, one label per flag (M1); checklist: M2's grader (M2-grader.md)")
    g.add_argument("--k", type=int, default=3, help="answers per checklist item, decided by majority (M2: 3)")
    g.add_argument("--changes-only", action="store_true",
                   help="grade the changes, not the probes: a check of the grader's noise, which `score` refuses")
    rl = sub.add_parser("relabel", parents=[], help="apply the current checklist rule to a checklist sitting's "
                        "answers, without grading again")
    rl.add_argument("--out", type=Path, default=DEFAULT_OUT)
    rl.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    rl.add_argument("--scoring", required=True)
    rs = sub.add_parser("rescript", help="take back script labels the current rule no longer gives (a sitting "
                        "graded before the fix); the label becomes the grader's")
    rs.add_argument("--out", type=Path, default=DEFAULT_OUT)
    rs.add_argument("--scoring", default="scoring")
    rg = sub.add_parser("regrade-missing", parents=[common], help="grade again each probe run a sitting left "
                        "without a pass or fail (no JSON after the retry)")
    rg.add_argument("--out", type=Path, default=DEFAULT_OUT)
    rg.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    rg.add_argument("--scoring", default="scoring")
    rg.add_argument("--redo", action="append", default=[], metavar="ARM:SEQ",
                    help="grade these probe runs again too, e.g. toprope:0 after --redo-baseline-probes")
    cp = sub.add_parser("check-probe-tools", parents=[common], help="start one Toprope probe's conversation as a run "
                        "does and report whether its domain servers connected (no probe is graded)")
    cp.add_argument("--out", type=Path, default=DEFAULT_OUT)
    cp.add_argument("--toolchain", type=Path, default=None,
                    help="the deployed declarations to use, as a run does (e.g. OUT/toprope/seq-00/probes/run-1/"
                         "deployed-toolchain)")
    cg = sub.add_parser("compare-gradings", help="the grader's noise: each arm's recall from two sittings")
    cg.add_argument("--out", type=Path, default=DEFAULT_OUT)
    cg.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    cg.add_argument("--first", default="scoring")
    cg.add_argument("--second", default="scoring-2")
    cg.add_argument("--limit", type=float, default=0.1, help="the noise limit (M1: 0.1; M2's grader: 0.05)")
    sc = sub.add_parser("score", help="the metrics and pilot verdicts, from scoring/confirmed.yaml")
    sc.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sc.add_argument("--instruments", type=Path, default=INSTRUMENTS)
    args = ap.parse_args(argv)
    for k, v in vars(args).items():               # every path absolute: subprocesses run elsewhere
        if isinstance(v, Path):
            setattr(args, k, v.resolve())
    out = getattr(args, "out", None)
    if isinstance(out, Path) and (out / "RAW.json").exists():   # raw records in git history (ADR-0055)
        missing = [p for p in json.loads((out / "RAW.json").read_text())["raw"] if not (out / p).exists()]
        if missing:
            raise SystemExit(f"error: {out} keeps its raw records in git history (ADR-0055), and "
                             f"{', '.join(missing)} are not here. Fix: python tools/run_archive.py restore {out}")

    if args.cmd == "freeze-prompts":
        print(json.dumps(freeze_prompts(args.instruments, args.reason), indent=2))
        return
    if args.cmd == "relabel":
        from .score import relabel
        print(json.dumps(relabel(args.out, args.instruments, args.scoring), indent=2))
        return
    if args.cmd == "rescript":
        from .score import rescript
        print(json.dumps(rescript(args.out, args.scoring), indent=2))
        return
    if args.cmd == "compare-gradings":
        from .score import compare_gradings
        print(json.dumps(compare_gradings(args.out, args.instruments, args.first, args.second, args.limit), indent=2))
        return
    if args.cmd == "recheck-toprope":
        print(json.dumps(recheck_toprope(args.out), indent=2))
        return
    if args.cmd == "to-decide":
        from .score import to_decide
        print(json.dumps(to_decide(args.out), indent=2, ensure_ascii=False))
        return
    if args.cmd == "status":
        print(json.dumps(status(args.out), indent=2))
        return
    if args.cmd == "score":
        print(json.dumps(score_run(args.out, args.instruments), indent=2, ensure_ascii=False))
        return
    if args.cmd == "materials":
        print(json.dumps({"baseline": baseline(),
                          "structured": str(export_toolchain(baseline_root(ROOT), args.out / "structured")),
                          "toprope": str(build_sandbox(baseline_root(ROOT), args.out / "toprope"))}))
        return
    if backend is None:
        backend = make_backend(args)
    mem = user_memory()
    extra: dict[str, Any] = {"backend": args.backend, "user_memory": hashlib.sha256(mem.read_bytes()).hexdigest()
                             if mem and args.allow_user_memory else None}
    if args.cmd == "combine-toprope":
        errs = verify_instruments(args.instruments)
        if errs:
            raise SystemExit("the instruments do not verify; nothing runs:\n" + "\n".join(errs))
        from .combined import combine
        print(json.dumps({**combine(args.out, args.to, backend), "usage": backend.report()}))
        return
    if args.cmd == "check-probe-tools":
        print(json.dumps(check_probe_tools(backend, probe_worlds(args.out), args.toolchain,
                                           args.out / "toprope" / "probe-tools-check"), indent=2))
        return
    if args.cmd == "regrade-missing":
        from .score import regrade_missing
        redo = [(x.split(":")[0], int(x.split(":")[1])) for x in args.redo]
        print(json.dumps({**regrade_missing(args.out, args.instruments, backend, args.scoring, redo),
                          "usage": backend.report()}, indent=2))
        return
    if args.cmd == "grade":
        errs = verify_instruments(args.instruments)
        if errs:
            raise SystemExit("the instruments do not verify; nothing is graded:\n" + "\n".join(errs))
        path = grade_run(args.out, args.instruments, backend, change_requests(args.instruments), args.partial,
                         into=args.into, grader=args.grader, k=args.k, changes_only=args.changes_only)
        print(json.dumps({"proposed": str(path), "usage": backend.report()}))
        return
    if args.cmd == "render":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        render_skill(args.declarations, args.out, backend, args.out.parent / f"{args.out.name}.render.jsonl")
        _stamp(args.out).write_text(tree_hash(args.declarations) + "\n")
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
    extra["baseline"] = baseline()             # every arm and the probes start from these commits
    materials = args.materials or M1 / "arms" / args.arm
    if args.arm == "nl" and args.materials is None:
        stale = rendered_from_other(materials, M1 / "arms/structured")
        if stale:
            raise SystemExit(stale)
    if args.arm == "toprope":
        from toprope.commits import CommitStore
        store = CommitStore(materials / ".toprope/commits")
        got = {d: store.main(d).id for d in extra["baseline"]}
        if got != extra["baseline"]:
            raise SystemExit(f"the Toprope materials start from {got}, the repository from {extra['baseline']}: "
                             "rebuild them with `materials`")
    arm = ARMS[args.arm](materials, work, backend, resume)
    arm.reviews, arm.timed = args.reviews, args.timed           # the runs a resume must keep (manifest)
    extra["runs"] = {"reviews": args.reviews if args.arm != "toprope" else None, "probes": args.probe_runs,
                     "timed": args.timed if args.arm == "toprope" else None}
    m = run_arm(arm, work, [r for r in reqs if r["seq"] in chosen], backend, args.model or "unnamed",
                args.instruments, extra, total=len(reqs), worlds=worlds, jobs=max(1, args.jobs),
                runs_of_probes=args.probe_runs, redo_baseline_probes=args.redo_baseline_probes)
    stopped = m["sessions"][-1]["stopped"]
    print(json.dumps({"arm": args.arm, "done": m["done"], "stopped": stopped, "usage": backend.report(),
                      "seconds": round(time.monotonic() - t, 1)}))
    if stopped:
        print("Stopped; run the same command again to continue.", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
