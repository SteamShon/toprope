"""Measure friction in the self domains' change loop from their logs (ADR-0049, F1).

    uv run python tools/usability_baseline.py [--root .] [--since DATE] [--until DATE] [--json]

Reads, per self domain:
- `domains/<d>/events/idempotency.jsonl`: one entry per kernel command, with its outcome. This
  is the window measured: changes approved before the first command here are not counted;
- `domains/<d>/events/events.jsonl`: who each actor is (person, agent, system) and failed
  effects;
- `.toprope/commits/<d>/`: commits and their check runs;
- `.toprope/approval-runs.jsonl`: the researcher's approved human requests (ADR-0039).

A change is approved by a person's `approve_commit`, in whichever domain it is made, and shipped
through another; so a change's commands are counted across all domains. The kernel's own
replies (`record_*`, taken by `external:` and `handoff:` actors) are not friction and are left
out of the rates.

A command that fails before the gate (a bad argument, a refused option, a crash) is recorded
since ADR-0049's D1b, one file each under `.toprope/failures/`. They are counted apart from the
rates above, and per change approved since the first one was recorded: a successful read leaves
no record, so failures cannot share a denominator with the commands. Failures from before D1b
were never recorded.

Beside the kernel commands, it measures what ADR-0049 (5) and ADR-0050 name as targets
(definitions in `docs/experiments/U-theme1-change-loop.md`, "How F1 is computed"):
- a person's touches per approved change: approvals of human requests that take a change step,
  plus commands by a person outside any approved request's run. A request's steps run as the
  person (`--identity github`), so they are kernel commands by a person, but one approval;
- approvals per approved change, by the risk `check_commit` last recorded on it (ADR-0050);
- refusals and failed effects per command, with failures before the gate per command attempted.

`--since` and `--until` bound every count to a window (from `--since`, up to but not including
`--until`), so a re-measure can leave out an earlier batch and the baseline stays reproducible.
A command's time is that of the events it appended; one that appended none (a refusal) takes the
time of the command before it in the same log.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from human_request import APPROVAL_RUNS, MADE, SHIPS, shipped_commit

from toprope.errors import fixed

SYSTEM_PREFIXES = ("external:", "handoff:")
APPROVE = "approve_commit"
# Checks whose `ok: false` is a state of the commit, not a finding: `confirmed` is false while
# proposed elements are left (ADR-0041), and a skipped check did not run.
NOT_FINDINGS = {"confirmed", "risk"}   # risk: a classification (ADR-0050), not a finding


def _when(value: object) -> datetime | None:
    """A time from a log (`"…"` or the kernel's `{"$dt": "…"}`), in UTC; None if there is none."""
    if isinstance(value, dict):
        value = value.get("$dt")
    if not isinstance(value, str) or not value:
        return None
    try:
        t = datetime.fromisoformat(value)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


class Window:
    """From `since` up to but not including `until`; either may be open. A row without a time is
    inside an open window only: it cannot be placed."""

    def __init__(self, since: object = None, until: object = None):
        self.since, self.until = _when(since), _when(until)

    def __contains__(self, t: datetime | None) -> bool:
        if t is None:
            return self.since is None and self.until is None
        return (self.since is None or t >= self.since) and (self.until is None or t < self.until)

    def as_dict(self) -> dict:
        return {"since": self.since and self.since.isoformat(), "until": self.until and self.until.isoformat()}


def _commands(root: Path, domain: str) -> tuple[list[dict], list[datetime | None]]:
    """The domain's finished commands, in log order, each with its time; and the times of those
    never finished."""
    ev_dir = root / "domains" / domain / "events"
    kinds = _actor_kinds(_jsonl(ev_dir / "events.jsonl"))
    rows = []
    for row in _jsonl(ev_dir / "idempotency.jsonl"):
        outcome = None if row["state"] == "pending" else json.loads(row["state"])
        t = next((w for e in (outcome or {}).get("events") or [] if (w := _when(e.get("at")))), None)
        rows.append((row["key"], outcome, t))
    first = next((t for _, _, t in rows if t is not None), None)
    finished, pending, last = {}, {}, None
    for key, outcome, t in rows:            # an untimed row takes the time before it (or the first)
        last = t or last or first
        if outcome is None:
            pending.setdefault(key, last)
        else:
            actor_id, action, target = (json.loads(key) + [None, None, None])[:3]
            finished[key] = {"domain": domain, "actor": actor_id, "kind": _kind(actor_id, kinds),
                             "action": action, "target": target, "outcome": outcome, "t": last,
                             "ok": outcome.get("status") == "ok"}
    return list(finished.values()), [t for k, t in pending.items() if k not in finished]


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _actor_kinds(events: list[dict]) -> dict[str, str]:
    kinds = {}
    for row in events:
        actor = json.loads(row["event"]).get("actor")
        if actor:
            kinds[actor["id"]] = actor["kind"]
    return kinds


def _kind(actor_id: str, kinds: dict[str, str]) -> str:
    if actor_id.startswith(SYSTEM_PREFIXES):
        return "system"
    return kinds.get(actor_id, "unknown")


def _check_failed(row: dict) -> bool:
    """A check that ran and found something."""
    return (not row["ok"] and row.get("check") not in NOT_FINDINGS
            and not row.get("summary", "").startswith("skipped"))


def measure_domain(root: Path, domain: str, window: Window | None = None) -> dict:
    window = window or Window()
    ev_dir = root / "domains" / domain / "events"
    events = _jsonl(ev_dir / "events.jsonl")
    commands, unfinished = _commands(root, domain)
    by_kind, refused_by_kind, refused_codes = Counter(), Counter(), Counter()
    approvals = 0
    for c in commands:
        if c["t"] not in window:
            continue
        kind = c["kind"]
        by_kind[kind] += 1
        if not c["ok"]:
            refused_by_kind[kind] += 1
            refused_codes[f"{c['action']}:{c['outcome'].get('code')}"] += 1
        elif c["action"] == APPROVE and kind == "person":
            approvals += 1

    store = root / ".toprope" / "commits" / domain
    commits = [r["id"] for r in _jsonl(store / "log.jsonl") if _when(r.get("at")) in window]
    ends = Window(None, window.until)
    approved = {r["commit"] for r in _jsonl(store / "approvals.jsonl") if _when(r.get("at")) in ends}
    failed_checks = {r["commit"] for r in _jsonl(store / "checks.jsonl") if _check_failed(r)} & set(commits)
    failed_effects = [e for r in events if (e := json.loads(r["event"]))["type"] == "EffectFailed"]

    return {
        "commands": sum(by_kind.values()),
        "commands_by_actor": dict(by_kind),
        "commands_unfinished": sum(1 for t in unfinished if t in window),
        "refused": sum(refused_by_kind.values()),
        "refused_by_actor": dict(refused_by_kind),
        "refused_codes": dict(refused_codes),
        "effects_failed": sum(1 for e in failed_effects if _when(e.get("at")) in window),
        "approvals_in_window": approvals,
        "commits": len(commits),
        "commits_never_approved": len([c for c in commits if c not in approved]),
        "commits_with_a_failed_check": len(failed_checks),
    }


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def _match_runs(runs: list[dict], commands: list[dict]) -> list[tuple[dict, list[dict], int]]:
    """Each approved request run with the kernel commands its `run` steps took, and how many of
    its steps were not found. A step took the latest command, not yet matched, by the person the
    run acted as, with the step's action and target (`$commit` stands for any commit), at or
    before the run was recorded and after the run before it. Only commands that succeeded: a
    recorded run is one whose every step did."""
    by_time = sorted((c for c in commands if c["ok"] and c["kind"] == "person" and c["t"]),
                     key=lambda c: c["t"])
    used: set[int] = set()
    out, before = [], None
    for run in sorted(runs, key=lambda r: _when(r.get("at")) or datetime.min.replace(tzinfo=UTC)):
        at = _when(run.get("at"))
        steps = [st["run"] for st in run.get("steps") or [] if isinstance(st, dict) and "run" in st]
        took = []
        for st in reversed(steps):
            target = re.escape(str(st.get("target"))).replace(re.escape(MADE), r"[^:]+")
            found = [i for i, c in enumerate(by_time) if i not in used and at is not None
                     and c["actor"] == run.get("as") and c["action"] == st.get("action")
                     and re.fullmatch(target, str(c["target"]))
                     and c["t"] <= at + timedelta(seconds=1) and (before is None or c["t"] > before)]
            if found:
                used.add(found[-1])
                took.append(by_time[found[-1]])
        out.append((run, took, len(steps) - len(took)))
        before = at or before
    return out


def _risk(root: Path) -> dict[str, str]:
    """The risk `check_commit` last recorded on each commit (ADR-0050), in any domain."""
    level = {}
    for path in sorted((root / ".toprope" / "commits").glob("*/checks.jsonl")):
        for r in _jsonl(path):
            if r.get("check") == "risk":
                level[r["commit"]] = str(r.get("summary", "")).split(":", 1)[0].strip()
    return level


def _changes_touched(took: list[dict]) -> set[str]:
    """The commits a run approved or shipped."""
    out = set()
    for c in took:
        if c["action"] == APPROVE:
            out.add(c["target"])
        elif c["action"] in SHIPS and (ships := shipped_commit({"action": c["action"], "target": c["target"]}, None)):
            out.add(ships)
    return out


def measure(root: Path, since: object = None, until: object = None) -> dict:
    root = Path(root)
    window = Window(since, until)
    base = root / "domains"
    domains = sorted(p.name for p in base.iterdir()
                     if (p / "events" / "idempotency.jsonl").exists()) if base.exists() else []
    per = {d: measure_domain(root, d, window) for d in domains}

    def total(f):
        return sum(f(m) for m in per.values())

    person = total(lambda m: m["commands_by_actor"].get("person", 0))
    agent = total(lambda m: m["commands_by_actor"].get("agent", 0))
    unknown = total(lambda m: m["commands_by_actor"].get("unknown", 0))
    taken = person + agent + unknown
    approvals = total(lambda m: m["approvals_in_window"])
    refused = total(lambda m: m["refused"] - m["refused_by_actor"].get("system", 0))
    effects = total(lambda m: m["effects_failed"])
    bad = refused + effects
    failures, malformed = [], 0
    for path in sorted((root / ".toprope" / "failures").glob("*.json")):
        try:
            f = json.loads(path.read_text())
        except (OSError, ValueError):
            malformed += 1
            continue
        if _when(f.get("at")) in window:
            failures.append(f)
    by_kind = Counter(f.get("kind") for f in failures)
    first = min((f["at"] for f in failures if isinstance(f.get("at"), str)), default=None)
    approved_since = sum(1 for d in per for r in _jsonl(root / ".toprope" / "commits" / d / "approvals.jsonl")
                         if first is not None and str(r.get("at", "")) >= first and _when(r.get("at")) in window)

    # Touches and approvals (ADR-0049, 5; ADR-0050): a request run is one approval by a person.
    commands = [c for d in domains for c in _commands(root, d)[0]]
    runs = _jsonl(root / APPROVAL_RUNS)
    matched = [(r, took, missing) for r, took, missing in _match_runs(runs, commands) if _when(r.get("at")) in window]
    change_runs = [(r, took, missing) for r, took, missing in matched
                   if any(isinstance(st, dict) and "run" in st for st in r.get("steps") or [])]
    in_runs = {id(c) for _, took, _ in matched for c in took}
    outside = [c for c in commands if c["kind"] == "person" and c["t"] in window and id(c) not in in_runs]
    touches = len(change_runs) + len(outside)

    approved_changes = {c["target"] for c in commands
                        if c["ok"] and c["kind"] == "person" and c["action"] == APPROVE and c["t"] in window}
    approvals_of = Counter(c["target"] for c in outside if c["ok"] and c["action"] == APPROVE)
    for _, took, _ in change_runs:
        approvals_of.update(_changes_touched(took))
    level = _risk(root)
    by_risk: dict[str, dict] = {}
    for commit in sorted(approved_changes):
        r = by_risk.setdefault(level.get(commit) or "unknown", {"changes": 0, "approvals": 0})
        r["changes"] += 1
        r["approvals"] += approvals_of[commit]
    for r in by_risk.values():
        r["per_change"] = _ratio(r["approvals"], r["changes"])

    attempted = taken + len(failures)
    return {
        "window": window.as_dict(),
        "domains": per,
        "commands_by_person_agent_unknown": [person, agent, unknown],
        "approvals_in_window": approvals,
        "per_approved_change": {
            "commands_by_person_or_agent": _ratio(taken, approvals),
            "commands_by_person": _ratio(person, approvals),
        },
        "person_touches": {
            "approvals_of_human_requests": len(change_runs),
            "commands_outside_an_approved_request": len(outside),
            "request_steps_not_found": sum(missing for _, _, missing in change_runs),
            "approval_runs_without_a_change_step": len(matched) - len(change_runs),
            "per_approved_change": _ratio(touches, approvals),
        },
        "approvals_per_approved_change_by_risk": by_risk,
        "approval_runs": len(matched),
        "refused_or_failed_per_command": _ratio(bad, taken),
        "refusals_per_command": {
            "commands": taken,
            "refused": refused,
            "effects_failed": effects,
            "refused_or_failed": _ratio(bad, taken),
            "failed_before_the_gate": len(failures),
            "failed_before_the_gate_per_command_attempted": _ratio(len(failures), attempted),
            "all_per_command_attempted": _ratio(bad + len(failures), attempted),
        },
        "failed_before_the_gate": dict(by_kind),
        "failed_before_the_gate_without_a_fix": sum(1 for f in failures if not f.get("has_fix")),
        "failed_before_the_gate_unreadable": malformed,
        "failed_before_the_gate_since": first,
        "failed_before_the_gate_per_change_approved_since": _ratio(len(failures), approved_since),
    }


def render(m: dict) -> str:
    rows = ["| | " + " | ".join(m["domains"]) + " |", "|---|" + "---|" * len(m["domains"])]

    def row(label, f):
        rows.append(f"| {label} | " + " | ".join(str(f(d)) for d in m["domains"].values()) + " |")

    row("kernel commands", lambda d: d["commands"])
    row("… by a person / an agent / the kernel / unknown",
        lambda d: "{} / {} / {} / {}".format(*(d["commands_by_actor"].get(k, 0)
                                               for k in ("person", "agent", "system", "unknown"))))
    row("refused at the gate", lambda d: d["refused"])
    row("failed effects", lambda d: d["effects_failed"])
    row("approvals in the window", lambda d: d["approvals_in_window"])
    row("commits (never approved)", lambda d: f"{d['commits']} ({d['commits_never_approved']})")
    row("commits with a failed check", lambda d: d["commits_with_a_failed_check"])
    t, p, q = m["per_approved_change"], m["person_touches"], m["refusals_per_command"]
    risk = "; ".join(f"{k} {v['per_change']} ({v['approvals']} for {v['changes']})"
                     for k, v in m["approvals_per_approved_change_by_risk"].items()) or "none"
    w = m["window"]
    rows += ["",
             f"Window: from {w['since'] or 'the first record'} to {w['until'] or 'the last'}.",
             f"Per change approved in the window ({m['approvals_in_window']}): "
             f"{t['commands_by_person_or_agent']} commands by a person or agent, "
             f"{t['commands_by_person']} by a person.",
             f"Approved human requests: {m['approval_runs']}. Refused or failed per command by a "
             f"person or agent: {m['refused_or_failed_per_command']}.",
             f"Failed before the gate (recorded since D1b): {m['failed_before_the_gate'] or 'none'}, "
             f"{m['failed_before_the_gate_without_a_fix']} without a fix; per change approved since "
             f"{m['failed_before_the_gate_since'] or 'the first'}: "
             f"{m['failed_before_the_gate_per_change_approved_since']}.",
             f"A person's touches per approved change: {p['per_approved_change']} "
             f"({p['approvals_of_human_requests']} approved requests + "
             f"{p['commands_outside_an_approved_request']} commands outside one; "
             f"{p['request_steps_not_found']} request steps not found in the logs; "
             f"{p['approval_runs_without_a_change_step']} approved requests without a change step, not counted).",
             f"Approvals per approved change, by risk: {risk}.",
             f"Per command: refused or failed {q['refused_or_failed']} ({q['refused']} + {q['effects_failed']} "
             f"in {q['commands']}); failed before the gate {q['failed_before_the_gate_per_command_attempted']} "
             f"per command attempted ({q['failed_before_the_gate']}); all three "
             f"{q['all_per_command_attempted']} per command attempted."]
    return "\n".join(rows)


def _date(value: str) -> str:
    if _when(value) is None:
        raise argparse.ArgumentTypeError(fixed(f"{value!r} is not a date or time",
                                               "give an ISO date or time, e.g. 2026-11-10 or 2026-11-10T09:00:00+00:00"))
    return value


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--since", type=_date, help="count only what happened at or after this date or time (ISO, UTC "
                                                "if no offset)")
    ap.add_argument("--until", type=_date, help="count only what happened before this date or time")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    m = measure(Path(a.root), a.since, a.until)
    print(json.dumps(m, indent=2, sort_keys=True) if a.json else render(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
