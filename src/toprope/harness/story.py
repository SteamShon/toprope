"""A counterexample told as a short story in the domain's own terms (ADR-0049, D3).

A minimal flow that breaks an invariant reads, for the reviewer, as `analyst eli
propose_budget_change C-holdout → ...`. For the owner it reads as: who did what to which thing,
what became of it, and which rule no longer holds, in the words of the rule's reason. A thing, a
role or a fact the glossary defines is named by its term (#225's review).
"""
from __future__ import annotations

from typing import Any

from ..decl.models import Domain
from ..decl.words import term

# Outcomes that are not the rules refusing: the command or an effect went wrong (#222's review).
FAILURES = {"invalid-command", "effect-error", "unsupported-effect", "unauthenticated", "unknown-action",
            "not-found"}
BUDGET = 200                                     # characters of facts, cut between facts, never inside one


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _one_line(text: Any) -> str:
    return " ".join(str(text).split())


def _did(d: Domain, action: str) -> str:
    """What asking for the action means, as a verb phrase: its description when that starts with a
    verb, else `take the action <name>`."""
    a = d.actions.get(action)
    text = _one_line(a.description or "").rstrip(".") if a else ""
    first = text.split(" ", 1)[0].lower() if text else ""
    if not text or first in ("the", "a", "an", "this", "that", "one", "each", "every") or text[:1].isdigit():
        return f"take the action {action}" + (f" ({text[:1].lower() + text[1:]})" if text else "")
    return text[:1].lower() + text[1:]


def _rule(d: Domain, invariant: Any) -> str:
    inv = next((v for v in d.invariants if v.id == invariant), None)
    reason = inv.reason if inv else invariant
    return "“" + _one_line(reason) + "”" if reason else "one of its invariants"


def _who(d: Domain, actor: str) -> str:
    """`analyst eli` → `eli (analyst)`, the role by its glossary term."""
    role, _, who = str(actor).partition(" ")
    return f"{who} ({term(d, role)})" if who else term(d, role)


def facts(d: Domain, obj: str, data: dict[str, Any]) -> str:
    """The thing's facts, whole, up to a budget; a declared fact it lacks is said to be missing,
    first, since a missing fact is often why a rule breaks."""
    props = d.objects[obj].properties if obj in d.objects else {}
    parts = [f"no {term(d, k)}" for k in props if data.get(k) in (None, "")]          # first: often the cause
    parts += [f"{term(d, k)} {v}" for k, v in data.items() if k != "id" and v not in (None, "")]
    out, used = [], 0
    for p_ in parts:
        if used + len(p_) > BUDGET:
            out.append(f"and {len(parts) - len(out)} more")
            break
        out.append(p_)
        used += len(p_) + 2
    return ", ".join(out) or "any"


def _result(outcome: Any) -> str:
    if outcome in ("ok", None):
        return "and it is done"
    if outcome == "invariant-guard":
        return "and nothing in the rules refuses it: only the last-resort guard stops it"
    if outcome in FAILURES:
        return f"and it fails ({outcome}), which is not a rule refusing it"
    return f"and it is refused ({outcome})"


def flow_story(d: Domain, flow: dict[str, Any]) -> str:
    """`explore`'s minimal flow: `{invariant, steps: [{actor, action, target, from, outcome}]}`.
    Each step names the thing it acts on whenever that changes, with its stage then."""
    steps = flow.get("steps") or []
    if not steps:
        return f"The rule {_rule(d, flow.get('invariant'))} can be broken."
    lines, last = [], None
    for i, s in enumerate(steps, 1):
        obj = d.actions[s["action"]].target if s["action"] in d.actions else "thing"
        field_ = term(d, d.transitions[obj].field) if obj in d.transitions else "stage"
        on = ""
        if s["target"] != last:
            on = f" on {_a(term(d, obj))}, {s['target']}" + (f" (whose {field_} is {s['from']})" if s.get("from") else "") + ","
            last = s["target"]
        lines.append(f"{i}. {_who(d, s['actor'])}{on} asks to {_did(d, s['action'])}, {_result(s.get('outcome'))}.")
    lines.append(f"Then the rule {_rule(d, flow.get('invariant'))} would no longer hold.")
    return " ".join(lines)


def inductive_story(d: Domain, case: str, detail: dict[str, Any]) -> str:
    """A move that breaks an invariant from a state the invariants allow (ADR-0035). The case is
    `mechanical:<Object>.<state>.<action>.<role>`."""
    start = detail.get("start") or {}
    cell = case.split(":", 1)[1] if ":" in case else case
    parts = cell.split(".")
    obj = parts[0] if parts else "thing"
    action = parts[2] if len(parts) >= 3 else parts[-1]
    role = f"the {term(d, parts[3])}" if len(parts) >= 4 else "someone"
    reason = detail.get("reason")
    rule = "“" + _one_line(reason) + "”" if reason else "one of its invariants"
    return (f"Take {_a(term(d, obj))} like this: {facts(d, obj, start)}. Every rule allows it. Yet if {role} may "
            f"{_did(d, action)} now, the rule {rule} breaks. Either the rules should not allow such a "
            "start, or this move should be refused.")


def case_action(d: Domain, case: str) -> str | None:
    """The declared action a generated case exercises: its ids are `<kind>:<Object>.<state>.<action>.<role>`,
    `create:<action>.<role>`, with `@…` details after."""
    body = case.split(":", 1)[1] if ":" in case else case
    for seg in body.split("@", 1)[0].split("."):
        if seg in d.actions:
            return seg
    return None


def case_stories(d: Domain, findings: list[Any], limit: int = 5) -> list[str]:
    """Generated cases whose action only the last-resort guard stopped, one story per action and
    broken rule, with how many cases showed it."""
    groups: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        if f.kind != "invariant":
            continue
        observed = (f.detail or {}).get("observed") or {}
        action = case_action(d, f.case) or f.case
        groups.setdefault((action, _one_line(observed.get("reason") or "")), []).append(f.case)
    out = []
    for (action, reason), cases in list(groups.items())[:limit]:
        rule = "\u201c" + reason + "\u201d" if reason else "one of its invariants"
        did = _did(d, action) if action in d.actions else f"run the case {action}"
        out.append(f"The rules let someone {did}, and then the rule {rule} would no longer hold: only the "
                   f"last-resort guard stopped it ({len(cases)} case(s), e.g. {cases[0]}). A precondition or "
                   "a matrix cell should refuse it.")
    return out


__all__ = ["case_action", "case_stories", "facts", "flow_story", "inductive_story"]
