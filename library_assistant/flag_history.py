"""The append-only Flag history (ADR-0003 addendum, "Flag lifecycle").

Binding: this module exposes only `append_event` and `get_history`. Nothing here
updates or deletes a row, because the history is append-only, full stop.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

EVENTS = ("raised", "viewed", "closed", "reopened", "repeated")


@dataclass(frozen=True)
class HistoryEvent:
    """One append-only row of a Flag's history."""

    id: int
    flag_id: int
    event: str
    at: str
    account: str | None
    reason: str | None
    outcome: str | None
    source: str | None
    entry_id: str | None
    watchlist_version: str | None
    repeat_count: int | None


def append_event(
    db: sqlite3.Connection,
    flag_id: int,
    event: str,
    at: str,
    account: str | None = None,
    reason: str | None = None,
    outcome: str | None = None,
    source: str | None = None,
    entry_id: str | None = None,
    watchlist_version: str | None = None,
    repeat_count: int | None = None,
) -> int:
    """Append one Flag history event and return its id."""
    if event not in EVENTS:
        raise ValueError(f"unknown Flag history event: {event!r}")
    cursor = db.execute(
        """
        INSERT INTO flag_history (
            flag_id, event, at, account, reason, outcome, source, entry_id,
            watchlist_version, repeat_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            flag_id,
            event,
            at,
            account,
            reason,
            outcome,
            source,
            entry_id,
            watchlist_version,
            repeat_count,
        ),
    )
    db.commit()
    return cursor.lastrowid


def get_history(db: sqlite3.Connection, flag_id: int) -> list[HistoryEvent]:
    """Read one Flag's history, oldest first."""
    rows = db.execute(
        """
        SELECT id, flag_id, event, at, account, reason, outcome, source, entry_id,
               watchlist_version, repeat_count
        FROM flag_history
        WHERE flag_id = ?
        ORDER BY id ASC
        """,
        (flag_id,),
    ).fetchall()
    return [HistoryEvent(*row) for row in rows]
