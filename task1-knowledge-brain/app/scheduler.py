"""Standalone daily refresh scheduler; it is never started by the API process."""

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import get_settings
from app.crawler import _run_cli


def seconds_until_next_refresh(now: datetime, utc_hour: int) -> float:
    if not 0 <= utc_hour <= 23:
        raise ValueError("DAILY_REFRESH_UTC_HOUR must be between 0 and 23")
    current = now.astimezone(timezone.utc)
    target = current.replace(hour=utc_hour, minute=0, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return (target - current).total_seconds()


async def run_daily_scheduler() -> None:
    settings = get_settings()
    while True:
        await asyncio.sleep(seconds_until_next_refresh(datetime.now(timezone.utc), settings.daily_refresh_utc_hour))
        try:
            await _run_cli(None)
        except Exception as exc:
            # Keep the scheduler alive; the crawler checkpoint preserves page progress.
            print(f"Daily knowledge refresh failed ({type(exc).__name__}); retry on the next scheduled run.")


if __name__ == "__main__":
    asyncio.run(run_daily_scheduler())
