import logging
import random
from typing import Type, TypeVar, cast

from google import genai
from google.genai.errors import ClientError, ServerError
from google.genai.types import (
    ContentListUnionDict,
    FileData,
    GenerateContentConfig,
    HttpOptions,
    Part,
    PartMediaResolution,
    PartMediaResolutionLevel,
    VideoMetadata,
)
from pydantic import BaseModel
from tenacity import RetryCallState, retry, retry_if_exception, stop_after_attempt
from tenacity.wait import wait_base

from src.config.backoff_config import BackoffConfig
from src.config.gemini_config import GeminiConfig, get_gemini_config
from src.config.gemini_models import MediaResolution
from src.config.video_format_config import DEFAULT_VIDEO_MIME_TYPE
from src.models.errors import retry_delay_seconds
from src.models.token_usage import add_gemini_usage

GEMINI_CONFIG: GeminiConfig = get_gemini_config()
BACKOFF_CONFIG: BackoffConfig = BackoffConfig()

# Gemini's level for each media resolution the service offers
_MEDIA_RESOLUTION_LEVELS = {
    MediaResolution.LOW: PartMediaResolutionLevel.MEDIA_RESOLUTION_LOW,
    MediaResolution.HIGH: PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
}

T = TypeVar("T", bound=BaseModel)


# The retry policy of generate_structured_output comes first: its @retry decorator uses
# GeminiWait, _should_retry_on_exception and _log_retry at import time
class GeminiWait(wait_base):
    """
    Exponential backoff with jitter that honours the retry delay a Gemini error names.

    A 429 may carry a RetryInfo detail with the delay Gemini suggests; then that delay is waited
    instead of the exponential one. Jitter staggers concurrent retries, so they don't hit the API at
    the same moment.
    """

    def __init__(self, factor: float, max_wait: float, jitter: float) -> None:
        """
        Initialize the wait strategy.

        :param factor: Multiplier of the exponential wait (wait = 2^attempt * factor).
        :param max_wait: Maximum exponential wait in seconds.
        :param jitter: Random variation of the wait as a fraction (0.25 = ±25%); 0 for deterministic waits.
        """
        self.factor = factor
        self.max_wait = max_wait
        self.jitter = jitter

    def __call__(self, retry_state: RetryCallState) -> float:
        """
        Calculate the wait time before the next attempt.

        :param retry_state: The current state of the retry.
        :return: Wait time in seconds (with jitter applied).
        """
        wait = min(2**retry_state.attempt_number * self.factor, self.max_wait)
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exception, (ClientError, ServerError)):
            suggested = retry_delay_seconds(exception)
            if suggested is not None:
                wait = suggested
        if self.jitter > 0:
            wait = wait * random.uniform(1 - self.jitter, 1 + self.jitter)
        return wait


def _should_retry_on_exception(exception: BaseException) -> bool:
    """
    Determine if an exception should trigger a retry.

    Only short-lived errors are retried:
    429: Rate limit, unless Gemini names a retry delay above BackoffConfig.max_retry_delay_seconds
    (e.g. a daily quota that resets in hours, or quota 0 for a model outside the tier).
    502/503: Transient gateway errors and overload ("high demand").
    Timeouts (504 DEADLINE_EXCEEDED, httpx.TimeoutException) are not retried: a request that ran into
    the request timeout would most likely run into it again, and the user would wait twice as long.

    :param exception: The exception that occurred during the API call.
    :return: True if the exception should be retried, False otherwise.
    """
    if isinstance(exception, ClientError) and exception.code == 429:
        delay = retry_delay_seconds(exception)
        return delay is None or delay <= BACKOFF_CONFIG.max_retry_delay_seconds
    if isinstance(exception, ServerError):
        return exception.code in (502, 503)
    return False


def _log_retry(retry_state: RetryCallState) -> None:
    """
    Log a warning message before each retry attempt.

    :param retry_state: The state of the retry attempt.
    """
    if retry_state.outcome:  # Check if outcome exists (it should if an exception occurred)
        exc = retry_state.outcome.exception()
        exc_type = type(exc).__name__ if exc else "Unknown Exception"
    else:
        exc_type = "Unknown State"

    wait_time = retry_state.next_action.sleep if retry_state.next_action else 0

    logging.warning(
        f"API call failed with {exc_type}, backing off for {wait_time:.1f}s "
        f"(retry {retry_state.attempt_number}/{BACKOFF_CONFIG.max_tries - 1})"
    )


def build_video_part(
    file_uri: str, mime_type: str | None, fps_analysis: int, media_resolution: MediaResolution
) -> Part:
    """
    Build the Gemini Part of a video in the Files API.

    :param file_uri: URI of the video in the Files API.
    :param mime_type: MIME type of the video; DEFAULT_VIDEO_MIME_TYPE if unknown.
    :param fps_analysis: Gemini analysis sampling rate (frames analyzed per second of video).
        This is NOT the video's framerate - it's how many frames Gemini samples per second.
    :param media_resolution: Resolution at which Gemini tokenizes each sampled frame; Gemini 3 sets it per part.
    :return: Part referencing the video, with the sampling rate in its VideoMetadata and the media resolution.
    """
    return Part(
        file_data=FileData(file_uri=file_uri, mime_type=mime_type or DEFAULT_VIDEO_MIME_TYPE),
        video_metadata=VideoMetadata(fps=fps_analysis),
        media_resolution=PartMediaResolution(level=_MEDIA_RESOLUTION_LEVELS[media_resolution]),
    )


def get_client() -> genai.Client:
    """
    Initialize a Google GenAI client for the Gemini Developer API with the API key and the configured request timeout.

    The SDK sends the timeout to the server as well (header X-Server-Timeout), and the server gives up
    shortly before it with 504 DEADLINE_EXCEEDED, so a timed-out request also stops running at Google.

    :raises ValueError: If GEMINI_API_KEY is not set.
    :return: An initialized Google GenAI client instance.
    """
    api_key = get_gemini_config().api_key
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Create a key in Google AI Studio and put it into .env (see README)."
        )
    http_options = HttpOptions(timeout=GEMINI_CONFIG.request_timeout_seconds * 1000)  # milliseconds
    return genai.Client(api_key=api_key, http_options=http_options)


@retry(
    wait=GeminiWait(factor=BACKOFF_CONFIG.factor, max_wait=BACKOFF_CONFIG.max_wait, jitter=BACKOFF_CONFIG.jitter),
    stop=stop_after_attempt(BACKOFF_CONFIG.max_tries),
    retry=retry_if_exception(_should_retry_on_exception),
    before_sleep=_log_retry,
    reraise=True,
)
def generate_structured_output(
    client: genai.Client,
    contents: ContentListUnionDict,
    response_schema: Type[T],
    model: str,
) -> T:
    """
    Generate structured output from the given content using the Gemini API.

    This function sends the content (e.g. videos and a prompt, or text only) to Gemini, expecting a
    structured JSON response conforming to the provided Pydantic schema.

    :param client: An initialized Google GenAI client.
    :param contents: A list of Parts or a dict defining the content to analyze (e.g., videos and a prompt).
    :param response_schema: A Pydantic BaseModel class that defines the structure of the expected response.
    :param model: Gemini model ID.
    :return: The response parsed into an instance of response_schema.
    :raises ValueError: If Gemini returns no parseable response.
    :raises ClientError | ServerError | httpx.TimeoutException: If the call still fails after the retries,
        or right away for errors that are not retried.
    """
    config = GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=response_schema,
        max_output_tokens=65536,  # Set to maximum (64K tokens)
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )
    except Exception as e:
        # This will log the details of the exception before tenacity catches it
        logging.error(
            f"Exception occurred during Gemini API call.\n"
            f"Exception Type (full): {type(e).__module__}.{type(e).__name__}\n"
            f"Exception Message: {e}\n"
            f"Exception Code (if applicable): {getattr(e, 'code', 'N/A')}"
        )

        raise  # Re-raise the exception so retry mechanism can handle it

    # Log token usage metadata from Gemini response and record it on the job's collector
    _log_usage_metadata(getattr(response, "usage_metadata", None), model)
    add_gemini_usage(getattr(response, "usage_metadata", None))

    parsed_response = response.parsed
    if not parsed_response:
        raise ValueError("No valid response received from Gemini API.")
    return cast(T, parsed_response)


def _log_usage_metadata(usage_metadata, model: str) -> None:  # noqa: ANN001, C901
    """
    Log detailed token usage metadata from Gemini API response.

    :param usage_metadata: UsageMetadata object from Gemini response
    :param model: The model name used for the request
    """
    if not usage_metadata:
        logging.warning("No usage_metadata found in Gemini API response")
        return

    log_lines = [f"Gemini API Token Usage for model '{model}':"]

    log_lines.append(f"  INPUT (prompt_token_count): {getattr(usage_metadata, 'prompt_token_count', 'N/A')}")
    if hasattr(usage_metadata, "prompt_tokens_details") and usage_metadata.prompt_tokens_details:
        for detail in usage_metadata.prompt_tokens_details:
            log_lines.append(f"    - {detail.modality}: {detail.token_count} tokens")

    log_lines.append(f"  OUTPUT (candidates_token_count): {getattr(usage_metadata, 'candidates_token_count', 'N/A')}")
    if hasattr(usage_metadata, "candidates_tokens_details") and usage_metadata.candidates_tokens_details:
        for detail in usage_metadata.candidates_tokens_details:
            log_lines.append(f"    - {detail.modality}: {detail.token_count} tokens")

    if hasattr(usage_metadata, "cached_content_token_count") and usage_metadata.cached_content_token_count:
        log_lines.append(f"  CACHED (cached_content_token_count): {usage_metadata.cached_content_token_count}")
        if hasattr(usage_metadata, "cache_tokens_details") and usage_metadata.cache_tokens_details:
            for detail in usage_metadata.cache_tokens_details:
                log_lines.append(f"    - {detail.modality}: {detail.token_count} tokens")

    # Thinking tokens
    if hasattr(usage_metadata, "thoughts_token_count") and usage_metadata.thoughts_token_count:
        log_lines.append(f"  THINKING (thoughts_token_count): {usage_metadata.thoughts_token_count}")

    if hasattr(usage_metadata, "tool_use_prompt_token_count") and usage_metadata.tool_use_prompt_token_count:
        log_lines.append(f"  TOOL USE (tool_use_prompt_token_count): {usage_metadata.tool_use_prompt_token_count}")

    log_lines.append(f"  TOTAL (total_token_count): {getattr(usage_metadata, 'total_token_count', 'N/A')}")

    logging.info("\n".join(log_lines))
