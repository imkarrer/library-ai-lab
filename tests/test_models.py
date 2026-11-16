"""The models' pins (models/) against what the stack serves, and ADR-0006's model exception.

The pins are Ollama registry manifests kept verbatim. The Nix checks evaluate only, so they
download no weights and run on CI's Linux runner too.
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
NIX = shutil.which("nix") or "/nix/var/nix/profiles/default/bin/nix"


def _stack():
    spec = importlib.util.spec_from_file_location(
        "stack", ROOT / "scripts" / "stack.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("stack", module)  # its dataclasses look themselves up here
    spec.loader.exec_module(module)
    return module


def _pin(model: str) -> Path:
    return MODELS / "pins" / f"{model.replace(':', '-')}.json"


def _eval(attr: str, apply: str):
    if not Path(NIX).exists():
        pytest.skip("no nix on this machine")
    result = subprocess.run(
        [NIX, "--extra-experimental-features", "nix-command flakes", "eval", "--json"]
        + [f"path:{MODELS}#packages.aarch64-darwin.{attr}", "--apply", apply],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("name", ["ANSWER_MODEL", "OVERSIGHT_MODEL"])
def test_each_model_the_stack_serves_is_pinned(name):
    model = getattr(_stack(), name)
    repo, tag = model.split(":")
    assert _pin(model).is_file()
    assert (
        f'repo = "library/{repo}"; tag = "{tag}"' in (MODELS / "flake.nix").read_text()
    )


@pytest.mark.parametrize(
    "pin", sorted((MODELS / "pins").glob("*.json")), ids=lambda p: p.stem
)
def test_every_pinned_file_is_named_by_its_digest(pin):
    manifest = json.loads(pin.read_text())
    for layer in manifest["layers"] + [manifest["config"]]:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", layer["digest"])
        assert layer["size"] > 0


def test_setup_fetches_to_the_paths_the_install_reads():
    # The one fetch and the environment's refusing build must agree on every store path,
    # or activation after setup would look for files setup never put there.
    paths = "p: map (b: b.path.outPath) p.blobs ++ [ p.outPath ]"
    assert _eval("default", paths) == _eval("online", paths)


def test_the_install_has_no_url_to_fetch_a_model_from():
    has_url = "p: map (b: b.path.drvAttrs ? urls || b.path.drvAttrs ? url) p.blobs"
    assert not any(_eval("default", has_url))
    assert all(_eval("online", has_url))
