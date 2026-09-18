"""Fetch per-GW live points for early-season haul-resistant projections."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fpl_agent.evaluation.scorecard import points_from_live_payload
from fpl_agent.ingestion.client import FplClient, LiveAdapter
from fpl_agent.projections.preseason import (
    EARLY_SEASON_GWS,
    finished_event_ids,
    finished_gameweeks,
    merge_live_points_by_gw,
)

logger = logging.getLogger(__name__)

CACHE_PATH = Path("data/cache/live-gw-points.json")


def _read_cache(event_ids: list[int], *, path: Path = CACHE_PATH) -> dict[int, list[float]] | None:
    """Return cached points only when they cover exactly the finished event set."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("live-gw-points cache unreadable at %s", path)
        return None
    cached_ids = [int(x) for x in (payload.get("event_ids") or [])]
    if cached_ids != event_ids:
        return None
    by_player = payload.get("points_by_player") or {}
    try:
        return {int(pid): [float(p) for p in pts] for pid, pts in by_player.items()}
    except (TypeError, ValueError):
        logger.warning("live-gw-points cache malformed at %s", path)
        return None


def _write_cache(
    event_ids: list[int],
    points: dict[int, list[float]],
    *,
    path: Path = CACHE_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_ids": list(event_ids),
        "points_by_player": {str(pid): pts for pid, pts in sorted(points.items())},
    }
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def load_recent_points_by_player(
    bootstrap: dict[str, Any],
    *,
    client: FplClient | None = None,
    offline: bool = False,
    cache_path: Path = CACHE_PATH,
) -> dict[int, list[float]]:
    """Load finished-GW live points while the season is still haul-sensitive.

    Online: one `/api/event/{gw}/live/` call per finished gameweek (typically ≤5),
    then refresh ``data/cache/live-gw-points.json``.

    Offline / fetch failure: reuse that cache when it matches the finished event ids.
    Returns ``{}`` preseason, after the early-season window, or when nothing is available.
    """
    played = finished_gameweeks(bootstrap)
    if played <= 0 or played >= EARLY_SEASON_GWS:
        return {}

    event_ids = finished_event_ids(bootstrap)
    if not event_ids:
        return {}

    if offline:
        cached = _read_cache(event_ids, path=cache_path)
        if cached is not None:
            logger.info("using cached live GW points for haul resistance (%s GWs)", len(event_ids))
            return cached
        logger.warning("offline: no live-gw-points cache for events %s; haul resistance skipped", event_ids)
        return {}

    own = client is None
    http = client or FplClient()
    live_by_gw: dict[int, dict[int, int | float]] = {}
    try:
        adapter = LiveAdapter(http)
        for gw in event_ids:
            try:
                payload = adapter.fetch(gw).payload
                live_by_gw[gw] = points_from_live_payload(payload)
            except Exception:  # noqa: BLE001 — projections must degrade without live form
                logger.warning("live points unavailable for GW%s; trying cache", gw)
                cached = _read_cache(event_ids, path=cache_path)
                return cached or {}
    finally:
        if own:
            http.close()

    if len(live_by_gw) != len(event_ids):
        cached = _read_cache(event_ids, path=cache_path)
        return cached or {}

    merged = merge_live_points_by_gw(live_by_gw)
    try:
        _write_cache(event_ids, merged, path=cache_path)
    except OSError:
        logger.warning("could not write live-gw-points cache to %s", cache_path)
    return merged
