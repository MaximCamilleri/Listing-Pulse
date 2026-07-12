import logging
import sys
import time

from src.config.settings import settings


LOG_FORMAT = (
    "%(asctime)sZ %(levelname)s [%(name)s] "
    "%(filename)s:%(lineno)d - %(message)s"
)


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

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setLevel(settings.log_level)
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(settings.log_level)
    handler.setFormatter(UTCFormatter(LOG_FORMAT))

    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
