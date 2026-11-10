"""Bounded exploration (ADR-0010 §4, gate tier): stateful search over action sequences on the
model level, bounded by depth and a fixed number of derandomized examples, never by wall-clock
time, so a run is reproducible. A violation is shrunk to a minimal flow in domain terms."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from hypothesis import HealthCheck, Phase, find, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample

from ..semantics import refusals
from .surfaces import ModelSurface

if TYPE_CHECKING:
    from .run import Harness


def explore(h: Harness, *, examples: int = 200, depth: int = 5) -> dict[str, Any] | None:
    """Return the minimal flow that breaks an invariant, or None if none was found."""
    d, w = h.d, h.world
    starts = [i for i in w.all_instances() if i.obj in d.transitions] or w.all_instances()
    moves = [(name, role) for name, a in d.actions.items() if a.target in d.transitions and a.creates is None
             for role in sorted(w.actors)]
    if not starts or not moves:
        return None
    step = st.tuples(st.integers(0, len(starts) - 1), st.sampled_from(moves))
    flows = st.lists(step, min_size=1, max_size=depth)

    def replay(flow) -> dict[str, Any] | None:
        s = ModelSurface(d, h.clock)
        for obj, data in w.fixtures:
            s.seed(obj, copy.deepcopy(data))
        ids = {}
        steps = []
        for k, (i, (action, role)) in enumerate(flow):
            inst = starts[i]
            if i not in ids:
                ids[i] = f"{inst.data['id']}~x{i}"
                s.seed(inst.obj, {**copy.deepcopy(inst.data), "id": ids[i]})
            if d.actions[action].target != inst.obj:
                continue
            actor = w.actors[role]
            tr = d.transitions.get(inst.obj)
            before = (s.state(ids[i]) or {}).get(tr.field) if tr else None
            o = s.do(actor, action, ids[i], h.planner.params(d.actions[action]), f"x{k}")
            steps.append({"actor": f"{role} {actor.id}", "action": action, "target": inst.id,
                          "from": before, "path": [f"{m.role} {m.action}" for m in inst.path],
                          "outcome": o.get("code") or o.get("status")})
            if o.get("code") == "invariant-guard":
                inv = next((v.id for v in d.invariants if refusals.invariant(v.reason, v.check, d) == o.get("reason")),
                           o.get("reason"))
                return {"invariant": inv, "steps": steps}
            st_ = s.state(ids[i])
            broken = h.interp.violated_invariants(inst.obj, st_, s.lookup) if st_ else []
            if broken:
                return {"invariant": broken[0].id, "steps": steps}
        return None

    try:
        flow = find(flows, lambda f: replay(f) is not None,
                    settings=settings(max_examples=examples, derandomize=True, database=None,
                                      phases=[Phase.generate, Phase.shrink],
                                      suppress_health_check=list(HealthCheck), deadline=None))
    except NoSuchExample:
        return None
    return replay(flow)
