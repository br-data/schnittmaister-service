import logging
import math
import re

from src.config.snapping_config import SnappingConfig
from src.models.gemini_output import GeminiVideoClipProposal, VideoClipProposal
from src.models.user_messages import add_user_warning
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.utils.time_utils import seconds_to_frames, seconds_to_timestamp, timestamp_to_seconds

SNAPPING_CONFIG = SnappingConfig()

# How far beyond one sampling interval a clip may end after the end of its video and still be cut to it; Gemini
# rounds the end of a clip that runs to the end of the video up, but an end further away is a wrong timestamp,
# e.g. hours confused with minutes
END_OVERSHOOT_SECONDS = 1.0


def transform_gemini_proposals(
    gemini_video_clip_proposals: list[GeminiVideoClipProposal],
    video_metadata_index: VideoMetadataIndex,
    fps_analysis: int,
    max_allowed_clip_duration_seconds: float | None = None,
) -> list[VideoClipProposal]:
    """
    Transform GeminiVideoClipProposals into enriched VideoClipProposal objects.

    A proposal that cannot be used (missing or unparseable timestamps, unknown source file, failed checks) is
    left out with a warning, so one bad proposal does not cost the other clips.

    :param gemini_video_clip_proposals: List of GeminiVideoClipProposal objects from Gemini.
    :param video_metadata_index: Index of VideoMetadata for video files.
    :param fps_analysis: Frames per second Gemini sampled; sets how far a boundary may be snapped to a cut.
    :param max_allowed_clip_duration_seconds: Maximum allowed clip duration (from task config).
    :return: List of VideoClipProposal objects with calculated in/out frames, in Gemini's order.
    """
    clips = []
    for gemini_proposal in gemini_video_clip_proposals:
        try:
            clips.append(
                _to_video_clip_proposal(
                    gemini_proposal=gemini_proposal,
                    video_metadata_index=video_metadata_index,
                    fps_analysis=fps_analysis,
                    max_allowed_clip_duration_seconds=max_allowed_clip_duration_seconds,
                )
            )
        except ValueError as e:
            add_user_warning(
                f"Left out the clip '{gemini_proposal.label}' ({gemini_proposal.start_timestamp} - "
                f"{gemini_proposal.end_timestamp}) of '{gemini_proposal.source_filename}': {e}"
            )
    return clips


def _sanitize_proposed_timestamp(timestamp_str: str) -> str:
    """
    Cleans a raw timestamp string from Gemini by removing invalid characters.

    Removes every character that is not a digit, colon or period, and colons and periods with no
    digit on either side; then collapses repeated colons or periods and strips them at the end. This
    handles LLM hallucinations like '05:58S.800', '0:01 R:39.000', or '0:02:11 A.M.'

    :param timestamp_str: The raw timestamp string from the Gemini proposal.
    :return: The cleaned timestamp string.
    """
    # Remove characters other than digits, ':' and '.', and runs of ':'/'.' with no digit on either side
    sanitized = re.sub(r"(?<!\d)[:.]+(?!\d)|[^\d:.]", "", timestamp_str)

    # Replace multiple consecutive colons/periods with a single one
    sanitized = re.sub(r"[:]{2,}", ":", sanitized)
    sanitized = re.sub(r"[.]{2,}", ".", sanitized)

    # Remove trailing colons or periods
    sanitized = re.sub(r"[:.]+$", "", sanitized)

    if sanitized != timestamp_str:
        logging.warning(f"Sanitized timestamp: Original='{timestamp_str}', Cleaned='{sanitized}'")
    return sanitized


def _to_video_clip_proposal(
    gemini_proposal: GeminiVideoClipProposal,
    video_metadata_index: VideoMetadataIndex,
    fps_analysis: int,
    max_allowed_clip_duration_seconds: float | None,
) -> VideoClipProposal:
    """
    Check one Gemini proposal, convert its timestamps into frames of its video and snap them to the cuts.

    An end just after the end of the video (up to one sampling interval plus END_OVERSHOOT_SECONDS) is moved
    onto it before the checks; Gemini often rounds the end of a clip that runs to the end of the video up, e.g.
    "0:59.000" for a 58.5-second video.

    :param gemini_proposal: Proposal from Gemini.
    :param video_metadata_index: Index of VideoMetadata for video files.
    :param fps_analysis: Frames per second Gemini sampled.
    :param max_allowed_clip_duration_seconds: Maximum allowed clip duration (from task config).
    :raises ValueError: If the proposal has missing or unparseable timestamps or an unknown source filename,
        starts after the end of the video, ends too far after it, or fails the semantic checks.
    :return: VideoClipProposal with in/out frames.
    """
    if not gemini_proposal.start_timestamp or not gemini_proposal.end_timestamp:
        raise ValueError("the start or end timestamp is missing")

    source_filename = _sanitize_proposed_source_filename(gemini_proposal, video_metadata_index)
    video_metadata = video_metadata_index.get(source_filename)
    video_fps = video_metadata.frame_rate  # Actual video framerate, NOT analysis fps

    # Gemini timestamp -> seconds -> frame of the source video
    start_timestamp = _sanitize_proposed_timestamp(gemini_proposal.start_timestamp)
    end_timestamp = _sanitize_proposed_timestamp(gemini_proposal.end_timestamp)
    start_seconds = timestamp_to_seconds(start_timestamp)
    end_seconds = timestamp_to_seconds(end_timestamp)
    in_frame = seconds_to_frames(start_seconds, video_fps)
    out_frame = seconds_to_frames(end_seconds, video_fps)

    logging.info(
        f"Proposal: source={source_filename} | Gemini: {start_timestamp} - {end_timestamp} | "
        f"→ XMEML: {seconds_to_timestamp(start_seconds)} - {seconds_to_timestamp(end_seconds)} "
        f"(frames {in_frame}-{out_frame} @{round(video_fps, 3):g}fps)"
    )

    # A clip behind the end of the video has no frames to show; an end just behind it is moved onto it
    if in_frame >= video_metadata.duration_frames:
        raise ValueError("it starts after the end of the video")
    overshoot_seconds = (out_frame - video_metadata.duration_frames) / video_fps
    if overshoot_seconds > 1 / fps_analysis + END_OVERSHOOT_SECONDS:
        raise ValueError(f"it ends {overshoot_seconds:.1f} seconds after the end of the video")
    if out_frame > video_metadata.duration_frames:
        logging.info(
            f"Clip end {out_frame} is after the end of '{source_filename}', moved to {video_metadata.duration_frames}"
        )
        out_frame = video_metadata.duration_frames

    _semantic_check_proposed_clip_duration(
        in_frame=in_frame,
        out_frame=out_frame,
        video_fps=video_fps,
        max_allowed_clip_duration_seconds=max_allowed_clip_duration_seconds,
    )

    # After the checks: they judge Gemini's proposal, and the snapping keeps within the maximum duration
    max_frames = (
        int(max_allowed_clip_duration_seconds * video_fps) if max_allowed_clip_duration_seconds is not None else None
    )
    in_frame, out_frame = _snap_to_video_cuts(in_frame, out_frame, video_metadata, fps_analysis, max_frames)

    return VideoClipProposal(
        **(
            gemini_proposal.model_dump()
            | {"source_filename": source_filename, "start_timestamp": start_timestamp, "end_timestamp": end_timestamp}
        ),
        in_frame=in_frame,
        out_frame=out_frame,
    )


def _sanitize_proposed_source_filename(
    gemini_proposal: GeminiVideoClipProposal,
    video_metadata_index: VideoMetadataIndex,
) -> str:
    """
    Validates and corrects the source filename from a Gemini proposal.

    For single-video jobs, it ignores Gemini's output and returns the only possible filename.
    For multi-video jobs, it validates that the filename from Gemini exists in the index.

    :param gemini_proposal: The raw proposal from Gemini.
    :param video_metadata_index: The index of all video metadata for the job.
    :raises ValueError: If, in a multi-video job, Gemini's filename is not in the index.
    :return: The corrected filename.
    """
    is_single_video_job = len(video_metadata_index) == 1

    if is_single_video_job:
        # If there's only one video, we know its correct filename.
        correct_filename = next(iter(video_metadata_index.keys()))
        if gemini_proposal.source_filename != correct_filename:
            logging.info(
                f"Correcting filename from Gemini proposal for single-video job. "
                f"Gemini provided '{gemini_proposal.source_filename}', "
                f"overwriting with '{correct_filename}'."
            )
        return correct_filename

    # For multi-video jobs, validate the filename from Gemini.
    source_filename = gemini_proposal.source_filename
    if source_filename not in video_metadata_index:
        raise ValueError(
            f"Gemini provided an invalid source_filename '{source_filename}' "
            f"that does not exist in the video metadata index. Valid names are: {video_metadata_index.keys()}"
        )

    return source_filename


def _semantic_check_proposed_clip_duration(
    in_frame: int,
    out_frame: int,
    video_fps: float,
    max_allowed_clip_duration_seconds: float | None,
) -> None:
    """
    Check that a proposed clip ends after it starts and is not longer than the task allows.

    :param in_frame: The calculated in-frame of the proposed clip.
    :param out_frame: The calculated out-frame of the proposed clip, at most the end of the video.
    :param video_fps: Video framerate in frames per second.
    :param max_allowed_clip_duration_seconds: Maximum allowed clip duration in seconds, or None for no limit.
    :raises ValueError: If the proposed clip fails a check.
    """
    # Check 1: the clip ends after it starts
    if in_frame >= out_frame:
        raise ValueError(f"it does not end after it starts (frames {in_frame} to {out_frame})")

    # Check 2: the clip is not longer than the task's maximum clip duration (if set)
    clip_seconds = (out_frame - in_frame) / video_fps
    if max_allowed_clip_duration_seconds is not None and clip_seconds > max_allowed_clip_duration_seconds:
        raise ValueError(
            f"it is {clip_seconds:.1f} seconds long, more than the {max_allowed_clip_duration_seconds:g} seconds "
            f"the task allows"
        )


def _snap_to_video_cuts(
    in_frame: int, out_frame: int, video: VideoMetadata, fps_analysis: int, max_frames: int | None
) -> tuple[int, int]:
    """
    Snap the boundaries of a clip onto the cuts of its video that are within the snap tolerance.

    Gemini's timestamps fall on its sampling grid, so a real cut lies at most one sampling interval away. The
    tolerance is SnappingConfig.snap_tolerance_intervals such intervals; the start and end of the video
    count as cuts too.

    :param in_frame: Start frame of the clip.
    :param out_frame: End frame of the clip (exclusive).
    :param video: Metadata of the clip's video, with its cuts and frame rate.
    :param fps_analysis: Frames per second Gemini sampled.
    :param max_frames: Maximum clip duration of the task in frames, or None for no limit.
    :return: The snapped in and out frame.
    """
    cuts = [0, *video.shot_cuts, video.duration_frames]
    tolerance_frames = math.ceil(SNAPPING_CONFIG.snap_tolerance_intervals * video.frame_rate / fps_analysis)
    return _snap_to_cuts(in_frame, out_frame, cuts, tolerance_frames, max_frames)


def _snap_to_cuts(
    in_frame: int, out_frame: int, cuts: list[int], tolerance_frames: int, max_frames: int | None = None
) -> tuple[int, int]:
    """
    Snap the in and out frame of a clip to the nearest cut within the tolerance.

    Both frames snap independently. The clip keeps its frames if both would land on the same cut, which can
    happen to a short clip, or if snapping would make it longer than max_frames.

    :param in_frame: Start frame of the clip.
    :param out_frame: End frame of the clip (exclusive).
    :param cuts: Frames where a shot starts, incl. the start and end of the video.
    :param tolerance_frames: Maximum distance between a boundary and the cut it snaps to.
    :param max_frames: Maximum clip duration in frames, or None for no limit.
    :return: The snapped in and out frame.
    """
    snapped_in = _nearest_cut(in_frame, cuts, tolerance_frames)
    snapped_out = _nearest_cut(out_frame, cuts, tolerance_frames)
    new_in = in_frame if snapped_in is None else snapped_in
    new_out = out_frame if snapped_out is None else snapped_out

    if new_in >= new_out:
        logging.warning(f"Snapping clip {in_frame}-{out_frame} would leave no frames; keeping it unsnapped")
        return in_frame, out_frame
    if max_frames is not None and new_out - new_in > max_frames:
        logging.info(f"Snapping clip {in_frame}-{out_frame} would exceed {max_frames} frames; keeping it unsnapped")
        return in_frame, out_frame
    if (new_in, new_out) != (in_frame, out_frame):
        logging.info(f"Snapped clip {in_frame}-{out_frame} to the cuts: {new_in}-{new_out}")
    return new_in, new_out


def _nearest_cut(frame: int, cuts: list[int], tolerance_frames: int) -> int | None:
    """
    Find the cut nearest to a frame, at most tolerance_frames away.

    :param frame: The frame to snap.
    :param cuts: Frames of the cuts.
    :param tolerance_frames: Maximum distance to the cut.
    :return: The nearest cut within the tolerance, or None if there is none.
    """
    near_cuts = [cut for cut in cuts if abs(frame - cut) <= tolerance_frames]
    return min(near_cuts, key=lambda cut: abs(frame - cut), default=None)
