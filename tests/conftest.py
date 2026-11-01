"""What every test starts without: limits kept in process memory."""

import pytest

from library_assistant import staff
from library_assistant.routers import session


@pytest.fixture(autouse=True)
def _no_limits_carried_over():
    session._recent_asks.clear()
    staff._failed_logins.clear()
    yield
