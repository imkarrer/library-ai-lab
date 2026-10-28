"""Settings and the Catalog adapter factory.

An Install's settings come from the environment (decision lib-f24.25): each field is read
from `LIBRARY_ASSISTANT_<FIELD NAME UPPERCASE>`, else its default. Settings a Librarian
changes at runtime live in the database instead.

Adding a backend is a new class plus a config value: a new `elif` branch in
`build_catalog` wired to a new `catalog_backend` string.
"""

from __future__ import annotations

import dataclasses
import os
import typing
from collections.abc import Mapping
from dataclasses import dataclass

from library_assistant.catalog import Catalog
from library_assistant.catalog.sqlite_backend import SqliteCatalog

ENV_PREFIX = "LIBRARY_ASSISTANT_"

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Settings:
    catalog_backend: str = "sqlite"
    catalog_path: str = "catalog.db"
    openai_endpoint: str = "http://localhost:11434"  # Default to local Ollama
    openai_api_key: str = "no-key-needed"  # For compatibility with OpenAI client
    openai_model: str = "llama3"  # Default model
    school_timezone: str = "America/Chicago"  # IANA name
    school_day_end: str = "15:30"  # HH:MM, local to school_timezone
    oversight_endpoint: str | None = None
    oversight_model: str | None = None
    oversight_timeout_seconds: int = 20
    flags_overdue_days: int = 7  # ADR-0003 addendum: flags.overdue_days
    flags_history_days: int = 90  # ADR-0003 addendum: flags.history_days
    holds_review_days: int = 30  # ADR-0003 addendum: holds.review_days
    demo: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        environ = os.environ if environ is None else environ
        hints = typing.get_type_hints(cls)
        values = {}
        for field in dataclasses.fields(cls):
            raw = environ.get(ENV_PREFIX + field.name.upper())
            if raw is not None:
                values[field.name] = _parse(field.name, hints[field.name], raw)
        return cls(**values)

    @property
    def oversight_enabled(self) -> bool:
        return self.oversight_endpoint is not None and self.oversight_model is not None


def _parse(name: str, hint: object, raw: str) -> object:
    if hint is bool:
        if raw.strip().lower() in _TRUE:
            return True
        if raw.strip().lower() in _FALSE:
            return False
        raise ValueError(
            f"{ENV_PREFIX}{name.upper()} must be true or false, not {raw!r}"
        )
    if hint is int:
        return int(raw)
    if hint == str | None:
        return raw or None
    return raw


def build_catalog(settings: Settings) -> Catalog:
    if settings.catalog_backend == "sqlite":
        return SqliteCatalog.open(settings.catalog_path)
    raise ValueError(f"unknown catalog_backend: {settings.catalog_backend!r}")


def get_settings() -> Settings:
    return Settings.from_env()
