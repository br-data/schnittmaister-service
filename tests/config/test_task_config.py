"""Tests for the task configuration."""

import pytest
from pydantic import ValidationError

from src.config.task_config import TASKS_CONFIG, TaskConfig, TaskName
from src.services.prompts.builder import PROMPTS_DIR


@pytest.mark.unit
@pytest.mark.parametrize("task_name", list(TaskName))
def test_every_task_is_configured_with_a_prompt_file(task_name: TaskName) -> None:
    """Every task in the enum has a config under its own name, and its prompt file exists."""
    assert TASKS_CONFIG[task_name].name == task_name
    assert (PROMPTS_DIR / TASKS_CONFIG[task_name].prompt_file).is_file()


@pytest.mark.unit
@pytest.mark.parametrize(
    "settings",
    [{"fps_analysis": 0}, {"fps_analysis": 25}, {"prompt_file": ""}],
    ids=["fps 0", "fps 25", "empty prompt file"],
)
def test_invalid_task_config_is_rejected(settings: dict) -> None:
    with pytest.raises(ValidationError):
        TaskConfig.model_validate({"name": TaskName.GENERIC, "prompt_file": "test.md"} | settings)


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [{"fps_analysis": 30}, {"model_id_gemini": "gemini-unknown"}],
    ids=["fps above 24", "unknown model"],
)
def test_invalid_overrides_are_rejected(overrides: dict) -> None:
    """Overrides from a request are validated like a new task config."""
    with pytest.raises(ValidationError):
        TASKS_CONFIG[TaskName.NIF].with_overrides(**overrides)


@pytest.mark.unit
def test_overrides_keep_all_other_fields() -> None:
    """An override replaces only the given fields; all other settings stay."""
    base = TASKS_CONFIG[TaskName.NIF]

    task_config = base.with_overrides(fps_analysis=3)

    assert task_config.fps_analysis == 3
    assert task_config.model_dump() == base.model_dump() | {"fps_analysis": 3}


@pytest.mark.unit
def test_model_id_reads_as_the_model_name() -> None:
    """The model ID reads as the plain model name in f-strings, as used in user infos, logs and the Gemini SDK."""
    task_config = TASKS_CONFIG[TaskName.NIF].with_overrides(model_id_gemini="gemini-3.6-flash")

    assert f"{task_config.model_id_gemini}" == "gemini-3.6-flash"
