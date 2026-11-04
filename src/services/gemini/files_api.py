"""Videos in the Gemini Files API: upload, wait until they are processed, and delete them."""

import logging
import time

from google import genai
from google.genai.types import File, FileState

from src.models.video_metadata import VideoMetadata, VideoMetadataIndex
from src.services.gemini.gemini import GEMINI_CONFIG


def upload_videos(client: genai.Client, video_metadata_index: VideoMetadataIndex) -> None:
    """
    Upload the videos of a job to the Files API and wait until Gemini has processed them.

    All videos are uploaded first and then waited for, so Gemini processes the earlier videos while the
    later ones are still uploading.

    Sets gemini_file_name on every VideoMetadata right after its upload, so delete_files also finds a file
    whose processing fails or whose successor fails, and gemini_file_uri and mime_type once it is processed.

    :param client: Gemini client.
    :param video_metadata_index: Videos of the job.
    :raises TimeoutError: If an uploaded video is not ACTIVE within the configured time after its upload.
    :raises ValueError: If the Files API fails to process a video.
    :raises ClientError | ServerError: If the Files API rejects a request.
    """
    uploads: list[tuple[VideoMetadata, File, float]] = []
    for metadata in video_metadata_index.values():
        logging.info(f"Uploading '{metadata.filename}' to the Gemini Files API...")
        started = time.monotonic()
        file = client.files.upload(file=metadata.local_path, config={"display_name": metadata.filename})
        metadata.gemini_file_name = _name(file)
        uploaded = time.monotonic()
        logging.info(f"'{metadata.filename}' uploaded in {uploaded - started:.0f}s")
        uploads.append((metadata, file, uploaded))

    for metadata, file, uploaded in uploads:
        file = _wait_until_active(client, file, uploaded)
        logging.info(f"'{metadata.filename}' processed by Gemini {time.monotonic() - uploaded:.0f}s after its upload")
        _apply_file(metadata, file)


def delete_files(client: genai.Client, video_metadata_index: VideoMetadataIndex) -> None:
    """
    Delete the uploaded videos of a job from the Files API; a failure is logged, not raised.

    Files expire after 48 hours anyway, so a failed deletion only leaves the file around until then.

    :param client: Gemini client.
    :param video_metadata_index: Videos of the job; those with a gemini_file_name were uploaded.
    """
    for name in [metadata.gemini_file_name for metadata in video_metadata_index.values() if metadata.gemini_file_name]:
        try:
            client.files.delete(name=name)
            logging.info(f"Deleted '{name}' from the Gemini Files API")
        except Exception as e:
            logging.warning(f"Could not delete '{name}' from the Gemini Files API: {type(e).__name__}: {e}")


def _wait_until_active(client: genai.Client, file: File, uploaded: float) -> File:
    """
    Poll a file until the Files API has processed it.

    :param client: Gemini client.
    :param file: The file as returned by the upload.
    :param uploaded: time.monotonic() when the upload finished; the timeout counts from there.
    :raises TimeoutError: If the file is not ACTIVE within the configured time after its upload.
    :raises ValueError: If processing failed.
    :return: The file in state ACTIVE, with its metadata.
    """
    deadline = uploaded + GEMINI_CONFIG.file_processing_timeout_seconds
    while file.state == FileState.PROCESSING:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Gemini did not finish processing '{_name(file)}' within "
                f"{GEMINI_CONFIG.file_processing_timeout_seconds}s"
            )
        time.sleep(GEMINI_CONFIG.file_processing_poll_seconds)
        file = client.files.get(name=_name(file))
    if file.state != FileState.ACTIVE:
        error = file.error.message if file.error else "no error details"
        raise ValueError(f"Gemini could not process '{_name(file)}': state {file.state}, {error}")
    return file


def _apply_file(metadata: VideoMetadata, file: File) -> None:
    """
    Store the Files API data of a processed file on its VideoMetadata.

    :param metadata: Metadata of the video.
    :param file: The processed file.
    :raises ValueError: If the file has no URI.
    """
    if not file.uri:
        raise ValueError(f"Gemini file '{_name(file)}' has no URI")
    metadata.gemini_file_uri = file.uri
    metadata.mime_type = file.mime_type or metadata.mime_type
    logging.info(f"'{metadata.filename}' is ready in the Gemini Files API as {metadata.gemini_file_name}")


def _name(file: File) -> str:
    """
    Resource name of a file.

    :param file: The file.
    :return: Its name, e.g. "files/abc123xyz".
    """
    return file.name or ""
