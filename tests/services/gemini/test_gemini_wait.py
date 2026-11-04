from unittest.mock import MagicMock

import httpx
import pytest
from google.genai.errors import ClientError, ServerError

from src.config.backoff_config import BackoffConfig
from src.services.gemini.gemini import GeminiWait, _should_retry_on_exception


def _retry_state(attempt_number: int, exception: BaseException | None = None) -> MagicMock:
    """Create a retry state with the given attempt number and the exception of the failed attempt."""
    state = MagicMock()
    state.attempt_number = attempt_number
    state.outcome.exception.return_value = exception
    return state


def _gemini_error(code: int, retry_delay: str | None = None) -> ClientError | ServerError:
    """Build the error the SDK raises, with Google's RetryInfo detail if a delay is given."""
    error_json: dict = {"error": {"code": code, "status": "ERROR", "message": "test"}}
    if retry_delay is not None:
        error_json["error"]["details"] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}
        ]
    return (ClientError if code < 500 else ServerError)(code, error_json)


@pytest.mark.unit
class TestGeminiWait:
    def test_default_waits_are_ten_and_twenty_seconds(self) -> None:
        config = BackoffConfig()
        wait = GeminiWait(factor=config.factor, max_wait=config.max_wait, jitter=0)

        assert wait(_retry_state(1)) == 10.0
        assert wait(_retry_state(2)) == 20.0

    def test_max_wait_caps_the_exponential_wait(self) -> None:
        wait = GeminiWait(factor=10.0, max_wait=30.0, jitter=0)

        assert wait(_retry_state(3)) == 30.0

    def test_retry_delay_named_by_gemini_replaces_the_exponential_wait(self) -> None:
        wait = GeminiWait(factor=10.0, max_wait=60.0, jitter=0)

        assert wait(_retry_state(1, _gemini_error(429, "33s"))) == 33.0

    def test_error_without_retry_delay_keeps_the_exponential_wait(self) -> None:
        wait = GeminiWait(factor=10.0, max_wait=60.0, jitter=0)

        assert wait(_retry_state(1, _gemini_error(503))) == 20.0

    def test_jitter_randomizes_the_wait(self) -> None:
        wait = GeminiWait(factor=10.0, max_wait=60.0, jitter=BackoffConfig().jitter)

        waits = [wait(_retry_state(1)) for _ in range(100)]
        assert all(15.0 <= w <= 25.0 for w in waits)
        assert len(set(waits)) > 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_gemini_error(429), True),
        (_gemini_error(429, "30s"), True),
        (_gemini_error(429, "57260s"), False),
        (_gemini_error(503), True),
        (_gemini_error(504), False),
        (httpx.ReadTimeout("timed out"), False),
        (_gemini_error(404), False),
        (_gemini_error(400), False),
    ],
    ids=["429 plain", "429 short delay", "429 quota resets in hours", "503", "504", "client timeout", "404", "400"],
)
def test_should_retry_on_exception(error: BaseException, expected: bool) -> None:
    assert _should_retry_on_exception(error) is expected
