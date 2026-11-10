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


def _reserved(role: str) -> bool:
    return role == "system" or role.startswith(("external:", "handoff:"))


def suggest_rules(d: Domain) -> dict[str, dict[str, Any]]:
    """Outcome rules promoted mechanically from the declaration as it is (ADR-0048, Consequences):
    an outcome that every non-system action reaching it today reaches only with `requires: human`
    gets a `requires: human` rule. Nothing is judged: the rule says what the actions already say,
    so that an action added later is held to it too. An outcome a rule already guards is left out.
    Returned as declaration entries, `proposed`, with the actions they came from in the reason."""
    guarded = {r.on for r in d.rules.values()}
    by: dict[str, set[str]] = {}
    for name, a in d.actions.items():
        if all(_reserved(r if isinstance(r, str) else r.role) for r in a.actor):
            continue                                    # the kernel's replies, handoffs: not held to rules
        tr = d.transitions.get(a.object_type)
        froms = [None] if (a.creates or tr is None) else list(tr.matrix)
        for frm in froms:
            for outcome in reaches(d, name, frm):
                by.setdefault(outcome, set()).add(name)
    out: dict[str, dict[str, Any]] = {}
    for outcome, names in sorted(by.items()):
        if outcome in guarded or not all(d.actions[n].requires == "human" for n in names):
            continue
        obj, part = outcome.split(".", 1)
        rid = f"only-a-person-{obj.lower()}-{part.replace('_', '-').lower()}"
        acts = ", ".join(sorted(names))
        tr = d.transitions.get(obj)
        art = "an" if obj[:1].lower() in "aeiou" else "a"
        what = (f"brings {art} {obj} to {part}" if tr is not None and part in tr.matrix
                else f"sets the {part} of {art} {obj}")
        out[rid] = {"on": outcome, "requires": "human",
                    "reason": f"Only a person {what}: every action that does so today requires a person "
                              f"({acts}).",
                    "source": {"kind": "system", "ref": f"promoted from requires: human on {acts}"},
                    "status": "proposed"}
    return out


def main(argv: list[str] | None = None) -> int:
    """`python -m toprope.decl.rules suggest <domain.yaml>`: print the promoted rules as YAML."""
    import argparse
    import sys

    import yaml

    from . import load_domain
    ap = argparse.ArgumentParser(prog="python -m toprope.decl.rules")
    ap.add_argument("cmd", choices=["suggest"])
    ap.add_argument("declaration")
    args = ap.parse_args(argv)
    rules = suggest_rules(load_domain(args.declaration))
    sys.stdout.write(yaml.safe_dump({"rules": rules}, sort_keys=False, allow_unicode=True) if rules else "rules: {}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
