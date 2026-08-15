"""Normalized untrusted news/evidence contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClaimCategory(StrEnum):
    INJURY = "injury"
    SUSPENSION = "suspension"
    AVAILABILITY = "availability"
    PREDICTED_MINUTES = "predicted_minutes"
    ROTATION = "rotation"
    PRESS_CONFERENCE = "press_conference_statement"
    POSTPONEMENT = "postponement"
    FIXTURE_CHANGE = "confirmed_fixture_change"
    OTHER = "other"


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    category: ClaimCategory
    text: str = Field(max_length=2000)
    source_url: str
    source_tier: str
    player_ids: list[int] = Field(default_factory=list)
    team_ids: list[int] = Field(default_factory=list)
    fixture_ids: list[int] = Field(default_factory=list)
    published_at: datetime | None = None
    retrieved_at: datetime
    corroboration_count: int = 0
    confidence: float = Field(ge=0.0, le=1.0)
    expires_at: datetime | None = None
    contradicted_by: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    proposed_override: dict[str, object] | None = None

    @field_validator("source_url")
    @classmethod
    def https_only(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("only http(s) URLs allowed")
        return v

    @field_validator("text")
    @classmethod
    def inert_text(cls, v: str) -> str:
        # keep as data only — do not interpret as instructions
        return v


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    player_ids: list[int] = Field(default_factory=list)
    club_ids: list[int] = Field(default_factory=list)
    fixture_ids: list[int] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    budget: int = Field(ge=0, default=3)
