"""Test helpers for registering a Batch the way the Teacher's machine does (ADR-0002)."""

from __future__ import annotations

from library_assistant.access import hash_token


def batch_cards(*cards: tuple[str, str]) -> list[dict[str, str]]:
    """The `cards` of a Registration payload for (Token, Card number) pairs.

    Registration carries each Token's hash, never the Token, so a test keeps the raw
    Token to sign in with while /batches sees only its hash.
    """
    return [
        {"token_hash": hash_token(token), "card_number": card_number}
        for token, card_number in cards
    ]
