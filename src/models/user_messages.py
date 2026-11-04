import logging
from contextvars import ContextVar


class UserMessages:
    """
    Collector for user-facing warnings and info messages during job processing.

    Created at the start of job processing and accessible via the context variable
    ``current_user_messages``. Functions deep in the call stack can add messages
    via the module-level helpers ``add_user_warning`` and ``add_user_info``.

    Usage::

        from src.models.user_messages import UserMessages, current_user_messages, add_user_warning, add_user_info

        # At the top of the processing pipeline:
        messages = UserMessages()
        token = current_user_messages.set(messages)

        # Anywhere in the call stack during processing:
        add_user_warning("Something went wrong but we continued")
        add_user_info("Model: gemini-3.8-flash")

    :ivar warnings: Non-fatal issues the user should be aware of.
    :ivar infos: Informational metadata about the job.
    """

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []


current_user_messages: ContextVar[UserMessages | None] = ContextVar("current_user_messages", default=None)


def add_user_warning(msg: str) -> None:
    """
    Log a warning and collect it as a user-facing message if a job context is active.

    :param msg: Warning text to surface to the user.
    """
    logging.warning(msg)
    messages = current_user_messages.get(None)
    if messages:
        messages.warnings.append(msg)


def add_user_info(msg: str) -> None:
    """
    Log an info message and collect it as a user-facing message if a job context is active.

    :param msg: Info text to surface to the user.
    """
    logging.info(msg)
    messages = current_user_messages.get(None)
    if messages:
        messages.infos.append(msg)
