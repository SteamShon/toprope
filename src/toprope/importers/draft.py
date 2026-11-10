"""Candidates → a proposed draft (ADR-0051): each element `proposed`, citing its place."""
from __future__ import annotations

import copy
from typing import Any

from ..workspace import _set, element_path, is_element
from .port import Extraction


def build(domain: str, extraction: Extraction, roles: list[str]) -> dict[str, Any]:
    doc: dict[str, Any] = {"domain": domain, "version": 1, "roles": [], "objects": {}, "actions": {}, "transitions": {}}
    for c in extraction.candidates:
        segs = element_path(c.path)
        value = copy.deepcopy(c.value)
        if is_element(segs) and isinstance(value, dict):
            value = {**value, "source": {"kind": "system", "ref": c.ref}, "status": "proposed"}
        _set(doc, segs, value)
    used = sorted({r for a in doc["actions"].values() for r in a.get("actor") or [] if isinstance(r, str)})
    doc["roles"] = used or []
    return doc
