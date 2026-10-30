"""Start the assistant: `python -m library_assistant`.

The one start command, so the flags that matter are in code rather than remembered:

- No uvicorn access log: it writes the raw path and query, which could carry a Token or a
  Card number; the app keeps its own (ADR-0003 addendum).
- A two-second graceful shutdown: a Live view's event stream never ends on its own, so
  without a limit Ctrl-C waits for every open staff page to close.

`LIBRARY_ASSISTANT_HOST` (default 127.0.0.1) and `LIBRARY_ASSISTANT_PORT` (default 8000)
say where it listens; at the venue the host is the laptop's LAN address (ADR-0006).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

import uvicorn

GRACEFUL_SHUTDOWN_SECONDS = 2


def server_options(environ: Mapping[str, str] | None = None) -> dict[str, object]:
    environ = os.environ if environ is None else environ
    return {
        "host": environ.get("LIBRARY_ASSISTANT_HOST", "127.0.0.1"),
        "port": int(environ.get("LIBRARY_ASSISTANT_PORT", "8000")),
        "access_log": False,
        "timeout_graceful_shutdown": GRACEFUL_SHUTDOWN_SECONDS,
    }


def main() -> None:
    uvicorn.run("library_assistant.app:app", **server_options())


if __name__ == "__main__":
    main()
