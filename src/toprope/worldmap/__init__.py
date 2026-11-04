"""The world map (ADR-0020): a deterministic graph of the whole domain, compiled from the
declaration and, optionally, the build's harness results. It is a view; it never adds rules.

- structure layer: object types and declared links
- behavior layer: states, roles and actors, and one edge per (state, action) cell with its
  outcome, unlock requirements, the invariants it touches, and whether it records a decision
- overlays: element status (confirmed / proposed / unknown), fog for `undecided` cells, and
  harness status per edge (verified / failed / uncovered)

Usage heat from the event store is not emitted yet (ADR-0020 marks it optional).
"""

from __future__ import annotations

from collections import deque
from typing import Any

from ..decl.models import Action, ActorRule, ByRole, Deny, Domain, Target
from ..expr import parse, paths_read

FORMAT = "toprope.world-map/1"
NEW = "(new)"   # the pseudo-state a create action starts from


def _status(el: Any) -> str | None:
    return getattr(el, "status", None)


def _who(a: Action) -> list[dict[str, Any]]:
    return [{"role": r.role, "where": r.where} if isinstance(r, ActorRule) else {"role": r} for r in a.actor]


def _writes(d: Domain, a: Action) -> set[str]:
    out = set()
    tr = d.transitions.get(a.object_type)
    if tr is not None:
        out.add(tr.field)
    for e in a.effects:
        for key in e.set or {}:
            out.add(key.split(".", 1)[1] if key.startswith(("target.", "new.")) else key)
    if a.creates is not None:
        out |= set(d.objects.get(a.creates).properties if a.creates in d.objects else ())
    return out


def _touches(d: Domain, a: Action) -> list[str]:
    """Invariants on the action's object that read a field the action writes."""
    written = _writes(d, a)
    out = []
    for inv in d.invariants:
        if inv.on != a.object_type:
            continue
        reads = {p.attrs[0] for p in paths_read(parse(inv.check)) if p.root == "target" and p.attrs}
        if reads & written or inv.scope == "cross":
            out.append(inv.id)
    return out


def _unlock(a: Action) -> dict[str, Any]:
    return {"actors": _who(a),
            "preconditions": [{"id": p.id, "reason": p.reason, "check": p.check, "status": _status(p)}
                              for p in a.preconditions],
            "requires_human": a.requires == "human",
            "approvals": a.approvals,
            "reservations": []}


def _outcome(c: Any) -> dict[str, Any]:
    if isinstance(c, Target):
        return {"kind": "to", "to": c.to, "status": _status(c)}
    if isinstance(c, Deny):
        return {"kind": "deny", "reason": c.deny, "status": _status(c)}
    if isinstance(c, ByRole):
        return {"kind": "by_role", "status": _status(c),
                "by_role": {r: _outcome(o) for r, o in sorted(c.by_role.items())}}
    if c in ("n/a", "undecided"):
        return {"kind": c}
    return {"kind": "to", "to": c}


def _targets(o: dict[str, Any]) -> list[tuple[str | None, str]]:
    """(role or None for every role, target state) pairs an outcome allows."""
    if o["kind"] == "to":
        return [(None, o["to"])]
    if o["kind"] == "by_role":
        return [(r, x["to"]) for r, x in o["by_role"].items() if x["kind"] == "to"]
    return []


def build_world_map(d: Domain, harness: dict[str, Any] | None = None) -> dict[str, Any]:
    """`harness` is a harness report as JSON (`Report.to_json()`); without it every edge's
    harness status is `unknown`."""
    verdicts = ((harness or {}).get("coverage") or {}).get("edges", {})

    structure = {
        "nodes": [{"id": n, "description": o.description, "properties": sorted(o.properties),
                   "stateful": n in d.transitions, "status": _status(o)} for n, o in sorted(d.objects.items())],
        "edges": [{"id": n, "from": l.from_, "to": l.to, "cardinality": l.cardinality, "required": l.required,
                   "status": _status(l)} for n, l in sorted(d.links.items())],
    }

    states, edges = [], []
    for obj, tr in sorted(d.transitions.items()):
        outgoing: dict[str, int] = {}
        for state, cells in tr.matrix.items():
            for name, a in d.actions.items():
                if a.target != obj:
                    continue
                o = _outcome(cells.get(name, "undecided"))
                eid = f"{obj}.{state}.{name}"
                edges.append({"id": eid, "object": obj, "from": state, "action": name, "outcome": o,
                              "fog": o["kind"] == "undecided", "unlock": _unlock(a),
                              "invariants": _touches(d, a), "records_decision": a.records_decision,
                              "fired_by": [], "harness": verdicts.get(eid, "unknown")})
                outgoing[state] = outgoing.get(state, 0) + bool(_targets(o))
        for name, a in d.actions.items():
            if a.creates == obj:
                eid = f"{obj}.{NEW}.{name}"
                edges.append({"id": eid, "object": obj, "from": NEW, "action": name,
                              "outcome": {"kind": "to", "to": tr.initial}, "fog": False, "unlock": _unlock(a),
                              "invariants": _touches(d, a), "records_decision": a.records_decision,
                              "fired_by": [], "harness": verdicts.get(eid, "unknown")})
        for state in tr.matrix:
            states.append({"id": f"{obj}.{state}", "object": obj, "state": state, "initial": state == tr.initial,
                           "terminal": outgoing.get(state, 0) == 0})

    roles = [{"id": r, "people": d.world.actors.get(r, [])} for r in d.roles]
    reserved = sorted({r.role if isinstance(r, ActorRule) else r for a in d.actions.values() for r in a.actor
                       if (r.role if isinstance(r, ActorRule) else r) not in d.roles})
    unreachable = ((harness or {}).get("coverage") or {}).get("unreachable") or {}
    return {"format": FORMAT, "domain": d.domain, "version": d.version,
            "structure": structure,
            "behavior": {"states": states, "roles": roles, "system_actors": reserved, "edges": edges},
            "unreachable": unreachable}


# -- path questions --------------------------------------------------------------------------
def how_to_reach(world_map: dict[str, Any], obj: str, from_state: str | None, target_state: str,
                 roles: tuple[str, ...] | None = None) -> dict[str, Any]:
    """The shortest sequence of actions from `from_state` to `target_state`, with who may take
    each step. With `roles` (the caller's), each step says whether the caller can take it, and
    the path prefers steps the caller can take. Preconditions are listed, not evaluated."""
    edges = [e for e in world_map["behavior"]["edges"] if e["object"] == obj]
    start = from_state if from_state is not None else NEW
    if start == target_state:
        return {"reachable": True, "steps": []}
    mine = set(roles or ())

    def options(state):
        for e in edges:
            if e["from"] != state:
                continue
            for role, to in _targets(e["outcome"]):
                allowed = {a["role"] for a in e["unlock"]["actors"]}
                who = sorted(allowed if role is None else allowed & {role})
                if who:
                    yield e, to, who

    best: dict[str, list] = {}
    for prefer_mine in ((True, False) if roles is not None else (False,)):
        q, prev = deque([start]), {start: None}
        while q:
            s = q.popleft()
            for e, to, who in options(s):
                if prefer_mine and not (mine & set(who)):
                    continue
                if to not in prev:
                    prev[to] = (s, e, who)
                    q.append(to)
        if target_state in prev:
            steps, cur = [], target_state
            while prev[cur] is not None:
                s, e, who = prev[cur]
                step = {"action": e["action"], "from": s, "to": cur, "who": who,
                        "requires": [p["reason"] for p in e["unlock"]["preconditions"]],
                        "requires_human": e["unlock"]["requires_human"]}
                if roles is not None:
                    step["you_can"] = bool(mine & set(who))
                steps.append(step)
                cur = s
            best = {"reachable": True, "steps": list(reversed(steps))}
            break
    return best or {"reachable": False, "reason": f"No declared transition leads from {start} to {target_state}."}


# -- docs view -------------------------------------------------------------------------------
def to_mermaid(world_map: dict[str, Any]) -> dict[str, Any]:
    """A flowchart of the structure layer and a state diagram per stateful object."""
    lines = ["flowchart LR"]
    for n in world_map["structure"]["nodes"]:
        lines.append(f"  {n['id']}[{n['id']}]")
    for e in world_map["structure"]["edges"]:
        lines.append(f"  {e['from']} -->|{e['id']}| {e['to']}")
    diagrams = {}
    by_obj: dict[str, list] = {}
    for e in world_map["behavior"]["edges"]:
        by_obj.setdefault(e["object"], []).append(e)
    for obj, es in sorted(by_obj.items()):
        sd = ["stateDiagram-v2"]
        initial = next((s["state"] for s in world_map["behavior"]["states"] if s["object"] == obj and s["initial"]), None)
        if initial:
            sd.append(f"  [*] --> {initial}")
        for e in es:
            if e["from"] == NEW:
                continue
            for role, to in _targets(e["outcome"]):
                label = e["action"] + (f" ({role})" if role else "")
                sd.append(f"  {e['from']} --> {to}: {label}")
            if e["fog"]:
                sd.append(f"  note right of {e['from']}: {e['action']} undecided")
        diagrams[obj] = "\n".join(sd)
    return {"structure": "\n".join(lines), "states": diagrams}


__all__ = ["FORMAT", "NEW", "build_world_map", "how_to_reach", "to_mermaid"]
