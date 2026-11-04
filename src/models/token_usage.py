from contextvars import ContextVar
from typing import Any


class TokenUsage:
    """
    Collector for Gemini token usage accumulated during a job.

    Every Gemini call in a job reports its response's usage metadata here, including retries. The
    totals are logged at the end of the job.

    The collector is created at the top of the processing pipeline and made
    available to any function in the call stack via the context variable
    ``current_token_usage``. ``generate_structured_output`` reports usage
    after every successful Gemini response.

    :ivar prompt_tokens: Sum of input tokens (``prompt_token_count``).
    :ivar output_tokens: Sum of response tokens (``candidates_token_count``).
    :ivar thinking_tokens: Sum of reasoning tokens (``thoughts_token_count``).
    :ivar total_tokens: Sum of ``total_token_count`` as reported by the API
        (kept separate instead of computed, so components not tracked
        individually — e.g. tool-use tokens — are still included).
    :ivar gemini_call_count: Number of Gemini responses recorded.
    """

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.output_tokens: int = 0
        self.thinking_tokens: int = 0
        self.total_tokens: int = 0
        self.gemini_call_count: int = 0


current_token_usage: ContextVar[TokenUsage | None] = ContextVar("current_token_usage", default=None)


def add_gemini_usage(usage_metadata: Any) -> None:  # noqa: ANN401
    """
    Record one Gemini response's token usage on the active job's collector.

    No-op if no job context is active. Metadata fields that are missing or
    ``None`` (e.g. no thinking tokens for non-reasoning calls) count as 0;
    a response without usage metadata still increments the call count.

    :param usage_metadata: ``UsageMetadata`` from a Gemini response, or None.
    """
    usage = current_token_usage.get(None)
    if usage is None:
        return

    usage.gemini_call_count += 1
    usage.prompt_tokens += getattr(usage_metadata, "prompt_token_count", None) or 0
    usage.output_tokens += getattr(usage_metadata, "candidates_token_count", None) or 0
    usage.thinking_tokens += getattr(usage_metadata, "thoughts_token_count", None) or 0
    usage.total_tokens += getattr(usage_metadata, "total_token_count", None) or 0
