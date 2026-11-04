import logging
from xml.etree.ElementTree import Element, tostring

from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadataIndex
from src.services.xmeml.audio_builder import AudioBuilder
from src.services.xmeml.file_element_builder import FileElementBuilder
from src.services.xmeml.media_builder import MediaBuilder
from src.services.xmeml.sequence_builder import SequenceBuilder
from src.services.xmeml.video_builder import VideoBuilder


class XmemlBuilder:
    """Main builder to construct a complete <xmeml> document tree."""

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
        video_clip_proposals: list[VideoClipProposal],
        sequence_name: str,
    ) -> None:
        """
        Initialize the XmemlBuilder.

        :param video_metadata_index: Index of metadata for video files.
        :param video_clip_proposals: Ordered list of video clip proposals for the sequence.
        :param sequence_name: Name of the sequence in the editor.
        """
        self.video_metadata_index = video_metadata_index
        self.video_clip_proposals = video_clip_proposals
        self.sequence_name = sequence_name

        self.file_element_builder = FileElementBuilder(video_metadata_index=self.video_metadata_index)

        self.video_builder = VideoBuilder(
            video_metadata_index=self.video_metadata_index,
            file_element_builder=self.file_element_builder,
            video_clip_proposals=self.video_clip_proposals,
        )

        self.audio_builder = AudioBuilder(
            video_metadata_index=self.video_metadata_index,
            file_element_builder=self.file_element_builder,
            video_clip_proposals=self.video_clip_proposals,
        )

        self.media_builder = MediaBuilder(
            video_builder=self.video_builder,
            audio_builder=self.audio_builder,
        )

        self.sequence_builder = SequenceBuilder(
            video_clip_proposal_list=self.video_clip_proposals,
            video_metadata_index=self.video_metadata_index,
            media_builder=self.media_builder,
        )

    def build_xmeml(self) -> Element:
        """
        Construct the entire <xmeml> document.

        :return: The <xmeml> root element of the document.
        """
        xmeml_el = Element("xmeml", version="5")

        # <sequence>
        sequence_el = self.sequence_builder.build_sequence_element(sequence_name=self.sequence_name)

        xmeml_el.append(sequence_el)
        return xmeml_el

    def build_xmeml_string(self) -> str:
        """
        Build the complete XMEML document and serialize it to an XML string.

        :return: Complete XMEML as an XML string, with XML declaration and doctype.
        """
        logging.info("Building XMEML structure...")

        xml_body = tostring(self.build_xmeml(), encoding="unicode", method="xml")
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'

        logging.info("XMEML structure built successfully")
        return xml_header + xml_body
