"""The Watchlist: curated phrases, each with a Rubric category and a severity (ADR-0004).

Matching is deterministic: no model call, no regex. The file format (decided in lib-f24.24):

    version = "2026-10-25.1"          # YYYY-MM-DD.N

    [[entries]]
    id = "some-entry"                 # kebab-case, unique in the file
    category = "self-harm"            # self-harm | abuse | bullying | threats-of-violence
    severity = "high"                 # high | low
    phrases = ["a phrase"]            # at least one; any one of them raises the entry
    must_match = ["a message"]        # at least one example message the entry must match
    must_not_match = ["a message"]    # at least one example message it must not match

`normalize` is applied to messages and phrases alike: NFKD and drop combining marks;
lowercase; map 0>o 1>l 3>e 4>a 5>s 7>t @>a $>s; every character that is not a-z becomes a
space; collapse any run of the same letter to one ("kiiill" and "kill" both become "kil");
collapse whitespace; strip. A phrase matches when " " + phrase + " " occurs in
" " + message + " " after both are normalized, so phrases match whole words only.

Loading refuses the file with a ValueError naming the entry on an unknown category or
severity, a duplicate or non-kebab-case id, a missing or empty field, an unknown field, or a
must_match example that does not match its entry or a must_not_match example that does.
"""

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("watchlist.toml")
DEMO_PATH = Path(__file__).with_name("watchlist-demo.toml")

CATEGORIES = ("self-harm", "abuse", "bullying", "threats-of-violence")
SEVERITIES = ("high", "low")

_LIST_FIELDS = ("phrases", "must_match", "must_not_match")
_FIELDS = {"id", "category", "severity", *_LIST_FIELDS}
_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_VERSION = re.compile(r"\d{4}-\d{2}-\d{2}\.\d+")

# "1" is read as "l", not "i": "ki11" is "kill" spelled in digits, and the acceptance table
# (lib-f24.35) pins "Ki11 m3" to "kil me".
_LEET = str.maketrans(
    {"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"}
)
_NOT_LETTER = re.compile(r"[^a-z]+")
_REPEATED_LETTER = re.compile(r"([a-z])\1+")


def normalize(text: str) -> str:
    """Fold `text` to plain lowercase words so evasions match the plain phrase."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().translate(_LEET)
    text = _NOT_LETTER.sub(" ", text)
    text = _REPEATED_LETTER.sub(r"\1", text)
    return " ".join(text.split())


@dataclass(frozen=True)
class Entry:
    """One Watchlist entry: the phrases that raise it, the Rubric label it carries, and the
    example messages that prove it."""

    id: str
    category: str
    severity: str
    phrases: tuple[str, ...]
    must_match: tuple[str, ...]
    must_not_match: tuple[str, ...]

    def matches(self, text: str) -> bool:
        """True when any phrase occurs as whole words in `text`, both normalized."""
        message = f" {normalize(text)} "
        return any(f" {normalize(phrase)} " in message for phrase in self.phrases)


@dataclass(frozen=True)
class Watchlist:
    """A loaded, validated Watchlist."""

    version: str
    entries: tuple[Entry, ...]

    def match(self, text: str) -> list[Entry]:
        """Every Entry that `text` matches, in file order."""
        return [entry for entry in self.entries if entry.matches(text)]


def load_watchlist(path: str | Path = DEFAULT_PATH, demo: bool = False) -> Watchlist:
    """Load and validate the Watchlist at `path`; ValueError names the entry it refuses."""
    with open(path, "rb") as f:
        data = tomllib.load(f)

    version = data.get("version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        raise ValueError(f"watchlist version {version!r} is not YYYY-MM-DD.N")

    entries: list[Entry] = []
    seen: set[str] = set()
    for index, raw in enumerate(data.get("entries", [])):
        entry = _entry(raw, f"entries[{index}]")
        if entry.id in seen:
            raise ValueError(f"watchlist entry {entry.id!r}: duplicate id")
        seen.add(entry.id)
        entries.append(entry)
    if not entries:
        raise ValueError("watchlist has no entries")

    # If demo flag is True, load demo entries and append them
    if demo:
        try:
            with open(DEMO_PATH, "rb") as f:
                demo_data = tomllib.load(f)
            for index, raw in enumerate(demo_data.get("entries", [])):
                entry = _entry(raw, f"demo_entries[{index}]")
                if entry.id in seen:
                    raise ValueError(f"watchlist entry {entry.id!r}: duplicate id")
                seen.add(entry.id)
                entries.append(entry)
        except FileNotFoundError:
            # If demo file doesn't exist, continue with just the main entries
            pass
    return Watchlist(version=version, entries=tuple(entries))


def _entry(raw: dict, where: str) -> Entry:
    entry_id = raw.get("id")
    if not isinstance(entry_id, str) or not _ID.fullmatch(entry_id):
        raise ValueError(f"watchlist entry {where}: id {entry_id!r} is not kebab-case")
    name = f"watchlist entry {entry_id!r}"

    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise ValueError(f"{name}: unknown field(s) {unknown}")
    if raw.get("category") not in CATEGORIES:
        raise ValueError(
            f"{name}: category {raw.get('category')!r} is not one of {list(CATEGORIES)}"
        )
    if raw.get("severity") not in SEVERITIES:
        raise ValueError(
            f"{name}: severity {raw.get('severity')!r} is not one of {list(SEVERITIES)}"
        )
    lists: dict[str, tuple[str, ...]] = {}
    for field in _LIST_FIELDS:
        value = raw.get(field)
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError(f"{name}: {field} must be a non-empty list of strings")
        lists[field] = tuple(value)
    for phrase in lists["phrases"]:
        if not normalize(phrase):
            raise ValueError(f"{name}: phrase {phrase!r} is empty once normalized")

    entry = Entry(
        id=entry_id, category=raw["category"], severity=raw["severity"], **lists
    )
    for example in entry.must_match:
        if not entry.matches(example):
            raise ValueError(f"{name}: must_match example {example!r} does not match")
    for example in entry.must_not_match:
        if entry.matches(example):
            raise ValueError(f"{name}: must_not_match example {example!r} matches")
    return entry
