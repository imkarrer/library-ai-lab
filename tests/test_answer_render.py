"""static/answer.js, run in node: what a model's Markdown becomes for a Student."""

import json
import subprocess

from fastapi.testclient import TestClient

from library_assistant.app import app
from library_assistant.routers.session import CHAT_PAGE_HTML
from library_assistant.theme import ANSWER_SCRIPT_PATH, STATIC_DIR

SCRIPT = STATIC_DIR / "answer.js"


def _call(function: str, text: str):
    program = (
        f"const answer = require({json.dumps(str(SCRIPT))});"
        f"console.log(JSON.stringify(answer.{function}({json.dumps(text)})));"
    )
    result = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, timeout=30, check=True
    )
    return json.loads(result.stdout)


def test_a_table_becomes_rows_and_cells():
    text = (
        "Some ants:\n\n"
        "| Type | Where |\n|------|:---:|\n"
        "| **Pygmy** | Caves |\n| Fire ant | Lawns |\n\n"
        "That's all."
    )
    assert _call("answerBlocks", text) == [
        {"type": "paragraph", "text": "Some ants:"},
        {
            "type": "table",
            "header": ["Type", "Where"],
            "rows": [["**Pygmy**", "Caves"], ["Fire ant", "Lawns"]],
        },
        {"type": "paragraph", "text": "That's all."},
    ]


def test_a_table_right_after_a_sentence_is_still_a_table():
    blocks = _call("answerBlocks", "Look:\n| A | B |\n|---|---|\n| 1 | 2 |")
    assert [block["type"] for block in blocks] == ["paragraph", "table"]


def test_a_pipe_in_a_sentence_is_not_a_table():
    assert _call("answerBlocks", "Use a | b here.") == [
        {"type": "paragraph", "text": "Use a | b here."}
    ]


def test_a_half_streamed_table_stays_text_until_it_is_one():
    assert _call("answerBlocks", "| Type | Where |")[0]["type"] == "paragraph"


def test_lists_hold_together_across_blank_lines():
    [block] = _call("answerBlocks", "1. One\n\n2. Two\n3) Three")
    assert (block["type"], block["ordered"]) == ("list", True)
    assert block["items"] == ["One", "Two", "Three"]


def test_bullets_and_numbers_are_separate_lists():
    blocks = _call("answerBlocks", "- One\n- Two\n1. Three")
    assert [block["ordered"] for block in blocks] == [False, True]


def test_a_heading_and_a_rule():
    assert _call("answerBlocks", "## Ants\n\n---\n\nThey dig.") == [
        {"type": "heading", "text": "Ants"},
        {"type": "paragraph", "text": "They dig."},
    ]


def test_bold_italic_and_bold_around_italic():
    assert _call("inlineParts", "An **ant** and a *bee*") == [
        {"text": "An "},
        {"tag": "strong", "parts": [{"text": "ant"}]},
        {"text": " and a "},
        {"tag": "em", "parts": [{"text": "bee"}]},
    ]
    assert _call("inlineParts", "**Genus *Ooceraea***") == [
        {
            "tag": "strong",
            "parts": [
                {"text": "Genus "},
                {"tag": "em", "parts": [{"text": "Ooceraea"}]},
            ],
        }
    ]


def test_stray_asterisks_stay_as_they_are():
    assert _call("inlineParts", "2 * 3 * 4 and **half") == [
        {"text": "2 * 3 * 4 and **half"}
    ]


def test_nothing_a_model_writes_can_become_markup():
    assert "innerHTML" not in SCRIPT.read_text()
    assert "insertAdjacentHTML" not in SCRIPT.read_text()
    assert _call("answerBlocks", "<img src=x onerror=alert(1)>") == [
        {"type": "paragraph", "text": "<img src=x onerror=alert(1)>"}
    ]


def test_the_script_is_served_with_no_session_and_the_chat_page_loads_it():
    response = TestClient(app).get(ANSWER_SCRIPT_PATH)
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert f'<script src="{ANSWER_SCRIPT_PATH}"></script>' in CHAT_PAGE_HTML
