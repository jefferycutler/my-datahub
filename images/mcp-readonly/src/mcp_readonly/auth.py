"""Bearer-token authentication as pure ASGI middleware.

One token per client (MCP_TOKEN_<NAME> env vars) so a client can be revoked on
its own and audit logs show who made each call.
"""
import hmac
import logging
import os

from .common import client_var

log = logging.getLogger("mcp_readonly.auth")

PREFIX = "MCP_TOKEN_"


def load_tokens(environ=None) -> dict[str, str]:
    environ = os.environ if environ is None else environ
    tokens = {
        key[len(PREFIX):].lower(): val
        for key, val in environ.items()
        if key.startswith(PREFIX) and val
    }
    if not tokens:
        raise RuntimeError(f"no {PREFIX}* tokens configured; refusing to start unauthenticated")
    return tokens


def match_client(authorization: str, tokens: dict[str, str]) -> str | None:
    """Return the client name for a valid 'Bearer <token>' header, else None."""
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented.strip():
        return None
    presented_b = presented.strip().encode()
    found = None
    for name, token in tokens.items():  # no early exit: keep timing uniform
        if hmac.compare_digest(presented_b, token.encode()):
            found = name
    return found


class BearerAuth:
    def __init__(self, app, tokens: dict[str, str]):
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        client = match_client(headers.get(b"authorization", b"").decode("latin-1"), self.tokens)
        if client is None:
            peer = (scope.get("client") or ("-", 0))[0]
            fwd = headers.get(b"x-forwarded-for", b"").decode("latin-1")
            log.warning("auth failed path=%s peer=%s xff=%s", scope["path"], peer, fwd)
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b"Bearer"),
                ],
            })
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return

        reset = client_var.set(client)
        try:
            await self.app(scope, receive, send)
        finally:
            client_var.reset(reset)
