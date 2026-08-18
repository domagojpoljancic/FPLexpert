"""Deadline-relative cadence: daily = prices; full review ~1 day before deadline."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fpl_agent.config import CadenceSettings
from fpl_agent.suggest import next_gameweek


class PredeadlineGate(StrEnum):
    IN_WINDOW = "in_window"
    TOO_EARLY = "too_early"
    CLOSER_THAN_INTENDED = "closer_than_intended"
    DEADLINE_UNKNOWN = "deadline_unknown"
    FORCED = "forced"


def parse_deadline(raw: object) -> datetime | None:
    if not raw:
        return None
    text = str(raw).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def next_deadline(bootstrap: dict[str, Any]) -> tuple[int, datetime | None]:
    gw = next_gameweek(bootstrap)
    for event in bootstrap.get("events") or []:
        if int(event.get("id") or 0) == gw:
            return gw, parse_deadline(event.get("deadline_time"))
    return gw, None


def hours_until(deadline: datetime | None, *, now: datetime | None = None) -> float | None:
    if deadline is None:
        return None
    now = now or datetime.now(UTC)
    return (deadline - now).total_seconds() / 3600.0


def predeadline_gate(
    hours_to_deadline: float | None,
    settings: CadenceSettings,
    *,
    force: bool = False,
) -> tuple[bool, PredeadlineGate]:
    if force:
        return True, PredeadlineGate.FORCED
    if hours_to_deadline is None:
        return True, PredeadlineGate.DEADLINE_UNKNOWN
    if hours_to_deadline > settings.predeadline_early_hours:
        return False, PredeadlineGate.TOO_EARLY
    if hours_to_deadline < settings.predeadline_late_hours:
        return True, PredeadlineGate.CLOSER_THAN_INTENDED
    return True, PredeadlineGate.IN_WINDOW
