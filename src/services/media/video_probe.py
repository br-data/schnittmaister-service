"""Metadata of a local video file with ffprobe: duration, frame rate, length in frames, size and audio layout."""

import json
import logging
import subprocess
from pathlib import Path

from pydantic import BaseModel

from src.config.xmeml_config import AudioLayout
from src.models.errors import UnreadableVideoError
from src.utils.time_utils import real_frame_rate


class ProbedVideo(BaseModel):
    """
    Metadata of a video as read from its container and streams.

    :param duration_seconds: Duration of the container.
    :param timebase: Frame rate of the video stream, rounded to an integer.
    :param ntsc: Whether the frame rate is an NTSC rate, 1000/1001 of the timebase (e.g. 29.97 for 30).
    :param duration_frames: Length of the video stream in whole frames of its timebase, from the stream's
        duration. Phones record with a variable frame rate and store fewer images than that, but the XMEML
        timeline and the clip boundaries count in the timebase.
    :param width: Width of the picture in pixels as it is shown: phones store portrait video as landscape
        frames with a rotation of 90 degrees, so width and height are swapped for those.
    :param height: Height of the picture in pixels as it is shown.
    :param sample_aspect_ratio: Width of a pixel relative to its height; 1.0 for square pixels, e.g. 64/45 for
        anamorphic PAL 16:9, where 720x576 pixels are shown as 1024x576.
    :param audio_stream_count: Number of audio streams; 0 if the file has none.
    :param audio_layout_mode: Layout of the audio streams, see audio_layout_from_streams. None if the file
        has no audio stream.
    :param audio_track_count: Number of audio tracks for the layout. None if the file has no audio stream.
    """

    duration_seconds: float
    timebase: int
    ntsc: bool
    duration_frames: int
    width: int
    height: int
    sample_aspect_ratio: float
    audio_stream_count: int
    audio_layout_mode: AudioLayout | None
    audio_track_count: int | None


def probe_video(path: Path) -> ProbedVideo:
    """
    Read the metadata of a local video with ffprobe.

    :param path: Path of the video.
    :raises RuntimeError: If ffprobe is not installed.
    :raises UnreadableVideoError: If ffprobe cannot read the file, or the duration or the video stream is missing.
    :return: The probed metadata.
    """
    try:
        # fmt: off
        completed = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        # fmt: on
    except FileNotFoundError as e:
        raise RuntimeError("ffprobe is not installed or not on the PATH (it comes with ffmpeg)") from e
    except subprocess.CalledProcessError as e:
        raise UnreadableVideoError(f"Could not read '{path.name}' as a video. ffprobe: {e.stderr.strip()}") from e

    probe_data = json.loads(completed.stdout)
    try:
        duration_seconds = float(probe_data["format"]["duration"])
        video_stream = _find_video_stream(probe_data)
        width, height = int(video_stream["width"]), int(video_stream["height"])
    except (KeyError, ValueError, TypeError) as e:
        raise UnreadableVideoError(f"'{path.name}' has no readable video stream or duration ({e})") from e

    sample_aspect_ratio = _parse_sample_aspect_ratio(video_stream)
    if _is_rotated_by_quarter_turn(video_stream):
        # ffmpeg and the editors show the frames turned, so the picture is as wide as the stored frames are high
        width, height, sample_aspect_ratio = height, width, 1 / sample_aspect_ratio

    frame_rate_parts = _parse_frame_rate(video_stream)
    if frame_rate_parts is None:
        raise UnreadableVideoError(
            f"'{path.name}' has no plausible frame rate (r_frame_rate {video_stream.get('r_frame_rate')}, "
            f"avg_frame_rate {video_stream.get('avg_frame_rate')})"
        )
    timebase, ntsc = frame_rate_parts
    frame_rate = real_frame_rate(timebase, ntsc)
    duration_frames = _whole_frames(_parse_stream_duration(video_stream, duration_seconds), frame_rate)

    audio_streams = [stream for stream in probe_data.get("streams", []) if stream.get("codec_type") == "audio"]
    audio_layout_mode, audio_track_count = audio_layout_from_streams(audio_streams)

    logging.info(
        f"Probed '{path.name}': {duration_seconds:.1f}s (~{duration_seconds / 60:.1f} min), "
        f"{width}x{height}, {round(frame_rate, 3):g} fps, "
        f"{duration_frames} frames, audio: {audio_layout_mode} with {audio_track_count} track(s)"
    )
    return ProbedVideo(
        duration_seconds=duration_seconds,
        timebase=timebase,
        ntsc=ntsc,
        duration_frames=duration_frames,
        width=width,
        height=height,
        sample_aspect_ratio=sample_aspect_ratio,
        audio_stream_count=len(audio_streams),
        audio_layout_mode=audio_layout_mode,
        audio_track_count=audio_track_count,
    )


def audio_layout_from_streams(audio_streams: list[dict]) -> tuple[AudioLayout | None, int | None]:
    """
    Derive the XMEML audio layout from the audio streams of a file.

    One stream with one or two channels is a stereo pair (a mono stream is routed to both sides). Everything
    else gets one mono track per source channel, counted across all streams: eight mono streams and four
    stereo streams both give eight tracks, as in broadcast masterclips with discrete channels.

    :param audio_streams: The audio streams as ffprobe reports them; only ``channels`` is read (2 if missing).
    :return: Layout and track count; both None if there is no audio stream.
    """
    if not audio_streams:
        return None, None
    channel_counts = [int(stream.get("channels") or 2) for stream in audio_streams]
    if len(channel_counts) == 1 and channel_counts[0] <= 2:
        return AudioLayout.STEREO_PAIR, 2
    return AudioLayout.MONO_PER_CHANNEL, sum(channel_counts)


def _find_video_stream(probe_data: dict) -> dict:
    """
    Find the first video stream in ffprobe output.

    :param probe_data: ffprobe output dictionary.
    :return: Video stream dictionary.
    :raises ValueError: If no video stream found.
    """
    for stream in probe_data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise ValueError("No video stream found in probe data")


def _parse_sample_aspect_ratio(video_stream: dict) -> float:
    """
    Parse the pixel aspect ratio of a video stream.

    ffprobe gives it as a ratio, e.g. "64:45"; "0:1" or a missing value mean unknown and count as square.

    :param video_stream: Video stream dictionary from ffprobe.
    :return: Width of a pixel relative to its height.
    """
    try:
        num, denom = map(int, str(video_stream.get("sample_aspect_ratio", "1:1")).split(":"))
        return num / denom if num > 0 and denom > 0 else 1.0
    except ValueError:
        return 1.0


def _parse_stream_duration(video_stream: dict, container_duration: float) -> float:
    """
    Read the duration of a video stream, which can be shorter than the container (e.g. if the sound runs on).

    :param video_stream: Video stream dictionary from ffprobe.
    :param container_duration: Duration of the container, used if the stream reports none (not every container does).
    :return: The duration in seconds.
    """
    try:
        duration = float(video_stream["duration"])
    except (KeyError, ValueError, TypeError):
        return container_duration
    return duration if duration > 0 else container_duration


def _whole_frames(duration_seconds: float, frame_rate: float) -> int:
    """
    Count the whole frames of the timebase that fit into a duration.

    A frame that the video fills only partly does not count, so the length never reaches past the last image.
    Rounding to three decimals first absorbs the microsecond precision of ffprobe's durations, e.g. 19.986633 s
    at 29.97 fps is 598.99990 frames, which are 599.

    :param duration_seconds: Duration of the video stream.
    :param frame_rate: Frame rate of the timebase, e.g. 29.97 for NTSC 30.
    :return: Number of whole frames.
    """
    return int(round(duration_seconds * frame_rate, 3))


def _parse_frame_rate(video_stream: dict) -> tuple[int, bool] | None:
    """
    Parse the frame rate of a video stream into a timebase and the NTSC flag.

    ffprobe gives the rate as a fraction. NTSC rates are 1000/1001 of a whole number: "30000/1001" (29.97) is
    timebase 30 with NTSC, as FCP7 XML and Premiere write it; "25/1" is timebase 25 without. The nominal rate
    (r_frame_rate) comes first; if it is missing or implausible ("0/0", or a time base like "90000/1"), the
    average rate (avg_frame_rate) is taken.

    :param video_stream: Video stream dictionary from ffprobe.
    :return: Timebase (the rate rounded to a whole number) and whether it is an NTSC rate, or None if neither
        rate is a number between 1 and 120.
    """
    for key in ("r_frame_rate", "avg_frame_rate"):
        try:
            num, denom = map(int, str(video_stream.get(key, "")).split("/"))
            rate = num / denom
        except (ValueError, ZeroDivisionError):
            continue
        timebase = round(rate)
        if 1 <= timebase <= 120:
            ntsc = abs(rate - timebase) > 0.005 and abs(rate - timebase * 1000 / 1001) < 0.005
            return timebase, ntsc
    return None


def _is_rotated_by_quarter_turn(video_stream: dict) -> bool:
    """
    Tell whether a video stream is shown turned by 90 or 270 degrees, as phones store portrait video.

    ffprobe reports the rotation in the display matrix of the stream's side data (older files: the "rotate" tag).

    :param video_stream: Video stream dictionary from ffprobe.
    :return: True if the picture is shown turned by a quarter turn.
    """
    rotations = [side_data.get("rotation") for side_data in video_stream.get("side_data_list", [])]
    rotations.append(video_stream.get("tags", {}).get("rotate"))
    for rotation in rotations:
        try:
            if round(float(rotation)) % 180 == 90:
                return True
        except (TypeError, ValueError):
            continue
    return False
