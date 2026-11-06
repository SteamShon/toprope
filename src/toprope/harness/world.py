"""The small world (ADR-0010 §3): grown from the expert's fixtures.

It holds at least one instance per reachable state, one actor per role, and a default value
for every param. States that no allowed transition reaches are reported, because they are
either dead or point to a missing transition.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..decl.models import Action, Domain, Param
from ..semantics.model import ReferenceModel
from ..semantics.types import Actor, Command

MAX_GROWTH_STEPS = 500     # BFS bound: a small world, never an exhaustive one


@dataclass(frozen=True)
class Move:
    """One step of how an instance was reached, in domain terms."""
    role: str
    action: str
    params: dict[str, Any] = field(default_factory=dict, hash=False)


@dataclass
class Instance:
    obj: str
    id: str                      # the fixture id it descends from
    data: dict[str, Any]         # the state snapshot (including its own id)
    path: tuple[Move, ...] = ()  # how it was reached from the fixture

    def state_of(self, d: Domain) -> str | None:
        tr = d.transitions.get(self.obj)
        return None if tr is None else self.data.get(tr.field)


@dataclass
class SmallWorld:
    domain: Domain
    actors: dict[str, Actor]                                  # role → a person with that role
    fixtures: list[tuple[str, dict[str, Any]]]
    instances: dict[tuple[str, str | None], list[Instance]]   # (object type, state) → instances
    unreachable: dict[str, list[str]]                         # object type → matrix states never reached

    def in_state(self, obj: str, state: str | None) -> list[Instance]:
        return self.instances.get((obj, state), [])

    def all_instances(self) -> list[Instance]:
        return [i for xs in self.instances.values() for i in xs]


def world_actors(d: Domain) -> dict[str, Actor]:
    """One person per role: the first name the world declares for it, else `<role>-1`. If an
    action is for `external:kernel` (ADR-0028), the kernel is an actor too."""
    from ..kernel import KERNEL
    out = {}
    for role in d.roles:
        names = d.world.actors.get(role) or [f"{role}-1"]
        out[role] = Actor(names[0], "person", (role,))
    if any((r.role if hasattr(r, "role") else r) == KERNEL for a in d.actions.values() for r in a.actor):
        out[KERNEL] = Actor(KERNEL, "system", (KERNEL,))
    return out


def default_params(d: Domain, action: Action, fixtures: list[tuple[str, dict[str, Any]]],
                   clock: Callable[[], datetime]) -> dict[str, Any]:
    """A valid value for every required param. Optional params are left out."""
    out: dict[str, Any] = {}
    for name, spec in action.params.items():
        if spec.optional:
            continue
        v = _value(spec, fixtures, clock)
        out[name] = [v] if spec.many else v
    return out


def _value(spec: Param, fixtures: list[tuple[str, dict[str, Any]]], clock: Callable[[], datetime]) -> Any:
    if spec.enum:
        return spec.enum[0]
    if spec.ref:
        return next((data["id"] for obj, data in fixtures if obj == spec.ref), f"{spec.ref}-example")
    return {"string": "example", "integer": 1, "number": 1.0, "boolean": True,
            "datetime": clock().isoformat()}[spec.type or "string"]


def grow_world(d: Domain, clock: Callable[[], datetime] | None = None) -> SmallWorld:
    clock = clock or (lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    actors = world_actors(d)
    fixtures = [next(iter(fx.items())) for fx in d.world.fixtures]
    instances: dict[tuple[str, str | None], list[Instance]] = {}
    seen: set[tuple[str, str | None]] = set()
    frontier: list[Instance] = []

    def add(inst: Instance, always: bool = False) -> None:
        key = (inst.obj, inst.state_of(d))
        instances.setdefault(key, []).append(inst)
        if key not in seen or always:
            seen.add(key)
            frontier.append(inst)

    # Every example is explored, not one per stage: two examples in the same stage can differ
    # in what their preconditions allow (a refused and a successful deploy are both `done`).
    for obj, data in fixtures:
        add(Instance(obj, data["id"], copy.deepcopy(data)), always=True)

    # A scratch model: every attempt runs on a fresh clone, so instances never interfere.
    m = ReferenceModel(d, clock=clock, seed_world=False)
    for obj, data in fixtures:
        m.seed(obj, data)
    n = 0

    # Objects that only exist through a create action.
    for name, a in d.actions.items():
        if a.creates is None:
            continue
        for role, actor in actors.items():
            n += 1
            new_id = f"{a.creates}~new{n}"
            out = m.execute(Command(actor, name, new_id, default_params(d, a, fixtures, clock)))
            if out.ok and out.state is not None:
                add(Instance(a.creates, new_id, out.state, (Move(role, name, default_params(d, a, fixtures, clock)),)))
                break

    while frontier and n < MAX_GROWTH_STEPS:
        inst = frontier.pop(0)
        for name, a in d.actions.items():
            if a.target != inst.obj:
                continue
            params = default_params(d, a, fixtures, clock)
            for role, actor in actors.items():
                n += 1
                clone = f"{inst.data['id']}~g{n}"
                m.seed(inst.obj, {**copy.deepcopy(inst.data), "id": clone})
                out = m.execute(Command(actor, name, clone, params))
                if out.ok and out.state is not None:
                    data = {**out.state, "id": inst.data["id"]}
                    nxt = Instance(inst.obj, inst.id, data, inst.path + (Move(role, name, params),))
                    if (inst.obj, nxt.state_of(d)) not in seen:
                        add(nxt)
                    break   # one role reaching a state is enough

    unreachable = {obj: [s for s in tr.matrix if (obj, s) not in seen] for obj, tr in d.transitions.items()}
    return SmallWorld(d, actors, fixtures, instances, {k: v for k, v in unreachable.items() if v})
