"""Prompt building for the Research answer: an overview from the model, then books found with its search terms.

The prompt is a short overview of the subject from the model's own knowledge, for 11-to-13-year-olds, plain words,
honest when unsure, never naming a book as if the library has it. The reply ends with one line exactly
`SEARCH: term; term; term` (2-4 library subject terms).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

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
