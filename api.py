import json
import logging
import shutil
import uuid
from pathlib import Path

import uvicorn
from fastapi import Query, Response

from src.config.app_config import APP, HOST, PORT
from src.config.gemini_config import get_gemini_config
from src.config.gemini_models import GeminiModel, MediaResolution
from src.config.logging_config import LOGGING_CONFIG
from src.config.task_config import FPS_ANALYSIS_MAX, FPS_ANALYSIS_MIN, TaskName
from src.models.errors import http_status_and_message
from src.models.request_input import XmemlCreateRequest
from src.services.metadata.metadata_preparation import build_metadata_from_request
from src.services.xmeml_generation import generate_xmeml_from_metadata

# Response headers with the job's warnings and infos (a JSON array, see create_xmeml), and the folder the
# results were saved to
MESSAGES_HEADER = "X-Job-Messages"
OUTPUT_FOLDER_HEADER = "X-Output-Folder"


@APP.get("/", include_in_schema=False)
async def redirect() -> Response:
    """Redirect to the interactive documentation if the index page is called."""
    return Response(status_code=307, headers={"Location": "/docs"})


# def, not async def: FastAPI runs it in its thread pool, so a job's blocking steps don't stall other requests
@APP.post("/xmeml/create", response_class=Response)
def create_xmeml(
    video_paths: list[Path] = Query(  # noqa: B008
        ...,
        description=(
            "Local paths of the videos, in a format Gemini reads (e.g. MP4, MOV, WebM). "
            "The service probes them with ffprobe and uploads them to the Gemini Files API. "
            "The XMEML references the videos at these paths, so the editor links them on import."
        ),
        examples=["/Users/me/videos/interview.mp4"],
    ),
    task_name: TaskName = Query(  # noqa: B008
        ...,
        description="Task - determines the prompt, the model and the sampling rate",
    ),
    user_text_input: str | None = Query(  # noqa: B008
        None,
        description=(
            "Text input for the prompt: the voice-over text for nif, the task description for generic "
            "(e.g. 'Make a 2-minute trailer'). Ignored by scene_detection."
        ),
    ),
    gemini_model: GeminiModel | None = Query(  # noqa: B008
        None,
        description=(
            "Gemini model to use. If not set, uses the default model of the selected task "
            "(gemini-3.8-flash). The Flash models run in the free tier; gemini-3.1-pro-preview and "
            "gemini-4-argon need billing enabled for the API key."
        ),
    ),
    fps_analysis: int | None = Query(  # noqa: B008
        None,
        ge=FPS_ANALYSIS_MIN,
        le=FPS_ANALYSIS_MAX,
        description=(
            f"Frames per second Gemini samples from the video ({FPS_ANALYSIS_MIN} to {FPS_ANALYSIS_MAX}). "
            "If not set, uses the default of the selected task (1, nif 2). Every step up costs tokens for "
            "one more frame per second of video and shortens the maximum video length. Keep the default "
            "unless the result misses fast action."
        ),
    ),
    media_resolution: MediaResolution | None = Query(  # noqa: B008
        None,
        description=(
            "Resolution at which Gemini reads each sampled frame. If not set, uses the default of the "
            "selected task (low). high reads small text and details but costs about four times the "
            "tokens per frame and shortens the maximum video length to about a third. Keep the default "
            "unless the result misses details in the picture."
        ),
    ),
    render_preview: bool = Query(  # noqa: B008
        True,
        description=(
            "Render a preview video of the cut with ffmpeg. The XMEML and the preview are saved to "
            "output/<sequence name>/ in the repository; the response header X-Output-Folder names it."
        ),
    ),
) -> Response:
    """
    Generate an XMEML from videos and task parameters.

    :return: The XMEML with content type "application/xml", the result folder in the X-Output-Folder header
        and the job's messages as a JSON array in the X-Job-Messages header, or an error response with the error
        message as text.
    """
    # Each request is a new job
    job_id = str(uuid.uuid4())

    try:
        # The request model validates the videos and the combination of parameters
        input_data = XmemlCreateRequest(
            video_paths=video_paths,
            task_name=task_name,
            gemini_model=gemini_model,
            fps_analysis=fps_analysis,
            media_resolution=media_resolution,
            user_text_input=user_text_input,
            render_preview=render_preview,
            job_id=job_id,
        )
        logging.info(f"Endpoint '/xmeml/create' received input: {input_data.model_dump(exclude={'user_text_input'})}")

        job_metadata, video_metadata_index = build_metadata_from_request(input_data)
        result = generate_xmeml_from_metadata(
            job_metadata=job_metadata,
            video_metadata_index=video_metadata_index,
        )

        messages = [f"warning: {w}" for w in result.warning_messages] + [f"info: {i}" for i in result.info_messages]
        headers = {OUTPUT_FOLDER_HEADER: str(result.output_folder)}
        if messages:
            # JSON escapes line breaks and non-ASCII characters (e.g. in ffmpeg's error output), which a header
            # value must not contain; json.loads gives the messages back
            headers[MESSAGES_HEADER] = json.dumps(messages)
        return Response(content=result.xmeml, media_type="application/xml", headers=headers)

    except Exception as e:
        # The status code and message depend on what failed, see http_status_and_message
        status_code, message = http_status_and_message(e)
        if status_code == 500:
            # An unexpected error: the message sends the user to the log, so it gets the traceback
            logging.exception(f"Job {job_id} failed with {status_code}: {type(e).__name__}: {e}")
        else:
            logging.error(f"Job {job_id} failed with {status_code}: {type(e).__name__}: {e}")
        return Response(content=message, status_code=status_code, media_type="text/plain")


if __name__ == "__main__":
    # Every job probes, cuts and renders with ffmpeg; without it the service would fail on the first request
    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing_tools:
        raise SystemExit(f"{' and '.join(missing_tools)} not found on the PATH; install ffmpeg, see README.md")
    # Every job calls Gemini
    if not get_gemini_config().api_key:
        raise SystemExit("GEMINI_API_KEY is not set; put your key into .env, see README.md")
    uvicorn.run(APP, host=HOST, port=PORT, log_config=LOGGING_CONFIG)
