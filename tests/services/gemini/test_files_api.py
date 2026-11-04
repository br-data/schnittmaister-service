"""Tests for the Files API handling: waiting for processing, metadata, cleanup."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google.genai.types import File, FileState

from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.gemini.files_api import delete_files, upload_videos


def _file(state: FileState, name: str = "files/abc") -> File:
    return File(
        name=name,
        uri=f"https://generativelanguage.googleapis.com/v1beta/{name}",
        mime_type="video/mp4",
        state=state,
    )


def _metadata(tmp_path: Path) -> VideoMetadata:
    return VideoMetadata(
        file_nr=0,
        filename="video.mp4",
        local_path=tmp_path / "video.mp4",
        duration_seconds=10.0,
        duration_frames=250,
        xmeml_pathurl="file://localhost/video.mp4",
    )


@pytest.mark.unit
@patch("src.services.gemini.files_api.time.sleep")
def test_video_is_uploaded_and_waited_for(mock_sleep: MagicMock, tmp_path: Path) -> None:
    """An uploaded video is polled until ACTIVE; its name and URI land on the metadata."""
    client = MagicMock()
    client.files.upload.return_value = _file(FileState.PROCESSING)
    client.files.get.side_effect = [_file(FileState.PROCESSING), _file(FileState.ACTIVE)]
    metadata = _metadata(tmp_path)

    upload_videos(client, VideoMetadataIndex.from_list([metadata]))

    assert metadata.gemini_file_name == "files/abc"
    assert metadata.gemini_file_uri == "https://generativelanguage.googleapis.com/v1beta/files/abc"
    assert metadata.mime_type == "video/mp4"
    assert client.files.get.call_count == 2
    client.files.upload.assert_called_once_with(file=tmp_path / "video.mp4", config={"display_name": "video.mp4"})


@pytest.mark.unit
def test_failed_processing_raises(tmp_path: Path) -> None:
    """A file the Files API could not process fails the job with the API's reason."""
    client = MagicMock()
    failed = _file(FileState.FAILED)
    failed.error = MagicMock(message="unsupported codec")
    client.files.upload.return_value = failed

    metadata = _metadata(tmp_path)

    with pytest.raises(ValueError, match="unsupported codec"):
        upload_videos(client, VideoMetadataIndex.from_list([metadata]))

    # The name is kept, so the cleanup deletes the failed upload too
    assert metadata.gemini_file_name == "files/abc"


@pytest.mark.unit
@patch("src.services.gemini.files_api.time.sleep")
@patch("src.services.gemini.files_api.GEMINI_CONFIG")
def test_processing_timeout_raises(mock_config: MagicMock, mock_sleep: MagicMock, tmp_path: Path) -> None:
    """A file that stays in PROCESSING longer than configured fails the job."""
    mock_config.file_processing_timeout_seconds = 0
    mock_config.file_processing_poll_seconds = 0
    client = MagicMock()
    client.files.upload.return_value = _file(FileState.PROCESSING)
    client.files.get.return_value = _file(FileState.PROCESSING)

    with pytest.raises(TimeoutError):
        upload_videos(client, VideoMetadataIndex.from_list([_metadata(tmp_path)]))


@pytest.mark.unit
@patch("src.services.gemini.files_api.time.sleep")
def test_all_videos_are_uploaded_before_waiting(mock_sleep: MagicMock) -> None:
    """Every video is uploaded before the first is polled, so Gemini processes them while the rest upload."""
    client = MagicMock()
    client.files.upload.side_effect = [_file(FileState.PROCESSING, "files/a"), _file(FileState.PROCESSING, "files/b")]
    client.files.get.side_effect = [_file(FileState.ACTIVE, "files/a"), _file(FileState.ACTIVE, "files/b")]
    videos = [_named_metadata("a.mp4", None), _named_metadata("b.mp4", None)]

    upload_videos(client, VideoMetadataIndex.from_list(videos))

    calls = [c[0] for c in client.files.method_calls]
    assert calls == ["upload", "upload", "get", "get"]
    assert [v.gemini_file_uri for v in videos] == [
        "https://generativelanguage.googleapis.com/v1beta/files/a",
        "https://generativelanguage.googleapis.com/v1beta/files/b",
    ]


@pytest.mark.unit
def test_failed_processing_keeps_names_of_all_uploads() -> None:
    """If the first video fails processing, the later ones are already uploaded and named for the cleanup."""
    client = MagicMock()
    failed = _file(FileState.FAILED, "files/a")
    failed.error = MagicMock(message="unsupported codec")
    client.files.upload.side_effect = [failed, _file(FileState.PROCESSING, "files/b")]
    videos = [_named_metadata("a.mp4", None), _named_metadata("b.mp4", None)]

    with pytest.raises(ValueError, match="unsupported codec"):
        upload_videos(client, VideoMetadataIndex.from_list(videos))

    assert [v.gemini_file_name for v in videos] == ["files/a", "files/b"]


@pytest.mark.unit
def test_failed_deletion_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    """A deletion that fails only logs a warning; the file expires on its own."""
    client = MagicMock()
    client.files.delete.side_effect = [RuntimeError("gone"), None]
    videos = [
        _named_metadata(f"{name}.mp4", gemini_file_name)
        for name, gemini_file_name in [("a", "files/a"), ("b", "files/b"), ("c", None)]
    ]

    delete_files(client, VideoMetadataIndex.from_list(videos))

    assert [c.kwargs["name"] for c in client.files.delete.call_args_list] == ["files/a", "files/b"]
    assert "Could not delete 'files/a'" in caplog.text


def _named_metadata(filename: str, gemini_file_name: str | None) -> VideoMetadata:
    return VideoMetadata(
        file_nr=0,
        filename=filename,
        local_path=Path(filename),
        duration_seconds=10.0,
        duration_frames=250,
        xmeml_pathurl=f"file://localhost/{filename}",
        gemini_file_name=gemini_file_name,
    )
