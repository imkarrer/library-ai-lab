"""How long the Answer lane waits for the model before telling a Student it failed."""

import asyncio

from library_assistant.config import Settings
from library_assistant.dependencies import get_http_client


def _client_timeout(settings: Settings):
    async def first_client():
        clients = get_http_client(settings)
        client = await anext(clients)
        await clients.aclose()
        return client.timeout

    return asyncio.run(first_client())


def test_a_slow_model_gets_a_minute_not_httpx_s_five_seconds():
    # A model paging back in after a quiet spell took 28 s to read its prompt: with
    # httpx's 5 s default the Student got an error instead of a late answer.
    timeout = _client_timeout(Settings())
    assert timeout.read == 60
    assert timeout.write == 60
    assert timeout.pool == 60


def test_a_model_server_that_is_down_still_fails_fast():
    assert _client_timeout(Settings()).connect == 5


def test_the_wait_is_a_setting():
    settings = Settings.from_env({"LIBRARY_ASSISTANT_OPENAI_TIMEOUT_SECONDS": "90"})
    assert settings.openai_timeout_seconds == 90
    assert _client_timeout(settings).read == 90
