"""The Watch: an adult's deliberate, heartbeat-confirmed presence (ADR-0010).

One Watch covers the Install (ADR-0009: one supervised class at a time). Each staff account
holding it is a watcher, one `watchers` row per account, and the Watch is on while any
watcher is: started, heartbeat within `watch_grace_seconds`, and signed in. End watch and
sign-out remove the account's row; a missed heartbeat or an expired staff session drops it
at the next check. The Watch is staff data: it never names a Session or a Card, and the
Purge does not need it.

Every function takes `now` from the caller's injectable clock (`access.get_clock`).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta


def grace_seconds(db: sqlite3.Connection) -> int:
    # Imported here: install_settings imports staff, which imports this module.
    from library_assistant.install_settings import (
        DEFAULT_WATCH_GRACE_SECONDS,
        WATCH_GRACE_SECONDS,
        get_int_setting,
    )

    return get_int_setting(db, WATCH_GRACE_SECONDS, DEFAULT_WATCH_GRACE_SECONDS)


def _drop_lapsed(db: sqlite3.Connection, now: datetime) -> None:
    """Remove watchers past the grace period or with no unexpired staff session."""
    cutoff = now - timedelta(seconds=grace_seconds(db))
    db.execute(
        "DELETE FROM watchers WHERE last_heartbeat_at < ? OR NOT EXISTS ("
        "SELECT 1 FROM staff_sessions WHERE staff_sessions.account_id = "
        "watchers.account_id AND staff_sessions.expires_at > ?)",
        (cutoff.isoformat(), now.isoformat()),
    )
    db.commit()


def start_watch(db: sqlite3.Connection, account_id: int, now: datetime) -> None:
    """Make the account a watcher; pressing Start watch again restarts its heartbeat."""
    db.execute(
        "INSERT OR REPLACE INTO watchers (account_id, started_at, last_heartbeat_at) "
        "VALUES (?, ?, ?)",
        (account_id, now.isoformat(), now.isoformat()),
    )
    db.commit()


def heartbeat(db: sqlite3.Connection, account_id: int, now: datetime) -> bool:
    """Record a heartbeat; False when the account is not watching (never started, ended,
    or lapsed). A heartbeat never starts or revives a Watch: that takes Start watch."""
    _drop_lapsed(db, now)
    cursor = db.execute(
        "UPDATE watchers SET last_heartbeat_at = ? WHERE account_id = ?",
        (now.isoformat(), account_id),
    )
    db.commit()
    return cursor.rowcount == 1


def end_watch(db: sqlite3.Connection, account_id: int) -> None:
    """Remove the account as a watcher (End watch, sign-out). Others keep the Watch on."""
    db.execute("DELETE FROM watchers WHERE account_id = ?", (account_id,))
    db.commit()


def is_watching(db: sqlite3.Connection, account_id: int, now: datetime) -> bool:
    _drop_lapsed(db, now)
    row = db.execute(
        "SELECT 1 FROM watchers WHERE account_id = ?", (account_id,)
    ).fetchone()
    return row is not None


def watch_is_on(db: sqlite3.Connection, now: datetime) -> bool:
    """Is anyone on Watch: the check the gate on Card sign-in and asks reads."""
    _drop_lapsed(db, now)
    return db.execute("SELECT 1 FROM watchers LIMIT 1").fetchone() is not None


def watchers_count(db: sqlite3.Connection, now: datetime | None = None) -> int:
    """Return the count of watchers currently on Watch."""
    if now is None:
        # Imported here to avoid circular imports
        from library_assistant.access import get_clock

        now = get_clock()
    _drop_lapsed(db, now)
    row = db.execute("SELECT COUNT(*) FROM watchers").fetchone()
    return row[0] if row else 0


def gate_is_open(db: sqlite3.Connection, now: datetime) -> bool:
    """The gate on Card sign-in and asks (lib-f24.77): `live` needs a Watch; `off` is
    always open; `periodic` is open unless a review is overdue by more than the pause
    setting."""
    # Imported here: install_settings imports staff, which imports this module.
    from library_assistant.install_settings import (
        DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        DEFAULT_REVIEWS_EVERY_MINUTES,
        DEFAULT_SUPERVISION_MODE,
        PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        REVIEWS_EVERY_MINUTES,
        SUPERVISION_MODE,
        get_int_setting,
        get_setting,
    )

    mode = get_setting(db, SUPERVISION_MODE, DEFAULT_SUPERVISION_MODE)
    if mode == "off":
        return True
    if mode == "live":
        return watch_is_on(db, now)

    # mode == "periodic"
    pause_minutes = get_int_setting(
        db,
        PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
    )
    if pause_minutes <= 0:
        return True

    from library_assistant.access import review_due_at

    settings_dict = {
        "supervision_mode": mode,
        "reviews_every_minutes": str(
            get_int_setting(db, REVIEWS_EVERY_MINUTES, DEFAULT_REVIEWS_EVERY_MINUTES)
        ),
    }
    due_at = review_due_at(db, settings_dict, now)
    if due_at is None:
        return True
    return now < due_at + timedelta(minutes=pause_minutes)
