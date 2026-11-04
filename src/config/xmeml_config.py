from enum import StrEnum

from pydantic import BaseModel


class AudioLayout(StrEnum):
    """
    How the source audio is represented in the generated XMEML.

    STEREO_PAIR: Two mono audio tracks, track 1 routed to the left and track 2 to the right
        output; the source file is described as one stereo pair. Right for source material
        that is one stereo mix, which is what most MP4 files carry (phone recordings, web video,
        a finished mixdown).

    MONO_PER_CHANNEL: N independent mono audio tracks, one per source channel,
        with dual-mono panning (odd tracks → left, even tracks → right).
        Right for broadcast masterclips (e.g. a MOV with 8 discrete mono channels), where the
        source carries multiple discrete mono channels (e.g. ch1=voice-over, ch2=second
        language, ch3=nat sound, ch4=music, ...) and the editor must see every channel as a
        separate timeline track to pick the right one.
    """

    STEREO_PAIR = "stereo_pair"
    MONO_PER_CHANNEL = "mono_per_channel"


class RateDefaults(BaseModel):
    """
    Default rate settings for timebase and NTSC.

    :param timebase: Frames per second (e.g., 25 for PAL).
    :param ntsc: FALSE for PAL systems (TRUE for NTSC).
    """

    timebase: int = 25
    ntsc: bool = False


class CodecDefaults(BaseModel):
    """
    Default codec metadata for the <codec> block in samplecharacteristics.

    :param name: Name of the codec.
    :param appname: Application name (e.g., Final Cut Pro).
    :param appmanufacturer: Manufacturer name.
    :param appversion: Version of the app.
    :param codectypename: Type name for the codec.
    :param codectypecode: Codec type code.
    :param codecvendorcode: Vendor code of the codec.
    :param spatialquality: Spatial quality setting (0–1024).
    :param temporalquality: Temporal quality setting.
    :param keyframerate: Keyframe interval.
    :param datarate: Target data rate (usually 0 = automatic).
    """

    name: str = "Apple ProRes 422"
    appname: str = "Final Cut Pro"
    appmanufacturer: str = "Apple Inc."
    appversion: str = "7.0"
    codectypename: str = "Apple ProRes 422"
    codectypecode: str = "apcn"
    codecvendorcode: str = "appl"
    spatialquality: int = 1024
    temporalquality: int = 0
    keyframerate: int = 0
    datarate: int = 0


class VideoDefaults(BaseModel):
    """
    Default video parameters used across sequence and clip sample characteristics.

    :param width: Default video width in pixels.
    :param height: Default video height in pixels.
    :param anamorphic: Whether the image uses non-square pixels.
    :param pixelaspectratio: Usually 'square' for progressive HD footage.
    :param sample_aspect_ratio: Width of a pixel relative to its height; 1.0 for square pixels.
    :param fielddominance: 'none' for progressive; can be 'lower' or 'upper' for interlaced.
    :param colordepth: Bit depth of the video (e.g., 24).
    """

    width: int = 1920
    height: int = 1080
    anamorphic: bool = False
    pixelaspectratio: str = "square"
    sample_aspect_ratio: float = 1.0
    fielddominance: str = "none"
    colordepth: int = 24


class AudioDefaults(BaseModel):
    """
    Default audio parameters used in audio formatting and file sample characteristics.

    The per-<audio>-block channelcount and layout strings emitted in <file><media>
    are determined by layout_mode, not configured here:
      - STEREO_PAIR     → channelcount=2, layout="stereo"
      - MONO_PER_CHANNEL → channelcount=1, layout="mono" (per block)

    :param numOutputChannels: Number of output channels of the sequence; 2 (left and right) is the only
        value the track routing supports (see AudioBuilder._resolve_output_channel_index).
    :param samplerate: Sampling rate in Hz.
    :param depth: Bit depth per sample.
    :param layout_mode: How the source audio is represented in the generated XMEML for a file without
        audio streams. See AudioLayout.
    """

    numOutputChannels: int = 2
    samplerate: int = 48000
    depth: int = 16
    layout_mode: AudioLayout = AudioLayout.STEREO_PAIR


class TimecodeDefaults(BaseModel):
    """
    Default timecode settings for sequences and files.

    :param string: Starting timecode string.
    :param frame: Starting frame number (typically 0).
    :param displayformat: Timecode format, e.g., 'NDF' for non-drop frame.
    """

    string: str = "00:00:00:00"
    frame: int = 0
    displayformat: str = "NDF"
