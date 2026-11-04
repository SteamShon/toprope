"""The reference model: interpreter + event store, implementing steps 1-3 and 11.

Execution (M0a sub-PR 4) adds the Identity port and durable stores on top of the same flow.
"""

from __future__ import annotations

import copy
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
        state = {**(state or {}), **copy.deepcopy(ev.payload["changes"])}
    return state


class ReferenceModel:
    def __init__(self, domain: Domain, store: EventStore | None = None,
                 clock: Callable[[], datetime] | None = None, seed_world: bool = True):
        self.d = domain
        self.store = store or MemoryEventStore()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.interp = Interpreter(domain, self.clock)
        if seed_world:
            for fx in domain.world.fixtures:
                ((obj, data),) = fx.items()
                self.seed(obj, data)

    # -- state -------------------------------------------------------------------------
    def seed(self, obj: str, data: dict[str, Any]) -> None:
        """Load a fixture as a system-created object (not through an action)."""
        oid = data["id"]
        ev = Event(f"{obj}Created", oid, obj, at=self.clock(), actor=SYSTEM.ref(),
                   payload={"changes": copy.deepcopy(data), "params": {}, "action": None, "fixture": True},
                   domain_version=self.d.version)
        self.store.append(oid, self.store.version(oid), [ev])

    def state(self, oid: str) -> dict[str, Any] | None:
        return project(self.store.read(oid))

    def type_of(self, oid: str) -> str | None:
        events = self.store.read(oid)
        return events[0].aggregate if events else None

    def lookup(self, oid: str) -> tuple[str, dict[str, Any]] | None:
        events = self.store.read(oid)
        return (events[0].aggregate, project(events)) if events else None

    # -- commands (docs/semantics.md §2) -------------------------------------------------
    def execute(self, cmd: Command) -> Outcome:
        if cmd.actor is None:                                                  # step 1
            return Outcome("rejected", "unauthenticated", "Unknown actor.")
        key = None
        if cmd.idempotency_key:                                                # step 2
            key = (cmd.actor.id, cmd.action, cmd.target, cmd.idempotency_key)
            prev = self.store.claim(key)
            if prev == "pending":
                return Outcome("rejected", "in-progress", "The same command is already being processed.")
            if prev is not None:
                return prev
        try:
            out = self._run(cmd)
        except BaseException:
            if key is not None:
                self.store.release(key)        # never leave a key stuck in "pending"
            raise
        if key is not None:
            if out.code == "conflict":
                self.store.release(key)        # transient: the same key may be retried
            else:
                self.store.remember(key, out)
        return out

    def _run(self, cmd: Command) -> Outcome:
        action = self.d.actions.get(cmd.action)
        for _ in range(MAX_RETRIES + 1):
            stream = cmd.target or ""
            v = self.store.version(stream)                                     # step 3
            found = self.lookup(stream) if v else None
            # A target of another object type does not exist for this action, unless the action
            # creates: then the id is taken (rejected: exists).
            state = None if found is None else found[1]
            if found is not None and action is not None and action.creates is None and found[0] != action.object_type:
                state = None
            dec = self.interp.decide(cmd, state, self.lookup)
            for att in dec.attempts:
                self.store.append_attempt(att)
            if not dec.events:
                return dec.outcome
            try:                                                               # step 11
                written = self.store.append(stream, v, list(dec.events))
            except ConcurrencyError:
                continue
            return Outcome(dec.outcome.status, dec.outcome.code, dec.outcome.reason,
                           self.state(stream), tuple(written))
        return Outcome("rejected", "conflict", f"{cmd.target} kept changing; gave up after {MAX_RETRIES} retries.")

    def allowed_actions(self, oid: str, actor: Actor) -> list[str]:
        found = self.lookup(oid)
        return [] if found is None else self.interp.allowed_actions(found[0], found[1], actor, self.lookup)
