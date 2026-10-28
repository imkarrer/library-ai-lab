"""The app's own access log (ADR-0003 addendum, "Other copies").

One line per request: method, the matched route's path template, status, and duration.
Never the raw path or query string, which could carry a Token or a Card number; a request
that matches no route is logged as `<unmatched>`. uvicorn's own access log, which writes the
raw path and query, is off in the shipped start command (`--no-access-log`).
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("library_assistant.access")

UNMATCHED = "<unmatched>"


def route_template(scope: Scope) -> str:
    """The path template of the route that handled this request, never the raw path."""
    route = scope.get("route")
    template = getattr(route, "path", None)
    return template if isinstance(template, str) else UNMATCHED


def configure() -> None:
    """Send access lines to stderr at INFO, since uvicorn configures only its own loggers."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
        logger.addHandler(handler)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


class AccessLogMiddleware:
    """Pure ASGI middleware, so a streamed answer is timed to its last byte."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s %d %.1fms",
                scope["method"],
                route_template(scope),
                status,
                duration_ms,
            )
