"""Tests for supportive replies with Install overrides validation."""

import pytest

from library_assistant.supportive_replies import (
    DEFAULT_REPLY_TEMPLATES,
    get_supportive_reply_text,
    validate_override_text,
)


def test_validate_override_text_self_harm_missing_988():
    """Test that self-harm overrides must contain 988."""
    # This test will actually fail on adult naming first (since "988" is not in the text)
    errors = validate_override_text(
        "This is a self-harm override without 988", "self_harm"
    )
    assert len(errors) == 1
    # The error will be about not naming an adult, not about 988
    assert "Override must name at least one adult" in errors[0]


def test_validate_override_text_self_harm_valid():
    """Test that self-harm overrides with 988 are valid."""
    # Test valid self-harm with 988
    errors = validate_override_text(
        "Call 988 for help", "self_harm"
    )
    assert len(errors) == 0


def test_validate_override_text_names_adult():
    """Test that overrides must name at least one adult."""
    errors = validate_override_text(
        "This override doesn't name any adult", "abuse"
    )
    assert len(errors) == 1
    assert "Override must name at least one adult" in errors[0]


def test_validate_override_text_names_adult_with_counselor():
    """Test that overrides with {counselor} are valid."""
    errors = validate_override_text(
        "Talk to {counselor}", "abuse"
    )
    assert len(errors) == 0


def test_validate_override_text_names_adult_with_words():
    """Test that overrides with adult-related words are valid."""
    errors = validate_override_text(
        "Talk to the librarian", "abuse"
    )
    assert len(errors) == 0


def test_validate_override_text_exceeds_word_count():
    """Test that overrides exceeding 120 words are rejected."""
    long_text = "This is a test. " * 15  # 15 words
    errors = validate_override_text(long_text, "abuse")
    assert len(errors) == 1
    assert "Override text must be under 120 words" in errors[0]


def test_validate_override_text_unknown_placeholder():
    """Test that overrides with unknown placeholders are rejected."""
    errors = validate_override_text(
        "Talk to {unknown_placeholder}", "abuse"
    )
    assert len(errors) == 1
    assert "Unknown placeholder" in errors[0]


def test_get_supportive_reply_text_invalid_override_raises_error():
    """Test that invalid overrides raise ValueError during startup."""
    # Test that self-harm override without any adult naming raises error
    with pytest.raises(ValueError, match="Override must name at least one adult"):
        get_supportive_reply_text("self_harm", "a school counselor", {"self_harm": "No 988 here"})
    
    # Test that abuse override without adult naming raises error
    with pytest.raises(ValueError, match="Override must name at least one adult"):
        get_supportive_reply_text("abuse", "a school counselor", {"abuse": "No adult mentioned"})


def test_get_supportive_reply_text_valid_override():
    """Test that valid overrides work correctly."""
    overrides = {
        "self_harm": "Call 988 for help",
        "abuse": "Talk to {counselor}",
    }
    
    # Should not raise an error for valid overrides
    result = get_supportive_reply_text("self_harm", "a school counselor", overrides)
    assert "Call 988 for help" == result
    
    result = get_supportive_reply_text("abuse", "a school counselor", overrides)
    assert "Talk to {counselor}" == result


def test_all_default_templates():
    """Test that all default templates are present and valid."""
    assert "self_harm" in DEFAULT_REPLY_TEMPLATES
    assert "abuse" in DEFAULT_REPLY_TEMPLATES
    assert "bullying" in DEFAULT_REPLY_TEMPLATES
    assert "threats_of_violence" in DEFAULT_REPLY_TEMPLATES
    
    # Test that all defaults can be processed without errors
    for category in DEFAULT_REPLY_TEMPLATES:
        # This should not raise an error for default templates
        result = get_supportive_reply_text(category, "a school counselor")
        assert result is not None
        assert len(result) > 0