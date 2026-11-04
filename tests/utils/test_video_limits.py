import pytest

from src.config.gemini_models import MediaResolution
from src.utils.video_limits import calculate_max_request_duration


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fps_analysis", "media_resolution", "expected_minutes"),
    [(1, MediaResolution.LOW, 160), (2, MediaResolution.LOW, 96), (1, MediaResolution.HIGH, 54)],
    ids=["1 fps low: about 2.7 hours", "2 fps low: about 1.6 hours", "1 fps high: under an hour"],
)
def test_max_request_duration_follows_the_documented_token_costs(
    fps_analysis: int, media_resolution: MediaResolution, expected_minutes: int
) -> None:
    """66 (low) or 258 (high) tokens per frame plus 32 per second of audio, within 90% of 1M tokens."""
    duration = calculate_max_request_duration("gemini-3.8-flash", fps_analysis, media_resolution)
    assert round(duration / 60) == expected_minutes
