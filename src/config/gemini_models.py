from enum import StrEnum

from pydantic import BaseModel, Field


class GeminiModel(StrEnum):
    """
    Gemini models the service offers.

    The Flash models are available in the free tier of the Gemini API; the older ones are a fallback when
    the newest is overloaded. gemini-3.1-pro-preview and gemini-4-argon need billing enabled for the API key
    (checked in October 2026, see https://ai.google.dev/gemini-api/docs/pricing).
    """

    gemini_3_8_flash = "gemini-3.8-flash"
    gemini_3_7_flash = "gemini-3.7-flash"
    gemini_3_6_flash = "gemini-3.6-flash"
    gemini_3_1_pro_preview = "gemini-3.1-pro-preview"
    gemini_4_argon = "gemini-4-argon"


class MediaResolution(StrEnum):
    """
    Resolution at which Gemini tokenizes each sampled video frame.

    For video, Gemini 3 treats low and medium alike, and low is its default; high reads small text and details
    but costs about four times the tokens per frame (see
    https://ai.google.dev/gemini-api/docs/media-resolution).
    """

    LOW = "low"
    HIGH = "high"


class ModelTokenLimits(BaseModel):
    """
    Token budget and video token costs of a Gemini model.

    A video costs about duration × (fps_analysis × tokens_per_frame + audio_tokens_per_second) tokens, see
    https://ai.google.dev/gemini-api/docs/video-understanding#technical-details-video. The service refuses a
    request whose videos would not fit into the context window before calling Gemini.

    :param max_input_tokens: Context window of the model.
    :param tokens_per_frame: Tokens per sampled video frame, by media resolution.
    :param audio_tokens_per_second: Tokens per second of audio.
    """

    max_input_tokens: int = 1_048_576
    tokens_per_frame: dict[MediaResolution, int] = Field(
        default_factory=lambda: {MediaResolution.LOW: 66, MediaResolution.HIGH: 258}
    )
    audio_tokens_per_second: int = 32


# Token budget and costs of each model. This is the single source of truth for the limits.
MODEL_TOKEN_SETTINGS: dict[GeminiModel, ModelTokenLimits] = {
    GeminiModel.gemini_3_8_flash: ModelTokenLimits(),
    GeminiModel.gemini_3_7_flash: ModelTokenLimits(),
    GeminiModel.gemini_3_6_flash: ModelTokenLimits(),
    GeminiModel.gemini_3_1_pro_preview: ModelTokenLimits(),
    GeminiModel.gemini_4_argon: ModelTokenLimits(),
}


def get_token_settings_for_model(model_id: str) -> ModelTokenLimits:
    """
    Get the token budget and costs of a Gemini model.

    :param model_id: The Gemini model ID.
    :return: ModelTokenLimits of the model.
    :raises ValueError: If the model ID is not a GeminiModel.
    """
    return MODEL_TOKEN_SETTINGS[GeminiModel(model_id)]
