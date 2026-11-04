"""Execution: the runtime entry point for commands (docs/semantics.md §2, ADR-0012, ADR-0016).

It resolves the caller through the Identity port (step 1) and runs the same steps as the
reference model on a durable event store. Surfaces (MCP, HTTP, UI) call `submit`, never the
store or the interpreter directly, so every action goes through one gate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..decl.models import Domain
from ..identity import Identity
from ..semantics.model import ReferenceModel
from ..types import Actor, Command, Event, Outcome
from ..store import EventStore


class Execution:
    def __init__(self, domain: Domain, store: EventStore, identity: Identity,
                 clock: Callable[[], datetime] | None = None):
        self.d = domain
        self.store = store
        self.identity = identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._model = ReferenceModel(domain, store, clock=self.clock, seed_world=False)

    # -- commands ----------------------------------------------------------------------------
    def submit(self, credentials: str | None, action: str, target: str | None,
               params: dict[str, Any] | None = None, idempotency_key: str | None = None,
               thread_id: str | None = None, run_id: str | None = None) -> Outcome:
        caller = self.identity.resolve(credentials)
        if caller is None:
            return Outcome("rejected", "unauthenticated", "Unknown or missing credentials.")
        cmd = Command(caller.actor, action, target, dict(params or {}), idempotency_key, self.clock(),
                      caller.on_behalf_of, caller.grant, thread_id, run_id)
        return self._model.execute(cmd)

    def seed_world(self) -> int:
        """Load the declaration's fixtures into an empty store. Idempotent: existing ids are
        skipped. Returns the number of objects seeded."""
        n = 0
        for fx in self.d.world.fixtures:
            ((obj, data),) = fx.items()
            if self.store.version(data["id"]) == 0:
                self._model.seed(obj, data)
                n += 1
        return n

    # -- reads -------------------------------------------------------------------------------
    def state(self, oid: str) -> dict[str, Any] | None:
        return self._model.state(oid)

    def history(self, oid: str) -> list[Event]:
        return self.store.read(oid)

    def attempts(self, oid: str) -> list[Event]:
        return self.store.read_attempts(oid)

    def allowed_actions(self, oid: str, actor: Actor) -> list[str]:
        return self._model.allowed_actions(oid, actor)


__all__ = ["Execution"]
