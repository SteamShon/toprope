"""Streamable HTTP with per-request bearer tokens resolved through the Identity port."""

from __future__ import annotations

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


def build_http_app(ex: Execution, base_url: str):
    def credentials() -> str | None:
        tok = get_access_token()
        return tok.token if tok else None

    server = build_server(ex, credentials, token_verifier=IdentityTokenVerifier(ex),
                          # The Identity port validates tokens (JWT audience/issuer included), so
                          # the SDK's resource check is not used.
                          auth=AuthSettings(issuer_url=base_url, resource_server_url=f"{base_url}/mcp",
                                            validate_token_resource=False))
    return server.streamable_http_app()


def run_http(ex: Execution, host: str, port: int) -> None:
    import uvicorn
    uvicorn.run(build_http_app(ex, f"http://{host}:{port}"), host=host, port=port)
