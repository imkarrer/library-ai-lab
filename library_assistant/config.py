"""Settings and the Catalog adapter factory.

Adding a backend is a new class plus a config value: a new `elif` branch in
`build_catalog` wired to a new `catalog_backend` string.
"""

from __future__ import annotations

from dataclasses import dataclass

from library_assistant.catalog import Catalog
from library_assistant.catalog.sqlite_backend import SqliteCatalog


@dataclass(frozen=True)
class Settings:
    catalog_backend: str = "sqlite"
    catalog_path: str = "catalog.db"


def build_catalog(settings: Settings) -> Catalog:
    if settings.catalog_backend == "sqlite":
        return SqliteCatalog.open(settings.catalog_path)
    raise ValueError(f"unknown catalog_backend: {settings.catalog_backend!r}")
