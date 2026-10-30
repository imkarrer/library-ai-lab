"""The Alarm and Acknowledge (ADR-0010, `docs/design/watch.md`).

A high-severity Flag that is not a repeat (decision lib-f24.66) sounds an Alarm on every
open staff page: the LiveBus carries an `alarm` event to each staff stream. Every new Flag,
low-severity too, adds a row to the Live view's Open Flags panel (`flag`, ADR-0010
amendment) and moves the open-Flag count (`flag_count`); closing one removes its row
(`flag_closed`). Acknowledge records which adult said
"I'm on it" and when, on the Flag itself, and sends `silenced` to every stream; it never
closes the Flag. An Escalated Flag sounds its own Alarm (`escalated`) on an open
Counselor page, Acknowledged there separately.

Every Flag, whatever its severity, moves raised -> acknowledged -> closed (ADR-0010
amendment, lib-msq): severity only sorts. Any open Flag can be Acknowledged, and closing
one nobody Acknowledged records the closer's Acknowledgement first, so someone's
interaction is always on record and a closed Flag never keeps ringing.

Binding: an Alarm carries the Flag's own fields and the registering Teacher's name
(ADR-0002 addendum), never the Student's words (ADR-0003) and never a Student. It goes
only to the open pages' streams, never off the Install (ADR-0006).

Every function takes `publish` (a LiveBus's `publish`) and times from the caller.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime

from library_assistant.access import registering_teacher
from library_assistant.flag_history import append_event
from library_assistant.flags import FlagRow, get_flag, open_flags
from library_assistant.install_settings import (
    ALARM_CHIME,
    ALARM_REPEAT_SECONDS,
    DEFAULT_ALARM_CHIME,
    DEFAULT_ALARM_REPEAT_SECONDS,
    DEFAULT_SUPERVISION_MODE,
    SUPERVISION_MODE,
    get_int_setting,
    get_setting,
)
from library_assistant.watch import is_watching

Publish = Callable[[str, dict], None]

# LiveBus event kinds.
ALARM = "alarm"
ESCALATED = "escalated"
SILENCED = "silenced"
FLAG_COUNT = "flag_count"
FLAG_RAISED = "flag"
FLAG_CLOSED = "flag_closed"


def alarm_payload(db: sqlite3.Connection, flag: FlagRow) -> dict:
    """What an Alarm shows: the Flag's own fields, never the exchange's text."""
    return {
        "flag_id": flag.id,
        "category": flag.category,
        "severity": flag.severity,
        "source": flag.source,
        "class_label": flag.class_label,
        "card_number": flag.card_number,
        "registered_by": registering_teacher(
            db, flag.class_label, flag.card_number, flag.batch_expires_at
        ),
        "raised_at": flag.raised_at,
        "raised_unwatched": bool(flag.raised_unwatched),
        "url": f"/staff/flags/{flag.id}",
    }


def escalation_payload(db: sqlite3.Connection, flag: FlagRow) -> dict:
    """The Counselor's Alarm: the same fields, linking to the Counselor's Flag page."""
    return {
        **alarm_payload(db, flag),
        "escalated_at": flag.escalated_at,
        "url": f"/staff/counselor/flags/{flag.id}",
    }


def session_no_for_transcript(db: sqlite3.Connection, transcript_id: int) -> int | None:
    """The Live view tile (sessions rowid) a Flag's exchange belongs to, while its
    Session still exists."""
    row = db.execute(
        "SELECT sessions.rowid FROM transcripts JOIN sessions "
        "ON sessions.session_hash = transcripts.session_hash WHERE transcripts.id = ?",
        (transcript_id,),
    ).fetchone()
    return row[0] if row else None


def session_flag_severity(db: sqlite3.Connection, session_no: int | None) -> str | None:
    """The highest open Flag severity on a Session's exchanges, for its tile's marker."""
    if session_no is None:
        return None
    severities = {
        row[0]
        for row in db.execute(
            "SELECT flags.severity FROM flags "
            "JOIN transcripts ON transcripts.id = flags.transcript_id "
            "JOIN sessions ON sessions.session_hash = transcripts.session_hash "
            "WHERE sessions.rowid = ? AND flags.closed_at IS NULL",
            (session_no,),
        )
    }
    if "high" in severities:
        return "high"
    return "low" if severities else None


def panel_payload(db: sqlite3.Connection, flag: FlagRow) -> dict:
    """An Open Flags panel row. The Live view is safe to share (docs/design/live-view.md):
    severity and who, never the category, the reason, or the Student's words."""
    session_no = session_no_for_transcript(db, flag.transcript_id)
    return {
        "flag_id": flag.id,
        "severity": flag.severity,
        "source": flag.source,
        "class_label": flag.class_label,
        "card_number": flag.card_number,
        "raised_at": flag.raised_at,
        "url": f"/staff/flags/{flag.id}",
        "session_no": session_no,
        "session_severity": session_flag_severity(db, session_no),
        "acknowledged": acknowledgement(db, flag.id) is not None,
        "escalated": flag.escalated_at is not None,
    }


def flag_stage(flag: FlagRow, acknowledged: bool) -> str:
    """New, Acknowledged, Closed (ADR-0010 amendment); an open Escalated Flag is the
    Counselor's to resolve (lib-6n9)."""
    if flag.closed_at is not None:
        return "Closed"
    if flag.escalated_at is not None:
        return "Escalated: the Counselor owns it"
    return "Acknowledged" if acknowledged else "New"


def open_flag_count(db: sqlite3.Connection) -> int:
    return db.execute("SELECT COUNT(*) FROM flags WHERE closed_at IS NULL").fetchone()[
        0
    ]


def announce_flag(
    db: sqlite3.Connection, publish: Publish, flag_id: int, is_repeat: bool
) -> None:
    """Tell the open staff pages about a Flag `raise_or_repeat` just returned. A repeat
    raised no new Flag, so it sounds nothing (decision lib-f24.66); a high-severity Flag
    sounds the Alarm; any new Flag moves the count."""
    if is_repeat:
        return
    flag = get_flag(db, flag_id)
    if flag is None:
        return
    if flag.severity == "high":
        publish(ALARM, alarm_payload(db, flag))
    publish(FLAG_RAISED, panel_payload(db, flag))
    publish(FLAG_COUNT, {"open": open_flag_count(db)})


def announce_flag_closed(
    db: sqlite3.Connection, publish: Publish, flag_id: int
) -> None:
    """A closed Flag leaves the Open Flags panel, and its tile's marker drops to what
    stays open on that Session."""
    flag = get_flag(db, flag_id)
    if flag is None:
        return
    session_no = session_no_for_transcript(db, flag.transcript_id)
    publish(
        FLAG_CLOSED,
        {
            "flag_id": flag.id,
            "session_no": session_no,
            "session_severity": session_flag_severity(db, session_no),
        },
    )
    publish(FLAG_COUNT, {"open": open_flag_count(db)})


def announce_flag_row(db: sqlite3.Connection, publish: Publish, flag_id: int) -> None:
    """A Flag's panel row changed (reopened, Escalated): the panel redraws it, without a
    second Alarm."""
    flag = get_flag(db, flag_id)
    if flag is None:
        return
    publish(FLAG_RAISED, panel_payload(db, flag))
    publish(FLAG_COUNT, {"open": open_flag_count(db)})


def announce_escalation(db: sqlite3.Connection, publish: Publish, flag_id: int) -> None:
    """An Escalated Flag reaches an open Counselor page (ADR-0010)."""
    flag = get_flag(db, flag_id)
    if flag is not None:
        publish(ESCALATED, escalation_payload(db, flag))


def _acknowledge(
    db: sqlite3.Connection,
    publish: Publish,
    flag_id: int,
    account_id: int,
    at: datetime,
    escalation: bool,
) -> dict:
    """Record the first Acknowledgement (a later one changes nothing) and silence the
    Alarm on every page."""
    prefix = "escalation_" if escalation else ""
    first = db.execute(
        f"UPDATE flags SET {prefix}acknowledged_at = ?, {prefix}acknowledged_by = ? "
        f"WHERE id = ? AND {prefix}acknowledged_at IS NULL",
        (at.isoformat(), account_id, flag_id),
    ).rowcount
    db.commit()
    acknowledged_at, username = db.execute(
        f"SELECT flags.{prefix}acknowledged_at, staff_accounts.username FROM flags "
        f"LEFT JOIN staff_accounts ON staff_accounts.id = flags.{prefix}acknowledged_by "
        "WHERE flags.id = ?",
        (flag_id,),
    ).fetchone()
    if first:
        append_event(
            db,
            flag_id,
            "acknowledged",
            at=at.isoformat(),
            account=username,
            reason="escalation" if escalation else None,
        )
    silenced = {
        "flag_id": flag_id,
        "escalation": escalation,
        "acknowledged_by": username,
        "acknowledged_at": acknowledged_at,
    }
    publish(SILENCED, silenced)
    return silenced


def acknowledge_flag(
    db: sqlite3.Connection,
    publish: Publish,
    flag_id: int,
    account_id: int,
    at: datetime,
) -> dict | None:
    """The Librarian or a Stand-in Acknowledges an open Flag of any severity: "I see it
    and I'm reviewing it". Silences its Alarm if it has one. None when the Flag does not
    exist or is already closed."""
    flag = get_flag(db, flag_id)
    if flag is None or flag.closed_at is not None:
        return None
    return _acknowledge(db, publish, flag_id, account_id, at, escalation=False)


def acknowledge_before_close(
    db: sqlite3.Connection,
    publish: Publish,
    flag_id: int,
    account_id: int,
    at: datetime,
) -> None:
    """Closing is the last step: record the closer's Acknowledgement if nobody gave one,
    the Counselor's too for an Escalated Flag, and silence every Alarm it sounds."""
    row = db.execute(
        "SELECT acknowledged_at, escalated_at, escalation_acknowledged_at "
        "FROM flags WHERE id = ?",
        (flag_id,),
    ).fetchone()
    if row is None:
        return
    acknowledged_at, escalated_at, escalation_acknowledged_at = row
    if acknowledged_at is None:
        _acknowledge(db, publish, flag_id, account_id, at, escalation=False)
    if escalated_at is not None and escalation_acknowledged_at is None:
        _acknowledge(db, publish, flag_id, account_id, at, escalation=True)


def acknowledge_escalation(
    db: sqlite3.Connection,
    publish: Publish,
    flag_id: int,
    account_id: int,
    at: datetime,
) -> dict | None:
    """The Counselor Acknowledges an Escalated Flag's Alarm. None when the Flag does
    not exist or is not Escalated."""
    flag = get_flag(db, flag_id)
    if flag is None or flag.escalated_at is None:
        return None
    return _acknowledge(db, publish, flag_id, account_id, at, escalation=True)


def acknowledgement(db: sqlite3.Connection, flag_id: int) -> tuple[str, str] | None:
    """(account username, time) of the Alarm's Acknowledgement, or None."""
    row = db.execute(
        "SELECT staff_accounts.username, flags.acknowledged_at FROM flags "
        "JOIN staff_accounts ON staff_accounts.id = flags.acknowledged_by "
        "WHERE flags.id = ? AND flags.acknowledged_at IS NOT NULL",
        (flag_id,),
    ).fetchone()
    return (row[0], row[1]) if row else None


def _unacknowledged(db: sqlite3.Connection, column: str) -> set[int]:
    return {
        row[0]
        for row in db.execute(f"SELECT id FROM flags WHERE {column} IS NULL").fetchall()
    }


def unacknowledged_alarms(db: sqlite3.Connection) -> list[dict]:
    """Every open high-severity Flag nobody has Acknowledged, oldest first: what replays
    at Start watch and on the next staff page opened."""
    pending = _unacknowledged(db, "acknowledged_at")
    flags = [f for f in open_flags(db) if f.severity == "high" and f.id in pending]
    return [alarm_payload(db, flag) for flag in reversed(flags)]


def unacknowledged_escalations(db: sqlite3.Connection) -> list[dict]:
    """Every open Escalated Flag the Counselor has not Acknowledged, oldest first."""
    pending = _unacknowledged(db, "escalation_acknowledged_at")
    flags = [f for f in open_flags(db) if f.escalated_at and f.id in pending]
    return [escalation_payload(db, flag) for flag in reversed(flags)]


def replays_on_page_open(
    db: sqlite3.Connection, account_id: int, now: datetime
) -> bool:
    """Does opening a staff page replay the unacknowledged Alarms? In periodic or off
    mode, yes (decision lib-f24.77). In live mode they replay at Start watch, so only
    for an account already on Watch (a reloaded watching page)."""
    mode = get_setting(db, SUPERVISION_MODE, DEFAULT_SUPERVISION_MODE)
    return mode != "live" or is_watching(db, account_id, now)


def chime_settings(db: sqlite3.Connection) -> tuple[bool, int]:
    """(chime on, repeat seconds) from the Install settings (decision lib-f24.77)."""
    chime_on = get_setting(db, ALARM_CHIME, DEFAULT_ALARM_CHIME) == "on"
    repeat = get_int_setting(db, ALARM_REPEAT_SECONDS, DEFAULT_ALARM_REPEAT_SECONDS)
    return chime_on, repeat
