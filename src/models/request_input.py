from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from src.config.gemini_models import GeminiModel, MediaResolution
from src.config.task_config import TASKS_CONFIG, TaskName
from src.config.video_format_config import GEMINI_SUPPORTED_VIDEO_EXTENSIONS


def check_video_path(path: Path) -> Path:
    """
    Check that a path points to an existing video file in a format Gemini reads.

    :param path: The field value.
    :raises ValueError: If the file does not exist or its extension is not in GEMINI_SUPPORTED_VIDEO_EXTENSIONS.
    :return: The unchanged path.
    """
    if not path.is_file():
        raise ValueError(f"Video file not found: {path}")
    if path.suffix.lower() not in GEMINI_SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(
            f"Unsupported video format {path.suffix!r}: {path}. "
            f"Gemini reads {sorted(GEMINI_SUPPORTED_VIDEO_EXTENSIONS)}; convert other formats first, e.g. with ffmpeg."
        )
    return path


VideoPath = Annotated[Path, AfterValidator(check_video_path)]
"""Path of an existing local video file in a format Gemini reads."""


class XmemlCreateRequest(BaseModel):
    """
    Request to create an XMEML from one or more local videos.

    :param job_id: Identifier of the job, created by the endpoint
    :param video_paths: Local paths of the videos, at least one, with distinct file names (Gemini and the
        XMEML tell the videos apart by name); the service probes them and uploads them to Gemini
    :param task_name: Task to perform
    :param gemini_model: Gemini model to use (overrides the task default if set)
    :param fps_analysis: Frames per second Gemini samples (overrides the task default if set)
    :param media_resolution: Resolution at which Gemini tokenizes each frame (overrides the task
        default if set)
    :param user_text_input: Text input for the prompt (voice-over text for NiF, the task description of the
        generic task); required for the tasks that need one
    :param render_preview: Whether to render a preview video of the cut next to the XMEML (default True)
    """

    job_id: str
    video_paths: list[VideoPath] = Field(min_length=1)
    task_name: TaskName
    gemini_model: GeminiModel | None = None
    fps_analysis: int | None = None
    media_resolution: MediaResolution | None = None
    user_text_input: str | None = None
    render_preview: bool = True

    @field_validator("video_paths")
    @classmethod
    def _check_distinct_file_names(cls, video_paths: list[Path]) -> list[Path]:
        """
        Reject videos with the same file name from different folders, as camera cards often have.

        :param video_paths: The validated paths.
        :raises ValueError: If two paths share a file name.
        :return: The unchanged paths.
        """
        names = [path.name for path in video_paths]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                f"Videos must have distinct file names, these occur more than once: {', '.join(duplicates)}. "
                f"Rename the files."
            )
        return video_paths

    @model_validator(mode="after")
    def _check_user_text_input(self) -> "XmemlCreateRequest":
        """
        Reject a request without user_text_input for a task whose prompt needs one, before anything is uploaded.

        :raises ValueError: If the task needs a text input and it is missing or blank.
        :return: The unchanged request.
        """
        if TASKS_CONFIG[self.task_name].needs_user_text_input and not (self.user_text_input or "").strip():
            raise ValueError(
                f"The task {self.task_name} needs a user_text_input: the voice-over script for nif, the task "
                f"description for generic."
            )
        return self
