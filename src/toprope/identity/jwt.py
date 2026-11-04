"""JWT identity adapter (ADR-0016). The host's identity provider issues the tokens.

Claims:
  sub          actor id
  kind         "person" (default) or "agent"
  roles        list of role names
  act          for agents: the principal, {"sub": ..., "roles": [...]} (RFC 8693 actor claim)
  grant        for agents: {"id": ..., "actions": [...], "targets": [...] | null, "exp": <epoch>}
Standard `exp`, `aud` and `iss` are verified.
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt

from ..types import Actor, Grant
from . import Caller, Identity


class JWTIdentity(Identity):
    def __init__(self, key: str, *, algorithms: list[str] | None = None,
                 audience: str | None = None, issuer: str | None = None):
        self._key = key
        self._alg = algorithms or ["HS256"]
        self._aud = audience
        self._iss = issuer

    def resolve(self, credentials: str | None) -> Caller | None:
        if not credentials:
            return None
        try:
            c = jwt.decode(credentials, self._key, algorithms=self._alg, audience=self._aud,
                           issuer=self._iss, options={"require": ["sub", "exp"]})
            kind = c.get("kind", "person")
            actor = Actor(str(c["sub"]), kind, tuple(c.get("roles", [])))
            principal = grant = None
            if kind == "agent":
                act, g = c.get("act") or {}, c.get("grant") or {}
                principal = Actor(str(act["sub"]), "person", tuple(act.get("roles", [])))
                exp = g.get("exp")
                grant = Grant(str(g["id"]), frozenset(g.get("actions", [])),
                              None if g.get("targets") is None else frozenset(g["targets"]),
                              datetime.fromtimestamp(exp, timezone.utc) if exp else None)
            return Caller(actor, principal, grant)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            return None   # invalid, expired, malformed, or a reserved/inconsistent caller
