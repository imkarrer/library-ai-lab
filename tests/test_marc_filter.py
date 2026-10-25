from pathlib import Path

from library_assistant.catalog.marc import is_juvenile, parse_marcxml, target_audience

FIXTURE = Path(__file__).parent / "fixtures" / "catalog" / "fixture.xml"


def _by_id(marc_id: str):
    for marc_record in parse_marcxml(str(FIXTURE)):
        if marc_record.control_fields.get("001") == marc_id:
            return marc_record
    raise AssertionError(f"no fixture record {marc_id!r}")


def test_target_audience_reads_008_byte_22():
    assert target_audience(_by_id("loc0001")) == "j"
    assert target_audience(_by_id("loc0002")) == "d"
    assert target_audience(_by_id("loc0003")) == "e"


def test_is_juvenile_keeps_juvenile_and_adolescent_only():
    assert is_juvenile(_by_id("loc0001")) is True
    assert is_juvenile(_by_id("loc0002")) is True
    assert is_juvenile(_by_id("loc0003")) is False


def test_target_audience_missing_008_is_none():
    from library_assistant.catalog.marc import MarcRecord

    assert target_audience(MarcRecord()) is None
