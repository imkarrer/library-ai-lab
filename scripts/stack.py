#!/usr/bin/env python3
"""The whole stack in one command: `./stack up`, `down`, `seed`, `clear`, `status`.

    ./stack up              assistant on 127.0.0.1:8000, both Lanes on this Mac's Ollama
    ./stack up --lan        listening on the Wi-Fi address, for phones (the venue)
    ./stack up --mock       the fake model (scripts/fake_model.py) instead of Ollama
    ./stack seed            the demo cast, settings, and the Teacher's filled Minting page
    ./stack down            stop everything `up` started
    ./stack clear           down, then delete the stack's database and files
    ./stack status          what is running, and where

Every setting the assistant needs is given to its process here, so nothing is sourced by
hand and nothing depends on a shell's exports (lib-f9o). State lives in one folder outside
the repo, only you can read it (`--state`, default ~/library-assistant-demo): the database,
each process's pid and log, and `credentials.txt` with the demo cast's passwords.
Nothing here leaves the machine (ADR-0006): every process listens on 127.0.0.1 or, with
--lan, the laptop's own address.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEFAULT_STATE = Path.home() / "library-assistant-demo"
OLLAMA_BIN = Path("/Applications/Ollama.app/Contents/Resources/ollama")
ANSWER_OLLAMA = "http://127.0.0.1:11434"
OVERSIGHT_OLLAMA_PORT = 11435
FAKE_MODEL_PORT = 8090
ANSWER_MODEL, ANSWER_EFFORT = "gpt-oss:20b", "low"
OVERSIGHT_MODEL, OVERSIGHT_EFFORT = "qwen3.5:4b", "none"
FIXTURE_MARC = REPO / "tests" / "fixtures" / "catalog" / "loc-books-2016-sample.xml"


@dataclass(frozen=True)
class Persona:
    """A staff account in the demo cast. The username starts with the role, so whoever is
    watching knows who is who from any page that names an account."""

    username: str
    role: str
    name: str
    part: str


# Who `seed` makes sure exists, on every `up`. The deck (docs/handout/demo-deck.md)
# introduces the same cast: change one, change both.
DEMO_CAST = (
    Persona(
        "librarian.overdue",
        "librarian",
        "Ms. Overdue",
        "runs the library and keeps Watch on the Live view",
    ),
    Persona(
        "teacher.popquiz",
        "teacher",
        "Mr. Pop-Quiz",
        "makes Period 3's Cards and keeps the Roster",
    ),
    Persona(
        "counselor.hugsworth",
        "counselor",
        "Dr. Hugsworth",
        "owns every Flag that is escalated",
    ),
)
# Mr. Pop-Quiz's class, prefilled in his Minting page. Fictional, and only ever in that
# page on the presenter's own disk: the assistant never holds a name (ADR-0002).
DEMO_CLASS = "Period 3"
DEMO_STUDENTS = (
    "Paige Turner",
    "Justin Time",
    "Dot Matrix",
    "Moe Mentum",
    "Anita Nap",
    "Rhoda Book",
)


@dataclass(frozen=True)
class Component:
    """One process `up` starts: its pid file, log, how to stop it, and its health URL."""

    name: str
    health: str
    stop_signal: int = signal.SIGTERM


def _say(message: str) -> None:
    print(message, flush=True)


def _pid_path(state: Path, name: str) -> Path:
    return state / f"{name}.pid"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid(state: Path, name: str) -> int | None:
    path = _pid_path(state, name)
    if not path.exists():
        return None
    pid = int(path.read_text().strip() or 0)
    if pid and _alive(pid):
        return pid
    path.unlink(missing_ok=True)
    return None


def _healthy(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _wait_healthy(url: str, seconds: float, pid: int) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _healthy(url):
            return True
        if not _alive(pid):
            return False
        time.sleep(0.3)
    return False


def _start(
    state: Path, name: str, command: list[str], env: dict[str, str], health: str
) -> int:
    """Start `command` in the background, logging to <state>/<name>.log."""
    running = _read_pid(state, name)
    if running:
        _say(f"  {name}: already running (pid {running})")
        return running
    if _healthy(health):
        # Started by hand or by another tool: use it, and leave it for its owner to stop.
        _say(f"  {name}: something already answers at {health}; using it")
        return 0
    log = (state / f"{name}.log").open("ab")
    process = subprocess.Popen(
        command,
        cwd=REPO,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # not stopped by this terminal's Ctrl-C
    )
    _pid_path(state, name).write_text(str(process.pid))
    if not _wait_healthy(health, 60, process.pid):
        _say(f"  {name}: did not come up; see {state / (name + '.log')}")
        raise SystemExit(1)
    _say(f"  {name}: up (pid {process.pid})")
    return process.pid


def _stop(state: Path, name: str, sig: int) -> None:
    pid = _read_pid(state, name)
    if pid is None:
        return
    os.kill(pid, sig)
    deadline = time.monotonic() + 10
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.2)
    if _alive(pid):
        os.kill(pid, signal.SIGKILL)
    _pid_path(state, name).unlink(missing_ok=True)
    _say(f"  {name}: stopped")


def lan_address() -> str:
    """The Wi-Fi address phones reach the laptop on (macOS)."""
    result = subprocess.run(
        ["ipconfig", "getifaddr", "en0"], capture_output=True, text=True, check=False
    )
    address = result.stdout.strip()
    if not address:
        raise SystemExit(
            "no Wi-Fi address (en0); join the network first, or drop --lan"
        )
    return address


def _local_timezone() -> str:
    link = os.path.realpath("/etc/localtime")
    return link.split("zoneinfo/", 1)[1] if "zoneinfo/" in link else "America/Chicago"


def _config_path(state: Path) -> Path:
    return state / "stack.json"


def assistant_env(state: Path, config: dict) -> dict[str, str]:
    """The assistant's whole configuration, given to its process directly."""
    if config["mock"]:
        answer = oversight = f"http://127.0.0.1:{config['fake_port']}/v1"
        answer_model = oversight_model = "fake"
    else:
        answer = f"{ANSWER_OLLAMA}/v1"
        oversight = f"http://127.0.0.1:{OVERSIGHT_OLLAMA_PORT}/v1"
        answer_model, oversight_model = ANSWER_MODEL, OVERSIGHT_MODEL
    return {
        **os.environ,
        "LIBRARY_ASSISTANT_DB": str(state / "demo.db"),
        "LIBRARY_ASSISTANT_CATALOG_PATH": config["catalog"],
        "LIBRARY_ASSISTANT_HOST": config["host"],
        "LIBRARY_ASSISTANT_PORT": str(config["port"]),
        "LIBRARY_ASSISTANT_DEMO": "1",
        "LIBRARY_ASSISTANT_SCHOOL_TIMEZONE": config["timezone"],
        "LIBRARY_ASSISTANT_SCHOOL_DAY_END": config["day_end"],
        "LIBRARY_ASSISTANT_OPENAI_ENDPOINT": answer,
        "LIBRARY_ASSISTANT_OPENAI_MODEL": answer_model,
        "LIBRARY_ASSISTANT_OPENAI_REASONING_EFFORT": ANSWER_EFFORT,
        "LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT": oversight,
        "LIBRARY_ASSISTANT_OVERSIGHT_MODEL": oversight_model,
        "LIBRARY_ASSISTANT_OVERSIGHT_REASONING_EFFORT": OVERSIGHT_EFFORT,
    }


def fixture_catalog(state: Path) -> str:
    """The 270-record LoC sample as a Catalog, built once into the state folder."""
    from library_assistant.catalog.marc import parse_marcxml, to_record
    from library_assistant.catalog.sqlite_backend import SqliteCatalog

    path = state / "catalog-fixture.db"
    if not path.exists():
        catalog = SqliteCatalog.open(str(path))
        catalog.load_records(to_record(m) for m in parse_marcxml(str(FIXTURE_MARC)))
    return str(path)


def base_url(config: dict) -> str:
    return f"http://{config['host']}:{config['port']}"


def _warm(url: str, model: str, effort: str) -> None:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Say ready."}],
            "reasoning_effort": effort,
        }
    ).encode()
    request = urllib.request.Request(
        f"{url}/v1/chat/completions",
        data=body,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120):
            pass
    except (urllib.error.URLError, OSError) as error:
        _say(f"  warning: could not warm {model} at {url}: {error}")


def up(state: Path, args: argparse.Namespace) -> None:
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    catalog = args.catalog
    if catalog is None:
        demo = REPO / "catalog.db"
        catalog = (
            str(demo) if demo.exists() and not args.mock else fixture_catalog(state)
        )
    config = {
        "mock": args.mock,
        "host": lan_address() if args.on_wifi else "127.0.0.1",
        "port": args.port,
        "catalog": catalog,
        "timezone": args.timezone or _local_timezone(),
        "day_end": args.day_end,
        "fake_port": args.fake_port,
    }
    _config_path(state).write_text(json.dumps(config, indent=1))
    _say(f"Starting the stack ({'fake model' if args.mock else 'Ollama'}):")

    if args.mock:
        _start(
            state,
            "fake-model",
            [
                sys.executable,
                "scripts/fake_model.py",
                "--port",
                str(args.fake_port),
                "--delay-ms",
                str(args.fake_delay_ms),
            ],
            dict(os.environ),
            f"http://127.0.0.1:{args.fake_port}/health",
        )
    else:
        if not _healthy(f"{ANSWER_OLLAMA}/api/version"):
            raise SystemExit(
                "Ollama is not answering on 127.0.0.1:11434 (its LaunchAgent starts it at "
                "login); start it, or run `./stack up --mock`."
            )
        if not OLLAMA_BIN.exists():
            raise SystemExit(f"Oversight needs Ollama.app ({OLLAMA_BIN}).")
        oversight_env = {
            **os.environ,
            "OLLAMA_HOST": f"127.0.0.1:{OVERSIGHT_OLLAMA_PORT}",
            "OLLAMA_CONTEXT_LENGTH": "4096",
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_KEEP_ALIVE": "30m",
            "OLLAMA_FLASH_ATTENTION": "1",
        }
        _start(
            state,
            "oversight-ollama",
            [str(OLLAMA_BIN), "serve"],
            oversight_env,
            f"http://127.0.0.1:{OVERSIGHT_OLLAMA_PORT}/api/version",
        )
        _say("  warming both models (first time after a while: 10 to 30 s)")
        _warm(ANSWER_OLLAMA, ANSWER_MODEL, ANSWER_EFFORT)
        _warm(
            f"http://127.0.0.1:{OVERSIGHT_OLLAMA_PORT}",
            OVERSIGHT_MODEL,
            OVERSIGHT_EFFORT,
        )

    # Every `up`, not only the first: an older stack gains the cast it is missing.
    seed(state, quiet=True)
    _start(
        state,
        "assistant",
        [sys.executable, "-m", "library_assistant"],
        assistant_env(state, config),
        f"{base_url(config)}/health",
    )
    _say("")
    status(state)


def down(state: Path) -> None:
    _say("Stopping the stack:")
    _stop(state, "assistant", signal.SIGINT)
    _stop(state, "oversight-ollama", signal.SIGTERM)
    _stop(state, "fake-model", signal.SIGTERM)


def seed(state: Path, quiet: bool = False) -> None:
    """The demo cast (only those missing), settings not yet set, and the Teacher's filled
    Minting page.

    Re-running changes nothing that exists: a seeded password is written once, to
    credentials.txt, an existing account keeps its own, and a setting someone changed on
    the settings page stays changed.
    """
    from library_assistant.access import connect, issue_registration_key
    from library_assistant.install_settings import (
        SUPERVISION_MODE,
        WATCH_GRACE_SECONDS,
        set_setting,
    )
    from library_assistant.minting_page import download_filename, filled_minting_page
    from library_assistant.staff import create_account

    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = connect(str(state / "demo.db"))
    now = datetime.now(UTC)
    created: list[tuple[str, str, str]] = []
    for persona in DEMO_CAST:
        if db.execute(
            "SELECT 1 FROM staff_accounts WHERE username = ?", (persona.username,)
        ).fetchone():
            continue
        password = secrets.token_urlsafe(9)
        create_account(db, persona.username, password, persona.role)
        created.append((persona.username, persona.role, password))
    librarian, teacher, counselor = DEMO_CAST
    librarian_id = db.execute(
        "SELECT id FROM staff_accounts WHERE username = ?", (librarian.username,)
    ).fetchone()[0]
    for key, value in (
        (SUPERVISION_MODE, "live"),
        (WATCH_GRACE_SECONDS, "300"),
        # Who the supportive reply sends a Student to.
        ("counselor_name", counselor.name),
    ):
        if not db.execute(
            "SELECT 1 FROM install_settings WHERE key = ?", (key,)
        ).fetchone():
            set_setting(db, key, value, librarian_id, now)

    if created:
        credentials = state / "credentials.txt"
        with credentials.open("a") as out:
            for username, role, password in created:
                out.write(f"{username} ({role}): {password}\n")
        credentials.chmod(0o600)

    config = (
        json.loads(_config_path(state).read_text())
        if _config_path(state).exists()
        else {"host": "127.0.0.1", "port": 8000}
    )
    teacher_id = db.execute(
        "SELECT id FROM staff_accounts WHERE username = ?", (teacher.username,)
    ).fetchone()[0]
    page = state / download_filename(teacher.username)
    if not page.exists():
        key = issue_registration_key(db, teacher_id, now)
        page.write_text(
            filled_minting_page(
                base_url(config),
                teacher.username,
                key,
                config.get("day_end", "23:59"),
                class_label=DEMO_CLASS,
                class_list=DEMO_STUDENTS,
            )
        )
        page.chmod(0o600)
    if not quiet:
        _say("Seeded:")
    for username, role, _ in created:
        _say(f"  {role} account `{username}` (password in {state / 'credentials.txt'})")
    if not quiet:
        _say(f"  {teacher.name}'s Minting page: {page}")


def clear(state: Path) -> None:
    """Down, then delete what the stack made: database, Minting page, logs, settings."""
    down(state)
    if not state.exists():
        return
    names = [
        "demo.db",
        "demo.db-journal",
        "oversight.lock",
        "credentials.txt",
        "catalog-fixture.db",
        "stack.json",
        "assistant.log",
        "oversight-ollama.log",
        "fake-model.log",
    ]
    removed = [name for name in names if (state / name).exists()]
    removed += sorted(page.name for page in state.glob("*-minting-page.html"))
    for name in removed:
        (state / name).unlink()
    cards = state / "cards"
    if cards.exists():
        shutil.rmtree(cards)
        removed.append("cards/")
    _say(f"Cleared {state}: {', '.join(removed) or 'nothing to clear'}")


def status(state: Path) -> None:
    config = (
        json.loads(_config_path(state).read_text())
        if _config_path(state).exists()
        else None
    )
    components = [
        Component("assistant", f"{base_url(config)}/health" if config else ""),
        Component(
            "oversight-ollama", f"http://127.0.0.1:{OVERSIGHT_OLLAMA_PORT}/api/version"
        ),
        Component(
            "fake-model",
            f"http://127.0.0.1:{(config or {}).get('fake_port', FAKE_MODEL_PORT)}/health",
        ),
    ]
    for component in components:
        pid = _read_pid(state, component.name)
        if pid is None:
            continue
        health = (
            "healthy"
            if component.health and _healthy(component.health)
            else "not answering"
        )
        _say(f"  {component.name}: pid {pid}, {health}")
    if config and _read_pid(state, "assistant"):
        url = base_url(config)
        if config["host"] == "127.0.0.1":
            # Cards carry the address their Minting page was made with: 127.0.0.1 on a
            # phone is the phone itself.
            _say(
                "  Note: only this computer can reach it. For phones and other devices, "
                "`./stack down && ./stack up --lan`."
            )
        _say(f"  Staff sign-in: {url}/staff/login")
        _say(f"  Live view:     {url}/staff/live  (press Start watch)")
    credentials = state / "credentials.txt"
    if credentials.exists():
        _say(f"  Passwords:     {credentials}")
    from library_assistant.minting_page import download_filename

    page = state / download_filename(DEMO_CAST[1].username)
    if page.exists():
        _say(f"  Make Cards:    open {page}")
    if (state / "demo.db").exists():
        _say("  The cast:")
        for persona in DEMO_CAST:
            _say(f"    {persona.name:<14} {persona.username:<20} {persona.part}")
        _say(f"    {DEMO_CLASS}: {', '.join(DEMO_STUDENTS)}")
    if not any(_read_pid(state, c.name) for c in components):
        _say("  Nothing running. `./stack up` starts it.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="stack", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(os.environ.get("LIBRARY_ASSISTANT_STACK_DIR", DEFAULT_STATE)),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("up", help="start everything (seeds an empty stack)")
    start.add_argument("--mock", action="store_true", help="the fake model, no Ollama")
    start.add_argument(
        "--lan", dest="on_wifi", action="store_true", help="listen on the Wi-Fi address"
    )
    start.add_argument("--port", type=int, default=8000)
    start.add_argument("--fake-port", type=int, default=FAKE_MODEL_PORT)
    start.add_argument(
        "--fake-delay-ms", type=int, default=30, help="between streamed chunks (--mock)"
    )
    start.add_argument(
        "--catalog", help="a Catalog file (default: catalog.db, else the fixture)"
    )
    start.add_argument("--timezone", help="IANA name (default: this Mac's)")
    start.add_argument("--day-end", default="23:59", help="school day end, HH:MM")
    for name, text in (
        ("down", "stop everything"),
        ("seed", "accounts, settings, Minting page"),
        ("clear", "stop, then delete the stack's files"),
        ("status", "what is running"),
    ):
        commands.add_parser(name, help=text)
    args = parser.parse_args(argv)
    state = args.state.expanduser()
    if args.command == "up":
        up(state, args)
    elif args.command == "down":
        down(state)
    elif args.command == "seed":
        seed(state)
    elif args.command == "clear":
        clear(state)
    else:
        status(state)


if __name__ == "__main__":
    main()
