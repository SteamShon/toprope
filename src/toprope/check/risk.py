"""How risky a change is (ADR-0050): computed from the change check, never declared.

Low when every check that ran passed, the capability diff found no widening, nothing was
removed, no invariant or outcome rule changed, the in-flight check found nothing, and nothing
about who may take a person-only step changed (even a narrowing: ADR-0050, Resolved 2).
Anything else is high, with the reasons. A first version is high: there is nothing to compare.
"""
from __future__ import annotations

from typing import Any

from ..decl.models import Domain

LOW, HIGH = "low", "high"


def _person_only(d: Domain) -> dict[str, Any]:
    """What decides who may take a person-only step: per person-only action, its `requires` and
    actor rules; the approval rule; the outcome rules' `requires`."""
    dump = lambda x: x.model_dump(mode="json") if hasattr(x, "model_dump") else x  # noqa: E731
    out: dict[str, Any] = {"approval": dump(d.approval)}
    for name, a in d.actions.items():
        out[f"action:{name}"] = {"requires": a.requires, "actor": [dump(x) for x in a.actor]}
    for rid, r in d.rules.items():
        out[f"rule:{rid}"] = dump(r.requires)
    return out


def assess(report: Any, new: Domain, old: Domain | None) -> tuple[str, list[str]]:
    if old is None:
        return HIGH, ["a first version: nothing to compare with"]
    reasons: list[str] = []
    for name, res in report.checks.items():
        if res.ran and not res.ok:
            reasons.append(f"the {name} check failed")
    cap = report.checks.get("capability")
    if cap is not None:
        reasons += [f"widening: {p.message}" for p in cap.problems if p.severity == "warning"]
    flight = report.checks.get("in_flight")
    if flight is not None and flight.ran and flight.problems:
        reasons.append(f"in flight: {len(flight.problems)} object(s) in a state the change affects")
    diff = report.diff or {}
    if diff.get("removed"):
        reasons.append("removed: " + ", ".join(diff["removed"][:5]))
    touched = [k for k in (diff.get("changed") or []) + (diff.get("added") or []) + (diff.get("removed") or [])
               if k.startswith(("invariant:", "rule:"))]
    if touched:
        reasons.append("an invariant or outcome rule changed: " + ", ".join(sorted(set(touched))[:5]))
    was, now = _person_only(old), _person_only(new)
    person_only = {n for n, a in {**old.actions, **new.actions}.items()
                   if (old.actions.get(n) and old.actions[n].requires == "human")
                   or (new.actions.get(n) and new.actions[n].requires == "human")}
    who = sorted(k for k in set(was) | set(now)
                 if was.get(k) != now.get(k)
                 and (not k.startswith("action:") or k.split(":", 1)[1] in person_only))
    if who:
        reasons.append("who may take a person-only step changed: " + ", ".join(who[:5]))
    return (HIGH, reasons) if reasons else (LOW, [])


def summary(level: str, reasons: list[str]) -> str:
    return level if not reasons else f"{level}: " + "; ".join(reasons)


def parse(summary_text: str) -> tuple[str, list[str]]:
    level, _, rest = (summary_text or "").partition(": ")
    return level.strip(), [r for r in rest.split("; ") if r]
