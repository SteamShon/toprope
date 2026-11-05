"""Run the generated harness at every level and report (ADR-0010 §4-5, docs/semantics.md §3).

Parts: cell, precondition and create tests with invariant checks after every step; parity
across levels (outcomes, allowed actions, event streams); replay parity; race tests on one
cell; derandomized exploration that reports a minimal flow; the declaration's example
flows; and a coverage report. Findings block a build; coverage gaps are reported, not failed.
"""

from __future__ import annotations

import copy
import json
import tempfile
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..decl.models import Domain
from ..semantics.interpreter import Interpreter
from ..semantics.model import project
from ..store import EventStore
from .cases import MATRIX_CODES, Case, Planner, matches, raw_cell
from .surfaces import LEVELS, ExecutionSurface, ModelSurface, Surface
from .world import Instance, SmallWorld, grow_world

DEFAULT_LEVELS = ("model", "execution", "mcp")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
RANK = {"verified": 0, "uncovered": 1, "failed": 2}


@dataclass
class Finding:
    kind: str        # expectation | invariant | parity | replay | race | exploration | flow
    level: str
    case: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    levels: tuple[str, ...]
    findings: list[Finding]
    coverage: dict[str, Any]
    minimal_flows: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not self.findings

    def to_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "levels": list(self.levels), "findings": [asdict(f) for f in self.findings],
                "coverage": self.coverage, "minimal_flows": self.minimal_flows}

    def summary(self) -> str:
        c = self.coverage["cells"]
        lines = [f"harness: {'PASS' if self.ok else 'FAIL'} ({', '.join(self.levels)})",
                 f"cells: {c['decided']} decided, covered " +
                 ", ".join(f"{lv} {n}" for lv, n in c["covered"].items()) +
                 f"; {len(c['undecided'])} undecided; {len(c['gaps'])} without an instance",
                 f"invariants exercised: {self.coverage['invariants']['exercised']}/{self.coverage['invariants']['total']}",
                 f"flows: " + ", ".join(f"{lv} {n}" for lv, n in self.coverage["flows"]["passed"].items()) +
                 f" of {self.coverage['flows']['total']}",
                 f"race tests: {self.coverage['races']}",
                 f"unreachable states: {self.coverage['unreachable'] or 'none'}"]
        for f in self.findings[:20]:
            lines.append(f"  [{f.kind}] {f.level} {f.case}: {json.dumps(f.detail, default=str)[:300]}")
        if len(self.findings) > 20:
            lines.append(f"  ... {len(self.findings) - 20} more")
        for mf in self.minimal_flows:
            lines.append(f"  minimal flow breaking {mf['invariant']}: " +
                         " → ".join(f"{s['actor']} {s['action']} {s['target']}" for s in mf["steps"]))
        return "\n".join(lines)


class Harness:
    def __init__(self, d: Domain, *, levels: tuple[str, ...] = DEFAULT_LEVELS,
                 clock: Callable[[], datetime] | None = None,
                 store_factory: Callable[[], EventStore] | None = None,
                 build_server: Callable[..., Any] | None = None):
        self.d = d
        self.levels = tuple(levels)
        self.clock = clock or (lambda: NOW)
        self.store_factory = store_factory
        self.build_server = build_server
        self.interp = Interpreter(d, self.clock)
        self.world: SmallWorld = grow_world(d, self.clock)
        self.planner = Planner(self.world, self.clock)
        self.findings: list[Finding] = []
        self._exercised: set[str] = set()

    # -- surfaces --------------------------------------------------------------------------
    def surface(self, level: str) -> Surface:
        cls = LEVELS[level]
        # The model level is the reference: always the plain in-memory store.
        store = self.store_factory() if self.store_factory and level != "model" else None
        s = cls(self.d, self.clock, store, build=self.build_server) if level == "mcp" else cls(self.d, self.clock, store)
        for obj, data in self.world.fixtures:
            s.seed(obj, copy.deepcopy(data))
        return s

    def _check_invariants(self, s: Surface, level: str, case: str, obj: str, oid: str) -> None:
        st = s.state(oid)
        if st is None:
            return
        self._exercised |= {i.id for i in self.d.invariants if i.on == obj and i.scope == "aggregate"}
        for inv in self.interp.violated_invariants(obj, st, s.lookup):
            self.findings.append(Finding("invariant", level, case, {"invariant": inv.id, "reason": inv.reason, "state": st}))

    # -- cases at one level ----------------------------------------------------------------
    def run_cases(self, level: str, cases: list[Case]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (observed outcome per case, observed side data per case: events, allowed)."""
        s = self.surface(level)
        obs: dict[str, Any] = {}
        side: dict[str, Any] = {}
        try:
            for n, c in enumerate(cases):
                if c.gap:
                    continue
                actor = self.world.actors[c.role]
                oid = f"{c.instance.data['id']}~h{n}" if c.instance else f"{c.obj}~h{n}"
                if c.instance:
                    s.seed(c.obj, {**copy.deepcopy(c.instance.data), "id": oid})
                    side[c.id + "#allowed"] = sorted(s.allowed(actor, oid))
                o = s.do(actor, c.action, oid, c.params, f"h{n}")
                obs[c.id] = o
                if not matches(c.expect, o, self.d, c.obj):
                    kind = "invariant" if o.get("code") == "invariant-guard" else "expectation"
                    self.findings.append(Finding(kind, level, c.id, {"expected": c.expect, "observed": o}))
                self._check_invariants(s, level, c.id, c.obj, oid)
                evs = s.events(oid)
                if evs is not None and o.get("status") == "ok":
                    # Replay parity: folding the stored stream rebuilds the state the command produced.
                    if project(evs) != o.get("state"):
                        self.findings.append(Finding("replay", level, c.id,
                                                     {"outcome_state": o.get("state"), "replayed": project(evs)}))
                    side[c.id + "#events"] = [(e.type, e.kind, e.version, e.actor, e.payload) for e in evs]
        finally:
            s.close()
        return obs, side

    # -- races (docs/semantics.md §3) ------------------------------------------------------
    def races(self, cases: list[Case], limit: int = 12) -> int:
        """Two actors on the same object at once (Execution on a durable store): the outcomes
        must be those of one of the two serial orders, and the invariants must hold."""
        by_state: dict[tuple[str, str | None], list[Case]] = {}
        for c in cases:
            if c.kind == "cell" and not c.gap and c.expect["status"] == "ok":
                by_state.setdefault((c.obj, c.state), []).append(c)
        pairs = [(a, b) for xs in by_state.values() for i, a in enumerate(xs) for b in xs[i:]
                 if (a.action, a.role) != (b.action, b.role) or a is b]
        tmp = tempfile.TemporaryDirectory()
        ran = 0
        try:
            for n, (a, b) in enumerate(pairs[:limit]):
                serial = [self._serial(n, a, b), tuple(reversed(self._serial(n, b, a)))]
                from ..store.sqlite import SQLiteEventStore
                store = (self.store_factory() if self.store_factory else SQLiteEventStore(str(Path(tmp.name) / f"r{n}.db")))
                s = ExecutionSurface(self.d, self.clock, store)
                for obj, data in self.world.fixtures:
                    s.seed(obj, copy.deepcopy(data))
                oid = f"{a.instance.data['id']}~r{n}"
                s.seed(a.obj, {**copy.deepcopy(a.instance.data), "id": oid})
                got: list[Any] = [None, None]
                gate = threading.Barrier(2)

                def go(i: int, c: Case) -> None:
                    gate.wait()
                    got[i] = s.do(self.world.actors[c.role], c.action, oid, c.params, f"race{i}")

                ts = [threading.Thread(target=go, args=(i, c)) for i, c in enumerate((a, b))]
                for t in ts:
                    t.start()
                for t in ts:
                    t.join(30)
                if tuple(got) not in serial:
                    self.findings.append(Finding("race", "execution", f"{a.id} || {b.id}",
                                                 {"observed": got, "allowed": serial}))
                self._check_invariants(s, "execution", f"race:{a.id}||{b.id}", a.obj, oid)
                ran += 1
        finally:
            tmp.cleanup()
        return ran

    def _serial(self, n: int, first: Case, second: Case) -> tuple[Any, Any]:
        s = ModelSurface(self.d, self.clock)
        for obj, data in self.world.fixtures:
            s.seed(obj, copy.deepcopy(data))
        oid = f"{first.instance.data['id']}~r{n}"
        s.seed(first.obj, {**copy.deepcopy(first.instance.data), "id": oid})
        o1 = s.do(self.world.actors[first.role], first.action, oid, first.params, "race-a")
        o2 = s.do(self.world.actors[second.role], second.action, oid, second.params, "race-b")
        return (o1, o2)

    # -- flows (the declaration's scenarios) -----------------------------------------------
    def flows(self, level: str) -> int:
        passed = 0
        for sc in self.d.scenarios:
            s = self.surface(level)
            try:
                if "from_world" not in sc.given:
                    for obj, data in sc.given.items():
                        s.seed(obj, data)
                for i, step in enumerate(sc.steps):
                    why = self._flow_step(s, step)
                    if why:
                        self.findings.append(Finding("flow", level, f"{sc.id}#{i + 1}", {"why": why}))
                        break
                else:
                    passed += 1
            finally:
                s.close()
        return passed

    def _flow_step(self, s: Surface, step) -> str | None:
        role = step.actor.get("role") or (f"external:{step.actor['external']}" if "external" in step.actor else None)
        actor = self.world.actors.get(role)
        if actor is None:
            return f"no actor for role {role!r}"
        exp = step.expect
        if step.read:
            target = step.read["target"]
            if "actions_shown" in exp and sorted(s.allowed(actor, target)) != sorted(exp["actions_shown"]):
                return f"actions shown {sorted(s.allowed(actor, target))}, expected {sorted(exp['actions_shown'])}"
            st = s.state(target) or {}
            missing = [f for f in exp.get("fields_include", []) if f not in st]
            return f"fields missing: {missing}" if missing else None
        o = s.do(actor, step.do, step.target, step.params, f"flow:{id(step)}")
        if "denied_by" in exp:
            want = exp["denied_by"]
            if o.get("status") != "denied" or not ((o.get("code") in MATRIX_CODES) if want == "matrix" else o.get("code") == want):
                return f"expected denial by {want}, got {o}"
            if exp.get("reason_shown") and not o.get("reason"):
                return "no reason shown"
        if "state" in exp:
            if o.get("status") != "ok":
                return f"expected ok, got {o}"
            for path, val in exp["state"].items():
                oid, fld = path.split(".", 1)
                if (s.state(oid) or {}).get(fld) != val:
                    return f"{path} is {(s.state(oid) or {}).get(fld)!r}, expected {val!r}"
        if exp.get("decision_recorded"):
            evs = s.events(step.target)
            if evs is not None and not any(e.kind == "decision" for e in evs):
                return "no decision recorded"
        return None

    # -- everything --------------------------------------------------------------------------
    def run(self, *, explore_examples: int = 200, explore_depth: int = 5, races: bool = True) -> Report:
        cases = self.planner.cases()
        results = {lv: self.run_cases(lv, cases) for lv in self.levels}
        ref = self.levels[0]
        for lv in self.levels[1:]:
            mine = {**results[ref][0], **results[ref][1]}
            theirs = {**results[lv][0], **results[lv][1]}
            for key in sorted(mine.keys() | theirs.keys()):
                want, got = mine.get(key), theirs.get(key)
                if got != want:
                    self.findings.append(Finding("parity", lv, key, {ref: want, lv: got}))

        n_races = self.races(cases) if races and "execution" in self.levels else 0
        flows = {lv: self.flows(lv) for lv in self.levels}

        from .explore import explore
        minimal = explore(self, examples=explore_examples, depth=explore_depth) if explore_examples else None
        if minimal is not None:
            self.findings.append(Finding("exploration", "model", "explore", minimal))

        return Report(self.levels, self.findings, self._coverage(cases, results, flows, n_races),
                      [minimal] if minimal else [])

    def _edge_verdicts(self, cases, results) -> dict[str, str]:
        """Per world-map edge (ADR-0020): failed if any of its cases has a finding at any level,
        uncovered if any of its cases could not run at every level, else verified."""
        failed_cases = {f.case.split("#", 1)[0] for f in self.findings}
        for f in self.findings:
            if f.kind == "race":
                failed_cases |= set(f.case.split(" || "))
        out: dict[str, str] = {}
        for c in cases:
            if c.kind not in ("cell", "create"):
                continue
            e = _edge_of(c)
            if c.id in failed_cases:
                v = "failed"
            elif c.gap or any(c.id not in results[lv][0] for lv in self.levels):
                v = "uncovered"
            else:
                v = "verified"
            prev = out.get(e)
            if prev is None or RANK[v] > RANK[prev]:
                out[e] = v
        return dict(sorted(out.items()))

    def _coverage(self, cases, results, flows, n_races) -> dict[str, Any]:
        cells = [c for c in cases if c.kind == "cell"]
        decided = [c for c in cells if raw_cell(self.d, c.obj, c.state, c.action, c.role) != "undecided"]
        failed = {(f.level, f.case) for f in self.findings}
        covered = {lv: sum(1 for c in decided if c.id in results[lv][0] and (lv, c.id) not in failed)
                   for lv in self.levels}
        return {
            "edges": self._edge_verdicts(cases, results),
            "cells": {"decided": len(decided), "covered": covered,
                      "undecided": sorted({f"{c.obj}.{c.state}.{c.action}" for c in cells if c not in decided}),
                      "gaps": sorted({f"{c.obj}.{c.state}.{c.action}" for c in decided if c.gap})},
            "preconditions": {"cases": sum(c.kind == "precondition" and not c.gap for c in cases),
                              "gaps": [c.id for c in cases if c.kind == "precondition" and c.gap]},
            "creates": sum(c.kind == "create" for c in cases),
            "invariants": {"total": sum(i.scope == "aggregate" for i in self.d.invariants),
                           "exercised": len(self._exercised)},
            "flows": {"total": len(self.d.scenarios), "passed": flows},
            "races": n_races,
            "unreachable": self.world.unreachable,
        }


def _edge_of(c: Case) -> str:
    return f"{c.obj}.{c.state}.{c.action}" if c.kind == "cell" else f"{c.obj}.(new).{c.action}"


def run_harness(d: Domain, **kw: Any) -> Report:
    run_kw = {k: kw.pop(k) for k in ("explore_examples", "explore_depth", "races") if k in kw}
    return Harness(d, **kw).run(**run_kw)


__all__ = ["Finding", "Harness", "Instance", "Report", "run_harness"]
