from xml.etree.ElementTree import Element

from src.services.xmeml.audio_builder import AudioBuilder
from src.services.xmeml.video_builder import VideoBuilder


class MediaBuilder:
    """Builds the <media> element, including <video> and <audio>."""

    def __init__(
        self,
        video_builder: VideoBuilder,
        audio_builder: AudioBuilder,
    ) -> None:
        """
        Initialize the MediaBuilder.

        :param video_builder: Instance responsible for building the <video> section.
        :param audio_builder: Instance responsible for building the <audio> section.
        """
        self.video_builder = video_builder
        self.audio_builder = audio_builder

    def build_media_element(self, starting_audio_clipitem_nr: int) -> Element:
        """
        Create the <media> element containing <video> and <audio>.

        :param starting_audio_clipitem_nr: The first clipitem number to assign in the audio section.
        :return: An ElementTree Element representing <media>.
        """
        media_el = Element("media")

        # <video>
        media_el.append(self.video_builder.build_video_element())

        # <audio>
        media_el.append(self.audio_builder.build_audio_element(starting_clipitem_nr=starting_audio_clipitem_nr))

        return media_el
