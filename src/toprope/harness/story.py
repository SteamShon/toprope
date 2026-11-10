"""A counterexample told as a short story in the domain's own terms (ADR-0049, D3).

A minimal flow that breaks an invariant reads, for the reviewer, as `analyst eli
propose_budget_change C-holdout → ...`. For the owner it reads as: who did what to which thing,
what became of it, and which rule no longer holds, in the words of the rule's reason.
"""
from __future__ import annotations

from typing import Any

from ..decl.models import Domain


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _did(d: Domain, action: str) -> str:
    a = d.actions.get(action)
    text = (a.description or action).rstrip(".") if a else action
    return text[:1].lower() + text[1:]


def _rule(d: Domain, invariant: str) -> str:
    inv = next((v for v in d.invariants if v.id == invariant), None)
    return f"“{' '.join((inv.reason if inv else invariant).split())}”"


def flow_story(d: Domain, flow: dict[str, Any]) -> str:
    """`explore`'s minimal flow: `{invariant, steps: [{actor, action, target, from, outcome}]}`."""
    steps = flow.get("steps") or []
    if not steps:
        return f"The rule {_rule(d, flow.get('invariant', ''))} can be broken."
    first = steps[0]
    obj = d.actions[first["action"]].target if first["action"] in d.actions else "thing"
    field_ = d.transitions[obj].field if obj in d.transitions else "stage"
    lines = [f"Start with {_a(obj)}, {first['target']}"
             + (f", whose {field_} is {first['from']}" if first.get("from") else "") + "."]
    for i, s in enumerate(steps, 1):
        who = s["actor"].replace(" ", ", ", 1) if " " in s["actor"] else s["actor"]
        outcome = s.get("outcome")
        result = ("and it is done" if outcome in ("ok", None) else
                  "and it is refused" if outcome != "invariant-guard" else
                  "and nothing in the rules refuses it: only the last-resort guard stops it")
        lines.append(f"{i}. The {who} asks to {_did(d, s['action'])}, {result}.")
    lines.append(f"Then the rule {_rule(d, flow['invariant'])} would no longer hold.")
    return " ".join(lines)


def inductive_story(d: Domain, case: str, detail: dict[str, Any]) -> str:
    """A move that breaks an invariant from a state the invariants allow (ADR-0035). The case is
    `mechanical:<Object>.<state>.<action>[.<role>]`."""
    start = detail.get("start") or {}
    cell = case.split(":", 1)[1] if ":" in case else case
    parts = cell.split(".")
    obj = parts[0] if parts else "thing"
    action = parts[2] if len(parts) >= 3 else parts[-1]
    role = f"the {parts[3]}" if len(parts) >= 4 else "someone"
    facts = ", ".join(f"{k} {v}" for k, v in start.items() if k != "id" and v not in (None, ""))[:160]
    reason = " ".join(str(detail.get("reason")).split())
    return (f"Take {_a(obj)} like this: {facts or 'any'}. Every rule allows it. Yet if {role} may "
            f"{_did(d, action)} now, the rule \u201c{reason}\u201d breaks. Either the rules should not "
            "allow such a start, or this move should be refused.")


__all__ = ["flow_story", "inductive_story"]
