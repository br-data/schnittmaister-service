import json
import logging
from logging import LogRecord
from pathlib import Path
from typing import Callable

from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    """
    Logging settings from the environment or ``.env``; environment variables win over the file.

    :param log_level: Level of the service's own log lines (``LOG_LEVEL``: DEBUG, INFO, WARNING, ERROR).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = "INFO"


def filter_maker(level: str) -> Callable:
    """
    Create a logging filter that only allows log records with a level less than or equal to the specified level.

    Used in logging_config.json so the stdout handler gets everything up to WARNING and errors go
    only to the stderr handler.

    :param level: The logging level to filter by, e.g., 'DEBUG', 'INFO', 'WARNING', etc.
    :return: A function that can be used as a logging filter.
    """
    level_int = getattr(logging, level)

    def filter(record: LogRecord) -> bool:
        return record.levelno <= level_int

    return filter


with open(Path(__file__).with_name("logging_config.json")) as f:
    LOGGING_CONFIG = json.load(f)

LOGGING_CONFIG["handlers"]["stdout"]["level"] = LoggingSettings().log_level.upper()
