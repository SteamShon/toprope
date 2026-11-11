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
from bisect import bisect_left, bisect_right
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


def _bad(path: Path, n: int, what: str) -> SystemExit:
    return SystemExit(fixed(f"{path}:{n}: {what}",
                            "repair or remove that line (`git log -p` on the file shows who wrote it), "
                            "then measure again"))


def _jsonl(path: Path) -> list[dict]:
    """The rows of a JSON-lines log, each with its line number as `_line`."""
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise _bad(path, n, "not a line of JSON") from None
        if not isinstance(row, dict):
            raise _bad(path, n, "not a JSON object")
        rows.append({**row, "_line": n})
    return rows


def _events(path: Path) -> list[dict]:
    """The events of an event log, parsed once."""
    out = []
    for row in _jsonl(path):
        try:
            e = json.loads(row["event"])
            if not isinstance(e, dict):
                raise TypeError
        except (KeyError, TypeError, ValueError):
            raise _bad(path, row["_line"], "no event in it, or one that is not JSON") from None
        out.append(e)
    return out


def _actor_kinds(events: list[dict]) -> dict[str, str]:
    kinds = {}
    for e in events:
        actor = e.get("actor")
        if actor:
            kinds[actor["id"]] = actor["kind"]
    return kinds


def _commands(root: Path, domain: str, events: list[dict] | None = None) -> tuple[list[dict], list[datetime | None]]:
    """The domain's finished commands, in log order, each with its time; and the times of those
    never finished. A command's time is that of the events it appended; one that appended none (a
    refusal) takes the time of the command before it in the log, and has none if no command
    before it has one. A `commit_draft` carries the commit it `made`: the target of the kernel's
    `record_commit` reply that follows it in the log."""
    ev_dir = root / "domains" / domain / "events"
    path = ev_dir / "idempotency.jsonl"
    kinds = _actor_kinds(_events(ev_dir / "events.jsonl") if events is None else events)
    finished, pending, last = {}, {}, None
    drafts: list[dict] = []
    for row in _jsonl(path):
        try:
            key = row["key"]
            outcome = None if row["state"] == "pending" else json.loads(row["state"])
            if outcome is not None and not isinstance(outcome, dict):
                raise TypeError
            t = next((w for e in (outcome or {}).get("events") or [] if (w := _when(e.get("at")))), None)
            actor_id, action, target = (json.loads(key) + [None, None, None])[:3]
        except (KeyError, TypeError, ValueError, AttributeError):
            raise _bad(path, row["_line"], "not a command entry (`key`, and `state` pending or an outcome)") from None
        last = t or last
        if outcome is None:
            pending.setdefault(key, last)
            continue
        c = {"domain": domain, "actor": actor_id, "kind": _kind(str(actor_id), kinds), "action": action,
             "target": target, "outcome": outcome, "t": last, "ok": outcome.get("status") == "ok",
             "seq": len(finished)}
        finished.setdefault(key, c)
        if c["ok"] and action == "commit_draft":
            drafts.append(c)
        elif c["ok"] and action == "record_commit" and c["kind"] == "system":
            for d in drafts:
                d["made"] = target
            drafts = []
    return list(finished.values()), [t for k, t in pending.items() if k not in finished]


def _kind(actor_id: str, kinds: dict[str, str]) -> str:
    if actor_id.startswith(SYSTEM_PREFIXES):
        return "system"
    return kinds.get(actor_id, "unknown")


def _check_failed(row: dict) -> bool:
    """A check that ran and found something."""
    return (not row["ok"] and row.get("check") not in NOT_FINDINGS
            and not row.get("summary", "").startswith("skipped"))


def measure_domain(root: Path, domain: str, window: Window | None = None,
                   parsed: tuple[list[dict], list[dict], list] | None = None) -> dict:
    """`parsed`: the domain's (events, commands, unfinished), if already read."""
    window = window or Window()
    ev_dir = root / "domains" / domain / "events"
    if parsed is None:
        events = _events(ev_dir / "events.jsonl")
        parsed = (events, *_commands(root, domain, events))
    events, commands, unfinished = parsed
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

    return {
        "commands": sum(by_kind.values()),
        "commands_by_actor": dict(by_kind),
        "commands_unfinished": sum(1 for t in unfinished if t in window),
        "refused": sum(refused_by_kind.values()),
        "refused_by_actor": dict(refused_by_kind),
        "refused_codes": dict(refused_codes),
        "effects_failed": sum(1 for e in events if e.get("type") == "EffectFailed" and _when(e.get("at")) in window),
        "approvals_in_window": approvals,
        "commits": len(commits),
        "commits_never_approved": len([c for c in commits if c not in approved]),
        "commits_with_a_failed_check": len(failed_checks),
    }


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


# A request's steps all run inside the workflow's `act` job, which `record` ends; the job stops
# after `timeout-minutes: 20` (.github/workflows/human-request.yml). So a run's commands are no
# earlier than this before its record.
RUN_SPAN = timedelta(minutes=20)
# A person's command this long before a recorded run, with the action and target of one of its
# steps, may be a step of an earlier run of the same request that failed and was not recorded.
RETRY_SPAN = timedelta(minutes=60)
SLACK = timedelta(seconds=1)              # a record's `at` is cut to the second


def _run_steps(run: dict) -> list[dict]:
    """The `run` steps of a recorded request that ran: all of them, or, for a run recorded as
    failed (`ran`, `failed`) or held after a preview (`ran`, `held`; a local apply, ADR-0050 3),
    the ones before the step it stopped at."""
    steps = [st["run"] for st in run.get("steps") or [] if isinstance(st, dict) and isinstance(st.get("run"), dict)]
    ran = run.get("ran")
    if (run.get("failed") or run.get("held")) and isinstance(ran, int):
        n = sum(1 for st in (run.get("steps") or [])[:ran] if isinstance(st, dict) and "run" in st)
        steps = steps[:n]
    return steps


def _failed_step(run: dict) -> dict | None:
    """The `run` step a run recorded as failed stopped at, when it was refused or broke (its
    command did not succeed). A step whose action was taken but whose follow-up failed
    (`accepted`) is among the `ran` steps instead. `failed.step` is its position in `steps`."""
    failed = run.get("failed") or {}
    at = failed.get("step")
    steps = run.get("steps") or []
    if failed.get("accepted") or not isinstance(at, int) or not 1 <= at <= len(steps):
        return None
    st = steps[at - 1]
    return st["run"] if isinstance(st, dict) and isinstance(st.get("run"), dict) else None


def _target_matches(pattern: str, target: object, made: str | None) -> bool:
    """A step's target against a command's: `$commit` is the commit the run's commit_draft made,
    or, when there is none to bind it to, matches nothing."""
    if MADE not in pattern:
        return pattern == target
    return made is not None and pattern.replace(MADE, made) == target


def _match_runs(runs: list[dict], commands: list[dict]) -> list[tuple[dict, list[dict], int]]:
    """Each approved request run with the kernel commands its `run` steps took, in order, and how
    many of its steps were not found. The steps are matched in their order: each takes the
    earliest command not yet taken, by the person the run acted as, with the step's action and
    target, after the step before it, no earlier than `RUN_SPAN` before the run's record or than
    the record before it, and no later than the record. `$commit` is the commit the matched
    commit_draft made. Only commands that succeeded: a step recorded as run succeeded; but the
    step a run recorded as failed stopped at is matched to a command that did not succeed, since
    the run took it, not the person by hand."""
    index: dict[tuple, list[dict]] = {}
    for c in sorted((c for c in commands if c["kind"] == "person" and c["t"]),
                    key=lambda c: (c["t"], c["domain"], c["seq"])):
        index.setdefault((c["actor"], c["action"]), []).append(c)
    times = {k: [c["t"] for c in v] for k, v in index.items()}
    used: set[int] = set()
    out, before = [], None
    for run in sorted(runs, key=lambda r: _when(r.get("at")) or datetime.min.replace(tzinfo=UTC)):
        at = _when(run.get("at"))
        last = _failed_step(run)
        steps = [*_run_steps(run), *([last] if last else [])]
        took: list[dict] = []
        if at is not None:
            lower = max(x for x in (at - RUN_SPAN, before) if x is not None)
            after, made = lower, None
            for st in steps:
                key = (run.get("as"), st.get("action"))
                cands, ts = index.get(key, []), times.get(key, [])
                pattern = str(st.get("target"))
                ok = st is not last                     # the failed step's command did not succeed
                found = None
                for c in cands[bisect_right(ts, after) if not took else bisect_left(ts, after):]:
                    if c["t"] > at + SLACK:
                        break
                    if id(c) not in used and c["ok"] == ok and _target_matches(pattern, c["target"], made):
                        found = c
                        break
                if found is None:
                    continue
                used.add(id(found))
                took.append(found)
                after = found["t"]
                if found["action"] == "commit_draft":
                    made = found.get("made")
        # a failed step not found took no command at the gate (a failure before it, D1b): not missing
        out.append((run, took, len(steps) - (1 if last else 0) - sum(1 for c in took if c["ok"])))
        before = at or before
    return out


def _run_time(run: dict, took: list[dict]) -> datetime | None:
    """When a run counts: at its approval, so a change and the run that approves it fall in the
    same window; a run that approves nothing, at its first command; one with none, at its record."""
    approve = next((c["t"] for c in took if c["action"] == APPROVE and c["ok"]), None)
    return approve or (took[0]["t"] if took else _when(run.get("at")))


def _risk_at(root: Path) -> dict[str, list[tuple[datetime | None, str]]]:
    """Every risk `check_commit` recorded (ADR-0050), per commit, in any domain, in order."""
    level: dict[str, list] = {}
    for path in sorted((root / ".toprope" / "commits").glob("*/checks.jsonl")):
        for r in _jsonl(path):
            if r.get("check") == "risk":
                level.setdefault(r["commit"], []).append(
                    (_when(r.get("at")), str(r.get("summary", "")).split(":", 1)[0].strip()))
    return level


def _risk_when(levels: list[tuple[datetime | None, str]], t: datetime | None) -> str | None:
    """The risk last recorded at or before `t` (a row without a time counts as before)."""
    found = None
    for at, level in sorted(levels, key=lambda x: x[0] or datetime.min.replace(tzinfo=UTC)):
        if at is None or t is None or at <= t + SLACK:
            found = level
    return found


def _changes_touched(took: list[dict]) -> set[str]:
    """The commits a run approved or shipped."""
    out = set()
    for c in took:
        if not c["ok"]:
            continue
        if c["action"] == APPROVE:
            out.add(c["target"])
        elif c["action"] in SHIPS and (ships := shipped_commit({"action": c["action"], "target": c["target"]}, None)):
            out.add(ships)
    return out


def _possibly_failed(c: dict, runs: list[dict]) -> bool:
    """A command with the action and target of a step of a run recorded within RETRY_SPAN after it."""
    for run in runs:
        at = _when(run.get("at"))
        if at is None or c["actor"] != run.get("as") or not (c["t"] < at <= c["t"] + RETRY_SPAN):
            continue
        for st in _run_steps(run):
            pattern = re.escape(str(st.get("target"))).replace(re.escape(MADE), r"[^:]+")
            if st.get("action") == c["action"] and re.fullmatch(pattern, str(c["target"])):
                return True
    return False


def measure(root: Path, since: object = None, until: object = None) -> dict:
    root = Path(root)
    window = Window(since, until)
    base = root / "domains"
    domains = sorted(p.name for p in base.iterdir()
                     if (p / "events" / "idempotency.jsonl").exists()) if base.exists() else []
    parsed = {}
    for d in domains:
        events = _events(base / d / "events" / "events.jsonl")
        parsed[d] = (events, *_commands(root, d, events))
    per = {d: measure_domain(root, d, window, parsed[d]) for d in domains}

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
    # Runs are matched over the whole log, then placed in the window by `_run_time`, so a window
    # edge inside a run neither splits it nor counts its steps as typed by the person.
    commands = [c for d in domains for c in parsed[d][1]]
    runs = _jsonl(root / APPROVAL_RUNS)
    every = _match_runs(runs, commands)
    in_runs = {id(c) for _, took, _ in every for c in took}
    matched = [(r, took, missing) for r, took, missing in every if _run_time(r, took) in window]
    change_runs = [(r, took, missing) for r, took, missing in matched
                   if any(isinstance(st, dict) and "run" in st for st in r.get("steps") or [])]
    outside = [c for c in commands if c["kind"] == "person" and c["t"] in window and id(c) not in in_runs]
    touches = len(change_runs) + len(outside)

    approved_at: dict[str, datetime | None] = {}
    for c in commands:
        if c["ok"] and c["kind"] == "person" and c["action"] == APPROVE and c["t"] in window:
            approved_at.setdefault(c["target"], c["t"])
    approvals_of = Counter(c["target"] for c in outside if c["ok"] and c["action"] == APPROVE)
    for _, took, _ in change_runs:
        approvals_of.update(_changes_touched(took))
    levels = _risk_at(root)
    by_risk: dict[str, dict] = {}
    for commit in sorted(approved_at):
        level = _risk_when(levels.get(commit, []), approved_at[commit]) or "unknown"
        r = by_risk.setdefault(level, {"changes": 0, "approvals": 0})
        r["changes"] += 1
        r["approvals"] += approvals_of[commit]
    for r in by_risk.values():
        r["per_change"] = _ratio(r["approvals"], r["changes"])

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
            "possibly_failed_request_steps": sum(1 for c in outside if c["ok"] and _possibly_failed(c, runs)),
            "per_approved_change": _ratio(touches, approvals),
        },
        "approvals_per_approved_change_by_risk": by_risk,
        "approval_runs": len(matched),
        # how each was approved: in GitHub, or applied at a person's terminal (ADR-0053, 3); a record
        # from before the channel was written is a GitHub run
        "approval_runs_by_channel": dict(Counter(str(r.get("channel") or "github") for r, _, _ in matched)),
        "refused_or_failed_per_command": _ratio(bad, taken),
        "refusals_per_command": {
            "commands": taken,
            "refused": refused,
            "effects_failed": effects,
            "refused_or_failed": _ratio(bad, taken),
            "failed_before_the_gate": len(failures),
            "failed_before_the_gate_per_command_attempted": _ratio(len(failures), taken + len(failures)),
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
             f"Approved human requests: {m['approval_runs']} ("
             + (", ".join(f"{v} {k}" for k, v in sorted(m["approval_runs_by_channel"].items())) or "none")
             + f"). Refused or failed per command by a "
             f"person or agent: {m['refused_or_failed_per_command']}.",
             f"Failed before the gate (recorded since D1b): {m['failed_before_the_gate'] or 'none'}, "
             f"{m['failed_before_the_gate_without_a_fix']} without a fix; per change approved since "
             f"{m['failed_before_the_gate_since'] or 'the first'}: "
             f"{m['failed_before_the_gate_per_change_approved_since']}.",
             f"A person's touches per approved change: {p['per_approved_change']} "
             f"({p['approvals_of_human_requests']} approved requests + "
             f"{p['commands_outside_an_approved_request']} commands outside one; "
             f"{p['request_steps_not_found']} request steps not found in the logs; "
             f"{p['approval_runs_without_a_change_step']} approved requests without a change step, not counted; "
             f"{p['possibly_failed_request_steps']} of the commands outside may be steps of a request run that "
             "failed, which is not recorded).",
             f"Approvals per approved change, by risk: {risk}.",
             f"Per command: refused or failed {q['refused_or_failed']} ({q['refused']} + {q['effects_failed']} "
             f"in {q['commands']}); failed before the gate {q['failed_before_the_gate_per_command_attempted']} "
             f"per command attempted ({q['failed_before_the_gate']}), reported beside the rate, not in it."]
    return "\n".join(rows)


def _date(value: str) -> str:
    if _when(value) is None:
        raise argparse.ArgumentTypeError(fixed(f"{value!r} is not a date or time",
                                               "give an ISO date or time, e.g. 2026-11-10 or 2026-11-10T09:00:00+00:00"))
    return value


def _commit_time(root: Path, ref: str) -> str:
    """The time a commit was made (its committer date), for a window that starts at a merge."""
    import subprocess
    r = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%cI", ref, "--"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise SystemExit(fixed(f"{ref!r} is not a commit in {root}",
                               "give a commit or tag the repository has, e.g. the merge that started the window"))
    return r.stdout.strip()


def _head(root: Path) -> str | None:
    import subprocess
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    when = ap.add_mutually_exclusive_group()
    when.add_argument("--since", type=_date, help="count only what happened at or after this date or time (ISO, UTC "
                                                  "if no offset)")
    when.add_argument("--since-commit", metavar="REF", help="count only what happened at or after this commit was "
                                                            "made (e.g. the merge that started the window)")
    ap.add_argument("--until", type=_date, help="count only what happened before this date or time")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--record", metavar="FILE", help="also write the measure, its window and the repository's HEAD "
                                                     "to this new JSON file (never overwritten)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    since = _commit_time(root, a.since_commit) if a.since_commit else a.since
    if a.record and Path(a.record).exists():
        raise SystemExit(fixed(f"{a.record} exists", "give --record a new file; a recorded measure is never rewritten"))
    m = measure(root, since, a.until)
    print(json.dumps(m, indent=2, sort_keys=True) if a.json else render(m))
    if a.record:
        rec = {"measured_at": datetime.now(UTC).isoformat(timespec="seconds"), "head": _head(root),
               "since_commit": a.since_commit, "measures": m}
        Path(a.record).parent.mkdir(parents=True, exist_ok=True)
        Path(a.record).write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
        print(f"\nRecorded in {a.record}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
