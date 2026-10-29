"""Start watch, heartbeat, and End watch for the Install's one Watch (ADR-0010).

The Live view's event stream (`/staff/live/events`) sends a ping every 20 s; a page answers
each with POST /staff/watch/heartbeat. See `docs/design/watch.md`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from library_assistant.access import NO_STORE, get_clock, get_db
from library_assistant.alarms import unacknowledged_alarms
from library_assistant.config import Settings
from library_assistant.dependencies import get_settings
from library_assistant.staff import StaffDep, StandInDep
from library_assistant.watch import end_watch, heartbeat, start_watch, watchers_count

router = APIRouter(prefix="/staff/watch")


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
    """The Librarian or a Stand-in goes on Watch; anyone else gets 403. The answer
    carries every unacknowledged high-severity Alarm, which the page sounds before
    anything else (ADR-0010, "Replay")."""
    start_watch(db, account.id, clock)
    return JSONResponse(
        {"watching": True, "alarms": unacknowledged_alarms(db)}, headers=NO_STORE
    )


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
async def end_watch_route(
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """This account stops watching; the Watch stays on while anyone else is watching.

    If this is the last watcher, wait for in-flight Oversight screens to complete before
    ending the watch.
    """
    # Check if this is the last watcher
    if watchers_count(db) == 1:
        # Wait for in-flight screens to settle
        from library_assistant.routers.session import screens_settled

        await screens_settled(settings.oversight_timeout_seconds)

    end_watch(db, account.id)
    return _watching(False)
