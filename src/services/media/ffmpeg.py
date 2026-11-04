"""Running the ffmpeg command line tool."""

import subprocess

# Seconds after which a single ffmpeg call is aborted
FFMPEG_TIMEOUT_SECONDS = 600


def run_ffmpeg(args: list[str], loglevel: str = "error") -> str:
    """
    Run ffmpeg with the given arguments, overwriting the output.

    :param args: Arguments after the global options.
    :param loglevel: ffmpeg's log level; "info" for filters that report results, e.g. volumedetect or showinfo.
    :raises RuntimeError: If ffmpeg is missing, fails or runs into FFMPEG_TIMEOUT_SECONDS.
    :return: What ffmpeg wrote to stderr.
    """
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", loglevel, *args]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    except FileNotFoundError as e:
        raise RuntimeError("ffmpeg is not installed or not on the PATH") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"ffmpeg did not finish within {FFMPEG_TIMEOUT_SECONDS}s") from e
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {completed.stderr.strip()[-500:]}")
    return completed.stderr
