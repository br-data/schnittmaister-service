from pathlib import Path

import pytest

from src.models.gemini_output import GeminiVideoClipProposal
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.gemini.gemini_proposal_processing import (
    _sanitize_proposed_timestamp,
    _snap_to_cuts,
    transform_gemini_proposals,
)

# -----------------------------------------
# --- Sanitize Proposed Timestamp Tests ---
# -----------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "input_timestamp, expected_output",
    [
        # --- Valid formats that should pass through unchanged ---
        ("00:05:58.800", "00:05:58.800"),
        ("0:5:8.8", "0:5:8.8"),
        ("5:58.800", "5:58.800"),
        ("58.800", "58.800"),
        ("05:58", "05:58"),
        ("0:00:00.000", "0:00:00.000"),
        # --- Faulty formats that can be sanitized ---
        (" 5:58.800 ", "5:58.800"),  # Leading/trailing spaces
        ("05:58S.800", "05:58.800"),  # Addition of 'S' inside the timestamp
        ("0:01 R:39.000", "0:01:39.000"),  # Addition of ' R' inside the timestamp
        ("0:02:11 A.M.", "0:02:11"),  # Addition of ' A.M.' at the end
        ("00:01:::23..456", "00:01:23.456"),  # Multiple colons and periods
        ("0:01:23.", "0:01:23"),  # period without digits after it
        ("0:01:", "0:01"),  # colon without digits after it
    ],
)
def test_sanitize_proposed_timestamp(input_timestamp: str, expected_output: str) -> None:
    """Tests the `_sanitize_proposed_timestamp` function with various formats and edge cases."""
    actual_output = _sanitize_proposed_timestamp(input_timestamp)
    assert actual_output == expected_output


# -----------------------------------------
# --- Full-Video Transform Tests ---
# -----------------------------------------


@pytest.mark.unit
def test_full_video_timestamps_are_converted_to_frames_without_offset() -> None:
    """Tests that a full-video analysis turns Gemini's timestamps directly into frames."""
    video_metadata_index = VideoMetadataIndex.from_list(
        [
            VideoMetadata(
                file_nr=0,
                filename="video.mp4",
                local_path=Path("video.mp4"),
                xmeml_pathurl="file://localhost/video.mp4",
                timebase=25,
                duration_frames=90000,
                duration_seconds=3600.0,
            )
        ]
    )
    proposals = [
        GeminiVideoClipProposal(
            source_filename="video.mp4",
            start_timestamp="0:00:10.000",
            end_timestamp="0:00:20.500",
            label="Test clip",
        )
    ]

    results = transform_gemini_proposals(
        gemini_video_clip_proposals=proposals,
        video_metadata_index=video_metadata_index,
        fps_analysis=1,
    )

    assert len(results) == 1
    result = results[0]
    # 10s * 25fps = 250, 20.5s * 25fps = 512.5 -> 512
    assert (result.in_frame, result.out_frame) == (250, 512)
    assert result.source_filename == "video.mp4"
    assert (result.start_timestamp, result.end_timestamp) == ("0:00:10.000", "0:00:20.500")


# -----------------------------------------
# --- Snapping to Cuts ---
# -----------------------------------------

# Cuts detected in the fire test video (25 fps), and the boundaries Gemini proposed for a trailer on it at 1 fps,
# so the tolerance is one sampling interval of 25 frames
FIRE_VIDEO_CUTS = [0, 125, 236, 503, 575, 650, 736, 1176, 1302, 1853, 1957, 3958, 4076, 4254]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("proposed", "expected"),
    [
        ((1175, 1287), (1176, 1302)),  # 47.00-51.50: starts 1 frame before the cut, ends 15 frames before the next
        ((1850, 1950), (1853, 1957)),  # 74.00-78.00: starts 3 frames before the cut
        ((3950, 4075), (3958, 4076)),  # 158.00-163.00: starts 8 frames before the cut
        ((125, 225), (125, 236)),  # 5.00-9.00: start on the cut stays, end moves onto the next cut
        ((575, 700), (575, 700)),  # 23.00-28.00: end in the middle of a shot, 50 and 36 frames from the cuts
    ],
    ids=["1 frame early", "3 frames early", "8 frames early", "end before the cut", "end mid-shot"],
)
def test_clip_boundaries_snap_to_the_cuts(proposed: tuple[int, int], expected: tuple[int, int]) -> None:
    assert _snap_to_cuts(*proposed, FIRE_VIDEO_CUTS, 25) == expected


@pytest.mark.unit
def test_tolerance_is_one_sampling_interval() -> None:
    """At 4 fps on a 25 fps video Gemini sees every 7th frame, so a cut 10 frames away is another boundary."""
    assert _snap_to_cuts(100, 300, [90, 305], 7) == (100, 305)


@pytest.mark.unit
def test_short_clip_that_would_collapse_stays_unsnapped() -> None:
    """In and out of a short clip near the same cut would land on it; the clip keeps its frames."""
    assert _snap_to_cuts(990, 1005, [1000], 25) == (990, 1005)


@pytest.mark.unit
def test_snapping_takes_the_nearest_cut() -> None:
    assert _snap_to_cuts(100, 400, [95, 110, 380, 420], 25) == (95, 380)


@pytest.mark.unit
def test_snapping_does_not_exceed_the_maximum_clip_duration() -> None:
    """A 60 s clip at 25 fps (1500 frames) whose end would snap 8 frames later keeps its frames."""
    assert _snap_to_cuts(1000, 2500, [1000, 2508], 25, max_frames=1500) == (1000, 2500)
    assert _snap_to_cuts(1000, 2500, [1000, 2508], 25) == (1000, 2508)


# -----------------------------------------
# --- Video End Tests ---
# -----------------------------------------


def _video_of_58_5_seconds() -> VideoMetadataIndex:
    """A 25 fps video of 58.5 seconds (frames 0 to 1462) without detected cuts."""
    return VideoMetadataIndex.from_list(
        [
            VideoMetadata(
                file_nr=0,
                filename="video.mp4",
                local_path=Path("video.mp4"),
                xmeml_pathurl="file://localhost/video.mp4",
                timebase=25,
                duration_frames=1462,
                duration_seconds=58.5,
            )
        ]
    )


def _proposal(start: str, end: str, label: str = "clip") -> GeminiVideoClipProposal:
    return GeminiVideoClipProposal(source_filename="video.mp4", start_timestamp=start, end_timestamp=end, label=label)


@pytest.mark.unit
def test_clip_end_after_the_video_end_is_moved_onto_it() -> None:
    """At 4 fps the snap tolerance is 7 frames, too little for an end 12 frames after the video end."""
    results = transform_gemini_proposals(
        gemini_video_clip_proposals=[_proposal("0:50.000", "0:59.000")],
        video_metadata_index=_video_of_58_5_seconds(),
        fps_analysis=4,
    )

    assert (results[0].in_frame, results[0].out_frame) == (1250, 1462)


@pytest.mark.unit
def test_clip_after_the_video_end_is_left_out(caplog: pytest.LogCaptureFixture) -> None:
    """A clip that starts after the end has no frames to show; the other clips are kept."""
    results = transform_gemini_proposals(
        gemini_video_clip_proposals=[_proposal("0:10.000", "0:15.000"), _proposal("1:02.000", "1:05.000", "late")],
        video_metadata_index=_video_of_58_5_seconds(),
        fps_analysis=1,
    )

    assert [(clip.in_frame, clip.out_frame) for clip in results] == [(250, 375)]
    assert "Left out the clip 'late'" in caplog.text
    assert "starts after the end of the video" in caplog.text


@pytest.mark.unit
def test_clip_over_the_whole_video_with_a_rounded_up_end_is_kept() -> None:
    """A single-shot video, proposed as one clip whose end Gemini rounded up past the end of the video."""
    results = transform_gemini_proposals(
        gemini_video_clip_proposals=[_proposal("0:00.000", "0:59.000")],
        video_metadata_index=_video_of_58_5_seconds(),
        fps_analysis=1,
    )

    assert (results[0].in_frame, results[0].out_frame) == (0, 1462)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("bad_proposal", "reason"),
    [
        (_proposal("0:20.000", "0:15.000", "backwards"), "does not end after it starts"),
        (_proposal("0:00.000", "0:45.000", "too long"), "more than the 30 seconds the task allows"),
        (_proposal("0:20.000", "", "no end"), "timestamp is missing"),
        (_proposal("0:20.000", "soon", "unparseable"), "Invalid or unrecognized timestamp"),
        (_proposal("0:20.000", "1:05:00.000", "hours for minutes"), "seconds after the end of the video"),
    ],
    ids=["end before start", "longer than the task allows", "missing end", "unparseable end", "far after the end"],
)
def test_unusable_proposal_is_left_out_and_the_others_are_kept(
    bad_proposal: GeminiVideoClipProposal, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    results = transform_gemini_proposals(
        gemini_video_clip_proposals=[_proposal("0:10.000", "0:15.000"), bad_proposal],
        video_metadata_index=_video_of_58_5_seconds(),
        fps_analysis=1,
        max_allowed_clip_duration_seconds=30.0,
    )

    assert [(clip.in_frame, clip.out_frame) for clip in results] == [(250, 375)]
    assert f"Left out the clip '{bad_proposal.label}'" in caplog.text
    assert reason in caplog.text
