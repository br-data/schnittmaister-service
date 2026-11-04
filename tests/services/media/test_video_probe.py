"""Tests for ffprobe: parsing of frame rate, pixel aspect ratio, stream duration and audio layout, and its errors."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.xmeml_config import AudioLayout
from src.models.errors import UnreadableVideoError
from src.services.media.video_probe import (
    _is_rotated_by_quarter_turn,
    _parse_frame_rate,
    _parse_sample_aspect_ratio,
    _parse_stream_duration,
    _whole_frames,
    audio_layout_from_streams,
    probe_video,
)

RUN = "src.services.media.video_probe.subprocess.run"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("streams", "expected"),
    [
        ([], (None, None)),
        ([{"channels": 2}], (AudioLayout.STEREO_PAIR, 2)),
        ([{"channels": 1}], (AudioLayout.STEREO_PAIR, 2)),
        ([{}], (AudioLayout.STEREO_PAIR, 2)),
        ([{"channels": 6}], (AudioLayout.MONO_PER_CHANNEL, 6)),
        ([{"channels": 1}] * 8, (AudioLayout.MONO_PER_CHANNEL, 8)),
        ([{"channels": 2}] * 4, (AudioLayout.MONO_PER_CHANNEL, 8)),
        ([{"channels": 1}, {"channels": 2}], (AudioLayout.MONO_PER_CHANNEL, 3)),
    ],
    ids=["no audio", "stereo", "mono", "unknown channels", "5.1", "8 mono streams", "4 stereo streams", "mixed"],
)
def test_audio_layout_from_streams(streams: list[dict], expected: tuple) -> None:
    assert audio_layout_from_streams(streams) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({"r_frame_rate": "25/1"}, (25, False)),
        ({"r_frame_rate": "30/1"}, (30, False)),
        ({"r_frame_rate": "30000/1001"}, (30, True)),
        ({"r_frame_rate": "24000/1001"}, (24, True)),
        ({"r_frame_rate": "60000/1001"}, (60, True)),
        ({"r_frame_rate": "2997/100"}, (30, True)),
        ({"avg_frame_rate": "50/1"}, (50, False)),
        ({"r_frame_rate": "0/0", "avg_frame_rate": "25/1"}, (25, False)),
        ({"r_frame_rate": "90000/1", "avg_frame_rate": "30000/1001"}, (30, True)),
        ({}, None),
        ({"r_frame_rate": "0/0", "avg_frame_rate": "0/0"}, None),
        ({"r_frame_rate": "1000/1"}, None),
    ],
    ids=[
        "pal",
        "30",
        "ntsc 29.97",
        "ntsc 23.976",
        "ntsc 59.94",
        "29.97 as 2997/100",
        "only average",
        "division by zero, average",
        "time base, average",
        "missing",
        "both unknown",
        "implausible",
    ],
)
def test_parse_frame_rate(stream: dict, expected: tuple[int, bool] | None) -> None:
    assert _parse_frame_rate(stream) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({}, False),
        ({"side_data_list": [{"side_data_type": "Display Matrix", "rotation": 90}]}, True),
        ({"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]}, True),
        ({"side_data_list": [{"side_data_type": "Display Matrix", "rotation": 180}]}, False),
        ({"tags": {"rotate": "270"}}, True),
        ({"side_data_list": [{"side_data_type": "Other"}]}, False),
    ],
    ids=["none", "90", "-90", "180", "old rotate tag", "other side data"],
)
def test_quarter_turn_is_detected(stream: dict, expected: bool) -> None:
    assert _is_rotated_by_quarter_turn(stream) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({"sample_aspect_ratio": "64:45"}, 64 / 45),
        ({"sample_aspect_ratio": "1:1"}, 1.0),
        ({"sample_aspect_ratio": "0:1"}, 1.0),
        ({}, 1.0),
        ({"sample_aspect_ratio": "N/A"}, 1.0),
    ],
    ids=["anamorphic pal", "square", "unknown", "missing", "not a ratio"],
)
def test_parse_sample_aspect_ratio(stream: dict, expected: float) -> None:
    assert _parse_sample_aspect_ratio(stream) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("stream", "expected"),
    [
        ({"duration": "26.613333"}, 26.613333),
        ({}, 30.0),
        ({"duration": "N/A"}, 30.0),
        ({"duration": "0.000000"}, 30.0),
    ],
    ids=["stream duration", "missing", "not a number", "zero"],
)
def test_parse_stream_duration(stream: dict, expected: float) -> None:
    assert _parse_stream_duration(stream, container_duration=30.0) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("duration_seconds", "frame_rate", "expected"),
    [
        (20.0, 25, 500),
        (19.986633, 30000 / 1001, 599),
        (24.016667, 30, 720),
        (26.613333, 30, 798),
    ],
    ids=["pal", "ntsc, just below a whole frame", "variable rate, half a frame left", "variable rate"],
)
def test_whole_frames(duration_seconds: float, frame_rate: float, expected: int) -> None:
    assert _whole_frames(duration_seconds, frame_rate) == expected


@pytest.mark.unit
def test_missing_ffprobe_is_a_system_error() -> None:
    with patch(RUN, side_effect=FileNotFoundError("ffprobe")), pytest.raises(RuntimeError, match="not installed"):
        probe_video(Path("video.mp4"))


@pytest.mark.unit
def test_file_ffprobe_cannot_read_is_unreadable() -> None:
    error = subprocess.CalledProcessError(1, "ffprobe", stderr="video.mp4: Invalid data found when processing input")
    with patch(RUN, side_effect=error), pytest.raises(UnreadableVideoError, match="Invalid data"):
        probe_video(Path("video.mp4"))


@pytest.mark.unit
def test_file_without_video_stream_is_unreadable() -> None:
    output = '{"format": {"duration": "10.0"}, "streams": [{"codec_type": "audio", "channels": 2}]}'
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
    with patch(RUN, return_value=completed), pytest.raises(UnreadableVideoError, match="no readable video stream"):
        probe_video(Path("audio_only.mp4"))
