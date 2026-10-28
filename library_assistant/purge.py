"""Purge transcripts according to ADR-0003.

Every transcript is deleted at the end of the school day it was made, except those
attached to an open Flag, which stay until an adult closes the Flag. The purge runs
at the end of each school day (ADR-0003).
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from library_assistant.config import Settings
from library_assistant.schoolday import last_day_end_before, school_day_end_for

PurgeReport = namedtuple(
    "PurgeReport", ["deleted", "kept_for_flags", "kept_unscreened", "overdue_flags"]
)


def run_if_due(db, now: datetime, settings: Settings) -> PurgeReport | None:
    """Run purge if it hasn't been run for the last school day end.

    Args:
        db: SQLite database connection
        now: Current time (UTC)
        settings: Configuration settings

    Returns:
        PurgeReport with counts of deleted and kept transcripts, or None if already run
    """
    # Check if purge has already been run for the last day end
    cutoff = last_day_end_before(now, settings)
    existing_run = db.execute(
        "SELECT 1 FROM purge_runs WHERE ran_at >= ?", (cutoff.isoformat(),)
    ).fetchone()

    if existing_run:
        return None

    # Run the purge and record that it was run
    report = purge(db, now, settings)
    db.execute("INSERT INTO purge_runs (ran_at) VALUES (?)", (now.isoformat(),))
    db.commit()

    return report


def purge(db, now: datetime, settings: Settings) -> PurgeReport:
    """Purge old transcripts, keeping those referenced by open Flags.

    Args:
        db: SQLite database connection
        now: Current time (UTC)
        settings: Configuration settings

    Returns:
        PurgeReport with counts of deleted and kept transcripts
    """
    # Calculate the cutoff time (end of the school day before 'now')
    cutoff = last_day_end_before(now, settings)

    # Find all transcripts that are older than the cutoff
    # But keep transcripts that are referenced by open Flags (closed_at IS NULL)
    # This includes both direct references via transcript_id and references via flag_repeats

    # Get all transcripts that are older than cutoff
    transcripts_to_delete = db.execute(
        "SELECT id FROM transcripts WHERE asked_at < ?", (cutoff.isoformat(),)
    ).fetchall()

    deleted_count = 0
    kept_for_flags_count = 0
    kept_unscreened_count = 0

    # Process each transcript to see if it should be kept
    for transcript_row in transcripts_to_delete:
        transcript_id = transcript_row[0]

        # Check if this transcript is referenced by an open flag (closed_at IS NULL)
        # Either directly via flags.transcript_id or through flag_repeats
        flag_check = db.execute(
            """
            SELECT COUNT(*)
            FROM flags
            WHERE transcript_id = ? AND closed_at IS NULL
            """,
            (transcript_id,),
        ).fetchone()

        # Also check flag_repeats for open flags
        flag_repeat_check = db.execute(
            """
            SELECT COUNT(*)
            FROM flag_repeats fr
            JOIN flags f ON fr.flag_id = f.id
            WHERE fr.transcript_id = ? AND f.closed_at IS NULL
            """,
            (transcript_id,),
        ).fetchone()

        # Oversight down does not hold Students (ADR-0004 addenda): a transcript
        # still awaiting screening stays, whatever its day.
        unscreened_check = db.execute(
            """
            SELECT COUNT(*)
            FROM transcripts
            WHERE id = ? AND screened_at IS NULL
                AND screening IN ('oversight', 'watchlist_alone')
            """,
            (transcript_id,),
        ).fetchone()

        # If the transcript is referenced by an open flag, keep it
        if flag_check[0] > 0 or flag_repeat_check[0] > 0:
            kept_for_flags_count += 1
        elif unscreened_check[0] > 0:
            kept_unscreened_count += 1
        else:
            # Delete the transcript
            db.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))

            # Delete related flag_repeats entries for this transcript
            db.execute(
                "DELETE FROM flag_repeats WHERE transcript_id = ?", (transcript_id,)
            )

            deleted_count += 1

    db.commit()
    # Fold any write-ahead log back into the database and truncate it, so no
    # purged transcript survives in a -wal file (ADR-0003 addendum).
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # A Flag open longer than flags.overdue_days is counted here too (ADR-0003 addendum).
    overdue_cutoff = now - timedelta(days=settings.flags_overdue_days)
    overdue_count = db.execute(
        "SELECT COUNT(*) FROM flags WHERE closed_at IS NULL AND raised_at < ?",
        (overdue_cutoff.isoformat(),),
    ).fetchone()[0]

    return PurgeReport(
        deleted=deleted_count,
        kept_for_flags=kept_for_flags_count,
        kept_unscreened=kept_unscreened_count,
        overdue_flags=overdue_count,
    )


async def purge_loop(
    db,
    settings: Settings,
    now: Callable[[], datetime],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    """Sleep until each school-day end, then purge if due (ADR-0003).

    Runs forever; cancel the task to stop it.
    """
    while True:
        moment = now()
        next_end = school_day_end_for(moment, settings)
        if next_end <= moment:
            next_end = school_day_end_for(moment + timedelta(days=1), settings)
        await sleep((next_end - moment).total_seconds())
        run_if_due(db, now(), settings)
