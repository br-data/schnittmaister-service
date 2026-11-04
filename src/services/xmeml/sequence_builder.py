import uuid
from xml.etree.ElementTree import Element, SubElement

from src.config.xmeml_config import TimecodeDefaults
from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadataIndex
from src.services.xmeml.media_builder import MediaBuilder
from src.services.xmeml.shared_elements import build_logginginfo_element, build_rate_element, timeline_positions

TIMECODE_DEFAULTS = TimecodeDefaults()


class SequenceBuilder:
    """Builds a <sequence> element."""

    def __init__(
        self,
        video_clip_proposal_list: list[VideoClipProposal],
        video_metadata_index: VideoMetadataIndex,
        media_builder: MediaBuilder,
    ) -> None:
        """
        Initialize the SequenceBuilder.

        :param video_clip_proposal_list: Ordered list of the video clip proposals of the sequence.
        :param video_metadata_index: Metadata of the videos; the first one sets the rate of the sequence.
        :param media_builder: Builder for the <media> section.
        """
        self.video_clip_proposal_list = video_clip_proposal_list
        self.video_metadata_index = video_metadata_index
        self.media_builder = media_builder

    def build_sequence_element(self, sequence_name: str) -> Element:
        """
        Create the complete <sequence> element.

        uuid, duration, rate and name come first, then the <media> with all tracks, then timecode, labels
        and logginginfo. The sequence starts at the TimecodeDefaults timecode.

        :param sequence_name: Name of the sequence shown in the editing software.
        :return: The <sequence> element.
        """
        sequence = Element("sequence", id="sequence-1")

        SubElement(sequence, "uuid").text = str(uuid.uuid4())

        # The sequence runs at the rate of the job's first video; its duration is the end of the last clip
        first_video = self.video_metadata_index.values()[0]
        timebase, ntsc = first_video.timebase, first_video.ntsc
        positions = timeline_positions(self.video_clip_proposal_list, self.video_metadata_index)
        SubElement(sequence, "duration").text = str(positions[-1][1] if positions else 0)

        # <rate>
        rate = build_rate_element(
            timebase=timebase,
            ntsc=ntsc,
        )
        sequence.append(rate)

        SubElement(sequence, "name").text = sequence_name

        # <media>
        # Video clipitems are numbered from 1. Audio clipitems follow, starting at len(video_clip_proposal_list) + 1.
        starting_audio_clipitem_nr = len(self.video_clip_proposal_list) + 1
        sequence.append(self.media_builder.build_media_element(starting_audio_clipitem_nr=starting_audio_clipitem_nr))

        # <timecode>
        timecode = Element("timecode")
        timecode.append(
            build_rate_element(
                timebase=timebase,
                ntsc=ntsc,
            )
        )
        SubElement(timecode, "string").text = TIMECODE_DEFAULTS.string
        SubElement(timecode, "frame").text = str(TIMECODE_DEFAULTS.frame)
        SubElement(timecode, "displayformat").text = TIMECODE_DEFAULTS.displayformat
        sequence.append(timecode)

        # <labels>
        labels = Element("labels")
        SubElement(labels, "label2").text = "Mango"
        sequence.append(labels)

        # <logginginfo>
        sequence.append(build_logginginfo_element())

        return sequence
