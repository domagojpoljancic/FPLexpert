"""Price prediction accuracy scorecard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpl_agent.prices.types import LikelihoodBand, PriceOutcome


@dataclass
class PriceScorecard:
    n_predictions: int
    n_moved: int
    n_false_alarms: int
    n_missed_rises: int
    precision: float
    recall: float
    false_alarm_rate: float
    missed_move_rate: float
    by_band: dict[str, dict[str, float]]

    def as_payload(self) -> dict[str, Any]:
        return {
            "n_predictions": self.n_predictions,
            "n_moved": self.n_moved,
            "n_false_alarms": self.n_false_alarms,
            "n_missed_rises": self.n_missed_rises,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_alarm_rate": round(self.false_alarm_rate, 4),
            "missed_move_rate": round(self.missed_move_rate, 4),
            "by_band": self.by_band,
        }


def build_price_scorecard(
    outcomes: list[PriceOutcome],
    *,
    planned_in_ids: set[int] | None = None,
) -> PriceScorecard:
    planned_in_ids = planned_in_ids or set()
    watch_bands = {
        LikelihoodBand.WATCH,
        LikelihoodBand.LIKELY_NEXT_WINDOW,
        LikelihoodBand.ALREADY_MOVED,
    }
    score_bands = watch_bands | {LikelihoodBand.UNLIKELY}
    predicted_watch = [o for o in outcomes if o.predicted_band in score_bands]
    moved = [o for o in outcomes if o.price_moved]
    hits = [o for o in moved if o.hit]
    false_alarms = [o for o in outcomes if not o.price_moved and o.predicted_band in score_bands]
    missed = [
        o
        for o in moved
        if o.actual_delta_tenths > 0 and o.predicted_band not in watch_bands
    ]
    planned_missed = [o for o in missed if o.player_id in planned_in_ids]
    precision = len(hits) / len(predicted_watch) if predicted_watch else 0.0
    recall = len(hits) / len(moved) if moved else 0.0
    false_alarm_rate = len(false_alarms) / len(predicted_watch) if predicted_watch else 0.0
    missed_rate = len(missed) / len(moved) if moved else 0.0
    by_band: dict[str, dict[str, float]] = {}
    for band in LikelihoodBand:
        rows = [o for o in outcomes if o.predicted_band == band]
        if not rows:
            continue
        band_hits = sum(1 for o in rows if o.hit)
        by_band[band.value] = {
            "n": float(len(rows)),
            "precision": band_hits / len(rows),
            "false_alarms": float(sum(1 for o in rows if not o.price_moved)),
        }
    _ = planned_missed  # surfaced in payload extension
    return PriceScorecard(
        n_predictions=len(outcomes),
        n_moved=len(moved),
        n_false_alarms=len(false_alarms),
        n_missed_rises=len(planned_missed) or len(missed),
        precision=precision,
        recall=recall,
        false_alarm_rate=false_alarm_rate,
        missed_move_rate=missed_rate,
        by_band=by_band,
    )


def load_outcomes_jsonl(path: Path) -> list[PriceOutcome]:
    if not path.exists():
        return []
    rows: list[PriceOutcome] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(PriceOutcome.model_validate(json.loads(line)))
    return rows
