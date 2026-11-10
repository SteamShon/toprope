"""Candidates → a proposed draft (ADR-0051): each element `proposed`, citing its place.

Two candidates for one element are a conflict: the first is kept, and both places are named.
An undecided cell never replaces a decided one."""
from __future__ import annotations

import copy
from typing import Any

from ..workspace import _set, element_path, is_element
from .port import Extraction


def build(domain: str, extraction: Extraction) -> dict[str, Any]:
    doc: dict[str, Any] = {"domain": domain, "version": 1, "roles": [], "objects": {}, "actions": {}, "transitions": {}}
    placed: dict[tuple[str, ...], tuple[Any, str]] = {}
    for c in extraction.candidates:
        segs = element_path(c.path)
        key = tuple(segs)
        if key in placed:
            before, where = placed[key]
            cell = len(segs) == 5 and segs[0] == "transitions"
            if cell and (c.value == "undecided" or c.value == before):
                continue
            if not cell or before != "undecided":             # two places for one thing, or two moves
                extraction.conflicts.append(f"{c.path} is said twice, at {where} and at {c.ref}; kept the first")
                continue
        placed[key] = (c.value, c.ref)
        value = copy.deepcopy(c.value)
        if is_element(segs) and isinstance(value, dict):
            value = {**value, "source": {"kind": "system", "ref": c.ref}, "status": "proposed"}
        _set(doc, segs, value)
    doc["roles"] = sorted({r for a in doc["actions"].values() for r in a.get("actor") or [] if isinstance(r, str)})
    return doc
