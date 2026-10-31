#!/usr/bin/env python3
"""Copy the built lesson decks and handouts into the app, so an Install serves them.

An Install has no browser to build them (docs/handout's environment stays apart from it), so
the pipeline commits them to library_assistant/static/materials. A build's PDF differs byte
for byte every time, so a document is copied only when its source or the shared styling
changed: sources.json records what each copy was built from.

Run from docs/handout, after `make`: `make publish`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CURRICULUM = REPO / "docs/curriculum"
BUILD = REPO / "docs/handout/build"
MATERIALS = REPO / "library_assistant/static/materials"
STYLING = (
    REPO / "docs/handout/deck.css",
    REPO / "docs/handout/handout.css",
    REPO / "docs/handout/.marprc.yml",
    REPO / "library_assistant/static/palette.css",
    REPO / "library_assistant/static/components.css",
)
SOURCES = "sources.json"


def fingerprint(doc: Path, styling: tuple[Path, ...]) -> str:
    digest = hashlib.sha256(doc.read_bytes())
    for path in styling:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def outputs(doc: Path) -> list[str]:
    """A deck goes out as a PDF and as HTML, which has the speaker notes. A handout is
    printed, so only its PDF."""
    suffixes = (".pdf", ".html") if doc.stem.endswith("-deck") else (".pdf",)
    return [doc.stem + suffix for suffix in suffixes]


def publish(
    docs: list[Path], build: Path, dest: Path, styling: tuple[Path, ...]
) -> list[str]:
    """Copy each changed document's outputs to `dest`; returns the files copied."""
    dest.mkdir(parents=True, exist_ok=True)
    record = dest / SOURCES
    known = json.loads(record.read_text()) if record.exists() else {}
    copied: list[str] = []
    for doc in docs:
        built_from = fingerprint(doc, styling)
        names = outputs(doc)
        if known.get(doc.stem) == built_from and all(
            (dest / name).exists() for name in names
        ):
            continue
        for name in names:
            shutil.copyfile(build / name, dest / name)
            copied.append(name)
        known[doc.stem] = built_from
    record.write_text(json.dumps(known, indent=2, sort_keys=True) + "\n")
    return copied


def main() -> None:
    docs = sorted(CURRICULUM.glob("lesson-*.md"))
    copied = publish(docs, BUILD, MATERIALS, STYLING)
    print(f"Published {len(copied)} files" if copied else "Nothing changed")


if __name__ == "__main__":
    main()
