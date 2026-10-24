"""MARC -> Record mapping and the target-audience filter.

Reads MARCXML (the LoC open-access distribution's native format), not binary
MARC. `target_audience` is pure and used by both the fixture loader and
`scripts/build_demo_catalog.py` so the filter is tested without a network.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from library_assistant.catalog import Record

_MARCXML_NS = "http://www.loc.gov/MARC21/slim"


def _tag(name: str) -> str:
    return f"{{{_MARCXML_NS}}}{name}"


@dataclass
class MarcRecord:
    """One <record> from a MARCXML file, kept close to the wire format."""

    control_fields: dict[str, str] = field(default_factory=dict)
    data_fields: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)

    def subfields(self, tag: str, code: str) -> list[str]:
        return [
            value
            for field_tag, subfields in self.data_fields
            if field_tag == tag
            for subfield_code, value in subfields
            if subfield_code == code
        ]


def parse_marcxml(path: str) -> Iterator[MarcRecord]:
    """Stream <record> elements from a MARCXML file, one at a time."""
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag != _tag("record"):
            continue
        marc_record = MarcRecord()
        for control_field in element.findall(_tag("controlfield")):
            tag = control_field.get("tag", "")
            marc_record.control_fields[tag] = control_field.text or ""
        for data_field in element.findall(_tag("datafield")):
            tag = data_field.get("tag", "")
            subfields = [
                (subfield.get("code", ""), subfield.text or "")
                for subfield in data_field.findall(_tag("subfield"))
            ]
            marc_record.data_fields.append((tag, subfields))
        yield marc_record
        element.clear()


# Books 008/22 (target audience): Preschool, Primary, Pre-adolescent,
# Adolescent, Juvenile. Excludes Adult, Specialized, General, unmarked.
JUVENILE_AUDIENCE_CODES = frozenset({"a", "b", "c", "d", "j"})


def target_audience(marc_record: MarcRecord) -> str | None:
    """The 008/22 target-audience byte, or None if the 008 is too short."""
    field_008 = marc_record.control_fields.get("008", "")
    if len(field_008) <= 22:
        return None
    return field_008[22]


def is_juvenile(marc_record: MarcRecord) -> bool:
    return target_audience(marc_record) in JUVENILE_AUDIENCE_CODES


def to_record(marc_record: MarcRecord) -> Record:
    """Map a MarcRecord to a Record, carrying only bibliographic fields."""
    title_parts = marc_record.subfields("245", "a") + marc_record.subfields("245", "b")
    author_parts = marc_record.subfields("100", "a") or marc_record.subfields(
        "700", "a"
    )
    call_number_parts = marc_record.subfields("050", "a") + marc_record.subfields(
        "050", "b"
    ) or marc_record.subfields("090", "a") + marc_record.subfields("090", "b")
    return Record(
        id=marc_record.control_fields.get("001", ""),
        title=" ".join(title_parts),
        author=" ".join(author_parts),
        subjects="; ".join(marc_record.subfields("650", "a")),
        summary=" ".join(marc_record.subfields("520", "a")),
        call_number=" ".join(call_number_parts),
    )
