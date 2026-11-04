"""A preview video of the cut: the clips of the sequence, cut from their source videos and joined with ffmpeg."""

import logging
import re
import tempfile
from pathlib import Path

from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.media.ffmpeg import run_ffmpeg

# Peak level below which an audio stream counts as silent; ffmpeg reports -91 dB for digital silence
SILENCE_THRESHOLD_DB = -60.0

# Peak level per filter in the log of ffmpeg's volumedetect, e.g. "[Parsed_volumedetect_2 @ 0x1] max_volume: -3.5 dB"
_MAX_VOLUME_PATTERN = re.compile(r"\[Parsed_volumedetect_(\d+) @ [^\]]+\] max_volume: (-?[\d.]+) dB")


def render_preview(
    video_clip_proposals: list[VideoClipProposal],
    video_metadata_index: VideoMetadataIndex,
    output_path: Path,
) -> None:
    """
    Render the clips in their order into one MP4 file.

    Every clip is re-encoded on its own (frame-accurate cuts, unlike a stream copy that starts at the
    previous keyframe) into one common format: H.264 with square pixels in the display size and frame rate of
    the job's first video (anamorphic material is widened, NTSC rates are kept), letterboxed if a source has
    another aspect ratio, and the sound of the first audio stream that is not silent as AAC stereo (broadcast
    files often carry several streams, some of them empty), or silence if a source has none. The clips are
    then joined without another encode.

    :param video_clip_proposals: The clips in cut order, with in and out frames of their source videos.
    :param video_metadata_index: Metadata of the source videos, with their local paths.
    :param output_path: Path of the MP4 to write.
    :raises ValueError: If there are no clips.
    :raises RuntimeError: If ffmpeg is missing, fails or runs into its timeout.
    """
    if not video_clip_proposals:
        raise ValueError("No clips to render")

    # The sequence of the XMEML takes size and rate of the job's first video, the preview too
    first_video = video_metadata_index.values()[0]
    # Display size with square pixels, rounded to an even width as H.264 requires
    width = round(first_video.width * first_video.sample_aspect_ratio / 2) * 2
    height = first_video.height
    fps = f"{first_video.timebase * 1000}/1001" if first_video.ntsc else str(first_video.timebase)

    # Audio stream of each source video, measured once per video
    audio_streams = {
        filename: _first_audible_stream(video_metadata_index.get(filename))
        for filename in {clip.source_filename for clip in video_clip_proposals}
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        clip_paths = []
        for clip_nr, clip in enumerate(video_clip_proposals):
            clip_path = Path(tmpdir) / f"clip_{clip_nr:03d}.mp4"
            video = video_metadata_index.get(clip.source_filename)
            _render_clip(clip, video, audio_streams[clip.source_filename], clip_path, width, height, fps)
            clip_paths.append(clip_path)

        # The concat demuxer joins files of the same format without re-encoding
        clip_list = Path(tmpdir) / "clips.txt"
        clip_list.write_text("".join(f"file '{path}'\n" for path in clip_paths), encoding="utf-8")
        # fmt: off
        run_ffmpeg([
            "-f", "concat", "-safe", "0", "-i", str(clip_list),
            "-c", "copy", "-movflags", "+faststart",
            str(output_path),
        ])
        # fmt: on
    logging.info(f"Preview video with {len(video_clip_proposals)} clip(s) written to {output_path}")


def _first_audible_stream(video: VideoMetadata) -> int | None:
    """
    Find the first audio stream of a video that is not silent.

    A single stream is taken as it is. With several, ffmpeg measures the peak level of each in one pass over
    the file's audio.

    :param video: Metadata of the video, with its local path and number of audio streams.
    :raises RuntimeError: If ffmpeg is missing, fails or runs into its timeout.
    :return: Index of the stream among the file's audio streams, or None if the file has no sound.
    """
    if video.audio_stream_count <= 1:
        return 0 if video.audio_stream_count == 1 else None

    streams = range(video.audio_stream_count)
    measure = ";".join(f"[0:a:{i}]volumedetect[out{i}]" for i in streams)
    outputs = [arg for i in streams for arg in ("-map", f"[out{i}]")]
    stderr = run_ffmpeg(
        ["-i", str(video.local_path), "-vn", "-filter_complex", measure, *outputs, "-f", "null", "-"],
        loglevel="info",
    )
    peaks = {int(index): float(level) for index, level in _MAX_VOLUME_PATTERN.findall(stderr)}

    for stream in streams:
        if peaks.get(stream, SILENCE_THRESHOLD_DB) > SILENCE_THRESHOLD_DB:
            logging.info(f"Preview sound of '{video.filename}': audio stream {stream + 1}, {peaks[stream]} dB peak")
            return stream
    logging.warning(f"All {video.audio_stream_count} audio streams of '{video.filename}' are silent")
    return None


def _render_clip(
    clip: VideoClipProposal,
    video: VideoMetadata,
    audio_stream: int | None,
    clip_path: Path,
    width: int,
    height: int,
    fps: str,
) -> None:
    """
    Cut one clip from its source video and encode it in the common preview format.

    :param clip: The clip, with in and out frame (out exclusive).
    :param video: Metadata of the clip's source video.
    :param audio_stream: Index of the audio stream to take the sound from, or None for silence.
    :param clip_path: Path of the clip file to write.
    :param width: Width of the preview in pixels.
    :param height: Height of the preview in pixels.
    :param fps: Frame rate of the preview, as ffmpeg takes it (e.g. "25" or "30000/1001").
    :raises RuntimeError: If ffmpeg is missing, fails or runs into its timeout.
    """
    start = f"{clip.in_frame / video.frame_rate:.3f}"
    duration = f"{(clip.out_frame - clip.in_frame) / video.frame_rate:.3f}"

    # Seeking before -i is fast and, since the clip is re-encoded, still frame-accurate
    args = ["-ss", start, "-t", duration, "-i", str(video.local_path)]
    if audio_stream is not None:
        audio_input = f"0:a:{audio_stream}"
    else:
        args += ["-f", "lavfi", "-t", duration, "-i", "anullsrc=r=48000:cl=stereo"]
        audio_input = "1:a:0"

    # Square pixels first (widens anamorphic material), then fit into the preview size, pad the rest black,
    # common frame rate
    video_filter = (
        "scale=trunc(iw*sar/2)*2:ih,setsar=1,"
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )
    # fmt: off
    run_ffmpeg(args + [
        "-map", "0:v:0", "-map", audio_input,
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "48000",
        "-shortest",
        str(clip_path),
    ])
    # fmt: on
