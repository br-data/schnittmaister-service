import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from src.config.task_config import TASKS_CONFIG, TaskConfig
from src.models.job_metadata import JobMetadata
from src.models.request_input import XmemlCreateRequest
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.media.shot_detection import detect_shot_cuts
from src.services.media.video_probe import probe_video
from src.utils.video_limits import ensure_video_fits_single_request


def build_metadata_from_request(request: XmemlCreateRequest) -> tuple[JobMetadata, VideoMetadataIndex]:
    """
    Build job and video metadata for a request.

    The task config comes from TASKS_CONFIG with the request's overrides applied. The videos are probed
    with ffprobe for duration, frame rate, size and audio layout. Right after the probe, before anything
    expensive (shot detection, upload), the videos are checked against the model's token budget. Then the
    cuts of each video are detected with ffmpeg; if that fails, clip boundaries are not snapped.

    :param request: The request with the videos and the task configuration.
    :raises pydantic.ValidationError: If the overrides make the task config invalid (e.g. fps outside the
        allowed range).
    :raises RuntimeError: If ffprobe is not installed.
    :raises UnreadableVideoError: If ffprobe cannot read a video.
    :raises VideoTooLongError: If the videos together exceed the model's token budget.
    :return: Tuple of (JobMetadata, VideoMetadataIndex).
    """
    logging.info(f"Building metadata from request for job {request.job_id}")

    job_metadata = JobMetadata(
        job_id=request.job_id,
        task_config=_task_config_from_request(request),
        user_text_input=request.user_text_input,
        render_preview=request.render_preview,
    )

    videos = [_video_metadata_from_path(file_nr, path) for file_nr, path in enumerate(request.video_paths)]
    _ensure_videos_fit_single_request(videos, job_metadata.task_config)
    for video in videos:
        _detect_cuts(video)
    video_metadata_index = VideoMetadataIndex.from_list(videos)

    logging.info(f"Successfully built metadata from request for job {request.job_id}")
    return job_metadata, video_metadata_index


def _task_config_from_request(request: XmemlCreateRequest) -> TaskConfig:
    """
    Get the task config of the request's task with the request's overrides applied.

    :param request: The request.
    :raises pydantic.ValidationError: If the overrides make the task config invalid.
    :return: The task config of the job.
    """
    overrides: dict = {}
    if request.gemini_model is not None:
        overrides["model_id_gemini"] = request.gemini_model
    if request.fps_analysis is not None:
        overrides["fps_analysis"] = request.fps_analysis
    if request.media_resolution is not None:
        overrides["media_resolution"] = request.media_resolution
    return TASKS_CONFIG[request.task_name].with_overrides(**overrides)


def _video_metadata_from_path(file_nr: int, path: Path) -> VideoMetadata:
    """
    Build the metadata of a video of the request, from an ffprobe of the file.

    The XMEML references the video at its local path, so the editor links it on import. Duration, frame
    rate, size and audio layout come from the probe.

    :param file_nr: Number of the video within the job, used in the XMEML.
    :param path: Local path of the video.
    :raises RuntimeError: If ffprobe is not installed.
    :raises UnreadableVideoError: If ffprobe cannot read the video.
    :return: The video's metadata.
    """
    metadata: dict = {
        "file_nr": file_nr,
        "filename": path.name,
        "xmeml_pathurl": file_url(path.resolve()),
        "local_path": path,
        "mime_type": mimetypes.guess_type(path.name)[0],
    }

    probed = probe_video(path)
    metadata |= {
        "duration_seconds": probed.duration_seconds,
        "duration_frames": probed.duration_frames,
        "timebase": probed.timebase,
        "ntsc": probed.ntsc,
        "width": probed.width,
        "height": probed.height,
        "sample_aspect_ratio": probed.sample_aspect_ratio,
        "audio_stream_count": probed.audio_stream_count,
    }
    # A file without an audio stream keeps the VideoMetadata defaults for the XMEML audio tracks
    if probed.audio_layout_mode is not None:
        metadata |= {"audio_layout_mode": probed.audio_layout_mode, "audio_track_count": probed.audio_track_count}
    return VideoMetadata(**metadata)


def _ensure_videos_fit_single_request(videos: list[VideoMetadata], task_config: TaskConfig) -> None:
    """
    Check that the videos of the job, which go to Gemini in one request, fit into the model's token budget.

    :param videos: The probed videos of the job.
    :param task_config: Task config with model, sampling rate and media resolution.
    :raises VideoTooLongError: If the videos together exceed the model's token budget.
    """
    ensure_video_fits_single_request(
        video_duration_seconds=sum(video.duration_seconds for video in videos),
        model_id=task_config.model_id_gemini,
        fps_analysis=task_config.fps_analysis,
        media_resolution=task_config.media_resolution,
    )


def _detect_cuts(video: VideoMetadata) -> None:
    """
    Detect the cuts of a probed video and store them on its metadata.

    A failed detection is logged; the clips of the video are then not snapped.

    :param video: Metadata of the video; its shot_cuts are set.
    """
    try:
        video.shot_cuts = detect_shot_cuts(video.local_path, video.frame_rate)
    except RuntimeError as e:
        logging.warning(f"Could not detect the cuts of '{video.filename}': {e}. Clip boundaries are not snapped.")


def file_url(path: Path) -> str:
    r"""
    Write an absolute local path as the file URL Premiere uses in its own XML exports.

    POSIX paths become ``file://localhost/Users/me/clip.mp4``, Windows drives
    ``file://localhost/C%3A/Users/me/clip.mp4`` and UNC paths ``file://server/share/clip.mp4``. Characters
    outside the unreserved set are percent-encoded, the drive colon included, as Premiere does.

    :param path: Absolute path of the video.
    :raises ValueError: If the path is not absolute.
    :return: The file URL.
    """
    # as_uri gives file:///C:/... for drives and file://server/share/... for UNC paths; Premiere writes
    # the drive form with a localhost host and an encoded colon
    url = path.as_uri()
    if url.startswith("file:///"):
        url = "file://localhost/" + quote(url[len("file:///") :].replace(":", "%3A", 1), safe="/%")
    return url
