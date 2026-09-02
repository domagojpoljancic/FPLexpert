"""Leakage-free backtest row schema and dataset loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Pre-deadline feature keys permitted on each row. Labels are separate.
ALLOWED_FEATURE_KEYS: frozenset[str] = frozenset(
    {
        "player_id",
        "gameweek",
        "position",
        "element_type",
        "now_cost",
        "minutes",
        "starts",
        "total_points",
        "team_id",
        "web_name",
        "ep_next",
        "expected_goals",
        "expected_assists",
        "goals_scored",
        "assists",
        "status",
        "chance_of_playing_next_round",
        "penalties_order",
        "games_played",
        "recent_minutes",
        "recent_points",
        "position_prior_minutes",
        "team_attack",
        "team_defence",
        "opp_attack",
        "opp_defence",
        "is_home",
        "fixtures_in_gw",
        "fdr_difficulty",
        "availability",
        "def_contrib_rate",
        "clearances_blocks_interceptions",
        "recoveries",
        "tackles",
        "defensive_contribution",
        "defensive_contribution_per_90",
    }
)

LABEL_KEYS: frozenset[str] = frozenset({"actual_points"})

DATASET_META_KEYS: frozenset[str] = frozenset(
    {"season", "rules_version", "rows", "source", "blocked", "blocked_reason"}
)

SUPPORTED_RULES_SEASONS: frozenset[str] = frozenset({"2026-27"})


@dataclass(frozen=True)
class BacktestRow:
    """One player-gameweek holdout row: pre-deadline features + post-deadline label."""

    player_id: int
    gameweek: int
    actual_points: float
    features: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BacktestRow:
        validate_row(raw)
        label = float(raw["actual_points"])
        features = {k: v for k, v in raw.items() if k in ALLOWED_FEATURE_KEYS}
        return cls(
            player_id=int(raw["player_id"]),
            gameweek=int(raw["gameweek"]),
            actual_points=label,
            features=features,
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.features, "actual_points": self.actual_points}


def validate_row(row: dict[str, Any]) -> None:
    """Reject unknown or future-looking fields on a single row."""
    if "future_leak" in row:
        raise ValueError("future leakage field present")
    if "actual_points" not in row:
        raise ValueError("missing label field actual_points")
    unknown = set(row) - ALLOWED_FEATURE_KEYS - LABEL_KEYS
    if unknown:
        raise ValueError(f"non-allowlisted row fields: {sorted(unknown)}")


def validate_dataset_meta(payload: dict[str, Any]) -> None:
    unknown = set(payload) - DATASET_META_KEYS
    if unknown:
        raise ValueError(f"non-allowlisted dataset fields: {sorted(unknown)}")
    if "rows" not in payload:
        raise ValueError("dataset missing rows")


def load_dataset(path: Path, *, source: Path | None = None) -> dict[str, Any]:
    """Load a backtest dataset from JSON. Optional ``source`` merges an external dump."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dataset root must be an object")
    if source is not None:
        extra = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(extra, dict) and "rows" in extra:
            payload = {**extra, **payload, "rows": payload.get("rows") or extra.get("rows", [])}
        payload["source"] = str(source)
    validate_dataset_meta(payload)
    rows_raw = payload["rows"]
    if not isinstance(rows_raw, list):
        raise ValueError("rows must be a list")
    rows = [BacktestRow.from_dict(r).as_dict() for r in rows_raw]
    return {
        "season": payload.get("season"),
        "rules_version": payload.get("rules_version"),
        "blocked": payload.get("blocked"),
        "blocked_reason": payload.get("blocked_reason"),
        "source": payload.get("source"),
        "rows": rows,
    }


def rules_mismatch(dataset_season: str | None, cli_season: str | None) -> bool:
    """True when the dataset season cannot be scored with verified rules."""
    effective = cli_season or dataset_season
    if effective is None:
        return False
    return effective not in SUPPORTED_RULES_SEASONS
