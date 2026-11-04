from xml.etree.ElementTree import Element, SubElement

from src.config.xmeml_config import AudioDefaults, AudioLayout
from src.models.gemini_output import VideoClipProposal
from src.models.user_messages import add_user_warning
from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.xmeml.audio_clipitem_builder import AudioClipitemBuilder
from src.services.xmeml.file_element_builder import FileElementBuilder
from src.services.xmeml.shared_elements import timeline_positions

AUDIO_DEFAULTS = AudioDefaults()


class AudioBuilder:
    """Builds the <audio> section within the <media> element of the XMEML structure."""

    def __init__(
        self,
        video_metadata_index: VideoMetadataIndex,
        file_element_builder: FileElementBuilder,
        video_clip_proposals: list[VideoClipProposal],
    ) -> None:
        """
        Initialize the AudioBuilder.

        :param video_metadata_index: Metadata index for all source files.
        :param file_element_builder: Builder responsible for <file> references.
        :param video_clip_proposals: Ordered list of video clip proposals.
        """
        self.video_metadata_index = video_metadata_index
        self.video_clip_proposals = video_clip_proposals
        self.audio_clipitem_builder = AudioClipitemBuilder(
            video_metadata_index=video_metadata_index,
            file_element_builder=file_element_builder,
        )

    def build_format_element(self) -> Element:
        """
        Create the <format> element for the <audio> section, with the AudioDefaults depth and sample rate.

        :return: An ElementTree Element containing audio format defaults.
        """
        format_el = Element("format")
        samplechar = SubElement(format_el, "samplecharacteristics")
        SubElement(samplechar, "depth").text = str(AUDIO_DEFAULTS.depth)
        SubElement(samplechar, "samplerate").text = str(AUDIO_DEFAULTS.samplerate)
        return format_el

    def build_outputs_element(self) -> Element:
        """
        Create the <outputs> element: one output group with one channel per output channel of the sequence.

        :return: An ElementTree Element containing audio output group structure.
        """
        outputs = Element("outputs")
        for i in range(AUDIO_DEFAULTS.numOutputChannels):
            group = SubElement(outputs, "group")
            SubElement(group, "index").text = str(i + 1)
            SubElement(group, "numchannels").text = "1"
            SubElement(group, "downmix").text = "0"
            channel = SubElement(group, "channel")
            SubElement(channel, "index").text = str(i + 1)
        return outputs

    @staticmethod
    def _resolve_output_channel_index(trackindex: int, layout_mode: AudioLayout) -> int:
        """
        Map a 1-based audio track index to its <outputchannelindex> value.

        STEREO_PAIR: track 1 → output 1 (left), track 2 → output 2 (right).
            Each timeline track routes to its corresponding stereo bus channel.

        MONO_PER_CHANNEL: dual-mono panning — odd tracks (1, 3, 5, 7) route to
            output 1 (left), even tracks (2, 4, 6, 8) route to output 2 (right).
            This gives the editor every source channel as a separate timeline
            track, alternately panned, so they can audition all channels and
            pick which to keep without rerouting.

        :param trackindex: 1-based track number on the timeline.
        :param layout_mode: Audio layout of the timeline.
        :return: The output channel of the track (1 = left, 2 = right).
        """
        if layout_mode == AudioLayout.STEREO_PAIR:
            return trackindex
        return 1 if trackindex % 2 == 1 else 2

    def build_audio_track(
        self,
        trackindex: int,
        starting_clipitem_nr: int,
        outputchannelindex: int,
        audio_track_count: int,
    ) -> Element:
        """
        Create an <audio><track> element for one timeline audio track.

        Each track aggregates one mono <clipitem> per video clip proposal,
        all reading from the same source channel (= trackindex on the source file).

        :param trackindex: 1-based track number on the timeline. Also used as
            the <sourcetrack><trackindex> on each contained clipitem, i.e. the
            channel of the source file this track plays.
        :param starting_clipitem_nr: Global clipitem ID at which the audio
            section starts (immediately after the video clipitems). Each track
            owns a contiguous block of N IDs, where N = number of video clip proposals.
        :param outputchannelindex: Value for the <outputchannelindex> tag (1 = left,
            2 = right). Computed by _resolve_output_channel_index based on layout.
        :param audio_track_count: Total number of audio tracks in the sequence.
            Threaded down to the link builder so each clipitem links to all
            its sibling audio clipitems across tracks.
        :return: An ElementTree Element representing one audio <track>.
        """
        track = Element("track")
        track.set("TL.SQTrackAudioKeyframeStyle", "0")
        track.set("TL.SQTrackShy", "0")
        track.set("TL.SQTrackExpandedHeight", "25")
        track.set("TL.SQTrackExpanded", "0")
        track.set("MZ.TrackTargeted", "1")
        track.set("PannerCurrentValue", "0.5")
        track.set("PannerIsInverted", "true")
        track.set("PannerStartKeyframe", "-91445760000000000,0.5,0,0,0,0,0,0")
        track.set("PannerName", "Balance")
        track.set("currentExplodedTrackIndex", "0")
        track.set("totalExplodedTrackCount", "1")
        track.set("premiereTrackType", "Mono")

        # Each track owns a block of total_video_clip_count clipitem IDs, track 1 first
        total_video_clip_count = len(self.video_clip_proposals)
        current_clipitem_nr = starting_clipitem_nr + (trackindex - 1) * total_video_clip_count

        positions = timeline_positions(self.video_clip_proposals, self.video_metadata_index)

        for i, (clip, (start_frame, end_frame)) in enumerate(zip(self.video_clip_proposals, positions, strict=True)):
            audio_clipitem = self.audio_clipitem_builder.build_audio_clipitem_element(
                clipitem_nr=current_clipitem_nr + i,
                source_filename=clip.source_filename,
                in_frame=clip.in_frame,
                out_frame=clip.out_frame,
                start_frame=start_frame,
                end_frame=end_frame,
                video_clipitem_nr=i + 1,
                total_video_clip_count=total_video_clip_count,
                trackindex=trackindex,
                audio_track_count=audio_track_count,
            )
            track.append(audio_clipitem)

        SubElement(track, "enabled").text = "TRUE"
        SubElement(track, "locked").text = "FALSE"
        SubElement(track, "outputchannelindex").text = str(outputchannelindex)

        return track

    def _warn_about_audio_the_sequence_does_not_fit(self, first_metadata: VideoMetadata) -> None:
        """
        Warn about videos of the cut whose sound the audio tracks of the sequence do not carry.

        The sequence takes the layout and track count of the job's first video (two stereo tracks if it has no
        sound). One warning names the videos without sound, another the videos with sound in another layout.

        :param first_metadata: Metadata of the job's first video, whose layout the sequence takes.
        """
        used_videos = [
            self.video_metadata_index.get(name)
            for name in dict.fromkeys(clip.source_filename for clip in self.video_clip_proposals)
        ]
        silent = [video for video in used_videos if video.audio_stream_count == 0]
        if silent:
            add_user_warning(
                ", ".join(f"'{video.filename}'" for video in silent)
                + " without sound: the audio tracks of its clips stay empty or offline in the editor."
            )

        sequence_layout = (first_metadata.audio_layout_mode, first_metadata.audio_track_count)
        different = [
            video
            for video in used_videos
            if video.audio_stream_count > 0 and (video.audio_layout_mode, video.audio_track_count) != sequence_layout
        ]
        if different:
            add_user_warning(
                f"The audio tracks of the sequence follow '{first_metadata.filename}' "
                f"({_layout_description(first_metadata)}); "
                + ", ".join(f"'{video.filename}' has {_layout_description(video)}" for video in different)
                + ". The sound of these clips may be missing or wrong in the editor."
            )

    def build_audio_element(self, starting_clipitem_nr: int) -> Element:
        """
        Create the full <audio> element with format, outputs, and timeline tracks.

        :param starting_clipitem_nr: Global clipitem ID at which the audio
            section starts (immediately after the video clipitems).
        :return: An ElementTree Element for the <audio> section.
        """
        # The first video's audio layout governs the timeline; clips of videos with another layout or without
        # sound point to channels their files may not have
        first_metadata = self.video_metadata_index.values()[0]
        self._warn_about_audio_the_sequence_does_not_fit(first_metadata)
        layout_mode = first_metadata.audio_layout_mode
        audio_track_count = first_metadata.audio_track_count

        audio_el = Element("audio")

        SubElement(audio_el, "numOutputChannels").text = str(AUDIO_DEFAULTS.numOutputChannels)

        # <format>
        audio_el.append(self.build_format_element())

        # <outputs>
        audio_el.append(self.build_outputs_element())

        # <track> per timeline audio track
        for trackindex in range(1, audio_track_count + 1):
            audio_el.append(
                self.build_audio_track(
                    trackindex=trackindex,
                    starting_clipitem_nr=starting_clipitem_nr,
                    outputchannelindex=self._resolve_output_channel_index(trackindex, layout_mode),
                    audio_track_count=audio_track_count,
                )
            )

        return audio_el


def _layout_description(metadata: VideoMetadata) -> str:
    """
    Describe the audio layout of a video as the sequence lays it out, for the user.

    :param metadata: Metadata of the video.
    :return: "stereo" or e.g. "8 mono tracks".
    """
    if metadata.audio_layout_mode == AudioLayout.STEREO_PAIR:
        return "stereo"
    return f"{metadata.audio_track_count} mono tracks"
