"""Tests for the research prompt functionality."""

from library_assistant.catalog import Record
from library_assistant.prompt import (
    MAX_BOOKS,
    PICK_PROMPT,
    RESEARCH_PROMPT,
    SearchLineFilter,
    build_messages,
    build_pick_messages,
    parse_picks,
)


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


def test_prompt_asks_for_the_search_line_the_filter_reads():
    """The prompt once ended with a bare "SEARCH: " and no instruction, so no model wrote
    the line and the Catalog was searched with the raw question (lib-f24.59)."""
    assert "end with one last line in exactly this form" in RESEARCH_PROMPT
    example = [
        line for line in RESEARCH_PROMPT.splitlines() if line.startswith("SEARCH:")
    ]
    assert example, "the prompt shows the SEARCH: line's form"
    for line in example:
        terms = SearchLineFilter()
        terms.feed(line + "\n")
        assert 2 <= len(terms.finish()[1]) <= 6


def test_search_line_without_a_final_newline_is_held_back():
    """A model's last line has no newline; it is still the SEARCH line, not answer text."""
    f = SearchLineFilter()
    assert f.feed("Wolves eat deer.\nSEARCH: wolves; predators") == "Wolves eat deer.\n"
    assert f.finish() == ("", ["wolves", "predators"])


def test_search_line_with_a_semicolon_slip_is_held_back():
    f = SearchLineFilter()
    assert f.feed("Overview.\nSEARCH; wolves; diet\n") == "Overview.\n"
    assert f.finish() == ("", ["wolves", "diet"])


def test_a_line_that_only_mentions_search_is_answer_text():
    f = SearchLineFilter()
    text = "Search the shelves for more.\n"
    assert f.feed(text) == text
    assert f.finish() == ("", [])


def test_the_model_chooses_from_numbered_books_it_is_shown():
    record = Record(
        "1", "Wolves /", "Gibbons, Gail,", "Wolves", "x" * 500, "599.77 GIB"
    )
    system, user = build_pick_messages(
        "do wolves howl?", "They howl at night.", [record]
    )
    assert system == {"role": "system", "content": PICK_PROMPT}
    assert "do wolves howl?" in user["content"]
    assert "They howl at night." in user["content"]
    assert "1. Wolves / Gibbons, Gail," in user["content"]
    assert "x" * 200 in user["content"] and "x" * 201 not in user["content"]


def test_the_search_terms_stay_on_the_subject():
    assert "pair the main subject" in RESEARCH_PROMPT
    assert "at most one broader subject" in RESEARCH_PROMPT


def test_picks_are_read_best_first_in_the_forms_a_model_writes():
    assert parse_picks("3: Good.\n1. Fine.\n[2]) Also.", 3) == [
        (2, "Good."),
        (0, "Fine."),
        (1, "Also."),
    ]


def test_picks_run_together_on_one_line_are_still_read_apart():
    # Seen from gpt-oss:20b at low effort. A year in a reason doesn't start a pick.
    assert parse_picks("1: Set in 1939. Dust storms. 2: About farms.", 2) == [
        (0, "Set in 1939. Dust storms."),
        (1, "About farms."),
    ]


def test_a_reason_starts_with_a_capital():
    assert parse_picks("1: a book about wolves", 1) == [(0, "A book about wolves")]


def test_a_number_off_the_list_or_repeated_is_dropped():
    assert parse_picks("0: No.\n4: No.\n1: Yes.\n1: Again.", 3) == [(0, "Yes.")]


def test_only_so_many_books_are_picked():
    reply = "\n".join(f"{n}: Fits." for n in range(1, 13))
    assert len(parse_picks(reply, 12)) == MAX_BOOKS


def test_none_differs_from_a_reply_that_cant_be_read():
    assert parse_picks(" none.\n", 3) == []
    assert parse_picks("Those all look great!", 3) is None
    assert parse_picks("", 3) is None


def test_the_overview_is_told_not_to_invent():
    assert (
        "Never make up a name, a scientific name, a date, or a number"
        in RESEARCH_PROMPT
    )
    assert "without naming a winner" in RESEARCH_PROMPT
    assert "not tables" in RESEARCH_PROMPT


def test_the_overview_never_gives_methods_and_points_to_help():
    assert "never give methods, amounts, or instructions" in RESEARCH_PROMPT
    assert "school counselor" in RESEARCH_PROMPT
    assert "988" in RESEARCH_PROMPT
