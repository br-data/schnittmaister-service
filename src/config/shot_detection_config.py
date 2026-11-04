from pydantic import BaseModel


class ShotDetectionConfig(BaseModel):
    """
    Settings of the shot detection with ffmpeg.

    The clip boundaries are snapped onto the cuts it finds, see SnappingConfig.

    :param scene_threshold: Change between two frames (0 to 1) from which ffmpeg's scene filter reports a cut.
        Hard cuts score far above 0.3; fades and dissolves change slowly and are mostly not detected.
    :param analysis_width: Width in pixels the video is scaled to for the detection; small is fast and enough.
    :param min_shot_seconds: A cut closer than this to the previous one is dropped as a false alarm, e.g. a
        fast pan right after a cut.
    """

    scene_threshold: float = 0.3
    analysis_width: int = 320
    min_shot_seconds: float = 0.2
