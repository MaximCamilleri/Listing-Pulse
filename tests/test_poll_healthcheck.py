import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config.settings import settings
from src.support.poll_healthcheck import (
    check_poll_health,
    poll_healthcheck_max_age_seconds,
    record_poll_success,
    reset_poll_health,
)


class PollHealthcheckTests(unittest.TestCase):
    def test_record_poll_success_creates_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "nested" / "poll-heartbeat"

            record_poll_success(heartbeat)

            self.assertTrue(heartbeat.is_file())

    def test_missing_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "poll-heartbeat"

            healthy, message = check_poll_health(heartbeat)

            self.assertFalse(healthy)
            self.assertIn("does not exist", message)

    def test_fresh_heartbeat_is_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "poll-heartbeat"
            heartbeat.touch()
            modified_at = heartbeat.stat().st_mtime

            healthy, _ = check_poll_health(heartbeat, now=modified_at + 1)

            self.assertTrue(healthy)

    def test_stale_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "poll-heartbeat"
            heartbeat.touch()
            modified_at = heartbeat.stat().st_mtime

            with (
                patch.object(settings, "scraper_cooldown", 10.0),
                patch.object(settings, "scraper_cooldown_offset", 2.5),
                patch.object(settings, "scraper_timeout", 5.0),
                patch.object(settings, "poll_healthcheck_grace_seconds", 15.0),
            ):
                healthy, message = check_poll_health(
                    heartbeat,
                    now=modified_at + 33,
                )

            self.assertFalse(healthy)
            self.assertIn("stale", message)

    def test_max_age_uses_poll_schedule_and_grace(self):
        with (
            patch.object(settings, "scraper_cooldown", 10.0),
            patch.object(settings, "scraper_cooldown_offset", -2.5),
            patch.object(settings, "scraper_timeout", 5.0),
            patch.object(settings, "poll_healthcheck_grace_seconds", 15.0),
        ):
            self.assertEqual(poll_healthcheck_max_age_seconds(), 32.5)

    def test_reset_removes_existing_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "poll-heartbeat"
            heartbeat.touch()

            reset_poll_health(heartbeat)

            self.assertFalse(heartbeat.exists())


if __name__ == "__main__":
    unittest.main()
