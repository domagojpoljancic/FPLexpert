"""Replayable price-prediction outcomes. No auto-tuning."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fpl_agent.prices.snapshot import row_map
from fpl_agent.prices.types import (
    LikelihoodBand,
    PriceDirection,
    PriceOutcome,
    PricePrediction,
    PriceSnapshot,
)

DEFAULT_OUTCOMES = Path("data/outcomes/prices.jsonl")


def ownership_band(pct: float | None) -> str:
    if pct is None:
        return "unknown"
    if pct < 5:
        return "0-5"
    if pct < 15:
        return "5-15"
    if pct < 30:
        return "15-30"
    if pct < 50:
        return "30-50"
    return "50+"


def outcomes_from_snapshots(
    *,
    previous: PriceSnapshot,
    current: PriceSnapshot,
    predictions: list[PricePrediction],
    gameweek: int,
    now: datetime | None = None,
) -> list[PriceOutcome]:
    now = now or datetime.now(UTC)
    before = row_map(previous)
    after = row_map(current)
    pred_map = {p.player_id: p for p in predictions}
    hours = (current.retrieved_at - previous.retrieved_at).total_seconds() / 3600.0
    out: list[PriceOutcome] = []
    for pid, old in before.items():
        new = after.get(pid)
        if new is None or new.now_cost == old.now_cost:
            continue
        pred = pred_map.get(pid)
        if pred is None:
            continue
        delta = new.now_cost - old.now_cost
        actual_dir = PriceDirection.RISE if delta > 0 else PriceDirection.FALL
        hit = pred.direction == actual_dir and pred.likelihood in {
            LikelihoodBand.LIKELY_NEXT_WINDOW,
            LikelihoodBand.WATCH,
            LikelihoodBand.ALREADY_MOVED,
        }
        out.append(
            PriceOutcome(
                player_id=pid,
                gameweek=gameweek,
                predicted_direction=pred.direction,
                predicted_band=pred.likelihood,
                actual_delta_tenths=delta,
                hours_since_prediction=hours,
                ownership_band=ownership_band(old.selected_by_percent),
                hit=hit,
                recorded_at=now,
                model_version=pred.model_version,
            )
        )
    return out


def append_outcomes(records: list[PriceOutcome], path: Path = DEFAULT_OUTCOMES) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec.model_dump(mode="json"), default=str) + "\n")
