"""Lets the offline Minting page register a Batch (ADR-0002).

The page runs from a file:// URL on the Teacher's machine, so its POST to /batches is a
cross-origin request the browser blocks unless the assistant answers CORS. Only /batches
does: it authenticates with the Registration key in the body, never a cookie, so allowing
any origin without credentials gives a page nothing it could not already send. Every other
route, the staff pages and their session cookies included, stays same-origin.
"""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REGISTRATION_PATH = "/batches"

_ALLOW_ORIGIN = (b"access-control-allow-origin", b"*")


class RegistrationCorsMiddleware:
    """Pure ASGI middleware, like AccessLogMiddleware, scoped to REGISTRATION_PATH."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] != REGISTRATION_PATH:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if scope["method"] == "OPTIONS" and "access-control-request-method" in headers:
            preflight = [
                _ALLOW_ORIGIN,
                (b"access-control-allow-methods", b"POST"),
                (b"access-control-allow-headers", b"content-type"),
                (b"access-control-max-age", b"600"),
            ]
            # Chrome asks before a file:// page reaches a private (intranet) address.
            if headers.get("access-control-request-private-network") == "true":
                preflight.append((b"access-control-allow-private-network", b"true"))
            await send(
                {"type": "http.response.start", "status": 204, "headers": preflight}
            )
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_with_allow_origin(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), _ALLOW_ORIGIN]
            await send(message)

        await self.app(scope, receive, send_with_allow_origin)
