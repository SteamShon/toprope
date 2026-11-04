"""Spike: compile a declared representation (+ host overlay) to A2UI v0.9 messages, deterministically."""
from __future__ import annotations

import copy
import json
import sys
from typing import Any

import yaml

from .kernel import Actor, Domain, _eval

CATALOG_ID = "toprope://catalog/spike-v1"


def merge_overlay(base: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    """ADR-0008 merge: maps by key; keyed lists (sections by title) merged by key."""
    out = copy.deepcopy(base)
    if not overlay:
        return out
    for obj, views in overlay.get("views", {}).items():
        for vname, vspec in views.items():
            tgt = out["views"].setdefault(obj, {}).setdefault(vname, {})
            for key, val in vspec.items():
                if key == "sections":
                    by_title = {s["title"]: i for i, s in enumerate(tgt.get("sections", []))}
                    for sec in val:
                        if sec["title"] in by_title:
                            tgt["sections"][by_title[sec["title"]]] = sec
                        else:
                            tgt.setdefault("sections", []).append(sec)
                else:
                    tgt[key] = val
    out["aliases"] = {**out.get("aliases", {}), **overlay.get("aliases", {})}
    out["host_components"] = {**out.get("components", {}), **overlay.get("components", {})}
    return out


def allowed_actions(domain: Domain, obj_id: str, actor: Actor, candidates: list[str]) -> list[str]:
    """Same rules as Execution (semantics §2 steps 4-6), evaluated without side effects."""
    target = domain.project(obj_id)
    out = []
    for action in candidates:
        spec = domain.decl["actions"][action]
        if actor.role not in spec.get("actor", []):
            continue
        tr = domain.decl["transitions"][spec["target"]]
        cell = tr["matrix"].get(target[tr["field"]], {}).get(action, "undecided")
        if not isinstance(cell, str) or cell in ("n/a", "undecided"):
            continue
        if all(_eval(p["check"], target, actor, {}) for p in spec.get("preconditions", [])):
            out.append(action)
    return out


def compile_detail(domain: Domain, rep: dict[str, Any], obj_type: str, obj_id: str, actor: Actor) -> list[dict]:
    view = rep["views"][obj_type]["detail"]
    aliases = rep.get("aliases", {})
    label = lambda term: aliases.get(term, term.replace("_", " "))  # noqa: E731
    comps: list[dict[str, Any]] = []
    section_ids = []
    for i, sec in enumerate(view.get("sections", [])):
        sid = f"sec{i}"
        section_ids.append(sid)
        if sec.get("component"):  # host-injected component
            comps.append({"id": sid, "component": sec["component"],
                          **{f: {"path": f"/obj/{f}"} for f in sec.get("fields", [])}})
            continue
        rows = []
        for f in sec.get("fields", []):
            rows.append(f"{sid}_{f}")
            comps.append({"id": f"{sid}_{f}", "component": "Text", "text": {"path": f"/display/{f}"}})
        comps.append({"id": f"{sid}_title", "component": "Text", "text": sec["title"], "variant": "h4"})
        comps.append({"id": f"{sid}_col", "component": "Column", "children": [f"{sid}_title", *rows]})
        comps.append({"id": sid, "component": "Card", "child": f"{sid}_col"})
    btn_ids = []
    for action in allowed_actions(domain, obj_id, actor, view.get("actions", [])):
        comps.append({"id": f"btn_{action}_label", "component": "Text", "text": label(action)})
        comps.append({"id": f"btn_{action}", "component": "Button", "child": f"btn_{action}_label",
                      "action": {"event": {"name": action, "context": {"target_id": obj_id}}}})
        btn_ids.append(f"btn_{action}")
    comps.append({"id": "actions", "component": "Row", "children": btn_ids})
    comps.append({"id": "heading", "component": "Text", "text": f"{obj_type} {obj_id}", "variant": "h2"})
    comps.append({"id": "root", "component": "Column", "children": ["heading", *section_ids, "actions"]})
    state = domain.project(obj_id)
    surface = f"{obj_type}.detail:{obj_id}"
    return [
        {"version": "v0.9", "createSurface": {"surfaceId": surface, "catalogId": CATALOG_ID}},
        {"version": "v0.9", "updateComponents": {"surfaceId": surface, "components": comps}},
        {"version": "v0.9", "updateDataModel": {"surfaceId": surface, "path": "/", "value": {
            "obj": state,
            "display": {k: f"{label(k)}: {v if v is not None else '-'}" for k, v in state.items()}}}},
    ]


if __name__ == "__main__":
    dom = Domain("toy.domain.yaml")
    with open("toy.representation.yaml") as f:
        base = yaml.safe_load(f)
    overlay = None
    if "--overlay" in sys.argv:
        with open("acme.overlay.yaml") as f:
            overlay = yaml.safe_load(f)
    role = sys.argv[sys.argv.index("--role") + 1] if "--role" in sys.argv else "approver"
    print(json.dumps(compile_detail(dom, merge_overlay(base, overlay), "Experiment", "E1", Actor("u", role)), indent=1))
