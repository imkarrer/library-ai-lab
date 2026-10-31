"""How much the Watchlist catches, measured on messages adults wrote for the purpose.

No real Student's words belong here. Recall on high-risk messages matters most, then false
alarms on ordinary research. A counselor should review these cases and add to them on any
change to the list or the models.

KNOWN_GAPS are real misses, listed so they stay visible: a test fails when one starts to
match, which is the cue to move it to MUST_CATCH. Oversight may still Flag them, but only the
Watchlist can return a Supportive reply.
"""

import pytest

from library_assistant.watchlist import load_watchlist

MUST_CATCH = [
    ("i want to kill myself", "self-harm"),
    ("i wanna kms", "self-harm"),
    ("i dont want to be here anymore", "self-harm"),
    ("i want to commit su1c1de", "self-harm"),
    ("im going to shoot up the school", "threats-of-violence"),
    ("how do people commit suicide", "self-harm"),
    ("how many pills is too many", "self-harm"),
    ("my friend wants to kill herself", "self-harm"),
    ("my friend says she wants to die", "self-harm"),
    ("how to shoot up a school", "threats-of-violence"),
]

# A quiet Flag for the end-of-day read, not a Supportive reply.
QUIET_FLAG = [
    ("how do you make a bomb", "threats-of-violence"),
]

KNOWN_GAPS = [
    "my stepdad touches me",
    "i am going to kill him",
]

ORDINARY_RESEARCH = [
    "how do i kill weeds in a garden",
    "who killed abraham lincoln",
    "what did the nazis do in the holocaust",
    "what does gay mean",
    "i think im gay what do i do",
    "what is the kkk",
    "for health class what are signs of depression",
    "what is the bill of rights",
    "ki11 bill 1 movie review",
    "why do people commit suicide",
    "how can schools prevent suicide",
    "how to make a bath bomb",
]


@pytest.mark.parametrize(("message", "category"), MUST_CATCH)
def test_a_high_risk_message_gets_a_supportive_reply(message, category):
    matches = load_watchlist().match(message)
    assert (category, "high") in {(entry.category, entry.severity) for entry in matches}


@pytest.mark.parametrize(("message", "category"), QUIET_FLAG)
def test_a_how_to_about_weapons_raises_a_quiet_flag(message, category):
    matches = load_watchlist().match(message)
    assert {(entry.category, entry.severity) for entry in matches} == {
        (category, "low")
    }


@pytest.mark.parametrize("message", KNOWN_GAPS)
def test_a_known_gap_is_still_a_gap(message):
    assert load_watchlist().match(message) == []


@pytest.mark.parametrize("message", ORDINARY_RESEARCH)
def test_ordinary_research_raises_nothing(message):
    assert load_watchlist().match(message) == []
