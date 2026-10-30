"""Tests for fetch_demo_model.sh's verify, sourced so no download runs.

verify must pass a file whose digest matches and fail one that does not, with whatever
sha256sum the machine has: macOS's rejects `--check --status`, and reading that usage
error as a mismatch once deleted a good download.
"""

import hashlib
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_demo_model.sh"


def run_verify(path: Path, expected: str) -> int:
    return subprocess.run(
        [
            "bash",
            "-c",
            # $0 must not be the script, or the script takes itself as run, not sourced.
            'source "$1" && SHA256="$2" && verify "$3"',
            "bash",
            SCRIPT,
            expected,
            path,
        ],
        check=False,
    ).returncode


def test_verify_accepts_matching_digest(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"demo model bytes")
    assert run_verify(model, hashlib.sha256(b"demo model bytes").hexdigest()) == 0


def test_verify_rejects_other_digest(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"truncated")
    assert run_verify(model, hashlib.sha256(b"demo model bytes").hexdigest()) != 0


def test_verify_rejects_missing_file(tmp_path):
    assert run_verify(tmp_path / "absent.gguf", "0" * 64) != 0
