import logging
import time
from pathlib import Path

from src.models.job_metadata import JobMetadata
from src.models.response_output import XmemlResult
from src.models.token_usage import TokenUsage, current_token_usage
from src.models.user_messages import UserMessages, add_user_info, add_user_warning, current_user_messages
from src.models.video_metadata import VideoMetadataIndex
from src.services.analysis.video_analysis import generate_clip_proposals_from_video
from src.services.gemini.files_api import delete_files, upload_videos
from src.services.gemini.gemini import get_client
from src.services.media.preview_render import render_preview
from src.services.xmeml.xmeml_builder import XmemlBuilder
from src.utils.xml_utils import generate_timestamped_sequence_name

# Every job saves its results to a subfolder named like the sequence; relative to the repository root the
# service runs in
OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def generate_xmeml_from_metadata(
    job_metadata: JobMetadata,
    video_metadata_index: VideoMetadataIndex,
) -> XmemlResult:
    """
    Generate the XMEML of a job: upload the videos to Gemini, get clip proposals, build the document.

    The XMEML and, if requested, a preview video of the cut are saved to ``output/<sequence name>/``. A
    preview that fails to render is a warning, not a job failure. The uploaded videos are deleted from the
    Files API at the end, also on failure.

    Initializes two context-bound collectors so functions deeper in the call stack can record results
    without threading return values: ``UserMessages`` (warnings and infos for the response) and
    ``TokenUsage`` (Gemini token counts for the log).

    Errors are raised; the caller turns them into the error response.

    :param job_metadata: Job configuration with the task config, the text input and the preview setting.
    :param video_metadata_index: Videos of the job with their metadata.
    :raises ValueError: If GEMINI_API_KEY is not set or a video cannot be processed.
    :raises Exception: Any other error of the upload or the analysis, see upload_videos and
        generate_clip_proposals_from_video.
    :return: XmemlResult with the XMEML and the collected user messages.
    """
    logging.info(f"Starting XMEML generation for job {job_metadata.job_id}")

    # Job-scoped collectors, accessible via context vars throughout the call stack
    user_messages = UserMessages()
    token_usage = TokenUsage()
    user_messages_token = current_user_messages.set(user_messages)
    token_usage_token = current_token_usage.set(token_usage)

    start_time = time.monotonic()
    client = get_client()

    try:
        add_user_info(f"Model: {job_metadata.task_config.model_id_gemini}")
        add_user_info(f"Task: {job_metadata.task_config.name}")

        upload_videos(client, video_metadata_index)

        video_clip_proposals = generate_clip_proposals_from_video(
            client=client,
            video_metadata_index=video_metadata_index,
            job_metadata=job_metadata,
        )
        if not video_clip_proposals:
            add_user_info("No clips to place; the sequence is empty.")

        sequence_name = generate_timestamped_sequence_name(job_metadata.task_config.name, job_metadata.job_id)
        xmeml_str = XmemlBuilder(
            video_metadata_index=video_metadata_index,
            video_clip_proposals=video_clip_proposals,
            sequence_name=sequence_name,
        ).build_xmeml_string()

        output_folder = OUTPUT_DIR / sequence_name
        output_folder.mkdir(parents=True, exist_ok=True)
        xmeml_path = output_folder / f"{sequence_name}.xml"
        xmeml_path.write_text(xmeml_str, encoding="utf-8")
        logging.info(f"XMEML with {len(video_clip_proposals)} clip(s) written to {xmeml_path}")
        if job_metadata.render_preview and video_clip_proposals:
            try:
                render_preview(video_clip_proposals, video_metadata_index, output_folder / f"{sequence_name}.mp4")
            except RuntimeError as e:
                add_user_warning(f"The preview video could not be rendered, the XMEML is complete: {e}")

        elapsed = time.monotonic() - start_time
        minutes, seconds = divmod(int(elapsed), 60)
        add_user_info(f"Duration: {minutes}m {seconds:02d}s")
        # Gemini bills thinking as output tokens
        logging.info(
            f"Gemini usage of job {job_metadata.job_id}: {token_usage.gemini_call_count} call(s), "
            f"{token_usage.prompt_tokens} input tokens, "
            f"{token_usage.output_tokens + token_usage.thinking_tokens} output tokens "
            f"({token_usage.thinking_tokens} of them thinking), {token_usage.total_tokens} in total"
        )

        logging.info(f"Job {job_metadata.job_id} done, results in {output_folder.resolve()}")
        return XmemlResult(
            xmeml=xmeml_str,
            output_folder=output_folder,
            warning_messages=user_messages.warnings,
            info_messages=user_messages.infos,
        )

    finally:
        delete_files(client, video_metadata_index)
        current_token_usage.reset(token_usage_token)
        current_user_messages.reset(user_messages_token)
