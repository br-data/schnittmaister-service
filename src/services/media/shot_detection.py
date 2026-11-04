"""Detection of the cuts (shot changes) in a local video with ffmpeg's scene filter."""

import logging
import re
from pathlib import Path

from src.config.shot_detection_config import ShotDetectionConfig
from src.services.media.ffmpeg import run_ffmpeg

SHOT_DETECTION_CONFIG = ShotDetectionConfig()

# Timestamp of a selected frame in the log of ffmpeg's showinfo filter, e.g. "... pts_time:47.04 duration..."
_PTS_TIME_PATTERN = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


def detect_shot_cuts(path: Path, frame_rate: float) -> list[int]:
    """
    Find the frames where a new shot starts.

    ffmpeg's scene filter scores every frame by how much it differs from the previous one; frames above
    ShotDetectionConfig.scene_threshold are cuts. The video is scaled down first, which makes the pass fast
    (about 1.5 seconds for 3 minutes of SD video). Cuts closer than min_shot_seconds to the previous one are
    dropped as false alarms.

    :param path: Path of the video.
    :param frame_rate: Frame rate of the video, to turn the cut times into frames.
    :raises RuntimeError: If ffmpeg is missing, fails or runs into its timeout.
    :return: The frames where a new shot starts, ascending.
    """
    config = SHOT_DETECTION_CONFIG
    video_filter = f"scale={config.analysis_width}:-2,select='gt(scene,{config.scene_threshold})',showinfo"
    log = run_ffmpeg(["-i", str(path), "-an", "-vf", video_filter, "-f", "null", "-"], loglevel="info")

    min_shot_frames = round(config.min_shot_seconds * frame_rate)
    cuts: list[int] = []
    for time in _PTS_TIME_PATTERN.findall(log):
        frame = round(float(time) * frame_rate)
        if not cuts or frame - cuts[-1] >= min_shot_frames:
            cuts.append(frame)
    logging.info(f"Detected {len(cuts)} cut(s) in '{path.name}'")
    return cuts
