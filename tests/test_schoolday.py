from datetime import UTC, datetime, timedelta, timezone

import pytest

from library_assistant.config import Settings
from library_assistant.schoolday import last_day_end_before, school_day_end_for

SETTINGS = Settings(school_timezone="America/Chicago", school_day_end="15:30")


def test_end_on_same_local_date():
    # 10:00 in Chicago (CDT, UTC-5) on 2026-10-26 ends at 15:30 local, 20:30 UTC.
    moment = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)
    assert school_day_end_for(moment, SETTINGS) == datetime(
        2026, 10, 26, 20, 30, tzinfo=UTC
    )


def test_local_date_not_utc_date():
    # 01:00 UTC on 10-27 is still the evening of 10-26 in Chicago.
    moment = datetime(2026, 10, 27, 1, 0, tzinfo=UTC)
    assert school_day_end_for(moment, SETTINGS) == datetime(
        2026, 10, 26, 20, 30, tzinfo=UTC
    )


def test_end_across_dst_change():
    # DST ends in Chicago on 2026-11-01: the wall-clock end stays 15:30, UTC moves an hour.
    before = datetime(2026, 10, 31, 17, 0, tzinfo=UTC)
    after = datetime(2026, 11, 1, 17, 0, tzinfo=UTC)
    assert school_day_end_for(before, SETTINGS) == datetime(
        2026, 10, 31, 20, 30, tzinfo=UTC
    )
    assert school_day_end_for(after, SETTINGS) == datetime(
        2026, 11, 1, 21, 30, tzinfo=UTC
    )


def test_last_day_end_before_morning_is_yesterday():
    morning = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)  # 08:00 in Chicago
    assert last_day_end_before(morning, SETTINGS) == datetime(
        2026, 10, 26, 20, 30, tzinfo=UTC
    )


def test_last_day_end_before_evening_is_today():
    evening = datetime(2026, 10, 26, 23, 0, tzinfo=UTC)  # 18:00 in Chicago
    assert last_day_end_before(evening, SETTINGS) == datetime(
        2026, 10, 26, 20, 30, tzinfo=UTC
    )


def test_last_day_end_before_at_the_end_is_that_end():
    end = datetime(2026, 10, 26, 20, 30, tzinfo=UTC)
    assert last_day_end_before(end, SETTINGS) == end
    assert last_day_end_before(end - timedelta(seconds=1), SETTINGS) == end - timedelta(
        days=1
    )


def test_other_offsets_in_and_out():
    moment = datetime(2026, 10, 26, 10, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert school_day_end_for(moment, SETTINGS).tzinfo == UTC


def test_naive_moment_is_refused():
    with pytest.raises(ValueError):
        school_day_end_for(datetime(2026, 10, 26, 15, 0), SETTINGS)


def test_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("LIBRARY_ASSISTANT_SCHOOL_DAY_END", "14:45")
    monkeypatch.setenv("LIBRARY_ASSISTANT_SCHOOL_TIMEZONE", "America/New_York")
    monkeypatch.setenv("LIBRARY_ASSISTANT_OPENAI_MODEL", "demo-model")
    settings = Settings.from_env()
    assert settings.school_day_end == "14:45"
    assert settings.school_timezone == "America/New_York"
    assert settings.openai_model == "demo-model"
    assert settings.catalog_backend == "sqlite"  # untouched fields keep their defaults


def test_from_env_defaults_without_env():
    assert Settings.from_env({}) == Settings()


def test_from_env_parses_bool_int_and_optional():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Probe(Settings):
        flag: bool = False
        count: int = 1
        endpoint: str | None = None

    probe = Probe.from_env(
        {
            "LIBRARY_ASSISTANT_FLAG": "yes",
            "LIBRARY_ASSISTANT_COUNT": "7",
            "LIBRARY_ASSISTANT_ENDPOINT": "",
        }
    )
    assert (probe.flag, probe.count, probe.endpoint) == (True, 7, None)
    with pytest.raises(ValueError):
        Probe.from_env({"LIBRARY_ASSISTANT_FLAG": "maybe"})
