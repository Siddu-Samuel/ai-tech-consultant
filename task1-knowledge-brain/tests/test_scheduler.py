import unittest
from datetime import datetime, timezone

from app.scheduler import seconds_until_next_refresh


class SchedulerTests(unittest.TestCase):
    def test_next_run_is_daily_at_configured_utc_hour(self) -> None:
        current = datetime(2026, 10, 18, 1, 30, tzinfo=timezone.utc)
        self.assertEqual(seconds_until_next_refresh(current, 2), 1800)
        at_run_time = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)
        self.assertEqual(seconds_until_next_refresh(at_run_time, 2), 86400)

    def test_invalid_utc_hour_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            seconds_until_next_refresh(datetime.now(timezone.utc), 24)


if __name__ == "__main__":
    unittest.main()
