"""Deterministic leakage-free backtest on frozen fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.projections.dataset import rules_mismatch, validate_row
from fpl_agent.projections.model import MODEL_VERSION as BASELINE_VERSION
from fpl_agent.projections.model import project_player_gw
from fpl_agent.projections.preseason import PRESEASON_MODEL_VERSION, project_player

ModelKind = Literal["xp-v2", "baseline-v1", "ep_next"]


@dataclass
class BacktestResult:
    mae: float
    bias: float
    n: int
    by_position: dict[str, dict[str, float]]
    dataset_hash: str
    model_version: str


@dataclass
class BacktestReport:
    model: BacktestResult
    ep_next_baseline: BacktestResult
    season: str | None = None
    rules_mismatch: bool = False
    blocked: str | None = None
    blocked_reason: str | None = None


def _element_from_row(row: dict[str, Any]) -> dict[str, Any]:
    element_type = int(row.get("element_type", _position_to_element_type(str(row.get("position", "MID")))))
    return {
        "id": int(row["player_id"]),
        "element_type": element_type,
        "now_cost": int(row.get("now_cost", 50)),
        "team": int(row.get("team_id", 0)),
        "minutes": float(row.get("minutes", 0)),
        "starts": float(row.get("starts", 0)),
        "total_points": float(row.get("total_points", 0)),
        "ep_next": float(row.get("ep_next", 0)),
        "expected_goals": float(row.get("expected_goals", 0)),
        "expected_assists": float(row.get("expected_assists", 0)),
        "goals_scored": float(row.get("goals_scored", 0)),
        "assists": float(row.get("assists", 0)),
        "status": str(row.get("status", "a")),
        "web_name": str(row.get("web_name", "")),
        "penalties_order": row.get("penalties_order"),
        "chance_of_playing_next_round": row.get("chance_of_playing_next_round"),
    }


def _position_to_element_type(position: str) -> int:
    return {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}.get(position.upper(), 3)


def _fixtures_from_row(row: dict[str, Any]) -> dict[int, list[tuple[int, bool]]]:
    gw = int(row["gameweek"])
    fdr = int(row.get("fdr_difficulty", 3))
    is_home = bool(row.get("is_home", True))
    count = max(0, int(row.get("fixtures_in_gw", 1)))
    return {gw: [(fdr, is_home)] * count}


def predict_row(row: dict[str, Any], model: ModelKind) -> float:
    """Score one holdout row with the chosen model."""
    if model == "ep_next":
        return float(row.get("ep_next", 0.0))
    if model == "baseline-v1":
        pred = project_player_gw(
            player_id=int(row["player_id"]),
            gameweek=int(row["gameweek"]),
            recent_minutes=list(row.get("recent_minutes", [])),
            recent_points=list(row.get("recent_points", [])),
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
        return pred.expected_points
    if model == "xp-v2":
        element = _element_from_row(row)
        gw = int(row["gameweek"])
        games_played = int(row.get("games_played", 0))
        proj = project_player(
            element,
            fixtures_by_gw=_fixtures_from_row(row),
            gameweeks=[gw],
            weights=[1.0],
            games_played=games_played,
        )
        return proj.xp_by_gw[0] if proj.xp_by_gw else 0.0
    raise ValueError(f"unsupported model: {model}")


def _aggregate_errors(rows: list[dict[str, Any]], model: ModelKind, version: str) -> BacktestResult:
    errs: list[float] = []
    by_pos: dict[str, list[float]] = {}
    for row in rows:
        validate_row(row)
        pred = predict_row(row, model)
        err = pred - float(row["actual_points"])
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
        model_version=version,
    )


def run_backtest(rows: list[dict[str, Any]], *, model: ModelKind = "baseline-v1") -> BacktestResult:
    """Each row must only include features available before its deadline."""
    version = {
        "baseline-v1": BASELINE_VERSION,
        "xp-v2": PRESEASON_MODEL_VERSION,
        "ep_next": "ep_next-naive",
    }[model]
    return _aggregate_errors(rows, model, version)


def run_backtest_report(
    rows: list[dict[str, Any]],
    *,
    model: ModelKind = "xp-v2",
    season: str | None = None,
    dataset_season: str | None = None,
    blocked: str | None = None,
    blocked_reason: str | None = None,
) -> BacktestReport:
    """Run model and ep_next baseline side by side."""
    return BacktestReport(
        model=run_backtest(rows, model=model),
        ep_next_baseline=run_backtest(rows, model="ep_next"),
        season=season or dataset_season,
        rules_mismatch=rules_mismatch(dataset_season, season),
        blocked=blocked,
        blocked_reason=blocked_reason,
    )


def report_to_dict(report: BacktestReport) -> dict[str, Any]:
    def _result(r: BacktestResult) -> dict[str, Any]:
        return {
            "mae": r.mae,
            "bias": r.bias,
            "n": r.n,
            "by_position": r.by_position,
            "dataset_hash": r.dataset_hash,
            "model_version": r.model_version,
        }

    return {
        "season": report.season,
        "rules_mismatch": report.rules_mismatch,
        "blocked": report.blocked,
        "blocked_reason": report.blocked_reason,
        "model": _result(report.model),
        "ep_next_baseline": _result(report.ep_next_baseline),
    }


def format_report_markdown(report: BacktestReport, *, model_name: str) -> str:
    lines = [
        "# Backtest summary",
        "",
        f"- Season: {report.season or 'unspecified'}",
        f"- Rules mismatch: {report.rules_mismatch}",
    ]
    if report.blocked:
        lines.append(f"- Historical eval: **blocked** — {report.blocked_reason or report.blocked}")
    lines.extend(
        [
            "",
            f"## {model_name} ({report.model.model_version})",
            f"- n={report.model.n} MAE={report.model.mae:.3f} bias={report.model.bias:+.3f}",
            "",
            "| position | n | MAE |",
            "| --- | ---: | ---: |",
        ]
    )
    for pos, stats in sorted(report.model.by_position.items()):
        lines.append(f"| {pos} | {int(stats['n'])} | {stats['mae']:.3f} |")
    lines.extend(
        [
            "",
            f"## ep_next naive ({report.ep_next_baseline.model_version})",
            f"- n={report.ep_next_baseline.n} MAE={report.ep_next_baseline.mae:.3f} "
            f"bias={report.ep_next_baseline.bias:+.3f}",
            "",
            "| position | n | MAE |",
            "| --- | ---: | ---: |",
        ]
    )
    for pos, stats in sorted(report.ep_next_baseline.by_position.items()):
        lines.append(f"| {pos} | {int(stats['n'])} | {stats['mae']:.3f} |")
    return "\n".join(lines) + "\n"
