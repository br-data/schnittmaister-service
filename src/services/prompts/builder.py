import logging
import re
from pathlib import Path

from src.config.task_config import TaskConfig
from src.models.user_messages import add_user_warning

# The prompt templates live next to the code, one file per task plus the shared output instructions
PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
OUTPUT_FORMAT_FILE = "output_format.md"

VIDEO_FILENAMES_PLACEHOLDER = "{{video_filenames}}"
USER_TEXT_INPUT_PLACEHOLDER = "{{user_text_input}}"


def build_prompt(
    video_filenames: list[str],
    task_config: TaskConfig,
    user_text_input: str | None = None,
) -> str:
    """
    Build the Gemini prompt of a task from its template file and the shared output instructions.

    The template of the task comes first, then the output format and timestamp rules, which are the same
    for every task. Fills the placeholders for the video file names and the user's text input; a template
    without the file name placeholder gets the file names appended.

    :param video_filenames: A list of video file names in the order of video data input.
    :param task_config: The task configuration; its prompt_file selects the template.
    :param user_text_input: Optional user-provided text input for the prompt (e.g., voice-over text, task
        description).
    :raises ValueError: If a prompt file is missing.
    :return: A formatted prompt string including video name references.
    """
    logging.info(f"Building prompt from {task_config.prompt_file}")
    task_template = _read_prompt_file(task_config.prompt_file).strip()
    output_format = _read_prompt_file(OUTPUT_FORMAT_FILE).strip()
    prompt = f"{task_template}\n\n{output_format}\n"

    if not video_filenames:
        logging.warning("No video filenames provided for prompt generation.")

    # Join the filenames of the videos into a string representing an ordered list
    video_filenames_joined = "\n".join(f"Video {i + 1}: {name}" for i, name in enumerate(video_filenames))

    # Replace video filenames placeholder or append manually as fallback
    if VIDEO_FILENAMES_PLACEHOLDER in prompt:
        prompt = prompt.replace(VIDEO_FILENAMES_PLACEHOLDER, video_filenames_joined)
    else:
        logging.warning(
            f"Prompt template is missing '{VIDEO_FILENAMES_PLACEHOLDER}'. "
            "Appending video filenames at the end of the prompt."
        )
        prompt = (
            f"{prompt.strip()}\n\n"
            f"# Use the following file names to reference the video a clip comes from in the "
            f'"source_filename" field. Always use the exact spelling of the file name.\n{video_filenames_joined}'
        )

    # Replace the user text input placeholder (if present in prompt)
    if USER_TEXT_INPUT_PLACEHOLDER in prompt:
        if user_text_input:
            prompt = prompt.replace(USER_TEXT_INPUT_PLACEHOLDER, user_text_input.strip())
            logging.info(f"Replaced '{USER_TEXT_INPUT_PLACEHOLDER}' with user-provided text input.")
        else:
            add_user_warning(
                f"The prompt of this task expects a text input ('{USER_TEXT_INPUT_PLACEHOLDER}') "
                f"but user_text_input was not given; the placeholder is left empty."
            )
            prompt = prompt.replace(USER_TEXT_INPUT_PLACEHOLDER, "")

    # Warn about any unreplaced placeholders remaining in the prompt
    unreplaced = re.findall(r"\{\{(.+?)\}\}", prompt)
    if unreplaced:
        placeholder_list = ", ".join("{{" + p + "}}" for p in unreplaced)
        add_user_warning(f"Prompt {task_config.prompt_file} contains unreplaced placeholders: {placeholder_list}")

    return prompt


def _read_prompt_file(file_name: str) -> str:
    """
    Read a prompt template from the prompts directory.

    :param file_name: File name within PROMPTS_DIR.
    :raises ValueError: If the file does not exist.
    :return: The file content.
    """
    path = PROMPTS_DIR / file_name
    if not path.is_file():
        raise ValueError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
