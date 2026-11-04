import httpx
from google.genai.errors import ClientError, ServerError
from pydantic import ValidationError

from src.config.gemini_models import MediaResolution

RETRY_LATER_MESSAGE = "Gemini is currently overloaded or the rate limit is reached, try again in a few minutes."
TIMEOUT_MESSAGE = (
    "Gemini did not finish within the request timeout. Try a shorter video, a lower fps_analysis, "
    "the low media_resolution or another model."
)
GEMINI_ERROR_MESSAGE = "Gemini rejected the request."
DEFAULT_USER_ERROR_MESSAGE = "An unexpected error occurred, see the service log."

# Type of the google.rpc.Status detail that names the delay before a retry
RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"


class UserFacingError(Exception):
    """
    A job failure caused by the request rather than by the system.

    ``str(error)`` is the technical description for the logs, ``user_message`` the text and
    ``status_code`` the HTTP status of the response.

    :ivar user_message: Message suitable for the end user.
    :ivar status_code: HTTP status code of the response.
    """

    status_code: int = 400

    def __init__(self, message: str, user_message: str | None = None) -> None:
        """
        Create the error.

        :param message: Technical description for the logs.
        :param user_message: Message suitable for the end user; defaults to the technical description.
        """
        super().__init__(message)
        self.user_message = user_message or message


class UnreadableVideoError(UserFacingError):
    """A video file that ffprobe cannot read, or that has no video stream or duration."""

    status_code = 422


class VideoTooLongError(UserFacingError):
    """The videos of the request need more tokens than the model's context window allows."""

    status_code = 422

    def __init__(
        self,
        video_duration_seconds: float,
        fps_analysis: int,
        media_resolution: MediaResolution,
        tokens: int,
        max_tokens: int,
        max_duration_seconds: float,
        model_id: str,
    ) -> None:
        """
        Create the error from the numbers of the token budget check.

        :param video_duration_seconds: Total duration of the videos of the request.
        :param fps_analysis: Gemini analysis sampling rate.
        :param media_resolution: Resolution at which Gemini tokenizes each frame.
        :param tokens: Tokens the videos would cost.
        :param max_tokens: Token budget of the model for the videos.
        :param max_duration_seconds: Longest duration that fits at this sampling rate.
        :param model_id: Gemini model ID.
        """
        super().__init__(
            message=(
                f"Video too long for a single Gemini request: {video_duration_seconds:.0f}s × {fps_analysis} fps "
                f"at {media_resolution} resolution = {tokens} tokens > {max_tokens} ({model_id})"
            ),
            user_message=(
                f"The video is too long for one Gemini request: {video_duration_seconds / 60:.1f} minutes at "
                f"{fps_analysis} fps and {media_resolution} resolution, but {model_id} takes at most about "
                f"{max_duration_seconds / 60:.0f} minutes with these settings. Shorten the video, lower "
                f"fps_analysis or use the low media_resolution."
            ),
        )


def http_status_and_message(error: BaseException) -> tuple[int, str]:
    """
    Map a job failure to the HTTP status code and the message of the response.

    Walks the exception chain (``__cause__`` / ``__context__``) and decides on the first error it knows:
    a ``UserFacingError`` gives its own status and message, a request validation error 422. Gemini errors keep
    their status where it tells the user what to do: 429 (rate limit) with Gemini's message, which names the
    exhausted quota, 503 (overload) with a retry hint, 504 (timeout, also on the client side) with the timeout
    hint. Any other Gemini error is a 502 with Gemini's message, everything else a 500.

    :param error: The exception that caused the job to fail.
    :return: HTTP status code and message of the response.
    """
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, UserFacingError):
            return current.status_code, current.user_message
        if isinstance(current, ValidationError):
            return 422, str(current)
        if isinstance(current, httpx.TimeoutException):
            return 504, TIMEOUT_MESSAGE
        if isinstance(current, (ClientError, ServerError)):
            if current.code == 429:
                # Gemini's own text names the exhausted quota and when it resets
                return 429, f"{RETRY_LATER_MESSAGE} Gemini: {current.message}"
            if current.code == 503:
                return 503, RETRY_LATER_MESSAGE
            if current.code == 504:
                return 504, TIMEOUT_MESSAGE
            return 502, f"{GEMINI_ERROR_MESSAGE} {type(current).__name__}: {current}"
        current = current.__cause__ or current.__context__
    return 500, f"{DEFAULT_USER_ERROR_MESSAGE} {type(error).__name__}: {error}"


def retry_delay_seconds(error: ClientError | ServerError) -> float | None:
    """
    Read the delay Gemini suggests before retrying, from the RetryInfo detail of the error.

    Google APIs report errors in the google.rpc.Status format: a ``details`` list whose entries carry a
    ``@type``. A rate limit error adds ``google.rpc.RetryInfo`` with ``retryDelay`` as a proto3 JSON
    duration, seconds with an optional fraction and the suffix "s" (e.g. "57260s"). The SDK hands the
    response JSON over unparsed in ``error.details``.

    :param error: The error as raised by the SDK.
    :return: The delay in seconds, or None if the error names none.
    """
    error_json = error.details.get("error", {}) if isinstance(error.details, dict) else {}
    for detail in error_json.get("details", []) or []:
        if isinstance(detail, dict) and detail.get("@type") == RETRY_INFO_TYPE:
            try:
                return float(str(detail.get("retryDelay", "")).removesuffix("s"))
            except ValueError:
                return None
    return None
