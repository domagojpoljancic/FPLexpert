"""Shared domain identifiers and contracts. Rule behavior lives in SeasonRules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Tenths = Annotated[int, Field(ge=0)]  # prices in £0.1m units


class SeasonId(StrEnum):
    S2026_27 = "2026-27"


class Position(StrEnum):
    GKP = "GKP"
    DEF = "DEF"
    MID = "MID"
    FWD = "FWD"


POSITION_FROM_ELEMENT_TYPE: dict[int, Position] = {
    1: Position.GKP,
    2: Position.DEF,
    3: Position.MID,
    4: Position.FWD,
}


class ChipKind(StrEnum):
    WILDCARD = "wildcard"
    FREE_HIT = "freehit"
    BENCH_BOOST = "bboost"
    TRIPLE_CAPTAIN = "3xc"


class ChipHalf(StrEnum):
    FIRST = "first"  # GW1–GW19 window (instance start may be later)
    SECOND = "second"  # GW20–GW38


class SourceTier(StrEnum):
    OFFICIAL = "official"
    ESTABLISHED = "established"
    COMMUNITY = "community"
    USER_SYNC = "user_sync"
    LOCAL_CACHE = "local_cache"
    UNKNOWN = "unknown"


class FieldSourceType(StrEnum):
    PRIVATE_SYNC = "private_sync"
    PUBLIC_POST_DEADLINE = "public_post_deadline"
    LOCAL_SNAPSHOT = "local_snapshot"
    UNKNOWN = "unknown"


class RunMode(StrEnum):
    DAILY = "daily"
    PRICES = "prices"
    PREDEADLINE = "predeadline"
    DEADLINE = "deadline"
    WEEKLY_REVIEW = "weekly_review"
    MANUAL = "manual"
    DRY_RUN = "dry_run"


class RunStatus(StrEnum):
    PREPARED = "prepared"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    DEGRADED = "degraded"
    FAILED = "failed"


class Executability(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    CONDITIONAL_ONLY = "CONDITIONAL_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


class RiskProfile(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


T = TypeVar("T")


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    retrieved_at: datetime
    published_at: datetime | None = None
    event_at: datetime | None = None
    tier: SourceTier
    content_hash: str
    adapter_version: str
    schema_version: str


class Provenanced(BaseModel, Generic[T]):
    """Generic per-field provenance wrapper."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    value: T
    source_type: FieldSourceType
    observed_at: datetime | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    warnings: list[str] = Field(default_factory=list)
    fresh: bool = False


class ChipInstanceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChipKind
    half: ChipHalf
    available: bool
    used_in_gameweek: PositiveInt | None = None


class SquadPlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: PositiveInt
    position: Position
    club_id: PositiveInt
    purchase_price_tenths: Tenths | None = None
    selling_price_tenths: Tenths | None = None
    current_price_tenths: Tenths | None = None
    is_starter: bool | None = None
    bench_order: NonNegativeInt | None = None
    is_captain: bool | None = None
    is_vice: bool | None = None


class ResolvedTeamState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: SeasonId
    applies_to_gameweek: PositiveInt
    as_of: datetime
    squad: Provenanced[list[SquadPlayer]]
    bank_tenths: Provenanced[Tenths | None]
    free_transfers: Provenanced[NonNegativeInt | None]
    chip_instances: Provenanced[list[ChipInstanceState] | None]
    captain_id: Provenanced[PositiveInt | None] = Field(
        default_factory=lambda: Provenanced[PositiveInt | None](
            value=None, source_type=FieldSourceType.UNKNOWN, confidence=0.0
        )
    )
    vice_id: Provenanced[PositiveInt | None] = Field(
        default_factory=lambda: Provenanced[PositiveInt | None](
            value=None, source_type=FieldSourceType.UNKNOWN, confidence=0.0
        )
    )
    executability: Executability
    executable_advice_allowed: bool
    warnings: list[str] = Field(default_factory=list)

    @field_validator("executable_advice_allowed")
    @classmethod
    def _align_flag(cls, v: bool, info: object) -> bool:
        return v


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    season: SeasonId
    gameweek: PositiveInt
    mode: RunMode
    data_cutoff: datetime
    input_hashes: dict[str, str] = Field(default_factory=dict)
    output_hashes: dict[str, str] = Field(default_factory=dict)
    status: RunStatus
    warnings: list[str] = Field(default_factory=list)
    code_version: str
    rules_version: str
    config_hash: str
