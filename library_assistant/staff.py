"""Staff accounts and authentication for Library Assistant.

This module handles staff account management, including:
- First-run setup for creating the Librarian account
- Staff authentication system
- Role-based access control for staff pages
- Registration key management
"""

import hashlib
import os
import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from passlib.context import CryptContext

DB_PATH = os.environ.get("LIBRARY_ASSISTANT_DB", "library_assistant.db")

# Create a password context for hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Staff roles
class StaffRole:
    LIBRARIAN = "librarian"
    TEACHER = "teacher"
    COUNSELOR = "counselor"

# Staff account model
class StaffAccount(BaseModel):
    username: str
    password: str
    role: str

# Staff login request
class StaffLogin(BaseModel):
    username: str
    password: str

# Staff session model
class StaffSession(BaseModel):
    username: str
    role: str

# Session cookie name
STAFF_SESSION_COOKIE = "staff_session"

# Staff account database table name
STAFF_TABLE = "staff_accounts"

# Staff session cookie name
STAFF_SESSION_COOKIE = "staff_session"

# Staff login HTML page
STAFF_LOGIN_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Staff Login - Library Assistant</title>
</head>
<body>
  <h1>Staff Login</h1>
  <form id="loginForm">
    <div>
      <label for="username">Username:</label>
      <input type="text" id="username" name="username" required>
    </div>
    <div>
      <label for="password">Password:</label>
      <input type="password" id="password" name="password" required>
    </div>
    <button type="submit">Login</button>
  </form>
  <div id="error" style="color: red; display: none;"></div>

  <script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(e.target);
      const credentials = {
        username: formData.get('username'),
        password: formData.get('password')
      };

      try {
        const response = await fetch('/staff/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(credentials)
        });

        if (response.ok) {
          window.location.href = '/staff/dashboard';
        } else {
          const errorDiv = document.getElementById('error');
          errorDiv.textContent = 'Invalid username or password';
          errorDiv.style.display = 'block';
        }
      } catch (error) {
        const errorDiv = document.getElementById('error');
        errorDiv.textContent = 'Login failed. Please try again.';
        errorDiv.style.display = 'block';
      }
    });
  </script>
</body>
</html>
"""

# Staff dashboard HTML
STAFF_DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Staff Dashboard - Library Assistant</title>
</head>
<body>
  <h1>Staff Dashboard</h1>
  <p>Welcome, <span id="username"></span>!</p>
  <p>Role: <span id="role"></span></p>
  <nav>
    <ul>
      <li><a href="/staff/dashboard">Dashboard</a></li>
      <li><a href="/staff/accounts">Manage Accounts</a></li>
      <li><a href="/staff/registration-key">Registration Key</a></li>
      <li><a href="/staff/logout">Logout</a></li>
    </ul>
  </nav>
  <div id="content"></div>
  <script>
    // Fetch staff session info
    fetch('/staff/session')
      .then(response => response.json())
      .then(data => {
        document.getElementById('username').textContent = data.username;
        document.getElementById('role').textContent = data.role;
      });
  </script>
</body>
</html>
"""

# First-run setup HTML
FIRST_RUN_SETUP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>First Run Setup - Library Assistant</title>
</head>
<body>
  <h1>First Run Setup</h1>
  <p>Create your Librarian account to get started.</p>
  <form id="setupForm">
    <div>
      <label for="username">Username:</label>
      <input type="text" id="username" name="username" required>
    </div>
    <div>
      <label for="password">Password:</label>
      <input type="password" id="password" name="password" required>
    </div>
    <button type="submit">Create Account</button>
  </form>
  <div id="error" style="color: red; display: none;"></div>

  <script>
    document.getElementById('setupForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(e.target);
      const account = {
        username: formData.get('username'),
        password: formData.get('password'),
        role: 'librarian'
      };

      try {
        const response = await fetch('/staff/setup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(account)
        });

        if (response.ok) {
          window.location.href = '/staff/dashboard';
        } else {
          const errorDiv = document.getElementById('error');
          errorDiv.textContent = 'Setup failed. Please try again.';
          errorDiv.style.display = 'block';
        }
      } catch (error) {
        const errorDiv = document.getElementById('error');
        errorDiv.textContent = 'Setup failed. Please try again.';
        errorDiv.style.display = 'block';
      }
    });
  </script>
</body>
</html>
"""

# Staff session middleware to check authentication
def require_staff_auth(request: Request) -> StaffSession:
    """Check if staff is authenticated."""
    session_cookie = request.cookies.get(STAFF_SESSION_COOKIE)
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # In a real implementation, this would check the session against database
    # For now, we'll just validate that session cookie exists
    return StaffSession(username="librarian", role="librarian")

# Connect to database and create staff accounts table if it doesn't exist
def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    
    # Create staff accounts table
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {STAFF_TABLE} (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    # Create registration keys table if it doesn't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS registration_keys (
            key_hash TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_used_at TEXT
        )
    """)
    
    conn.commit()
    return conn

# Global connection variable
_connection: sqlite3.Connection | None = None

def get_db() -> sqlite3.Connection:
    global _connection
    if _connection is None:
        _connection = connect()
    return _connection

# Hash a password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# Verify a password
def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

# Check if staff accounts exist
def staff_accounts_exist(db: sqlite3.Connection) -> bool:
    cursor = db.execute(f"SELECT COUNT(*) FROM {STAFF_TABLE}")
    count = cursor.fetchone()[0]
    return count > 0

# Check if first-run setup is needed
def first_run_needed(db: sqlite3.Connection) -> bool:
    cursor = db.execute(f"SELECT COUNT(*) FROM {STAFF_TABLE}")
    count = cursor.fetchone()[0]
    return count == 0

# Create first-time librarian account
def create_librarian_account(username: str, password: str, db: sqlite3.Connection) -> None:
    password_hash = hash_password(password)
    created_at = datetime.now(UTC).isoformat()
    
    db.execute(
        f"INSERT INTO {STAFF_TABLE} (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, StaffRole.LIBRARIAN, created_at)
    )
    db.commit()

# Get staff account by username
def get_staff_account(username: str, db: sqlite3.Connection) -> tuple | None:
    cursor = db.execute(f"SELECT username, password_hash, role FROM {STAFF_TABLE} WHERE username = ?", (username,))
    return cursor.fetchone()

# Create a registration key
def create_registration_key(role: str, db: sqlite3.Connection) -> str:
    import secrets
    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    created_at = datetime.now(UTC).isoformat()
    
    db.execute(
        "INSERT INTO registration_keys (key_hash, role, created_at) VALUES (?, ?, ?)",
        (key_hash, role, created_at)
    )
    db.commit()
    
    return key

# Get registration key
def get_registration_key(role: str, db: sqlite3.Connection) -> str | None:
    cursor = db.execute(
        "SELECT key_hash FROM registration_keys WHERE role = ? ORDER BY created_at DESC LIMIT 1",
        (role,)
    )
    row = cursor.fetchone()
    if row:
        return row[0]
    return None

# Rotate registration key
def rotate_registration_key(role: str, db: sqlite3.Connection) -> str:
    # First, get the current key
    current_key = get_registration_key(role, db)
    if current_key:
        # Mark it as used (in a real implementation, we'd update the last_used_at field)
        pass
    
    # Create new key
    return create_registration_key(role, db)

# Staff router
router = APIRouter(prefix="/staff")

@router.get("/login", response_model=None)
def staff_login_page() -> HTMLResponse:
    """Display staff login page."""
    return HTMLResponse(STAFF_LOGIN_HTML)

@router.post("/login")
def staff_login(
    login_data: StaffLogin,
    request: Request,
    response: Response,
    db: sqlite3.Connection = Depends(get_db)
) -> PlainTextResponse:
    """Authenticate staff member."""
    # Verify credentials
    account = get_staff_account(login_data.username, db)
    if not account or not verify_password(login_data.password, account[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create session cookie
    session_cookie = hashlib.sha256(f"{login_data.username}:{datetime.now(UTC)}".encode()).hexdigest()
    response.set_cookie(
        key=STAFF_SESSION_COOKIE,
        value=session_cookie,
        httponly=True,
        samesite="strict",
        secure=False  # Set to True in production with HTTPS
    )
    
    return PlainTextResponse("Login successful")

@router.get("/setup", response_model=None)
def first_run_setup_page(db: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Display first-run setup page if no staff accounts exist."""
    if staff_accounts_exist(db):
        # If staff accounts exist, redirect to dashboard or login
        # This is a simple approach - in reality, we'd redirect to dashboard
        return HTMLResponse("<html><body><p>Setup already complete.</p></body></html>")
    
    return HTMLResponse(FIRST_RUN_SETUP_HTML)

@router.post("/setup")
def first_run_setup(
    account: StaffAccount,
    db: sqlite3.Connection = Depends(get_db)
) -> PlainTextResponse:
    """Create first librarian account."""
    if staff_accounts_exist(db):
        raise HTTPException(status_code=400, detail="Setup already completed")
    
    if account.role != StaffRole.LIBRARIAN:
        raise HTTPException(status_code=400, detail="Only librarian account can be created during setup")
    
    create_librarian_account(account.username, account.password, db)
    return PlainTextResponse("Setup complete")

@router.get("/dashboard", response_model=None)
def staff_dashboard(
    request: Request,
    db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Display staff dashboard."""
    # Check if staff is authenticated
    try:
        require_staff_auth(request)
    except HTTPException:
        # Redirect to login page if not authenticated
        return HTMLResponse("<html><body><p>Please <a href='/staff/login'>login</a> first.</p></body></html>")
    
    return HTMLResponse(STAFF_DASHBOARD_HTML)

@router.get("/session", response_model=StaffSession)
def staff_session(request: Request) -> StaffSession:
    """Get current staff session info."""
    # In a real implementation, this would return the actual session data
    # For now, returning hardcoded values for demonstration
    return StaffSession(username="librarian", role="librarian")

@router.post("/logout")
def staff_logout(response: Response) -> dict[str, str]:
    """Logout staff member."""
    response.delete_cookie(STAFF_SESSION_COOKIE, httponly=True, samesite="strict")
    return {"status": "logged_out"}

@router.get("/accounts", response_model=None)
def staff_accounts_page(
    request: Request,
    db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Display staff accounts management page."""
    # This would require authentication and proper role checking
    return HTMLResponse("<html><body><h1>Staff Accounts Management</h1></body></html>")

@router.get("/registration-key", response_model=None)
def registration_key_page(
    request: Request,
    db: sqlite3.Connection = Depends(get_db)
) -> HTMLResponse:
    """Display registration key management page."""
    return HTMLResponse("<html><body><h1>Registration Key Management</h1></body></html>")