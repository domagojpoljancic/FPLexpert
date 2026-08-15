"""Deterministic counterfactual replay using official per-player points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fpl_agent.rules.engine import LineupPick, manager_gameweek_total
from fpl_agent.rules.season import SeasonRules


class ProcessQuality(StrEnum):
    GOOD = "good"
    MIXED = "mixed"
    POOR = "poor"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class OutcomeQuality(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class RootCause(StrEnum):
    SOUND_PROCESS_NORMAL_VARIANCE = "sound_process_normal_variance"
    PROJECTION_OR_MINUTES_MISS = "projection_or_minutes_miss"
    NEWS_OR_DATA_FRESHNESS_MISS = "news_or_data_freshness_miss"
    SCENARIO_GENERATION_GAP = "scenario_generation_gap"
    RANKING_OR_REASONING_MISS = "ranking_or_reasoning_miss"
    RULES_OR_CALCULATION_BUG = "rules_or_calculation_bug"
    USER_EXECUTION_DIFFERENCE = "user_execution_difference"
    UNAVOIDABLE_LATE_EVENT = "unavoidable_late_event"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass
class ReplayResult:
    actual_net: int | None
    recommendation_net: int | None
    roll_net: int | None
    alternatives: dict[str, int]
    process: ProcessQuality
    outcome: OutcomeQuality
    root_cause: RootCause


def picks_from_dict(raw: list[dict[str, Any]]) -> list[LineupPick]:
    from fpl_agent.domain.models import Position

    out: list[LineupPick] = []
    for p in raw:
        out.append(
            LineupPick(
                player_id=int(p["player_id"]),
                position=Position(p["position"]),
                is_starter=bool(p["is_starter"]),
                bench_order=p.get("bench_order"),
                is_captain=bool(p.get("is_captain", False)),
                is_vice=bool(p.get("is_vice", False)),
            )
        )
    return out


def replay_scenario(
    *,
    picks: list[LineupPick],
    player_points: dict[int, int],
    minutes: dict[int, int],
    hit_cost: int,
    bench_boost: bool,
    triple_captain: bool,
    rules: SeasonRules,
) -> int:
    return manager_gameweek_total(
        player_points=player_points,
        picks=picks,
        minutes=minutes,
        hit_cost=hit_cost,
        bench_boost=bench_boost,
        triple_captain=triple_captain,
        rules=rules,
    )


def grade_process_outcome(
    *,
    recommendation_net: int | None,
    roll_net: int | None,
    actual_net: int | None,
    predeadline_ev_positive: bool | None,
) -> tuple[ProcessQuality, OutcomeQuality, RootCause]:
    if predeadline_ev_positive is None or recommendation_net is None or roll_net is None:
        return (
            ProcessQuality.INSUFFICIENT_EVIDENCE,
            OutcomeQuality.NEUTRAL,
            RootCause.INSUFFICIENT_EVIDENCE,
        )
    process = ProcessQuality.GOOD if predeadline_ev_positive else ProcessQuality.POOR
    if actual_net is None:
        return process, OutcomeQuality.NEUTRAL, RootCause.INSUFFICIENT_EVIDENCE
    delta = actual_net - roll_net
    if delta > 2:
        outcome = OutcomeQuality.POSITIVE
    elif delta < -2:
        outcome = OutcomeQuality.NEGATIVE
    else:
        outcome = OutcomeQuality.NEUTRAL
    if process == ProcessQuality.GOOD and outcome == OutcomeQuality.NEGATIVE:
        root = RootCause.SOUND_PROCESS_NORMAL_VARIANCE
    elif process == ProcessQuality.POOR and outcome == OutcomeQuality.POSITIVE:
        root = RootCause.SOUND_PROCESS_NORMAL_VARIANCE  # lucky haul — still poor process
        # represent lucky haul via poor process + positive outcome; root stays variance-adjacent
        root = RootCause.RANKING_OR_REASONING_MISS
    else:
        root = RootCause.SOUND_PROCESS_NORMAL_VARIANCE
    return process, outcome, root
