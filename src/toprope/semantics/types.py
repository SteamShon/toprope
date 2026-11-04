"""Commands, actors, grants, events and outcomes (docs/semantics.md §1, §5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class Actor:
    id: str
    kind: Literal["person", "agent", "system"] = "person"
    roles: tuple[str, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)

    def as_env(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "roles": list(self.roles),
                "role": self.roles[0] if self.roles else None, **self.attrs}

    def ref(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind}


@dataclass(frozen=True)
class Grant:
    """What an agent may do on behalf of a principal (ADR-0016)."""

    id: str
    actions: frozenset[str]
    targets: frozenset[str] | None = None   # None: any target
    expires_at: datetime | None = None


@dataclass(frozen=True)
class Command:
    actor: Actor | None
    action: str
    target: str | None
    params: dict[str, Any] = field(default_factory=dict, hash=False)
    idempotency_key: str | None = None
    at: datetime | None = None
    on_behalf_of: Actor | None = None
    grant: Grant | None = None
    thread_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class Event:
    type: str
    stream: str                 # aggregate id
    aggregate: str              # object type
    at: datetime | None
    actor: dict[str, Any] | None
    payload: dict[str, Any]
    kind: Literal["domain", "decision", "attempt"] = "domain"
    version: int | None = None  # set on append for domain/decision events
    domain_version: int | None = None
    on_behalf_of: dict[str, Any] | None = None
    grant: str | None = None
    thread_id: str | None = None
    run_id: str | None = None


Status = Literal["ok", "denied", "rejected", "pending"]


@dataclass(frozen=True)
class Outcome:
    status: Status
    code: str | None = None          # matrix | actor | not-applicable | undecided | <precondition id> | ...
    reason: str | None = None
    state: dict[str, Any] | None = None
    events: tuple[Event, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "ok"
