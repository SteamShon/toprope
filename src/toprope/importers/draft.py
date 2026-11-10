"""Candidates → a proposed draft (ADR-0051): each element `proposed`, citing its place.

Two candidates for one element are a conflict: the first is kept, and both places are named.
An undecided cell never replaces a decided one.

A draft can also be joined to one that exists (`plan`): what the existing draft lacks is added,
what it already says the same is left, and what it says differently is a conflict naming both
places; nothing in it is overwritten. The same plan is written as a patch for `toprope-change`
(`loop.py`) or applied to a file (`apply`)."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ..decl.models import RESERVED_ACTORS
from ..workspace import _get, _set, element_path, is_element
from .port import Extraction

UNDECIDED = "undecided"
UNASSIGNED = "unassigned"        # the role an importer names until the interview says who acts


def build(domain: str, extraction: Extraction, places: dict[str, str] | None = None) -> dict[str, Any]:
    """The draft. `places`, if given, receives the place each path was taken from (the citation
    of a bare cell or of a stages entry, which carry none of their own)."""
    doc: dict[str, Any] = {"domain": domain, "version": 1, "roles": [], "objects": {}, "actions": {}, "transitions": {}}
    placed: dict[tuple[str, ...], tuple[Any, str]] = {}
    for c in extraction.candidates:
        segs = element_path(c.path)
        key = tuple(segs)
        if key in placed:
            before, where = placed[key]
            cell = len(segs) == 5 and segs[0] == "transitions"
            if cell and (c.value == UNDECIDED or c.value == before):
                continue
            if not cell or before != UNDECIDED:             # two places for one thing, or two moves
                extraction.conflict(f"{c.path} is said twice, at {where} and at {c.ref}; kept the first", [c.path],
                                    [where, c.ref])
                continue
        placed[key] = (c.value, c.ref)
        if places is not None:
            places[c.path] = c.ref
        value = copy.deepcopy(c.value)
        if is_element(segs) and isinstance(value, dict):
            value = {**value, "source": {"kind": "system", "ref": c.ref}, "status": "proposed"}
        _set(doc, segs, value)
    doc["roles"] = roles_of(doc)
    return doc


def roles_of(doc: dict[str, Any]) -> list[str]:
    """The roles the actions name, leaving out the reserved actors (`external:kernel`, `system`)."""
    return sorted({r for a in (doc.get("actions") or {}).values() if isinstance(a, dict) for r in a.get("actor") or []
                   if isinstance(r, str) and r not in RESERVED_ACTORS and not r.startswith("external:")})


@dataclass
class Item:
    """One change to propose: a path, its value without provenance, and the place it cites."""
    path: str
    value: Any
    ref: str


def bare(v: Any) -> Any:
    return {k: x for k, x in v.items() if k not in ("source", "status")} if isinstance(v, dict) else v


def _where(v: Any) -> str:
    return str(((v or {}).get("source") or {}).get("ref") or "the draft") if isinstance(v, dict) else "the draft"


ORDER = ("roles", "objects", "links", "actions", "transitions")


def plan(base: dict[str, Any], new: dict[str, Any], places: dict[str, str], out: Extraction) -> list[Item]:
    """What joining `new` (a built draft) to `base` (an existing draft) changes, in an order the
    loop can propose one by one. Conflicts go into `out`, naming both places."""
    items: list[Item] = []
    base = copy.deepcopy(base)

    def ref_of(path: str, v: Any) -> str:
        return places.get(path) or _where(v)

    def differ(path: str, have: Any, want: Any, what: str = "") -> None:
        out.conflict(f"{path}{what}: the draft has {_show(bare(have))} ({_where(have)}), the source says "
                     f"{_show(bare(want))} ({ref_of(path, want)}); kept the draft's", [path],
                     [_where(have), ref_of(path, want)])

    roles = [r for r in new.get("roles") or [] if r not in (base.get("roles") or [])]
    if roles:
        items.append(Item("roles", sorted({*(base.get("roles") or []), *roles}),
                          next(iter(places.values()), "the source")))
    for name, v in (new.get("objects") or {}).items():
        path, have = f"objects.{name}", (base.get("objects") or {}).get(name)
        if have is None:
            items.append(Item(path, bare(v), ref_of(path, v)))
            continue
        for p, spec in (v.get("properties") or {}).items():
            had = (have.get("properties") or {}).get(p)
            if had is None:
                items.append(Item(f"{path}.properties.{p}", spec, ref_of(path, v)))
            elif had != spec:
                out.conflict(f"{path}.properties.{p}: the draft has {_show(had)} ({_where(have)}), the source says "
                             f"{_show(spec)} ({ref_of(path, v)}); kept the draft's", [f"{path}.properties.{p}"],
                             [_where(have), ref_of(path, v)])
    for section in ("links", "actions"):
        for name, v in (new.get(section) or {}).items():
            path, have = f"{section}.{name}", (base.get(section) or {}).get(name)
            if have is None:
                items.append(Item(path, bare(v), ref_of(path, v)))
            elif not _same(bare(have), bare(v)):
                differ(path, have, v)
    for obj, tr in (new.get("transitions") or {}).items():
        path, have = f"transitions.{obj}", (base.get("transitions") or {}).get(obj)
        if have is None:
            items.append(Item(path, {**{k: x for k, x in tr.items() if k != "matrix"},
                                     "matrix": {s: {} for s in tr.get("matrix") or {}}}, ref_of(path, tr)))
            have = {"field": tr.get("field"), "matrix": {s: {} for s in tr.get("matrix") or {}}}
        elif have.get("field") != tr.get("field") or set(tr.get("matrix") or {}) - set(have.get("matrix") or {}):
            out.conflict(f"{path}: the draft's stages are {have.get('field')} "
                         f"({', '.join(have.get('matrix') or {})}), the source's are {tr.get('field')} "
                         f"({', '.join(tr.get('matrix') or {})}) at {ref_of(path, tr)}; kept the draft's", [path],
                         [ref_of(path, tr)])
            continue
        for state, row in (tr.get("matrix") or {}).items():
            for action, cell in (row or {}).items():
                cpath = f"{path}.matrix.{state}.{action}"
                had = ((have.get("matrix") or {}).get(state) or {}).get(action)
                if had is None or (had == UNDECIDED and cell != UNDECIDED):
                    items.append(Item(cpath, bare(cell), ref_of(cpath, cell)))
                elif cell != UNDECIDED and bare(had) != bare(cell):
                    differ(cpath, had, cell)
    for section, v in new.items():                                # anything a plugged-in extractor adds
        if section in ORDER or section in ("domain", "version") or not isinstance(v, dict):
            continue
        for name, x in v.items():
            path, have = f"{section}.{name}", _get(base, [section, name])
            if have is None:
                items.append(Item(path, bare(x), ref_of(path, x)))
            elif bare(have) != bare(x):
                differ(path, have, x)
    return items


def _same(have: Any, new: Any) -> bool:
    """Two elements say the same, a description aside (a person words it once), and so does a
    source that names no actor (the placeholder `unassigned`) against a draft that names one."""
    if isinstance(have, dict) and isinstance(new, dict):
        skip = {"description"} | ({"actor"} if new.get("actor") == [UNASSIGNED] else set())
        return {k: v for k, v in have.items() if k not in skip} == {k: v for k, v in new.items() if k not in skip}
    return have == new


def _show(v: Any) -> str:
    import json
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


def apply(base: dict[str, Any], items: list[Item]) -> dict[str, Any]:
    """The items written into a copy of `base`: each element proposed, citing its place; a change
    inside an element proposes the element again, as `propose_element` does."""
    doc = copy.deepcopy(base)
    for it in items:
        segs = element_path(it.path)
        value = copy.deepcopy(it.value)
        src = {"kind": "system", "ref": it.ref}
        if is_element(segs) and isinstance(value, dict):
            value = {**value, "source": src, "status": "proposed"}
        _set(doc, segs, value)
        for k in range(len(segs) - 1, 1, -1):
            if is_element(segs[:k]) and isinstance(el := _get(doc, segs[:k]), dict):
                el["status"], el["source"] = "proposed", src
                break
    return doc
