from pydantic import BaseModel


class SnappingConfig(BaseModel):
    """
    Settings of snapping clip boundaries onto the detected cuts.

    Gemini sees the video at fps_analysis (1 frame per second by default), so its clip boundaries fall on that
    grid and often miss the real cut by a few frames: a clip then starts with the last frames of the previous
    shot, or misses the first frames of its own. A boundary is moved onto a cut that is close enough, in either
    direction, since the grid error goes both ways.

    :param snap_tolerance_intervals: How far a boundary may be snapped, in Gemini sampling intervals
        (1 / fps_analysis). One interval covers the error of the sampling grid: at 1 fps on a 25 fps video,
        25 frames; a cut further away belongs to another boundary.
    """

    snap_tolerance_intervals: float = 1.0
