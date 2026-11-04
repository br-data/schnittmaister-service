import pytest
from google.genai.types import PartMediaResolutionLevel

from src.config.gemini_models import MediaResolution
from src.services.gemini.gemini import build_video_part


@pytest.mark.unit
@pytest.mark.parametrize(
    ("media_resolution", "expected_level"),
    [
        (MediaResolution.LOW, PartMediaResolutionLevel.MEDIA_RESOLUTION_LOW),
        (MediaResolution.HIGH, PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH),
    ],
)
def test_video_part_carries_sampling_rate_and_media_resolution(
    media_resolution: MediaResolution, expected_level: PartMediaResolutionLevel
) -> None:
    part = build_video_part("https://files/abc", None, fps_analysis=4, media_resolution=media_resolution)

    assert part.video_metadata is not None and part.video_metadata.fps == 4
    assert part.media_resolution is not None and part.media_resolution.level == expected_level
    assert part.file_data is not None and part.file_data.mime_type == "video/mp4"
