import pytest

from library_assistant.shelf import author_name, where_to_find


@pytest.mark.parametrize(
    ("call_number", "where"),
    [
        ("E MCN", "Picture books, under MCN"),
        ("FIC ZUS", "Fiction, under ZUS for the author"),
        ("B LIN", "Biographies, under LIN for the person"),
        (
            "599.773 WEL",
            "Nonfiction, the 500s (science, animals, and math): find 599.773, then WEL",
        ),
        ("973 ADL", "Nonfiction, the 900s (history and geography): find 973, then ADL"),
        ("FIC", "Fiction"),
    ],
)
def test_a_school_call_number_says_where_to_walk(call_number, where):
    assert where_to_find(call_number) == where


def test_a_call_number_from_another_scheme_gets_no_directions():
    assert where_to_find("PZ10.3.L47 St") == ""
    assert where_to_find("") == ""


@pytest.mark.parametrize(
    ("heading", "name"),
    [
        ("Leaf, Munro,", "Munro Leaf"),
        ("Gibbons, Gail, 1944-", "Gail Gibbons"),
        ("Zusak, Markus.", "Markus Zusak"),
        ("White, E. B.", "E. B. White"),
        ("White, E. B. (Elwyn Brooks),", "E. B. White"),
        ("National Geographic Society", "National Geographic Society"),
        ("", ""),
    ],
)
def test_a_marc_heading_reads_as_a_name(heading, name):
    assert author_name(heading) == name
