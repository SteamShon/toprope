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
        """Issue the command in the receiving domain as `system` (`handoff:<name>`)."""


class LocalTransport(HandoffTransport):
    """Receiving domains served by Executions in this process."""

    def __init__(self, receivers: dict[str, Execution]):
        self.receivers = dict(receivers)

    def deliver(self, domain, handoff, action, target, params, handoff_id, origin):
        ex = self.receivers.get(domain)
        if ex is None:
            raise LookupError(f"no receiver for domain {domain!r}")
        return ex.receive_handoff(handoff, action, target, params, handoff_id, origin)


@dataclass(frozen=True)
class Pending:
    id: str
    event: Event


def handoff_id(e: Event) -> str:
    return f"{e.payload['handoff']}:{e.stream}@{e.version}"


class Outbox:
    def __init__(self, ex: Execution):
        self.ex = ex

    def pending(self) -> list[Pending]:
        store = self.ex.store
        out = []
        for stream in store.streams():
            if stream.startswith(RESOLUTION_PREFIX):
                continue
            for e in store.read(stream):
                if e.kind == "outbox":
                    hid = handoff_id(e)
                    if store.version(RESOLUTION_PREFIX + hid) == 0:
                        out.append(Pending(hid, e))
        return out

    def resolution(self, hid: str) -> Event | None:
        evs = self.ex.store.read(RESOLUTION_PREFIX + hid)
        return evs[0] if evs else None

    def dispatch(self, transport: HandoffTransport) -> list[dict[str, Any]]:
        """Send every pending handoff once. Returns what happened to each."""
        report = []
        for p in self.pending():
            pl = p.event.payload
            if pl.get("error"):
                report.append(self._resolve(p, "HandoffFailed", {"code": "mapping-error", "reason": pl["error"]}))
                continue
            try:
                o = transport.deliver(pl["to"]["domain"], pl["handoff"], pl["to"]["action"], pl["target"],
                                      pl["params"], p.id, pl.get("origin"))
            except Exception as e:   # the receiver is unreachable: stays pending, retried later
                report.append({"id": p.id, "result": "pending", "reason": f"{type(e).__name__}: {e}"})
                continue
            detail = {"status": o.status, "code": o.code, "reason": o.reason}
            if o.status == "rejected" and o.code in TRANSIENT:
                report.append({"id": p.id, "result": "pending", "reason": o.reason})
            elif o.status == "ok":
                report.append(self._resolve(p, "HandoffDelivered", detail))
            elif o.status == "denied":
                report.append(self._resolve(p, "HandoffDenied", detail))
            else:
                report.append(self._resolve(p, "HandoffFailed", detail))
        return report

    def _resolve(self, p: Pending, etype: str, detail: dict[str, Any]) -> dict[str, Any]:
        e = p.event
        ev = Event(etype, RESOLUTION_PREFIX + p.id, e.aggregate, at=self.ex.clock(), actor=None, kind="handoff",
                   payload={"handoff": e.payload["handoff"], "object": e.stream, "to": e.payload["to"],
                            "target": e.payload["target"], **detail},
                   domain_version=self.ex.d.version, causation=p.id)
        try:
            self.ex.store.append(RESOLUTION_PREFIX + p.id, 0, [ev])
        except ConcurrencyError:
            pass    # another dispatcher resolved it first; its record stands
        return {"id": p.id, "result": etype, **detail}


__all__ = ["HandoffTransport", "LocalTransport", "Outbox", "Pending", "handoff_id"]
