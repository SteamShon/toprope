"""The mechanical layer (ADR-0035): tests of "it does what the declaration says" that need no
examples. Objects are generated from the declaration's property types, enums and links, in
every stage of the matrix, keeping only those that satisfy every invariant. Then every
(stage, action, role) cell is run on them:

- **inductive invariants**: a move the matrix allows must not leave an invariant broken. At
  every level the invariant guard refuses such a move; the finding (`inductive`) names the
  cell, the invariant and the generated starting object. It is a **warning**: the start may be
  one no real history reaches, but nothing in the declaration rules it out.
- **parity**: every level must give the same outcome as the model for the same object.
- **reachability from creation**: stages that no declared move reaches from the stage a
  created object starts in (a static walk of the matrix).

Generation is seeded and bounded, so a run is reproducible and cacheable (ADR-0013). Whether
what is declared is *right* is the semantic layer's question (examples and scenarios).
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..decl.models import ByRole, Domain, Target
from ..errors import fixed
from ..semantics.interpreter import Interpreter
from .world import default_params, world_actors

ATTEMPTS = 30                          # tries per cell to find objects that satisfy the invariants
INTS = (0, 1, 2, 7, 30, 100)
NUMS = (0.0, 0.5, 1.0, -1.0, 100.0)
STRS = ("x", "example", "")
DATES = ("2026-01-01T00:00:00+00:00", "2026-06-30T12:00:00+00:00")


@dataclass
class Mechanical:
    findings: list[Any] = field(default_factory=list)
    cells: int = 0                      # (stage, action, role) cells run
    samples: int = 0                    # generated objects run through them
    no_sample: list[str] = field(default_factory=list)   # cells with no object satisfying the invariants
    unreachable_from_creation: dict[str, list[str]] = field(default_factory=dict)

    def coverage(self) -> dict[str, Any]:
        return {"cells": self.cells, "samples": self.samples, "no_sample": self.no_sample,
                "unreachable_from_creation": self.unreachable_from_creation}


def _value(spec: Any, rng: random.Random) -> Any:
    if spec.enum:
        return rng.choice(spec.enum)
    return {"integer": lambda: rng.choice(INTS), "number": lambda: rng.choice(NUMS),
            "boolean": lambda: rng.random() < 0.5, "datetime": lambda: rng.choice(DATES),
            "string": lambda: rng.choice(STRS)}[spec.type or "string"]()


class Generator:
    """Objects from the declaration's types; linked objects are generated alongside. `tag`
    keeps ids apart between cells that share a surface."""

    def __init__(self, d: Domain, rng: random.Random, tag: str = ""):
        self.d, self.rng, self.n, self.tag = d, rng, 0, tag

    def make(self, obj: str, state: str | None, depth: int = 1) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        self.n += 1
        oid = f"{obj}~m{self.tag}{self.n}"
        tr = self.d.transitions.get(obj)
        data: dict[str, Any] = {"id": oid}
        extras: list[tuple[str, dict[str, Any]]] = []
        for name, spec in self.d.objects[obj].properties.items():
            if tr is not None and name == tr.field:
                continue
            if spec.optional and self.rng.random() < 0.4:
                continue
            data[name] = _value(spec, self.rng)
        if tr is not None:
            data[tr.field] = state if state is not None else tr.initial
        for lname, link in self.d.links.items():
            if link.from_ != obj:
                continue
            # Required links are always filled, two levels deep; optional ones only at the top.
            if (link.required and depth <= -2) or (not link.required and (depth <= 0 or self.rng.random() < 0.3)):
                continue
            ttr = self.d.transitions.get(link.to)
            tstate = self.rng.choice(list(ttr.matrix)) if ttr else None
            tdata, more = self.make(link.to, tstate, depth - 1)
            extras += more + [(link.to, tdata)]
            data[lname] = [tdata["id"]] if link.cardinality.endswith("many") else tdata["id"]
        return data, extras


def _params(d: Domain, a: Any, gen: Generator, clock: Callable[[], datetime]) -> tuple[dict[str, Any], list]:
    """The action's required params; a `ref` param names a generated object of that type."""
    params = default_params(d, a, [], clock)
    extras: list[tuple[str, dict[str, Any]]] = []
    for name, spec in a.params.items():
        if spec.optional or not spec.ref or spec.ref not in d.objects:
            continue
        ttr = d.transitions.get(spec.ref)
        tdata, more = gen.make(spec.ref, ttr.initial if ttr else None)
        extras += more + [(spec.ref, tdata)]
        params[name] = [tdata["id"]] if spec.many else tdata["id"]
    return params, extras


def _allows(cell: Any) -> list[str]:
    if isinstance(cell, Target):
        return [cell.to]
    if isinstance(cell, ByRole):
        return [t for c in cell.by_role.values() for t in _allows(c)]
    if isinstance(cell, str) and cell not in ("n/a", "undecided"):
        return [cell]
    return []


def unreachable_from_creation(d: Domain) -> dict[str, list[str]]:
    """Stages no declared move reaches from where a created object starts. Objects no action
    creates come from elsewhere (seeded, handed over), so they are not walked."""
    out = {}
    for obj, tr in d.transitions.items():
        if not any(a.creates == obj for a in d.actions.values()):
            continue
        seen, todo = {tr.initial}, [tr.initial]
        while todo:
            st = todo.pop()
            for nxt in (t for c in tr.matrix.get(st, {}).values() for t in _allows(c)):
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        lost = [s for s in tr.matrix if s not in seen]
        if lost:
            out[obj] = lost
    return out


def run_mechanical(d: Domain, surfaces: dict[str, Any], clock: Callable[[], datetime], *,
                   samples: int = 3, seed: int = 0, actions: set[str] | None = None,
                   actors: dict[str, Any] | None = None,
                   unreachable: dict[str, list[str]] | None = None) -> Mechanical:
    """Run every cell of `d` (or of `actions`) on generated objects, on each surface; the first
    surface is the reference for parity. `surfaces` maps a level to a fresh Surface. Each cell
    has its own seeded generator, so a cell's objects never depend on which other cells ran."""
    import hashlib

    from .run import Finding
    res = Mechanical(unreachable_from_creation=unreachable if unreachable is not None
                     else unreachable_from_creation(d))
    interp = Interpreter(d, clock)
    actors = actors or world_actors(d)
    levels = list(surfaces)
    ref = levels[0]
    k = 0
    for obj, tr in sorted(d.transitions.items()):
        for state in tr.matrix:
            for name, a in d.actions.items():
                if a.target != obj or (actions is not None and name not in actions):
                    continue
                for role, actor in actors.items():
                    cell = f"{obj}.{state}.{name}.{role}"
                    tag = hashlib.sha256(f"{seed}|{cell}".encode()).hexdigest()[:8]
                    gen = Generator(d, random.Random(tag), tag)
                    found = []
                    for _ in range(ATTEMPTS):
                        data, extras = gen.make(obj, state)
                        pool = {x["id"]: (o, x) for o, x in extras}
                        if any(interp.violated_invariants(o, x, pool.get) for o, x in extras):
                            continue
                        if interp.violated_invariants(obj, data, pool.get):
                            continue
                        found.append((data, extras))
                        if len(found) >= samples:
                            break
                    res.cells += 1
                    if not found:
                        res.no_sample.append(cell)
                        res.findings.append(Finding("no-sample", ref, f"mechanical:{cell}", {
                            "reason": fixed("no generated object satisfies the invariants in this stage",
                                            "give an example in this stage"),
                            "why": "the cell is not tested mechanically; give an example in this stage"}))
                        continue
                    for data, extras in found:
                        params, refs = _params(d, a, gen, clock)
                        extras = extras + refs
                        k += 1
                        res.samples += 1
                        got = {}
                        for lv, s in surfaces.items():
                            for o, x in extras:
                                s.seed(o, copy.deepcopy(x))
                            s.seed(obj, copy.deepcopy(data))
                            got[lv] = s.do(actor, name, data["id"], params, f"mech{k}")
                        out = got[ref]
                        case = f"mechanical:{cell}"
                        if out.get("code") == "invariant-guard":
                            res.findings.append(Finding("inductive", ref, case, {
                                "reason": out.get("reason"), "start": data,
                                "why": "from an object every invariant allows, this move breaks one: strengthen "
                                       "an invariant (rule out the start) or a precondition (refuse the move)"}))
                        for lv in levels[1:]:
                            if got[lv] != out:
                                res.findings.append(Finding("parity", lv, case, {ref: out, lv: got[lv], "start": data}))
    return res


__all__ = ["Generator", "Mechanical", "run_mechanical", "unreachable_from_creation"]
