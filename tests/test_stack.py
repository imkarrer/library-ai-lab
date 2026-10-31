"""`./stack` (scripts/stack.py) end to end in mock mode: up, seed, down, clear."""

from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import httpx
import pytest

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
        # The demo cast: each username says the role it plays.
        assert [line.split(" ")[0] for line in credentials.splitlines()] == [
            "librarian.overdue",
            "teacher.popquiz",
            "counselor.hugsworth",
        ]
        assert oct((state / "credentials.txt").stat().st_mode & 0o777) == "0o600"
        page = (state / "teacher.popquiz-minting-page.html").read_text()
        config = json.loads(
            re.search(r'id="install-config">(.*?)</script>', page, re.DOTALL).group(1)
        )
        assert config["assistant_url"] == f"http://127.0.0.1:{port}"
        assert config["username"] == "teacher.popquiz"
        assert config["class_label"] == "Period 3"
        assert config["class_list"][0] == "Paige Turner"

        # Easy to type on stage: the word after the dot.
        assert "librarian.overdue (librarian): overdue" in credentials
        # Seeding again creates nothing and puts a changed password back.
        import sqlite3

        db = sqlite3.connect(state / "demo.db")
        db.execute("UPDATE staff_accounts SET password_hash = 'x'")
        db.commit()
        db.close()
        _stack(state, "seed")
        assert (state / "credentials.txt").read_text() == credentials
        login = httpx.post(
            f"http://127.0.0.1:{port}/staff/login",
            data={"username": "counselor.hugsworth", "password": "hugsworth"},
        )
        assert login.status_code == 303
        # Make Cards, the app: Mr. Pop-Quiz's fictional class comes prefilled.
        teacher = httpx.Client(base_url=f"http://127.0.0.1:{port}")
        teacher.post(
            "/staff/login", data={"username": "teacher.popquiz", "password": "popquiz"}
        )
        app_page = teacher.get("/staff/mint/").text
        app_config = json.loads(
            re.search(r'id="install-config">(.*?)</script>', app_page, re.DOTALL)[1]
        )
        assert app_config["class_list"][0] == "Paige Turner"
        assert "registration_key" not in app_config

        assert len(_pids(state)) == 2
        status = _stack(state, "status")
        assert "healthy" in status
        # Bound to 127.0.0.1: the stack says phones cannot reach it.
        assert "only this computer can reach it" in status
        assert "Dr. Hugsworth" in status and "counselor.hugsworth" in status
        assert f"http://127.0.0.1:{port}/staff/mint/" in status
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
    assert not list(state.glob("*-minting-page.html"))


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


def test_up_with_https_serves_a_certificate_a_device_can_verify(tmp_path):
    """`--https`: the stack's own CA; the health check, the Minting page and the IT kit
    all use https, and a client that trusts only the CA connects."""
    import ssl

    state = tmp_path / "stack"
    port, fake_port = _free_port(), _free_port()
    try:
        out = _stack(
            state,
            "up",
            "--mock",
            "--https",
            "--port",
            str(port),
            "--fake-port",
            str(fake_port),
        )
        assert "assistant: up" in out
        ca = state / "tls" / "library-assistant-ca.crt"
        context = ssl.create_default_context(cafile=str(ca))
        with urllib.request.urlopen(
            f"https://127.0.0.1:{port}/it-check", context=context, timeout=5
        ) as response:
            assert (
                "This device trusts the Library Assistant" in response.read().decode()
            )
        page = (state / "teacher.popquiz-minting-page.html").read_text()
        assert f'"assistant_url": "https://127.0.0.1:{port}"' in page
        assert "IT kit:" in _stack(state, "status")
    finally:
        _stack(state, "down")
    _stack(state, "clear")
    assert not (state / "tls").exists()


def test_ollama_env_is_local_only_with_no_cloud_and_no_prompt_logging(monkeypatch):
    sys.path.insert(0, str(REPO / "scripts"))
    import stack

    monkeypatch.setenv("OLLAMA_DEBUG", "2")
    monkeypatch.setenv("OLLAMA_DEBUG_LOG_REQUESTS", "1")
    monkeypatch.setenv("OLLAMA_HOST", "elsewhere:11434")
    env = stack.ollama_env(11435, 4096)
    assert env["OLLAMA_HOST"] == "127.0.0.1:11435"  # ADR-0006
    assert env["OLLAMA_NO_CLOUD"] == "1"  # ADR-0006: no ollama.com calls
    assert "OLLAMA_DEBUG" not in env  # ADR-0003 addendum
    assert "OLLAMA_DEBUG_LOG_REQUESTS" not in env
    assert env["OLLAMA_CONTEXT_LENGTH"] == "4096"


@pytest.mark.parametrize(
    ("config", "installable"),
    [
        ({"host": "127.0.0.1", "port": 8000}, True),
        ({"host": "192.0.2.10", "port": 8000, "https": True}, True),
        ({"host": "192.0.2.10", "port": 8000}, False),
    ],
)
def test_status_offers_install_only_where_a_browser_will(config, installable):
    """Chrome offers Install only in a secure context: HTTPS, or the computer's own address."""
    sys.path.insert(0, str(REPO / "scripts"))
    import stack

    hint = stack.install_hint(config)
    assert hint.startswith("Install") is installable
    if not installable:
        assert "--https" in hint


def test_materials_builds_without_starting_anything(tmp_path):
    """`./stack materials` runs make in the handout's environment and needs no server."""
    log = tmp_path / "calls"
    flox = tmp_path / "flox"
    flox.write_text(f'#!/bin/sh\npwd > "{log}"\necho "$@" >> "{log}"\n')
    flox.chmod(0o755)
    state = tmp_path / "state"
    subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/stack.py"),
            "--state",
            str(state),
            "materials",
        ],
        env={"PATH": f"{tmp_path}:/usr/bin:/bin"},
        check=True,
        capture_output=True,
    )
    cwd, command = log.read_text().splitlines()
    assert cwd.endswith("docs/handout")
    assert command.endswith("-- make all check")
    assert not state.exists()
