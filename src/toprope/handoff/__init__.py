"""Handoffs: the outbox and its transport (ADR-0022, docs/semantics.md step 12).

The sender's interpreter appends a `HandoffRequested` outbox event atomically with the
action's events. After the append, `Outbox.dispatch` sends each pending request through a
`HandoffTransport` and records the outcome in the sender's store, in a resolution stream
`handoff:<handoff id>`:
- `HandoffDelivered` (the receiver accepted), `HandoffDenied` (the receiver's rules denied
  it: the sender's own rules and proposals can react), or `HandoffFailed` (the mapping could
  not be evaluated, or the receiver rejected the command, e.g. not-found or invalid params).
- A transient outcome (`conflict`, `in-progress`) or a transport error leaves it pending,
  and the next dispatch retries it.

The handoff id is `<handoff name>:<sender stream>@<outbox event version>`. It is the
receiver's idempotency key, so a retry after a crash never delivers twice, and it is the
`causation` recorded on the receiver's events, so the two stores are linked.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..store import ConcurrencyError
from ..types import Event, Outcome

if TYPE_CHECKING:
    from ..exec import Execution

TRANSIENT = {"conflict", "in-progress"}
RESOLUTION_PREFIX = "handoff:"


class HandoffTransport(ABC):
    @abstractmethod
    def deliver(self, domain: str, handoff: str, action: str, target: str, params: dict[str, Any],
                handoff_id: str, origin: dict[str, Any] | None) -> Outcome:
        """Issue the command in the receiving domain as `system` (`handoff:<sender>.<name>`);
        `handoff` is the qualified `<sender domain>.<handoff name>`."""


class LocalTransport(HandoffTransport):
    """Receiving domains served by Executions in this process."""

    def __init__(self, receivers: dict[str, Execution]):
        self.receivers = dict(receivers)

    def deliver(self, domain, handoff, action, target, params, handoff_id, origin):
        ex = self.receivers.get(domain)
        if ex is None:
            raise LookupError(f"no receiver for domain {domain!r}")
        return ex.receive_handoff(handoff, action, target, params, handoff_id, origin)


EFFECT_PREFIX = "effect:"


@dataclass(frozen=True)
class Pending:
    id: str
    event: Event
    kind: str = "handoff"       # handoff | effect

    @property
    def stream(self) -> str:
        return (RESOLUTION_PREFIX if self.kind == "handoff" else EFFECT_PREFIX) + self.id


def pending_of(e: Event) -> Pending:
    return (Pending(handoff_id(e), e, "handoff") if e.type == "HandoffRequested"
            else Pending(effect_id(e), e, "effect"))


def handoff_id(e: Event) -> str:
    return f"{e.payload['handoff']}:{e.stream}@{e.version}"


def effect_id(e: Event) -> str:
    return f"{e.payload['service']}:{e.stream}@{e.version}"


class Outbox:
    """The domain's outbox (step 12): handoffs (ADR-0024) and kernel-service calls (ADR-0028).
    Each entry gets exactly one resolution, in its own stream, so nothing is sent twice and the
    sender's objects never change version because of it."""

    def __init__(self, ex: Execution):
        self.ex = ex

    def pending(self, kind: str | None = "handoff") -> list[Pending]:
        store = self.ex.store
        out = []
        for stream in store.streams():
            if stream.startswith((RESOLUTION_PREFIX, EFFECT_PREFIX)):
                continue
            for e in store.read(stream):
                if e.kind != "outbox":
                    continue
                p = (Pending(handoff_id(e), e, "handoff") if e.type == "HandoffRequested"
                     else Pending(effect_id(e), e, "effect"))
                if (kind is None or p.kind == kind) and store.version(p.stream) == 0:
                    out.append(p)
        return out

    def resolution(self, oid: str, kind: str = "handoff") -> Event | None:
        evs = self.ex.store.read(Pending(oid, None, kind).stream)   # type: ignore[arg-type]
        return evs[0] if evs else None

    def process(self, p: Pending, transport: HandoffTransport | None, services: Any) -> tuple[dict[str, Any] | None, list[Event]]:
        """Send one entry if its channel is configured and it is still unresolved. Returns its
        report entry (None if not sent) and the events a kernel reply produced in this domain,
        whose own outbox entries come next."""
        if self.ex.store.version(p.stream) != 0:
            return None, []
        if p.kind == "handoff":
            return (self._handoff(p, transport), []) if transport is not None else (None, [])
        if services is None:
            return None, []
        self._follow: list[Event] = []
        rep = self._effect(p, services)
        return rep, self._follow

    def dispatch(self, transport: HandoffTransport | None = None, services: Any = None) -> list[dict[str, Any]]:
        """Send every pending entry once: handoffs through `transport`, kernel calls through
        `services`. An entry whose channel is missing stays pending. Returns what happened."""
        report = []
        for p in self.pending(kind=None):
            if p.kind == "handoff" and transport is not None:
                report.append(self._handoff(p, transport))
            elif p.kind == "effect" and services is not None:
                report.append(self._effect(p, services))
        return report

    def _handoff(self, p: Pending, transport: HandoffTransport) -> dict[str, Any]:
        pl = p.event.payload
        if pl.get("error"):
            return self._resolve(p, "HandoffFailed", {"code": "mapping-error", "reason": pl["error"]})
        try:
            o = transport.deliver(pl["to"]["domain"], f"{self.ex.d.domain}.{pl['handoff']}", pl["to"]["action"],
                                  pl["target"], pl["params"], p.id, pl.get("origin"))
        except Exception as e:   # the receiver is unreachable: stays pending, retried later
            return {"id": p.id, "result": "pending", "reason": f"{type(e).__name__}: {e}"}
        detail = {"status": o.status, "code": o.code, "reason": o.reason}
        if o.status == "rejected" and o.code in TRANSIENT:
            return {"id": p.id, "result": "pending", "reason": o.reason}
        etype = {"ok": "HandoffDelivered", "denied": "HandoffDenied"}.get(o.status, "HandoffFailed")
        return self._resolve(p, etype, detail)

    def _effect(self, p: Pending, services: Any) -> dict[str, Any]:
        from ..kernel import CATALOG
        pl = p.event.payload
        svc = CATALOG[pl["service"]]
        result = (svc.failure(f"mapping-error: {pl['error']}") if pl.get("error")
                  else services.call(pl["service"], pl["inputs"], caller=p.event.actor))
        reply = self.ex.d.actions[pl["reply"]]
        params = {k: result[k] for k in reply.params if k in result}
        if reply.creates is not None:
            # A creating reply (ADR-0029) makes the object the service named; nothing to make on
            # failure, and an object that already exists (the same commit again) is not an error.
            if not result["ok"] or not result.get("id"):
                return self._resolve(p, "EffectFailed", {"service": pl["service"], "result": result,
                                                        "reply": pl["reply"], "status": "skipped",
                                                        "code": None, "reason": result.get("error")})
            if self.ex.lookup(result["id"]) is not None:
                return self._resolve(p, "EffectSucceeded", {"service": pl["service"], "result": result,
                                                           "reply": pl["reply"], "status": "ok",
                                                           "code": "unchanged", "reason": None})
            o = self.ex.receive_kernel_reply(p.id, pl["reply"], result["id"], params)
        else:
            o = self.ex.receive_kernel_reply(p.id, pl["reply"], p.event.stream, params)
        self._follow = list(o.events)
        if o.status == "rejected" and o.code in TRANSIENT:
            return {"id": p.id, "result": "pending", "reason": o.reason}
        detail = {"service": pl["service"], "result": result, "reply": pl["reply"],
                  "status": o.status, "code": o.code, "reason": o.reason}
        return self._resolve(p, "EffectSucceeded" if result["ok"] else "EffectFailed", detail)

    def _resolve(self, p: Pending, etype: str, detail: dict[str, Any]) -> dict[str, Any]:
        e = p.event
        head = ({"handoff": e.payload["handoff"], "to": e.payload["to"], "target": e.payload["target"]}
                if p.kind == "handoff" else {})
        ev = Event(etype, p.stream, e.aggregate, at=self.ex.clock(), actor=None, kind="handoff",
                   payload={**head, "object": e.stream, **detail},
                   domain_version=self.ex.d.version, causation=p.id)
        try:
            self.ex.store.append(p.stream, 0, [ev])
        except ConcurrencyError:
            # Another dispatcher resolved it first: its record stands, and is what we report.
            stored = self.ex.store.read(p.stream)
            if stored:
                etype = stored[0].type
                detail = {k: stored[0].payload.get(k) for k in ("status", "code", "reason") if k in stored[0].payload}
        return {"id": p.id, "result": etype, **detail}


__all__ = ["EFFECT_PREFIX", "HandoffTransport", "LocalTransport", "Outbox", "Pending", "effect_id", "handoff_id"]
