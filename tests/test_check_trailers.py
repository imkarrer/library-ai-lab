"""The gate refuses a commit with a Claude co-author trailer."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_trailers.sh"
IDENTITY = ("-c", "user.name=Test", "-c", "user.email=test@example.com")
# The machine's own git config can sign commits and wait on an agent; tests ignore it.
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", *IDENTITY, "commit", "--allow-empty", "-q", "-m", message],
        cwd=repo,
        check=True,
        env=ENV,
    )


def _check(repo: Path) -> int:
    return subprocess.run(
        ["bash", str(SCRIPT)], check=False, cwd=repo, capture_output=True, env=ENV
    ).returncode


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, env=ENV)
    _commit(tmp_path, "A commit\n\nCo-Authored-By: A Person <person@example.com>")
    return tmp_path


def test_a_clean_history_passes(repo: Path) -> None:
    assert _check(repo) == 0


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-Authored-By: Claude Opus 5.5 <noreply@example.com>",
        "co-authored-by: a bot <bot@anthropic.example.com>",
    ],
)
def test_a_claude_trailer_fails(repo: Path, trailer: str) -> None:
    _commit(repo, f"Another commit\n\n{trailer}")
    assert _check(repo) == 1
