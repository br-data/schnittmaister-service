from pydantic import BaseModel


class GeminiVideoClipProposal(BaseModel):
    """
    A proposed clip to include in a video sequence.

    This class is used for the structured output of the Gemini model.

    :cvar source_filename: Name of video file this clip comes from
    :cvar start_timestamp: Start timestamp of the clip in the source video, MM:SS.sss or H:MM:SS.sss
    :cvar end_timestamp: End timestamp of the clip in the source video, MM:SS.sss or H:MM:SS.sss
    :cvar label: Defined in the prompt
    :cvar description: Defined in the prompt
    :cvar reasoning: Defined in the prompt
    """

    source_filename: str
    start_timestamp: str | None = None
    end_timestamp: str | None = None
    label: str | None = None
    description: str | None = None
    reasoning: str | None = None


class VideoClipProposal(GeminiVideoClipProposal):
    """
    A proposed video clip with additional start and end frame information.

    This class extends GeminiVideoClipProposal to include the start and end frame numbers,
    which are based on the FPS (frames per second) of the video.

    :cvar in_frame: Start frame number in the source video.
    :cvar out_frame: End frame number in the source video (exclusive).
    """

    in_frame: int
    out_frame: int


class GeminiVideoClipProposalList(BaseModel):
    """
    A sequence of video clip items proposed by Gemini.

    This class is used for the structured output of the Gemini model.

    :cvar clips: Ordered list of GeminiVideoClipProposal objects representing the timeline.
    """

    clips: list[GeminiVideoClipProposal]
