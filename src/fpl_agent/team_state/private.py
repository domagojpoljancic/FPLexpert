"""Private team-state schema and validation (no FPL authentication)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fpl_agent.domain.models import ChipHalf, ChipKind, SeasonId
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode
from fpl_agent.rules.season import load_season_rules

PositiveInt = Annotated[int, Field(gt=0)]
NonNegInt = Annotated[int, Field(ge=0)]


class PrivateChipInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChipKind
    half: ChipHalf
    available: bool = True
    used_in_gameweek: PositiveInt | None = None


class PrivateTeamState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    season: SeasonId
    applies_before_gameweek: PositiveInt
    as_of: datetime
    player_ids: list[PositiveInt]
    bank_tenths: NonNegInt
    free_transfers: NonNegInt
    purchase_prices_tenths: dict[str, NonNegInt]
    chip_instances: list[PrivateChipInstance] = Field(default_factory=list)
    captain_id: PositiveInt | None = None
    vice_id: PositiveInt | None = None
    starters: list[PositiveInt] | None = None
    bench_order: list[PositiveInt] | None = None

    @field_validator("player_ids")
    @classmethod
    def _fifteen(cls, v: list[int]) -> list[int]:
        if len(v) != 15:
            raise ValueError("player_ids must contain exactly 15 players")
        if len(set(v)) != 15:
            raise ValueError("player_ids must be unique")
        return v


def load_and_validate_private_state(
    path: Path,
    *,
    catalog_player_ids: set[int] | None = None,
) -> PrivateTeamState:
    if not path.exists():
        raise AgentError(
            f"private state not found: {path}",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        )
    try:
        state = PrivateTeamState.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AgentError(
            f"malformed private state: {exc}",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        ) from exc

    rules = load_season_rules(state.season)
    if state.free_transfers > rules.max_banked_free_transfers:
        raise AgentError(
            "free_transfers exceed season maximum",
            code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
            exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
        )
    for pid in state.player_ids:
        price_key = str(pid)
        if price_key not in state.purchase_prices_tenths:
            raise AgentError(
                f"missing purchase price for player {pid}",
                code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
                exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
            )
    if catalog_player_ids is not None:
        unknown = [p for p in state.player_ids if p not in catalog_player_ids]
        if unknown:
            raise AgentError(
                f"player ids not in catalog: {unknown}",
                code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
                exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
            )
    if state.chip_instances:
        seen: set[tuple[ChipKind, ChipHalf]] = set()
        for chip in state.chip_instances:
            chip_key = (chip.kind, chip.half)
            if chip_key in seen:
                raise AgentError(
                    f"duplicate chip instance {chip_key}",
                    code=AgentErrorCode.INSUFFICIENT_TEAM_STATE,
                    exit_code=ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE,
                )
            seen.add(chip_key)
    return state
