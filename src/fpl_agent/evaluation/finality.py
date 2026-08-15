"""Official result finality policy for 2026/27."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")


def provisional_until(final_match_kickoff_or_end: datetime) -> datetime:
    """Lock at 09:00 UK on the day after the final match of the gameweek."""
    local = final_match_kickoff_or_end.astimezone(UK)
    day_after = (local + timedelta(days=1)).date()
    return datetime(day_after.year, day_after.month, day_after.day, 9, 0, tzinfo=UK)


def is_final(*, now: datetime, final_match_end: datetime, data_checked: bool) -> bool:
    return now >= provisional_until(final_match_end) and data_checked
