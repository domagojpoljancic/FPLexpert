"""Versioned SeasonRules contract and 2026/27 loader."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from fpl_agent.domain.models import ChipHalf, ChipKind, Position, SeasonId

PositiveInt = Annotated[int, Field(gt=0)]


class RuleOrigin(StrEnum):
    OFFICIAL_DOCUMENTED = "official_documented"
    OBSERVED_BOOTSTRAP = "observed_bootstrap"
    APPLICATION_POLICY = "application_policy"


class PositionQuota(BaseModel):
    model_config = ConfigDict(extra="forbid")

    squad_count: PositiveInt
    min_starters: PositiveInt
    max_starters: PositiveInt


class DefensiveContributionRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    points: int = 2
    defender_threshold_cbit: int = 10
    mid_fwd_threshold_cbirt: int = 12
    notes: str = (
        "Defenders use clearances+blocks+interceptions+tackles (CBIT). "
        "MID/FWD also count ball recoveries (CBIRT)."
    )


class ChipInstanceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChipKind
    half: ChipHalf
    start_event: PositiveInt
    stop_event: PositiveInt
    bootstrap_id: PositiveInt | None = None


class ScoringCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    description: str


class SeasonRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    season: SeasonId
    rules_version: str
    reviewed: bool
    initial_budget_tenths: int
    squad_size: int
    starters: int
    club_limit: int
    position_quotas: dict[Position, PositionQuota]
    free_transfers_per_gw: int
    max_banked_free_transfers: int
    hit_cost_points: int
    sell_on_fee_fraction: float
    currency_multiplier: int
    captain_multiplier: int
    triple_captain_multiplier: int
    vice_captain_fallback: bool
    chip_instances: tuple[ChipInstanceRule, ...]
    free_hit_forbidden_events: tuple[int, ...]
    no_consecutive_free_hit_across_halves: bool
    preserve_ft_across_wildcard_and_free_hit: bool
    defensive_contribution: DefensiveContributionRule
    scoring_categories: tuple[ScoringCategory, ...]
    result_finality: str
    origins: dict[str, RuleOrigin]


FIRST_HALF_CHIP_EXPIRY_EVENT = 19  # GW19 deadline Sat 2 Jan 2027 13:30 GMT


def load_season_rules_2026_27() -> SeasonRules:
    """Immutable 2026/27 rules verified against PL articles + bootstrap 2026-08-15."""
    return SeasonRules(
        season=SeasonId.S2026_27,
        rules_version="2026-27.1",
        reviewed=True,
        initial_budget_tenths=1000,
        squad_size=15,
        starters=11,
        club_limit=3,
        position_quotas={
            Position.GKP: PositionQuota(squad_count=2, min_starters=1, max_starters=1),
            Position.DEF: PositionQuota(squad_count=5, min_starters=3, max_starters=5),
            Position.MID: PositionQuota(squad_count=5, min_starters=2, max_starters=5),
            Position.FWD: PositionQuota(squad_count=3, min_starters=1, max_starters=3),
        },
        free_transfers_per_gw=1,
        max_banked_free_transfers=5,
        hit_cost_points=4,
        sell_on_fee_fraction=0.5,
        currency_multiplier=10,
        captain_multiplier=2,
        triple_captain_multiplier=3,
        vice_captain_fallback=True,
        chip_instances=(
            ChipInstanceRule(kind=ChipKind.WILDCARD, half=ChipHalf.FIRST, start_event=2, stop_event=19, bootstrap_id=1),
            ChipInstanceRule(kind=ChipKind.WILDCARD, half=ChipHalf.SECOND, start_event=20, stop_event=38, bootstrap_id=2),
            ChipInstanceRule(kind=ChipKind.FREE_HIT, half=ChipHalf.FIRST, start_event=2, stop_event=19, bootstrap_id=3),
            ChipInstanceRule(kind=ChipKind.BENCH_BOOST, half=ChipHalf.FIRST, start_event=1, stop_event=19, bootstrap_id=4),
            ChipInstanceRule(kind=ChipKind.TRIPLE_CAPTAIN, half=ChipHalf.FIRST, start_event=1, stop_event=19, bootstrap_id=5),
            ChipInstanceRule(kind=ChipKind.FREE_HIT, half=ChipHalf.SECOND, start_event=20, stop_event=38, bootstrap_id=6),
            ChipInstanceRule(kind=ChipKind.BENCH_BOOST, half=ChipHalf.SECOND, start_event=20, stop_event=38, bootstrap_id=7),
            ChipInstanceRule(kind=ChipKind.TRIPLE_CAPTAIN, half=ChipHalf.SECOND, start_event=20, stop_event=38, bootstrap_id=8),
        ),
        free_hit_forbidden_events=(1,),
        no_consecutive_free_hit_across_halves=True,
        preserve_ft_across_wildcard_and_free_hit=True,
        defensive_contribution=DefensiveContributionRule(),
        scoring_categories=(
            ScoringCategory(key="minutes", description="Appearance minutes points"),
            ScoringCategory(key="goals", description="Goals scored by position"),
            ScoringCategory(key="assists", description="Assists"),
            ScoringCategory(key="clean_sheet", description="Clean sheet by position"),
            ScoringCategory(key="goals_conceded", description="Goals conceded penalties"),
            ScoringCategory(key="saves", description="Goalkeeper saves"),
            ScoringCategory(key="penalty_saves", description="Penalty saves"),
            ScoringCategory(key="penalty_misses", description="Penalty misses"),
            ScoringCategory(key="yellow_cards", description="Yellow cards"),
            ScoringCategory(key="red_cards", description="Red cards"),
            ScoringCategory(key="own_goals", description="Own goals"),
            ScoringCategory(key="bonus", description="Bonus points"),
            ScoringCategory(key="defensive_contribution", description="Defensive contribution points"),
        ),
        result_finality=(
            "Scores remain provisional until 09:00 UK time on the day after the final match "
            "of the gameweek; also observe event.data_checked from bootstrap/live metadata."
        ),
        origins={
            "initial_budget_tenths": RuleOrigin.OBSERVED_BOOTSTRAP,
            "squad_composition": RuleOrigin.OBSERVED_BOOTSTRAP,
            "club_limit": RuleOrigin.OBSERVED_BOOTSTRAP,
            "free_transfers": RuleOrigin.OFFICIAL_DOCUMENTED,
            "hit_cost_points": RuleOrigin.OFFICIAL_DOCUMENTED,
            "sell_on_fee_fraction": RuleOrigin.OBSERVED_BOOTSTRAP,
            "chips": RuleOrigin.OFFICIAL_DOCUMENTED,
            "chip_windows": RuleOrigin.OBSERVED_BOOTSTRAP,
            "defensive_contribution": RuleOrigin.OFFICIAL_DOCUMENTED,
            "result_finality": RuleOrigin.OFFICIAL_DOCUMENTED,
            "preserve_ft_across_wildcard_and_free_hit": RuleOrigin.OFFICIAL_DOCUMENTED,
        },
    )


def load_season_rules(season: SeasonId | str) -> SeasonRules:
    from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode

    if isinstance(season, SeasonId):
        sid = season
    else:
        try:
            sid = SeasonId(season)
        except ValueError as exc:
            raise AgentError(
                f"unsupported or unverified season rules: {season}",
                code=AgentErrorCode.UNSUPPORTED_SEASON_RULES,
                exit_code=ExitCode.UNSUPPORTED_SEASON_RULES,
            ) from exc
    if sid == SeasonId.S2026_27:
        return load_season_rules_2026_27()
    raise AgentError(
        f"unsupported or unverified season rules: {sid}",
        code=AgentErrorCode.UNSUPPORTED_SEASON_RULES,
        exit_code=ExitCode.UNSUPPORTED_SEASON_RULES,
    )
