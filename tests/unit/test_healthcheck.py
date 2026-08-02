import tempfile
import unittest
from pathlib import Path

from src.support.healthcheck import (
    check_health,
    record_health,
    reset_health,
)


class HealthcheckTests(unittest.TestCase):
    def test_record_creates_heartbeat_and_check_reports_healthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "nested" / "heartbeat"

            record_health(heartbeat)
            modified_at = heartbeat.stat().st_mtime
            healthy, message = check_health(
                heartbeat,
                now=modified_at + 1,
                max_age_seconds=90,
            )

            self.assertTrue(healthy)
            self.assertIn("healthy", message)

    def test_missing_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "heartbeat"

            healthy, message = check_health(heartbeat)

            self.assertFalse(healthy)
            self.assertIn("does not exist", message)

    def test_stale_heartbeat_is_unhealthy(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "heartbeat"
            record_health(heartbeat)
            modified_at = heartbeat.stat().st_mtime

            healthy, message = check_health(
                heartbeat,
                now=modified_at + 91,
                max_age_seconds=90,
            )

            self.assertFalse(healthy)
            self.assertIn("stale", message)

    def test_reset_removes_existing_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            heartbeat = Path(directory) / "heartbeat"
            record_health(heartbeat)

            reset_health(heartbeat)

            self.assertFalse(heartbeat.exists())


if __name__ == "__main__":
    unittest.main()
