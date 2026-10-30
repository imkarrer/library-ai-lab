"""Acknowledge, the chime, and the Counselor's stream (ADR-0010, `library_assistant.alarms`).

The Librarian or a Stand-in Acknowledges a high-severity Flag's Alarm; a Counselor
Acknowledges the Alarm an Escalated Flag sounds on their page. Either records the
account and the time and silences the Alarm on every page; neither closes the Flag.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from library_assistant.access import get_clock, get_db
from library_assistant.alarms import (
    ESCALATED,
    SILENCED,
    acknowledge_escalation,
    acknowledge_flag,
)
from library_assistant.chime import chime_wav
from library_assistant.routers.live import (
    LiveBus,
    event_stream,
    get_live_bus,
    get_ping_wait,
)
from library_assistant.staff import StaffAccount, StaffDep, StandInDep, require_role

router = APIRouter(prefix="/staff")

CounselorDep = Annotated[StaffAccount, Depends(require_role("counselor"))]

NO_STORE = {"Cache-Control": "no-store"}


@router.get("/alarm/chime.wav")
def chime(account: StaffDep) -> Response:
    """The Alarm chime, made by the assistant itself: never fetched from anywhere."""
    return Response(chime_wav(), media_type="audio/wav")


@router.post("/alarms/{flag_id}/acknowledge")
def acknowledge_route(
    flag_id: int,
    account: StandInDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    bus: LiveBus = Depends(get_live_bus),
) -> JSONResponse:
    """I'm on it: records the Acknowledgement and silences any Alarm everywhere. The
    Flag stays open until it is closed."""
    silenced = acknowledge_flag(db, bus.publish, flag_id, account.id, clock)
    if silenced is None:
        raise HTTPException(status_code=404, detail="no open Flag to acknowledge")
    return JSONResponse(silenced, headers=NO_STORE)


@router.post("/counselor/alarms/{flag_id}/acknowledge")
def acknowledge_escalation_route(
    flag_id: int,
    account: CounselorDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    bus: LiveBus = Depends(get_live_bus),
) -> JSONResponse:
    """The Counselor's I'm on it, for an Escalated Flag's Alarm."""
    silenced = acknowledge_escalation(db, bus.publish, flag_id, account.id, clock)
    if silenced is None:
        raise HTTPException(status_code=404, detail="no Escalated Flag")
    return JSONResponse(silenced, headers=NO_STORE)


def counselor_may_hear(kind: str, data: dict) -> bool:
    """A Counselor sees only Escalated Flags (lib-f24.7): their stream carries the
    Escalation Alarm and its silencing, nothing else on the bus."""
    return kind == ESCALATED or (kind == SILENCED and bool(data.get("escalation")))


@router.get("/counselor/events")
async def counselor_events(
    account: CounselorDep,
    bus: LiveBus = Depends(get_live_bus),
    wait: Callable[[], Awaitable[None]] = Depends(get_ping_wait),
) -> StreamingResponse:
    """The Counselor page's server-sent event stream: Escalations only."""
    queue = bus.subscribe()
    return StreamingResponse(
        event_stream(bus, queue, wait, counselor_may_hear),
        media_type="text/event-stream",
        headers=NO_STORE,
    )
