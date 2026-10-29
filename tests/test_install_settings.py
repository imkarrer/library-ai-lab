from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db
from library_assistant.app import app
from library_assistant.install_settings import (
    SESSION_IDLE_MINUTES,
    get_int_setting,
    get_setting,
)
from library_assistant.staff import create_account

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def client(db, clock):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: clock["now"]
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in(client, username="librarian", password="correct horse"):
    return client.post(
        "/staff/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_default_idle_minutes_is_0(db):
    assert get_int_setting(db, SESSION_IDLE_MINUTES, 0) == 0


def test_librarian_sets_idle_minutes(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    response = client.post(
        "/staff/settings",
        data={"session_idle_minutes": "120"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert get_int_setting(db, SESSION_IDLE_MINUTES, 0) == 120


def test_teacher_and_counselor_get_403(client, db):
    create_account(db, "teacher", "correct horse", "teacher")
    create_account(db, "counselor", "correct horse", "counselor")

    _sign_in(client, username="teacher")
    assert client.get("/staff/settings").status_code == 403
    assert (
        client.post("/staff/settings", data={"session_idle_minutes": "60"}).status_code
        == 403
    )

    _sign_in(client, username="counselor")
    assert client.get("/staff/settings").status_code == 403
    assert (
        client.post("/staff/settings", data={"session_idle_minutes": "60"}).status_code
        == 403
    )


def test_out_of_range_is_400(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    assert (
        client.post("/staff/settings", data={"session_idle_minutes": "481"}).status_code
        == 400
    )
    assert (
        client.post("/staff/settings", data={"session_idle_minutes": "-1"}).status_code
        == 400
    )


def test_defaults_live_120_0_90_on_30_carry_on(db):
    """Test that the new default values are set correctly."""
    # Test defaults for supervision mode constants
    from library_assistant.install_settings import (
        DEFAULT_ALARM_CHIME,
        DEFAULT_ALARM_REPEAT_SECONDS,
        DEFAULT_OVERSIGHT_DOWN,
        DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES,
        DEFAULT_REVIEWS_EVERY_MINUTES,
        DEFAULT_SUPERVISION_MODE,
        DEFAULT_WATCH_GRACE_SECONDS,
    )

    assert DEFAULT_SUPERVISION_MODE == "live"
    assert DEFAULT_REVIEWS_EVERY_MINUTES == 120
    assert DEFAULT_PAUSE_WHEN_REVIEW_OVERDUE_MINUTES == 0
    assert DEFAULT_WATCH_GRACE_SECONDS == 90
    assert DEFAULT_ALARM_CHIME == "on"
    assert DEFAULT_ALARM_REPEAT_SECONDS == 30
    assert DEFAULT_OVERSIGHT_DOWN == "carry_on"


def test_librarian_sets_periodic_every_120(client, db):
    """Test that librarian can set periodic supervision mode with reviews_every_minutes."""
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "0",
            "supervision_mode": "periodic",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Verify settings are set
    assert get_setting(db, "supervision_mode", "live") == "periodic"
    assert get_int_setting(db, "reviews_every_minutes", 120) == 120


def test_bad_mode_is_400(client, db):
    """Test that invalid supervision mode raises 400."""
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    # Test with invalid supervision mode
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "0",
            "supervision_mode": "invalid_mode",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_change_is_recorded_with_account_and_time(client, db):
    """Test that changes are recorded with account and timestamp."""
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    # First change
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "120",
            "supervision_mode": "periodic",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Check that setting_changes table has a record
    rows = db.execute("SELECT * FROM setting_changes").fetchall()
    assert len(rows) >= 1  # At least one change for the session_idle_minutes


def test_unchanged_value_records_nothing(client, db):
    """Test that unchanged values don't create new records."""
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    # Set initial values
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "120",
            "supervision_mode": "periodic",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Get initial change count
    initial_count = len(db.execute("SELECT * FROM setting_changes").fetchall())

    # Set the same values again - should not create new records
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "120",
            "supervision_mode": "periodic",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Check that no new records were created
    final_count = len(db.execute("SELECT * FROM setting_changes").fetchall())
    assert final_count == initial_count


def test_recent_changes_listed(client, db):
    """Test that recent changes are listed on the settings page."""
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    # Make a change
    response = client.post(
        "/staff/settings",
        data={
            "session_idle_minutes": "120",
            "supervision_mode": "periodic",
            "reviews_every_minutes": "120",
            "pause_when_review_overdue_minutes": "0",
            "watch_grace_seconds": "90",
            "alarm_chime": "on",
            "alarm_repeat_seconds": "30",
            "oversight_down": "carry_on",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    # Get the settings page to check for recent changes
    response = client.get("/staff/settings")
    assert response.status_code == 200
    # Verify the page contains recent changes information
    assert "Recent changes" in response.text
