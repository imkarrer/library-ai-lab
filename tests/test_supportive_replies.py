#!/usr/bin/env python3
"""Tests for supportive replies with overrides."""

from library_assistant.supportive_replies import (
    get_supportive_reply_text,
)


def test_valid_override_fills_counselor_and_strips_bold():
    """Test that valid overrides get counselor filled and bold markers stripped."""
    # This would be a valid override
    override_text = """It sounds like you are going through something really hard. You don't have to handle it alone.

Please talk to an adult you trust today, like {counselor} or the librarian.

You can call or text **988** any time, day or night. It is free, and a real person will listen. If you might hurt yourself right now, tell an adult near you or call **911**.

I am a library computer, so a person can help with this better than I can. An adult here may check in with you, because they care how you are doing."""

    result = get_supportive_reply_text(
        "self_harm", "Jane Smith", {"self_harm": override_text}
    )

    # The counselor should be filled in
    assert "Jane Smith" in result

    # Bold markers should be stripped
    assert "**" not in result

    # 988 should be present
    assert "988" in result


def test_invalid_override_falls_back_to_default():
    """Test that invalid overrides fall back to default text."""
    # This override is invalid - missing 988
    invalid_override = """It sounds like you are going through something really hard. You don't have to handle it alone.

Please talk to an adult you trust today, like the librarian.

You can call or text any time, day or night. It is free, and a real person will listen. If you might hurt yourself right now, tell an adult near you or call **911**.

I am a library computer, so a person can help with this better than I can. An adult here may check in with you, because they care how you are doing."""

    result = get_supportive_reply_text(
        "self_harm", "Jane Smith", {"self_harm": invalid_override}
    )

    # Should fall back to default and have counselor filled in and bold stripped
    assert "Jane Smith" in result
    assert "**" not in result
    assert "988" in result  # Should be from default
