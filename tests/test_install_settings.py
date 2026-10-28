from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from library_assistant.access import connect, get_clock, get_db, get_registration_key
from library_assistant.app import app
from library_assistant.install_settings import SESSION_IDLE_MINUTES, get_int_setting
from library_assistant.staff import create_account

NOW = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)
REGISTRATION_KEY = "s3cret-registration-key"


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
    app.dependency_overrides[get_registration_key] = lambda: REGISTRATION_KEY
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
