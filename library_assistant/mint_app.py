"""Make Cards, as an app the assistant serves (ADR-0002 addendum of 2026-10-30).

`/staff/mint/` is the offline Minting page, served to a signed-in Teacher or Librarian with
no Registration key in it: its requests go to this router's own routes, which know the
Teacher by their staff sign-in. Chrome and Edge offer to install it (the manifest, an icon,
a service worker), so it opens from the shelf, the Dock, or the Start menu like an app, with
nothing downloaded and nothing for IT to approve. Tokens are still made in the Teacher's
browser, and only their hashes arrive here; the Rosters stay in that browser.

The page carries a Content-Security-Policy that lets it run only its own two scripts (by
hash) and send requests only to this assistant, so the published hashes are the check that
the page a Teacher runs is the page in the repo.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import struct
import zlib
from datetime import datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from library_assistant.access import BatchCards, get_clock, get_db, register_cards
from library_assistant.config import Settings, get_settings
from library_assistant.minting_page import with_install_config
from library_assistant.staff import MINTING_ROLES, StaffAccount, StaffDep
from library_assistant.tls import TLS_NAMES_ENV, ca_cert_path

APP_PATH = "/staff/mint"
router = APIRouter(prefix=APP_PATH)

GREEN = (0x24, 0x53, 0x3F)
PAPER = (0xFA, 0xF6, 0xEC)
BRASS = (0xB0, 0x8A, 0x3E)
ICON_SIZES = (192, 512)

# What the app adds to the shipped page's <head>; the page itself is unchanged.
APP_HEAD = (
    '<link rel="manifest" href="manifest.webmanifest">\n'
    '    <link rel="icon" href="icon-192.png">\n'
    '    <link rel="apple-touch-icon" href="icon-192.png">\n'
    '    <meta name="theme-color" content="#24533f">\n'
    "</head>"
)

_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", re.DOTALL)


def _minter(account: StaffDep) -> StaffAccount:
    if account.role not in MINTING_ROLES:
        raise HTTPException(status_code=403, detail="a Counselor does not make Cards")
    return account


MinterDep = Annotated[StaffAccount, Depends(_minter)]


def script_hashes(page: str) -> list[str]:
    """The CSP hash of each inline script the page runs (a JSON data block runs nothing)."""
    return [
        "sha256-"
        + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
        for attrs, body in _SCRIPT_RE.findall(page)
        if "application/json" not in attrs
    ]


def content_security_policy(page: str) -> str:
    scripts = " ".join(f"'{h}'" for h in script_hashes(page))
    return (
        "default-src 'none'; "
        f"script-src {scripts}; "
        "style-src 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )


def card_base_url(request: Request) -> str:
    """The address Cards carry: the one the assistant listens on, so Cards made from
    `localhost` on the assistant's own computer still open on a phone. Falls back to the
    address the page was opened at when the assistant listens on a loopback or every
    address."""
    host = os.environ.get("LIBRARY_ASSISTANT_HOST", "")
    names = [n.strip() for n in os.environ.get(TLS_NAMES_ENV, "").split(",") if n]
    https = ca_cert_path() is not None
    if https and names:
        host = names[0]
    try:
        address = ipaddress.ip_address(host)
        if address.is_loopback or address.is_unspecified:
            host = ""
    except ValueError:
        if host in ("", "localhost"):
            host = ""
    if not host:
        return str(request.base_url).rstrip("/")
    scheme = "https" if https else "http"
    port = os.environ.get("LIBRARY_ASSISTANT_PORT", "8000")
    shown = f"[{host}]" if ":" in host else host
    return f"{scheme}://{shown}:{port}"


def _demo_class(settings: Settings) -> dict[str, object]:
    """The demo stack's fictional class, prefilled (`./stack up` sets it). Only with
    LIBRARY_ASSISTANT_DEMO: a school's assistant never holds a name (ADR-0002)."""
    if not settings.demo or not settings.demo_class:
        return {}
    label, *names = [part.strip() for part in settings.demo_class.split("|")]
    return {"class_label": label, "class_list": [n for n in names if n]}


def app_page(
    assistant_url: str,
    username: str,
    school_day_end: str | None = None,
    demo_class: dict[str, object] | None = None,
) -> str:
    page = with_install_config(
        {
            "app": APP_PATH,
            "assistant_url": assistant_url,
            "username": username,
            **({"school_day_end": school_day_end} if school_day_end else {}),
            **(demo_class or {}),
        }
    )
    # The first </head> is the page's own; later ones are in its print templates.
    if not 0 < page.find("</head>") < page.find("<body>"):
        raise RuntimeError("the Minting page has lost its </head>")
    return page.replace("</head>", APP_HEAD, 1)


@router.get("/")
def make_cards_app(
    request: Request,
    account: MinterDep,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    page = app_page(
        card_base_url(request),
        account.username,
        settings.school_day_end,
        _demo_class(settings),
    )
    return HTMLResponse(
        page,
        headers={
            "Content-Security-Policy": content_security_policy(page),
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/manifest.webmanifest")
def manifest() -> Response:
    """Public, like any manifest: the browser fetches it without the sign-in cookie."""
    icons = [
        {
            "src": f"{APP_PATH}/icon-{size}.png",
            "sizes": f"{size}x{size}",
            "type": "image/png",
            "purpose": "any",
        }
        for size in ICON_SIZES
    ]
    icons.append({**icons[-1], "purpose": "maskable"})
    body = {
        "id": f"{APP_PATH}/",
        "name": "Make Cards · Library Assistant",
        "short_name": "Make Cards",
        "description": "Make your class's Library Assistant Cards. Names stay on this "
        "computer.",
        "start_url": f"{APP_PATH}/",
        "scope": f"{APP_PATH}/",
        "display": "standalone",
        "background_color": "#faf6ec",
        "theme_color": "#24533f",
        "icons": icons,
    }
    return Response(json.dumps(body), media_type="application/manifest+json")


# Network first, so the app is always the assistant's current page; the kept copy opens
# it when the assistant can't be reached, for Find a Card. A sign-in page or an error is
# never kept in place of the app.
SERVICE_WORKER = f"""const CACHE = 'make-cards-v1';
const PAGE = '{APP_PATH}/';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {{
  const request = event.request;
  if (request.method !== 'GET' || request.mode !== 'navigate') return;
  event.respondWith(fetch(request).then(response => {{
    if (response.ok && !response.redirected) {{
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(PAGE, copy));
    }}
    return response;
  }}).catch(() => caches.match(PAGE).then(kept => kept || Response.error())));
}});
"""


@router.get("/sw.js")
def service_worker() -> Response:
    return Response(
        SERVICE_WORKER,
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


def _png(size: int, pixel) -> bytes:
    rows = b"".join(
        b"\x00" + b"".join(bytes(pixel(x / size, y / size)) for x in range(size))
        for y in range(size)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


# A Card with a QR code on it, inside the maskable safe zone.
_QR = ("111.111", "1.1.1.1", "111.111", "...1...", "111.1.1", "1.1..1.", "111.1.1")


def _icon_pixel(x: float, y: float) -> tuple[int, int, int]:
    if not (0.30 <= x < 0.70 and 0.24 <= y < 0.76):
        return GREEN
    if 0.36 <= x < 0.64 and 0.64 <= y < 0.69:
        return BRASS
    if 0.36 <= x < 0.64 and 0.30 <= y < 0.58:
        column, row = int((x - 0.36) / 0.04), int((y - 0.30) / 0.04)
        if _QR[min(row, 6)][min(column, 6)] == "1":
            return GREEN
    return PAPER


@lru_cache(maxsize=len(ICON_SIZES))
def icon_png(size: int) -> bytes:
    return _png(size, _icon_pixel)


@router.get("/icon-{size}.png")
def icon(size: int) -> Response:
    if size not in ICON_SIZES:
        raise HTTPException(status_code=404)
    return Response(
        icon_png(size),
        media_type="image/png",
        headers={"Cache-Control": "max-age=86400"},
    )


@router.post("/batches", status_code=201)
def register_from_app(
    batch: BatchCards,
    account: MinterDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> dict[str, int]:
    """Registration, as `/batches`, for the Teacher signed in rather than a key's."""
    return register_cards(db, account.id, batch, clock, settings)


@router.post("/batches/identification-requests")
def app_identification_requests(
    account: MinterDep,
    db: sqlite3.Connection = Depends(get_db),
) -> dict[str, list[dict]]:
    from library_assistant.identification import open_requests_for

    return {"requests": [r.for_teacher() for r in open_requests_for(db, account.id)]}


class AppAnswer(BaseModel):
    answer: str


@router.post("/batches/identification-requests/{request_id}/answer")
def app_identification_answer(
    request_id: int,
    body: AppAnswer,
    account: MinterDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> dict[str, str]:
    from library_assistant.identification import answer

    if answer(db, request_id, account.id, body.answer, clock) is None:
        raise HTTPException(status_code=404, detail="no open request of yours")
    return {"status": "answered"}
