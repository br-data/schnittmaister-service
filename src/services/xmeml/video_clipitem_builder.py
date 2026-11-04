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


class VideoClipitemBuilder:
    """Builds <clipitem> elements for video."""

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
        file_element_builder: FileElementBuilder,
    ) -> None:
        """
        Initialize the VideoClipitemBuilder.

        :param video_metadata_index: Index of the metadata of all videos of the job.
        :param file_element_builder: Builder for the <file> elements.
        """
        self.video_metadata_index = video_metadata_index
        self.file_element_builder = file_element_builder

    def build_video_clipitem_element(
        self,
        video_clipitem_nr: int,
        source_filename: str,
        in_frame: int,
        out_frame: int,
        start_frame: int,
        end_frame: int,
        total_video_clip_count: int,
        audio_track_count: int,
        label: str,
        description: str,
        reasoning: str,
    ) -> Element:
        """
        Create a <clipitem> element for a video clip.

        :param video_clipitem_nr: The number of the video clipitem in the timeline. Starting from 1 and incrementing.
        :param source_filename: The filename of the source video file.
        :param in_frame: The start frame of the video clipitem in the source video.
        :param out_frame: The end frame of the video clipitem in the source video.
        :param start_frame: The start frame of the video clipitem on the sequence timeline.
        :param end_frame: The end frame (exclusive) of the video clipitem on the sequence timeline.
        :param total_video_clip_count: The total number of video clipitems in the timeline.
        :param audio_track_count: Total number of audio tracks in the sequence.
            Threaded into the link builder so this video clipitem links to
            every sibling audio clipitem across all audio tracks.
        :param label: A short label of the video clipitem, intended for human readers.
        :param description: A longer description of the video clipitem, intended for human readers.
        :param reasoning: A short reasoning of why the video clipitem was chosen, intended for human readers.

        :return: An ElementTree Element representing the video clipitem.
        """
        metadata = self.video_metadata_index.get(source_filename)

        clipitem = Element("clipitem", id=f"clipitem-{video_clipitem_nr}")
        SubElement(clipitem, "masterclipid").text = f"masterclip-{metadata.file_nr}"
        SubElement(clipitem, "name").text = metadata.filename
        SubElement(clipitem, "enabled").text = "TRUE"
        SubElement(clipitem, "duration").text = str(metadata.duration_frames)

        # <rate>
        clipitem.append(
            build_rate_element(
                timebase=metadata.timebase,
                ntsc=metadata.ntsc,
            )
        )

        SubElement(clipitem, "start").text = str(start_frame)
        SubElement(clipitem, "end").text = str(end_frame)
        SubElement(clipitem, "in").text = str(in_frame)
        SubElement(clipitem, "out").text = str(out_frame)

        SubElement(clipitem, "pproTicksIn").text = str(
            convert_frame_to_ppro_ticks(
                frame=in_frame,
                timebase=metadata.timebase,
                ntsc=metadata.ntsc,
            )
        )
        SubElement(clipitem, "pproTicksOut").text = str(
            convert_frame_to_ppro_ticks(
                frame=out_frame,
                timebase=metadata.timebase,
                ntsc=metadata.ntsc,
            )
        )

        SubElement(clipitem, "alphatype").text = "none"
        SubElement(clipitem, "pixelaspectratio").text = str(metadata.pixelaspectratio)
        SubElement(clipitem, "anamorphic").text = str(metadata.anamorphic).upper()

        # <file>
        clipitem.append(self.file_element_builder.build_file_element(source_filename))

        # <link> to the clipitem itself and to its audio clipitems
        for link_elem in build_link_elements_for_clipitem(
            video_clipitem_nr=video_clipitem_nr,
            total_video_clip_count=total_video_clip_count,
            audio_track_count=audio_track_count,
        ):
            clipitem.append(link_elem)

        # <marker> with Gemini's label, description and reasoning
        clipitem.append(
            self.build_gemini_marker_element(
                label=label, description=description, reasoning=reasoning, in_frame=in_frame, out_frame=out_frame
            )
        )

        # <logginginfo>
        clipitem.append(build_logginginfo_element())

        # <colorinfo>
        clipitem.append(build_colorinfo_element())

        # <labels>
        clipitem.append(self.build_labels_element())

        return clipitem

    def build_gemini_marker_element(
        self, label: str, description: str, reasoning: str, in_frame: int, out_frame: int
    ) -> Element:
        """
        Create a <marker> element with Gemini-generated information for the video clipitem.

        :param label: The short label for the marker (goes into <name>).
        :param description: A brief description of the scene or visual.
        :param reasoning: A sentence or two justifying why this moment was selected.
        :param in_frame: Start frame of the marker.
        :param out_frame: End frame of the marker.
        :return: An ElementTree Element representing the <marker>.
        """
        marker = Element("marker")
        comment_text = f"Description: {description} — Reasoning: {reasoning}"
        SubElement(marker, "comment").text = comment_text
        SubElement(marker, "name").text = label
        SubElement(marker, "in").text = str(in_frame)
        SubElement(marker, "out").text = str(out_frame)
        return marker

    def build_labels_element(self) -> Element:
        """
        Create a <labels> element with the color label "None" in <label2>.

        :return: An ElementTree Element representing the labels.
        """
        labels = Element("labels")
        SubElement(labels, "label2").text = "None"
        return labels
