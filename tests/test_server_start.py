"""`python -m library_assistant`, the one start command: its flags, and Ctrl-C with a Live
view open (a staff page's event stream never ends on its own)."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx

from library_assistant.__main__ import GRACEFUL_SHUTDOWN_SECONDS, server_options
from library_assistant.access import connect
from library_assistant.staff import create_account

REPO = Path(__file__).resolve().parent.parent


def test_server_options_keep_no_access_log_and_bound_shutdown():
    options = server_options({})
    assert options == {
        "host": "127.0.0.1",
        "port": 8000,
        "access_log": False,  # ADR-0003 addendum
        "timeout_graceful_shutdown": GRACEFUL_SHUTDOWN_SECONDS,
    }


def test_server_options_read_host_and_port():
    options = server_options(
        {"LIBRARY_ASSISTANT_HOST": "192.0.2.10", "LIBRARY_ASSISTANT_PORT": "8123"}
    )
    assert (options["host"], options["port"]) == ("192.0.2.10", 8123)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_ctrl_c_exits_promptly_with_a_live_view_stream_open(tmp_path):
    db_path = tmp_path / "install.db"
    create_account(connect(str(db_path)), "librarian", "correct horse", "librarian")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "LIBRARY_ASSISTANT_DB": str(db_path),
        "LIBRARY_ASSISTANT_PORT": str(port),
    }
    server = subprocess.Popen(
        [sys.executable, "-m", "library_assistant"],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        staff = httpx.Client(base_url=base, timeout=5)
        staff.post(
            "/staff/login",
            data={"username": "librarian", "password": "correct horse"},
        )

        streaming = threading.Event()

        def hold_stream() -> None:
            try:
                with staff.stream(
                    "GET", "/staff/live/events", timeout=None
                ) as response:
                    streaming.set()
                    for _ in response.iter_bytes():
                        pass
            except httpx.HTTPError:
                pass

        threading.Thread(target=hold_stream, daemon=True).start()
        assert streaming.wait(10), "the Live view stream never opened"

        started = time.monotonic()
        server.send_signal(signal.SIGINT)
        server.wait(timeout=GRACEFUL_SHUTDOWN_SECONDS + 8)
        assert time.monotonic() - started < GRACEFUL_SHUTDOWN_SECONDS + 5
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
