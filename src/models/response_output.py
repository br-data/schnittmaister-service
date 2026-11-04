from pathlib import Path

from pydantic import BaseModel


class XmemlResult(BaseModel):
    """
    Result of a job.

    :param xmeml: The generated XMEML document as a string.
    :param output_folder: Folder the job saved its results to: the XMEML and, if rendered, the preview video.
    :param warning_messages: Non-fatal warnings the user should be aware of.
    :param info_messages: Informational metadata about the job (e.g. model, duration).
    """

    xmeml: str
    output_folder: Path
    warning_messages: list[str]
    info_messages: list[str]
