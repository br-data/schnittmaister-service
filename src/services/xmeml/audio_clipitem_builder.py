from xml.etree.ElementTree import Element, SubElement

from src.models.video_metadata import VideoMetadataIndex
from src.services.xmeml.file_element_builder import FileElementBuilder
from src.services.xmeml.shared_elements import (
    build_colorinfo_element,
    build_link_elements_for_clipitem,
    build_logginginfo_element,
    build_rate_element,
)
from src.utils.time_utils import convert_frame_to_ppro_ticks


class AudioClipitemBuilder:
    """Builds <clipitem> elements for audio."""

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
        file_element_builder: FileElementBuilder,
    ) -> None:
        """
        Initialize the AudioClipitemBuilder.

        :param video_metadata_index: Index mapping filenames to their metadata.
        :param file_element_builder: Builder for generating <file> stubs.
        """
        self.video_metadata_index = video_metadata_index
        self.file_element_builder = file_element_builder

    def build_audio_clipitem_element(
        self,
        clipitem_nr: int,
        source_filename: str,
        in_frame: int,
        out_frame: int,
        start_frame: int,
        end_frame: int,
        video_clipitem_nr: int,
        total_video_clip_count: int,
        trackindex: int,
        audio_track_count: int,
    ) -> Element:
        """
        Create a <clipitem> element for an audio track.

        Each video clip proposal produces one mono audio clipitem per timeline
        track (so audio_track_count clipitems per video clip). This builder
        emits one of those.

        :param clipitem_nr: The global sequential ID number of this audio clipitem (used in its element ID).
        :param source_filename: The filename of the associated media source.
        :param in_frame: The start frame within the source file.
        :param out_frame: The end frame within the source file.
        :param start_frame: The start frame of the audio clipitem on the sequence timeline.
        :param end_frame: The end frame (exclusive) of the audio clipitem on the sequence timeline.
        :param video_clipitem_nr: The 1-based index of the associated video clipitem in the sequence.
        :param total_video_clip_count: The total nr of video clipitems in the sequence, used to compute link references.
        :param trackindex: 1-based audio track number this clipitem belongs to.
            Also written to <sourcetrack><trackindex>, i.e. the source channel played.
        :param audio_track_count: Total number of audio tracks in the sequence.
            Threaded into the link builder so this clipitem links to all its
            sibling audio clipitems across tracks.

        :return: An ElementTree Element representing the audio <clipitem>.
        """
        metadata = self.video_metadata_index.get(source_filename)

        # Every audio clipitem plays one mono channel of its source file
        clipitem = Element("clipitem", id=f"clipitem-{clipitem_nr}", premiereChannelType="mono")

        SubElement(clipitem, "masterclipid").text = f"masterclip-{metadata.file_nr}"
        SubElement(clipitem, "name").text = metadata.filename
        SubElement(clipitem, "enabled").text = "TRUE"
        SubElement(clipitem, "duration").text = str(metadata.duration_frames)

        # <rate>
        clipitem.append(build_rate_element(metadata.timebase, metadata.ntsc))

        SubElement(clipitem, "start").text = str(start_frame)
        SubElement(clipitem, "end").text = str(end_frame)
        SubElement(clipitem, "in").text = str(in_frame)
        SubElement(clipitem, "out").text = str(out_frame)
        SubElement(clipitem, "pproTicksIn").text = str(
            convert_frame_to_ppro_ticks(in_frame, metadata.timebase, metadata.ntsc)
        )
        SubElement(clipitem, "pproTicksOut").text = str(
            convert_frame_to_ppro_ticks(out_frame, metadata.timebase, metadata.ntsc)
        )

        # <file>
        clipitem.append(self.file_element_builder.build_file_element(source_filename))

        # <sourcetrack>
        sourcetrack = SubElement(clipitem, "sourcetrack")
        SubElement(sourcetrack, "mediatype").text = "audio"
        SubElement(sourcetrack, "trackindex").text = str(trackindex)

        # <link> to the video clipitem and to all its audio clipitems
        for link_elem in build_link_elements_for_clipitem(
            video_clipitem_nr=video_clipitem_nr,
            total_video_clip_count=total_video_clip_count,
            audio_track_count=audio_track_count,
        ):
            clipitem.append(link_elem)

        # <logginginfo>
        clipitem.append(build_logginginfo_element())

        # <colorinfo>
        clipitem.append(build_colorinfo_element())

        # <labels>
        clipitem.append(self.build_labels_element())

        return clipitem

    def build_labels_element(self) -> Element:
        """
        Create a <labels> element with the color label of the audio clipitems.

        :return: An ElementTree Element representing the labels.
        """
        labels = Element("labels")
        SubElement(labels, "label2").text = "Iris"
        return labels
