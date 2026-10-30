"""The flox manifest's model service: what the demo Mac's model server runs with."""

import tomllib
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / ".flox" / "env" / "manifest.toml"


def _model_command() -> str:
    """The command without its comments, which name flags it does not pass."""
    command = tomllib.loads(MANIFEST.read_text())["services"]["model"]["command"]
    return "\n".join(
        line for line in command.splitlines() if not line.lstrip().startswith("#")
    )


def test_model_server_runs_on_the_cpu():
    """lib-30v: the M5 Pro's Metal backend fails every request; the CPU answers."""
    assert "--n-gpu-layers 0" in _model_command()


def test_model_server_is_local_only_and_keeps_no_question():
    command = _model_command()
    assert "--host 127.0.0.1" in command  # ADR-0006
    assert "--no-slots" in command  # ADR-0003 addendum
    for flag in ("--log-prompts-dir", "--slot-save-path", " -v "):
        assert flag not in command
