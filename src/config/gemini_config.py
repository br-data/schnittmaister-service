from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GeminiConfig(BaseSettings):
    """
    Configuration of the Gemini API connection, from ``GEMINI_*`` variables in the environment or ``.env``.

    Environment variables win over the file.

    :param api_key: API key of the Gemini API, from Google AI Studio (``GEMINI_API_KEY``). None until
        configured; the client refuses to start without it.
    :param request_timeout_seconds: Timeout per Gemini request. The SDK passes it to the server too, which
        gives up shortly before with a 504 DEADLINE_EXCEEDED.
    :param file_processing_timeout_seconds: How long to wait for an uploaded video to become ACTIVE
        in the Files API before giving up.
    :param file_processing_poll_seconds: Interval between two state checks of an uploaded video.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix="GEMINI_")

    api_key: str | None = None
    request_timeout_seconds: int = 900
    file_processing_timeout_seconds: int = 600
    file_processing_poll_seconds: float = 2.0


@lru_cache
def get_gemini_config() -> GeminiConfig:
    """
    Get the Gemini configuration, read once.

    :return: The configuration.
    """
    return GeminiConfig()
