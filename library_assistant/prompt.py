"""Prompt building for the Research answer: an overview from the model, then books found with its search terms.

The prompt is a short overview of the subject from the model's own knowledge, for 11-to-13-year-olds, plain words,
honest when unsure, never naming a book as if the library has it. The reply ends with one line exactly
`SEARCH: term; term; term` (2-4 library subject terms).

A second, short prompt shows the model what that search found and has it choose the books that fit and say why. Keyword
search can't tell red wolves from red barns; the model can. It only ever chooses by number from Records it was given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from library_assistant.catalog import Record

RESEARCH_PROMPT = """You are a helpful librarian. Answer the student's question using only your own knowledge, not the records. For 11-to-13-year-olds, use plain words. If you're not sure, say so. Never mention a book as if it's in our library.

After your answer, end with one last line in exactly this form, and nothing after it:
SEARCH: term; term; term
Use 2 to 4 short library subject terms for books on the topic. For example, for a question about what sharks eat:
SEARCH: sharks; marine animals; food chains"""


def build_messages(question: str) -> list[dict]:
    """Build the messages for the research answer prompt."""
    return [
        {"role": "system", "content": RESEARCH_PROMPT},
        {"role": "user", "content": question},
    ]


# The most books a Student is shown for one question.
MAX_BOOKS = 5

PICK_PROMPT = f"""You help a student aged 11 to 13 choose books from a school library. You are given their question and a numbered list of books from the library's catalog. Choose up to {MAX_BOOKS} books that would really help with the question, best first. Leave out any book that only shares a word with the question but is about something else.

Go only by the title, subjects, and summary you are given. You have not read these books, so never add details that are not there, and never say how good or easy a book is.

For each book you choose, write one line in exactly this form:
3: one short sentence in plain words on what this book is about
Use the book's number from the list. Write nothing else. If no book fits, write only:
NONE"""

_PICK_LINE = re.compile(r"\s*\[?(\d+)\]?\s*[:.)]\s*(\S.*)")
# A model sometimes runs its picks together on one line: "1: A book. 2: Another."
_RUN_TOGETHER_PICK = re.compile(r"(?<=[.!?])\s+(?=\d+:\s)")

# Enough of a Record for the model to judge it, and no more: every book costs prompt.
_DESCRIPTION_CHARS = 200


def build_pick_messages(question: str, records: list[Record]) -> list[dict]:
    """Build the messages asking the model to choose among `records`."""
    books = "\n".join(
        f"{number}. {record.title} {record.author} "
        f"Subjects: {record.subjects[:_DESCRIPTION_CHARS]} "
        f"Summary: {record.summary[:_DESCRIPTION_CHARS]}"
        for number, record in enumerate(records, start=1)
    )
    return [
        {"role": "system", "content": PICK_PROMPT},
        {"role": "user", "content": f"Question: {question}\n\nBooks:\n{books}"},
    ]


def parse_picks(reply: str, count: int) -> list[tuple[int, str]] | None:
    """The (0-based index, reason) pairs in a reply about `count` books, best first.

    [] means the model said no book fits. None means the reply can't be read, so the
    caller falls back on the search's own order. A number outside the list is dropped:
    the model can only choose a book it was shown.
    """
    if reply.strip().upper().rstrip(".") == "NONE":
        return []
    picks: dict[int, str] = {}
    for line in _RUN_TOGETHER_PICK.sub("\n", reply).splitlines():
        match = _PICK_LINE.fullmatch(line.strip())
        if match is None:
            continue
        index = int(match.group(1)) - 1
        if 0 <= index < count and index not in picks:
            why = match.group(2).strip()
            picks[index] = why[0].upper() + why[1:]
    return list(picks.items())[:MAX_BOOKS] or None


# "SEARCH:" as asked, and "SEARCH;", a slip a small model makes (qwen3.5:4b, lib-30v).
_SEARCH_LINE = re.compile(r"\s*SEARCH\s*[:;]")


@dataclass
class SearchLineFilter:
    """A filter for streaming responses that holds back lines starting with 'SEARCH:'.

    This enables us to parse the search terms from the model's response before
    yielding the rest of the text, so we can perform a catalog search.
    """

    _buffer: str = ""
    _search_terms: list[str] = None

    def feed(self, delta: str) -> str:
        """Feed a delta from the streaming response to the filter.

        If the delta contains a line starting with 'SEARCH:', it will be held back
        until finish() is called. This allows us to parse the search terms before
        yielding the rest of the text.
        """
        self._buffer += delta
        lines = self._buffer.splitlines(keepends=True)
        # If the last line is incomplete (doesn't end with a newline), keep it in the buffer
        if not self._buffer.endswith("\n"):
            self._buffer = lines.pop()
        else:
            self._buffer = ""

        return "".join(line for line in lines if not self._take_search_line(line))

    def _take_search_line(self, line: str) -> bool:
        """Record `line`'s terms and return True if it is a SEARCH line."""
        match = _SEARCH_LINE.match(line)
        if match is None:
            return False
        if self._search_terms is None:
            self._search_terms = []
        self._search_terms.extend(
            term.strip() for term in line[match.end() :].split(";") if term.strip()
        )
        return True

    def finish(self) -> tuple[str, list[str]]:
        """Finish the filter and return the remaining text and search terms.

        Returns:
            A tuple of (remaining_text, search_terms) where remaining_text is the
            text that was not prefixed with 'SEARCH:' and search_terms is the list
            of search terms found in the response.
        """
        # The last line, which a model usually ends without a newline, may be the SEARCH
        # line itself: it is held back like any other.
        output, self._buffer = self._buffer, ""
        if output and self._take_search_line(output):
            output = ""

        # If we didn't find any search terms, return empty list
        if self._search_terms is None:
            self._search_terms = []

        return output, self._search_terms
