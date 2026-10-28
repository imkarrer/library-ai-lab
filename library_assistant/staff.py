"""Staff accounts: password sign-in, the staff session, and role guards.

Decision lib-f24.22: passwords are hashed with the standard library's scrypt, staff pages
are plain HTML forms, and the `staff_session` cookie is stored only as its hash, the way a
Student's Session is. A Student's `session` cookie never opens a staff page. Registration
keys are not part of staff accounts (lib-90j.1).
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import html
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from library_assistant.access import get_clock, get_db, get_registration_key, hash_token

STAFF_SESSION_COOKIE = "staff_session"
STAFF_SESSION_LIFETIME = timedelta(hours=12)

ROLES = ("librarian", "teacher", "counselor")

# 16 MiB of memory per hash, inside hashlib's default 32 MiB limit.
_SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1}

PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title} - Library Assistant</title>
</head>
<body>
{body}
</body>
</html>
"""

LOGIN_FORM = """<h1>Staff sign-in</h1>
{message}
<form method="post" action="/staff/login">
  <p><label>Username <input name="username" autocomplete="username" required></label></p>
  <p><label>Password <input name="password" type="password"
     autocomplete="current-password" required></label></p>
  <p><button>Sign in</button></p>
</form>"""

SETUP_FORM = """<h1>Create the librarian account</h1>
{message}
<form method="post" action="/staff/setup">
  <p><label>Username <input name="username" autocomplete="username" required></label></p>
  <p><label>Password <input name="password" type="password"
     autocomplete="new-password" required></label></p>
  <p><label>Password again <input name="password_again" type="password"
     autocomplete="new-password" required></label></p>
  <p><button>Create account</button></p>
</form>"""


def page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        PAGE_HTML.format(title=html.escape(title), body=body), status_code=status_code
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT_PARAMS)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT_PARAMS)
    return hmac.compare_digest(digest.hex(), digest_hex)


@functools.cache
def _unknown_user_hash() -> str:
    """Checked when the username is unknown, so a wrong name costs as long as a wrong password."""
    return hash_password(secrets.token_urlsafe(16))


def create_account(
    db: sqlite3.Connection, username: str, password: str, role: str
) -> int:
    if role not in ROLES:
        raise ValueError(f"unknown role: {role!r}")
    cursor = db.execute(
        "INSERT INTO staff_accounts (username, password_hash, role, created_at) "
        "VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, datetime.now(UTC).isoformat()),
    )
    db.commit()
    return cursor.lastrowid


@dataclass(frozen=True)
class StaffAccount:
    id: int
    username: str
    role: str
    is_stand_in: bool = False


class StaffSignInRequired(Exception):
    """No valid staff session. Answered with 401 and a link to the sign-in page."""


def sign_in_required_handler(
    request: Request, exc: StaffSignInRequired
) -> HTMLResponse:
    return page(
        "Sign in",
        '<p>Please <a href="/staff/login">sign in</a> first.</p>',
        status_code=401,
    )


def current_staff(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> StaffAccount:
    """The staff account this request's `staff_session` cookie names, or 401."""
    session_id = request.cookies.get(STAFF_SESSION_COOKIE)
    if not session_id:
        raise StaffSignInRequired
    row = db.execute(
        "SELECT staff_accounts.id, staff_accounts.username, staff_accounts.role, "
        "staff_accounts.is_stand_in, staff_sessions.expires_at "
        "FROM staff_sessions JOIN staff_accounts "
        "ON staff_accounts.id = staff_sessions.account_id "
        "WHERE staff_sessions.session_hash = ?",
        (hash_token(session_id),),
    ).fetchone()
    if row is None:
        raise StaffSignInRequired
    account_id, username, role, is_stand_in, expires_at = row
    if clock >= datetime.fromisoformat(expires_at):
        raise StaffSignInRequired
    return StaffAccount(
        id=account_id, username=username, role=role, is_stand_in=bool(is_stand_in)
    )


StaffDep = Annotated[StaffAccount, Depends(current_staff)]


def require_role(*roles: str) -> Callable[..., StaffAccount]:
    """A dependency that lets through only signed-in staff with one of `roles`, else 403."""

    def dependency(account: StaffDep) -> StaffAccount:
        if account.role not in roles:
            raise HTTPException(status_code=403, detail="not available to your role")
        return account

    return dependency


# Route parameters use these, so ruff B008 sees no call in an argument default.
LibrarianDep = Annotated[StaffAccount, Depends(require_role("librarian"))]


def require_watch_access() -> Callable[..., StaffAccount]:
    """Lets through the Librarian or a Stand-in; everyone else gets 403 (ADR-0010)."""

    def dependency(account: StaffDep) -> StaffAccount:
        if account.role != "librarian" and not account.is_stand_in:
            raise HTTPException(status_code=403, detail="not available to your role")
        return account

    return dependency


StandInDep = Annotated[StaffAccount, Depends(require_watch_access())]


def set_stand_in(db: sqlite3.Connection, account_id: int, is_stand_in: bool) -> None:
    """Grant or revoke the Stand-in role on a staff account (ADR-0010)."""
    cursor = db.execute(
        "UPDATE staff_accounts SET is_stand_in = ? WHERE id = ?",
        (1 if is_stand_in else 0, account_id),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="no such account")
    db.commit()


router = APIRouter(prefix="/staff")


def _any_staff_account_exists(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM staff_accounts LIMIT 1").fetchone() is not None


def _sign_in(
    db: sqlite3.Connection, account_id: int, clock: datetime
) -> RedirectResponse:
    """Open a staff session for the account and send them to /staff."""
    session_id = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO staff_sessions (session_hash, account_id, expires_at) "
        "VALUES (?, ?, ?)",
        (
            hash_token(session_id),
            account_id,
            (clock + STAFF_SESSION_LIFETIME).isoformat(),
        ),
    )
    db.commit()
    response = RedirectResponse("/staff", status_code=303)
    response.set_cookie(
        key=STAFF_SESSION_COOKIE, value=session_id, httponly=True, samesite="strict"
    )
    return response


@router.get("/login", response_model=None)
def login_page(
    db: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if not _any_staff_account_exists(db):
        return RedirectResponse("/staff/setup", status_code=303)
    return page("Sign in", LOGIN_FORM.format(message=""))


@router.get("/setup", response_model=None)
def setup_page(db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    if _any_staff_account_exists(db):
        raise HTTPException(status_code=404)
    return page("Set up", SETUP_FORM.format(message=""))


@router.post("/setup", response_model=None)
def setup(
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    password_again: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse | RedirectResponse:
    if _any_staff_account_exists(db):
        raise HTTPException(status_code=404)
    if password != password_again:
        return page(
            "Set up",
            SETUP_FORM.format(message="<p>Passwords did not match.</p>"),
            status_code=400,
        )
    account_id = create_account(db, username, password, "librarian")
    return _sign_in(db, account_id, clock)


@router.post("/login", response_model=None)
def login(
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse | RedirectResponse:
    row = db.execute(
        "SELECT id, password_hash FROM staff_accounts WHERE username = ?", (username,)
    ).fetchone()
    stored = row[1] if row else _unknown_user_hash()
    if not verify_password(password, stored) or row is None:
        return page(
            "Sign in",
            LOGIN_FORM.format(message="<p>Wrong username or password.</p>"),
            status_code=401,
        )
    return _sign_in(db, row[0], clock)


@router.post("/logout")
def logout(
    request: Request, db: sqlite3.Connection = Depends(get_db)
) -> RedirectResponse:
    session_id = request.cookies.get(STAFF_SESSION_COOKIE)
    if session_id:
        db.execute(
            "DELETE FROM staff_sessions WHERE session_hash = ?",
            (hash_token(session_id),),
        )
        db.commit()
    response = RedirectResponse("/staff/login", status_code=303)
    response.delete_cookie(STAFF_SESSION_COOKIE, httponly=True, samesite="strict")
    return response


@router.get("")
def staff_home(account: StaffDep) -> HTMLResponse:
    return page(
        "Staff",
        f"<h1>Library Assistant staff</h1>"
        f"<p>Signed in as {html.escape(account.username)} ({account.role}).</p>"
        '<form method="post" action="/staff/logout"><button>Sign out</button></form>',
    )


def _account_row_html(row: tuple[int, str, str, int]) -> str:
    account_id, username, role, is_stand_in = row
    action = "revoke" if is_stand_in else "grant"
    return (
        "<tr>"
        f"<td>{html.escape(username)}</td>"
        f"<td>{html.escape(role)}</td>"
        f"<td>{'yes' if is_stand_in else 'no'}</td>"
        f'<td><form method="post" action="/staff/accounts/{account_id}/stand-in/{action}">'
        f"<button>{action.capitalize()} Stand-in</button></form></td>"
        "</tr>"
    )


@router.get("/accounts")
def accounts_page(
    account: LibrarianDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Librarian-only: grant or revoke Stand-in on any staff account (ADR-0010)."""
    rows = db.execute(
        "SELECT id, username, role, is_stand_in FROM staff_accounts ORDER BY username"
    ).fetchall()
    body = (
        "<h1>Staff accounts</h1>"
        "<table><thead><tr>"
        "<th>Username</th><th>Role</th><th>Stand-in</th><th></th>"
        "</tr></thead><tbody>"
        f"{''.join(_account_row_html(row) for row in rows)}"
        "</tbody></table>"
    )
    return page("Staff accounts", body)


@router.post("/accounts/{account_id}/stand-in/grant", response_model=None)
def grant_stand_in_route(
    account_id: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    set_stand_in(db, account_id, True)
    return RedirectResponse("/staff/accounts", status_code=303)


@router.post("/accounts/{account_id}/stand-in/revoke", response_model=None)
def revoke_stand_in_route(
    account_id: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    set_stand_in(db, account_id, False)
    return RedirectResponse("/staff/accounts", status_code=303)


@router.get("/keys")
def keys_page(
    account: LibrarianDep, key: str | None = Depends(get_registration_key)
) -> HTMLResponse:
    """Librarian-only: the Install's Registration key. Per-Teacher keys are lib-90j.1."""
    body = (
        "<h1>Registration key</h1>"
        f"<p>{html.escape(key) if key else 'No registration key is set.'}</p>"
    )
    return page("Registration key", body)
