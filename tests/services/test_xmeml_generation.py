"""Tests for the job frame of the orchestrator: Files API upload and cleanup, saved results, preview, result."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config.task_config import TASKS_CONFIG, TaskName
from src.models.gemini_output import VideoClipProposal
from src.models.job_metadata import JobMetadata
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.xmeml_generation import generate_xmeml_from_metadata

MODULE = "src.services.xmeml_generation"


def _video_metadata_index() -> VideoMetadataIndex:
    return VideoMetadataIndex.from_list(
        [
            VideoMetadata(
                file_nr=0,
                filename="video.mp4",
                local_path=Path("video.mp4"),
                xmeml_pathurl="file://localhost/video.mp4",
                duration_frames=2500,
                duration_seconds=100.0,
            )
        ]
    )


def _job_metadata(render_preview: bool = True) -> JobMetadata:
    return JobMetadata(job_id="job-42", task_config=TASKS_CONFIG[TaskName.NIF], render_preview=render_preview)


def _clip() -> VideoClipProposal:
    return VideoClipProposal(source_filename="video.mp4", in_frame=0, out_frame=100, label="clip")


@pytest.fixture(autouse=True)
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Save the results of the tests to a temporary folder instead of the repository's output folder."""
    monkeypatch.setattr(f"{MODULE}.OUTPUT_DIR", tmp_path)
    return tmp_path


@pytest.mark.unit
@patch(f"{MODULE}.get_client")
@patch(f"{MODULE}.delete_files")
@patch(f"{MODULE}.upload_videos")
class TestJobFrame:
    @patch(f"{MODULE}.generate_clip_proposals_from_video", return_value=[])
    def test_result_holds_the_xmeml_and_the_messages(
        self, mock_proposals: MagicMock, mock_upload: MagicMock, mock_delete: MagicMock, mock_client: MagicMock
    ):
        """Tests that the built XMEML and the collected infos end up in the result."""
        result = generate_xmeml_from_metadata(_job_metadata(), _video_metadata_index())

        assert result.xmeml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert "SchnittmAIster_nif_" in result.xmeml
        assert result.warning_messages == []
        assert any(info.startswith("Model: ") for info in result.info_messages)
        assert any(info.startswith("Duration: ") for info in result.info_messages)

    @patch(f"{MODULE}.generate_clip_proposals_from_video", return_value=[])
    def test_uploaded_files_are_deleted_after_the_job(
        self, mock_proposals: MagicMock, mock_upload: MagicMock, mock_delete: MagicMock, mock_client: MagicMock
    ):
        """Tests that the files this job uploaded are deleted from the Files API at the end."""
        video_metadata_index = _video_metadata_index()
        generate_xmeml_from_metadata(_job_metadata(), video_metadata_index)

        mock_delete.assert_called_once_with(mock_client.return_value, video_metadata_index)

    @patch(f"{MODULE}.generate_clip_proposals_from_video", side_effect=RuntimeError("Gemini down"))
    def test_uploaded_files_are_deleted_on_failure(
        self, mock_proposals: MagicMock, mock_upload: MagicMock, mock_delete: MagicMock, mock_client: MagicMock
    ):
        """Tests that a failed analysis still deletes the uploaded files and raises the error."""
        video_metadata_index = _video_metadata_index()
        with pytest.raises(RuntimeError, match="Gemini down"):
            generate_xmeml_from_metadata(_job_metadata(), video_metadata_index)

        mock_delete.assert_called_once_with(mock_client.return_value, video_metadata_index)


@pytest.mark.unit
@patch(f"{MODULE}.get_client")
@patch(f"{MODULE}.delete_files")
@patch(f"{MODULE}.upload_videos")
@patch(f"{MODULE}.generate_clip_proposals_from_video", return_value=[_clip()])
@patch(f"{MODULE}.render_preview")
class TestSavedResults:
    def test_xmeml_and_preview_are_saved_to_a_folder_named_like_the_sequence(
        self,
        mock_render: MagicMock,
        mock_proposals: MagicMock,
        mock_upload: MagicMock,
        mock_delete: MagicMock,
        mock_client: MagicMock,
        output_dir: Path,
    ):
        """Tests that the folder, the XMEML and the preview path share the sequence name."""
        result = generate_xmeml_from_metadata(_job_metadata(), _video_metadata_index())

        folder = result.output_folder
        assert folder.parent == output_dir
        assert folder.name.startswith("SchnittmAIster_nif_")
        assert folder.name.endswith("_job-42"), "the start of the job ID keeps parallel jobs apart"
        assert (folder / f"{folder.name}.xml").read_text(encoding="utf-8") == result.xmeml
        assert mock_render.call_args.args[2] == folder / f"{folder.name}.mp4"

    def test_preview_is_skipped_when_not_requested(
        self,
        mock_render: MagicMock,
        mock_proposals: MagicMock,
        mock_upload: MagicMock,
        mock_delete: MagicMock,
        mock_client: MagicMock,
    ):
        result = generate_xmeml_from_metadata(_job_metadata(render_preview=False), _video_metadata_index())

        mock_render.assert_not_called()
        assert (result.output_folder / f"{result.output_folder.name}.xml").is_file()

    def test_failed_preview_is_a_warning_not_a_failure(
        self,
        mock_render: MagicMock,
        mock_proposals: MagicMock,
        mock_upload: MagicMock,
        mock_delete: MagicMock,
        mock_client: MagicMock,
    ):
        mock_render.side_effect = RuntimeError("ffmpeg failed: boom")

        result = generate_xmeml_from_metadata(_job_metadata(), _video_metadata_index())

        assert result.xmeml.startswith("<?xml")
        assert any("preview video could not be rendered" in w and "boom" in w for w in result.warning_messages)
