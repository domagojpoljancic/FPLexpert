"""Detect a skipped or late GitHub price-watch job from last-success.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_MAX_AGE_HOURS = 26.0
WATCHDOG_ISSUE_TITLE = "FPL price watchdog"


@dataclass(frozen=True)
class LivenessResult:
    stale: bool
    missing: bool
    age_hours: float | None
    last_utc: str | None
    message: str
    gameweek: int | None = None
    status: str | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "stale": self.stale,
            "missing": self.missing,
            "age_hours": None if self.age_hours is None else round(self.age_hours, 2),
            "last_utc": self.last_utc,
            "message": self.message,
            "gameweek": self.gameweek,
            "status": self.status,
            "issue_title": WATCHDOG_ISSUE_TITLE,
        }


def parse_last_success_utc(payload: dict[str, Any]) -> datetime | None:
    raw = str(payload.get("utc") or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evaluate_price_liveness(
    payload: dict[str, Any] | None,
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> LivenessResult:
    clock = now or datetime.now(UTC)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=UTC)
    if not payload:
        return LivenessResult(
            stale=True,
            missing=True,
            age_hours=None,
            last_utc=None,
            message="No last-success.json — the overnight price job has never recorded a success.",
        )
    stamp = parse_last_success_utc(payload)
    if stamp is None:
        return LivenessResult(
            stale=True,
            missing=True,
            age_hours=None,
            last_utc=str(payload.get("utc") or "") or None,
            message="last-success.json has no parseable utc timestamp.",
            gameweek=payload.get("gameweek") if isinstance(payload.get("gameweek"), int) else None,
            status=str(payload.get("status") or "") or None,
        )
    age = (clock.astimezone(UTC) - stamp).total_seconds() / 3600
    stale = age > max_age_hours
    gw = payload.get("gameweek") if isinstance(payload.get("gameweek"), int) else None
    status = str(payload.get("status") or "") or None
    if stale:
        message = (
            f"Price watch last succeeded {age:.1f}h ago (limit {max_age_hours:.0f}h). "
            "GitHub cron may have skipped or the job failed."
        )
    else:
        message = f"Price watch is fresh ({age:.1f}h since last success)."
    return LivenessResult(
        stale=stale,
        missing=False,
        age_hours=age,
        last_utc=stamp.strftime("%Y-%m-%dT%H:%MZ"),
        message=message,
        gameweek=gw,
        status=status,
    )


def load_last_success(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def evaluate_last_success_file(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> LivenessResult:
    return evaluate_price_liveness(
        load_last_success(path),
        now=now,
        max_age_hours=max_age_hours,
    )


def stale_after(*, hours: float = DEFAULT_MAX_AGE_HOURS) -> timedelta:
    return timedelta(hours=hours)
