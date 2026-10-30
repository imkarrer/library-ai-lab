"""The fake model (scripts/fake_model.py): what the stack and the integration tests rely on."""

import json

from fake_model import answer_text, build_app, verdict
from fastapi.testclient import TestClient

from library_assistant.oversight import _SYSTEM_PROMPT, _parse_verdict
from library_assistant.prompt import RESEARCH_PROMPT, SearchLineFilter


def test_answer_ends_with_a_search_line_the_filter_reads():
    f = SearchLineFilter()
    shown = f.feed(answer_text("What do wolves eat in winter?"))
    rest, terms = f.finish()
    assert "wolves" in shown and "SEARCH" not in shown + rest
    assert terms == ["wolves", "winter"]


def test_verdicts_follow_keyword_rules():
    assert verdict("Billy says I stink")["category"] == "bullying"
    assert verdict("i want to disappear")["severity"] == "high"
    assert verdict("my dad hits me")["category"] == "abuse"
    assert verdict("how do volcanoes form?")["category"] is None


def _chat(client, system, question, stream):
    return client.post(
        "/v1/chat/completions",
        json={
            "model": "fake",
            "stream": stream,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        },
    )


def test_oversight_prompt_gets_a_verdict_the_assistant_parses():
    client = TestClient(build_app(delay_ms=0))
    response = _chat(client, _SYSTEM_PROMPT, "everyone picks on me", stream=False)
    content = response.json()["choices"][0]["message"]["content"]
    parsed = _parse_verdict(content)
    assert (parsed.category, parsed.severity) == ("bullying", "low")


def test_answer_lane_streams_openai_chunks():
    client = TestClient(build_app(delay_ms=0))
    response = _chat(client, RESEARCH_PROMPT, "tell me about sharks", stream=True)
    events = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1] == "[DONE]"
    text = "".join(json.loads(e)["choices"][0]["delta"]["content"] for e in events[:-1])
    assert text == answer_text("tell me about sharks")
