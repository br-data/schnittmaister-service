"""Tests for the shot detection: parsing ffmpeg's log and dropping false alarms."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.services.media.shot_detection import detect_shot_cuts

RUN = "src.services.media.shot_detection.run_ffmpeg"


def _showinfo(*times: float) -> str:
    """Log lines of ffmpeg's showinfo filter for frames at the given times."""
    return "\n".join(
        f"[Parsed_showinfo_2 @ 0x1] n: {i} pts: {int(t * 12800)} pts_time:{t} duration:512" for i, t in enumerate(times)
    )


@pytest.mark.unit
@patch(RUN)
def test_cut_times_become_frames(mock_run: MagicMock) -> None:
    mock_run.return_value = _showinfo(5.0, 9.44, 47.04)

    assert detect_shot_cuts(Path("video.mp4"), 25) == [125, 236, 1176]
    video_filter = mock_run.call_args.args[0][mock_run.call_args.args[0].index("-vf") + 1]
    assert "select='gt(scene,0.3)'" in video_filter and video_filter.startswith("scale=320:-2")


@pytest.mark.unit
@patch(RUN)
def test_a_cut_right_after_another_is_dropped(mock_run: MagicMock) -> None:
    """A second detection within 0.2 s (5 frames at 25 fps) is a false alarm, e.g. a fast pan after the cut."""
    mock_run.return_value = _showinfo(163.04, 163.08, 163.24)

    assert detect_shot_cuts(Path("video.mp4"), 25) == [4076, 4081]


@pytest.mark.unit
@patch(RUN, return_value="no frame selected")
def test_video_without_cuts(mock_run: MagicMock) -> None:
    assert detect_shot_cuts(Path("video.mp4"), 25) == []


@pytest.mark.unit
@patch(RUN, side_effect=RuntimeError("ffmpeg failed: Invalid data"))
def test_ffmpeg_failure_is_raised(mock_run: MagicMock) -> None:
    with pytest.raises(RuntimeError, match="Invalid data"):
        detect_shot_cuts(Path("video.mp4"), 25)
