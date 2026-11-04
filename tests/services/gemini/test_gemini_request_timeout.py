from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel
from tenacity import wait_none

from src.config.gemini_config import get_gemini_config
from src.services.gemini.gemini import (
    BACKOFF_CONFIG,
    GEMINI_CONFIG,
    generate_structured_output,
    get_client,
)

# The tenacity decorator adds retry_with and retry, which pyright doesn't see on the function type.
retrying_generate_structured_output = cast(Any, generate_structured_output)


@patch("src.services.gemini.gemini.genai.Client")
def test_client_has_the_api_key_and_the_request_timeout(mock_client: MagicMock, monkeypatch: pytest.MonkeyPatch):
    """Tests that the client gets the API key and the request timeout."""
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    get_gemini_config.cache_clear()

    get_client()

    assert mock_client.call_args.kwargs["api_key"] == "key"
    http_options = mock_client.call_args.kwargs["http_options"]
    assert http_options.timeout == GEMINI_CONFIG.request_timeout_seconds * 1000


def test_missing_api_key_fails_with_a_hint(monkeypatch: pytest.MonkeyPatch):
    """Tests that a missing API key fails before any request, with a hint where to get one."""
    # An empty variable in the environment shadows a key in the developer's .env file
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_gemini_config.cache_clear()

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        get_client()


def test_client_side_timeout_is_not_retried():
    """Tests that an httpx timeout (no answer from the server at all) is raised right away."""

    class _Result(BaseModel):
        value: str

    client = MagicMock()
    client.models.generate_content.side_effect = httpx.ReadTimeout("timed out")

    with pytest.raises(httpx.ReadTimeout):
        retrying_generate_structured_output.retry_with(wait=wait_none())(client, [], _Result, "gemini-test")

    assert client.models.generate_content.call_count == 1


def test_failures_are_retried_up_to_max_tries():
    """Tests that retried errors stop after max_tries attempts."""
    stop = retrying_generate_structured_output.retry.stop

    assert not stop(SimpleNamespace(attempt_number=BACKOFF_CONFIG.max_tries - 1, seconds_since_start=300))
    assert stop(SimpleNamespace(attempt_number=BACKOFF_CONFIG.max_tries, seconds_since_start=300))
