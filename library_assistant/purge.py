"""Purge transcripts according to ADR-0003.

Every transcript is deleted at the end of the school day it was made, except those
attached to an open Flag, which stay until an adult closes the Flag, and those in an
active Hold's scope, which stay until the Librarian lifts it (ADR-0003 addendum). The
purge runs at the end of each school day (ADR-0003). Transcripts older than flags.history_days
are also deleted, unless they are referenced by an open Flag or covered by a Hold.
"""

from __future__ import annotations

from collections import namedtuple
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from library_assistant.config import Settings
from library_assistant.holds import active_holds, holding, mark_holds_for_review
from library_assistant.schoolday import last_day_end_before, school_day_end_for

# kept_for_holds counts transcripts kept because a Hold covers them (whatever else
# would also keep them); holds is how many active Holds the Purge honoured.
PurgeReport = namedtuple(
    "PurgeReport",
    [
        "deleted",
        "kept_for_flags",
        "kept_unscreened",
        "kept_for_holds",
        "holds",
        "overdue_flags",
    ],
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

    # Run the purge and record that it was run, with its report
    report = purge(db, now, settings)
    columns = ", ".join(PurgeReport._fields)
    placeholders = ", ".join("?" for _ in PurgeReport._fields)
    db.execute(
        f"INSERT INTO purge_runs (ran_at, {columns}) VALUES (?, {placeholders})",
        (now.isoformat(), *report),
    )
    db.commit()

    return report


def purge(db, now: datetime, settings: Settings) -> PurgeReport:
    """Purge old transcripts, keeping those under a Hold or referenced by open Flags.

    Also marks for review each Hold older than `holds_review_days`.

    Args:
        db: SQLite database connection
        now: Current time (UTC)
        settings: Configuration settings

    Returns:
        PurgeReport with counts of deleted and kept transcripts
    """
    # Calculate the cutoff time (end of the school day before 'now')
    cutoff = last_day_end_before(now, settings)

    # Calculate history cutoff based on flags_history_days setting
    history_cutoff = now - timedelta(days=settings.flags_history_days)

    # Find all transcripts that are older than the cutoff
    # But keep transcripts that are referenced by open Flags (closed_at IS NULL)
    # This includes both direct references via transcript_id and references via flag_repeats

    # Get all transcripts that are older than cutoff
    transcripts_to_delete = db.execute(
        "SELECT id, class_label, card_number, asked_at FROM transcripts "
        "WHERE asked_at < ?",
        (cutoff.isoformat(),),
    ).fetchall()

    holds = active_holds(db)
    deleted_count = 0
    kept_for_flags_count = 0
    kept_unscreened_count = 0
    kept_for_holds_count = 0

    # Process each transcript to see if it should be kept
    for transcript_id, class_label, card_number, asked_at in transcripts_to_delete:
        # A Hold keeps exactly what its scope covers: Class label (or all), the school
        # date the transcript was made, and its Card number when the Hold names any.
        if holding(holds, class_label, card_number, asked_at, settings):
            kept_for_holds_count += 1
            continue

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
            # Check if this transcript is also older than flags_history_days
            # If so, it should be deleted even if it passed the day-end cutoff
            if asked_at < history_cutoff.isoformat():
                # This transcript is older than flags_history_days, so delete it
                # but first check if it should be kept for holds or flags
                # (This check is redundant because it already passed the hold/flag check)
                # But we need to make sure it's not covered by a Hold or open Flag
                # However, it's already been through that check above, so we just delete it
                db.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))

                # Delete related flag_repeats entries for this transcript
                db.execute(
                    "DELETE FROM flag_repeats WHERE transcript_id = ?", (transcript_id,)
                )

                deleted_count += 1
            else:
                # Standard day-end cutoff logic - delete if not covered by holds/flags
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

    # A Hold never expires on its own; one older than holds.review_days is marked
    # for review instead (ADR-0003 addendum).
    mark_holds_for_review(db, now, settings.holds_review_days)

    return PurgeReport(
        deleted=deleted_count,
        kept_for_flags=kept_for_flags_count,
        kept_unscreened=kept_unscreened_count,
        kept_for_holds=kept_for_holds_count,
        holds=len(holds),
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
