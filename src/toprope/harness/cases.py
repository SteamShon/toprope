"""Test cases generated from the declaration (ADR-0010 §4).

Expected outcomes come from the declared matrix, actor rules and preconditions, read
directly here, not from the interpreter's decision. So the cell tests also check the oracle
against the declaration it interprets. Only actor-rule `where` conditions and expressions
are evaluated through the interpreter's expression evaluator.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..decl.models import Action, ActorRule, ByRole, Deny, Domain, Target
from ..expr import parse, paths_read
from ..semantics.interpreter import Interpreter
from ..semantics.types import Command
from .world import Instance, SmallWorld, default_params

MATRIX_CODES = {"matrix", "not-applicable", "undecided"}


@dataclass
class Case:
    id: str
    kind: str                         # cell | precondition | create
    obj: str
    state: str | None
    action: str
    role: str
    instance: Instance | None         # None: not runnable (a coverage gap)
    params: dict[str, Any] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    gap: str | None = None


def raw_cell(d: Domain, obj: str, state: str, action: str, role: str) -> Any:
    """The declared cell for one role: a target state, Deny, "n/a" or "undecided"."""
    c = d.transitions[obj].matrix.get(state, {}).get(action, "undecided")
    if isinstance(c, ByRole):
        c = c.by_role.get(role, "n/a")
    return c.to if isinstance(c, Target) else c


def undecided_cells(d: Domain, world: Any) -> list[str]:
    """Every cell (object.state.action) that is undecided for some role, a missing cell or row
    included: the interpreter treats those as undecided (docs/semantics.md step 5)."""
    return sorted({f"{obj}.{st}.{a}" for obj, tr in d.transitions.items() for st in tr.matrix
                   for a, act in d.actions.items() if act.target == obj and act.creates is None
                   for role in world.actors if raw_cell(d, obj, st, a, role) == "undecided"})


def cell_expectation(c: Any, state: str) -> dict[str, Any]:
    if c == "n/a":
        return {"status": "denied", "code": "not-applicable", "reason": f"Not applicable when {state}."}
    if c == "undecided":
        return {"status": "denied", "code": "undecided", "reason": "Undecided."}
    if isinstance(c, Deny):
        return {"status": "denied", "code": "matrix", "reason": c.deny}
    return {"status": "ok", "to": c}


class Planner:
    def __init__(self, world: SmallWorld, clock: Callable[[], datetime]):
        self.w, self.d = world, world.domain
        self.interp = Interpreter(self.d, clock)
        self._fixtures = {data["id"]: (obj, data) for obj, data in world.fixtures}

    def lookup(self, oid: str):
        return self._fixtures.get(oid)

    def params(self, a: Action) -> dict[str, Any]:
        return default_params(self.d, a, self.w.fixtures, self.interp.clock)

    def actor_ok(self, name: str, a: Action, role: str, inst: Instance | None) -> bool:
        actor = self.w.actors[role]
        if a.requires == "human" and actor.kind != "person":
            return False
        plain = [r for r in a.actor if isinstance(r, str)]
        if role in plain:
            return True
        rules = [r for r in a.actor if isinstance(r, ActorRule) and r.role == role]
        if not rules:
            return False
        # A relation (`where`) depends on the object: evaluated with the expression evaluator.
        from ..semantics.interpreter import ObjectView
        view = ObjectView(self.d, a.object_type, (inst.data if inst else {}), self.lookup)
        return self.interp.actor_allowed(a, Command(actor, name, inst.data["id"] if inst else "new", self.params(a)), view)[0]

    def first_failing(self, a: Action, inst_data: dict[str, Any], role: str) -> str | None:
        """The id of the first precondition that does not hold, or None."""
        from ..expr import EvalError, evaluate
        from ..semantics.interpreter import ObjectView
        view = ObjectView(self.d, a.object_type, inst_data, self.lookup)
        for pre in a.preconditions:
            try:
                ok = evaluate(parse(pre.check), self.interp._env(view, self.w.actors[role], self.params(a))) is True
            except EvalError:
                ok = False
            if not ok:
                return pre.id
        return None

    # -- case generation -----------------------------------------------------------------
    def cases(self) -> list[Case]:
        out: list[Case] = []
        for name, a in self.d.actions.items():
            if a.creates is not None:
                out += self._create_cases(name, a)
            elif a.target in self.d.transitions:
                out += self._cell_cases(name, a)
                out += self._precondition_cases(name, a)
        return out

    def _cell_cases(self, name: str, a: Action) -> list[Case]:
        out = []
        obj = a.object_type
        for state in self.d.transitions[obj].matrix:
            insts = self.w.in_state(obj, state)
            for role in self.w.actors:
                cid = f"cell:{obj}.{state}.{name}.{role}"
                if not insts:
                    out.append(Case(cid, "cell", obj, state, name, role, None, gap="no-instance-in-state"))
                    continue
                # Prefer an instance where every precondition holds, so the cell itself is tested.
                inst = next((i for i in insts if self.first_failing(a, i.data, role) is None), insts[0])
                if not self.actor_ok(name, a, role, inst):
                    expect = {"status": "denied", "code": "actor"}
                else:
                    expect = cell_expectation(raw_cell(self.d, obj, state, name, role), state)
                    if expect["status"] == "ok" and (pre := self.first_failing(a, inst.data, role)):
                        expect = {"status": "denied", "code": pre}
                out.append(Case(cid, "cell", obj, state, name, role, inst, self.params(a), expect))
        return out

    def _precondition_cases(self, name: str, a: Action) -> list[Case]:
        """Boundary cases: an instance on which exactly this precondition is the first to fail."""
        out = []
        obj = a.object_type
        for i, pre in enumerate(a.preconditions):
            if any(p.root == "params" for p in paths_read(parse(pre.check))):
                continue
            found = None
            for state in self.d.transitions[obj].matrix:
                for role in self.w.actors:
                    if cell_expectation(raw_cell(self.d, obj, state, name, role), state)["status"] != "ok":
                        continue
                    for inst in self.w.in_state(obj, state):
                        if self.actor_ok(name, a, role, inst) and self.first_failing(a, inst.data, role) == pre.id:
                            found = (state, role, inst)
                            break
                    if found:
                        break
                if found:
                    break
            cid = f"precondition:{name}.{pre.id}"
            if found is None:
                out.append(Case(cid, "precondition", obj, None, name, "", None, gap="no-boundary-instance"))
            else:
                state, role, inst = found
                out.append(Case(cid, "precondition", obj, state, name, role, inst, self.params(a),
                                {"status": "denied", "code": pre.id}))
        return out

    def _create_cases(self, name: str, a: Action) -> list[Case]:
        out = []
        obj = a.creates
        tr = self.d.transitions.get(obj)
        for role in self.w.actors:
            cid = f"create:{name}.{role}"
            if not self.actor_ok(name, a, role, None):
                expect: dict[str, Any] = {"status": "denied", "code": "actor"}
            elif pre := self.first_failing(a, {}, role):
                expect = {"status": "denied", "code": pre}
            else:
                expect = {"status": "ok", "to": tr.initial if tr else None}
            out.append(Case(cid, "create", obj, None, name, role, None, self.params(a), expect))
        return out


def matches(expect: dict[str, Any], obs: dict[str, Any], d: Domain, obj: str) -> bool:
    if obs.get("status") != expect["status"]:
        return False
    if expect["status"] == "ok":
        tr = d.transitions.get(obj)
        return tr is None or expect.get("to") is None or (obs.get("state") or {}).get(tr.field) == expect["to"]
    if obs.get("code") != expect["code"]:
        return False
    return "reason" not in expect or obs.get("reason") == expect["reason"]
