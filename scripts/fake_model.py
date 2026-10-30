#!/usr/bin/env python3
"""A fake model server for development and integration tests: no Ollama, no GPU.

It answers the two requests the assistant makes, on the OpenAI-style API both Lanes use:

- The Answer lane (streamed): a short overview naming the question's subject, then the
  `SEARCH:` line the Catalog search reads (library_assistant/prompt.py).
- The Oversight Lane (not streamed, recognised by Oversight's system prompt): a Verdict from
  keyword rules, so a test can raise a Flag of a chosen category and severity on purpose.

Deterministic: the same question gets the same answer. `--delay-ms` spaces the streamed
chunks so a page shows text arriving, as with a real model.

    python3 scripts/fake_model.py --port 8090
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections.abc import AsyncIterator
from pathlib import Path

# Run as `python3 scripts/fake_model.py`, Python puts scripts/ on the path, not the repo.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from library_assistant.oversight import _SYSTEM_PROMPT as OVERSIGHT_PROMPT

# (phrases, category, severity): first match wins, most serious first.
VERDICT_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("hurt myself", "kill myself", "disappear", "end it all"), "self-harm", "high"),
    (("hits me", "hurts me at home", "touched me"), "abuse", "high"),
    (("bring a gun", "going to hurt them", "shoot"), "threats-of-violence", "high"),
    (("stink", "picks on me", "makes me cry", "calls me names"), "bullying", "low"),
]

STOPWORDS = {
    "about",
    "there",
    "their",
    "which",
    "would",
    "could",
    "books",
    "what",
    "when",
    "where",
    "does",
    "have",
    "with",
    "from",
    "that",
    "this",
    "your",
    "they",
    "were",
    "tell",
    "some",
    "into",
    "make",
    "many",
    "more",
    "most",
    "than",
    "then",
    "them",
    "these",
    "those",
    "very",
    "also",
    "just",
    "like",
    "know",
    "want",
    "find",
}


def subject_terms(question: str) -> list[str]:
    """Up to three words from the question to talk about and search for."""
    words = re.findall(r"[a-zA-Z]{4,}", question.lower())
    terms: list[str] = []
    for word in words:
        if word not in STOPWORDS and word not in terms:
            terms.append(word)
    return terms[:3] or ["reading"]


def answer_text(question: str) -> str:
    terms = subject_terms(question)
    subject = ", ".join(terms)
    return (
        f"Here is a short overview about {subject}. This is the fake model, so it "
        "knows nothing really: it only shows how an answer arrives.\n"
        f"SEARCH: {'; '.join(terms)}"
    )


def verdict(question: str) -> dict:
    lowered = question.lower()
    for phrases, category, severity in VERDICT_RULES:
        if any(phrase in lowered for phrase in phrases):
            return {
                "category": category,
                "severity": severity,
                "reason": f"fake model: matched a {category} phrase",
            }
    return {"category": None, "severity": None, "reason": "fake model: no concern"}


def _user_text(body: dict) -> str:
    return next(
        (m["content"] for m in reversed(body["messages"]) if m["role"] == "user"), ""
    )


def build_app(delay_ms: int) -> FastAPI:
    app = FastAPI(title="Fake model")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        question = _user_text(body)
        system = next(
            (m["content"] for m in body["messages"] if m["role"] == "system"), ""
        )
        if system == OVERSIGHT_PROMPT:
            content = json.dumps(verdict(question))
            return JSONResponse(
                {"choices": [{"message": {"role": "assistant", "content": content}}]}
            )
        text = answer_text(question)
        if not body.get("stream"):
            return JSONResponse(
                {"choices": [{"message": {"role": "assistant", "content": text}}]}
            )

        async def chunks() -> AsyncIterator[bytes]:
            for piece in re.findall(r"\S+\s*", text):
                event = {"choices": [{"delta": {"content": piece}}]}
                yield f"data: {json.dumps(event)}\n\n".encode()
                if delay_ms:
                    await asyncio.sleep(delay_ms / 1000)
            yield b"data: [DONE]\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    return app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--delay-ms", type=int, default=30)
    args = parser.parse_args(argv)
    uvicorn.run(
        build_app(args.delay_ms),
        host=args.host,
        port=args.port,
        access_log=False,
        timeout_graceful_shutdown=1,
    )


if __name__ == "__main__":
    main()
