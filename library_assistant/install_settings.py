"""Install settings: Librarian-only knobs stored in the `install_settings` table.

Binding: ADR-0010. Only the Librarian manages Install settings.
"""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from library_assistant.access import get_db
from library_assistant.staff import LibrarianDep, page
from library_assistant.supportive_replies import (
    PRECEDENCE_ORDER,
    validate_override_text,
)

# Supervision mode constants
SUPERVISION_MODE = "supervision_mode"
REVIEWS_EVERY_MINUTES = "reviews_every_minutes"
PAUSE_WHEN_REVIEW_OVERDUE_MINUTES = "pause_when_review_overdue_minutes"
WATCH_GRACE_SECONDS = "watch_grace_seconds"
ALARM_CHIME = "alarm_chime"
ALARM_REPEAT_SECONDS = "alarm_repeat_seconds"
OVERSIGHT_DOWN = "oversight_down"

# Default values
DEFAULT_SUPERVISION_MODE = "live"
DEFAULT_REVIEWS_EVERY_MINUTES = 120
DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES = 0
DEFAULT_WATCH_GRACE_SECONDS = 90
DEFAULT_ALARM_CHIME = "on"
DEFAULT_ALARM_REPEAT_SECONDS = 30
DEFAULT_OVERSIGHT_DOWN = "carry_on"
DEFAULT_COUNSELOR_NAME = "a school counselor"

SESSION_IDLE_MINUTES = "session_idle_minutes"

MAX_SESSION_IDLE_MINUTES = 480

SETTINGS_FORM = """<h1>Install settings</h1>
{message}
<form method="post" action="/staff/settings">
  <p><label>Session idle minutes (0-480, 0 means no limit)
     <input name="session_idle_minutes" type="number" min="0" max="480"
            value="{session_idle_minutes}" required></label></p>
  <p><label>Supervision mode (live, periodic, off)
     <select name="supervision_mode" required>
        <option value="live" {live_selected}>Live</option>
        <option value="periodic" {periodic_selected}>Periodic review</option>
        <option value="off" {off_selected}>Off</option>
     </select></label></p>
  <p><label>Reviews every minutes (periodic mode)
     <input name="reviews_every_minutes" type="number" min="1" max="1440"
            value="{reviews_every_minutes}" required></label></p>
  <p><label>Pause when review overdue minutes (0 = never)
     <input name="pause_when_review_overdue_minutes" type="number" min="0" max="1440"
            value="{pause_when_review_overdue_minutes}" required></label></p>
  <p><label>Watch grace seconds
     <input name="watch_grace_seconds" type="number" min="0" max="3600"
            value="{watch_grace_seconds}" required></label></p>
  <p><label>Alarm chime (on/off)
     <select name="alarm_chime" required>
        <option value="on" {alarm_on_selected}>On</option>
        <option value="off" {alarm_off_selected}>Off</option>
     </select></label></p>
  <p><label>Alarm repeat seconds
     <input name="alarm_repeat_seconds" type="number" min="0" max="3600"
            value="{alarm_repeat_seconds}" required></label></p>
  <p><label>Oversight down (carry_on/pause)
     <select name="oversight_down" required>
        <option value="carry_on" {carry_on_selected}>Carry on</option>
        <option value="pause" {pause_selected}>Pause</option>
     </select></label></p>
  <h2>Supportive replies</h2>
  <p><label>Counselor line (default: "{default_counselor_name}")
     <input name="counselor_name" type="text" value="{counselor_name}" /></label></p>
  <p>Per-category reply overrides (empty means use default):</p>
  {supportive_reply_inputs}
  <p><a href="/staff/supportive-replies-preview">Preview</a></p>
  <p><button>Save</button></p>
</form>
<h2>Recent changes</h2>
{recent_changes}"""

RECENT_CHANGES_TEMPLATE = """<table>
  <thead>
    <tr><th>Setting</th><th>Old Value</th><th>New Value</th><th>Changed by</th><th>When</th></tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>"""

RECENT_CHANGE_ROW_TEMPLATE = """<tr><td>{key}</td><td>{old_value}</td><td>{new_value}</td><td>{account_id}</td><td>{changed_at}</td></tr>"""


def get_setting(db: sqlite3.Connection, key: str, default: str) -> str:
    """Get a setting value with a default if not found."""
    row = db.execute(
        "SELECT value FROM install_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    return row[0]


def get_int_setting(db: sqlite3.Connection, key: str, default: int) -> int:
    row = db.execute(
        "SELECT value FROM install_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return default
    return int(row[0])


def set_setting(
    db: sqlite3.Connection, key: str, value: object, account_id: int, now: datetime
) -> None:
    """Set a setting value, recording the change if it differs from the current value."""
    # Get the current value
    current_row = db.execute(
        "SELECT value FROM install_settings WHERE key = ?", (key,)
    ).fetchone()

    current_value = current_row[0] if current_row else None

    # Only update if the value is different
    if current_value != str(value):
        # Insert the old value into the setting_changes table
        db.execute(
            "INSERT INTO setting_changes (key, old_value, new_value, account_id, changed_at) VALUES (?, ?, ?, ?, ?)",
            (key, current_value, str(value), account_id, now.isoformat()),
        )

        # Update the setting
        db.execute(
            "INSERT OR REPLACE INTO install_settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    db.commit()


def get_recent_changes(db: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Get recent setting changes."""
    rows = db.execute(
        "SELECT key, old_value, new_value, account_id, changed_at FROM setting_changes ORDER BY changed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()

    return [
        {
            "key": row[0],
            "old_value": row[1],
            "new_value": row[2],
            "account_id": row[3],
            "changed_at": row[4],
        }
        for row in rows
    ]


router = APIRouter(prefix="/staff")


@router.get("/settings")
def settings_page(
    account: LibrarianDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    # Get current values
    idle_minutes = get_int_setting(db, SESSION_IDLE_MINUTES, 0)
    supervision_mode = get_setting(db, SUPERVISION_MODE, DEFAULT_SUPERVISION_MODE)
    reviews_every_minutes = get_int_setting(
        db, REVIEWS_EVERY_MINUTES, DEFAULT_REVIEWS_EVERY_MINUTES
    )
    pause_when_review_overdue_minutes = get_int_setting(
        db, PAUSE_WHEN_REVIEW_OVERDUE_MINUTES, DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES
    )
    watch_grace_seconds = get_int_setting(
        db, WATCH_GRACE_SECONDS, DEFAULT_WATCH_GRACE_SECONDS
    )
    alarm_chime = get_setting(db, ALARM_CHIME, DEFAULT_ALARM_CHIME)
    alarm_repeat_seconds = get_int_setting(
        db, ALARM_REPEAT_SECONDS, DEFAULT_ALARM_REPEAT_SECONDS
    )
    oversight_down = get_setting(db, OVERSIGHT_DOWN, DEFAULT_OVERSIGHT_DOWN)

    # Get supportive replies settings
    counselor_name = get_setting(db, "counselor_name", DEFAULT_COUNSELOR_NAME)

    # Generate supportive reply inputs
    supportive_reply_inputs = []
    for category in PRECEDENCE_ORDER:
        override_text = get_setting(db, f"supportive_reply_{category}", "")
        supportive_reply_inputs.append(
            f'<p><label>Override for "{category}"<br><textarea name="supportive_reply_{category}" rows="6" cols="80">{html.escape(override_text)}</textarea></label></p>'
        )
    supportive_reply_inputs_str = "\n".join(supportive_reply_inputs)

    # Format recent changes
    recent_changes = get_recent_changes(db)
    recent_changes_html = ""
    if recent_changes:
        rows = []
        for change in recent_changes:
            rows.append(
                RECENT_CHANGE_ROW_TEMPLATE.format(
                    key=change["key"],
                    old_value=change["old_value"] or "(none)",
                    new_value=change["new_value"],
                    account_id=change["account_id"],
                    changed_at=change["changed_at"],
                )
            )
        recent_changes_html = RECENT_CHANGES_TEMPLATE.format(rows="\n".join(rows))

    # Format form values
    live_selected = "selected" if supervision_mode == "live" else ""
    periodic_selected = "selected" if supervision_mode == "periodic" else ""
    off_selected = "selected" if supervision_mode == "off" else ""
    alarm_on_selected = "selected" if alarm_chime == "on" else ""
    alarm_off_selected = "selected" if alarm_chime == "off" else ""
    carry_on_selected = "selected" if oversight_down == "carry_on" else ""
    pause_selected = "selected" if oversight_down == "pause" else ""

    return page(
        "Install settings",
        SETTINGS_FORM.format(
            message="",
            session_idle_minutes=html.escape(str(idle_minutes)),
            supervision_mode=html.escape(supervision_mode),
            reviews_every_minutes=html.escape(str(reviews_every_minutes)),
            pause_when_review_overdue_minutes=html.escape(
                str(pause_when_review_overdue_minutes)
            ),
            watch_grace_seconds=html.escape(str(watch_grace_seconds)),
            alarm_chime=html.escape(alarm_chime),
            alarm_repeat_seconds=html.escape(str(alarm_repeat_seconds)),
            oversight_down=html.escape(oversight_down),
            live_selected=live_selected,
            periodic_selected=periodic_selected,
            off_selected=off_selected,
            alarm_on_selected=alarm_on_selected,
            alarm_off_selected=alarm_off_selected,
            carry_on_selected=carry_on_selected,
            pause_selected=pause_selected,
            counselor_name=html.escape(counselor_name),
            default_counselor_name=html.escape(DEFAULT_COUNSELOR_NAME),
            supportive_reply_inputs=supportive_reply_inputs_str,
            recent_changes=recent_changes_html,
        ),
    )


@router.post("/settings", response_model=None)
def update_settings(
    account: LibrarianDep,
    session_idle_minutes: Annotated[int, Form()],
    supervision_mode: Annotated[str, Form()] = DEFAULT_SUPERVISION_MODE,
    reviews_every_minutes: Annotated[int, Form()] = DEFAULT_REVIEWS_EVERY_MINUTES,
    pause_when_review_overdue_minutes: Annotated[
        int, Form()
    ] = DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
    watch_grace_seconds: Annotated[int, Form()] = DEFAULT_WATCH_GRACE_SECONDS,
    alarm_chime: Annotated[str, Form()] = DEFAULT_ALARM_CHIME,
    alarm_repeat_seconds: Annotated[int, Form()] = DEFAULT_ALARM_REPEAT_SECONDS,
    oversight_down: Annotated[str, Form()] = DEFAULT_OVERSIGHT_DOWN,
    counselor_name: Annotated[str, Form()] = "",
    supportive_reply_self_harm: Annotated[str, Form()] = "",
    supportive_reply_threats_of_violence: Annotated[str, Form()] = "",
    supportive_reply_abuse: Annotated[str, Form()] = "",
    supportive_reply_bullying: Annotated[str, Form()] = "",
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    # Validate supervision_mode
    if supervision_mode not in ["live", "periodic", "off"]:
        raise HTTPException(
            status_code=400,
            detail="supervision_mode must be one of: live, periodic, off",
        )

    # Validate reviews_every_minutes
    if not 1 <= reviews_every_minutes <= 1440:
        raise HTTPException(
            status_code=400, detail="reviews_every_minutes must be between 1 and 1440"
        )

    # Validate pause_when_review_overdue_minutes
    if not 0 <= pause_when_review_overdue_minutes <= 1440:
        raise HTTPException(
            status_code=400,
            detail="pause_when_review_overdue_minutes must be between 0 and 1440",
        )

    # Validate watch_grace_seconds
    if not 0 <= watch_grace_seconds <= 3600:
        raise HTTPException(
            status_code=400, detail="watch_grace_seconds must be between 0 and 3600"
        )

    # Validate alarm_chime
    if alarm_chime not in ["on", "off"]:
        raise HTTPException(
            status_code=400, detail="alarm_chime must be one of: on, off"
        )

    # Validate alarm_repeat_seconds
    if not 0 <= alarm_repeat_seconds <= 3600:
        raise HTTPException(
            status_code=400, detail="alarm_repeat_seconds must be between 0 and 3600"
        )

    # Validate oversight_down
    if oversight_down not in ["carry_on", "pause"]:
        raise HTTPException(
            status_code=400, detail="oversight_down must be one of: carry_on, pause"
        )

    if not 0 <= session_idle_minutes <= MAX_SESSION_IDLE_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"session_idle_minutes must be between 0 and {MAX_SESSION_IDLE_MINUTES}",
        )

    # Validate counselor name (allow empty to use default)
    if counselor_name != "" and counselor_name.isspace():
        raise HTTPException(
            status_code=400,
            detail="Counselor name cannot be only whitespace",
        )

    # Validate all supportive reply overrides
    invalid_overrides = []
    supportive_replies = {
        "self_harm": supportive_reply_self_harm,
        "threats_of_violence": supportive_reply_threats_of_violence,
        "abuse": supportive_reply_abuse,
        "bullying": supportive_reply_bullying,
    }

    for category, override_text in supportive_replies.items():
        if override_text and override_text.strip():
            errors = validate_override_text(override_text, category)
            if errors:
                invalid_overrides.append((category, errors))

    # If there are invalid overrides, return error
    if invalid_overrides:
        # Re-render the page with errors
        error_messages = []
        for category, errors in invalid_overrides:
            error_messages.append(f"Errors for {category}: " + ", ".join(errors))

        # Get current values for re-display
        idle_minutes = get_int_setting(db, SESSION_IDLE_MINUTES, 0)
        supervision_mode = get_setting(db, SUPERVISION_MODE, DEFAULT_SUPERVISION_MODE)
        reviews_every_minutes = get_int_setting(
            db, REVIEWS_EVERY_MINUTES, DEFAULT_REVIEWS_EVERY_MINUTES
        )
        pause_when_review_overdue_minutes = get_int_setting(
            db,
            PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
            DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        )
        watch_grace_seconds = get_int_setting(
            db, WATCH_GRACE_SECONDS, DEFAULT_WATCH_GRACE_SECONDS
        )
        alarm_chime = get_setting(db, ALARM_CHIME, DEFAULT_ALARM_CHIME)
        alarm_repeat_seconds = get_int_setting(
            db, ALARM_REPEAT_SECONDS, DEFAULT_ALARM_REPEAT_SECONDS
        )
        oversight_down = get_setting(db, OVERSIGHT_DOWN, DEFAULT_OVERSIGHT_DOWN)

        # Get supportive replies settings
        counselor_name = get_setting(db, "counselor_name", DEFAULT_COUNSELOR_NAME)

        # Generate supportive reply inputs
        supportive_reply_inputs = []
        for category in PRECEDENCE_ORDER:
            override_text = get_setting(db, f"supportive_reply_{category}", "")
            supportive_reply_inputs.append(
                f'<p><label>Override for "{category}"<br><textarea name="supportive_reply_{category}" rows="6" cols="80">{html.escape(override_text)}</textarea></label></p>'
            )
        supportive_reply_inputs_str = "\n".join(supportive_reply_inputs)

        # Format recent changes
        recent_changes = get_recent_changes(db)
        recent_changes_html = ""
        if recent_changes:
            rows = []
            for change in recent_changes:
                rows.append(
                    RECENT_CHANGE_ROW_TEMPLATE.format(
                        key=change["key"],
                        old_value=change["old_value"] or "(none)",
                        new_value=change["new_value"],
                        account_id=change["account_id"],
                        changed_at=change["changed_at"],
                    )
                )
            recent_changes_html = RECENT_CHANGES_TEMPLATE.format(rows="\n".join(rows))

        # Format form values
        live_selected = "selected" if supervision_mode == "live" else ""
        periodic_selected = "selected" if supervision_mode == "periodic" else ""
        off_selected = "selected" if supervision_mode == "off" else ""
        alarm_on_selected = "selected" if alarm_chime == "on" else ""
        alarm_off_selected = "selected" if alarm_chime == "off" else ""
        carry_on_selected = "selected" if oversight_down == "carry_on" else ""
        pause_selected = "selected" if oversight_down == "pause" else ""

        # Create error message
        message = (
            '<div style="color: red;"><p>Errors found:</p><ul>'
            + "".join([f"<li>{msg}</li>" for msg in error_messages])
            + "</ul></div>"
        )

        return page(
            "Install settings",
            SETTINGS_FORM.format(
                message=message,
                session_idle_minutes=html.escape(str(idle_minutes)),
                supervision_mode=html.escape(supervision_mode),
                reviews_every_minutes=html.escape(str(reviews_every_minutes)),
                pause_when_review_overdue_minutes=html.escape(
                    str(pause_when_review_overdue_minutes)
                ),
                watch_grace_seconds=html.escape(str(watch_grace_seconds)),
                alarm_chime=html.escape(alarm_chime),
                alarm_repeat_seconds=html.escape(str(alarm_repeat_seconds)),
                oversight_down=html.escape(oversight_down),
                live_selected=live_selected,
                periodic_selected=periodic_selected,
                off_selected=off_selected,
                alarm_on_selected=alarm_on_selected,
                alarm_off_selected=alarm_off_selected,
                carry_on_selected=carry_on_selected,
                pause_selected=pause_selected,
                counselor_name=html.escape(counselor_name),
                default_counselor_name=html.escape(DEFAULT_COUNSELOR_NAME),
                supportive_reply_inputs=supportive_reply_inputs_str,
                recent_changes=recent_changes_html,
            ),
        )

    # Set all settings
    set_setting(
        db, SESSION_IDLE_MINUTES, session_idle_minutes, account.id, datetime.now()
    )
    set_setting(db, SUPERVISION_MODE, supervision_mode, account.id, datetime.now())
    set_setting(
        db, REVIEWS_EVERY_MINUTES, reviews_every_minutes, account.id, datetime.now()
    )
    set_setting(
        db,
        PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        pause_when_review_overdue_minutes,
        account.id,
        datetime.now(),
    )
    set_setting(
        db, WATCH_GRACE_SECONDS, watch_grace_seconds, account.id, datetime.now()
    )
    set_setting(db, ALARM_CHIME, alarm_chime, account.id, datetime.now())
    set_setting(
        db, ALARM_REPEAT_SECONDS, alarm_repeat_seconds, account.id, datetime.now()
    )
    set_setting(db, OVERSIGHT_DOWN, oversight_down, account.id, datetime.now())

    # Set counselor name (empty string deletes the setting, using default)
    if counselor_name == "":
        # Delete the setting to use default
        db.execute("DELETE FROM install_settings WHERE key = 'counselor_name'")
        db.commit()
    else:
        set_setting(db, "counselor_name", counselor_name, account.id, datetime.now())

    # Set all supportive reply overrides
    for category, override_text in supportive_replies.items():
        if override_text and override_text.strip() != "":
            set_setting(
                db,
                f"supportive_reply_{category}",
                override_text,
                account.id,
                datetime.now(),
            )
        else:
            # Delete the setting if empty
            db.execute(
                "DELETE FROM install_settings WHERE key = ?",
                (f"supportive_reply_{category}",),
            )
            db.commit()

    return RedirectResponse("/staff/settings", status_code=303)
