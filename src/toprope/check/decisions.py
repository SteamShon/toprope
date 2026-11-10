"""The change check's impact, stated as the decisions a person makes by approving (ADR-0049, D2).

Each change between two declarations becomes one sentence in the domain's own words: the
reasons its rules give, its actions and states. "Refunds are allowed within 7 days of purchase
becomes ... within 30 days" says more to the owner than "changes 1 precondition, affects 4 cell
tests", which the impact report keeps for the reviewer.

A person approves on these sentences, so nothing enforced may go unsaid (#221's review): every
changed element that has no sentence of its own gets a plain one with its before and after, and
only the glossary, examples, scenarios and purpose, which nothing enforces, are left out, and
counted.
"""
from __future__ import annotations

import json
from typing import Any

from ..decl.interface import review_contents
from ..decl.models import Domain

NOT_ENFORCED = ("term", "fixture", "scenario", "purpose")   # wording and evidence: counted, not decided


def _q(text: Any) -> str:
    """A reason, quoted on one line: a newline in it cannot start a fake item of the list."""
    return "“" + " ".join(str(text).split()) + "”"


def _a(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


def _short(x: Any) -> str:
    s = json.dumps(x, ensure_ascii=False, sort_keys=True, default=str)
    return s if len(s) <= 120 else s[:117] + "..."


def _cell(c: Any) -> str:
    """What a matrix cell, as `review_contents` shows it, does to the action."""
    if not isinstance(c, dict):
        return str(c)
    if "deny" in c:
        return "is refused (" + _q(c["deny"]) + ")"
    if "by_role" in c:
        return "depends on the role: " + "; ".join(
            f"{r}: {_cell(v if isinstance(v, dict) else {'value': v})}" for r, v in c["by_role"].items())
    v = c.get("value", c.get("to"))
    if v == "n/a":
        return "does not apply"
    if v == "undecided":
        return "is undecided, so refused"
    return f"moves it to {v}"


def _actor(x: Any) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " where ".join(str(v) for v in (x.get("role"), x.get("where")) if v) or _short(x)
    return str(x)


def _who(a: dict[str, Any]) -> str:
    who = ", ".join(_actor(x) for x in a.get("actor") or []) or "nobody"
    return who + (" (a person only)" if a.get("requires") == "human" else "")


def _requires(r: Any) -> str:
    if r == "human":
        return "a person"
    if isinstance(r, dict) and r.get("roles"):
        return "role " + ", ".join(r["roles"])
    if isinstance(r, dict) and r.get("check"):
        return f"`{r['check']}`"
    return _short(r)


def decisions(new: Domain, old: Domain | None) -> list[dict[str, str]]:
    """What approving the change from `old` to `new` decides, one sentence per change."""
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
        n = len(out)
        if kind in NOT_ENFORCED:
            continue
        if kind == "precondition":
            action = name.split(".")[0]
            if b is None:
                say(key, f"{action} gets a new rule: {_q(a.get('reason'))} (checks `{a.get('check')}`)")
            elif a is None:
                say(key, f"{action} loses the rule {_q(b.get('reason'))}: it will no longer refuse on it")
            else:
                if b.get("reason") != a.get("reason"):
                    say(key, f"{action}: {_q(b.get('reason'))} becomes {_q(a.get('reason'))}")
                if b.get("check") != a.get("check"):
                    say(key, f"{action}: the rule {_q(a.get('reason'))} checks `{a.get('check')}` "
                             f"(was `{b.get('check')}`)")
        elif kind == "cell":
            obj, state, action = name.split(".", 2)
            if b is None:
                say(key, f"When {_a(obj)} is {state}, {action} {_cell(a)}")
            elif a is None:
                say(key, f"When {_a(obj)} is {state}, {action} {_cell(b)}; it will be undecided, so refused")
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
                for field in sorted((set(b) | set(a)) - {"actor", "requires", "description"}):
                    if b.get(field) != a.get(field):
                        say(key, f"{name}: its {field.replace('_', ' ')} changes from {_short(b.get(field))} "
                                 f"to {_short(a.get(field))}")
        elif kind == "param":
            action, _, param = name.partition(".")
            if b is None:
                say(key, f"{action} takes a new input, {param} ({_short(a)})")
            elif a is None:
                say(key, f"{action} no longer takes {param}")
            else:
                say(key, f"{action}: its input {param} changes from {_short(b)} to {_short(a)}")
        elif kind == "invariant":
            if b is None:
                say(key, f"A new rule that always holds: {_q(a.get('reason'))} (checks `{a.get('check')}`)")
            elif a is None:
                say(key, f"No longer always holds: {_q(b.get('reason'))}")
            else:
                if a.get("reason") != b.get("reason"):
                    say(key, f"The rule {_q(b.get('reason'))} becomes {_q(a.get('reason'))}")
                if a.get("check") != b.get("check"):
                    say(key, f"The rule {_q(a.get('reason'))} checks `{a.get('check')}` (was `{b.get('check')}`)")
        elif kind == "stages":
            if b is not None and a is not None:
                say(key, f"{name}'s stages: {_short(b)} becomes {_short(a)}")
        if len(out) == n and b is not None and a is not None and kind in ("object", "action") and \
                {k: v for k, v in b.items() if k != "description"} == {k: v for k, v in a.items() if k != "description"}:
            continue                                          # only its wording changed
        if len(out) == n:
            # nothing above said it: say it plainly, so no enforced change goes unsaid
            label = {"property": "fact", "stages": "stages of", "link": "link", "role": "role"}.get(kind, kind)
            say(key, f"New {label}: {name}" if b is None else f"Removed {label}: {name}" if a is None
                else f"Changed {label} {name}: {_short(b)} becomes {_short(a)}")
    ob, nb = old.approval.model_dump(mode="json"), new.approval.model_dump(mode="json")
    if ob != nb:
        say("approval", f"Who may approve a commit of this domain changes: {_short(ob)} becomes {_short(nb)}")
    if old.world.actors != new.world.actors:
        say("world.actors", f"The example people change: {_short(old.world.actors)} becomes {_short(new.world.actors)}")
    old_rules = {k: r.model_dump(mode="json") for k, r in old.rules.items()}
    new_rules = {k: r.model_dump(mode="json") for k, r in new.rules.items()}
    for rid in sorted(set(old_rules) | set(new_rules)):
        o, n_ = old_rules.get(rid), new_rules.get(rid)
        if o == n_:
            continue
        if o is None:
            say(f"rule:{rid}", f"New outcome rule: {_q(n_.get('reason'))}: only {_requires(n_.get('requires'))} "
                               f"may bring about {n_.get('on')}")
        elif n_ is None:
            say(f"rule:{rid}", f"Outcome rule removed: {_q(o.get('reason'))} (on {o.get('on')})")
        else:
            parts = [f"{f} {_requires(o.get(f)) if f == 'requires' else _short(o.get(f))} becomes "
                     f"{_requires(n_.get(f)) if f == 'requires' else _short(n_.get(f))}"
                     for f in ("on", "requires", "reason") if o.get(f) != n_.get(f)]
            say(f"rule:{rid}", f"Outcome rule {_q(o.get('reason'))}: " + "; ".join(parts))
    return out


def unenforced(new: Domain, old: Domain | None) -> int:
    """How many changed elements nothing enforces: the glossary, examples, scenarios, purpose."""
    if old is None:
        return 0
    before, after = review_contents(old), review_contents(new)
    return sum(1 for k in set(before) | set(after)
               if before.get(k) != after.get(k) and k.partition(":")[0] in NOT_ENFORCED)


def render(items: list[dict[str, str]], unenforced_count: int = 0) -> str:
    tail = (f"Also changed, but enforced by nothing: {unenforced_count} element(s) of the glossary, "
            "examples, scenarios or purpose.\n") if unenforced_count else ""
    if not items:
        return "Approving this changes no rule: nothing it enforces is different.\n" + tail
    return "Approving this decides:\n" + "".join(f"  - {d['decide']}\n" for d in items) + tail
