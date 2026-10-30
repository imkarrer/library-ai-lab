"""The flox manifest's model service: what the demo Mac's model server runs with."""

import tomllib
from pathlib import Path

MANIFEST = Path(__file__).resolve().parent.parent / ".flox" / "env" / "manifest.toml"


def _service_command(name: str) -> str:
    """A service's command without its comments, which name flags it does not pass."""
    command = tomllib.loads(MANIFEST.read_text())["services"][name]["command"]
    return "\n".join(
        line for line in command.splitlines() if not line.lstrip().startswith("#")
    )


def _model_command() -> str:
    return _service_command("model")


def test_model_server_uses_the_gpu():
    """lib-30v: llama.cpp 0.7.0 answers on the M5 Pro's GPU, so it is not held to the CPU."""
    assert "--n-gpu-layers 0" not in _model_command()


def test_ollama_comes_from_the_environment_on_the_demo_mac():
    """./stack runs both Lanes on the manifest's Ollama, not an Ollama.app (ADR-0008)."""
    ollama = tomllib.loads(MANIFEST.read_text())["install"]["ollama"]
    assert ollama["pkg-path"] == "ollama"
    assert ollama["systems"] == ["aarch64-darwin"]


def test_model_server_is_local_only_and_keeps_no_question():
    command = _model_command()
    assert "--host 127.0.0.1" in command  # ADR-0006
    assert "--no-slots" in command  # ADR-0003 addendum
    for flag in ("--log-prompts-dir", "--slot-save-path", " -v "):
        assert flag not in command


def test_assistant_service_uses_the_one_start_command():
    """python -m library_assistant: no access log and a bounded Ctrl-C (lib-4m7)."""
    command = _service_command("assistant")
    assert "-m library_assistant" in command
    assert "uvicorn" not in command
