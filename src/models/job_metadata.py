from pydantic import BaseModel

from src.config.task_config import TaskConfig


class JobMetadata(BaseModel):
    """
    Metadata of a job.

    :param job_id: A unique identifier for the job.
    :param task_config: Configuration of the task to perform, with the request's overrides applied.
    :param user_text_input: User-provided text input for the prompt (e.g. voice-over text, the task
        description of the generic task).
    :param render_preview: Whether to render a preview video of the cut next to the XMEML.
    """

    job_id: str
    task_config: TaskConfig
    user_text_input: str | None = None
    render_preview: bool = True
