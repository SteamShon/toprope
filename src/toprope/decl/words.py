"""The domain's own words for its names (ADR-0049, D2 and D3; ADR-0053).

A person reads `LeaveRequest`, `days_since_purchase` and `approve_leave` as a developer's names.
Where the glossary defines a term for one of them (`leave request`), a sentence for a person uses
the term; an action is named by its description (“approve the request”), not by its id.
"""
from __future__ import annotations

import re
from typing import Any


def normal(name: str) -> str:
    """`LeaveRequest`, `leave_request` and `leave-request` all read `leave request`."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(name))
    return " ".join(spaced.replace("_", " ").replace("-", " ").lower().split())


def term(d: Any, name: str) -> str:
    """The glossary's term for a name, when the glossary has one; else the name as declared."""
    glossary = getattr(d, "glossary", None) or {}
    n = normal(name)
    for k in glossary:
        if normal(k) == n:
            return k
    return name


def one_line(text: Any) -> str:
    return " ".join(str(text).split())


def doing(d: Any, action: str) -> str:
    """An action as a person names it: its description, quoted, as a phrase (“refund a paid
    order”); its id when it has no description."""
    a = (getattr(d, "actions", None) or {}).get(action)
    text = one_line(getattr(a, "description", "") or "").rstrip(".") if a is not None else ""
    if not text:
        return action
    if not (len(text) > 1 and text[1].isupper()):          # keep an acronym: "HR approves"
        text = text[:1].lower() + text[1:]
    return f"“{text}”"


def a_(word: str) -> str:
    return f"{'an' if word[:1].lower() in 'aeiou' else 'a'} {word}"


__all__ = ["a_", "doing", "normal", "one_line", "term"]
