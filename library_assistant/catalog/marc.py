"""MARC -> Record mapping and the target-audience filter.

Reads MARCXML (the LoC open-access distribution's native format), and for a
school's own export binary MARC as well (`read_export`). `target_audience` is
pure and used by both the fixture loader and `scripts/build_demo_catalog.py` so
the filter is tested without a network.
"""

from __future__ import annotations

import gzip
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import BinaryIO
from xml.etree import ElementTree as ET

from pymarc import MARCReader

from library_assistant.catalog import Record

_MARCXML_NS = "http://www.loc.gov/MARC21/slim"


def _tag(name: str) -> str:
    return f"{{{_MARCXML_NS}}}{name}"


@dataclass
class MarcRecord:
    """One <record> from a MARCXML file, kept close to the wire format."""

    leader: str = ""
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
    """Stream <record> elements from a MARCXML file, one at a time.

    A path ending in .gz is read through gzip, as the LoC distribution ships.
    """
    if path.endswith(".gz"):
        with gzip.open(path, "rb") as source:
            yield from _iter_records(source)
    else:
        with open(path, "rb") as source:
            yield from _iter_records(source)


def _iter_records(source) -> Iterator[MarcRecord]:
    for _, element in ET.iterparse(source, events=("end",)):
        if element.tag != _tag("record"):
            continue
        marc_record = MarcRecord(leader=element.findtext(_tag("leader")) or "")
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


class NotMarc(ValueError):
    """A file that is neither binary MARC nor MARCXML."""


def read_export(source: BinaryIO) -> Iterator[MarcRecord]:
    """Stream a library system's export, binary MARC or MARCXML by its first bytes.

    A binary record too damaged to read comes back empty, so it can be counted.
    """
    start = source.read(64).removeprefix(b"\xef\xbb\xbf").lstrip()
    source.seek(0)
    if start.startswith(b"<"):
        try:
            yield from _iter_records(source)
        except ET.ParseError as error:
            raise NotMarc("not well-formed XML") from error
    elif start[:5].isdigit():
        yield from _iter_binary(source)
    else:
        raise NotMarc("starts like neither binary MARC nor MARCXML")


def _iter_binary(source: BinaryIO) -> Iterator[MarcRecord]:
    # to_unicode decodes each record by its leader, UTF-8 or the older MARC-8.
    for record in MARCReader(source, to_unicode=True, utf8_handling="replace"):
        if record is None:
            yield MarcRecord()
            continue
        marc_record = MarcRecord(leader=str(record.leader))
        for marc_field in record.fields:
            if marc_field.is_control_field():
                marc_record.control_fields[marc_field.tag] = marc_field.data
            else:
                subfields = [(sub.code, sub.value) for sub in marc_field.subfields]
                marc_record.data_fields.append((marc_field.tag, subfields))
        yield marc_record


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


# What a school library's spine label starts with, from the record's Dewey field (082$a):
# the Library of Congress gives juvenile titles "[E]" (easy) or "[Fic]" (fiction) in place
# of a number, and biographies an alternative "B".
_SHELF_CLASSES = {"E": "E", "FIC": "FIC", "B": "B", "92": "B", "920": "B"}
_DEWEY_RE = re.compile(r"^\d{3}(\.\d+)?$")
_ARTICLES = ("the ", "a ", "an ")


def _cutter(name: str) -> str:
    """The three letters after the class on a spine label: SPI for "Spinelli, Jerry."."""
    letters = re.sub(r"[^A-Za-z]", "", name)
    return letters[:3].upper()


def school_call_number(marc_record: MarcRecord) -> str | None:
    """The call number a school library would shelve this book under, or None.

    A Dewey number cut at LoC's first segmentation mark, which is where the abridged
    Dewey that school libraries use ends (813/.54 is 813), or E, FIC, or B; then the first
    three letters of the author's surname (the biography's subject's, for B; the title's
    first word, with no author): "FIC SPI", "599.77 GIB", "B EIN".
    """
    shelf = None
    for value in marc_record.subfields("082", "a"):
        value = value.strip().strip("[]").strip()
        if value.upper() in _SHELF_CLASSES:
            shelf = _SHELF_CLASSES[value.upper()]
            # LoC lists the Dewey number first and "B" after it: B wins, as on a shelf.
            if shelf == "B":
                break
            continue
        number = value.split("/")[0].replace("'", "")
        if shelf is None and _DEWEY_RE.match(number):
            shelf = number
    if shelf is None:
        return None
    if shelf == "B":
        names = marc_record.subfields("600", "a") or marc_record.subfields("100", "a")
    else:
        names = marc_record.subfields("100", "a") or marc_record.subfields("110", "a")
    if names:
        cutter = _cutter(names[0].split(",")[0])
    else:
        title = " ".join(marc_record.subfields("245", "a")).lower()
        for article in _ARTICLES:
            if title.startswith(article):
                title = title[len(article) :]
                break
        cutter = _cutter(title.split(" ")[0] if title else "")
    return f"{shelf} {cutter}".strip()


def is_shelf_ready(marc_record: MarcRecord) -> bool:
    """A juvenile book with a call number a school librarian would recognize."""
    return is_juvenile(marc_record) and school_call_number(marc_record) is not None


# Leader/06, the type of record: language material, manuscript language material.
_BOOK_TYPES = frozenset("at")


def is_book(marc_record: MarcRecord) -> bool:
    """Not a DVD, a kit, or a projector: school libraries catalog those too."""
    return marc_record.leader[6:7] in _BOOK_TYPES


def holding_call_number(marc_record: MarcRecord) -> str | None:
    """The call number the school itself shelves this book under, or None.

    From the first copy's holding: 852 ($k prefix, $h class, $i item, $m suffix), or the
    952 $o that Koha uses. Only those subfields are read: a holding also carries barcodes
    and prices, which have no place in a Record.
    """
    for tag, subfields in marc_record.data_fields:
        if tag == "852":
            parts = [value for code in "khim" for c, value in subfields if c == code]
            if parts:
                return " ".join(part.strip() for part in parts)
    koha = marc_record.subfields("952", "o")
    return koha[0].strip() if koha else None


def to_school_record(marc_record: MarcRecord) -> Record:
    """`to_record`, with the school's own call number where the export has one."""
    record = to_record(marc_record)
    call_number = holding_call_number(marc_record)
    return replace(record, call_number=call_number) if call_number else record


def to_record(marc_record: MarcRecord) -> Record:
    """Map a MarcRecord to a Record, carrying only bibliographic fields.

    The call number is the school one (`school_call_number`) where the record has one,
    else the Library of Congress's own (050, or 090).
    """
    title_parts = marc_record.subfields("245", "a") + marc_record.subfields("245", "b")
    author_parts = marc_record.subfields("100", "a") or marc_record.subfields(
        "700", "a"
    )
    lc_parts = marc_record.subfields("050", "a") + marc_record.subfields(
        "050", "b"
    ) or marc_record.subfields("090", "a") + marc_record.subfields("090", "b")
    return Record(
        # LoC pads the 001 control number with spaces; a Record id is used in Citations
        # and lookups, so it carries none.
        id=marc_record.control_fields.get("001", "").strip(),
        title=" ".join(title_parts),
        author=" ".join(author_parts),
        subjects="; ".join(marc_record.subfields("650", "a")),
        summary=" ".join(marc_record.subfields("520", "a")),
        call_number=school_call_number(marc_record) or " ".join(lc_parts),
    )
