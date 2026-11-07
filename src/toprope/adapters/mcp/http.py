"""Streamable HTTP with per-request bearer tokens resolved through the Identity port."""

from __future__ import annotations

from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from ...exec import Execution
from . import build_server


class IdentityTokenVerifier:
    """Accepts a bearer token only if the Identity port resolves it to a caller."""

    def __init__(self, ex: Execution):
        self.ex = ex

    async def verify_token(self, token: str) -> AccessToken | None:
        caller = self.ex.identity.resolve(token)
        if caller is None:
            return None
        return AccessToken(token=token, client_id=caller.actor.id, scopes=[], subject=caller.actor.id)


def build_http_app(ex: Execution, public_url: str, issuer_url: str | None = None,
                   harness: dict | None = None, sources: Any = None):
    """`public_url` is where clients reach this server (it names the protected resource).
    `issuer_url` is the identity provider that issues the tokens; it defaults to `public_url`
    only for identities with no external issuer (static tokens)."""
    def credentials() -> str | None:
        tok = get_access_token()
        return tok.token if tok else None

    base = public_url.rstrip("/")
    server = build_server(ex, credentials, harness=harness, sources=sources, token_verifier=IdentityTokenVerifier(ex),
                          # The Identity port validates tokens (JWT audience/issuer included), so
                          # the SDK's resource check is not used.
                          auth=AuthSettings(issuer_url=issuer_url or base, resource_server_url=f"{base}/mcp",
                                            validate_token_resource=False))
    return server.streamable_http_app()


def run_http(ex: Execution, host: str, port: int, public_url: str | None = None,
             issuer_url: str | None = None, harness: dict | None = None, sources: Any = None) -> None:
    import uvicorn
    uvicorn.run(build_http_app(ex, public_url or f"http://{host}:{port}", issuer_url, harness, sources),
                host=host, port=port)
