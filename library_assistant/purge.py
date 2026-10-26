"""Purge transcripts according to ADR-0003.

Every transcript is deleted at the end of the school day it was made, except those
attached to an open Flag, which stay until an adult closes the Flag. The purge runs
at the end of each school day (ADR-0003).
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime

from library_assistant.config import Settings
from library_assistant.schoolday import last_day_end_before

PurgeReport = namedtuple("PurgeReport", ["deleted", "kept_for_flags"])


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

        # If the transcript is referenced by an open flag, keep it
        if flag_check[0] > 0 or flag_repeat_check[0] > 0:
            kept_for_flags_count += 1
        else:
            # Delete the transcript
            db.execute("DELETE FROM transcripts WHERE id = ?", (transcript_id,))

            # Delete related flag_repeats entries for this transcript
            db.execute(
                "DELETE FROM flag_repeats WHERE transcript_id = ?", (transcript_id,)
            )

            deleted_count += 1

    return PurgeReport(deleted=deleted_count, kept_for_flags=kept_for_flags_count)
