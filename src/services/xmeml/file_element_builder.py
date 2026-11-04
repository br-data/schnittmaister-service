from xml.etree.ElementTree import Element, SubElement

from src.config.xmeml_config import AudioLayout
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.xmeml.shared_elements import build_rate_element


class FileElementBuilder:
    """
    Build <file> elements for video files using metadata.

    The <file> element is a container for media information, including video and audio characteristics.
    The first occurrence of a file is fully described, while subsequent occurrences are represented by a stub.
    """

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
    ) -> None:
        """
        Initialize the FileElementBuilder.

        :param video_metadata_index: Index mapping source filenames to their metadata.
        """
        self.video_metadata_index = video_metadata_index
        self.emitted_filenames: set[str] = set()

    def build_file_element(self, video_source_filename: str) -> Element:
        """
        Build a <file> element for the given source file.

        Returns a full <file> element on first occurrence,
        and a stub <file id="..."/> on subsequent occurrences.

        :param video_source_filename: The source video filename.
        :return: An ElementTree Element representing the file.
        """
        metadata = self.video_metadata_index.get(video_source_filename)

        file_id = f"file-{metadata.file_nr}"

        # Return stub if this file has already been fully emitted
        if video_source_filename in self.emitted_filenames:
            return Element("file", id=file_id)

        self.emitted_filenames.add(video_source_filename)

        file_elem = Element("file", id=file_id)
        SubElement(file_elem, "name").text = metadata.filename
        SubElement(file_elem, "pathurl").text = metadata.xmeml_pathurl

        # <rate>
        file_elem.append(build_rate_element(timebase=metadata.timebase, ntsc=metadata.ntsc))
        SubElement(file_elem, "duration").text = str(metadata.duration_frames)

        # <timecode>
        file_elem.append(self._build_timecode_element(video_source_filename))

        # <media>
        file_elem.append(self._build_media_element(video_source_filename))

        return file_elem

    def _build_timecode_element(self, video_source_filename: str) -> Element:
        """
        Create a <timecode> element for the given source file.

        :param video_source_filename: The source video filename.
        :return: An ElementTree Element representing the timecode.
        """
        metadata: VideoMetadata = self.video_metadata_index.get(video_source_filename)

        timecode = Element("timecode")
        timecode.append(build_rate_element(timebase=metadata.timebase, ntsc=metadata.ntsc))
        SubElement(timecode, "string").text = metadata.timecode_string
        SubElement(timecode, "frame").text = str(metadata.timecode_frame)
        SubElement(timecode, "displayformat").text = metadata.timecode_displayformat
        return timecode

    def _build_media_audio_element(
        self,
        video_source_filename: str,
        sourcechannel: int,
        channellabel: str,
        channelcount: int,
        layout: str,
    ) -> Element:
        """
        Create an <audio> element as subelement of the <media> element.

        Sample characteristics (depth, samplerate) come from metadata since they
        describe the source file. Per-block channelcount and layout are caller-
        supplied because they depend on the layout mode (STEREO_PAIR emits
        channelcount=2/layout="stereo" per block; MONO_PER_CHANNEL emits
        channelcount=1/layout="mono" per block).

        :param video_source_filename: The source video filename.
        :param sourcechannel: 1-based source channel this block represents.
        :param channellabel: Human-readable channel label (e.g. "left", "channel 3").
        :param channelcount: Value for the <channelcount> tag.
        :param layout: Value for the <layout> tag (e.g. "stereo", "mono").
        :return: An ElementTree Element representing the audio.
        """
        metadata: VideoMetadata = self.video_metadata_index.get(video_source_filename)

        audio = Element("audio")

        # <samplecharacteristics>
        samplecharacteristics = SubElement(audio, "samplecharacteristics")
        SubElement(samplecharacteristics, "depth").text = str(metadata.audio_depth)
        SubElement(samplecharacteristics, "samplerate").text = str(metadata.audio_samplerate)

        SubElement(audio, "channelcount").text = str(channelcount)
        SubElement(audio, "layout").text = str(layout)

        # <audiochannel>
        audiochannel = SubElement(audio, "audiochannel")
        SubElement(audiochannel, "sourcechannel").text = str(sourcechannel)
        SubElement(audiochannel, "channellabel").text = str(channellabel)

        return audio

    def _build_media_element(self, video_source_filename: str) -> Element:
        """
        Create a <media> element as subelement of the <file> element.

        Dispatches on the source file's audio_layout_mode to pick the right
        per-channel <audio> blocks. See AudioLayout for the two strategies.

        :param video_source_filename: The source video filename.
        :return: An ElementTree Element representing the media.
        """
        metadata: VideoMetadata = self.video_metadata_index.get(video_source_filename)

        media = Element("media")

        # <video>
        video = SubElement(media, "video")
        video_sample_chars = SubElement(video, "samplecharacteristics")
        video_sample_chars.append(build_rate_element(timebase=metadata.timebase, ntsc=metadata.ntsc))
        SubElement(video_sample_chars, "width").text = str(metadata.width)
        SubElement(video_sample_chars, "height").text = str(metadata.height)
        SubElement(video_sample_chars, "anamorphic").text = str(metadata.anamorphic).upper()
        SubElement(video_sample_chars, "pixelaspectratio").text = str(metadata.pixelaspectratio)
        SubElement(video_sample_chars, "fielddominance").text = str(metadata.fielddominance)

        # <audio> per source channel; channel count and layout depend on the layout mode
        if metadata.audio_layout_mode == AudioLayout.STEREO_PAIR:
            channels = [(1, "left"), (2, "right")]
            channelcount, layout = 2, "stereo"
        else:  # MONO_PER_CHANNEL
            channels = [(i, f"channel {i}") for i in range(1, metadata.audio_track_count + 1)]
            channelcount, layout = 1, "mono"

        for sourcechannel, channellabel in channels:
            media.append(
                self._build_media_audio_element(
                    video_source_filename=video_source_filename,
                    sourcechannel=sourcechannel,
                    channellabel=channellabel,
                    channelcount=channelcount,
                    layout=layout,
                )
            )

        return media
