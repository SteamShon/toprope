"""Measure friction in the self domains' change loop from their logs (ADR-0049, F1).

    uv run python tools/usability_baseline.py [--root .] [--json]

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

What it cannot see: a command that fails before the gate (a bad argument, an unresolved
citation, a crash) writes nothing, so it is not counted. ADR-0049's theme 1 records those.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

SYSTEM_PREFIXES = ("external:", "handoff:")
APPROVE = "approve_commit"
# Checks whose `ok: false` is a state of the commit, not a finding: `confirmed` is false while
# proposed elements are left (ADR-0041), and a skipped check did not run.
NOT_FINDINGS = {"confirmed"}


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


def measure_domain(root: Path, domain: str) -> dict:
    ev_dir = root / "domains" / domain / "events"
    events = _jsonl(ev_dir / "events.jsonl")
    kinds = _actor_kinds(events)

    started, finished = set(), {}
    for row in _jsonl(ev_dir / "idempotency.jsonl"):
        if row["state"] == "pending":
            started.add(row["key"])
        else:
            finished[row["key"]] = json.loads(row["state"])
    by_kind, refused_by_kind, refused_codes = Counter(), Counter(), Counter()
    approvals = 0
    for key, outcome in finished.items():
        actor_id, action = json.loads(key)[:2]
        kind = _kind(actor_id, kinds)
        by_kind[kind] += 1
        if outcome.get("status") != "ok":
            refused_by_kind[kind] += 1
            refused_codes[f"{action}:{outcome.get('code')}"] += 1
        elif action == APPROVE and kind == "person":
            approvals += 1

    store = root / ".toprope" / "commits" / domain
    commits = [r["id"] for r in _jsonl(store / "log.jsonl")]
    approved = {r["commit"] for r in _jsonl(store / "approvals.jsonl")}
    failed_checks = {r["commit"] for r in _jsonl(store / "checks.jsonl") if _check_failed(r)}

    return {
        "commands": sum(by_kind.values()),
        "commands_by_actor": dict(by_kind),
        "commands_unfinished": len(started - finished.keys()),
        "refused": sum(refused_by_kind.values()),
        "refused_by_actor": dict(refused_by_kind),
        "refused_codes": dict(refused_codes),
        "effects_failed": sum(1 for r in events if json.loads(r["event"])["type"] == "EffectFailed"),
        "approvals_in_window": approvals,
        "commits": len(commits),
        "commits_never_approved": len([c for c in commits if c not in approved]),
        "commits_with_a_failed_check": len(failed_checks),
    }


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def measure(root: Path) -> dict:
    root = Path(root)
    base = root / "domains"
    domains = sorted(p.name for p in base.iterdir()
                     if (p / "events" / "idempotency.jsonl").exists()) if base.exists() else []
    per = {d: measure_domain(root, d) for d in domains}

    def total(f):
        return sum(f(m) for m in per.values())

    person = total(lambda m: m["commands_by_actor"].get("person", 0))
    agent = total(lambda m: m["commands_by_actor"].get("agent", 0))
    unknown = total(lambda m: m["commands_by_actor"].get("unknown", 0))
    taken = person + agent + unknown
    approvals = total(lambda m: m["approvals_in_window"])
    bad = total(lambda m: m["refused"] - m["refused_by_actor"].get("system", 0) + m["effects_failed"])
    return {
        "domains": per,
        "commands_by_person_agent_unknown": [person, agent, unknown],
        "approvals_in_window": approvals,
        "per_approved_change": {
            "commands_by_person_or_agent": _ratio(taken, approvals),
            "commands_by_person": _ratio(person, approvals),
        },
        "approval_runs": len(_jsonl(root / ".toprope" / "approval-runs.jsonl")),
        "refused_or_failed_per_command": _ratio(bad, taken),
        "not_counted": "commands that fail before the gate write nothing (ADR-0049, theme 1)",
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
    t = m["per_approved_change"]
    rows += ["",
             f"Per change approved in the window ({m['approvals_in_window']}): "
             f"{t['commands_by_person_or_agent']} commands by a person or agent, "
             f"{t['commands_by_person']} by a person.",
             f"Approved human requests: {m['approval_runs']}. Refused or failed per command by a "
             f"person or agent: {m['refused_or_failed_per_command']}. Not counted: {m['not_counted']}."]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    m = measure(Path(a.root))
    print(json.dumps(m, indent=2, sort_keys=True) if a.json else render(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
