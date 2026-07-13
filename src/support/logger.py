import logging
import sys
import time
from logging.handlers import TimedRotatingFileHandler

from src.config.settings import settings


LOG_FORMAT = (
    "%(asctime)sZ %(levelname)s [%(name)s] "
    "%(filename)s:%(lineno)d - %(message)s"
)
LOG_FILE_NAME = "application.log"
_APPLICATION_HANDLER_ATTRIBUTE = "_upbit_scraper_handler"


class UTCFormatter(logging.Formatter):
    converter = time.gmtime


def configure_logging() -> None:
    """
    Configure process-wide application logging.

    This is intentionally idempotent so test harnesses and runtime entrypoints can
    call it without duplicating handlers.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    application_handlers = [
        handler
        for handler in root_logger.handlers
        if getattr(handler, _APPLICATION_HANDLER_ATTRIBUTE, False)
    ]
    if application_handlers:
        for handler in application_handlers:
            handler.setLevel(settings.log_level)
        return

    formatter = UTCFormatter(LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.log_level)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _APPLICATION_HANDLER_ATTRIBUTE, True)

    settings.log_directory.mkdir(parents=True, exist_ok=True)
    file_handler = TimedRotatingFileHandler(
        filename=settings.log_directory / LOG_FILE_NAME,
        when="midnight",
        interval=1,
        backupCount=settings.log_retention_days,
        encoding="utf-8",
        utc=True,
    )
    file_handler.setLevel(settings.log_level)
    file_handler.setFormatter(formatter)
    setattr(file_handler, _APPLICATION_HANDLER_ATTRIBUTE, True)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
