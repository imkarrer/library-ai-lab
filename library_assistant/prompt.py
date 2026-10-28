"""Prompt building for the Research answer: an overview from the model, then books found with its search terms.

The prompt is a short overview of the subject from the model's own knowledge, for 11-to-13-year-olds, plain words,
honest when unsure, never naming a book as if the library has it. The reply ends with one line exactly
`SEARCH: term; term; term` (2-4 library subject terms).
"""

from __future__ import annotations

from dataclasses import dataclass

RESEARCH_PROMPT = """You are a helpful librarian. Answer the student's question using only your own knowledge, not the records. For 11-to-13-year-olds, use plain words. If you're not sure, say so. Never mention a book as if it's in our library.

SEARCH: """


def build_messages(question: str) -> list[dict]:
    """Build the messages for the research answer prompt."""
    return [
        {"role": "system", "content": RESEARCH_PROMPT},
        {"role": "user", "content": question},
    ]


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

        output = ""
        for line in lines:
            if line.startswith("SEARCH:"):
                if self._search_terms is None:
                    self._search_terms = []
                self._search_terms.extend(
                    term.strip()
                    for term in line.removeprefix("SEARCH:").split(";")
                    if term.strip()
                )
            else:
                output += line
        return output

    def finish(self) -> tuple[str, list[str]]:
        """Finish the filter and return the remaining text and search terms.

        Returns:
            A tuple of (remaining_text, search_terms) where remaining_text is the
            text that was not prefixed with 'SEARCH:' and search_terms is the list
            of search terms found in the response.
        """
        # Handle any remaining text that was not a complete line
        if self._buffer:
            output = self._buffer
            self._buffer = ""
        else:
            output = ""

        # If we didn't find any search terms, return empty list
        if self._search_terms is None:
            self._search_terms = []

        return output, self._search_terms
