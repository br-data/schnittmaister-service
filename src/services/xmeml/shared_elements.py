from xml.etree.ElementTree import Element, SubElement

from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadataIndex


def build_link_elements_for_clipitem(
    video_clipitem_nr: int,
    total_video_clip_count: int,
    audio_track_count: int,
) -> list[Element]:
    """
    Build <link> elements that bind one video clipitem to its sibling audio clipitems.

    Each logical clip (one VideoClipProposal) produces:
      - 1 video clipitem on track 1
      - audio_track_count mono audio clipitems, one per audio track

    Clipitem IDs are assigned globally across the sequence:
      - video clipitems    : 1 .. N
      - audio track 1 clips: N+1 .. 2N
      - audio track 2 clips: 2N+1 .. 3N
      - ...
      - audio track M clips: M*N+1 .. (M+1)*N
    where N = total_video_clip_count and M = audio_track_count.

    For a video clipitem with index `v`, its linked audio clipitem on track `t`
    therefore has ID `v + t*N`. This is what the comprehension below computes.

    :param video_clipitem_nr: 1-based index of this video clipitem within the sequence.
    :param total_video_clip_count: Total number of video clipitems in the sequence (= N).
    :param audio_track_count: Number of audio tracks bound to each video clip
        (2 for STEREO_PAIR, typically 8 for MONO_PER_CHANNEL).
    :return: A list with 1 video <link> followed by audio_track_count audio <link> elements.
    """
    video_link = build_link_element(
        f"clipitem-{video_clipitem_nr}",
        mediatype="video",
        trackindex=1,
        clipindex=video_clipitem_nr,
    )
    audio_links = [
        build_link_element(
            f"clipitem-{video_clipitem_nr + total_video_clip_count * track_index}",
            mediatype="audio",
            trackindex=track_index,
            clipindex=video_clipitem_nr,
        )
        for track_index in range(1, audio_track_count + 1)
    ]
    return [video_link, *audio_links]


def build_link_element(linkclipref: str, mediatype: str, trackindex: int, clipindex: int) -> Element:
    """
    Create a <link> element for linking clips in the timeline.

    :param linkclipref: The reference ID of the clip to link to.
    :param mediatype: The type of media (e.g., "video", "audio").
    :param trackindex: The index of the track in the timeline.
    :param clipindex: The index of the clip in the track.
    :return: An ElementTree Element representing the link.
    """
    link = Element("link")
    SubElement(link, "linkclipref").text = linkclipref
    SubElement(link, "mediatype").text = mediatype
    SubElement(link, "trackindex").text = str(trackindex)
    SubElement(link, "clipindex").text = str(clipindex)
    return link


def build_rate_element(timebase: int, ntsc: bool) -> Element:
    """
    Create a <rate> element.

    :param timebase: Frames per second.
    :param ntsc: Whether the frame rate is an NTSC rate.
    :return: An ElementTree Element representing the rate.
    """
    rate = Element("rate")
    SubElement(rate, "timebase").text = str(timebase)
    SubElement(rate, "ntsc").text = str(ntsc).upper()
    return rate


def build_logginginfo_element() -> Element:
    """
    Create an empty <logginginfo> element for a clipitem or the sequence.

    Premiere keeps logging metadata such as scene, take and original file names in it; the service
    leaves all fields empty.

    :return: An ElementTree Element representing the logginginfo.
    """
    logginginfo = Element("logginginfo")
    SubElement(logginginfo, "description").text = ""
    SubElement(logginginfo, "scene").text = ""
    SubElement(logginginfo, "shottake").text = ""
    SubElement(logginginfo, "lognote").text = ""
    SubElement(logginginfo, "good").text = ""
    SubElement(logginginfo, "originalvideofilename").text = ""
    SubElement(logginginfo, "originalaudiofilename").text = ""
    return logginginfo


def build_colorinfo_element() -> Element:
    """
    Create an empty <colorinfo> element for a clipitem.

    Premiere keeps LUTs and ASC color grading values in it; the service leaves all fields empty.

    :return: An ElementTree Element representing the colorinfo.
    """
    colorinfo = Element("colorinfo")
    SubElement(colorinfo, "lut").text = ""
    SubElement(colorinfo, "lut1").text = ""
    SubElement(colorinfo, "asc_sop").text = ""
    SubElement(colorinfo, "asc_sat").text = ""
    SubElement(colorinfo, "lut2").text = ""
    return colorinfo


def timeline_positions(
    video_clip_proposals: list[VideoClipProposal],
    video_metadata_index: VideoMetadataIndex,
) -> list[tuple[int, int]]:
    """
    Start and end of each clip on the sequence timeline, one after the other, in frames of the sequence.

    The sequence runs at the frame rate of the job's first video. A clip from a video with another rate is
    converted, so that it keeps its duration on the timeline; in and out stay in frames of its own video.

    :param video_clip_proposals: The clips in sequence order.
    :param video_metadata_index: Metadata of the videos; the first one sets the sequence rate.
    :return: (start, end) per clip, end exclusive.
    """
    sequence_rate = video_metadata_index.values()[0].frame_rate
    positions = []
    start = 0
    for clip in video_clip_proposals:
        clip_rate = video_metadata_index.get(clip.source_filename).frame_rate
        end = start + round((clip.out_frame - clip.in_frame) * sequence_rate / clip_rate)
        positions.append((start, end))
        start = end
    return positions
