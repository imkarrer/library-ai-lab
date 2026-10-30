"""Identification requests (lib-axb): the Counselor or Librarian asks the registering
Teacher who held a Card; the Teacher's own page answers. The name never reaches the
assistant (ADR-0002)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import (
    connect,
    get_clock,
    get_db,
    hash_token,
    issue_registration_key,
    registering_teacher,
)
from library_assistant.app import app
from library_assistant.flags import raise_flag
from library_assistant.identification import ask, open_requests_for

NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
EXPIRES = (NOW + timedelta(hours=2)).isoformat()


@pytest.fixture
def db():
    return connect(":memory:")


@pytest.fixture
def accounts(db):
    from library_assistant.staff import create_account

    return {
        role: create_account(db, f"the-{role}", "correct horse", role)
        for role in ("librarian", "teacher", "counselor")
    }


@pytest.fixture
def client(db, accounts):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clock] = lambda: NOW
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def _signed_in(role: str) -> TestClient:
    client = TestClient(app, follow_redirects=False)
    response = client.post(
        "/staff/login", data={"username": f"the-{role}", "password": "correct horse"}
    )
    assert response.status_code == 303
    return client


def _flag(db, accounts, severity="low", question="everyone picks on me") -> int:
    """A Flag on Period 3 card 1, whose Card the Teacher registered."""
    db.execute(
        "INSERT INTO cards (token_hash, card_number, expires_at, class_label, "
        "registered_by_account_id) VALUES (?, '1', ?, 'Period 3', ?)",
        (hash_token("token-1"), EXPIRES, accounts["teacher"]),
    )
    db.execute(
        "INSERT INTO transcripts (session_hash, class_label, card_number, question, "
        "answer, citations, asked_at) VALUES ('s', 'Period 3', '1', ?, 'a', '', ?)",
        (question, NOW.isoformat()),
    )
    transcript_id = db.execute("SELECT max(id) FROM transcripts").fetchone()[0]
    return raise_flag(
        db,
        transcript_id,
        "Period 3",
        "1",
        EXPIRES,
        "h",
        "bullying",
        severity,
        "oversight",
        NOW.isoformat(),
        reason="names a classmate",
    )


def test_a_flag_keeps_its_teacher_after_the_purge_deletes_the_card(db, accounts):
    flag_id = _flag(db, accounts)
    db.execute("DELETE FROM cards")  # what the Purge does after the Batch expires
    db.commit()

    assert registering_teacher(db, "Period 3", "1", EXPIRES) == "the-teacher"
    assert ask(db, flag_id, accounts["librarian"], NOW) is not None


def test_asking_twice_reuses_the_open_request(db, accounts):
    flag_id = _flag(db, accounts)
    first = ask(db, flag_id, accounts["librarian"], NOW)
    second = ask(db, flag_id, accounts["counselor"], NOW)
    assert first.id == second.id
    assert len(open_requests_for(db, accounts["teacher"])) == 1


def test_librarian_asks_from_the_flag_page_and_the_teacher_sees_it(
    client, db, accounts
):
    flag_id = _flag(db, accounts, severity="high")
    librarian = _signed_in("librarian")

    page = librarian.get(f"/staff/flags/{flag_id}").text
    assert "Ask the-teacher who held it" in page
    assert "don&#x27;t wait" in page or "don't wait" in page

    assert librarian.post(f"/staff/flags/{flag_id}/identify").status_code == 303
    assert "Waiting for them" in librarian.get(f"/staff/flags/{flag_id}").text

    home = _signed_in("teacher").get("/staff").text
    assert "Who held these Cards?" in home
    assert "Period 3 &middot; card 1" in home
    assert "This is urgent" in home
    # The Teacher's list says who asks about which Card, never what was said.
    for withheld in ("bullying", "names a classmate", "picks on me"):
        assert withheld not in home


def test_the_teacher_answers_and_the_asker_sees_it_without_a_name(client, db, accounts):
    flag_id = _flag(db, accounts)
    ask(db, flag_id, accounts["librarian"], NOW)
    [request] = open_requests_for(db, accounts["teacher"])

    teacher = _signed_in("teacher")
    answered = teacher.post(
        f"/staff/identification/{request.id}/answer", data={"answer": "told"}
    )
    assert answered.status_code == 303
    assert open_requests_for(db, accounts["teacher"]) == []

    page = _signed_in("librarian").get(f"/staff/flags/{flag_id}").text
    assert "the-teacher has the name and told the-librarian" in page
    events = db.execute(
        "SELECT event, account, outcome FROM flag_history WHERE flag_id = ? ORDER BY id",
        (flag_id,),
    ).fetchall()
    assert ("identification_requested", "the-librarian", None) in events
    assert ("identification_answered", "the-teacher", "told") in events


def test_not_in_my_rosters_points_the_asker_at_the_sealed_roster(client, db, accounts):
    flag_id = _flag(db, accounts)
    ask(db, flag_id, accounts["librarian"], NOW)
    [request] = open_requests_for(db, accounts["teacher"])
    _signed_in("teacher").post(
        f"/staff/identification/{request.id}/answer", data={"answer": "not_in_rosters"}
    )
    page = _signed_in("librarian").get(f"/staff/flags/{flag_id}").text
    assert "could not find card 1 in their Rosters" in page
    assert "sealed Roster" in page
    assert "Ask the-teacher again" in page


def test_only_the_asked_teacher_may_answer(client, db, accounts):
    flag_id = _flag(db, accounts)
    ask(db, flag_id, accounts["librarian"], NOW)
    [request] = open_requests_for(db, accounts["teacher"])
    response = _signed_in("counselor").post(
        f"/staff/identification/{request.id}/answer", data={"answer": "told"}
    )
    assert response.status_code == 404


def test_the_counselor_asks_only_about_an_escalated_flag(client, db, accounts):
    flag_id = _flag(db, accounts)
    counselor = _signed_in("counselor")
    assert (
        counselor.post(f"/staff/counselor/flags/{flag_id}/identify").status_code == 404
    )

    db.execute(
        "UPDATE flags SET escalated_at = ? WHERE id = ?", (NOW.isoformat(), flag_id)
    )
    db.commit()
    assert (
        "Ask the-teacher who held it"
        in counselor.get(f"/staff/counselor/flags/{flag_id}").text
    )
    assert (
        counselor.post(f"/staff/counselor/flags/{flag_id}/identify").status_code == 303
    )
    assert open_requests_for(db, accounts["teacher"])[0].requested_by == "the-counselor"


def test_the_minting_page_reads_and_answers_by_registration_key(client, db, accounts):
    flag_id = _flag(db, accounts, severity="high")
    ask(db, flag_id, accounts["counselor"], NOW)
    key = issue_registration_key(db, accounts["teacher"], NOW)
    page = TestClient(app)

    listed = page.post(
        "/batches/identification-requests",
        json={"registration_key": key},
        headers={"Origin": "null"},
    )
    assert listed.status_code == 200
    assert listed.headers["access-control-allow-origin"] == "*"
    [row] = listed.json()["requests"]
    assert set(row) == {
        "request_id",
        "class_label",
        "card_number",
        "batch_expires_at",
        "requested_by",
        "requested_by_role",
        "requested_at",
        "severity",
    }
    assert (row["class_label"], row["card_number"], row["batch_expires_at"]) == (
        "Period 3",
        "1",
        EXPIRES,
    )

    wrong_key = page.post(
        "/batches/identification-requests", json={"registration_key": "nope"}
    )
    assert wrong_key.status_code == 403

    answered = page.post(
        f"/batches/identification-requests/{row['request_id']}/answer",
        json={"registration_key": key, "answer": "told"},
    )
    assert answered.status_code == 200
    assert page.post(
        "/batches/identification-requests", json={"registration_key": key}
    ).json() == {"requests": []}


def test_the_answer_must_be_told_or_not_in_rosters(client, db, accounts):
    flag_id = _flag(db, accounts)
    ask(db, flag_id, accounts["librarian"], NOW)
    key = issue_registration_key(db, accounts["teacher"], NOW)
    [request] = open_requests_for(db, accounts["teacher"])
    response = TestClient(app).post(
        f"/batches/identification-requests/{request.id}/answer",
        json={"registration_key": key, "answer": "Fred"},
    )
    assert response.status_code == 404
    assert open_requests_for(db, accounts["teacher"])


def test_asking_acknowledges_and_a_told_answer_lifts_the_urgent_note(
    client, db, accounts
):
    flag_id = _flag(db, accounts, severity="high")
    librarian = _signed_in("librarian")
    librarian.post(f"/staff/flags/{flag_id}/identify")
    assert (
        db.execute(
            "SELECT acknowledged_by FROM flags WHERE id = ?", (flag_id,)
        ).fetchone()[0]
        == accounts["librarian"]
    )

    [request] = open_requests_for(db, accounts["teacher"])
    _signed_in("teacher").post(
        f"/staff/identification/{request.id}/answer", data={"answer": "told"}
    )
    page = librarian.get(f"/staff/flags/{flag_id}").text
    assert "Find the-teacher in person or by phone now" not in page
    assert "has the name and told" in page
