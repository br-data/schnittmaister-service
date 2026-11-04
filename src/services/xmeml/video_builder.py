from xml.etree.ElementTree import Element, SubElement

from src.config.xmeml_config import CodecDefaults, VideoDefaults
from src.models.gemini_output import VideoClipProposal
from src.models.video_metadata import VideoMetadataIndex
from src.services.xmeml.file_element_builder import FileElementBuilder
from src.services.xmeml.shared_elements import build_rate_element, timeline_positions
from src.services.xmeml.video_clipitem_builder import VideoClipitemBuilder

VIDEO_DEFAULTS = VideoDefaults()
CODEC_DEFAULTS = CodecDefaults()


class VideoBuilder:
    """Builds the <video> section within the <media> element of the XMEML structure."""

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
        file_element_builder: FileElementBuilder,
        video_clip_proposals: list[VideoClipProposal],
    ) -> None:
        """
        Initialize the VideoBuilder.

        :param video_metadata_index: Metadata index for all video files.
        :param file_element_builder: Builder responsible for creating <file> elements.
        :param video_clip_proposals: Ordered list of Gemini-generated video clip proposals.
        """
        self.video_metadata_index = video_metadata_index
        self.video_clip_proposals = video_clip_proposals
        self.video_clipitem_builder = VideoClipitemBuilder(
            video_metadata_index=video_metadata_index,
            file_element_builder=file_element_builder,
        )

    def build_format_element(self, timebase: int, ntsc: bool, width: int, height: int) -> Element:
        """
        Create the <format> element of the sequence.

        Its <samplecharacteristics> take rate and size from the arguments, the rest from VideoDefaults and
        CodecDefaults.

        :param timebase: Frame rate of the sequence, rounded to a whole number (e.g. 25 for PAL).
        :param ntsc: Whether the frame rate is 1000/1001 of the timebase.
        :param width: Width of the sequence in pixels.
        :param height: Height of the sequence in pixels.
        :return: An ElementTree Element for <format>.
        """
        format_el = Element("format")
        samplechar = SubElement(format_el, "samplecharacteristics")

        # <rate>
        samplechar.append(build_rate_element(timebase=timebase, ntsc=ntsc))

        # <codec>
        codec = SubElement(samplechar, "codec")
        SubElement(codec, "name").text = CODEC_DEFAULTS.name

        appspecificdata = SubElement(codec, "appspecificdata")
        SubElement(appspecificdata, "appname").text = CODEC_DEFAULTS.appname
        SubElement(appspecificdata, "appmanufacturer").text = CODEC_DEFAULTS.appmanufacturer
        SubElement(appspecificdata, "appversion").text = str(CODEC_DEFAULTS.appversion)

        data = SubElement(appspecificdata, "data")
        qtcodec = SubElement(data, "qtcodec")
        SubElement(qtcodec, "codecname").text = CODEC_DEFAULTS.name
        SubElement(qtcodec, "codectypename").text = CODEC_DEFAULTS.codectypename
        SubElement(qtcodec, "codectypecode").text = CODEC_DEFAULTS.codectypecode
        SubElement(qtcodec, "codecvendorcode").text = CODEC_DEFAULTS.codecvendorcode
        SubElement(qtcodec, "spatialquality").text = str(CODEC_DEFAULTS.spatialquality)
        SubElement(qtcodec, "temporalquality").text = str(CODEC_DEFAULTS.temporalquality)
        SubElement(qtcodec, "keyframerate").text = str(CODEC_DEFAULTS.keyframerate)
        SubElement(qtcodec, "datarate").text = str(CODEC_DEFAULTS.datarate)

        SubElement(samplechar, "width").text = str(width)
        SubElement(samplechar, "height").text = str(height)
        SubElement(samplechar, "anamorphic").text = str(VIDEO_DEFAULTS.anamorphic).upper()
        SubElement(samplechar, "pixelaspectratio").text = VIDEO_DEFAULTS.pixelaspectratio
        SubElement(samplechar, "fielddominance").text = VIDEO_DEFAULTS.fielddominance
        SubElement(samplechar, "colordepth").text = str(VIDEO_DEFAULTS.colordepth)

        return format_el

    def build_track_from_video_clip_proposals(self) -> Element:
        """
        Create a <track> element containing all <clipitem> elements derived from Gemini's proposals.

        :return: An ElementTree Element for the <track>.
        """
        track = Element("track")
        track.set("TL.SQTrackShy", "0")
        track.set("TL.SQTrackExpandedHeight", "25")
        track.set("TL.SQTrackExpanded", "0")
        track.set("MZ.TrackTargeted", "1")

        # Links to the same number of audio tracks as AudioBuilder.build_audio_element emits
        audio_track_count = self.video_metadata_index.values()[0].audio_track_count

        positions = timeline_positions(self.video_clip_proposals, self.video_metadata_index)
        total_clips = len(self.video_clip_proposals)

        for i, (clip, (start_frame, end_frame)) in enumerate(zip(self.video_clip_proposals, positions, strict=True)):
            clipitem_element = self.video_clipitem_builder.build_video_clipitem_element(
                video_clipitem_nr=i + 1,
                source_filename=clip.source_filename,
                in_frame=clip.in_frame,
                out_frame=clip.out_frame,
                start_frame=start_frame,
                end_frame=end_frame,
                total_video_clip_count=total_clips,
                audio_track_count=audio_track_count,
                label=clip.label or "",
                description=clip.description or "",
                reasoning=clip.reasoning or "",
            )
            track.append(clipitem_element)

        SubElement(track, "enabled").text = "TRUE"
        SubElement(track, "locked").text = "FALSE"

        return track

    def build_video_element(self) -> Element:
        """
        Create the full <video> element for the <media> section, including format and track.

        :return: An ElementTree Element for the <video> section.
        """
        video_el = Element("video")

        # <format> of the sequence: size and rate of the job's first video
        first_video = self.video_metadata_index.values()[0]
        video_el.append(
            self.build_format_element(
                timebase=first_video.timebase,
                ntsc=first_video.ntsc,
                width=first_video.width,
                height=first_video.height,
            )
        )

        # <track> with one clipitem per video clip proposal
        video_el.append(self.build_track_from_video_clip_proposals())

        return video_el
