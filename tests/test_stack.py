"""`./stack` (scripts/stack.py) end to end in mock mode: up, seed, down, clear."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _stack(state: Path, *args: str) -> str:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "stack.py"),
            "--state",
            str(state),
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _pids(state: Path) -> list[int]:
    return [int(p.read_text()) for p in state.glob("*.pid")]


def test_up_seed_down_clear(tmp_path):
    state = tmp_path / "stack"
    port, fake_port = _free_port(), _free_port()
    try:
        out = _stack(
            state, "up", "--mock", "--port", str(port), "--fake-port", str(fake_port)
        )
        assert "assistant: up" in out and "fake-model: up" in out
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
            assert r.status == 200

        credentials = (state / "credentials.txt").read_text()
        assert [line.split(" ")[0] for line in credentials.splitlines()] == [
            "librarian",
            "teacher",
            "counselor",
        ]
        assert oct((state / "credentials.txt").stat().st_mode & 0o777) == "0o600"
        page = (state / "teacher-minting-page.html").read_text()
        config = json.loads(
            re.search(r'id="install-config">(.*?)</script>', page, re.DOTALL).group(1)
        )
        assert config["assistant_url"] == f"http://127.0.0.1:{port}"

        # Seeding again creates nothing and keeps every password.
        _stack(state, "seed")
        assert (state / "credentials.txt").read_text() == credentials

        assert len(_pids(state)) == 2
        status = _stack(state, "status")
        assert "healthy" in status
        # Bound to 127.0.0.1: the stack says phones cannot reach it.
        assert "only this computer can reach it" in status
    finally:
        pids = _pids(state)
        _stack(state, "down")
    assert not list(state.glob("*.pid"))
    for pid in pids:
        assert subprocess.run(
            ["kill", "-0", str(pid)], capture_output=True, check=False
        ).returncode

    _stack(state, "clear")
    assert not (state / "demo.db").exists()
    assert not (state / "credentials.txt").exists()


def test_up_uses_a_fake_model_already_running_and_leaves_it(tmp_path):
    """Something already on the port (started by hand) is used, not shadowed."""
    port, fake_port = _free_port(), _free_port()
    other = subprocess.Popen(
        [
            sys.executable,
            str(REPO / "scripts" / "fake_model.py"),
            "--port",
            str(fake_port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    state = tmp_path / "stack"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{fake_port}/health", timeout=1
                )
                break
            except OSError:
                import time

                time.sleep(0.2)
        out = _stack(
            state, "up", "--mock", "--port", str(port), "--fake-port", str(fake_port)
        )
        assert "already answers" in out
        assert not (state / "fake-model.pid").exists()
        _stack(state, "down")
        assert other.poll() is None, "down stopped a process it did not start"
    finally:
        _stack(state, "down")
        other.terminate()
        other.wait(timeout=10)
