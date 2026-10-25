from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from library_assistant.access import (
    SESSION_COOKIE,
    connect,
    get_clock,
    get_db,
    get_registration_key,
)
from library_assistant.app import app
from library_assistant.staff import (
    STAFF_SESSION_COOKIE,
    LibrarianDep,
    StaffSignInRequired,
    create_account,
    hash_password,
    sign_in_required_handler,
    verify_password,
)
from library_assistant.staff import router as staff_router

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


def test_password_hash_round_trip():
    stored = hash_password("correct horse")
    assert stored.startswith("scrypt$")
    assert "correct horse" not in stored
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert hash_password("correct horse") != stored  # salted
    assert not verify_password("correct horse", "not-a-hash")


def test_login_sets_httponly_strict_cookie(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    response = _sign_in(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/staff"
    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{STAFF_SESSION_COOKIE}=")
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    session_id = response.cookies[STAFF_SESSION_COOKIE]
    stored = [row[0] for row in db.execute("SELECT session_hash FROM staff_sessions")]
    assert stored and session_id not in stored

    home = client.get("/staff")
    assert home.status_code == 200
    assert "librarian" in home.text


def test_wrong_password_is_401(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    assert _sign_in(client, password="wrong horse").status_code == 401
    assert _sign_in(client, username="nobody").status_code == 401
    assert STAFF_SESSION_COOKIE not in client.cookies


def test_staff_home_anonymous_is_401(client):
    response = client.get("/staff")
    assert response.status_code == 401
    assert 'href="/staff/login"' in response.text


def test_student_cookie_is_401_on_staff_home(client):
    client.post(
        "/batches",
        json={
            "registration_key": REGISTRATION_KEY,
            "cards": [{"token": "token-1", "card_number": "14"}],
            "expires_at": (NOW + timedelta(hours=2)).isoformat(),
            "class_label": "Period 3",
        },
    )
    assert client.post("/card", json={"token": "token-1"}).status_code == 200
    assert SESSION_COOKIE in client.cookies
    assert client.get("/staff").status_code == 401


def test_wrong_role_is_403(db, clock):
    guarded = FastAPI()
    guarded.include_router(staff_router)
    guarded.add_exception_handler(StaffSignInRequired, sign_in_required_handler)

    @guarded.get("/librarian-only")
    def librarian_only(
        account: LibrarianDep,
    ) -> dict[str, str]:
        return {"username": account.username}

    guarded.dependency_overrides[get_db] = lambda: db
    guarded.dependency_overrides[get_clock] = lambda: clock["now"]
    create_account(db, "librarian", "correct horse", "librarian")
    create_account(db, "teacher", "correct horse", "teacher")
    client = TestClient(guarded)

    assert client.get("/librarian-only").status_code == 401
    _sign_in(client, username="teacher")
    assert client.get("/librarian-only").status_code == 403
    _sign_in(client, username="librarian")
    assert client.get("/librarian-only").json() == {"username": "librarian"}


def test_expired_staff_session_is_401(client, db, clock):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    assert client.get("/staff").status_code == 200
    clock["now"] = NOW + timedelta(hours=12)
    assert client.get("/staff").status_code == 401


def test_logout_ends_the_session(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    session_id = client.cookies[STAFF_SESSION_COOKIE]
    response = client.post("/staff/logout", follow_redirects=False)
    assert response.status_code == 303
    client.cookies.set(STAFF_SESSION_COOKIE, session_id)
    assert client.get("/staff").status_code == 401


def test_create_account_refuses_unknown_role(db):
    with pytest.raises(ValueError):
        create_account(db, "someone", "pw", "admin")
