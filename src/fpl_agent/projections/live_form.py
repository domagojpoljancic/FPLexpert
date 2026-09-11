"""Fetch per-GW live points for early-season haul-resistant projections."""

from __future__ import annotations

import logging
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


def load_recent_points_by_player(
    bootstrap: dict[str, Any],
    *,
    client: FplClient | None = None,
    offline: bool = False,
) -> dict[int, list[float]]:
    """Load finished-GW live points while the season is still haul-sensitive.

    Uses one `/api/event/{gw}/live/` call per finished gameweek (typically ≤5).
    Returns ``{}`` offline, preseason, after the early-season window, or on fetch errors.
    """
    played = finished_gameweeks(bootstrap)
    if offline or played <= 0 or played >= EARLY_SEASON_GWS:
        return {}

    event_ids = finished_event_ids(bootstrap)
    if not event_ids:
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
                logger.warning("live points unavailable for GW%s; skipping winsorized form", gw)
                return {}
    finally:
        if own:
            http.close()

    if len(live_by_gw) != len(event_ids):
        return {}
    return merge_live_points_by_gw(live_by_gw)
