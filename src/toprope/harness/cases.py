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
from ..semantics import refusals
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


def cell_expectation(d: Domain, obj: str, state: str, action: str, role: str, c: Any) -> dict[str, Any]:
    """What a cell gives a person with one role: the interpreter's reason, with its fix, for a
    cell that refuses."""
    if c == "n/a":
        return {"status": "denied", "code": "not-applicable",
                "reason": refusals.not_applicable(d, obj, state, action, [(role,)])}
    if c == "undecided":
        return {"status": "denied", "code": "undecided", "reason": refusals.undecided(obj, state, action)}
    if isinstance(c, Deny):
        return {"status": "denied", "code": "matrix",
                "reason": refusals.matrix_denied(d, obj, state, action, c.deny, [(role,)])}
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

    def rule_refusing(self, name: str, a: Action, role: str, inst: Instance | None) -> str | None:
        """The outcome rule (ADR-0048) that refuses this actor here, if any: checked after the
        cell and before the preconditions, as the interpreter does."""
        from ..decl.rules import covering, meets
        actor = self.w.actors[role]
        tr = self.d.transitions.get(a.object_type)
        frm = inst.data.get(tr.field) if (tr is not None and inst is not None and a.target) else None
        return next((rid for rid, r in covering(self.d, name, frm) if not meets(r, actor.kind, actor.roles, actor.roles)),
                    None)

    def actor_ok(self, name: str, a: Action, role: str, inst: Instance | None, rules: bool = True) -> bool:
        actor = self.w.actors[role]
        if a.requires == "human" and actor.kind != "person":
            return False
        if rules and self.rule_refusing(name, a, role, inst):
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

    def first_failing(self, a: Action, inst_data: dict[str, Any], role: str,
                      params: dict[str, Any] | None = None) -> str | None:
        """The id of the first precondition that does not hold, or None."""
        from ..expr import EvalError, evaluate
        from ..semantics.interpreter import ObjectView
        view = ObjectView(self.d, a.object_type, inst_data, self.lookup)
        params = self.params(a) if params is None else params
        for pre in a.preconditions:
            try:
                ok = evaluate(parse(pre.check), self.interp._env(view, self.w.actors[role], params)) is True
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
                out += self._param_cases(name, a)
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
                if not self.actor_ok(name, a, role, inst, rules=False):
                    expect = {"status": "denied", "code": "actor"}
                else:
                    expect = cell_expectation(self.d, obj, state, name, role, raw_cell(self.d, obj, state, name, role))
                    if expect["status"] == "ok" and (rule := self.rule_refusing(name, a, role, inst)):
                        expect = {"status": "denied", "code": rule}
                    elif expect["status"] == "ok" and (pre := self.first_failing(a, inst.data, role)):
                        expect = {"status": "denied", "code": pre}
                out.append(Case(cid, "cell", obj, state, name, role, inst, self.params(a), expect))
        return out

    def _param_cases(self, name: str, a: Action) -> list[Case]:
        """Each allowed cell, on every instance in its state, with one param set to another value of
        a finite type (boolean, enum, integer). A cell test takes the default params only, so a
        move that breaks an invariant only with another value went unseen: TLC found two, a
        failing kernel reply on an approved commit or a deployed request (ADR-0043). Expected
        outcomes come from the declaration, as for cells; an invariant guard is a finding."""
        out = []
        obj = a.object_type
        base = self.params(a)
        finite = [(p, s) for p, s in a.params.items() if not s.optional and s.ref is None
                  and (s.enum or s.type in ("boolean", "integer"))]
        if not finite:
            return out
        for state in self.d.transitions[obj].matrix:
            for role in self.w.actors:
                cell = cell_expectation(self.d, obj, state, name, role, raw_cell(self.d, obj, state, name, role))
                if cell["status"] != "ok":
                    continue
                for k, inst in enumerate(self.w.in_state(obj, state)):
                    if not self.actor_ok(name, a, role, inst):
                        continue
                    for p, spec in finite:
                        for v in self._candidates(spec):
                            v = [v] if spec.many else v
                            if v == base[p]:
                                continue
                            params = {**base, p: v}
                            pre = self.first_failing(a, inst.data, role, params)
                            expect = {"status": "denied", "code": pre} if pre else cell
                            out.append(Case(f"param:{obj}.{state}.{name}.{role}@{inst.data['id']}:{p}={v}", "param",
                                            obj, state, name, role, inst, params, expect))
        return out

    def _precondition_cases(self, name: str, a: Action) -> list[Case]:
        """Boundary cases: an instance on which exactly this precondition is the first to fail.
        When no world instance is one, a boundary is made from one: a single property or param
        the precondition reads is set to another value of its type (or an actor's id), keeping
        every invariant. Without it, a skipped precondition would go unseen (harness mutants)."""
        out = []
        obj = a.object_type
        for pre in a.preconditions:
            found = self._boundary(name, a, pre)
            cid = f"precondition:{name}.{pre.id}"
            if found is None:
                out.append(Case(cid, "precondition", obj, None, name, "", None, gap="no-boundary-instance"))
            else:
                state, role, inst, params = found
                out.append(Case(cid, "precondition", obj, state, name, role, inst, params,
                                {"status": "denied", "code": pre.id}))
        return out

    def _boundary(self, name: str, a: Action, pre: Any):
        obj = a.object_type
        for state in self.d.transitions[obj].matrix:
            for role in self.w.actors:
                if cell_expectation(self.d, obj, state, name, role, raw_cell(self.d, obj, state, name, role))["status"] != "ok":
                    continue
                for inst in self.w.in_state(obj, state):
                    for data, params in self._variants(a, pre, inst.data):
                        cand = inst if data is inst.data else Instance(inst.obj, inst.id, data, inst.path)
                        if (self.actor_ok(name, a, role, cand) and self.first_failing(a, data, role, params) == pre.id
                                and not self.interp.violated_invariants(obj, data, self.lookup)):
                            return state, role, cand, params
        return None

    def _variants(self, a: Action, pre: Any, data: dict[str, Any]):
        """The instance as it is, then each one-field change to what the precondition reads."""
        params = self.params(a)
        yield data, params
        props = self.d.objects[a.object_type].properties
        tr = self.d.transitions.get(a.object_type)
        for p in paths_read(parse(pre.check)):
            if not p.attrs:
                continue
            attr = p.attrs[0]
            if p.root == "target" and attr in props and not (tr and attr == tr.field):
                for v in self._candidates(props[attr]):
                    if v != data.get(attr):
                        yield {**data, attr: v}, params
            elif p.root == "params" and attr in a.params and not a.params[attr].ref:
                for v in self._candidates(a.params[attr]):
                    if v != params.get(attr):
                        yield data, {**params, attr: [v] if a.params[attr].many else v}

    def _candidates(self, spec: Any) -> list[Any]:
        from .mechanical import DATES, INTS, NUMS, STRS
        if spec.enum:
            return list(spec.enum)
        return {"integer": list(INTS) + [1000, 10000], "number": list(NUMS) + [1000.0, 10000.0],
                "boolean": [True, False], "datetime": list(DATES),
                "string": list(STRS) + sorted({x.id for x in self.w.actors.values()})}[spec.type or "string"]

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
