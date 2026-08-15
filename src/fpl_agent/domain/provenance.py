"""Freshness helpers for provenanced fields."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def ensure_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def is_fresh(
    observed_at: datetime | None,
    *,
    now: datetime,
    max_age: timedelta,
) -> bool:
    if observed_at is None:
        return False
    return ensure_aware(now) - ensure_aware(observed_at) <= max_age


def age_seconds(observed_at: datetime | None, *, now: datetime) -> float | None:
    if observed_at is None:
        return None
    return (ensure_aware(now) - ensure_aware(observed_at)).total_seconds()
