"""The token budget of a Gemini request: how long a video may be at a given sampling rate and resolution."""

import math

from src.config.gemini_models import MediaResolution, get_token_settings_for_model
from src.models.errors import VideoTooLongError

# Share of the context window the videos may use; the rest is for the prompt and the answer
TOKEN_BUDGET_SAFETY_MARGIN = 0.9


def calculate_max_request_duration(model_id: str, fps_analysis: int, media_resolution: MediaResolution) -> float:
    """
    Calculate the longest video duration that fits into one request of the model.

    :param model_id: Gemini model ID (e.g., "gemini-3.8-flash")
    :param fps_analysis: Gemini analysis sampling rate (frames analyzed per second of video)
    :param media_resolution: Resolution at which Gemini tokenizes each frame
    :return: Maximum video duration in seconds
    :raises ValueError: If the model is unknown
    """
    max_tokens = get_token_settings_for_model(model_id).max_input_tokens * TOKEN_BUDGET_SAFETY_MARGIN
    return max_tokens / _tokens_per_second(model_id, fps_analysis, media_resolution)


def ensure_video_fits_single_request(
    video_duration_seconds: float, model_id: str, fps_analysis: int, media_resolution: MediaResolution
) -> None:
    """
    Check that the videos of a request fit into the model's context window.

    :param video_duration_seconds: Total duration of all videos sent in the request
    :param model_id: Gemini model ID (e.g., "gemini-3.8-flash")
    :param fps_analysis: Gemini analysis sampling rate (frames analyzed per second of video)
    :param media_resolution: Resolution at which Gemini tokenizes each frame
    :raises VideoTooLongError: If the videos need more tokens than the budget allows
    :raises ValueError: If the model is unknown
    """
    tokens = math.ceil(video_duration_seconds * _tokens_per_second(model_id, fps_analysis, media_resolution))
    max_tokens = int(get_token_settings_for_model(model_id).max_input_tokens * TOKEN_BUDGET_SAFETY_MARGIN)
    if tokens > max_tokens:
        raise VideoTooLongError(
            video_duration_seconds=video_duration_seconds,
            fps_analysis=fps_analysis,
            media_resolution=media_resolution,
            tokens=tokens,
            max_tokens=max_tokens,
            max_duration_seconds=calculate_max_request_duration(model_id, fps_analysis, media_resolution),
            model_id=model_id,
        )


def _tokens_per_second(model_id: str, fps_analysis: int, media_resolution: MediaResolution) -> int:
    """
    Calculate the tokens one second of video costs: the sampled frames plus the audio.

    :param model_id: Gemini model ID
    :param fps_analysis: Gemini analysis sampling rate
    :param media_resolution: Resolution at which Gemini tokenizes each frame
    :return: Tokens per second of video
    :raises ValueError: If the model is unknown
    """
    limits = get_token_settings_for_model(model_id)
    return fps_analysis * limits.tokens_per_frame[media_resolution] + limits.audio_tokens_per_second
