"""The capability diff (ADR-0048 §3): who can reach each outcome, before and after a change.

An outcome is an object's state (`Experiment.approved`) or a property an effect sets
(`Experiment.approved_by`). A path to it is an action, from a state, with:
- the actors that may take it (the action's actor rules, narrowed by a per-role cell);
- whether it requires a person;
- its preconditions.

A change that widens how an outcome that already existed can be reached is a warning:
- a new path;
- a new actor on a path;
- a path that no longer requires a person;
- a dropped precondition.

A narrowing is info. A wholly new outcome (a new state or property) is info: a widening is about
what was reachable before. M1 missed rule conflicts because a new action went around a rule bound
to one action (M1-report, *Why*); this finds such a path whatever the rules say.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..decl.models import ByRole, Deny, Domain, Target

NOT_TO = ("n/a", "undecided")


@dataclass(frozen=True)
class Path:
    actors: frozenset[str]
    human: bool
    preconditions: frozenset[str]


def _actors(action: Any, only: set[str] | None = None) -> frozenset[str]:
    out = set()
    for r in action.actor:
        role = r if isinstance(r, str) else r.role
        if only is not None and role not in only:
            continue
        out.add(role if isinstance(r, str) or not r.where else f"{role} where {r.where}")
    return frozenset(out)


def _targets(cell: Any) -> list[tuple[str, set[str] | None]]:
    if isinstance(cell, str):
        return [] if cell in NOT_TO else [(cell, None)]
    if isinstance(cell, Target):
        return [(cell.to, None)]
    if isinstance(cell, ByRole):
        out: dict[str, set[str]] = {}
        for role, v in cell.by_role.items():
            to = v if isinstance(v, str) else None
            if to and to not in NOT_TO:
                out.setdefault(to, set()).add(role)
        return list(out.items())
    if isinstance(cell, Deny):
        return []
    return []


def capabilities(d: Domain) -> dict[str, dict[tuple[str, str], Path]]:
    """Every outcome, and every path to it: {"Object.state": {(action, from): Path}}."""
    out: dict[str, dict[tuple[str, str], Path]] = {}

    def add(outcome: str, action: str, frm: str, only: set[str] | None = None) -> None:
        a = d.actions.get(action)
        if a is None:
            return
        out.setdefault(outcome, {})[(action, frm)] = Path(
            _actors(a, only), a.requires == "human", frozenset(p.id for p in a.preconditions))

    for obj, tr in d.transitions.items():
        for state, row in tr.matrix.items():
            for action, cell in row.items():
                for to, roles in _targets(cell):
                    add(f"{obj}.{to}", action, state, roles)
        for name, a in d.actions.items():
            if a.creates == obj and tr.initial:
                add(f"{obj}.{tr.initial}", name, "(new)")
    for name, a in d.actions.items():
        for e in a.effects:
            for key in (e.set or {}):
                if key.startswith("target.") and a.target:
                    add(f"{a.target}.{key.split('.', 1)[1]}", name, "*")
    return out


def capability_diff(new: Domain, old: Domain) -> list[tuple[str, str, str]]:
    """(severity, where, message) for each widening (warning) and narrowing (info)."""
    before, after = capabilities(old), capabilities(new)
    found: list[tuple[str, str, str]] = []
    for outcome in sorted(after):
        if outcome not in before:
            found.append(("info", f"outcome:{outcome}", f"a new outcome, {outcome}"))
            continue
        was, now = before[outcome], after[outcome]
        for (action, frm), p in sorted(now.items()):
            where = f"actions.{action}"
            path = f"{action} from {frm}" if frm not in ("*", "(new)") else action
            o = was.get((action, frm))
            if o is None:
                who = ", ".join(sorted(p.actors)) or "nobody"
                found.append(("warning", where, f"{outcome} can now be reached by a new path: {path}, by {who}"
                              + ("" if p.human else ", not only by a person")))
                continue
            if p.actors - o.actors:
                found.append(("warning", where, f"{outcome} via {path}: new actor(s) "
                              f"{', '.join(sorted(p.actors - o.actors))}"))
            if o.human and not p.human:
                found.append(("warning", where, f"{outcome} via {path} no longer requires a person"))
            if o.preconditions - p.preconditions:
                found.append(("warning", where, f"{outcome} via {path} no longer checks "
                              f"{', '.join(sorted(o.preconditions - p.preconditions))}"))
            if (o.actors - p.actors) or (p.human and not o.human) or (p.preconditions - o.preconditions):
                found.append(("info", where, f"{outcome} via {path} is narrower"))
        for (action, frm) in sorted(set(was) - set(now)):
            found.append(("info", f"actions.{action}", f"{outcome} is no longer reached by {action} from {frm}"))
    return found
