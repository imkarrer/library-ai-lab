"""The gate refuses a commit with a Claude co-author trailer."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_trailers.sh"
IDENTITY = ("-c", "user.name=Test", "-c", "user.email=test@example.com")


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", *IDENTITY, "commit", "--allow-empty", "-q", "-m", message],
        cwd=repo,
        check=True,
    )


def _check(repo: Path) -> int:
    return subprocess.run(
        ["bash", str(SCRIPT)], cwd=repo, capture_output=True
    ).returncode


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _commit(tmp_path, "A commit\n\nCo-Authored-By: A Person <person@example.com>")
    return tmp_path


def test_a_clean_history_passes(repo: Path) -> None:
    assert _check(repo) == 0


@pytest.mark.parametrize(
    "trailer",
    [
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
        "co-authored-by: claude <noreply@example.com>",
    ],
)
def test_a_claude_trailer_fails(repo: Path, trailer: str) -> None:
    _commit(repo, f"Another commit\n\n{trailer}")
    assert _check(repo) == 1
