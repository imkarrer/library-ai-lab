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

# Far in the future on purpose: sign-in sets the cookie to expire with the Card, an
# absolute time the HTTP client compares with the real clock, so a past NOW drops it.
NOW = datetime(2036, 10, 27, 14, 0, tzinfo=UTC)
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


def test_librarian_can_grant_and_revoke_stand_in(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    account_id = create_account(db, "teacher", "correct horse", "teacher")
    _sign_in(client)

    grant = client.post(
        f"/staff/accounts/{account_id}/stand-in/grant", follow_redirects=False
    )
    assert grant.status_code == 303
    assert (
        db.execute(
            "SELECT is_stand_in FROM staff_accounts WHERE id = ?", (account_id,)
        ).fetchone()[0]
        == 1
    )

    revoke = client.post(
        f"/staff/accounts/{account_id}/stand-in/revoke", follow_redirects=False
    )
    assert revoke.status_code == 303
    assert (
        db.execute(
            "SELECT is_stand_in FROM staff_accounts WHERE id = ?", (account_id,)
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_grant_stand_in_refused_to_non_librarian(client, db, role):
    create_account(db, role, "correct horse", role)
    account_id = create_account(db, "other", "correct horse", "teacher")
    _sign_in(client, username=role)

    assert (
        client.post(f"/staff/accounts/{account_id}/stand-in/grant").status_code == 403
    )


def test_stand_in_gets_403_on_accounts_and_keys_and_settings(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    account_id = create_account(db, "teacher", "correct horse", "teacher")
    _sign_in(client)
    client.post(f"/staff/accounts/{account_id}/stand-in/grant")
    client.post("/staff/logout")

    _sign_in(client, username="teacher")
    assert client.get("/staff/accounts").status_code == 403
    assert client.get("/staff/keys").status_code == 403
    assert client.get("/staff/settings").status_code == 403


def test_librarian_sees_accounts_and_keys_pages(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    create_account(db, "teacher", "correct horse", "teacher")
    _sign_in(client)

    accounts = client.get("/staff/accounts")
    assert accounts.status_code == 200
    assert "teacher" in accounts.text

    keys = client.get("/staff/keys")
    assert keys.status_code == 200
    assert REGISTRATION_KEY in keys.text


def test_setup_creates_librarian(client, db):
    response = client.post(
        "/staff/setup",
        data={
            "username": "librarian",
            "password": "correct horse",
            "password_again": "correct horse",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/staff"
    assert STAFF_SESSION_COOKIE in response.cookies
    row = db.execute("SELECT username, role FROM staff_accounts").fetchone()
    assert row == ("librarian", "librarian")


def test_setup_is_404_once_an_account_exists(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    assert client.get("/staff/setup").status_code == 404
    response = client.post(
        "/staff/setup",
        data={
            "username": "someone",
            "password": "pw",
            "password_again": "pw",
        },
    )
    assert response.status_code == 404


def test_setup_refuses_mismatched_passwords(client, db):
    response = client.post(
        "/staff/setup",
        data={
            "username": "librarian",
            "password": "correct horse",
            "password_again": "wrong horse",
        },
    )
    assert response.status_code == 400
    assert db.execute("SELECT 1 FROM staff_accounts").fetchone() is None


def test_login_redirects_to_setup_when_no_accounts(client):
    response = client.get("/staff/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/staff/setup"


def _username_exists(db, username):
    return (
        db.execute(
            "SELECT 1 FROM staff_accounts WHERE username = ?", (username,)
        ).fetchone()
        is not None
    )


def test_accounts_anonymous_401(client):
    assert client.get("/staff/accounts").status_code == 401
    response = client.post(
        "/staff/accounts",
        data={"username": "new", "password": "pw", "role": "teacher"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("role", ["teacher", "counselor"])
def test_teacher_cannot_add_account_403(client, db, role):
    create_account(db, "librarian", "correct horse", "librarian")
    create_account(db, role, "correct horse", role)
    _sign_in(client, username=role)

    response = client.post(
        "/staff/accounts",
        data={"username": "newteacher", "password": "pw", "role": "teacher"},
    )

    assert response.status_code == 403
    assert not _username_exists(db, "newteacher")


def test_librarian_adds_teacher_and_counselor(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    for username, role in [("newteacher", "teacher"), ("newcounselor", "counselor")]:
        response = client.post(
            "/staff/accounts",
            data={"username": username, "password": "pw", "role": role},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/staff/accounts"

    roles = dict(db.execute("SELECT username, role FROM staff_accounts").fetchall())
    assert roles["newteacher"] == "teacher"
    assert roles["newcounselor"] == "counselor"
    text = client.get("/staff/accounts").text
    assert "newteacher" in text
    assert "newcounselor" in text
    assert '<form method="post" action="/staff/accounts">' in text


def test_accounts_page_shows_no_password_hash(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    create_account(db, "teacher", "correct horse", "teacher")
    _sign_in(client)

    response = client.get("/staff/accounts")

    assert response.status_code == 200
    assert "scrypt$" not in response.text
    for (password_hash,) in db.execute("SELECT password_hash FROM staff_accounts"):
        assert password_hash not in response.text


@pytest.mark.parametrize("role", ["librarian", "admin"])
def test_add_librarian_role_is_400(client, db, role):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)

    response = client.post(
        "/staff/accounts",
        data={"username": "newlibrarian", "password": "pw", "role": role},
    )

    assert response.status_code == 400
    assert not _username_exists(db, "newlibrarian")


def test_add_account_duplicate_username_409(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    data = {"username": "newteacher", "password": "pw", "role": "teacher"}

    first = client.post("/staff/accounts", data=data, follow_redirects=False)
    assert first.status_code == 303
    assert client.post("/staff/accounts", data=data).status_code == 409


def test_accounts_page_escapes_username(client, db):
    create_account(db, "librarian", "correct horse", "librarian")
    _sign_in(client)
    client.post(
        "/staff/accounts",
        data={
            "username": "<script>alert(1)</script>",
            "password": "pw",
            "role": "teacher",
        },
    )

    text = client.get("/staff/accounts").text

    assert "<script>" not in text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
