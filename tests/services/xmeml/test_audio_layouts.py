"""Tests for the warning about videos whose audio the sequence does not fit."""

from pathlib import Path

import pytest

from src.config.xmeml_config import AudioLayout
from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.xmeml.xmeml_builder import XmemlBuilder


def _video(filename: str, file_nr: int, **audio: object) -> VideoMetadata:
    return VideoMetadata(
        file_nr=file_nr,
        filename=filename,
        local_path=Path(filename),
        xmeml_pathurl=f"file://localhost/{filename}",
        duration_frames=3000,
        duration_seconds=120.0,
        **audio,  # type: ignore[arg-type]
    )


CAMERA = _video(
    "camera.mov", 0, audio_layout_mode=AudioLayout.MONO_PER_CHANNEL, audio_track_count=8, audio_stream_count=8
)
PHONE = _video("phone.mov", 1, audio_layout_mode=AudioLayout.STEREO_PAIR, audio_stream_count=1)
SCREEN = _video("screen.mp4", 2, audio_stream_count=0)


def _build(videos: list[VideoMetadata], clip_sources: list[str]) -> None:
    clips = [VideoClipProposal(source_filename=name, in_frame=0, out_frame=100) for name in clip_sources]
    XmemlBuilder(
        video_metadata_index=VideoMetadataIndex.from_list(videos), video_clip_proposals=clips, sequence_name="test"
    ).build_xmeml_string()


@pytest.mark.unit
def test_same_layout_gives_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    _build([PHONE], ["phone.mov", "phone.mov"])

    assert "WARNING" not in caplog.text


@pytest.mark.unit
def test_other_layout_and_no_sound_are_named(caplog: pytest.LogCaptureFixture) -> None:
    """The sequence takes the 8 tracks of the camera file; the phone video and the silent one do not fit them."""
    _build([CAMERA, PHONE, SCREEN], ["camera.mov", "phone.mov", "screen.mp4"])

    assert "'screen.mp4' without sound" in caplog.text
    assert "follow 'camera.mov' (8 mono tracks); 'phone.mov' has stereo." in caplog.text


@pytest.mark.unit
def test_single_silent_video_gets_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    _build([SCREEN], ["screen.mp4"])

    warnings = [record.message for record in caplog.records if record.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].startswith("'screen.mp4' without sound")


@pytest.mark.unit
def test_stereo_video_after_a_silent_first_video_fits_the_sequence(caplog: pytest.LogCaptureFixture) -> None:
    """Without sound, the first video leaves the sequence at two stereo tracks, which a phone video fits."""
    _build([SCREEN, PHONE], ["screen.mp4", "phone.mov"])

    assert "'screen.mp4' without sound" in caplog.text
    assert "follow" not in caplog.text


@pytest.mark.unit
def test_videos_without_clips_are_ignored(caplog: pytest.LogCaptureFixture) -> None:
    _build([PHONE, SCREEN], ["phone.mov"])

    assert "WARNING" not in caplog.text
