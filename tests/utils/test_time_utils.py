import pytest

from src.utils.time_utils import timestamp_to_seconds

# -------------------------------------------------
# --- Timestamp to Seconds: Formats and LLM Errors ---
# -------------------------------------------------

# A dictionary of test cases covering the prioritized formats and fallbacks.
# 'input': The timestamp string passed to the function.
# 'expected': The expected result in seconds or the expected exception type.
test_cases = {
    # === Standard Valid Cases ===
    "Primary H:MM:SS.sss": ("01:02:03.500", 3723.5),
    "Fallback MM:SS.sss": ("01:23.456", 83.456),
    "Fallback H:MM:SS": ("01:02:03", 3723.0),
    "Fallback MM:SS": ("01:23", 83.0),
    "Supported format - Seconds with ms": ("45.5", 45.5),
    "Supported format - Seconds only": ("45", 45.0),
    # === LLM Error Handling Cases ===
    "LLM Error - Seconds overflow": ("00:09:60.000", 600.0),  # Correctly parsed as 10 minutes
    "LLM Error - Colon as ms separator": ("00:01:23:456", 83.456),  # Correctly parsed as 00:01:23.456
    "LLM Error - One digit ms (ljust)": ("00:00:02.1", 2.1),  # Parsed as 2.100s
    "LLM Error - Two digit ms (ljust)": ("00:00:02.12", 2.12),  # Parsed as 2.120s
    "LLM Error - Four digit ms (truncate)": ("00:00:02.1239", 2.123),  # Parsed as 2.123s
    # === Edge Cases ===
    "Zero time": ("00:00:00.000", 0.0),
    "Just under a second": ("00:00:00.960", 0.96),
    # === Invalid Cases that should still fail ===
    "Invalid format with too many parts": ("01:02:03:04:05", ValueError),
    "Non-numeric characters": ("01:ab:03", ValueError),
    "Empty String": ("", ValueError),
}


@pytest.mark.unit
@pytest.mark.parametrize("timestamp, expected", test_cases.values(), ids=test_cases.keys())
def test_timestamp_to_seconds_formats_and_llm_errors(timestamp: str, expected: float | type) -> None:
    """
    Tests the `timestamp_to_seconds` function with various formats, LLM errors and edge cases.

    Uses Pytest's parametrization to run each case from the dictionary as a separate test.
    """
    # If the expected value is an exception type, check that this exception is raised.
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            timestamp_to_seconds(timestamp)
    else:
        # Otherwise, compare the actual result with the expected result.
        assert timestamp_to_seconds(timestamp) == pytest.approx(expected)


# -----------------------------------------
# --- Timestamp to Seconds Tests ---
# -----------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "timestamp, expected_seconds",
    [
        # Standard formats
        ("00:00.000", 0.0),
        ("00:01.000", 1.0),
        ("01:00.000", 60.0),
        ("01:30.500", 90.5),
        ("05:30.000", 330.0),
        ("10:00.000", 600.0),
        # With hours
        ("1:00:00.000", 3600.0),
        ("01:30:45.500", 5445.5),
        # Without milliseconds
        ("05:30", 330.0),
        ("1:00:00", 3600.0),
        # Edge cases
        ("0:00.000", 0.0),
        ("0:0.0", 0.0),
        ("30:26.000", 1826.0),  # From real SCENE_FINDER output
        ("35:08.000", 2108.0),  # From real SCENE_FINDER output
    ],
)
def test_timestamp_to_seconds(timestamp: str, expected_seconds: float) -> None:
    """Test timestamp_to_seconds converts various formats correctly."""
    assert timestamp_to_seconds(timestamp) == expected_seconds


@pytest.mark.unit
def test_timestamp_to_seconds_invalid_format() -> None:
    """Test that invalid timestamp formats raise ValueError."""
    with pytest.raises(ValueError):
        timestamp_to_seconds("invalid")
