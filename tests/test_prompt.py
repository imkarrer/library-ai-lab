"""Tests for the research prompt functionality."""

from library_assistant.prompt import RESEARCH_PROMPT, SearchLineFilter, build_messages


def test_build_messages_system_and_user():
    """Test that build_messages produces the correct system and user messages."""
    question = "What is a library?"
    messages = build_messages(question)

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == RESEARCH_PROMPT
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == question


def test_terms_parsed():
    """Test that search terms are correctly parsed from the response."""
    filter_instance = SearchLineFilter()

    # Feed some text that includes search terms
    output1 = filter_instance.feed("This is a test.\n")
    assert output1 == "This is a test.\n"

    # Feed text with search terms
    output2 = filter_instance.feed("SEARCH: books; reading; learning\n")
    assert output2 == ""

    # Feed more text
    output3 = filter_instance.feed("More content here.\n")
    assert output3 == "More content here.\n"

    # Finish and get results
    remaining_text, search_terms = filter_instance.finish()
    assert remaining_text == ""
    assert search_terms == ["books", "reading", "learning"]


def test_no_search_line_gives_no_terms():
    """Test that when there is no search line, no terms are returned."""
    filter_instance = SearchLineFilter()

    # Feed text without search terms
    output1 = filter_instance.feed("This is a test.\n")
    assert output1 == "This is a test.\n"

    # Finish and get results
    remaining_text, search_terms = filter_instance.finish()
    assert remaining_text == ""
    assert search_terms == []


def test_filter_hides_search_line_split_across_deltas():
    """Test that a search line split across multiple deltas is handled correctly."""
    filter_instance = SearchLineFilter()

    # Feed part of a search line
    output1 = filter_instance.feed("SEARCH: books")
    assert output1 == ""

    # Feed the rest of the search line
    output2 = filter_instance.feed("; reading; learning\n")
    assert output2 == ""

    # Feed more text
    output3 = filter_instance.feed("More content here.\n")
    assert output3 == "More content here.\n"

    # Finish and get results
    remaining_text, search_terms = filter_instance.finish()
    assert remaining_text == ""
    assert search_terms == ["books", "reading", "learning"]


def test_filter_handles_partial_lines():
    """Test that partial lines at the end are buffered correctly."""
    filter_instance = SearchLineFilter()

    # Feed text that ends without a newline
    output1 = filter_instance.feed("This is a test")
    assert output1 == ""
    assert filter_instance._buffer == "This is a test"

    # Feed more text
    output2 = filter_instance.feed(" with more text\n")
    assert output2 == "This is a test with more text\n"
    assert filter_instance._buffer == ""

    # Feed a line with search terms
    output3 = filter_instance.feed("SEARCH: books\n")
    assert output3 == ""
    assert filter_instance._buffer == ""

    # Finish and get results
    remaining_text, search_terms = filter_instance.finish()
    assert remaining_text == ""
    assert search_terms == ["books"]
