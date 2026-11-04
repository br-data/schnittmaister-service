import httpx
import pytest
from google.genai.errors import ClientError, ServerError
from pydantic import BaseModel, ValidationError

from src.config.gemini_models import MediaResolution
from src.models.errors import (
    GEMINI_ERROR_MESSAGE,
    RETRY_LATER_MESSAGE,
    TIMEOUT_MESSAGE,
    UnreadableVideoError,
    UserFacingError,
    VideoTooLongError,
    http_status_and_message,
    retry_delay_seconds,
)

VIDEO_TOO_LONG_ERROR = VideoTooLongError(
    video_duration_seconds=3600.0,
    fps_analysis=4,
    media_resolution=MediaResolution.LOW,
    tokens=1_065_600,
    max_tokens=943_718,
    max_duration_seconds=3188.0,
    model_id="gemini-3.8-flash",
)


class _Model(BaseModel):
    value: int


def _gemini_error(
    code: int, status: str, message: str | None = None, retry_delay: str | None = None
) -> ClientError | ServerError:
    response_json: dict = {"error": {"code": code, "status": status, "message": message or f"{status} test"}}
    if retry_delay is not None:
        response_json["error"]["details"] = [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}
        ]
    error_class = ClientError if code < 500 else ServerError
    return error_class(code, response_json)


def _validation_error() -> ValidationError:
    try:
        _Model(value="x")  # type: ignore[arg-type]
    except ValidationError as e:
        return e
    raise AssertionError("no validation error")


def _chained(cause: BaseException) -> RuntimeError:
    """Wrap ``cause`` the way an outer layer does (raise ... from cause)."""
    try:
        raise RuntimeError("job failed") from cause
    except RuntimeError as e:
        return e


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_in_message"),
    [
        # Gemini errors that are passed through with a retry hint
        (_gemini_error(429, "RESOURCE_EXHAUSTED"), 429, RETRY_LATER_MESSAGE),
        (_gemini_error(429, "RESOURCE_EXHAUSTED", message="Quota exceeded, limit: 0"), 429, "limit: 0"),
        (_gemini_error(503, "UNAVAILABLE"), 503, RETRY_LATER_MESSAGE),
        (_gemini_error(504, "DEADLINE_EXCEEDED"), 504, TIMEOUT_MESSAGE),
        # Other Gemini errors are an upstream failure with Gemini's message
        (_gemini_error(403, "PERMISSION_DENIED"), 502, GEMINI_ERROR_MESSAGE),
        (_gemini_error(400, "INVALID_ARGUMENT"), 502, "INVALID_ARGUMENT"),
        # Request timeout on the client (no answer from the server at all)
        (httpx.ReadTimeout("timed out"), 504, TIMEOUT_MESSAGE),
        # Errors caused by the request
        (VIDEO_TOO_LONG_ERROR, 422, "too long"),
        (UnreadableVideoError("Could not read 'x.mp4' as a video"), 422, "Could not read"),
        (UserFacingError("ffprobe failed", "The video could not be read"), 400, "could not be read"),
        (_validation_error(), 422, "value"),
        # Everything else
        (ValueError("Prompt file not found"), 500, "Prompt file not found"),
    ],
)
def test_http_status_and_message(error: BaseException, expected_status: int, expected_in_message: str):
    status, message = http_status_and_message(error)

    assert status == expected_status
    assert expected_in_message in message


def test_finds_gemini_error_in_exception_chain():
    assert http_status_and_message(_chained(_gemini_error(429, "RESOURCE_EXHAUSTED")))[0] == 429


def test_finds_user_facing_error_in_exception_chain():
    assert http_status_and_message(_chained(VIDEO_TOO_LONG_ERROR))[0] == 422


def test_finds_error_in_implicit_context():
    """Errors raised inside an except block (no explicit ``from``) are found via __context__."""
    try:
        try:
            raise _gemini_error(503, "UNAVAILABLE")
        except ServerError:
            # Deliberately without "from": the test is about the implicit __context__
            raise ValueError("wrapped without from")  # noqa: B904
    except ValueError as e:
        error = e
    assert http_status_and_message(error)[0] == 503


def test_cyclic_exception_chain_does_not_loop():
    first = ValueError("first")
    second = ValueError("second")
    first.__cause__ = second
    second.__cause__ = first
    assert http_status_and_message(first)[0] == 500


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_gemini_error(429, "RESOURCE_EXHAUSTED", retry_delay="57260s"), 57260.0),
        (_gemini_error(429, "RESOURCE_EXHAUSTED", retry_delay="0.5s"), 0.5),
        (_gemini_error(429, "RESOURCE_EXHAUSTED", retry_delay="soon"), None),
        (_gemini_error(429, "RESOURCE_EXHAUSTED"), None),
        (_gemini_error(503, "UNAVAILABLE"), None),
    ],
    ids=["hours", "fraction", "unparseable", "no detail", "503"],
)
def test_retry_delay_seconds(error: ClientError | ServerError, expected: float | None):
    assert retry_delay_seconds(error) == expected
