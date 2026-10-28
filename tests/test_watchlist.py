import pytest

from library_assistant.watchlist import (
    DEFAULT_PATH,
    Entry,
    load_watchlist,
    normalize,
)

SHIPPED = load_watchlist(DEFAULT_PATH)


def test_demo_entry_absent_by_default():
    """Test that demo entry is absent when demo flag is False (default)."""
    watchlist = load_watchlist(DEFAULT_PATH, demo=False)
    demo_entry_ids = [
        entry.id for entry in watchlist.entries if entry.id == "demo-flag"
    ]
    assert len(demo_entry_ids) == 0


def test_demo_entry_present_when_demo():
    """Test that demo entry is present when demo flag is True."""
    watchlist = load_watchlist(DEFAULT_PATH, demo=True)
    demo_entry = next(entry for entry in watchlist.entries if entry.id == "demo-flag")
    assert demo_entry.category == "self-harm"
    assert demo_entry.severity == "high"
    assert "library demo flag" in demo_entry.phrases


def test_demo_entry_matches_its_examples():
    """Test that demo entry matches its must_match examples."""
    watchlist = load_watchlist(DEFAULT_PATH, demo=True)
    demo_entry = next(entry for entry in watchlist.entries if entry.id == "demo-flag")

    # Test must_match examples
    for example in demo_entry.must_match:
        assert demo_entry in watchlist.match(example), (
            f"Demo entry should match: {example}"
        )

    # Test must_not_match examples
    for example in demo_entry.must_not_match:
        assert demo_entry not in watchlist.match(example), (
            f"Demo entry should not match: {example}"
        )


@pytest.mark.parametrize("entry", SHIPPED.entries, ids=lambda entry: entry.id)
def test_every_entry_matches_its_examples(entry):
    for example in entry.must_match:
        assert entry in SHIPPED.match(example), example
    for example in entry.must_not_match:
        assert entry not in SHIPPED.match(example), example


@pytest.mark.parametrize(
    "text,expected",
    [
        ("K-I-L-L", "k i l l"),
        ("Ki11 m3", "kil me"),
        ("kiiill", "kil"),
        ("café", "cafe"),
        ("naïve", "naive"),
        ("Hélène", "helene"),
        ("São Paulo", "sao paulo"),
        ("h4te @ll 0f $7uff", "hate al of stuf"),
        ("  what?!  now...  ", "what now"),
        ("", ""),
    ],
)
def test_normalize(text, expected):
    assert normalize(text) == expected


def _entry(phrases):
    return Entry("e", "self-harm", "high", tuple(phrases), ("x",), ("y",))


def test_phrase_matches_whole_words_only():
    entry = _entry(["kill me"])
    assert entry.matches("please KI11 ME now")
    assert entry.matches("kill me")
    assert not entry.matches("skill meter")
    assert not entry.matches("kill")


def _write(tmp_path, entries, version="2026-10-28.1"):
    path = tmp_path / "watchlist.toml"
    path.write_text(f'version = "{version}"\n' + entries)
    return path


GOOD = """
[[entries]]
id = "{id}"
category = "{category}"
severity = "{severity}"
phrases = ["inert phrase"]
must_match = ["an inert phrase here"]
must_not_match = ["{not_example}"]
"""


def _good(
    id="good-entry", category="abuse", severity="low", not_example="inert phrases"
):
    return GOOD.format(
        id=id, category=category, severity=severity, not_example=not_example
    )


def test_load_accepts_a_good_file(tmp_path):
    watchlist = load_watchlist(_write(tmp_path, _good()))
    assert watchlist.version == "2026-10-28.1"
    assert [entry.id for entry in watchlist.entries] == ["good-entry"]


def test_load_refuses_unknown_category(tmp_path):
    path = _write(tmp_path, _good(id="bad-category", category="spam"))
    with pytest.raises(ValueError, match="bad-category.*category"):
        load_watchlist(path)


def test_load_refuses_unknown_severity(tmp_path):
    path = _write(tmp_path, _good(id="bad-severity", severity="medium"))
    with pytest.raises(ValueError, match="bad-severity.*severity"):
        load_watchlist(path)


def test_load_refuses_failing_example(tmp_path):
    path = _write(tmp_path, _good(id="bad-not-example", not_example="inert phrase"))
    with pytest.raises(ValueError, match="bad-not-example.*must_not_match"):
        load_watchlist(path)

    path = _write(tmp_path, _good(id="bad-example").replace("an inert", "no"))
    with pytest.raises(ValueError, match="bad-example.*must_match"):
        load_watchlist(path)


def test_load_refuses_duplicate_id(tmp_path):
    path = _write(tmp_path, _good(id="twice") + _good(id="twice", category="bullying"))
    with pytest.raises(ValueError, match="twice.*duplicate"):
        load_watchlist(path)


@pytest.mark.parametrize(
    "edit,error",
    [
        (('must_not_match = ["inert phrases"]', ""), "must_not_match"),
        (('must_match = ["an inert phrase here"]', "must_match = []"), "must_match"),
        (('phrases = ["inert phrase"]', 'phrases = ["?!"]'), "empty"),
        (('severity = "low"', 'severity = "low"\nseverty = "high"'), "unknown"),
        (('id = "good-entry"', 'id = "Good Entry"'), "kebab-case"),
    ],
)
def test_load_refuses_malformed_entry(tmp_path, edit, error):
    path = _write(tmp_path, _good().replace(*edit))
    with pytest.raises(ValueError, match=error):
        load_watchlist(path)


def test_load_refuses_bad_version(tmp_path):
    with pytest.raises(ValueError, match="version"):
        load_watchlist(_write(tmp_path, _good(), version="1.0"))
