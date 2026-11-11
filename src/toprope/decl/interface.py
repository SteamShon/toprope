"""The domain interface: the published, hashed list of elements other layers compile against
(ADR-0008), versioned from the diff (removal/rename = major, addition = minor, text = patch)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .models import Domain

# Keys that hold wording or provenance, not shape. A change confined to these is a patch.
# `deny` holds the denial reason; `source`/`status` are provenance (confirming an element is
# not an interface change). Note: `ref` is NOT here: Param.ref names an object type.
TEXT_KEYS = {"description", "reason", "deny", "source", "status"}


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


# Keys whose values are user data (effect assignments, kernel inputs, fixture and scenario
# data, expectations): a key named `status` or `source` there is data, never provenance or text.
DATA_KEYS = {"set", "with", "given", "params", "expect", "data", "state", "changes", "inputs"}


def _strip_text(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (v if k in DATA_KEYS else _strip_text(v)) for k, v in obj.items() if k not in TEXT_KEYS}
    if isinstance(obj, list):
        return [_strip_text(v) for v in obj]
    return obj


@dataclass(frozen=True)
class Element:
    key: str            # e.g. "object:Experiment", "property:Experiment.status", "action:approve"
    content: dict
    hash: str           # full content
    shape_hash: str     # content without text (description/reason): a change here is not text-only


def _el(key: str, content: Any) -> Element:
    data = content if isinstance(content, dict) else {"value": content}
    return Element(key, data, hashlib.sha256(_canon(data).encode()).hexdigest()[:16],
                   hashlib.sha256(_canon(_strip_text(data)).encode()).hexdigest()[:16])


def interface(d: Domain) -> dict[str, Element]:
    dump = lambda m: m.model_dump(mode="json", by_alias=True, exclude_none=True)  # noqa: E731
    els: list[Element] = []
    for name, o in d.objects.items():
        els.append(_el(f"object:{name}", {"description": o.description}))
        for p, spec in o.properties.items():
            els.append(_el(f"property:{name}.{p}", dump(spec)))
    for name, link in d.links.items():
        els.append(_el(f"link:{name}", dump(link)))
    for name, a in d.actions.items():
        # Params and preconditions are their own elements, so adding one is "added" (minor),
        # not a shape change of the action (ADR-0008). Effects stay in the action: changing
        # what an action does is a shape change (major), conservatively.
        els.append(_el(f"action:{name}", {k: v for k, v in dump(a).items() if k not in ("params", "preconditions")}))
        for p, spec in a.params.items():
            els.append(_el(f"param:{name}.{p}", dump(spec)))
        for pre in a.preconditions:
            els.append(_el(f"precondition:{name}.{pre.id}", dump(pre)))
    for obj, tr in d.transitions.items():
        for state, cells in tr.matrix.items():
            for action, cell in cells.items():
                els.append(_el(f"cell:{obj}.{state}.{action}",
                               cell.model_dump(mode="json", exclude_none=True) if hasattr(cell, "model_dump") else cell))
    for inv in d.invariants:
        els.append(_el(f"invariant:{inv.id}", dump(inv)))
    for term, text in d.glossary.items():
        els.append(_el(f"term:{term}", {"text": text}))
    return {e.key: e for e in els}


@dataclass(frozen=True)
class InterfaceDiff:
    added: list[str]
    removed: list[str]
    changed: list[str]       # shape changed
    text_only: list[str]     # only description/reason/glossary text changed

    @property
    def bump(self) -> str:
        if self.removed or self.changed:
            return "major"
        if self.added:
            return "minor"
        if self.text_only:
            return "patch"
        return "none"


def diff_interface(old: dict[str, Element], new: dict[str, Element]) -> InterfaceDiff:
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed, text_only = [], []
    for k in sorted(set(old) & set(new)):
        if old[k].hash == new[k].hash:
            continue
        if k.startswith("term:") or old[k].shape_hash == new[k].shape_hash:
            text_only.append(k)   # glossary wording, descriptions, reasons (ADR-0008: patch)
        else:
            changed.append(k)
    return InterfaceDiff(added, removed, changed, text_only)


# -- review (ADR-0029) ---------------------------------------------------------------------------
PROVENANCE_KEYS = {"source", "status"}


def _strip_provenance(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (v if k in DATA_KEYS else _strip_provenance(v)) for k, v in obj.items()
                if k not in PROVENANCE_KEYS}
    if isinstance(obj, list):
        return [_strip_provenance(v) for v in obj]
    return obj


def review_hash(content: Any) -> str:
    """The hash that decides whether a confirmation carries over: everything an element says,
    references and wording included, except its provenance (`source`, `status`). Confirming an
    element therefore does not change it."""
    data = content if isinstance(content, dict) else {"value": content}
    return hashlib.sha256(_canon(_strip_provenance(data)).encode()).hexdigest()[:16]


def review_contents(d: Domain) -> dict[str, Any]:
    """Every reviewable element of a declaration, key → what it says. The interface's elements,
    plus what an owner confirms but other layers do not compile against: roles, each object's
    stage field and initial stage, handoffs, outcome rules, scenarios, fixtures and purpose."""
    dump = lambda m: m.model_dump(mode="json", by_alias=True, exclude_none=True)  # noqa: E731
    out: dict[str, Any] = {k: e.content for k, e in interface(d).items()}
    for r in d.roles:
        out[f"role:{r}"] = {"role": r}
    for obj, tr in d.transitions.items():
        out[f"stages:{obj}"] = {"field": tr.field, "initial": tr.initial}
    for name, h in d.handoffs.items():
        out[f"handoff:{name}"] = dump(h)
    for rid, r in d.rules.items():
        out[f"rule:{rid}"] = dump(r)
    for sc in d.scenarios:
        out[f"scenario:{sc.id}"] = dump(sc)
    for fx in d.world.fixtures:
        ((obj, data),) = fx.items()
        out[f"fixture:{obj}.{data.get('id')}"] = {"data": data}   # data: its `status` is a stage, kept
    if d.purpose is not None:
        out["purpose"] = dump(d.purpose)
    return out


def review_elements(d: Domain) -> dict[str, str]:
    """Every reviewable element of a declaration (see `review_contents`), key → review hash."""
    return {k: review_hash(c) for k, c in review_contents(d).items()}


@dataclass(frozen=True)
class ReviewDiff:
    changed: list[str]     # directly changed: the owner re-confirms these
    added: list[str]       # new: the owner confirms these
    removed: list[str]

    @property
    def to_review(self) -> list[str]:
        return sorted(self.changed + self.added)


def review_diff(old: dict[str, str], new: dict[str, str]) -> ReviewDiff:
    return ReviewDiff(changed=sorted(k for k in set(old) & set(new) if old[k] != new[k]),
                      added=sorted(set(new) - set(old)), removed=sorted(set(old) - set(new)))
