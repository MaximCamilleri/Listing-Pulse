import logging
import tempfile
import unittest
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from src.config.settings import settings
from src.support.logger import configure_logging


class LoggerTests(unittest.TestCase):
    def setUp(self):
        self.original_log_directory = settings.log_directory
        self.original_log_retention_days = settings.log_retention_days
        self.root_logger = logging.getLogger()
        self.original_handlers = list(self.root_logger.handlers)
        self.root_logger.handlers.clear()
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings.log_directory = Path(self.temporary_directory.name) / "logs"
        settings.log_retention_days = 7

    def tearDown(self):
        for handler in self.root_logger.handlers:
            handler.close()
        self.root_logger.handlers = self.original_handlers
        settings.log_directory = self.original_log_directory
        settings.log_retention_days = self.original_log_retention_days
        self.temporary_directory.cleanup()

    def test_configure_logging_adds_daily_rotating_file_handler(self):
        configure_logging()

        file_handlers = [
            handler
            for handler in self.root_logger.handlers
            if isinstance(handler, TimedRotatingFileHandler)
        ]

        self.assertEqual(len(file_handlers), 1)
        self.assertEqual(file_handlers[0].backupCount, 7)
        self.assertTrue(file_handlers[0].utc)
        self.assertEqual(
            Path(file_handlers[0].baseFilename),
            settings.log_directory.resolve() / "application.log",
        )

    def test_configure_logging_is_idempotent(self):
        configure_logging()
        configure_logging()

        self.assertEqual(len(self.root_logger.handlers), 2)


if __name__ == "__main__":
    unittest.main()
