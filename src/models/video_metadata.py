from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from src.config.xmeml_config import AudioDefaults, AudioLayout, RateDefaults, TimecodeDefaults, VideoDefaults
from src.utils.time_utils import real_frame_rate

VIDEO_DEFAULTS = VideoDefaults()
RATE_DEFAULTS = RateDefaults()
AUDIO_DEFAULTS = AudioDefaults()
TIMECODE_DEFAULTS = TimecodeDefaults()


class VideoMetadata(BaseModel):
    """
    Metadata of a video file.

    :param file_nr: An arbitrary number assigned to the file. Used in XMEML creation.
    :param filename: The name of the video file, including extension. It is the name Gemini gets and
        uses to reference the file, and the key of the VideoMetadataIndex.
    :param local_path: Path of the video on this machine.
    :param gemini_file_name: Resource name of the video in the Gemini Files API ("files/<id>"), once
        it is uploaded.
    :param gemini_file_uri: URI of the video in the Gemini Files API, once it is uploaded; this is what
        the Gemini request references.
    :param mime_type: MIME type of the video.

    :param xmeml_pathurl: The file URL of the video, as written into the XMEML so the editor links the
        file on import.

    :param duration_frames: Length of the video stream in whole frames of the timebase (from the probe).
    :param duration_seconds: Duration of the container in seconds (from the probe).
    :param shot_cuts: Frames where a new shot starts, detected with ffmpeg; clip boundaries are snapped to
        them. Empty if the detection failed or found no cut.

    :param timebase: Timebase (frames per second, rounded to a whole number).
    :param ntsc: Whether the frame rate is an NTSC rate, 1000/1001 of the timebase (e.g. 29.97 for timebase 30).

    :param width: The width of the video in pixels, as stored.
    :param height: The height of the video in pixels.
    :param sample_aspect_ratio: Width of a pixel relative to its height (1.0 for square pixels), from the probe;
        the preview video uses it to show anamorphic material in its display size.
    :param anamorphic: Non-square pixel flag.
    :param pixelaspectratio: Aspect ratio of pixels.
    :param fielddominance: Interlace setting.

    :param timecode_string: Start timecode string.
    :param timecode_frame: Start timecode as frame number.
    :param timecode_displayformat: Format for timecode (e.g. "NDF").

    :param audio_stream_count: Number of audio streams in the file, from the probe (1 if not given); the preview
        video takes its sound from the first stream that is not silent, and silence if there is none.
    :param audio_samplerate: Audio sample rate in Hz.
    :param audio_depth: Bit depth of audio.
    :param audio_layout_mode: How this file's audio is represented in the generated XMEML: two mono
        tracks routed left and right (STEREO_PAIR) or N independent mono tracks (MONO_PER_CHANNEL).
        Probed from the file's audio streams; a file without them keeps AudioDefaults.layout_mode.
    :param audio_track_count: Number of audio tracks the timeline emits for this file: 2 for STEREO_PAIR,
        the probed channel count for MONO_PER_CHANNEL.
    """

    file_nr: int
    filename: str
    local_path: Path
    gemini_file_name: str | None = None
    gemini_file_uri: str | None = None
    mime_type: str | None = None

    xmeml_pathurl: str

    duration_frames: int
    duration_seconds: float
    shot_cuts: list[int] = Field(default_factory=list)

    timebase: int = RATE_DEFAULTS.timebase
    ntsc: bool = RATE_DEFAULTS.ntsc

    width: int = VIDEO_DEFAULTS.width
    height: int = VIDEO_DEFAULTS.height
    sample_aspect_ratio: float = VIDEO_DEFAULTS.sample_aspect_ratio
    anamorphic: bool = VIDEO_DEFAULTS.anamorphic
    pixelaspectratio: str = VIDEO_DEFAULTS.pixelaspectratio
    fielddominance: str = VIDEO_DEFAULTS.fielddominance

    timecode_string: str = TIMECODE_DEFAULTS.string
    timecode_frame: int = TIMECODE_DEFAULTS.frame
    timecode_displayformat: str = TIMECODE_DEFAULTS.displayformat

    audio_stream_count: int = 1
    audio_samplerate: int = AUDIO_DEFAULTS.samplerate
    audio_depth: int = AUDIO_DEFAULTS.depth
    audio_layout_mode: AudioLayout = AUDIO_DEFAULTS.layout_mode
    audio_track_count: int = Field(default=2, ge=1)

    @property
    def frame_rate(self) -> float:
        """
        The real frame rate of the video, for converting between seconds and frames.

        :return: The timebase, or 1000/1001 of it for an NTSC rate.
        """
        return real_frame_rate(self.timebase, self.ntsc)

    @model_validator(mode="after")
    def check_audio_track_count(self) -> "VideoMetadata":
        """
        Reject an ``audio_track_count`` that contradicts the layout mode (STEREO_PAIR requires 2).

        :raises ValueError: If STEREO_PAIR is combined with a track count other than 2.
        :return: The validated video metadata.
        """
        if self.audio_layout_mode == AudioLayout.STEREO_PAIR and self.audio_track_count != 2:
            raise ValueError(
                f"audio_layout_mode=STEREO_PAIR requires audio_track_count=2, "
                f"got audio_track_count={self.audio_track_count}"
            )
        return self


class VideoMetadataIndex:
    """Index of the job's VideoMetadata objects by file name."""

    def __init__(self, metadata: Mapping[str, VideoMetadata]) -> None:
        """
        Initialize the index with a mapping of filenames to metadata.

        :param metadata: A mapping from source filename (str) to its VideoMetadata.
        """
        self._meta = dict(metadata)

    @classmethod
    def from_list(cls, metas: list[VideoMetadata]) -> "VideoMetadataIndex":
        """
        Build an index from a list of metadata objects, keyed by filename.

        :param metas: A list of VideoMetadata instances.
        :return: A new VideoMetadataIndex mapping each filename to its metadata.
        """
        return cls({m.filename: m for m in metas})

    def get(self, filename: str) -> VideoMetadata:
        """
        Retrieve the metadata for a given source file.

        :param filename: The name of the source file to look up.
        :return: The VideoMetadata for that filename.
        :raises ValueError: If the filename is not in the index.
        """
        try:
            return self._meta[filename]
        except KeyError as e:
            raise ValueError(f"Unknown source file: {filename!r}") from e

    def __len__(self) -> int:
        """
        Return the number of items in the index.

        :return: The number of video metadata objects.
        """
        return len(self._meta)

    def __contains__(self, filename: str) -> bool:
        """
        Test whether a filename is in the index.

        :param filename: The source filename to check.
        :return: True if the index contains metadata for that filename, else False.
        """
        return filename in self._meta

    def keys(self) -> list[str]:
        """
        List all filenames in the index.

        :return: A list of all source filenames.
        """
        return list(self._meta.keys())

    def values(self) -> list[VideoMetadata]:
        """
        List all metadata objects in the index.

        :return: A list of VideoMetadata instances.
        """
        return list(self._meta.values())
