"""The Identity port (ADR-0016): credentials in, a resolved caller out.

Toprope does not manage accounts. The host's identity provider issues credentials, and an
adapter resolves them into an actor, and for agents also a principal and a grant. M0a ships a
static adapter for tests and local use, and a JWT adapter (identity/jwt.py) for the server.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..types import Actor, Grant


@dataclass(frozen=True)
class Caller:
    actor: Actor
    on_behalf_of: Actor | None = None
    grant: Grant | None = None

    def __post_init__(self) -> None:
        a = self.actor
        p = self.on_behalf_of
        if p is not None and (p.id == "system" or p.id.startswith(("external:", "handoff:"))
                              or any(r == "system" or r.startswith("external:") for r in p.roles)):
            raise ValueError("a principal is a person, never a reserved actor (system, external:*, handoff:*)")
        for who in (a, self.on_behalf_of):
            if who is not None and (not isinstance(who.id, str) or not who.id
                                    or not all(isinstance(r, str) for r in who.roles)):
                raise ValueError("actor ids and roles are non-empty strings")
        if a.kind not in ("person", "agent"):
            raise ValueError(f"a caller is a person or an agent, not {a.kind!r}")
        if a.kind == "system" or a.id == "system" or a.id.startswith(("external:", "handoff:")) \
                or any(r == "system" or r.startswith("external:") for r in a.roles):
            raise ValueError("credentials never resolve to a reserved actor (system, external:*, handoff:*)")
        if a.kind == "person" and (self.on_behalf_of is not None or self.grant is not None):
            raise ValueError("a person acts for themselves: no principal or grant")
        if a.kind == "agent" and (self.on_behalf_of is None or self.grant is None):
            raise ValueError("an agent caller needs a principal and a grant (ADR-0016)")
        if self.on_behalf_of is not None and self.on_behalf_of.kind != "person":
            raise ValueError("a principal must be a person (ADR-0021)")


def str_list(v: object, what: str) -> tuple[str, ...]:
    """A claim or config value that must be a list of strings (a bare string is refused, so
    "admin" never becomes the roles a, d, m, i, n)."""
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ValueError(f"{what} must be a list of strings")
    return tuple(v)


class Identity(ABC):
    @abstractmethod
    def resolve(self, credentials: str | None) -> Caller | None:
        """Return the caller, or None if the credentials are missing, unknown or expired."""


class StaticIdentity(Identity):
    """Token → caller table. For tests and single-user local runs only."""

    def __init__(self, callers: dict[str, Caller]):
        self._callers = dict(callers)

    def resolve(self, credentials: str | None) -> Caller | None:
        return self._callers.get(credentials) if credentials else None


__all__ = ["Caller", "Identity", "StaticIdentity", "str_list"]
