from pathlib import Path

import pytest

from src.config.task_config import TASKS_CONFIG, TaskConfig, TaskName
from src.models.user_messages import UserMessages, current_user_messages
from src.services.prompts import builder
from src.services.prompts.builder import build_prompt

OUTPUT_FORMAT = "Output: {{video_filenames}}"


@pytest.fixture
def prompts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A prompts directory with the shared output format, into which tests write their task template."""
    (tmp_path / builder.OUTPUT_FORMAT_FILE).write_text(OUTPUT_FORMAT)
    monkeypatch.setattr(builder, "PROMPTS_DIR", tmp_path)
    return tmp_path


def _task(prompts_dir: Path, template: str) -> TaskConfig:
    (prompts_dir / "task.md").write_text(template)
    return TaskConfig(name=TaskName.GENERIC, prompt_file="task.md")


class TestBuildPromptComposition:
    def test_task_template_comes_before_the_output_format(self, prompts_dir: Path):
        result = build_prompt(video_filenames=["clip.mp4"], task_config=_task(prompts_dir, "Task text"))

        assert result == "Task text\n\nOutput: Video 1: clip.mp4\n"

    def test_missing_prompt_file_fails(self, prompts_dir: Path):
        with pytest.raises(ValueError, match="Prompt file not found"):
            build_prompt(
                video_filenames=["clip.mp4"], task_config=TaskConfig(name=TaskName.GENERIC, prompt_file="missing.md")
            )

    def test_real_prompt_files_build_for_every_task(self):
        """The prompt files in the repository compose without leftovers for the tasks that take no text input."""
        result = build_prompt(video_filenames=["clip.mp4"], task_config=TASKS_CONFIG[TaskName.SCENE_DETECTION])

        assert "Video 1: clip.mp4" in result
        assert "{{" not in result


class TestBuildPromptPlaceholderReplacement:
    def test_replaces_video_filenames_placeholder(self, prompts_dir: Path):
        result = build_prompt(
            video_filenames=["clip1.mp4", "clip2.mp4"],
            task_config=_task(prompts_dir, "Analyse: {{video_filenames}}"),
        )
        assert "Analyse: Video 1: clip1.mp4\nVideo 2: clip2.mp4" in result
        assert "{{video_filenames}}" not in result

    def test_replaces_user_text_input_placeholder(self, prompts_dir: Path):
        result = build_prompt(
            video_filenames=["clip.mp4"],
            task_config=_task(prompts_dir, "Script: {{user_text_input}}"),
            user_text_input="Parliament decides today.",
        )
        assert "Script: Parliament decides today." in result
        assert "{{user_text_input}}" not in result

    def test_user_text_input_replaced_with_empty_and_warned_when_no_input(self, prompts_dir: Path):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            result = build_prompt(
                video_filenames=["clip.mp4"],
                task_config=_task(prompts_dir, "Text: {{user_text_input}}"),
                user_text_input=None,
            )
        finally:
            current_user_messages.reset(token)

        assert "{{user_text_input}}" not in result
        assert len(messages.warnings) == 1
        assert "user_text_input was not given" in messages.warnings[0]


class TestBuildPromptUnreplacedPlaceholderWarning:
    def test_unreplaced_placeholders_are_collected_as_a_user_warning(self, prompts_dir: Path):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            build_prompt(video_filenames=["clip.mp4"], task_config=_task(prompts_dir, "{{foo}} and {{bar}}"))
        finally:
            current_user_messages.reset(token)

        assert len(messages.warnings) == 1
        assert "{{foo}}" in messages.warnings[0]
        assert "{{bar}}" in messages.warnings[0]
        assert "task.md" in messages.warnings[0]

    def test_no_warning_when_all_placeholders_replaced(self, prompts_dir: Path):
        messages = UserMessages()
        token = current_user_messages.set(messages)
        try:
            build_prompt(
                video_filenames=["clip.mp4"],
                task_config=_task(prompts_dir, "Text: {{user_text_input}}"),
                user_text_input="Some text",
            )
        finally:
            current_user_messages.reset(token)

        assert messages.warnings == []


class TestBuildPromptVideoFilenamesFallback:
    def test_appends_filenames_when_placeholder_missing(self, prompts_dir: Path, caplog: pytest.LogCaptureFixture):
        (prompts_dir / builder.OUTPUT_FORMAT_FILE).write_text("Output without placeholder")

        result = build_prompt(video_filenames=["video.mp4"], task_config=_task(prompts_dir, "A prompt"))

        assert result.endswith("Video 1: video.mp4")
        assert "missing" in caplog.text

    def test_warns_on_empty_video_filenames(self, prompts_dir: Path, caplog: pytest.LogCaptureFixture):
        build_prompt(video_filenames=[], task_config=_task(prompts_dir, "Videos: {{video_filenames}}"))

        assert "No video filenames provided" in caplog.text
