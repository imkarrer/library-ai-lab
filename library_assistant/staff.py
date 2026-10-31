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
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from library_assistant.access import (
    get_clock,
    get_db,
    hash_token,
    issue_registration_key,
)
from library_assistant.config import Settings
from library_assistant.dependencies import get_settings
from library_assistant.minting_page import download_filename, filled_minting_page
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
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/library.css">
<title>{title} - Library Assistant</title>
</head>
<body>
{body}
</body>
</html>
"""

# The sign-in, first-run setup, and "please sign in" pages: one centred card. The mark is
# an open book in the page's own colour (currentColor), so it carries no colour of its own.
AUTH_MARK = (
    '<svg class="auth-mark" viewBox="0 0 48 48" aria-hidden="true">'
    '<path d="M24 12c-4-3-10-4-16-3v26c6-1 12 0 16 3 4-3 10-4 16-3V9c-6-1-12 0-16 3z" '
    'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/>'
    '<path d="M24 12v26" stroke="currentColor" stroke-width="2.5"/></svg>'
)


def _auth_card(heading: str, lede: str, inner: str) -> str:
    return (
        '<div class="auth"><div class="auth-card">'
        f'<div class="auth-brand">{AUTH_MARK}<span>Library Assistant</span></div>'
        f"<h1>{heading}</h1>"
        f'<p class="auth-lede">{lede}</p>'
        f"{inner}"
        "</div>"
        '<p class="auth-foot">Staff only. Students sign in by scanning their Card.</p>'
        "</div>"
    )


LOGIN_FORM = _auth_card(
    "Staff sign-in",
    "Sign in to watch Sessions, work Flags, and make Cards.",
    '<div class="auth-message" role="alert">{message}</div>'
    '<form class="auth-form" method="post" action="/staff/login">'
    '<input type="hidden" name="next" value="{next}">'
    '<label>Username <input name="username" autocomplete="username" required autofocus>'
    "</label>"
    '<label>Password <input name="password" type="password"'
    ' autocomplete="current-password" required></label>'
    "<button>Sign in</button>"
    "</form>",
)

SETUP_FORM = _auth_card(
    "Create the librarian account",
    "The first account on this Install. It manages the others, and it cannot be removed.",
    '<div class="auth-message" role="alert">{message}</div>'
    '<form class="auth-form" method="post" action="/staff/setup">'
    '<label>Username <input name="username" autocomplete="username" required autofocus>'
    "</label>"
    '<label>Password <input name="password" type="password"'
    ' autocomplete="new-password" required></label>'
    '<label>Password again <input name="password_again" type="password"'
    ' autocomplete="new-password" required></label>'
    "<button>Create account</button>"
    "</form>",
)

SIGN_IN_FIRST = _auth_card(
    "Please sign in",
    "This page is for staff. Sign in first, then come back.",
    '<p><a class="auth-button" href="/staff/login{query}">Go to sign-in</a></p>',
)


def _safe_next(path: str | None) -> str:
    """Where to go after signing in: a staff page of this assistant, never another site."""
    if path and path.startswith("/staff/") and "\\" not in path:
        return path
    return "/staff"


# Which top-bar link a page belongs to, by its title.
_SECTION_OF_TITLE = {
    "Live view": "/staff/live",
    "Session Detail": "/staff/live",
    "Flag queue": "/staff/flags",
    "Flag": "/staff/flags",
    "Counselor flag queue": "/staff/counselor",
    "Staff accounts": "/staff/accounts",
    "Registration keys": "/staff/keys",
    "New registration key": "/staff/keys",
    "Holds": "/staff/holds",
    "Catalog": "/staff/catalog",
    "Install settings": "/staff/settings",
    "IT kit": "/staff/settings",
    "Staff": "/staff",
}


def nav_links(account: StaffAccount) -> list[tuple[str, str]]:
    """The pages this account may open, as (label, href): one list for the top bar and
    the /staff home, so a role never sees a link it would be refused."""
    links: list[tuple[str, str]] = []
    if account.role == "librarian" or account.is_stand_in:
        links += [("Live view", "/staff/live"), ("Flags", "/staff/flags")]
    if account.role == "counselor":
        links.append(("Escalated Flags", "/staff/counselor"))
    if account.role == "librarian":
        links += [
            ("Accounts", "/staff/accounts"),
            ("Keys", "/staff/keys"),
            ("Holds", "/staff/holds"),
            ("Catalog", "/staff/catalog"),
            ("Settings", "/staff/settings"),
        ]
    return links


# One line under each /staff home card: what that page is for.
_HOME_CARD_TEXT = {
    "/staff/live": "Start watch, and see every Session and open Flag as it happens.",
    "/staff/flags": "Every open Flag: Acknowledge, export, Escalate, and close.",
    "/staff/counselor": "The Flags Escalated to you, to resolve and close.",
    "/staff/accounts": "Add Teachers and Counselors; grant Stand-in.",
    "/staff/keys": "Registration keys, and each Teacher's Minting page.",
    "/staff/holds": "Keep an exchange past the Purge for a records request.",
    "/staff/catalog": "Load your library's books from your library system.",
    "/staff/settings": "Supervision mode, Watch grace, the Alarm chime.",
    "/staff/supportive-replies-preview": "What a Student sees instead of an answer.",
    "/staff/it-kit": "HTTPS for Chromebooks: what district IT needs, filled in.",
}


def _topbar(account: StaffAccount, title: str) -> str:
    current = _SECTION_OF_TITLE.get(title)
    items = "".join(
        f'<a href="{href}"{' aria-current="page"' if href == current else ""}>'
        f"{html.escape(label)}</a>"
        for label, href in nav_links(account)
    )
    return (
        '<header class="topbar">'
        '<a class="brand" href="/staff">Library Assistant</a>'
        f'<nav class="nav" aria-label="Staff pages">{items}</nav>'
        f'<div class="me"><span>{html.escape(account.username)} &middot; {account.role}'
        "</span>"
        '<form method="post" action="/staff/logout"><button class="link">Sign out'
        "</button></form></div>"
        "</header>"
    )


def page(
    title: str,
    body: str,
    status_code: int = 200,
    *,
    account: StaffAccount | None = None,
    db: sqlite3.Connection | None = None,
    now: datetime | None = None,
    wide: bool = False,
) -> HTMLResponse:
    """Any staff page. Pass `account`, `db`, and `now` for a signed-in page so it
    carries the top bar and the Alarm (or, for a Counselor, the Escalation banner) from
    `alarm_banner.alarm_banner` (decision lib-f24.77, ADR-0010). `wide` gives a page with
    columns (the Live view) the whole window."""
    # Imported here, not at module level: alarm_banner -> alarms -> install_settings -> staff.
    from library_assistant.alarm_banner import alarm_banner

    banner = alarm_banner(db, account, now) if account is not None else ""
    topbar = _topbar(account, title) if account is not None else ""
    main_class = "page wide" if wide else "page"
    return HTMLResponse(
        PAGE_HTML.format(
            title=html.escape(title),
            body=f'{topbar}<main class="{main_class}">{banner}{body}</main>',
        ),
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
        SIGN_IN_FIRST.format(
            # Back to the page that asked, such as the Make Cards app.
            query="?next=" + urllib.parse.quote(request.url.path)
            if request.method == "GET" and _safe_next(request.url.path) != "/staff"
            else ""
        ),
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
    db: sqlite3.Connection, account_id: int, clock: datetime, next_path: str = "/staff"
) -> RedirectResponse:
    """Open a staff session for the account and send them to `next_path`."""
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
    response = RedirectResponse(_safe_next(next_path), status_code=303)
    response.set_cookie(
        key=STAFF_SESSION_COOKIE, value=session_id, httponly=True, samesite="strict"
    )
    return response


@router.get("/login", response_model=None)
def login_page(
    db: sqlite3.Connection = Depends(get_db),
    next: str | None = None,
) -> HTMLResponse | RedirectResponse:
    if not _any_staff_account_exists(db):
        return RedirectResponse("/staff/setup", status_code=303)
    return page(
        "Sign in", LOGIN_FORM.format(message="", next=html.escape(_safe_next(next)))
    )


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
    next: Annotated[str | None, Form()] = None,
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
            LOGIN_FORM.format(
                message="<p>Wrong username or password.</p>",
                next=html.escape(_safe_next(next)),
            ),
            status_code=401,
        )
    return _sign_in(db, row[0], clock, _safe_next(next))


@router.post("/logout")
async def logout(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    session_id = request.cookies.get(STAFF_SESSION_COOKIE)
    if session_id:
        session_hash = hash_token(session_id)
        row = db.execute(
            "SELECT account_id FROM staff_sessions WHERE session_hash = ?",
            (session_hash,),
        ).fetchone()
        if row is not None:
            account_id = row[0]
            # Check if this account is the last watcher
            from library_assistant.watch import watchers_count

            if watchers_count(db) == 1:
                # Wait for in-flight screens to settle before ending the watch
                from library_assistant.routers.session import screens_settled

                await screens_settled(settings.oversight_timeout_seconds)
            # Signing out ends this account's Watch; other watchers keep it (ADR-0010).
            end_watch(db, account_id)
        db.execute("DELETE FROM staff_sessions WHERE session_hash = ?", (session_hash,))
        db.commit()
    response = RedirectResponse("/staff/login", status_code=303)
    response.delete_cookie(STAFF_SESSION_COOKIE, httponly=True, samesite="strict")
    return response


@router.get("")
def staff_home(
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    links_html = "".join(
        f'<a class="home-card" href="{href}"><strong>{html.escape(label)}</strong>'
        f"<span>{_HOME_CARD_TEXT.get(href, '')}</span></a>"
        for label, href in [
            *nav_links(account),
            ("Supportive reply preview", "/staff/supportive-replies-preview"),
            *([("IT kit", "/staff/it-kit")] if account.role == "librarian" else []),
        ]
    )
    links_html = f'<div class="home-grid">{links_html}</div>'

    # The accounts that mint (ADR-0002 addendum): their Minting page, filled in.
    minting_html = ""
    if account.role in MINTING_ROLES:
        minting_html = (
            '<section class="card-panel"><h2>Make Cards</h2>'
            "<p>Make your class's Cards on your own computer. The names you type stay "
            "on it: the assistant only learns each Card's fingerprint. Chrome or Edge "
            "can install Make Cards as an app, so it opens from your shelf, Dock, or "
            "Start menu.</p>"
            '<p><a class="button-link" href="/staff/mint/">Open Make Cards</a></p>'
            "<details><summary>Or download a Minting page to use offline</summary>"
            "<p>A file with this assistant's address and a new Registration key built "
            "in. Keep it to yourself; one you downloaded before stops working.</p>"
            '<form method="post" action="/staff/minting-page">'
            '<button class="secondary">Download my Minting page</button></form>'
            "</details></section>"
        )

    requests_html = _identification_requests_html(db, account)

    return page(
        "Staff",
        f"<h1>Welcome, {html.escape(account.username)}</h1>"
        f'<p class="lede">Signed in as {html.escape(account.username)} ({account.role}).</p>'
        f"{requests_html}"
        f"{minting_html}"
        f"{links_html}",
        account=account,
        db=db,
        now=clock,
    )


def _identification_requests_html(db: sqlite3.Connection, account: StaffAccount) -> str:
    """The questions waiting for this Teacher: who held a Card (lib-axb). The answer is a
    name, so it is given in person; here the Teacher only says that they have."""
    from library_assistant.identification import open_requests_for

    requests = open_requests_for(db, account.id)
    if not requests:
        return ""
    items = "".join(
        '<li class="id-request">'
        f"<p><strong>{html.escape(r.requested_by)}</strong> ({html.escape(r.requested_by_role)})"
        f" needs to know who held <strong>{html.escape(r.class_label)} &middot; card "
        f"{html.escape(r.card_number)}</strong>.</p>"
        + (
            '<p class="urgent">This is urgent: go and find them now.</p>'
            if r.severity == "high"
            else ""
        )
        + f'<form method="post" action="/staff/identification/{r.id}/answer">'
        '<button name="answer" value="told">I\'ve told them</button> '
        '<button name="answer" value="not_in_rosters" class="secondary">'
        "Not in my Rosters</button></form></li>"
        for r in requests
    )
    return (
        '<section class="card-panel id-requests"><h2>Who held these Cards?</h2>'
        "<p>Open your Minting page: it shows each name from the Roster on your computer "
        "(or use Find a Card). Tell the person asking, in person. Never type a name into "
        "the assistant.</p>"
        f'<ul class="id-list">{items}</ul></section>'
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
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
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
    return page("Staff accounts", body, account=account, db=db, now=clock)


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
        f"<td>{_minting_page_form(account_id, role)}</td>"
        "</tr>"
    )


# The roles that mint Batches (ADR-0002 addendum): a Counselor never does.
MINTING_ROLES = ("librarian", "teacher")


def _minting_page_form(account_id: int, role: str) -> str:
    if role not in MINTING_ROLES:
        return ""
    return (
        f'<form method="post" action="/staff/accounts/{account_id}/minting-page">'
        "<button>Download Minting page (new key)</button></form>"
    )


def _minting_page_download(
    request: Request,
    db: sqlite3.Connection,
    account_id: int,
    username: str,
    clock,
    settings: Settings,
) -> Response:
    """Rotate `account_id`'s key and send its filled Minting page as a download.

    The key is stored only as a hash, so the page needs a new one: issuing it here is
    what makes every earlier copy of this account's page stop registering.
    """
    key = issue_registration_key(db, account_id, clock)
    return Response(
        filled_minting_page(
            str(request.base_url), username, key, settings.school_day_end
        ),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{download_filename(username)}"'
            ),
            # The page holds a live key: no browser or proxy keeps a copy.
            "Cache-Control": "no-store",
        },
    )


@router.get("/keys")
def keys_page(
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
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
        "<table><thead><tr><th>Username</th><th>Role</th><th></th><th></th></tr>"
        "</thead><tbody>"
        f"{''.join(_key_row_html(row) for row in rows)}"
        "</tbody></table>"
        '<form method="post" action="/staff/key/rotate">'
        "<button>Rotate my own key</button></form>"
    )
    return page("Registration keys", body, account=account, db=db, now=clock)


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
        account=account,
        db=db,
        now=clock,
    )


@router.post("/accounts/{account_id}/minting-page", response_model=None)
def account_minting_page_route(
    account_id: int,
    request: Request,
    account: LibrarianDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Librarian-only: a Teacher's Minting page with a new key, to hand to them."""
    row = db.execute(
        "SELECT username, role FROM staff_accounts WHERE id = ? AND is_active = 1",
        (account_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such account")
    if row[1] not in MINTING_ROLES:
        raise HTTPException(status_code=400, detail="a Counselor does not make Cards")
    return _minting_page_download(request, db, account_id, row[0], clock, settings)


@router.post("/identification/{request_id}/answer", response_model=None)
def answer_identification_route(
    request_id: int,
    account: StaffDep,
    answer: str = Form(...),
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> RedirectResponse:
    """A Teacher answers their own request: told, or not in their Rosters. No name."""
    from library_assistant.identification import answer as answer_request

    if answer_request(db, request_id, account.id, answer, clock) is None:
        raise HTTPException(status_code=404, detail="no open request of yours")
    return RedirectResponse("/staff", status_code=303)


@router.post("/minting-page", response_model=None)
def own_minting_page_route(
    request: Request,
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> Response:
    """A Teacher's (or the Librarian's) own Minting page, with a new key."""
    if account.role not in MINTING_ROLES:
        raise HTTPException(status_code=403, detail="a Counselor does not make Cards")
    return _minting_page_download(
        request, db, account.id, account.username, clock, settings
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
        account=account,
        db=db,
        now=clock,
    )


@router.get("/supportive-replies-preview")
def supportive_replies_preview(
    account: StaffDep,
    db: sqlite3.Connection = Depends(get_db),
    clock: datetime = Depends(get_clock),
) -> HTMLResponse:
    """Staff-only: preview of all supportive replies rendered with Install overrides."""
    from library_assistant.supportive_replies import (
        PRECEDENCE_ORDER,
        get_supportive_reply_text,
        install_overrides,
    )

    counselor_name, overrides = install_overrides(db)

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
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="stylesheet" href="/library.css">
        <title>Supportive Replies Preview - Library Assistant</title>
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

    from library_assistant.alarm_banner import alarm_banner

    preview_html = preview_html.replace(
        "<body>", f"<body>\n{alarm_banner(db, account, clock)}", 1
    )
    return HTMLResponse(preview_html, headers={"Cache-Control": "no-store"})
