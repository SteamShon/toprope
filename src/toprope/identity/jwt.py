"""JWT identity adapter (ADR-0016). The host's identity provider issues the tokens.

Claims:
  sub          actor id (a string)
  kind         "person" (default) or "agent"
  roles        list of role names
  act          for agents: the principal, {"sub": ..., "roles": [...]} (RFC 8693 actor claim)
  grant        for agents: {"id": ..., "actions": [...], "targets": [...] | null, "exp": <epoch>}

Always verified: the signature with the configured key and algorithms ("none" is refused),
`exp`, and `aud` (an audience is required, so a token minted for another service is refused).
`iss` is verified when an issuer is configured.
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt

from ..types import Actor, Grant
from . import Caller, Identity, str_list
from ..errors import fixed


class JWTIdentity(Identity):
    def __init__(self, key: str, *, audience: str, algorithms: list[str] | None = None,
                 issuer: str | None = None):
        if not key:
            raise ValueError(fixed("a JWT key is required", "give the identity the key the tokens are signed with"))
        if not audience:
            raise ValueError(fixed("a JWT audience is required",
                                   "give the identity the audience the tokens are issued for"))
        self._alg = algorithms or ["HS256"]
        if not self._alg or any(not a or a.lower() == "none" for a in self._alg):
            raise ValueError(fixed("unsigned JWTs (alg none) are never accepted",
                                   "name a signing algorithm, such as HS256"))
        self._key = key
        self._aud = audience
        self._iss = issuer or None

    def resolve(self, credentials: str | None) -> Caller | None:
        if not credentials:
            return None
        try:
            c = jwt.decode(credentials, self._key, algorithms=self._alg, audience=self._aud,
                           issuer=self._iss, options={"require": ["sub", "exp", "aud"]})
            return self._caller(c)
        except (jwt.PyJWTError, KeyError, TypeError, ValueError, AttributeError, OverflowError, OSError):
            return None   # invalid, expired, malformed, or a reserved/inconsistent caller

    @staticmethod
    def _caller(c: dict) -> Caller:
        def sub(d: dict) -> str:
            if not isinstance(d.get("sub"), str):
                raise ValueError(fixed("sub must be a string", "issue the token with `sub` as the caller's id"))
            return d["sub"]

        kind = c.get("kind", "person")
        actor = Actor(sub(c), kind, str_list(c.get("roles", []), "roles"))
        if kind != "agent":
            return Caller(actor)
        act, g = c.get("act"), c.get("grant")
        if not isinstance(act, dict) or not isinstance(g, dict) or not isinstance(g.get("id"), str):
            raise ValueError(fixed("an agent token needs act and grant objects",
                                   "issue the agent's token with `act` (its person) and `grant` claims"))
        principal = Actor(sub(act), "person", str_list(act.get("roles", []), "act.roles"))
        targets = g.get("targets")
        exp = g.get("exp")
        if exp is not None and (isinstance(exp, bool) or not isinstance(exp, (int, float))):
            raise ValueError(fixed("grant.exp must be a number",
                                   "issue the grant's `exp` as seconds since the epoch"))
        grant = Grant(g["id"], frozenset(str_list(g.get("actions", []), "grant.actions")),
                      None if targets is None else frozenset(str_list(targets, "grant.targets")),
                      None if exp is None else datetime.fromtimestamp(exp, timezone.utc))
        return Caller(actor, principal, grant)
