import logging
import re
from datetime import timedelta

# Premiere counts time in ticks, 254016000000 per second
PPRO_TICKS_PER_SECOND = 254016000000


def real_frame_rate(timebase: int, ntsc: bool) -> float:
    """
    The real frame rate of a timebase, for converting between seconds and frames.

    :param timebase: Frames per second, rounded to a whole number.
    :param ntsc: Whether the frame rate is 1000/1001 of the timebase (e.g. 29.97 for 30).
    :return: The frame rate in frames per second.
    """
    return timebase * 1000 / 1001 if ntsc else timebase


def convert_frame_to_ppro_ticks(frame: int, timebase: int, ntsc: bool) -> int:
    """
    Convert a frame number to Premiere Pro ticks.

    :param frame: The frame number to convert.
    :param timebase: Frames per second of the video, rounded to a whole number.
    :param ntsc: Whether the frame rate is 1000/1001 of the timebase; ticks per frame stay whole numbers for
        the usual rates (24, 25, 30, 50, 60).
    :return: The corresponding tick value.
    """
    ticks_per_frame = PPRO_TICKS_PER_SECOND * 1001 // (timebase * 1000) if ntsc else PPRO_TICKS_PER_SECOND // timebase
    return frame * ticks_per_frame


def timestamp_to_seconds(timestamp: str) -> float:
    """
    Convert a timestamp string from various formats to total seconds.

    This function is robust against common LLM formatting errors by first
    normalizing the input and then using timedelta for reliable time calculation.
    It handles out-of-range values (e.g., 60 seconds) and inconsistent
    millisecond separators.

    This function assumes there are no frame components in the input timestamp.

    Supported formats:
    - H:MM:SS.sss or HH:MM:SS.sss (e.g., "1:23:45.678")
    - MM:SS.sss (e.g., "23:45.678")
    - SS.sss or SS (e.g., "45.678" or "45")
    - Edge cases: H:MM:SS:sss (colon instead of dot for milliseconds)

    :param timestamp: Timestamp string
    :return: Total seconds as a float
    :raises ValueError: If the timestamp format is fundamentally unparseable
    """
    original_timestamp = timestamp.strip()
    timestamp = original_timestamp

    # --- Normalization Step ---
    # Replace final colon with dot if it looks like milliseconds (e.g., "00:01:23:456")
    parts = timestamp.split(":")
    if len(parts) >= 2:
        last_part = parts[-1]
        # If last part is exactly 3 digits (no dot), it's likely milliseconds with wrong separator
        if re.fullmatch(r"\d{3}", last_part):
            # Find the position of the last colon and replace it with a dot
            last_colon_index = timestamp.rfind(":")
            timestamp = timestamp[:last_colon_index] + "." + timestamp[last_colon_index + 1 :]

    # --- Parsing Step ---
    try:
        parts = timestamp.split(":")
        h, m, s, ms = 0, 0, 0, 0

        # Parse seconds and milliseconds from the last part
        s_parts = parts[-1].split(".")
        s = int(s_parts[0])

        if len(s_parts) > 1:
            # Pad with zeros on the right or truncate milliseconds to 3 digits
            # "1:23.4" → 400ms (not 4ms)
            # "1:23.12" → 120ms (not 12ms)
            # "1:23.1234" → 123ms (truncate)
            ms_str = s_parts[1].ljust(3, "0")[:3]
            ms = int(ms_str)

        # Determine hours and minutes based on number of parts
        if len(parts) == 1:
            # SS.sss or SS
            pass  # h=0, m=0 already set
        elif len(parts) == 2:
            # MM:SS.sss or MM:SS
            m = int(parts[0])
        elif len(parts) == 3:
            # H:MM:SS.sss or H:MM:SS
            h = int(parts[0])
            m = int(parts[1])
        else:
            raise ValueError(f"Timestamp has too many parts: {len(parts)}")

        # --- Calculation Step ---
        # timedelta automatically handles overflows (e.g., 65 seconds → 1 min 5 sec)
        total_duration = timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms)
        total_seconds = total_duration.total_seconds()

        if timestamp != original_timestamp:
            logging.info(f"Normalized timestamp '{original_timestamp}' to '{timestamp}' -> {total_seconds:.3f}s")

        return total_seconds

    except (ValueError, IndexError) as e:
        logging.error(f"Could not parse timestamp: '{original_timestamp}'. Error: {e}")
        raise ValueError(f"Invalid or unrecognized timestamp format: '{original_timestamp}'") from e


def seconds_to_frames(total_seconds: float, video_fps: float) -> int:
    """
    Converts a float of total seconds into an integer frame number.

    :param total_seconds: Total time in seconds (can be fractional).
    :param video_fps: Frame rate of the video (positive, e.g. 29.97 for NTSC), NOT the analysis fps.
    :return: Corresponding frame number as an integer.
    :raises ValueError: If video_fps is not positive or total_seconds is negative.
    """
    if video_fps <= 0:
        raise ValueError("Video FPS must be a positive number.")
    if total_seconds < 0:
        raise ValueError("Total seconds cannot be negative.")
    return int(total_seconds * video_fps)


def seconds_to_timestamp(total_seconds: float) -> str:
    """
    Convert total seconds to a human-readable MM:SS.sss timestamp string.

    :param total_seconds: Total time in seconds (can be fractional).
    :return: Formatted timestamp string in MM:SS.sss format.
    """
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"
