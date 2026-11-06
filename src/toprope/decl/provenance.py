"""Provenance of declaration elements (ADR-0004, ADR-0041)."""

from __future__ import annotations

from typing import Any


def proposed_elements(doc: dict[str, Any]) -> list[str]:
    """Paths of the elements in a raw declaration that are still `status: proposed`: an agent's
    proposal that no person has confirmed (ADR-0041: a hypothesis in the context graph)."""
    out = []
    for kind in ("objects", "links", "actions"):
        for name, el in (doc.get(kind) or {}).items():
            if isinstance(el, dict) and el.get("status") == "proposed":
                out.append(f"{kind}.{name}")
            if kind == "actions" and isinstance(el, dict):
                for p in el.get("preconditions") or []:
                    if isinstance(p, dict) and p.get("status") == "proposed":
                        out.append(f"actions.{name}.preconditions.{p.get('id')}")
    for name, h in (doc.get("handoffs") or {}).items():
        if isinstance(h, dict) and h.get("status") == "proposed":
            out.append(f"handoffs.{name}")
    for inv in doc.get("invariants") or []:
        if isinstance(inv, dict) and inv.get("status") == "proposed":
            out.append(f"invariants.{inv.get('id')}")
    for obj, tr in (doc.get("transitions") or {}).items():
        for state, cells in ((tr or {}).get("matrix") or {}).items():
            for name, c in (cells or {}).items():
                if isinstance(c, dict) and c.get("status") == "proposed":
                    out.append(f"transitions.{obj}.matrix.{state}.{name}")
    return out
