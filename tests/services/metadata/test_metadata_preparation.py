from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from src.config.gemini_models import MediaResolution
from src.config.task_config import TaskName
from src.config.xmeml_config import AudioLayout
from src.models.errors import UnreadableVideoError, VideoTooLongError
from src.models.request_input import XmemlCreateRequest
from src.services.media.video_probe import ProbedVideo
from src.services.metadata.metadata_preparation import build_metadata_from_request, file_url

PROBE = "src.services.metadata.metadata_preparation.probe_video"
DETECT = "src.services.metadata.metadata_preparation.detect_shot_cuts"
VO_SCRIPT = "The bridge over the river is closed for three weeks."


@pytest.fixture(autouse=True)
def shot_cuts() -> Iterator[MagicMock]:
    """Detected cuts of the probed test videos; no ffmpeg runs in these tests."""
    with patch(DETECT, return_value=[120, 480]) as mock:
        yield mock


def _probed(**overrides: Any) -> ProbedVideo:  # noqa: ANN401
    return ProbedVideo(
        **(
            {
                "duration_seconds": 120.0,
                "timebase": 25,
                "ntsc": False,
                "duration_frames": 3000,
                "width": 1280,
                "height": 720,
                "sample_aspect_ratio": 1.0,
                "audio_stream_count": 1,
                "audio_layout_mode": AudioLayout.STEREO_PAIR,
                "audio_track_count": 2,
            }
            | overrides
        )
    )


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"x")
    return path


def _request(video: Path, **overrides: Any) -> XmemlCreateRequest:  # noqa: ANN401
    return XmemlCreateRequest(
        job_id="job", video_paths=[video], task_name=TaskName.NIF, user_text_input=VO_SCRIPT, **overrides
    )


@pytest.mark.unit
@patch(PROBE, return_value=_probed())
def test_probed_values_are_set(mock_probe: MagicMock, video: Path) -> None:
    """Duration, length in frames, timebase and audio layout of the video come from the probe."""
    _, video_metadata_index = build_metadata_from_request(_request(video))

    video_metadata = video_metadata_index.get("video.mp4")
    assert video_metadata.local_path == video
    assert video_metadata.mime_type == "video/mp4"
    assert video_metadata.duration_seconds == 120.0
    assert video_metadata.duration_frames == 3000
    assert video_metadata.timebase == 25
    assert (video_metadata.width, video_metadata.height) == (1280, 720)
    assert video_metadata.audio_stream_count == 1
    assert video_metadata.audio_layout_mode == AudioLayout.STEREO_PAIR
    assert video_metadata.audio_track_count == 2
    mock_probe.assert_called_once_with(video)


@pytest.mark.unit
@patch(PROBE, return_value=_probed(audio_layout_mode=AudioLayout.MONO_PER_CHANNEL, audio_track_count=4))
def test_probed_discrete_channels_give_one_track_each(mock_probe: MagicMock, video: Path) -> None:
    """A file with discrete channels gets MONO_PER_CHANNEL with one track per channel."""
    _, video_metadata_index = build_metadata_from_request(_request(video))

    video_metadata = video_metadata_index.get("video.mp4")
    assert video_metadata.audio_layout_mode == AudioLayout.MONO_PER_CHANNEL
    assert video_metadata.audio_track_count == 4


@pytest.mark.unit
@patch(PROBE, return_value=_probed(audio_stream_count=0, audio_layout_mode=None, audio_track_count=None))
def test_video_without_audio_is_marked(mock_probe: MagicMock, video: Path) -> None:
    """A file without an audio stream is marked, so the preview gets silence; the XMEML keeps the audio defaults."""
    _, video_metadata_index = build_metadata_from_request(_request(video))

    video_metadata = video_metadata_index.get("video.mp4")
    assert video_metadata.audio_stream_count == 0
    assert video_metadata.audio_layout_mode == AudioLayout.STEREO_PAIR


@pytest.mark.unit
@patch(PROBE, side_effect=UnreadableVideoError("Could not read 'video.mp4' as a video"))
def test_unreadable_video_fails_before_the_shot_detection(
    mock_probe: MagicMock, video: Path, shot_cuts: MagicMock
) -> None:
    """A file ffprobe cannot read fails the job right away, since its duration and frame rate are unknown."""
    with pytest.raises(UnreadableVideoError):
        build_metadata_from_request(_request(video))

    shot_cuts.assert_not_called()


@pytest.mark.unit
@patch(PROBE, return_value=_probed())
def test_request_overrides_reach_the_task_config(mock_probe: MagicMock, video: Path) -> None:
    """The task overrides land in the task config, which keeps its name."""
    request = _request(
        video,
        fps_analysis=3,
        media_resolution=MediaResolution.HIGH,
        gemini_model="gemini-3.6-flash",
        render_preview=False,
    )

    job_metadata, _ = build_metadata_from_request(request)

    assert job_metadata.render_preview is False
    assert job_metadata.task_config.name == TaskName.NIF
    assert job_metadata.task_config.fps_analysis == 3
    assert job_metadata.task_config.media_resolution == MediaResolution.HIGH
    assert job_metadata.task_config.model_id_gemini == "gemini-3.6-flash"


@pytest.mark.unit
@patch(PROBE, return_value=_probed())
def test_xmeml_references_the_video_at_its_local_path(mock_probe: MagicMock, tmp_path: Path) -> None:
    """The XMEML path is the file URL of the local video, so Premiere links it on import."""
    video = tmp_path / "my video.mp4"
    video.write_bytes(b"x")

    _, video_metadata_index = build_metadata_from_request(_request(video))

    expected = "file://localhost" + str(video.resolve()).replace(" ", "%20")
    assert video_metadata_index.get("my video.mp4").xmeml_pathurl == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (PurePosixPath("/Users/me/videos/clip.mp4"), "file://localhost/Users/me/videos/clip.mp4"),
        (PurePosixPath("/Volumes/share/my videos/clip.mp4"), "file://localhost/Volumes/share/my%20videos/clip.mp4"),
        (PureWindowsPath(r"C:\Users\me\clip.mp4"), "file://localhost/C%3A/Users/me/clip.mp4"),
        (PureWindowsPath(r"\\server\share\videos\clip.mp4"), "file://server/share/videos/clip.mp4"),
    ],
    ids=["posix", "posix with space", "windows drive", "windows unc"],
)
def test_file_url_matches_premiere_exports(path: PurePath, expected: str) -> None:
    """The file URL has the form Premiere writes itself: localhost host, encoded drive colon, UNC host."""
    assert file_url(path) == expected  # type: ignore[arg-type]


@pytest.mark.unit
def test_relative_path_has_no_file_url() -> None:
    with pytest.raises(ValueError):
        file_url(PurePosixPath("videos/clip.mp4"))  # type: ignore[arg-type]


@pytest.mark.unit
@patch(PROBE, return_value=_probed())
def test_detected_cuts_are_set(mock_probe: MagicMock, video: Path, shot_cuts: MagicMock) -> None:
    """The cuts of the shot detection land in the video metadata, detected at the probed frame rate."""
    _, video_metadata_index = build_metadata_from_request(_request(video))

    assert video_metadata_index.get("video.mp4").shot_cuts == [120, 480]
    shot_cuts.assert_called_once_with(video, 25)


@pytest.mark.unit
@patch(PROBE, return_value=_probed())
def test_failed_shot_detection_leaves_no_cuts(
    mock_probe: MagicMock, video: Path, shot_cuts: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed detection is a warning; the job goes on without snapping."""
    shot_cuts.side_effect = RuntimeError("ffmpeg failed: boom")

    _, video_metadata_index = build_metadata_from_request(_request(video))

    assert video_metadata_index.get("video.mp4").shot_cuts == []
    assert "not snapped" in caplog.text


def _nif_request(video_paths: list[Path]) -> XmemlCreateRequest:
    return XmemlCreateRequest(job_id="job", video_paths=video_paths, task_name=TaskName.NIF, user_text_input=VO_SCRIPT)


def _videos(tmp_path: Path, count: int) -> list[Path]:
    paths = [tmp_path / f"video_{i}.mp4" for i in range(count)]
    for path in paths:
        path.write_bytes(b"x")
    return paths


@pytest.mark.unit
class TestTokenBudget:
    """The videos are checked against the model's token budget right after the probe, before the shot detection."""

    def test_too_long_video_fails_before_the_shot_detection(self, tmp_path: Path, shot_cuts: MagicMock) -> None:
        """120 min at the 2 fps of NiF exceed the budget of gemini-3.8-flash (about 96 min)."""
        with patch(PROBE, return_value=_probed(duration_seconds=7200.0)), pytest.raises(VideoTooLongError):
            build_metadata_from_request(_nif_request(_videos(tmp_path, 1)))

        shot_cuts.assert_not_called()

    def test_durations_of_all_videos_are_summed(self, tmp_path: Path) -> None:
        """All videos go to Gemini in one request, so two videos of 60 min count as 120 min."""
        request = _nif_request(_videos(tmp_path, 2))

        with patch(PROBE, return_value=_probed(duration_seconds=3600.0)), pytest.raises(VideoTooLongError):
            build_metadata_from_request(request)

    def test_video_within_the_budget_passes(self, tmp_path: Path, shot_cuts: MagicMock) -> None:
        """90 min at 2 fps fit."""
        request = _nif_request(_videos(tmp_path, 1))

        with patch(PROBE, return_value=_probed(duration_seconds=5400.0)):
            build_metadata_from_request(request)

        shot_cuts.assert_called_once()

    def test_high_media_resolution_shortens_the_budget(self, tmp_path: Path) -> None:
        """60 min at 1 fps fit at low resolution (about 2.7 hours), but not at high (about 54 min)."""
        request = XmemlCreateRequest(
            job_id="job",
            video_paths=_videos(tmp_path, 1),
            task_name=TaskName.SCENE_DETECTION,
            media_resolution=MediaResolution.HIGH,
        )

        with patch(PROBE, return_value=_probed(duration_seconds=3600.0)), pytest.raises(VideoTooLongError):
            build_metadata_from_request(request)
