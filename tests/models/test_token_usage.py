from types import SimpleNamespace

from src.models.token_usage import TokenUsage, add_gemini_usage, current_token_usage


def _usage_metadata(
    prompt: int | None = None,
    output: int | None = None,
    thinking: int | None = None,
    total: int | None = None,
) -> SimpleNamespace:
    """Build a fake Gemini UsageMetadata object with the given token counts."""
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=output,
        thoughts_token_count=thinking,
        total_token_count=total,
    )


class TestTokenUsage:
    def test_starts_at_zero(self):
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.output_tokens == 0
        assert usage.thinking_tokens == 0
        assert usage.total_tokens == 0
        assert usage.gemini_call_count == 0


class TestAddGeminiUsage:
    def test_accumulates_across_calls(self):
        usage = TokenUsage()
        token = current_token_usage.set(usage)
        try:
            add_gemini_usage(_usage_metadata(prompt=100, output=20, thinking=30, total=150))
            add_gemini_usage(_usage_metadata(prompt=200, output=40, thinking=0, total=240))
        finally:
            current_token_usage.reset(token)

        assert usage.prompt_tokens == 300
        assert usage.output_tokens == 60
        assert usage.thinking_tokens == 30
        assert usage.total_tokens == 390
        assert usage.gemini_call_count == 2

    def test_is_a_no_op_without_active_context(self):
        add_gemini_usage(_usage_metadata(prompt=100, total=100))  # must not raise

    def test_none_valued_fields_count_as_zero(self):
        """The genai SDK reports None instead of 0 for absent counts (e.g. no thinking tokens)."""
        usage = TokenUsage()
        token = current_token_usage.set(usage)
        try:
            add_gemini_usage(_usage_metadata(prompt=100, output=None, thinking=None, total=100))
        finally:
            current_token_usage.reset(token)

        assert usage.prompt_tokens == 100
        assert usage.output_tokens == 0
        assert usage.thinking_tokens == 0
        assert usage.total_tokens == 100

    def test_missing_usage_metadata_still_counts_the_call(self):
        usage = TokenUsage()
        token = current_token_usage.set(usage)
        try:
            add_gemini_usage(None)
        finally:
            current_token_usage.reset(token)

        assert usage.gemini_call_count == 1
        assert usage.total_tokens == 0

    def test_collectors_are_isolated_per_context(self):
        first = TokenUsage()
        token = current_token_usage.set(first)
        try:
            add_gemini_usage(_usage_metadata(prompt=10, total=10))
        finally:
            current_token_usage.reset(token)

        second = TokenUsage()
        token = current_token_usage.set(second)
        try:
            add_gemini_usage(_usage_metadata(prompt=1, total=1))
        finally:
            current_token_usage.reset(token)

        assert first.prompt_tokens == 10
        assert second.prompt_tokens == 1
