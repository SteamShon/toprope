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
from ..identity import Caller, Identity
from ..semantics.model import ReferenceModel
from ..types import Actor, Command, Event, Outcome
from ..store import EventStore


class Execution:
    def __init__(self, domain: Domain, store: EventStore, identity: Identity,
                 clock: Callable[[], datetime] | None = None, transport: Any = None):
        """`transport` (a HandoffTransport) sends this domain's handoffs after each append."""
        self.d = domain
        self.store = store
        self.identity = identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.transport = transport
        self._model = ReferenceModel(domain, store, clock=self.clock, seed_world=False)

    # -- commands ----------------------------------------------------------------------------
    def submit(self, credentials: str | None, action: str, target: str | None,
               params: dict[str, Any] | None = None, idempotency_key: str | None = None,
               thread_id: str | None = None, run_id: str | None = None) -> Outcome:
        # Step 0 (command validation) before step 1 (identity), as in docs/semantics.md.
        spec = self.d.actions.get(action)
        if spec is None:
            return Outcome("rejected", "unknown-action", f"No action {action}.")
        if target is None:
            return Outcome("rejected", "invalid-command", "A target id is required.")
        if not idempotency_key:
            # Every command from outside the process carries a key (docs/semantics.md §1).
            return Outcome("rejected", "invalid-command", "An idempotency key is required.")
        bad = self._model.interp.invalid_params(spec, dict(params or {}))
        if bad:
            return Outcome("rejected", "invalid-command", bad)
        caller = self.identity.resolve(credentials)
        if caller is None:
            return Outcome("rejected", "unauthenticated", "Unknown or missing credentials.")
        cmd = Command(caller.actor, action, target, dict(params or {}), idempotency_key, self.clock(),
                      caller.on_behalf_of, caller.grant, thread_id, run_id)
        return self._after(self._model.execute(cmd))

    def _after(self, out: Outcome) -> Outcome:
        """Step 12: send the outbox after the append. It never changes the sender's outcome."""
        if self.transport is not None and any(e.kind == "outbox" for e in out.events):
            try:
                self.dispatch()
            except Exception:    # pending handoffs are retried by the next dispatch
                pass
        return out

    def dispatch(self) -> list[dict[str, Any]]:
        """Send every pending handoff of this domain through the transport."""
        from ..handoff import Outbox
        if self.transport is None:
            raise RuntimeError("no handoff transport configured")
        return Outbox(self).dispatch(self.transport)

    def receive_handoff(self, handoff: str, action: str, target: str, params: dict[str, Any],
                        handoff_id: str, origin: dict[str, Any] | None) -> Outcome:
        """A command from another domain's handoff (step 12): actor `system` (`handoff:<name>`),
        on behalf of the originating person, keyed by the handoff id. In-process transports
        call this; it never goes through credentials, so no caller can impersonate it."""
        spec = self.d.actions.get(action)
        if spec is None:
            return Outcome("rejected", "unknown-action", f"No action {action}.")
        bad = self._model.interp.invalid_params(spec, dict(params or {}))
        if bad:
            return Outcome("rejected", "invalid-command", bad)
        actor = Actor(f"handoff:{handoff}", "system", ("system",))
        principal = Actor(origin["id"], "person") if origin else None
        cmd = Command(actor, action, target, dict(params or {}), handoff_id, self.clock(),
                      on_behalf_of=principal, causation=handoff_id)
        return self._after(self._model.execute(cmd))

    def seed_world(self) -> int:
        """Load the declaration's fixtures into an empty store. Idempotent: existing ids are
        skipped. Returns the number of objects seeded."""
        n = 0
        for fx in self.d.world.fixtures:
            ((obj, data),) = fx.items()
            n += self._model.seed(obj, data, only_if_new=True)
        return n

    def seed(self, obj: str, data: dict[str, Any]) -> bool:
        """Load one object as a system-created fixture (not through an action), only if its id
        is new. For fixtures and harness setup; never exposed to callers."""
        return self._model.seed(obj, data, only_if_new=True)

    # -- reads -------------------------------------------------------------------------------
    def state(self, oid: str) -> dict[str, Any] | None:
        return self._model.state(oid)

    def lookup(self, oid: str) -> tuple[str, dict[str, Any]] | None:
        """(object type, state) of an object, or None."""
        return self._model.lookup(oid)

    def history(self, oid: str) -> list[Event]:
        return self.store.read(oid)

    def attempts(self, oid: str) -> list[Event]:
        return self.store.read_attempts(oid)

    def allowed_actions(self, oid: str, who: Actor | Caller) -> list[str]:
        """Actions the caller could take on `oid` now. Pass the resolved Caller for an agent, so
        its principal and grant are applied as they would be at submit time."""
        if isinstance(who, Caller):
            return self._model.allowed_actions(oid, who.actor, who.on_behalf_of, who.grant)
        return self._model.allowed_actions(oid, who)


__all__ = ["Execution"]
