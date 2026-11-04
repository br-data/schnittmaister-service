"""
Video analysis: Gemini sees the videos of the job in one request and proposes clips.

Entry point: ``generate_clip_proposals_from_video``.
"""

import logging

from google import genai

from src.models.gemini_output import GeminiVideoClipProposalList, VideoClipProposal
from src.models.job_metadata import JobMetadata
from src.models.video_metadata import VideoMetadataIndex
from src.services.gemini.gemini import build_video_part, generate_structured_output
from src.services.gemini.gemini_proposal_processing import transform_gemini_proposals
from src.services.prompts.builder import build_prompt


def generate_clip_proposals_from_video(
    client: genai.Client,
    video_metadata_index: VideoMetadataIndex,
    job_metadata: JobMetadata,
) -> list[VideoClipProposal]:
    """
    Generate clip proposals from the videos of the job in one Gemini request.

    The videos must be in the Files API already (see files_api); that they fit into the model's token budget
    was checked when the metadata was built.

    :param client: Gemini client.
    :param video_metadata_index: Metadata of all videos, with their Files API URIs.
    :param job_metadata: Job metadata containing general information on the job.
    :return: Validated list of clip proposals.
    :raises ClientError | ServerError | httpx.TimeoutException: If the Gemini call fails (see
        generate_structured_output).
    :raises ValueError: If a video has no Files API URI, the prompt file is missing, or Gemini returns no
        parseable response.
    """
    task_config = job_metadata.task_config
    video_filenames = video_metadata_index.keys()
    video_parts = []
    for metadata in video_metadata_index.values():
        if metadata.gemini_file_uri is None:
            raise ValueError(f"Video '{metadata.filename}' is not in the Gemini Files API")
        video_parts.append(
            build_video_part(
                metadata.gemini_file_uri, metadata.mime_type, task_config.fps_analysis, task_config.media_resolution
            )
        )

    prompt_text = build_prompt(
        video_filenames=video_filenames,
        task_config=task_config,
        user_text_input=job_metadata.user_text_input,
    )

    # With several videos, each one is preceded by its file name, so Gemini can name the source of a clip
    if len(video_parts) > 1:
        contents = []
        for i, (filename, video_part) in enumerate(zip(video_filenames, video_parts, strict=True), start=1):
            contents.append(f"Video {i}: {filename}")
            contents.append(video_part)
        contents.append(prompt_text)
    else:
        contents = [*video_parts, prompt_text]

    logging.info(
        f"Gemini API call: model={task_config.model_id_gemini}, fps={task_config.fps_analysis}, "
        f"media_resolution={task_config.media_resolution}"
    )
    response = generate_structured_output(
        client,
        contents,
        GeminiVideoClipProposalList,
        task_config.model_id_gemini,
    )
    logging.info(f"Raw Gemini response: {response.model_dump_json(indent=2)}")

    return transform_gemini_proposals(
        gemini_video_clip_proposals=response.clips,
        video_metadata_index=video_metadata_index,
        fps_analysis=task_config.fps_analysis,
        max_allowed_clip_duration_seconds=task_config.max_allowed_clip_duration_seconds,
    )
