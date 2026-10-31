"""The lessons the pipeline commits for an Install to serve (scripts/publish_materials.py)."""

import json

from scripts.publish_materials import publish


def _lesson(tmp_path):
    source = tmp_path / "src"
    build = tmp_path / "build"
    source.mkdir()
    build.mkdir()
    deck = source / "lesson-1-deck.md"
    handout = source / "lesson-1-handout.md"
    deck.write_text("slides")
    handout.write_text("sheet")
    for name in ("lesson-1-deck.pdf", "lesson-1-deck.html", "lesson-1-handout.pdf"):
        (build / name).write_text("built")
    style = source / "deck.css"
    style.write_text("colors")
    return [deck, handout], build, tmp_path / "materials", (style,)


def test_a_deck_gets_its_notes_version_and_a_handout_only_its_pdf(tmp_path):
    docs, build, dest, styling = _lesson(tmp_path)
    assert sorted(publish(docs, build, dest, styling)) == [
        "lesson-1-deck.html",
        "lesson-1-deck.pdf",
        "lesson-1-handout.pdf",
    ]
    assert not (dest / "lesson-1-handout.html").exists()


def test_an_unchanged_lesson_is_left_alone(tmp_path):
    """A PDF differs on every build, so copying it again would commit noise."""
    docs, build, dest, styling = _lesson(tmp_path)
    publish(docs, build, dest, styling)
    (build / "lesson-1-deck.pdf").write_text("rebuilt, same source")
    assert publish(docs, build, dest, styling) == []
    assert (dest / "lesson-1-deck.pdf").read_text() == "built"


def test_only_the_edited_lesson_is_copied_again(tmp_path):
    docs, build, dest, styling = _lesson(tmp_path)
    publish(docs, build, dest, styling)
    docs[1].write_text("a better sheet")
    assert publish(docs, build, dest, styling) == ["lesson-1-handout.pdf"]


def test_a_styling_change_copies_every_lesson(tmp_path):
    docs, build, dest, styling = _lesson(tmp_path)
    publish(docs, build, dest, styling)
    styling[0].write_text("new colors")
    assert len(publish(docs, build, dest, styling)) == 3


def test_a_missing_copy_is_replaced(tmp_path):
    docs, build, dest, styling = _lesson(tmp_path)
    publish(docs, build, dest, styling)
    (dest / "lesson-1-deck.html").unlink()
    assert "lesson-1-deck.html" in publish(docs, build, dest, styling)
    assert set(json.loads((dest / "sources.json").read_text())) == {
        "lesson-1-deck",
        "lesson-1-handout",
    }
