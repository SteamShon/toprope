"""Spike kernel: a tiny subset of docs/semantics.md, enough to test the server shape.

Not production code. `check` expressions are evaluated with Python eval on a restricted
namespace here; the real kernel will implement the declared expression language.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class Actor:
    id: str
    role: str
    kind: str = "person"  # person | agent | system


@dataclass
class Outcome:
    status: str  # ok | denied | rejected
    reason_code: str | None = None
    reason: str | None = None
    state: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class EventStore:
    streams: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    attempts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _seq: itertools.count = field(default_factory=itertools.count)

    def version(self, agg: str) -> int:
        return len(self.streams.get(agg, []))

    def append(self, agg: str, expected: int, event: dict[str, Any]) -> None:
        if self.version(agg) != expected:
            raise RuntimeError("version conflict")
        event = {**event, "seq": next(self._seq), "version": expected + 1}
        self.streams.setdefault(agg, []).append(event)

    def record_attempt(self, agg: str, event: dict[str, Any]) -> None:
        self.attempts.setdefault(agg, []).append({**event, "seq": next(self._seq)})


def _eval(expr: str, target: dict[str, Any], actor: Actor, params: dict[str, Any]) -> Any:
    return eval(expr, {"__builtins__": {}}, {"target": target, "actor": actor, "params": params})  # noqa: S307


class Domain:
    def __init__(self, path: str):
        with open(path) as f:
            self.decl = yaml.safe_load(f)
        self.store = EventStore()
        for fx in self.decl.get("world", {}).get("fixtures", []):
            (obj_type, data), = fx.items()
            self.store.append(data["id"], 0, {"type": f"{obj_type}Created", "aggregate": obj_type, "payload": dict(data)})

    # ---- projection (pure fold) -------------------------------------------------
    def project(self, agg: str) -> dict[str, Any] | None:
        state: dict[str, Any] | None = None
        for ev in self.store.streams.get(agg, []):
            if ev["type"].endswith("Created"):
                state = dict(ev["payload"])
            else:
                state = {**(state or {}), **ev["payload"]["changes"]}
        return state

    # ---- semantics.md §2, steps 3-11 (identity/idempotency/approvals/reservations omitted) --
    def execute(self, action: str, target_id: str, actor: Actor, params: dict[str, Any] | None = None) -> Outcome:
        params = params or {}
        spec = self.decl["actions"][action]
        v = self.store.version(target_id)
        target = self.project(target_id)
        if target is None:
            return Outcome("rejected", "not-found", f"No object {target_id}.")

        def deny(code: str, reason: str) -> Outcome:
            self.store.record_attempt(target_id, {"type": "DeniedAttempt", "action": action,
                                                  "actor": actor.__dict__, "code": code, "reason": reason})
            return Outcome("denied", code, reason, target)

        # 4. actor rule
        if actor.role not in spec.get("actor", []):
            return deny("actor", f"Role '{actor.role}' cannot {action}.")
        # 5. matrix cell
        tr = self.decl["transitions"][spec["target"]]
        cell = tr["matrix"].get(target[tr["field"]], {}).get(action, "undecided")
        if cell == "n/a":
            return deny("not-applicable", f"Not applicable when {target[tr['field']]}.")
        if cell == "undecided":
            return deny("undecided", "Undecided.")
        if isinstance(cell, dict) and "deny" in cell:
            return deny("matrix", cell["deny"])
        # 6. non-state preconditions
        for pre in spec.get("preconditions", []):
            if not _eval(pre["check"], target, actor, params):
                return deny(pre["id"], pre["reason"])
        # 9. effects on a copy
        changes: dict[str, Any] = {tr["field"]: cell}
        for eff in spec.get("effects", []):
            for k, expr in eff.get("set", {}).items():
                changes[k] = actor.id if expr == "actor.id" else expr
        new_state = {**copy.deepcopy(target), **changes}
        # 10. invariant guard
        for inv in self.decl.get("invariants", []):
            if not _eval(inv["check"], new_state, actor, params):
                self.store.record_attempt(target_id, {"type": "InvariantGuardTriggered", "invariant": inv["id"]})
                return Outcome("rejected", "invariant-guard", inv["reason"], target)
        # 11. append
        ev_type = spec.get("event") or "".join(p.capitalize() for p in action.split("_")) + "Applied"
        self.store.append(target_id, v, {"type": ev_type, "aggregate": spec["target"], "actor": actor.__dict__,
                                         "payload": {"changes": changes, "params": params}})
        if spec.get("records_decision"):
            self.store.record_attempt(target_id, {"type": "DecisionRecorded", "action": action,
                                                  "actor": actor.__dict__, "params": params})
        return Outcome("ok", state=self.project(target_id))

    # ---- world map (ADR-0020), behavior layer only ---------------------------------
    def world_map(self, role: str | None = None) -> dict[str, Any]:
        edges = []
        for obj, tr in self.decl["transitions"].items():
            for state, cells in tr["matrix"].items():
                for action, cell in cells.items():
                    spec = self.decl["actions"][action]
                    outcome = cell if isinstance(cell, str) else "deny"
                    edges.append({
                        "object": obj, "from": state, "action": action, "outcome": outcome,
                        "to": cell if outcome not in ("deny", "n/a", "undecided") else None,
                        "reason": cell.get("deny") if isinstance(cell, dict) else None,
                        "unlock": {"roles": spec.get("actor", []),
                                   "preconditions": [p["reason"] for p in spec.get("preconditions", [])]},
                        "unlocked_for_role": (role in spec.get("actor", [])) if role else None,
                    })
        return {"domain": self.decl["domain"], "version": self.decl["version"], "edges": edges}
