import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai.errors import ClientError

from api import APP, MESSAGES_HEADER, OUTPUT_FOLDER_HEADER
from src.models.request_input import XmemlCreateRequest
from src.models.response_output import XmemlResult


@pytest.fixture
def video_file(tmp_path: Path) -> Path:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not really a video")
    return video


def _params(video: Path | str, **extra: object) -> dict:
    """
    Query parameters for the endpoint.

    :param video: Path of the job's video.
    :param extra: Further query parameters.
    :return: Query parameters for ``/xmeml/create``.
    """
    return {"video_paths": str(video), "task_name": "nif", "user_text_input": "The bridge is closed."} | extra


def _result(warnings: list[str] | None = None) -> XmemlResult:
    return XmemlResult(
        xmeml="<xmeml/>",
        output_folder=Path("output/SchnittmAIster_nif_x"),
        warning_messages=warnings or [],
        info_messages=["Model: x"],
    )


@patch("api.generate_xmeml_from_metadata")
@patch("api.build_metadata_from_request")
def test_a_blocking_job_does_not_stall_other_requests(
    mock_build_metadata: MagicMock, mock_generate: MagicMock, tmp_path: Path
):
    """Tests that a request stuck in a blocking call (like a slow ffprobe) doesn't hold up another request."""
    blocked_video = tmp_path / "blocked.mp4"
    other_video = tmp_path / "other.mp4"
    blocked_video.write_bytes(b"x")
    other_video.write_bytes(b"x")
    blocked_job_started = threading.Event()
    release_blocked_job = threading.Event()

    def build_metadata_from_request(request: XmemlCreateRequest) -> None:
        if request.video_paths[0] == blocked_video:
            blocked_job_started.set()
            release_blocked_job.wait(timeout=10)
        raise RuntimeError("stop after building the metadata")

    mock_build_metadata.side_effect = build_metadata_from_request
    blocked_responses = []

    with TestClient(APP) as client:
        blocked_thread = threading.Thread(
            target=lambda: blocked_responses.append(client.post("/xmeml/create", params=_params(blocked_video)))
        )
        blocked_thread.start()
        try:
            assert blocked_job_started.wait(timeout=10)

            other_response = client.post("/xmeml/create", params=_params(other_video))

            # The other request is answered while the blocked one is still running
            assert other_response.status_code == 500
            assert "stop after building the metadata" in other_response.text
            assert blocked_responses == []
        finally:
            release_blocked_job.set()
            blocked_thread.join()

    assert blocked_responses[0].status_code == 500


@patch("api.generate_xmeml_from_metadata")
@patch("api.build_metadata_from_request")
def test_xmeml_is_returned_with_the_messages_header(
    mock_build_metadata: MagicMock, mock_generate: MagicMock, video_file: Path
):
    """Tests that a successful job answers with the XMEML and the job's warnings and infos in the header."""
    mock_build_metadata.return_value = (MagicMock(), MagicMock())
    mock_generate.return_value = _result(warnings=["placeholder left empty"])

    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(video_file))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.text == "<xmeml/>"
    assert json.loads(response.headers[MESSAGES_HEADER]) == ["warning: placeholder left empty", "info: Model: x"]
    assert response.headers[OUTPUT_FOLDER_HEADER] == "output/SchnittmAIster_nif_x"


@patch("api.generate_xmeml_from_metadata")
@patch("api.build_metadata_from_request")
def test_multiline_and_non_ascii_messages_stay_one_ascii_header_line(
    mock_build_metadata: MagicMock, mock_generate: MagicMock, video_file: Path
):
    """Tests that a warning with ffmpeg's multi-line output and non-Latin-1 characters cannot break the response."""
    mock_build_metadata.return_value = (MagicMock(), MagicMock())
    warning = "The preview video could not be rendered: ffmpeg failed: [in#0] /Volumes/a→b.mp4\nInvalid data"
    mock_generate.return_value = _result(warnings=[warning])

    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(video_file))

    header = response.headers[MESSAGES_HEADER]
    assert response.status_code == 200
    assert header.isascii() and "\n" not in header
    assert json.loads(header)[0] == f"warning: {warning}"


@pytest.mark.parametrize("fps_analysis", [0, 25])
@patch("api.build_metadata_from_request")
def test_fps_analysis_outside_the_range_is_rejected(
    mock_build_metadata: MagicMock, fps_analysis: int, video_file: Path
):
    """Tests that an fps override outside the allowed range is rejected with 422 before a job starts."""
    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(video_file, fps_analysis=fps_analysis))

    assert response.status_code == 422
    mock_build_metadata.assert_not_called()


@patch("api.build_metadata_from_request")
def test_unknown_media_resolution_is_rejected(mock_build_metadata: MagicMock, video_file: Path):
    """Tests that a media resolution other than low or high is rejected with 422 before a job starts."""
    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(video_file, media_resolution="medium"))

    assert response.status_code == 422
    mock_build_metadata.assert_not_called()


@pytest.mark.parametrize(("task_name", "user_text_input"), [("nif", None), ("generic", "  ")])
@patch("api.build_metadata_from_request")
def test_task_without_its_text_input_is_rejected(
    mock_build_metadata: MagicMock, task_name: str, user_text_input: str | None, video_file: Path
):
    """Tests that nif and generic without a text input are rejected with 422 before a job starts."""
    with TestClient(APP) as client:
        response = client.post(
            "/xmeml/create", params=_params(video_file, task_name=task_name, user_text_input=user_text_input)
        )

    assert response.status_code == 422
    assert "needs a user_text_input" in response.text
    mock_build_metadata.assert_not_called()


@patch("api.build_metadata_from_request")
def test_a_missing_video_file_answers_with_422(mock_build_metadata: MagicMock, tmp_path: Path):
    """Tests that a video path the request model rejects gives a 422 with the error text."""
    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(tmp_path / "missing.mp4"))

    assert response.status_code == 422
    assert "Video file not found" in response.text
    mock_build_metadata.assert_not_called()


@patch("api.build_metadata_from_request")
def test_no_video_at_all_answers_with_422(mock_build_metadata: MagicMock):
    """Tests that a request without a video path is rejected before a job starts."""
    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params={"task_name": "nif"})

    assert response.status_code == 422
    assert "video_paths" in response.text
    mock_build_metadata.assert_not_called()


@patch("api.generate_xmeml_from_metadata")
@patch("api.build_metadata_from_request")
def test_a_gemini_rate_limit_is_passed_through_as_429(
    mock_build_metadata: MagicMock, mock_generate: MagicMock, video_file: Path
):
    """Tests that a Gemini 429 answers with 429 and the retry hint."""
    mock_build_metadata.return_value = (MagicMock(), MagicMock())
    mock_generate.side_effect = ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}})

    with TestClient(APP) as client:
        response = client.post("/xmeml/create", params=_params(video_file))

    assert response.status_code == 429
    assert "try again" in response.text
