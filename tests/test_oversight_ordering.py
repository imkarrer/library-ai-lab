"""Tests for the Oversight ordering feature - when oversight is enabled, the Card's in-flight marker is held until the verdict is recorded."""

import json
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient
from library_assistant.main import app

from library_assistant.config import Settings
from library_assistant.oversight import Verdict


def _settings() -> Settings:
    return Settings(
        oversight_endpoint="http://oversight.example.com",
        oversight_model="guard-model",
        oversight_timeout_seconds=5,
    )


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


# Helper functions for testing with mocked endpoints
class MockOversightHandler:
    def __init__(self, verdict: Verdict = None):
        self.verdict = verdict or Verdict(
            category=None, severity=None, reason="no concern"
        )
        self.call_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        content = json.dumps(
            {
                "category": self.verdict.category,
                "severity": self.verdict.severity,
                "reason": self.verdict.reason,
            }
        )
        return _chat_response(content)


class MockAnswerHandler:
    def __init__(self, response: str = "This is the answer."):
        self.response = response
        self.call_count = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(200, content=self.response)


# Integration test helpers
@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def mock_oversight_settings():
    with patch.dict(
        "os.environ",
        {
            "LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT": "http://oversight.example.com",
            "LIBRARY_ASSISTANT_OVERSIGHT_MODEL": "test-model",
            "LIBRARY_ASSISTANT_OVERSIGHT_TIMEOUT_SECONDS": "30",
        },
    ):
        return Settings.from_env()


@pytest.fixture
def mock_no_oversight_settings():
    with patch.dict(
        "os.environ",
        {
            "LIBRARY_ASSISTANT_OVERSIGHT_ENDPOINT": "",
            "LIBRARY_ASSISTANT_OVERSIGHT_MODEL": "",
            "LIBRARY_ASSISTANT_OVERSIGHT_TIMEOUT_SECONDS": "30",
        },
    ):
        return Settings.from_env()
