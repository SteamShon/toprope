"""Measure friction in the self domains' change loop from their logs (ADR-0049, F1).

    uv run python tools/usability_baseline.py [--root .] [--json]

Reads, per self domain:
- `domains/<d>/events/idempotency.jsonl`: one entry per kernel command, with its outcome;
- `domains/<d>/events/events.jsonl`: who each actor is (person, agent, system) and failed
  effects;
- `.toprope/commits/<d>/`: commits, check runs, approvals, deployments;
- `.toprope/approval-runs.jsonl`: the researcher's approved human requests (ADR-0039).

What it cannot see: a command that fails before the gate (a bad argument, an unresolved
citation, a crash) writes nothing, so it is not counted. ADR-0049's theme 1 records those.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

SYSTEM_PREFIXES = ("external:", "handoff:")


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
    """A check that ran and failed; a skipped check is not a failure."""
    return not row["ok"] and not row.get("summary", "").startswith("skipped")


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
    for key, outcome in finished.items():
        actor_id, action = json.loads(key)[:2]
        kind = _kind(actor_id, kinds)
        by_kind[kind] += 1
        if outcome.get("status") != "ok":
            refused_by_kind[kind] += 1
            refused_codes[f"{action}:{outcome.get('code')}"] += 1

    effects_failed = sum(1 for r in events if json.loads(r["event"])["type"] == "EffectFailed")

    store = root / ".toprope" / "commits" / domain
    commits = [r["id"] for r in _jsonl(store / "log.jsonl")]
    approved = {r["commit"] for r in _jsonl(store / "approvals.jsonl")}
    deployed = {r["commit"] for r in _jsonl(store / "deployments.jsonl")}
    failed_checks = {r["commit"] for r in _jsonl(store / "checks.jsonl") if _check_failed(r)}

    commands = sum(by_kind.values())
    actor_commands = by_kind["person"] + by_kind["agent"] + by_kind["unknown"]
    n_approved = len(approved)
    return {
        "commands": commands,
        "commands_by_actor": dict(by_kind),
        "commands_unfinished": len(started - finished.keys()),
        "refused": sum(refused_by_kind.values()),
        "refused_by_actor": dict(refused_by_kind),
        "refused_codes": dict(refused_codes),
        "effects_failed": effects_failed,
        "commits": len(commits),
        "commits_approved": n_approved,
        "commits_deployed": len(deployed),
        "commits_never_approved": len([c for c in commits if c not in approved]),
        "commits_with_a_failed_check": len(failed_checks),
        "per_approved_commit": {
            "commands_by_person_or_agent": _ratio(actor_commands, n_approved),
            "commands_by_person": _ratio(by_kind["person"], n_approved),
        },
        "refused_or_failed_per_command": _ratio(sum(refused_by_kind.values()) + effects_failed,
                                                commands),
    }


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def measure(root: Path) -> dict:
    root = Path(root)
    domains = sorted(p.name for p in (root / "domains").iterdir()
                     if (p / "events" / "idempotency.jsonl").exists()) if (root / "domains").exists() else []
    per = {d: measure_domain(root, d) for d in domains}
    total_commands = sum(m["commands"] for m in per.values())
    bad = sum(m["refused"] + m["effects_failed"] for m in per.values())
    approved = sum(m["commits_approved"] for m in per.values())
    person = sum(m["commands_by_actor"].get("person", 0) for m in per.values())
    agent = sum(m["commands_by_actor"].get("agent", 0) + m["commands_by_actor"].get("unknown", 0)
                for m in per.values())
    return {
        "domains": per,
        # A change is made in one domain and shipped through another, so a change's commands
        # are counted across all of them.
        "per_approved_commit": {
            "commands_by_person_or_agent": _ratio(person + agent, approved),
            "commands_by_person": _ratio(person, approved),
        },
        "approval_runs": len(_jsonl(root / ".toprope" / "approval-runs.jsonl")),
        "refused_or_failed_per_command": _ratio(bad, total_commands),
        "not_counted": "commands that fail before the gate write nothing (ADR-0049, theme 1)",
    }


def render(m: dict) -> str:
    rows = ["| | " + " | ".join(m["domains"]) + " |", "|---|" + "---|" * len(m["domains"])]

    def row(label, f):
        rows.append(f"| {label} | " + " | ".join(str(f(d)) for d in m["domains"].values()) + " |")

    row("kernel commands", lambda d: d["commands"])
    row("… by a person / an agent / the system",
        lambda d: "{} / {} / {}".format(*(d["commands_by_actor"].get(k, 0)
                                          for k in ("person", "agent", "system"))))
    row("refused at the gate", lambda d: d["refused"])
    row("failed effects", lambda d: d["effects_failed"])
    row("commits (approved, deployed)",
        lambda d: f"{d['commits']} ({d['commits_approved']}, {d['commits_deployed']})")
    row("commits with a failed check", lambda d: d["commits_with_a_failed_check"])
    row("commands per approved commit, by a person or agent",
        lambda d: d["per_approved_commit"]["commands_by_person_or_agent"])
    row("… by a person", lambda d: d["per_approved_commit"]["commands_by_person"])
    rows.append("")
    t = m["per_approved_commit"]
    rows.append(f"All domains, per approved commit: {t['commands_by_person_or_agent']} commands by a "
                f"person or agent, {t['commands_by_person']} by a person.")
    rows.append(f"Approved human requests: {m['approval_runs']}. Refused or failed per command, "
                f"all domains: {m['refused_or_failed_per_command']}. Not counted: {m['not_counted']}.")
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
