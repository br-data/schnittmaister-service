"""Tests for the preview video: the ffmpeg calls per clip and the join."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.media.preview_render import render_preview

RUN = "src.services.media.ffmpeg.subprocess.run"
# Probed values the preview does not use
PROBED = {"duration_seconds": 60.0, "duration_frames": 1500, "xmeml_pathurl": "file://localhost/video"}


def _index() -> VideoMetadataIndex:
    return VideoMetadataIndex.from_list(
        [
            VideoMetadata(
                file_nr=0,
                filename="a.mp4",
                local_path=Path("/videos/a.mp4"),
                timebase=25,
                width=720,
                height=576,
                sample_aspect_ratio=64 / 45,
                **PROBED,
            ),
            VideoMetadata(
                file_nr=1,
                filename="b.mov",
                local_path=Path("/videos/b.mov"),
                timebase=50,
                audio_stream_count=0,
                **PROBED,
            ),
            VideoMetadata(
                file_nr=2,
                filename="c.mp4",
                local_path=Path("/videos/c.mp4"),
                timebase=25,
                audio_stream_count=4,
                **PROBED,
            ),
        ]
    )


def _clip(source: str, in_frame: int, out_frame: int) -> VideoClipProposal:
    return VideoClipProposal(source_filename=source, in_frame=in_frame, out_frame=out_frame)


def _ok() -> MagicMock:
    return MagicMock(returncode=0, stderr="")


@pytest.mark.unit
@patch(RUN)
def test_every_clip_is_cut_and_then_joined(mock_run: MagicMock, tmp_path: Path) -> None:
    """One ffmpeg call per clip with its start and duration in seconds, then one join without re-encoding."""
    captured_lists: list[str] = []

    def run(command: list[str], **kwargs: object) -> MagicMock:
        if "concat" in command:
            captured_lists.append(Path(command[command.index("-i") + 1]).read_text())
        return _ok()

    mock_run.side_effect = run
    render_preview([_clip("a.mp4", 250, 375), _clip("b.mov", 100, 400)], _index(), tmp_path / "preview.mp4")

    first, second, join = (call.args[0] for call in mock_run.call_args_list)
    assert first[first.index("-ss") + 1] == "10.000" and first[first.index("-t") + 1] == "5.000"
    assert second[second.index("-ss") + 1] == "2.000" and second[second.index("-t") + 1] == "6.000"
    # All clips in the display size (anamorphic 720x576 shown as 1024x576) and frame rate of the first video
    assert "scale=1024:576" in first[first.index("-vf") + 1] and "fps=25" in second[second.index("-vf") + 1]
    assert join[join.index("-c") + 1] == "copy" and join[-1] == str(tmp_path / "preview.mp4")
    assert captured_lists[0].count("file '") == 2 and "clip_000.mp4" in captured_lists[0].splitlines()[0]


@pytest.mark.unit
@patch(RUN, return_value=_ok())
def test_video_without_audio_gets_silence(mock_run: MagicMock, tmp_path: Path) -> None:
    render_preview([_clip("a.mp4", 0, 25), _clip("b.mov", 0, 50)], _index(), tmp_path / "preview.mp4")

    with_audio, without_audio = (call.args[0] for call in mock_run.call_args_list[:2])
    assert "0:a:0" in with_audio and "anullsrc" not in " ".join(with_audio)
    assert "1:a:0" in without_audio and any(arg.startswith("anullsrc") for arg in without_audio)


@pytest.mark.unit
@patch(RUN, return_value=MagicMock(returncode=1, stderr="Invalid data found"))
def test_ffmpeg_failure_raises_with_its_message(mock_run: MagicMock, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Invalid data found"):
        render_preview([_clip("a.mp4", 0, 25)], _index(), tmp_path / "preview.mp4")


@pytest.mark.unit
@patch(RUN, side_effect=FileNotFoundError("ffmpeg"))
def test_missing_ffmpeg_raises(mock_run: MagicMock, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not installed"):
        render_preview([_clip("a.mp4", 0, 25)], _index(), tmp_path / "preview.mp4")


@pytest.mark.unit
def test_no_clips_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        render_preview([], _index(), tmp_path / "preview.mp4")


def _levels(peaks: list[float]) -> str:
    """The log lines ffmpeg's volumedetect writes, one per audio stream."""
    return "\n".join(f"[Parsed_volumedetect_{i} @ 0x{i}] max_volume: {peak} dB" for i, peak in enumerate(peaks))


@pytest.mark.unit
@patch(RUN)
def test_sound_comes_from_the_first_stream_that_is_not_silent(mock_run: MagicMock, tmp_path: Path) -> None:
    """With several audio streams, the levels are measured once and the first audible stream is used."""
    levels = _levels([-91.0, -91.0, -4.2, -6.0])
    mock_run.side_effect = lambda command, **kwargs: MagicMock(
        returncode=0, stderr=levels if "volumedetect" in " ".join(command) else ""
    )

    render_preview([_clip("c.mp4", 0, 25), _clip("c.mp4", 50, 75)], _index(), tmp_path / "preview.mp4")

    commands = [call.args[0] for call in mock_run.call_args_list]
    assert sum("volumedetect" in " ".join(command) for command in commands) == 1
    clip_commands = [command for command in commands if "-ss" in command]
    assert all("0:a:2" in command for command in clip_commands)


@pytest.mark.unit
@patch(RUN)
def test_all_silent_streams_give_silence(mock_run: MagicMock, tmp_path: Path) -> None:
    levels = _levels([-91.0] * 4)
    mock_run.side_effect = lambda command, **kwargs: MagicMock(
        returncode=0, stderr=levels if "volumedetect" in " ".join(command) else ""
    )

    render_preview([_clip("c.mp4", 0, 25)], _index(), tmp_path / "preview.mp4")

    clip_command = next(call.args[0] for call in mock_run.call_args_list if "-ss" in call.args[0])
    assert any(arg.startswith("anullsrc") for arg in clip_command)
