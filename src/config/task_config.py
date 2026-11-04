from enum import StrEnum

from pydantic import BaseModel, Field

from src.config.gemini_models import GeminiModel, MediaResolution

# Range of fps_analysis; Gemini samples at most 24 frames per second
FPS_ANALYSIS_MIN = 1
FPS_ANALYSIS_MAX = 24


class TaskName(StrEnum):
    """The tasks the service offers; each one has a prompt file in ``prompts/``."""

    SCENE_DETECTION = "scene_detection"
    NIF = "nif"
    GENERIC = "generic"


class TaskConfig(BaseModel):
    """
    Configuration of a task.

    :param name: Name of the task, as chosen in a request; also names the XMEML sequence.
    :param prompt_file: File name of the task's prompt template in ``prompts/``.
    :param needs_user_text_input: Whether a request must bring a user_text_input, which the prompt template
        takes in its {{user_text_input}} placeholder.
    :param model_id_gemini: Gemini model ID. Defaults to gemini-3.8-flash.
    :param max_allowed_clip_duration_seconds: Maximum clip duration in seconds. None means no limit.
    :param fps_analysis: Frames per second Gemini samples from the video, FPS_ANALYSIS_MIN to
        FPS_ANALYSIS_MAX. Defaults to 1. Higher values see more detail but shorten the maximum video
        length (see ModelTokenLimits).
    :param media_resolution: Resolution at which Gemini tokenizes each sampled frame. Defaults to low; high
        costs about four times the tokens per frame and shortens the maximum video length accordingly.
    """

    name: TaskName
    prompt_file: str = Field(min_length=1)
    needs_user_text_input: bool = False
    model_id_gemini: GeminiModel = GeminiModel.gemini_3_8_flash
    max_allowed_clip_duration_seconds: float | None = None
    fps_analysis: int = Field(default=1, ge=FPS_ANALYSIS_MIN, le=FPS_ANALYSIS_MAX)
    media_resolution: MediaResolution = MediaResolution.LOW

    def with_overrides(self, **overrides: object) -> "TaskConfig":
        """
        Return a copy with the given fields replaced, validated like a new task config.

        :param overrides: Field values to replace.
        :raises pydantic.ValidationError: If the resulting config is invalid.
        :return: New TaskConfig with the overrides applied.
        """
        return TaskConfig.model_validate(self.model_dump() | overrides)


# The tasks by name; every TaskName has exactly one config
TASKS_CONFIG: dict[TaskName, TaskConfig] = {
    config.name: config
    for config in [
        TaskConfig(
            name=TaskName.SCENE_DETECTION,
            prompt_file="scene_detection.md",
        ),
        TaskConfig(
            name=TaskName.NIF,
            prompt_file="nif.md",
            needs_user_text_input=True,
            max_allowed_clip_duration_seconds=60.0,
            fps_analysis=2,
        ),
        TaskConfig(
            name=TaskName.GENERIC,
            prompt_file="generic.md",
            needs_user_text_input=True,
        ),
    ]
}
