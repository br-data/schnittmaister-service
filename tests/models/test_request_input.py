from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.task_config import TaskName
from src.models.request_input import XmemlCreateRequest


@pytest.mark.unit
def test_request_accepts_existing_videos_in_supported_formats(tmp_path: Path) -> None:
    videos = [tmp_path / "a.MP4", tmp_path / "b.mov"]
    for video in videos:
        video.write_bytes(b"x")

    request = XmemlCreateRequest(job_id="job", video_paths=videos, task_name=TaskName.SCENE_DETECTION)

    assert request.video_paths == videos


@pytest.mark.unit
@pytest.mark.parametrize("user_text_input", [None, "", "   "])
def test_task_that_needs_a_text_input_rejects_a_request_without_one(
    tmp_path: Path, user_text_input: str | None
) -> None:
    video = tmp_path / "a.mp4"
    video.write_bytes(b"x")

    with pytest.raises(ValidationError, match="needs a user_text_input"):
        XmemlCreateRequest(
            job_id="job", video_paths=[video], task_name=TaskName.GENERIC, user_text_input=user_text_input
        )


@pytest.mark.unit
def test_request_without_videos_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        XmemlCreateRequest(job_id="job", video_paths=[], task_name=TaskName.NIF)


@pytest.mark.unit
def test_missing_video_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Video file not found"):
        XmemlCreateRequest(job_id="job", video_paths=[tmp_path / "missing.mp4"], task_name=TaskName.NIF)


@pytest.mark.unit
@pytest.mark.parametrize("filename", ["video.mxf", "video.mkv", "video"], ids=["mxf", "mkv", "no extension"])
def test_unsupported_video_format_is_rejected(tmp_path: Path, filename: str) -> None:
    video = tmp_path / filename
    video.write_bytes(b"x")

    with pytest.raises(ValidationError, match="Unsupported video format"):
        XmemlCreateRequest(job_id="job", video_paths=[video], task_name=TaskName.NIF)


@pytest.mark.unit
def test_same_file_name_in_different_folders_is_rejected(tmp_path: Path) -> None:
    """Gemini and the XMEML tell the videos apart by file name, so camera-card names like C0001.MP4 must differ."""
    videos = [tmp_path / "card_a" / "C0001.MP4", tmp_path / "card_b" / "C0001.MP4"]
    for video in videos:
        video.parent.mkdir()
        video.write_bytes(b"x")

    with pytest.raises(ValidationError, match="distinct file names.*C0001.MP4"):
        XmemlCreateRequest(job_id="job", video_paths=videos, task_name=TaskName.NIF)
