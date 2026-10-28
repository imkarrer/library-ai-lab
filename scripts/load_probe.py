#!/usr/bin/env python3
"""Load probe: time concurrent asks against an Install.

Binding: ADR-0009. Mints throwaway Cards, signs each in with its own
httpx.AsyncClient, then fires concurrent asks at every concurrency level
from 1 up to the number of Cards minted, reporting p50/p95 time to first
byte and time to the full answer.
"""

import argparse
import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import httpx

from library_assistant.mint import Card, mint_cards

CLASS_LABEL = "load probe"


class Timing(NamedTuple):
    concurrency: int
    ttfb_p50: float
    ttfb_p95: float
    ttlb_p50: float
    ttlb_p95: float


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = round(pct / 100 * (len(ordered) - 1))
    return ordered[index]


async def _timed_ask(
    client: httpx.AsyncClient, question: str, clock: Callable[[], float]
) -> tuple[float, float]:
    start = clock()
    ttfb = None
    async with client.stream("POST", "/ask", json={"question": question}) as response:
        response.raise_for_status()
        async for _ in response.aiter_bytes():
            if ttfb is None:
                ttfb = clock() - start
    ttlb = clock() - start
    if ttfb is None:
        ttfb = ttlb
    return ttfb, ttlb


async def probe(
    client_factory: Callable[[], httpx.AsyncClient],
    cards: list[Card],
    question: str,
    rounds: int,
    clock: Callable[[], float] = time.monotonic,
) -> list[Timing]:
    """Sign in one Client per Card, then fire concurrent asks at every level 1..N.

    `clock` returns seconds; tests inject a fake one.
    """
    clients = [client_factory() for _ in cards]
    try:
        for client, card in zip(clients, cards):
            response = await client.post("/card", json={"token": card.token})
            # Report the status alone: the request carries the Token.
            if response.status_code != 200:
                raise SystemExit(f"Card sign-in refused ({response.status_code})")

        results = []
        for concurrency in range(1, len(cards) + 1):
            ttfb_samples: list[float] = []
            ttlb_samples: list[float] = []
            for _ in range(rounds):
                round_results = await asyncio.gather(
                    *(
                        _timed_ask(client, question, clock)
                        for client in clients[:concurrency]
                    )
                )
                for ttfb, ttlb in round_results:
                    ttfb_samples.append(ttfb)
                    ttlb_samples.append(ttlb)
            results.append(
                Timing(
                    concurrency=concurrency,
                    ttfb_p50=_percentile(ttfb_samples, 50),
                    ttfb_p95=_percentile(ttfb_samples, 95),
                    ttlb_p50=_percentile(ttlb_samples, 50),
                    ttlb_p95=_percentile(ttlb_samples, 95),
                )
            )
        return results
    finally:
        for client in clients:
            await client.aclose()


def render_report(timings: list[Timing]) -> str:
    header = (
        f"{'concurrency':>11}  {'ttfb_p50':>8}  {'ttfb_p95':>8}  "
        f"{'ttlb_p50':>8}  {'ttlb_p95':>8}"
    )
    lines = [header]
    for timing in timings:
        lines.append(
            f"{timing.concurrency:>11}  {timing.ttfb_p50:>8.3f}  "
            f"{timing.ttfb_p95:>8.3f}  {timing.ttlb_p50:>8.3f}  {timing.ttlb_p95:>8.3f}"
        )
    return "\n".join(lines)


async def run_and_print(
    client_factory: Callable[[], httpx.AsyncClient],
    cards: list[Card],
    question: str,
    rounds: int,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    timings = await probe(client_factory, cards, question, rounds, clock)
    print(render_report(timings))


def build_client_factory(
    base_url: str, transport: httpx.AsyncBaseTransport | None = None
) -> Callable[[], httpx.AsyncClient]:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=base_url, transport=transport)

    return factory


def register_cards(base_url: str, registration_key: str, mint_result) -> None:
    payload = {**mint_result.registration_payload, "registration_key": registration_key}
    with httpx.Client(base_url=base_url) as client:
        response = client.post("/batches", json=payload)
        response.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Time concurrent asks against an Install"
    )
    parser.add_argument("--base-url", required=True, help="Base URL of the Install")
    parser.add_argument("--registration-key", required=True, help="Registration key")
    parser.add_argument(
        "--cards", type=int, required=True, help="Number of Cards to mint"
    )
    parser.add_argument("--question", required=True, help="Question to ask")
    parser.add_argument(
        "--rounds", type=int, default=1, help="Rounds per concurrency level"
    )
    args = parser.parse_args()

    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    mint_result = mint_cards(args.cards, CLASS_LABEL, expires_at)
    register_cards(args.base_url, args.registration_key, mint_result)

    client_factory = build_client_factory(args.base_url)
    asyncio.run(
        run_and_print(client_factory, mint_result.cards, args.question, args.rounds)
    )


if __name__ == "__main__":
    main()
