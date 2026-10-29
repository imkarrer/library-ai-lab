"""Start watch, heartbeat, and End watch for the Install's one Watch (ADR-0010).

The Live view's event stream (`/staff/live/events`) sends a ping every 20 s; a page answers
each with POST /staff/watch/heartbeat. See `docs/design/watch.md`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from library_assistant.access import get_clock, get_db
from library_assistant.staff import StaffDep, StandInDep
from library_assistant.watch import end_watch, heartbeat, start_watch

router = APIRouter(prefix="/staff/watch")

NO_STORE = {"Cache-Control": "no-store"}


def _watching(watching: bool, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        {"watching": watching}, status_code=status_code, headers=NO_STORE
    )


@router.post("/start")
def start_watch_route(
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> JSONResponse:
    """The Librarian or a Stand-in goes on Watch; anyone else gets 403."""
    start_watch(db, account.id, clock)
    return _watching(True)


@router.post("/heartbeat")
def heartbeat_route(
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> JSONResponse:
    """Keeps this account's Watch on; 409 when it is not on (ended or lapsed)."""
    if heartbeat(db, account.id, clock):
        return _watching(True)
    return _watching(False, status_code=409)


@router.post("/end")
def end_watch_route(
    account: StaffDep, db: sqlite3.Connection = Depends(get_db)
) -> JSONResponse:
    """This account stops watching; the Watch stays on while anyone else is watching."""
    end_watch(db, account.id)
    return _watching(False)
