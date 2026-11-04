"""Tests for frame rates in the XMEML: sequence rate, timeline positions of mixed rates, NTSC ticks."""

from pathlib import Path
from xml.etree.ElementTree import fromstring

import pytest

from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.xmeml.shared_elements import timeline_positions
from src.services.xmeml.xmeml_builder import XmemlBuilder
from src.utils.time_utils import convert_frame_to_ppro_ticks


def _video(filename: str, file_nr: int, timebase: int, ntsc: bool = False) -> VideoMetadata:
    return VideoMetadata(
        file_nr=file_nr,
        filename=filename,
        local_path=Path(filename),
        xmeml_pathurl=f"file://localhost/{filename}",
        timebase=timebase,
        ntsc=ntsc,
        duration_frames=3000,
        duration_seconds=120.0,
        width=1280,
        height=720,
    )


def _clip(filename: str, in_frame: int, out_frame: int) -> VideoClipProposal:
    return VideoClipProposal(source_filename=filename, in_frame=in_frame, out_frame=out_frame)


@pytest.mark.unit
def test_ntsc_frame_rate_is_1000_of_1001_of_the_timebase() -> None:
    assert _video("a.mp4", 0, 30, ntsc=True).frame_rate == pytest.approx(29.97, abs=0.001)
    assert _video("a.mp4", 0, 25).frame_rate == 25


@pytest.mark.unit
def test_clips_of_another_rate_keep_their_duration_on_the_timeline() -> None:
    """The sequence runs at the first video's rate; 2 s of a 50 fps video take 60 frames of a 30 fps sequence."""
    index = VideoMetadataIndex.from_list([_video("a.mp4", 0, 30), _video("b.mp4", 1, 50)])

    positions = timeline_positions([_clip("a.mp4", 0, 90), _clip("b.mp4", 500, 600)], index)

    assert positions == [(0, 90), (90, 150)]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("timebase", "ntsc", "ticks_per_frame"),
    [(25, False, 10160640000), (30, False, 8467200000), (30, True, 8475667200), (24, True, 10594584000)],
    ids=["25", "30", "29.97", "23.976"],
)
def test_ppro_ticks_per_frame(timebase: int, ntsc: bool, ticks_per_frame: int) -> None:
    assert convert_frame_to_ppro_ticks(1, timebase, ntsc) == ticks_per_frame


@pytest.mark.unit
def test_sequence_takes_rate_and_size_of_the_first_video() -> None:
    index = VideoMetadataIndex.from_list([_video("a.mp4", 0, 30, ntsc=True), _video("b.mp4", 1, 25)])
    clips = [_clip("a.mp4", 0, 60), _clip("b.mp4", 0, 50)]

    root = fromstring(XmemlBuilder(index, clips, "test").build_xmeml_string().split("\n", 2)[2])

    sequence = root.find("sequence")
    assert sequence is not None
    assert (sequence.findtext("rate/timebase"), sequence.findtext("rate/ntsc")) == ("30", "TRUE")
    assert sequence.findtext("media/video/format/samplecharacteristics/width") == "1280"
    # 2 s of b.mp4 at 25 fps take 60 frames of the 29.97 fps sequence
    assert sequence.findtext("duration") == "120"
    second = sequence.findall("media/video/track/clipitem")[1]
    assert (second.findtext("start"), second.findtext("end")) == ("60", "120")
    assert (second.findtext("rate/timebase"), second.findtext("rate/ntsc")) == ("25", "FALSE")
