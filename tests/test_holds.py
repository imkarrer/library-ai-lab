"""Holds: set, lift, and the Purge honours them (ADR-0003 addendum, lib-a2e.1)."""

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import library_assistant.app as app_module
from library_assistant.access import connect, get_clock, get_db, hash_token
from library_assistant.app import app
from library_assistant.config import Settings, get_settings
from library_assistant.holds import get_hold, lift_hold, set_hold
from library_assistant.purge import purge, run_if_due
from library_assistant.staff import STAFF_SESSION_COOKIE, create_account, set_stand_in

# Far in the future on purpose (see tests/test_staff.py): a past NOW would make every
# staff session in this file look already expired.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
TODAY = date(2036, 10, 27)
# School days end at 15:00 UTC, so "past end of day" is unambiguous on the fake clock.
SETTINGS = Settings(school_timezone="UTC", school_day_end="15:00")
AFTER_TODAYS_END = datetime(2036, 10, 27, 16, 0, tzinfo=UTC)


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
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _sign_in_as(client, db, role, stand_in=False) -> TestClient:
    account_id = create_account(db, f"{role}-account", "correct horse", role)
    if stand_in:
        set_stand_in(db, account_id, True)
    response = client.post(
        "/staff/login",
        data={"username": f"{role}-account", "password": "correct horse"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, response.cookies[STAFF_SESSION_COOKIE])
    return client


def _transcript(db, class_label="Period 3", card_number="14", asked_at=NOW):
    cursor = db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            hash_token("session-1"),
            class_label,
            card_number,
            "what do snow leopards eat?",
            "an answer",
            "[]",
            asked_at.isoformat(),
        ),
    )
    db.commit()
    return cursor.lastrowid


def _hold(
    db,
    class_labels=("Period 3",),
    all_classes=False,
    card_numbers=(),
    date_from=TODAY,
    date_to=TODAY,
    set_at=NOW,
):
    return set_hold(
        db,
        all_classes=all_classes,
        class_labels=list(class_labels),
        card_numbers=list(card_numbers),
        date_from=date_from,
        date_to=date_to,
        reason_kind="inspection request",
        reference="REQ-2036-01",
        set_at=set_at,
        set_by="librarian-account",
    )


def _remaining(db) -> set[int]:
    return {row[0] for row in db.execute("SELECT id FROM transcripts")}


HOLD_FORM = {
    "class_labels": "Period 3, Period 5",
    "date_from": "2036-10-20",
    "date_to": "2036-11-10",
    "card_numbers": "14, 15",
    "reason_kind": "public records request",
    "reference": "PRR 2036-117",
}


# --- who may set, lift, or view -------------------------------------------------------


def test_librarian_sets_a_hold_and_sees_it_on_the_holds_page(client, db):
    _sign_in_as(client, db, "librarian")

    response = client.post("/staff/holds", data=HOLD_FORM, follow_redirects=False)
    assert response.status_code == 303

    hold = get_hold(db, 1)
    assert hold.class_labels == ("Period 3", "Period 5")
    assert not hold.all_classes
    assert hold.card_numbers == ("14", "15")
    assert hold.date_from == date(2036, 10, 20)
    assert hold.date_to == date(2036, 11, 10)
    assert hold.reason_kind == "public records request"
    assert hold.reference == "PRR 2036-117"
    assert hold.set_by == "librarian-account"

    page = client.get("/staff/holds")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert "Period 3, Period 5" in page.text
    assert "PRR 2036-117" in page.text
    assert "public records request" in page.text


def test_librarian_sets_a_hold_on_all_classes_without_card_numbers(client, db):
    _sign_in_as(client, db, "librarian")
    form = {**HOLD_FORM, "all_classes": "true", "class_labels": "", "card_numbers": ""}

    response = client.post("/staff/holds", data=form, follow_redirects=False)

    assert response.status_code == 303
    hold = get_hold(db, 1)
    assert hold.all_classes
    assert hold.card_numbers == ()


@pytest.mark.parametrize(
    "change",
    [
        {"class_labels": ""},  # neither Class labels nor all
        {"reason_kind": "because"},
        {"reference": "  "},
        {"date_from": "2036-11-11"},  # after date_to
    ],
)
def test_hold_with_an_unusable_scope_is_refused(client, db, change):
    _sign_in_as(client, db, "librarian")

    response = client.post("/staff/holds", data={**HOLD_FORM, **change})

    assert response.status_code == 422
    assert get_hold(db, 1) is None


@pytest.mark.parametrize(
    ("role", "stand_in"),
    [("teacher", False), ("counselor", False), ("teacher", True)],
)
def test_other_roles_cannot_set_lift_or_view_holds(client, db, role, stand_in):
    hold_id = _hold(db)
    _sign_in_as(client, db, role, stand_in=stand_in)

    assert client.get("/staff/holds").status_code == 403
    assert client.post("/staff/holds", data=HOLD_FORM).status_code == 403
    lift = client.post(f"/staff/holds/{hold_id}/lift", data={"reason": "done"})
    assert lift.status_code == 403
    assert get_hold(db, hold_id).active
    assert get_hold(db, 2) is None


def test_signed_out_cannot_set_lift_or_view_holds(client, db):
    hold_id = _hold(db)

    assert client.get("/staff/holds").status_code == 401
    assert client.post("/staff/holds", data=HOLD_FORM).status_code == 401
    lift = client.post(f"/staff/holds/{hold_id}/lift", data={"reason": "done"})
    assert lift.status_code == 401
    assert get_hold(db, hold_id).active


# --- the Purge keeps exactly a Hold's scope -------------------------------------------


def test_purge_keeps_everything_in_scope_and_deletes_unflagged_outside_it(db):
    _hold(db, class_labels=["Period 3"], card_numbers=["14"])
    held = _transcript(db, "Period 3", "14")
    other_card = _transcript(db, "Period 3", "15")
    other_class = _transcript(db, "Period 5", "14")
    other_day = _transcript(db, "Period 3", "14", asked_at=NOW - timedelta(days=1))

    report = purge(db, AFTER_TODAYS_END, SETTINGS)

    assert _remaining(db) == {held}
    assert {other_card, other_class, other_day}.isdisjoint(_remaining(db))
    assert report.kept_for_holds == 1
    assert report.deleted == 3


def test_hold_on_all_classes_keeps_every_class_in_its_dates(db):
    _hold(db, class_labels=[], all_classes=True)
    period_3 = _transcript(db, "Period 3", "14")
    period_5 = _transcript(db, "Period 5", "2")
    _transcript(db, "Period 5", "2", asked_at=NOW - timedelta(days=1))

    purge(db, AFTER_TODAYS_END, SETTINGS)

    assert _remaining(db) == {period_3, period_5}


def test_hold_with_a_future_end_date_keeps_transcripts_made_after_it_was_set(db):
    _hold(db, date_from=TODAY, date_to=TODAY + timedelta(days=7))
    tomorrow = NOW + timedelta(days=1)
    later = _transcript(db, "Period 3", "14", asked_at=tomorrow)
    _transcript(db, "Period 5", "14", asked_at=tomorrow)

    purge(db, AFTER_TODAYS_END + timedelta(days=1), SETTINGS)

    assert _remaining(db) == {later}


def test_hold_past_its_end_date_still_holds_until_lifted(db):
    """A Hold never expires on its own: its dates are its scope, not its life."""
    _hold(db)
    held = _transcript(db)

    purge(db, AFTER_TODAYS_END + timedelta(days=60), SETTINGS)

    assert _remaining(db) == {held}


# --- no edit; lift needs a reason; after a lift the ordinary rules --------------------


def test_hold_has_no_edit_path(client, db):
    hold_id = _hold(db)
    _sign_in_as(client, db, "librarian")

    for method in ("put", "patch"):
        response = getattr(client, method)(f"/staff/holds/{hold_id}", data=HOLD_FORM)
        assert response.status_code in (404, 405)
    with pytest.raises(sqlite3.DatabaseError, match="never edited"):
        db.execute("UPDATE holds SET date_to = '2099-01-01' WHERE id = ?", (hold_id,))
    assert get_hold(db, hold_id).date_to == TODAY


@pytest.mark.parametrize("data", [{}, {"reason": "   "}])
def test_lifting_needs_a_reason(client, db, data):
    hold_id = _hold(db)
    _sign_in_as(client, db, "librarian")

    response = client.post(f"/staff/holds/{hold_id}/lift", data=data)

    assert response.status_code == 422
    assert get_hold(db, hold_id).active


def test_after_a_lift_the_next_purge_applies_the_normal_rules(client, db, clock):
    hold_id = _hold(db)
    held = _transcript(db)
    purge(db, AFTER_TODAYS_END, SETTINGS)
    assert _remaining(db) == {held}

    _sign_in_as(client, db, "librarian")
    clock["now"] = AFTER_TODAYS_END + timedelta(hours=1)
    response = client.post(
        f"/staff/holds/{hold_id}/lift",
        data={"reason": "request granted, records inspected"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    hold = get_hold(db, hold_id)
    assert not hold.active
    assert hold.lift_reason == "request granted, records inspected"
    assert hold.lifted_by == "librarian-account"

    report = purge(db, AFTER_TODAYS_END + timedelta(days=1), SETTINGS)

    assert _remaining(db) == set()
    assert report.kept_for_holds == 0
    assert report.deleted == 1


def test_a_lifted_hold_cannot_be_lifted_again(client, db):
    hold_id = _hold(db)
    lift_hold(db, hold_id, NOW, "librarian-account", "first")
    _sign_in_as(client, db, "librarian")

    response = client.post(f"/staff/holds/{hold_id}/lift", data={"reason": "second"})

    assert response.status_code == 422
    assert get_hold(db, hold_id).lift_reason == "first"


# --- what is reported and shown --------------------------------------------------------


def test_purge_run_record_gives_counts_kept_under_holds(db):
    _hold(db, class_labels=["Period 3"])
    _hold(db, class_labels=["Period 5"])
    _transcript(db, "Period 3", "14")
    _transcript(db, "Period 3", "15")
    _transcript(db, "Period 7", "1")

    report = run_if_due(db, AFTER_TODAYS_END, SETTINGS)

    assert report.kept_for_holds == 2
    assert report.holds == 2
    assert report.deleted == 1
    row = db.execute(
        "SELECT deleted, kept_for_holds, holds FROM purge_runs ORDER BY rowid DESC"
    ).fetchone()
    assert row == (1, 2, 2)


def test_flag_queue_shows_active_hold_count(client, db):
    _hold(db)
    _hold(db)
    lifted = _hold(db)
    lift_hold(db, lifted, NOW, "librarian-account", "narrowed")
    _sign_in_as(client, db, "librarian")

    response = client.get("/staff/flags")

    assert response.status_code == 200
    assert "Active Holds: 2" in response.text


def test_holds_page_shows_what_each_hold_holds_without_transcript_text(client, db):
    _hold(db)
    _transcript(db)
    _transcript(db, card_number="15")
    _sign_in_as(client, db, "librarian")

    response = client.get("/staff/holds")

    assert "2 transcripts" in response.text
    assert "snow leopards" not in response.text


# --- review marking on the fake clock -------------------------------------------------


def test_hold_older_than_review_days_is_marked_for_review_by_the_purge(client, db):
    settings = Settings(
        school_timezone="UTC", school_day_end="15:00", holds_review_days=30
    )
    stale = _hold(db, set_at=NOW - timedelta(days=31))
    fresh = _hold(db, set_at=NOW - timedelta(days=29))

    purge(db, AFTER_TODAYS_END, settings)

    assert get_hold(db, stale).review_marked_at == AFTER_TODAYS_END.isoformat()
    assert get_hold(db, fresh).review_marked_at is None
    assert get_hold(db, stale).active  # marked for review, never expired

    _sign_in_as(client, db, "librarian")
    assert "Review due" in client.get("/staff/holds").text


def test_review_mark_keeps_its_first_date_and_skips_lifted_holds(db):
    stale = _hold(db, set_at=NOW - timedelta(days=40))
    lifted = _hold(db, set_at=NOW - timedelta(days=40))
    lift_hold(db, lifted, NOW, "librarian-account", "done")

    purge(db, AFTER_TODAYS_END, SETTINGS)
    purge(db, AFTER_TODAYS_END + timedelta(days=1), SETTINGS)

    assert get_hold(db, stale).review_marked_at == AFTER_TODAYS_END.isoformat()
    assert get_hold(db, lifted).review_marked_at is None


# --- the startup catch-up Purge -------------------------------------------------------


def test_startup_catch_up_purge_honours_holds(db, monkeypatch):
    """The app missed a day end while down; the Purge it runs at startup keeps the Hold."""
    _hold(db)
    held = _transcript(db, "Period 3", "14")
    unheld = _transcript(db, "Period 5", "14")
    monkeypatch.setattr(app_module, "connect", lambda: db)
    app.dependency_overrides[get_clock] = lambda: AFTER_TODAYS_END + timedelta(days=2)
    app.dependency_overrides[get_settings] = lambda: SETTINGS
    try:
        with TestClient(app):
            pass
    finally:
        app.dependency_overrides.clear()

    assert _remaining(db) == {held}
    assert unheld not in _remaining(db)
    row = db.execute("SELECT kept_for_holds, holds FROM purge_runs").fetchone()
    assert row == (1, 1)


def test_hold_export_contains_only_its_scope(client, db):
    _sign_in_as(client, db, "librarian")
    _transcript(db, "Period 3", "14")
    _transcript(db, "Period 5", "14")
    _transcript(db, "Period 3", "99")
    hold_id = _hold(db, class_labels=("Period 3",), card_numbers=("14",))

    response = client.get(f"/staff/holds/{hold_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    assert "what do snow leopards eat?" in body
    assert body.count("what do snow leopards eat?") == 1
    assert "Period 3" in body
    assert "99" not in body
    assert "Period 5" not in body


def test_hold_export_is_plain_text_not_html(client, db):
    _sign_in_as(client, db, "librarian")
    _transcript(db, "Art & Design", "14")
    hold_id = _hold(db, class_labels=("Art & Design",))

    body = client.get(f"/staff/holds/{hold_id}/export").text

    assert "Scope: Art & Design;" in body
    assert "&amp;" not in body


def test_hold_export_refused_to_non_librarian(client, db):
    _hold(db)
    _sign_in_as(client, db, "teacher")

    response = client.get("/staff/holds/1/export")
    assert response.status_code == 403


def test_older_purge_run_table_gains_the_count_columns(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE purge_runs (ran_at TEXT NOT NULL)")
    old.execute("INSERT INTO purge_runs VALUES ('2036-10-26T15:00:00+00:00')")
    old.commit()
    old.close()

    db = connect(str(path))

    columns = {row[1] for row in db.execute("PRAGMA table_info(purge_runs)")}
    assert {"kept_for_holds", "holds"} <= columns
    assert db.execute("SELECT COUNT(*) FROM purge_runs").fetchone()[0] == 1
