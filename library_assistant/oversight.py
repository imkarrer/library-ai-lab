"""The Oversight lane: one call screens one Student message against the Rubric.

Binding: ADR-0004, and the request/verdict contract decided in lib-f24.28. `screen` is the
only thing that talks to the Oversight endpoint; it retries once on an unparseable reply or
an unknown category, and raises `OversightUnavailable` for a connection error, a timeout, or
two bad replies in a row so the caller can fall back to the Watchlist alone.

While Oversight is down (ADR-0004 addendum, "Oversight down does not hold Students") the
module-level `screening_state` says since when, and whether an adult paused Sessions over
it; `probe` asks the endpoint whether it is back.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import IO

import httpx

logger = logging.getLogger(__name__)

RUBRIC_CATEGORIES = {"self-harm", "abuse", "bullying", "threats-of-violence"}

_SYSTEM_PROMPT = (
    "You are Oversight for a school library assistant. Decide whether the Student's "
    "message raises a concern in one of four Rubric categories: self-harm, abuse, "
    "bullying, threats-of-violence. Reply with exactly one JSON object and nothing else: "
    '{"category": "self-harm" | "abuse" | "bullying" | "threats-of-violence" | null, '
    '"severity": "high" | "low" | null, "reason": "<one short sentence>"}. '
    "Use null for category and severity when there is no concern."
)


@dataclass(frozen=True)
class Verdict:
    category: str | None
    severity: str | None
    reason: str


class OversightUnavailable(Exception):
    """The Oversight endpoint gave no usable verdict for this message."""


# A fixed message, never a Student's words: the probe only asks whether a verdict comes back.
PROBE_TEXT = "Is there a library book about clouds?"


@dataclass
class ScreeningState:
    """Whether Oversight is answering, and whether Sessions are paused.

    Process memory only (one process, ADR-0008): nothing here is stored or logged.
    `paused_by_setting` marks a pause the Install made itself (`oversight_down = pause`,
    decision lib-f24.77), which lifts when Oversight answers again; a pause an adult
    chose lifts only when an adult resumes.
    """

    unavailable_since: datetime | None = None
    paused: bool = False
    paused_by_setting: bool = False

    def reset(self) -> None:
        self.unavailable_since = None
        self.paused = False
        self.paused_by_setting = False


screening_state = ScreeningState()


def get_screening_state() -> ScreeningState:
    return screening_state


async def probe(client: httpx.AsyncClient, settings) -> bool:
    """True when the Oversight endpoint gives a verdict again."""
    try:
        await screen(client, settings, PROBE_TEXT)
    except OversightUnavailable:
        return False
    return True


def acquire_oversight_lock(db_path: str) -> IO | None:
    """Acquire an exclusive lock for Oversight operations.

    Args:
        db_path: Path to the database file

    Returns:
        File handle if lock acquired, None if another process holds the lock
    """
    # Create the lock file path in the same directory as the database
    lock_file_path = os.path.join(os.path.dirname(db_path), "oversight.lock")

    try:
        # Open the lock file (create if it doesn't exist) without context manager
        # ruff SIM115: We need to keep the file handle open for the process lifetime
        lock_file = open(lock_file_path, "w")  # noqa: SIM115
        # Try to acquire an exclusive non-blocking lock
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return lock_file
        except BlockingIOError:
            # Another process holds the lock
            # Close the file before returning None
            lock_file.close()
            logger.warning(f"Oversight off: another process holds {lock_file_path}")
            return None
    except OSError:
        # Handle file system errors (permissions, non-existent directory, etc.)
        return None


async def screen(client: httpx.AsyncClient, settings, question: str) -> Verdict:
    """Ask the Oversight lane for a Verdict on one Student message.

    One retry covers an unparseable reply or an unknown category; a connection error or a
    timeout raises `OversightUnavailable` at once, since retrying a dead endpoint only adds
    latency the Student's next message would wait on.
    """
    for _attempt in range(2):
        try:
            content = await _request(client, settings, question)
        except httpx.HTTPError as exc:
            raise OversightUnavailable("Oversight endpoint unavailable") from exc
        verdict = _parse_verdict(content)
        if verdict is not None:
            return verdict
    # The reply stays out of the message: it may echo the Student's words, and exception
    # text can outlive the daily purge in logs (ADR-0003).
    raise OversightUnavailable("Oversight reply unparseable after one retry")


async def _request(client: httpx.AsyncClient, settings, question: str) -> str | None:
    # The full URL, not a path, so the call reaches the configured Oversight endpoint
    # whatever base_url the caller's client carries (the shared client points at the
    # Answer lane).
    body: dict[str, object] = {
        "model": settings.oversight_model,
        "stream": False,
        "temperature": 0,
        "max_tokens": 256,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    }
    if settings.oversight_reasoning_effort:
        body["reasoning_effort"] = settings.oversight_reasoning_effort
    response = await client.post(
        f"{settings.oversight_endpoint.rstrip('/')}/chat/completions",
        json=body,
        timeout=settings.oversight_timeout_seconds,
    )
    response.raise_for_status()
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return content if isinstance(content, str) else None


def _parse_verdict(content: str | None) -> Verdict | None:
    """The first {...} in the reply as a Verdict, or None when it is unusable."""
    if content is None:
        return None
    match = re.search(r"\{.*?\}", content, re.DOTALL)
    if match is None:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    category = data.get("category")
    if category is not None and category not in RUBRIC_CATEGORIES:
        return None
    return Verdict(
        category=category,
        severity=data.get("severity"),
        reason=str(data.get("reason", "")),
    )
