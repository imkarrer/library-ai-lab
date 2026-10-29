"""Staff accounts: password sign-in, the staff session, and role guards.

Decision lib-f24.22: passwords are hashed with the standard library's scrypt, staff pages
are plain HTML forms, and the `staff_session` cookie is stored only as its hash, the way a
Student's Session is. A Student's `session` cookie never opens a staff page. Each account's
Registration key is a separate secret (ADR-0002 addendum, lib-90j): see
`library_assistant.access.issue_registration_key`.
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

from library_assistant.access import (
    get_clock,
    get_db,
    hash_token,
    issue_registration_key,
)
from library_assistant.watch import end_watch

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
        PAGE_HTML.format(title=html.escape(title), body=body),
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
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
        "WHERE staff_sessions.session_hash = ? AND staff_accounts.is_active = 1",
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


def deactivate_account(db: sqlite3.Connection, account_id: int) -> None:
    """Deactivate a Teacher or Counselor account (ADR-0002 addendum).

    Its Registration key is refused at once (`access.account_for_registration_key`
    checks the flag), it can no longer sign in to staff pages, and its open staff
    sessions and its Watch end now. Its row stays, so Batches it registered keep their reference.
    The Librarian account is never deactivated: the Install has no other way back in.
    """
    row = db.execute(
        "SELECT role FROM staff_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such account")
    if row[0] == "librarian":
        raise HTTPException(
            status_code=400, detail="the librarian account cannot be deactivated"
        )
    db.execute("UPDATE staff_accounts SET is_active = 0 WHERE id = ?", (account_id,))
    db.execute("DELETE FROM staff_sessions WHERE account_id = ?", (account_id,))
    db.commit()
    # As at sign-out, it stops being a watcher; others keep the Watch on (ADR-0010).
    end_watch(db, account_id)


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
        "SELECT id, password_hash, is_active FROM staff_accounts WHERE username = ?",
        (username,),
    ).fetchone()
    stored = row[1] if row else _unknown_user_hash()
    # A deactivated account gets the same answer as a wrong password, after the same work.
    if not verify_password(password, stored) or row is None or not row[2]:
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
        session_hash = hash_token(session_id)
        row = db.execute(
            "SELECT account_id FROM staff_sessions WHERE session_hash = ?",
            (session_hash,),
        ).fetchone()
        if row is not None:
            # Signing out ends this account's Watch; other watchers keep it (ADR-0010).
            end_watch(db, row[0])
        db.execute("DELETE FROM staff_sessions WHERE session_hash = ?", (session_hash,))
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


def _account_row_html(row: tuple[int, str, str, int, int]) -> str:
    account_id, username, role, is_stand_in, is_active = row
    action = "revoke" if is_stand_in else "grant"
    if not is_active:
        deactivate = "deactivated"
    elif role == "librarian":
        deactivate = ""
    else:
        deactivate = (
            f'<form method="post" action="/staff/accounts/{account_id}/deactivate">'
            "<button>Deactivate</button></form>"
        )
    return (
        "<tr>"
        f"<td>{html.escape(username)}</td>"
        f"<td>{html.escape(role)}</td>"
        f"<td>{'yes' if is_stand_in else 'no'}</td>"
        f'<td><form method="post" action="/staff/accounts/{account_id}/stand-in/{action}">'
        f"<button>{action.capitalize()} Stand-in</button></form></td>"
        f"<td>{deactivate}</td>"
        "</tr>"
    )


ADD_ACCOUNT_FORM = """<h2>Add an account</h2>
<form method="post" action="/staff/accounts">
  <p><label>Username <input name="username" required></label></p>
  <p><label>Password <input name="password" type="password"
     autocomplete="new-password" required></label></p>
  <p><label>Role <select name="role" required>
    <option value="teacher">Teacher</option>
    <option value="counselor">Counselor</option>
  </select></label></p>
  <p><button>Add account</button></p>
</form>"""

# Roles a Librarian may add here; a second Librarian is never added through this page.
ADDABLE_ROLES = ("teacher", "counselor")


@router.get("/accounts")
def accounts_page(
    account: LibrarianDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Librarian-only: list accounts (never a password hash), add a Teacher or
    Counselor, and grant or revoke Stand-in (ADR-0010)."""
    rows = db.execute(
        "SELECT id, username, role, is_stand_in, is_active FROM staff_accounts "
        "ORDER BY username"
    ).fetchall()
    body = (
        "<h1>Staff accounts</h1>"
        "<table><thead><tr>"
        "<th>Username</th><th>Role</th><th>Stand-in</th><th></th><th></th>"
        "</tr></thead><tbody>"
        f"{''.join(_account_row_html(row) for row in rows)}"
        "</tbody></table>"
        f"{ADD_ACCOUNT_FORM}"
    )
    return page("Staff accounts", body)


@router.post("/accounts", response_model=None)
def add_account_route(
    account: LibrarianDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()],
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    """Librarian-only: add a Teacher or Counselor account; anything else is 400."""
    if role not in ADDABLE_ROLES:
        raise HTTPException(status_code=400, detail="role must be teacher or counselor")
    try:
        create_account(db, username, password, role)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="username already taken") from None
    return RedirectResponse("/staff/accounts", status_code=303)


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


@router.post("/accounts/{account_id}/deactivate", response_model=None)
def deactivate_account_route(
    account_id: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
) -> RedirectResponse:
    """Librarian-only: deactivate a Teacher or Counselor; its key is refused at once."""
    deactivate_account(db, account_id)
    return RedirectResponse("/staff/accounts", status_code=303)


def _key_row_html(row: tuple[int, str, str]) -> str:
    account_id, username, role = row
    return (
        "<tr>"
        f"<td>{html.escape(username)}</td>"
        f"<td>{html.escape(role)}</td>"
        f'<td><form method="post" action="/staff/accounts/{account_id}/key/rotate">'
        "<button>Rotate key</button></form></td>"
        "</tr>"
    )


@router.get("/keys")
def keys_page(
    account: LibrarianDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Librarian-only: every account's Registration key, rotated here (ADR-0002 addendum).

    The key itself is never shown again after it is issued; this page only lists who
    holds one and lets the Librarian rotate it.
    """
    rows = db.execute(
        "SELECT id, username, role FROM staff_accounts ORDER BY username"
    ).fetchall()
    body = (
        "<h1>Registration keys</h1>"
        "<table><thead><tr><th>Username</th><th>Role</th><th></th></tr></thead><tbody>"
        f"{''.join(_key_row_html(row) for row in rows)}"
        "</tbody></table>"
        '<form method="post" action="/staff/key/rotate">'
        "<button>Rotate my own key</button></form>"
    )
    return page("Registration keys", body)


@router.post("/accounts/{account_id}/key/rotate", response_model=None)
def rotate_account_key_route(
    account_id: int,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    """Librarian-only: rotate any account's Registration key, shown once."""
    row = db.execute(
        "SELECT username FROM staff_accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such account")
    key = issue_registration_key(db, account_id, clock)
    return page(
        "New registration key",
        f"<h1>New Registration key for {html.escape(row[0])}</h1>"
        "<p>Shown once; it will not be shown again.</p>"
        f"<pre>{html.escape(key)}</pre>",
    )


@router.post("/key/rotate", response_model=None)
def rotate_own_key_route(
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    """Any signed-in staff account rotates its own Registration key, shown once."""
    key = issue_registration_key(db, account.id, clock)
    return page(
        "New registration key",
        "<h1>Your new Registration key</h1>"
        "<p>Shown once; it will not be shown again.</p>"
        f"<pre>{html.escape(key)}</pre>",
    )


@router.get("/supportive-replies-preview")
def supportive_replies_preview(
    account: StaffDep, db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Staff-only: preview of all supportive replies rendered with Install overrides."""
    from library_assistant.install_settings import get_setting
    from library_assistant.supportive_replies import (
        PRECEDENCE_ORDER,
        get_supportive_reply_text,
    )

    # Get counselor name from install settings or default
    counselor_name = get_setting(db, "counselor_name", "a school counselor")

    # Get overrides from install settings (if any)
    overrides = {}

    # Check for each category override
    for category in ["self_harm", "abuse", "bullying", "threats_of_violence"]:
        override_key = f"supportive_reply_{category}"
        override_text = get_setting(db, override_key, None)
        if override_text:
            overrides[category] = override_text

    # Generate all reply texts
    replies = {}
    for category in PRECEDENCE_ORDER:
        reply_text = get_supportive_reply_text(category, counselor_name, overrides)
        replies[category] = reply_text

    # Create HTML for the preview page
    preview_html = (
        """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Supportive Replies Preview - Library Assistant</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 2em auto; }
            .reply-section { 
                border: 1px solid #ccc; 
                padding: 1em; 
                margin-bottom: 1em; 
                background-color: #f9f9f9;
            }
            .reply-title { 
                font-weight: bold; 
                color: #333; 
                margin-bottom: 0.5em; 
            }
            .reply-content { 
                white-space: pre-wrap; 
                margin: 0; 
            }
            .print-button { 
                background-color: #007bff; 
                color: white; 
                border: none; 
                padding: 0.5em 1em; 
                cursor: pointer; 
                margin-bottom: 1em; 
            }
            .print-button:hover { 
                background-color: #0056b3; 
            }
            @media print {
                .no-print { display: none; }
            }
        </style>
    </head>
    <body>
        <h1>Supportive Replies Preview</h1>
        <p class="no-print">This preview shows how the supportive replies will appear to Students.</p>
        <p class="no-print">It uses the Install's overrides if any are configured.</p>
        
        <button class="print-button" onclick="window.print()">Print this page</button>
        
        <div class="reply-section">
            <div class="reply-title">Self-harm</div>
            <div class="reply-content">"""
        + html.escape(replies["self_harm"])
        + """</div>
        </div>
        
        <div class="reply-section">
            <div class="reply-title">Abuse</div>
            <div class="reply-content">"""
        + html.escape(replies["abuse"])
        + """</div>
        </div>
        
        <div class="reply-section">
            <div class="reply-title">Bullying</div>
            <div class="reply-content">"""
        + html.escape(replies["bullying"])
        + """</div>
        </div>
        
        <div class="reply-section">
            <div class="reply-title">Threats of violence</div>
            <div class="reply-content">"""
        + html.escape(replies["threats_of_violence"])
        + """</div>
        </div>
        
        <p class="no-print">Note: This preview does not raise Flags, write transcripts, or make model calls.</p>
    </body>
    </html>
    """
    )

    return HTMLResponse(preview_html, headers={"Cache-Control": "no-store"})
