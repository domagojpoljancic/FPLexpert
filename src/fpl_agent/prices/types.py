"""Price-change types. Deterministic; extra=forbid."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PriceDirection(StrEnum):
    RISE = "rise"
    FALL = "fall"
    NONE = "none"


class LikelihoodBand(StrEnum):
    UNLIKELY = "unlikely"
    WATCH = "watch"
    LIKELY_NEXT_WINDOW = "likely_next_window"
    ALREADY_MOVED = "already_moved"
    UNAVAILABLE = "unavailable"


class ActionClass(StrEnum):
    IGNORE = "ignore"
    WATCH = "watch"
    ACT_NOW_CONDITIONAL = "act_now_conditional"
    ACT_NOW_RECOMMENDED = "act_now_recommended"


class MoveType(StrEnum):
    NONE = "none"
    BUY_BEFORE_RISE = "buy_before_rise"
    SELL_BEFORE_FALL = "sell_before_fall"
    WAIT_FOR_RISE_THEN_SELL = "wait_for_rise_then_sell"
    HOLD = "hold"


class ReportStatus(StrEnum):
    NO_ACTION = "NO ACTION"
    WATCH = "WATCH"
    ACT_TONIGHT_CONDITIONAL = "ACT TONIGHT (conditional)"
    ACT_TONIGHT = "ACT TONIGHT"


class PlayerPriceRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: int
    now_cost: int
    transfers_in_event: int | None = None
    transfers_out_event: int | None = None
    selected_by_percent: float | None = None
    cost_change_event: int | None = None
    cost_change_event_fall: int | None = None
    status: str | None = None
    chance_of_playing_next_round: float | None = None
    web_name: str | None = None


class PriceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieved_at: datetime
    event_id: int
    season: str
    schema_version: str
    adapter_version: str
    content_hash: str
    players: list[PlayerPriceRow]


class PricePrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: int
    web_name: str
    now_cost_tenths: int
    direction: PriceDirection
    likelihood: LikelihoodBand
    progress_uncalibrated: float | None = Field(default=None, ge=0.0, le=1.0)
    net_transfers_event: int | None = None
    net_transfers_since_prev_snapshot: int | None = None
    snapshot_count_used: int
    model_version: str
    as_of: datetime
    warnings: list[str] = Field(default_factory=list)
    provenance: str = "fpl_public_snapshot"
    external_progress: float | None = None
    already_moved_tenths: int = 0


class PriceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_class: ActionClass
    move_type: MoveType
    summary: str
    rationale_codes: list[str] = Field(default_factory=list)
    player_ids: list[int] = Field(default_factory=list)
    related_scenario_id: str | None = None
    valid_until: datetime | None = None
    affordability_risk: bool = False
    sell_value_at_risk: bool = False
    counterfactual: bool = False


class PriceOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: int
    gameweek: int
    predicted_direction: PriceDirection
    predicted_band: LikelihoodBand
    actual_delta_tenths: int
    hours_since_prediction: float | None = None
    ownership_band: str
    hit: bool
    price_moved: bool = True
    recorded_at: datetime
    model_version: str
