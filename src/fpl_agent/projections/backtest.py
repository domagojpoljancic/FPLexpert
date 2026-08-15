"""Deterministic leakage-free backtest on frozen fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.projections.model import MODEL_VERSION, project_player_gw


@dataclass
class BacktestResult:
    mae: float
    bias: float
    n: int
    by_position: dict[str, dict[str, float]]
    dataset_hash: str
    model_version: str


def run_backtest(rows: list[dict[str, Any]]) -> BacktestResult:
    """Each row must only include features available before its deadline."""
    errs: list[float] = []
    by_pos: dict[str, list[float]] = {}
    for row in rows:
        # Guard: forbid future fields
        if "future_leak" in row:
            raise ValueError("future leakage field present")
        pred = project_player_gw(
            player_id=int(row["player_id"]),
            gameweek=int(row["gameweek"]),
            recent_minutes=list(row["recent_minutes"]),
            recent_points=list(row["recent_points"]),
            position_prior_minutes=float(row.get("position_prior_minutes", 70)),
            team_attack=float(row.get("team_attack", 0)),
            team_defence=float(row.get("team_defence", 0)),
            opp_attack=float(row.get("opp_attack", 0)),
            opp_defence=float(row.get("opp_defence", 0)),
            is_home=bool(row.get("is_home", True)),
            fixtures_in_gw=int(row.get("fixtures_in_gw", 1)),
            availability=str(row.get("availability", "available")),
            def_contrib_rate=float(row.get("def_contrib_rate", 0)),
            input_hashes={"row": stable_json_hash({k: row[k] for k in row if k != "actual_points"})},
        )
        err = pred.expected_points - float(row["actual_points"])
        errs.append(err)
        by_pos.setdefault(str(row.get("position", "?")), []).append(err)
    mae = sum(abs(e) for e in errs) / len(errs) if errs else 0.0
    bias = sum(errs) / len(errs) if errs else 0.0
    summary = {
        pos: {"mae": sum(abs(e) for e in es) / len(es), "n": float(len(es))}
        for pos, es in by_pos.items()
    }
    return BacktestResult(
        mae=mae,
        bias=bias,
        n=len(errs),
        by_position=summary,
        dataset_hash=stable_json_hash(rows),
        model_version=MODEL_VERSION,
    )
