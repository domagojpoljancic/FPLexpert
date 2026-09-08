"""Optional third-party price JSON (LiveFPL). Untrusted; never overrides now_cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from fpl_agent.prices.types import LikelihoodBand, PriceDirection

DEFAULT_LIVEFPL_PRICES_URL = "https://livefpl.us/api/prices.json"
MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT = 12.0


@dataclass(frozen=True)
class ExternalPriceRow:
    player_id: int
    name: str
    cost: float
    progress: float
    progress_tonight: float
    per_hour: float | None
    source: str = "livefpl"


@dataclass(frozen=True)
class MarketMover:
    player_id: int
    web_name: str
    direction: PriceDirection
    external_progress: float
    cost_millions: float | None
    band: LikelihoodBand
    owned: bool
    in_plan: bool
    source_label: str


def _band_from_abs_progress(
    abs_progress: float,
    *,
    watch: float,
    likely: float,
) -> LikelihoodBand:
    if abs_progress >= likely:
        return LikelihoodBand.LIKELY_NEXT_WINDOW
    if abs_progress >= watch:
        return LikelihoodBand.WATCH
    return LikelihoodBand.UNLIKELY


def parse_livefpl_prices(payload: dict[str, Any]) -> list[ExternalPriceRow]:
    """Validate LiveFPL-style id → row map. Skip malformed entries."""
    rows: list[ExternalPriceRow] = []
    if not isinstance(payload, dict):
        return rows
    for key, raw in payload.items():
        if not isinstance(raw, dict):
            continue
        try:
            pid = int(key)
        except (TypeError, ValueError):
            continue
        try:
            progress = float(raw.get("progress") if raw.get("progress") is not None else 0.0)
            tonight = float(
                raw.get("progress_tonight")
                if raw.get("progress_tonight") is not None
                else progress
            )
            cost = float(raw.get("cost") if raw.get("cost") is not None else 0.0)
        except (TypeError, ValueError):
            continue
        name = str(raw.get("name") or pid)
        per_hour = None
        if raw.get("per_hour") is not None:
            try:
                per_hour = float(raw["per_hour"])
            except (TypeError, ValueError):
                per_hour = None
        rows.append(
            ExternalPriceRow(
                player_id=pid,
                name=name,
                cost=cost,
                progress=progress,
                progress_tonight=tonight,
                per_hour=per_hour,
            )
        )
    return rows


def fetch_external_prices(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    max_bytes: int = MAX_BYTES,
) -> list[ExternalPriceRow]:
    """HTTPS JSON only. Empty url → empty list. Failures raise httpx/ValueError."""
    if not url:
        return []
    if not url.startswith("https://"):
        raise ValueError("external predictor URL must be HTTPS")
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; fpl-agent/0.1; +read-only)"},
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        raw = response.content
        if len(raw) > max_bytes:
            raise ValueError(f"external prices payload too large ({len(raw)} > {max_bytes})")
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("external prices JSON must be an object keyed by player id")
    return parse_livefpl_prices(payload)


def select_market_movers(
    rows: list[ExternalPriceRow],
    *,
    owned: set[int],
    plan_ids: set[int],
    watch_progress: float,
    likely_progress: float,
    top_n: int,
    catalog_names: dict[int, str] | None = None,
) -> list[MarketMover]:
    """Top risers and fallers by |progress_tonight|, watch-band and above."""
    catalog_names = catalog_names or {}
    scored: list[MarketMover] = []
    for row in rows:
        tonight = row.progress_tonight
        if tonight == 0:
            continue
        direction = PriceDirection.RISE if tonight > 0 else PriceDirection.FALL
        abs_p = abs(tonight)
        band = _band_from_abs_progress(abs_p, watch=watch_progress, likely=likely_progress)
        if band == LikelihoodBand.UNLIKELY:
            continue
        name = catalog_names.get(row.player_id) or row.name
        scored.append(
            MarketMover(
                player_id=row.player_id,
                web_name=name,
                direction=direction,
                external_progress=tonight,
                cost_millions=row.cost,
                band=band,
                owned=row.player_id in owned,
                in_plan=row.player_id in plan_ids,
                source_label=row.source,
            )
        )
    rises = sorted(
        (m for m in scored if m.direction == PriceDirection.RISE),
        key=lambda m: m.external_progress,
        reverse=True,
    )[:top_n]
    falls = sorted(
        (m for m in scored if m.direction == PriceDirection.FALL),
        key=lambda m: m.external_progress,
    )[:top_n]
    return rises + falls


def attach_external_progress(
    predictions: list[Any],
    by_id: dict[int, ExternalPriceRow],
) -> None:
    """Mutate predictions in place: set external_progress + provenance note."""
    for pred in predictions:
        row = by_id.get(pred.player_id)
        if row is None:
            continue
        pred.external_progress = row.progress_tonight
        if pred.provenance == "fpl_public_snapshot":
            pred.provenance = "fpl_public_snapshot+livefpl"
