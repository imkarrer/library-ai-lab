from collections import Counter
from pathlib import Path

from library_assistant.catalog.marc import (
    MarcRecord,
    is_juvenile,
    parse_marcxml,
    target_audience,
)

# Real Library of Congress records; see fixtures/catalog/README.md.
LOC_SAMPLE = (
    Path(__file__).parent / "fixtures" / "catalog" / "loc-books-2016-sample.xml"
)


def _by_id(lccn: str) -> MarcRecord:
    for marc_record in parse_marcxml(str(LOC_SAMPLE)):
        if marc_record.control_fields.get("001", "").strip() == lccn:
            return marc_record
    raise AssertionError(f"no sample record {lccn!r}")


def test_target_audience_reads_008_byte_22():
    assert target_audience(_by_id("00049673")) == "j"  # The three questions
    assert target_audience(_by_id("00042817")) == "d"  # Fighting Ruben Wolfe
    assert target_audience(_by_id("00456254")) == "e"  # How to be a domestic goddess
    assert target_audience(_by_id("00000002")) == " "  # Botanical materia medica


def test_is_juvenile_keeps_juvenile_and_adolescent_only():
    assert is_juvenile(_by_id("00049673")) is True
    assert is_juvenile(_by_id("00042817")) is True
    assert is_juvenile(_by_id("00456254")) is False
    assert is_juvenile(_by_id("00000002")) is False


def test_sample_audience_codes_and_filter_counts():
    # The sample was drawn as 50 records per juvenile code and 4 per other code
    # (fixtures/catalog/README.md). If the filter's code set changes, this shows it.
    marc_records = list(parse_marcxml(str(LOC_SAMPLE)))
    assert Counter(target_audience(m) for m in marc_records) == {
        "a": 50,
        "b": 50,
        "c": 50,
        "d": 50,
        "j": 50,
        " ": 4,
        "e": 4,
        "f": 4,
        "g": 4,
        "|": 4,
    }
    juvenile = [m for m in marc_records if is_juvenile(m)]
    assert len(juvenile) == 250
    assert len(marc_records) - len(juvenile) == 20


def test_target_audience_missing_008_is_none():
    assert target_audience(MarcRecord()) is None
