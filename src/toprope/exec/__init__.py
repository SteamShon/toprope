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
from ..errors import fixed
from ..identity import Caller, Identity
from ..semantics.interpreter import NO_TARGET, no_action
from ..semantics.model import ReferenceModel
from ..types import Actor, Command, Event, Outcome
from ..store import EventStore


class Execution:
    def __init__(self, domain: Domain, store: EventStore, identity: Identity,
                 clock: Callable[[], datetime] | None = None, transport: Any = None,
                 accepts: dict[str, set[str]] | None = None, services: Any = None):
        """`transport` (a HandoffTransport) sends this domain's handoffs after each append.
        `accepts` (from a composition, ADR-0026) maps each receiving action to the handoffs
        wired to it (`<sender domain>.<handoff>`); any other handoff is refused. None: a domain
        served alone accepts any handoff its actor rules allow."""
        self.d = domain
        self.store = store
        self.identity = identity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.transport = transport
        self.accepts = accepts
        self.services = services          # KernelServices: runs this domain's kernel calls (ADR-0028)
        self._dispatching = False
        self._model = ReferenceModel(domain, store, clock=self.clock, seed_world=False)

    @property
    def person_route(self) -> str | None:
        """How a person takes a step an agent is refused, in this deployment: added to such
        refusals' fix. Set by the adapter from its configuration; None says only to ask a person."""
        return self._model.interp.person_route

    @person_route.setter
    def person_route(self, route: str | None) -> None:
        self._model.interp.person_route = route or None

    # -- commands ----------------------------------------------------------------------------
    def submit(self, credentials: str | None, action: str, target: str | None,
               params: dict[str, Any] | None = None, idempotency_key: str | None = None,
               thread_id: str | None = None, run_id: str | None = None) -> Outcome:
        # Step 0 (command validation) before step 1 (identity), as in docs/semantics.md.
        spec = self.d.actions.get(action)
        if spec is None:
            return Outcome("rejected", "unknown-action", no_action(action))
        if target is None:
            return Outcome("rejected", "invalid-command", NO_TARGET)
        if not idempotency_key:
            # Every command from outside the process carries a key (docs/semantics.md §1).
            return Outcome("rejected", "invalid-command", fixed("An idempotency key is required.",
                                                                "give each command a key of its own, and the same "
                                                                "key when you send it again"))
        bad = self._model.interp.invalid_params(spec, dict(params or {}))
        if bad:
            return Outcome("rejected", "invalid-command", bad)
        caller = self.identity.resolve(credentials)
        if caller is None:
            return Outcome("rejected", "unauthenticated", fixed("Unknown or missing credentials.",
                                                                "give a token or git identity the identity file lists"))
        cmd = Command(caller.actor, action, target, dict(params or {}), idempotency_key, self.clock(),
                      caller.on_behalf_of, caller.grant, thread_id, run_id)
        return self._after(self._model.execute(cmd))

    def _after(self, out: Outcome) -> Outcome:
        """Step 12: send the outbox after the append. It never changes the sender's outcome."""
        if ((self.transport is not None or self.services is not None) and not self._dispatching
                and any(e.kind == "outbox" for e in out.events)):
            try:
                self._dispatch_events(list(out.events))
            except Exception:    # pending entries are retried by the next dispatch()
                pass
        return out

    def _dispatch_events(self, events: list[Event], limit: int = 100) -> list[dict[str, Any]]:
        """Send the outbox entries these events created, then those their kernel replies
        create, without scanning the store (`dispatch()` does that, for retries)."""
        from ..handoff import Outbox, pending_of
        box, report = Outbox(self), []
        queue = [pending_of(e) for e in events if e.kind == "outbox"]
        self._dispatching = True
        try:
            while queue and len(report) < limit:
                rep, follow = box.process(queue.pop(0), self.transport, self.services)
                if rep is not None:
                    report.append(rep)
                queue += [pending_of(e) for e in follow if e.kind == "outbox"]
        finally:
            self._dispatching = False
        return report

    def dispatch(self, rounds: int = 20) -> list[dict[str, Any]]:
        """Send every pending outbox entry: handoffs through the transport, kernel calls through
        the services. A reply may call again; that is sent in the next round, up to `rounds`."""
        from ..handoff import Outbox
        if self.transport is None and self.services is None:
            raise RuntimeError(fixed("no handoff transport or kernel services configured",
                                     "give the execution a transport or kernel services before dispatching"))
        report: list[dict[str, Any]] = []
        self._dispatching = True
        try:
            for _ in range(rounds):
                done = Outbox(self).dispatch(self.transport, self.services)
                report += done
                if not any(r["result"] != "pending" for r in done):
                    break
        finally:
            self._dispatching = False
        return report

    def receive_kernel_reply(self, effect_id: str, action: str, target: str,
                             params: dict[str, Any], requested_at: int | None = None) -> Outcome:
        """A kernel service's result (ADR-0028): a command from `external:kernel` to the reply
        action, keyed by the effect id, so it is applied at most once. It goes through the
        domain's rules like any other command. Only the outbox calls this. `requested_at` is
        the version of the target's stream that holds the call: a reply that comes after the
        target left the state it was called in is late, recorded and not applied."""
        from ..kernel import KERNEL
        spec = self.d.actions.get(action)
        if spec is None:
            return Outcome("rejected", "unknown-action", no_action(action))
        bad = self._model.interp.invalid_params(spec, dict(params))
        if bad:
            return Outcome("rejected", "invalid-command", bad)
        late = self._moved_since(target, requested_at) if requested_at is not None else None
        if late:
            return Outcome("denied", "late-reply", late)
        cmd = Command(Actor(KERNEL, "system", (KERNEL,)), action, target, dict(params), effect_id, self.clock(),
                      causation=effect_id)
        return self._after(self._model.execute(cmd))

    def _moved_since(self, target: str, version: int) -> str | None:
        """Why a reply is late: after the call, someone other than the kernel (a person, an
        agent, a handoff) moved the target out of its state (its matrix field). Another reply
        of the same call's action may move it: that is the action's own result, not moving on."""
        from ..kernel import KERNEL
        from ..semantics.model import project
        evs = self.store.read(target)
        tr = self.d.transitions.get(evs[0].aggregate) if evs else None
        if tr is None:
            return None
        domain = [e for e in evs if e.kind == "domain"]
        then = (project([e for e in domain if e.version <= version]) or {}).get(tr.field)
        for i, e in enumerate(domain):
            if e.version <= version or (e.actor or {}).get("id") == KERNEL:
                continue
            before = (project(domain[:i]) or {}).get(tr.field)
            after = (project(domain[:i + 1]) or {}).get(tr.field)
            if before != after:
                return fixed(f"Late reply: {target} was {then} when the kernel was called; "
                             f"{(e.payload or {}).get('action')} moved it to {after} since. "
                             "The reply is recorded, not applied.",
                             f"take the action that calls the kernel again from {after}, if it still applies")
        return None

    def receive_handoff(self, handoff: str, action: str, target: str, params: dict[str, Any],
                        handoff_id: str, origin: dict[str, Any] | None) -> Outcome:
        """A command from another domain's handoff (step 12). `handoff` is
        `<sender domain>.<handoff name>`; the actor is `system` with id `handoff:<that>`
        (ADR-0026), on behalf of the originating person, keyed by the handoff id. In-process
        transports call this; it never goes through credentials, so no caller can impersonate it."""
        spec = self.d.actions.get(action)
        if spec is None:
            return Outcome("rejected", "unknown-action", no_action(action))
        bad = self._model.interp.invalid_params(spec, dict(params or {}))
        if bad:
            return Outcome("rejected", "invalid-command", bad)
        actor = Actor(f"handoff:{handoff}", "system", ("system",))
        if self.accepts is not None and handoff not in self.accepts.get(action, set()):
            reason = fixed(f"{handoff} is not wired to {action} in this composition.",
                           f"wire the handoff to {action} in the composition, or send it to an action it is wired to")
            self.store.append_attempt(Event(
                "DeniedAttempt", target, spec.object_type, kind="attempt", at=self.clock(), actor=actor.ref(),
                domain_version=self.d.version, causation=handoff_id,
                payload={"action": action, "code": "actor", "reason": reason, "params": dict(params or {})}))
            return Outcome("denied", "actor", reason)
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
