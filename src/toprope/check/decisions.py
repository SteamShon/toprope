"""The change check's impact, stated as the decisions a person makes by approving (ADR-0049, D2).

Each change between two declarations becomes one sentence in the domain's own words: the
reasons its rules give, its actions and states. "Refunds are allowed within 7 days of purchase
becomes ... within 30 days" says more to the owner than "changes 1 precondition, affects 4 cell
tests", which the impact report keeps for the reviewer.
"""
from __future__ import annotations

from typing import Any

from ..decl.interface import review_contents
from ..decl.models import Domain

Q = "“{}”"


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _cell(c: Any) -> str:
    """What a matrix cell, as `review_contents` shows it, does to the action."""
    if not isinstance(c, dict):
        return str(c)
    if "deny" in c:
        return "is refused (" + Q.format(c["deny"]) + ")"
    if "by_role" in c:
        return "depends on the role: " + "; ".join(
            f"{r}: {_cell(v if isinstance(v, dict) else {'value': v})}" for r, v in c["by_role"].items())
    v = c.get("value", c.get("to"))
    if v == "n/a":
        return "does not apply"
    if v == "undecided":
        return "is undecided, so refused"
    return f"moves it to {v}"


def _who(a: dict[str, Any]) -> str:
    who = ", ".join(x if isinstance(x, str) else str(x) for x in a.get("actor") or []) or "nobody"
    return who + (" (a person only)" if a.get("requires") == "human" else "")


def decisions(new: Domain, old: Domain | None) -> list[dict[str, str]]:
    """What approving the change from `old` to `new` decides, one sentence per change. Wording
    and examples decide nothing, so they are left out."""
    if old is None:
        return [{"where": "domain", "decide": f"{new.domain} starts with {len(new.actions)} action(s) and "
                 f"{len(new.objects)} kind(s) of thing"}]
    before, after = review_contents(old), review_contents(new)
    out: list[dict[str, str]] = []

    def say(where: str, text: str) -> None:
        out.append({"where": where, "decide": text})

    for key in sorted(set(before) | set(after)):
        b, a = before.get(key), after.get(key)
        if b == a:
            continue
        kind, _, name = key.partition(":")
        if kind == "precondition":
            action = name.split(".")[0]
            if b is None:
                say(key, f"{action} gets a new rule: " + Q.format(a.get("reason")))
            elif a is None:
                say(key, f"{action} loses the rule " + Q.format(b.get("reason")) + ": it will no longer refuse on it")
            elif b.get("reason") != a.get("reason"):
                say(key, f"{action}: " + Q.format(b.get("reason")) + " becomes " + Q.format(a.get("reason")))
            else:
                say(key, f"{action}: the rule " + Q.format(a.get("reason")) + f" now checks `{a.get('check')}` "
                         f"(was `{b.get('check')}`), and its reason still says the same")
        elif kind == "cell":
            obj, state, action = name.split(".", 2)
            if b is None:
                say(key, f"When {_a(obj)} is {state}, {action} {_cell(a)}")
            elif a is None:
                say(key, f"When {_a(obj)} is {state}, {action} is no longer decided, so it is refused")
            else:
                say(key, f"When {_a(obj)} is {state}, {action} {_cell(b)}; it will be: {_cell(a)}")
        elif kind == "action":
            if b is None:
                say(key, f"New action {name}: {a.get('description', '')} Who may take it: {_who(a)}")
            elif a is None:
                say(key, f"The action {name} goes away: nobody can "
                         + str(b.get("description") or name).rstrip(".").lower())
            else:
                if _who(b) != _who(a):
                    say(key, f"{name}: who may take it changes from {_who(b)} to {_who(a)}")
                rest = ("actor", "requires", "description")
                if {k: v for k, v in b.items() if k not in rest} != {k: v for k, v in a.items() if k not in rest}:
                    say(key, f"{name}: what it does changes (its target, effects or event)")
        elif kind == "invariant":
            if b is None:
                say(key, "A new rule that always holds: " + Q.format(a.get("reason")))
            elif a is None:
                say(key, "No longer always holds: " + Q.format(b.get("reason")))
            elif a.get("reason") != b.get("reason"):
                say(key, "The rule " + Q.format(b.get("reason")) + " becomes " + Q.format(a.get("reason")))
            else:
                say(key, "The rule " + Q.format(a.get("reason")) + " now checks something else")
        elif kind in ("object", "link", "role", "property", "handoff", "stages"):
            label = {"property": "fact", "stages": "stages of"}.get(kind, kind)
            if b is None or a is None:
                say(key, f"{'New' if b is None else 'Removed'} {label}: {name}")
            elif kind != "object" or {k: v for k, v in b.items() if k != "description"} != \
                    {k: v for k, v in a.items() if k != "description"}:
                say(key, f"Changed {label}: {name}")
    old_rules = {k: r.model_dump(mode="json") for k, r in old.rules.items()}
    new_rules = {k: r.model_dump(mode="json") for k, r in new.rules.items()}
    for rid in sorted(set(old_rules) | set(new_rules)):
        if old_rules.get(rid) != new_rules.get(rid):
            r = new_rules.get(rid) or old_rules[rid]
            verb = "new" if rid not in old_rules else "removed" if rid not in new_rules else "changed"
            say(f"rule:{rid}", f"Outcome rule {verb}: " + Q.format(r.get("reason")) + f" (on {r.get('on')})")
    return out


def render(items: list[dict[str, str]]) -> str:
    if not items:
        return "Approving this decides nothing new: only wording or examples change.\n"
    return "Approving this decides:\n" + "".join(f"  - {d['decide']}\n" for d in items)
