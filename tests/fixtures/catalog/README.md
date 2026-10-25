# Catalog test fixtures

Two MARCXML files. One is real Library of Congress data; the other is synthetic.

## `loc-books-2016-sample.xml` (real)

270 bibliographic records copied verbatim from the Library of Congress MDSConnect
open-access distribution.

| | |
| --- | --- |
| Source file | `BooksAll.2016.part01.xml.gz` (70,683,117 bytes, 250,000 records; SHA-256 `949c6d86e4af92ed1f81c7d2339c6373cc819c797cab642e2befe98fb2350e16`) |
| URL | <https://www.loc.gov/cds/downloads/MDSConnect/BooksAll.2016.part01.xml.gz>, linked from the "Books All" page <https://www.loc.gov/cds/products/MDSConnect-books_all.html> |
| Fetched | 2026-10-25, with `fetch_index_links` and `download_resumable` from `scripts/build_demo_catalog.py` (its User-Agent; loc.gov answers 403 without one) |

### How the records were selected

From that one part, using `library_assistant/catalog/marc.py` to read each record:

- **Juvenile and adolescent (250).** Records whose 008/22 is `a`, `b`, `c`, `d`, or `j`
  and which have a title (245 $a), an author (100 $a or 700 $a), a subject (650 $a), a
  summary (520 $a), and a call number (050 $a or 090 $a). For each of the five codes,
  50 records were taken at an even stride through that code's eligible records in file
  order (eligible: a 454, b 1,685, c 1,288, d 87, j 788).
- **Not juvenile (20).** Four records each for 008/22 blank, `e`, `f`, `g`, and `|`,
  with a title and an author, at an even stride the same way, so the target-audience
  filter has several kinds of record to reject.

The chosen records are written in the part's own order (by LCCN). Each `<record>` element
is the source text, byte for byte; nothing was removed or edited. The LoC files carry no
holdings, circulation, or patron fields (no 852 or 9XX), so none appear here. Note that
LoC's 001 is the LCCN as distributed, space-padded (`"   00042606 "`); the file keeps it, and
`to_record` strips it, so the Record id is `"00042606"`.

### Terms of reuse

What the Library of Congress says, as read on 2026-10-25:

- The MARC Distribution Services page
  (<https://www.loc.gov/cds/products/marcDist.php>) offers MDSConnect "at no cost to
  users" and says "These MDS record sets have been made available primarily for research
  and development usage."
- The catalog record for the dataset, "Books all : MDSConnect dataset"
  (<https://www.loc.gov/item/2020445551/>), part of the "Selected Datasets" collection,
  carries the collection's general rights statement: "Many of the datasets, particularly
  those produced by the U.S. government are in the public domain and free of any rights
  restrictions," and "You are responsible for deciding whether your use of the items in
  this collection is legal."
- The MDS subscription terms (<https://www.loc.gov/cds/mdsftp.html>, "Copyright") say:
  "Records in the MARC Distribution Services originating with the Library of Congress are
  copyrighted by the Library of Congress for use outside the United States."

[VERIFY] No LoC page found states outright that MDSConnect records are free to reuse and
redistribute. Our reading: LoC catalog records are works of the U.S. government
(17 U.S.C. § 105) and so are in the public domain in the United States, and a few hundred
records in a public test fixture is research-and-development use. LoC still claims
copyright outside the United States, and that claim is not settled for the open-access
files. Confirm with the Cataloging Distribution Service (contact link on the MDS page) before
treating this as settled.

## `synthetic-patron-fields.xml` (synthetic)

One hand-written record, not from the Library of Congress, describing no real book. It
exists only for the test that patron, circulation, and hold fields in MARC input never
reach a Record (`tests/test_catalog.py`): real LoC records carry no such fields, so they
cannot show it. Its 952 field imitates a local holdings field from a school Catalog
export.
