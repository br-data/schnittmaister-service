# Video file extensions Gemini reads directly (https://ai.google.dev/gemini-api/docs/video-understanding).
# Other formats (e.g. MXF, MKV) have to be converted to one of these before, e.g. with ffmpeg.
GEMINI_SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mpg",
    ".mpeg",
    ".mov",
    ".qt",
    ".webm",
    ".flv",
    ".wmv",
    ".3gp",
    ".3gpp",
    ".avi",
}

# Default MIME type for video files when the type cannot be inferred from the extension
DEFAULT_VIDEO_MIME_TYPE: str = "video/mp4"
