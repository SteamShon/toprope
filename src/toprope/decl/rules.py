"""Outcome rules (ADR-0048): which rules an action meets on its way, and whether an actor meets them.

An action reaches an outcome directly (its matrix cell moves the object into a state; its effects
set a property) or through the kernel-service replies it starts (`call ... reply R`: R's cell and
effects, from the same state). Either way the rule is checked against the action's actor, the one
who started it: a reply's own actor is the kernel (a `system` actor), which carries out what an
allowed action asked, so rules do not apply to `system` actors.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import ByRole, Deny, Domain, Rule, RuleCheck, Target


def _to(cell: Any) -> set[str]:
    if isinstance(cell, str):
        return set() if cell in ("n/a", "undecided") else {cell}
    if isinstance(cell, Target):
        return {cell.to}
    if isinstance(cell, ByRole):
        return {v for v in cell.by_role.values() if isinstance(v, str) and v not in ("n/a", "undecided")}
    if isinstance(cell, Deny):
        return set()
    return set()


def reaches(d: Domain, action: str, from_state: str | None) -> set[str]:
    """The outcomes (`Object.state`, `Object.property`) an action reaches from a state, itself or
    through the replies it starts."""
    out: set[str] = set()
    names = [action]
    a = d.actions.get(action)
    if a is not None:
        names += [e.reply for e in a.effects if e.call and e.reply]
    for name in names:
        b = d.actions.get(name)
        if b is None:
            continue
        obj = b.object_type
        tr = d.transitions.get(obj)
        if tr is not None:
            if b.creates and tr.initial:
                out.add(f"{obj}.{tr.initial}")
            elif from_state is not None:
                out |= {f"{obj}.{s}" for s in _to(tr.matrix.get(from_state, {}).get(name)) if s != from_state}
        for e in b.effects:
            for key in e.set or {}:
                if key.startswith("target."):
                    out.add(f"{obj}.{key.split('.', 1)[1]}")
    return out


def covering(d: Domain, action: str, from_state: str | None) -> list[tuple[str, Rule]]:
    hit = reaches(d, action, from_state)
    return [(rid, r) for rid, r in d.rules.items() if r.on in hit]


def meets(rule: Rule, kind: str, roles: tuple[str, ...] | set[str], principal_roles: Any = None,
          check: Callable[[str], bool] | None = None) -> bool:
    """Whether an actor of this kind and roles meets the rule. A `system` actor is not held to it.
    An agent meets a roles rule only if its principal also holds one of the roles. A `check` rule
    is decided by `check(expression)`, evaluated by the caller against the actor, target and
    params; without one (a static reading: the capability diff, the TLA+ moves) it is left to the
    guard that evaluates it, and counts as met here."""
    if kind == "system":
        return True
    if isinstance(rule.requires, RuleCheck):
        return True if check is None else check(rule.requires.check)
    if rule.requires == "human":
        return kind == "person"
    allowed = set(rule.requires.roles)
    if not allowed & set(roles):
        return False
    return kind != "agent" or bool(allowed & set(principal_roles or ()))
