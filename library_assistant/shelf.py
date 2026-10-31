"""Sending a Student to the shelf: a call number and an author, in plain words."""

from __future__ import annotations

import re

# Dewey's ten hundreds, in words a 12-year-old would use.
_DEWEY_SECTIONS = {
    "0": "computers and general knowledge",
    "1": "the mind and big ideas",
    "2": "religion and myths",
    "3": "people, society, and holidays",
    "4": "languages",
    "5": "science, animals, and math",
    "6": "technology, health, cooking, and pets",
    "7": "art, music, and sports",
    "8": "poetry, plays, and literature",
    "9": "history and geography",
}

_DEWEY_RE = re.compile(r"^(\d)\d\d(\.\d+)?$")

# What schools put on a spine for the three shelves that aren't Dewey numbers. 92 and 920
# are biography by Dewey, and a school shelves them with B.
_SCHOOL_LABELS = {
    "E": "E",
    "EASY": "E",
    "FIC": "FIC",
    "FICTION": "FIC",
    "F": "FIC",
    "B": "B",
    "BIO": "B",
    "BIOG": "B",
    "BIOGRAPHY": "B",
    "92": "B",
    "920": "B",
}


def where_to_find(call_number: str) -> str:
    """Where `call_number` sits in a school library, or "" if it is not a school one."""
    shelf, _, letters = call_number.strip().partition(" ")
    letters = letters.strip()
    kind = _SCHOOL_LABELS.get(shelf.upper())
    if kind == "E":
        return f"Picture books, under {letters}" if letters else "Picture books"
    if kind == "FIC":
        return f"Fiction, under {letters} for the author" if letters else "Fiction"
    if kind == "B":
        return (
            f"Biographies, under {letters} for the person" if letters else "Biographies"
        )
    dewey = _DEWEY_RE.match(shelf)
    if dewey is None:
        return ""
    section = f"Nonfiction, the {dewey.group(1)}00s ({_DEWEY_SECTIONS[dewey.group(1)]})"
    return (
        f"{section}: find {shelf}, then {letters}"
        if letters
        else f"{section}: find {shelf}"
    )


def author_name(author: str) -> str:
    """A MARC heading as a name: "Leaf, Munro, 1905-1976." is "Munro Leaf"."""
    heading = re.sub(r"\([^)]*\)", "", author)
    heading = re.sub(r"(?<=\w\w)\.\s*$", "", heading.strip(" ,"))
    parts = [part.strip() for part in heading.split(",") if part.strip()]
    parts = [part for part in parts if not re.search(r"\d", part)]
    if len(parts) >= 2:
        return f"{parts[1]} {parts[0]}"
    return parts[0] if parts else ""
