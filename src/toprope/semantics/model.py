"""The reference model: interpreter + event store, implementing steps 1-3 and 11.

Execution (M0a sub-PR 4) adds the Identity port and durable stores on top of the same flow.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..decl.models import Domain
from ..store import ConcurrencyError, EventStore, MemoryEventStore
from .interpreter import Interpreter
from .types import Actor, Command, Event, Outcome

SYSTEM = Actor("system", "system", ("system",))
MAX_RETRIES = 3


def project(events: list[Event]) -> dict[str, Any] | None:
    """Pure fold of a stream's domain events into current state (replay parity, ADR-0012)."""
    state: dict[str, Any] | None = None
    for ev in events:
        if ev.kind != "domain":
            continue
        if ev.type.endswith("Created") and state is None:
            state = dict(ev.payload["changes"])
        else:
            state = {**(state or {}), **ev.payload["changes"]}
    return state


class ReferenceModel:
    def __init__(self, domain: Domain, store: EventStore | None = None,
                 clock: Callable[[], datetime] | None = None, seed_world: bool = True):
        self.d = domain
        self.store = store or MemoryEventStore()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.interp = Interpreter(domain, self.clock)
        self._types: dict[str, str] = {}
        if seed_world:
            for fx in domain.world.fixtures:
                ((obj, data),) = fx.items()
                self.seed(obj, data)

    # -- state -------------------------------------------------------------------------
    def seed(self, obj: str, data: dict[str, Any]) -> None:
        """Load a fixture as a system-created object (not through an action)."""
        oid = data["id"]
        self._types[oid] = obj
        ev = Event(f"{obj}Created", oid, obj, at=self.clock(), actor=SYSTEM.ref(),
                   payload={"changes": dict(data), "params": {}, "action": None, "fixture": True},
                   domain_version=self.d.version)
        self.store.append(oid, self.store.version(oid), [ev])

    def state(self, oid: str) -> dict[str, Any] | None:
        return project(self.store.read(oid))

    def type_of(self, oid: str) -> str | None:
        return self._types.get(oid)

    # -- commands (docs/semantics.md §2) -------------------------------------------------
    def execute(self, cmd: Command) -> Outcome:
        if cmd.actor is None:                                                  # step 1
            return Outcome("rejected", "unauthenticated", "Unknown actor.")
        key = None
        if cmd.idempotency_key:                                                # step 2
            key = (cmd.actor.id, cmd.action, cmd.target, cmd.idempotency_key)
            if (prev := self.store.recall(key)) is not None:
                return prev
        for _ in range(MAX_RETRIES + 1):
            stream = cmd.target or ""
            v = self.store.version(stream)                                     # step 3
            dec = self.interp.decide(cmd, self.state(stream) if v else None, self.state)
            for att in dec.attempts:
                self.store.append_attempt(att)
            if not dec.events:
                out = dec.outcome
                break
            try:                                                               # step 11
                written = self.store.append(stream, v, list(dec.events))
            except ConcurrencyError:
                continue
            if cmd.action in self.d.actions:
                self._types.setdefault(stream, self.d.actions[cmd.action].object_type)
            out = type(dec.outcome)(dec.outcome.status, dec.outcome.code, dec.outcome.reason,
                                    self.state(stream), tuple(written))
            break
        else:
            out = Outcome("rejected", "conflict", f"{cmd.target} kept changing; gave up after {MAX_RETRIES} retries.")
        if key is not None:
            self.store.remember(key, out)
        return out

    def allowed_actions(self, oid: str, actor: Actor) -> list[str]:
        st = self.state(oid)
        obj = self.type_of(oid)
        return [] if st is None or obj is None else self.interp.allowed_actions(obj, st, actor, self.state)
