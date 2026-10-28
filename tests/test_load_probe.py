#!/usr/bin/env python3
"""Tests for load_probe.py, against a fake Install built from httpx.MockTransport.

No network and no wall-clock sleeps: the fake Install advances an injected clock.
"""

import asyncio
import json

import httpx
from load_probe import build_client_factory, probe, run_and_print

from library_assistant.mint import Card

QUESTION = "what is a fish?"
FIRST_BYTE_DELAY = 0.25
ANSWER_DELAY = 1.0


def make_cards(n: int) -> list[Card]:
    return [Card(token=f"token-{i}", card_number=str(i)) for i in range(n)]


class FakeInstall:
    """Records every /card sign-in and the concurrency seen by /ask.

    `clock` is the probe's clock: it advances only when the fake Install says so.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.signed_tokens: list[str] = []
        self.current_concurrency = 0
        self.concurrency_log: list[int] = []

    def clock(self) -> float:
        return self.now

    async def _answer(self):
        yield b"a grounded "
        self.now += ANSWER_DELAY
        yield b"answer"

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/card":
            payload = json.loads(request.content)
            self.signed_tokens.append(payload["token"])
            return httpx.Response(200, text="ok")
        if request.url.path == "/ask":
            self.current_concurrency += 1
            self.concurrency_log.append(self.current_concurrency)
            # Yield to the event loop (no wall-clock wait) so sibling asks overlap.
            for _ in range(5):
                await asyncio.sleep(0)
            self.current_concurrency -= 1
            self.now += FIRST_BYTE_DELAY
            return httpx.Response(200, content=self._answer())
        raise AssertionError(f"unexpected path {request.url.path}")

    def client_factory(self) -> httpx.AsyncClient:
        transport = httpx.MockTransport(self.handler)
        return build_client_factory("http://fake-install", transport)()


def test_probe_signs_in_each_card():
    install = FakeInstall()
    cards = make_cards(3)

    asyncio.run(probe(install.client_factory, cards, QUESTION, 1, install.clock))

    assert sorted(install.signed_tokens) == sorted(card.token for card in cards)


def test_probe_fires_n_concurrent_asks():
    install = FakeInstall()
    cards = make_cards(3)
    rounds = 2

    asyncio.run(probe(install.client_factory, cards, QUESTION, rounds, install.clock))

    assert max(install.concurrency_log) == len(cards)
    # Every level 1..N runs `rounds` times with that many asks at once.
    assert len(install.concurrency_log) == rounds * sum(range(1, len(cards) + 1))


def test_report_has_p50_p95_per_level(capsys):
    install = FakeInstall()
    cards = make_cards(3)

    asyncio.run(
        run_and_print(install.client_factory, cards, QUESTION, 2, install.clock)
    )

    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].split() == [
        "concurrency",
        "ttfb_p50",
        "ttfb_p95",
        "ttlb_p50",
        "ttlb_p95",
    ]
    rows = [line.split() for line in lines[1:]]
    assert [int(row[0]) for row in rows] == [1, 2, 3]
    for row in rows:
        assert len(row) == 5
        ttfb_p50, ttfb_p95, ttlb_p50, ttlb_p95 = (float(cell) for cell in row[1:])
        assert ttfb_p50 >= FIRST_BYTE_DELAY
        assert ttfb_p95 >= ttfb_p50
        assert ttlb_p50 >= ttfb_p50 + ANSWER_DELAY
        assert ttlb_p95 >= ttlb_p50
    # A lone ask sees only its own delays, read off the fake clock.
    assert rows[0][1:] == ["0.250", "0.250", "1.250", "1.250"]


def test_output_has_no_token(capsys):
    install = FakeInstall()
    cards = make_cards(2)

    asyncio.run(
        run_and_print(install.client_factory, cards, QUESTION, 1, install.clock)
    )

    captured = capsys.readouterr()
    assert captured.out
    for card in cards:
        assert card.token not in captured.out
        assert card.token not in captured.err
