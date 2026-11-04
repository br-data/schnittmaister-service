from pydantic import BaseModel


class BackoffConfig(BaseModel):
    """
    Retry settings of the Gemini calls.

    Short-lived errors (429, 502, 503) are retried with exponential backoff and jitter; with the defaults,
    the waits before the second and third attempt are about 10 and 20 seconds. A 429 that names a retry
    delay (Google's RetryInfo) waits that long instead, or is not retried at all if the delay exceeds
    max_retry_delay_seconds: a quota that resets in hours is reported right away. Timeouts are not retried.

    :cvar max_tries: Maximum number of attempts (initial try + retries).
    :cvar factor: Multiplier of the exponential wait (wait = 2^attempt * factor).
    :cvar max_wait: Maximum wait between two attempts in seconds, before jitter.
    :cvar jitter: Random variation of every wait, as a fraction (0.25 = ±25%); staggers concurrent retries.
        0 makes the waits deterministic.
    :cvar max_retry_delay_seconds: Longest delay named by a 429 that is still waited for.
    """

    max_tries: int = 3
    factor: float = 5.0
    max_wait: float = 60.0
    jitter: float = 0.25
    max_retry_delay_seconds: float = 60.0
