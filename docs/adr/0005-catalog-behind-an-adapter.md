# The Catalog sits behind an adapter and stays bibliographic

Schools already run a Catalog, and each runs a different one, so the assistant talks to it
only through a Catalog adapter; the shipped adapter is SQLite over a MARC export, enough for
the demo and for schools without anything better. Adapters return Records only, never
circulation, holds, fines, or patron data: books are indexed, who read them is not. Shelf
availability, if it ever arrives, is an optional adapter capability that must not carry
patron data.

## Addendum: a school's Catalog is a loaded copy

A Librarian loads the library system's MARC export on the Catalog page, and each load replaces
the whole copy. The assistant does not query the library system live: most run in a vendor's
cloud, which ADR-0006 rules out, and connecting needs an administrator, which an Install must
not. The cost is staleness, not double entry: nothing is ever entered here. Availability stays
out for now.
