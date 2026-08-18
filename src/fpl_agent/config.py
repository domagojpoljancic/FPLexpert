"""Validated settings with YAML + environment overrides."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fpl_agent.domain.models import RiskProfile
from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode


class ManagerSettings(BaseModel):
    team_id: int = Field(gt=0)
    classic_league_ids: list[int] = Field(default_factory=list)
    timezone: str = "Europe/London"
    risk_profile: RiskProfile = RiskProfile.MODERATE

    @field_validator("classic_league_ids")
    @classmethod
    def _positive_leagues(cls, v: list[int]) -> list[int]:
        if any(x <= 0 for x in v):
            raise ValueError("classic_league_ids must be positive")
        return v

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"invalid timezone: {v}") from exc
        return v


class PlanningSettings(BaseModel):
    horizon: int = Field(default=6, ge=3, le=8)
    weights: list[float] = Field(default_factory=lambda: [1.00, 0.90, 0.78, 0.66, 0.55, 0.45])
    max_hit: int = Field(default=8, ge=0)
    hits_enabled: bool = True

    @model_validator(mode="after")
    def _weights_match_horizon(self) -> PlanningSettings:
        if len(self.weights) != self.horizon:
            raise ValueError(
                f"weights length {len(self.weights)} must equal horizon {self.horizon}"
            )
        if any(w < 0 for w in self.weights):
            raise ValueError("weights must be non-negative")
        if self.weights and self.weights[0] <= 0:
            raise ValueError("nearest-week weight must be positive")
        return self


class FreshnessSettings(BaseModel):
    public_fpl_max_age_minutes: int = Field(default=180, gt=0)
    private_squad_max_age_hours: int = Field(default=24, gt=0)
    financial_state_max_age_hours: int = Field(default=24, gt=0)
    news_max_age_hours: int = Field(default=12, gt=0)
    official_outcomes_max_age_hours: int = Field(default=72, gt=0)


class PublishingSettings(BaseModel):
    dry_run: bool = True
    markdown_history: bool = True
    issue_publishing: bool = False
    material_change_only: bool = True


class ModelsSettings(BaseModel):
    daily_model: str = "gpt-5.6"
    deadline_model: str = "gpt-5.6"
    review_model: str = "gpt-5.6"
    reasoning_effort: str = "medium"
    web_search_budget: int = Field(default=8, ge=0)
    max_output_tokens: int = Field(default=5000, gt=0)


class CostSettings(BaseModel):
    per_run_soft_limit_usd: float = Field(default=1.5, gt=0)
    monthly_soft_limit_usd: float = Field(default=40.0, gt=0)


class ReviewSettings(BaseModel):
    lookback_gameweeks: int = Field(default=6, gt=0)
    compare_recorded_alternatives: bool = True
    min_evidence_before_param_change: int = Field(default=3, gt=0)


class AlertsSettings(BaseModel):
    deadline_window_minutes: int = Field(default=180, gt=0)
    safety_floor_minutes: int = Field(default=20, gt=0)
    material_change_xp_delta: float = Field(default=1.5, gt=0)
    material_change_price_tenths: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def _floor_inside_window(self) -> AlertsSettings:
        if not (0 < self.safety_floor_minutes < self.deadline_window_minutes):
            raise ValueError(
                "safety_floor_minutes must be strictly inside deadline_window_minutes"
            )
        return self


class PricesSettings(BaseModel):
    """Uncalibrated price-change heuristic. Changing numeric fields is a model-version bump."""

    enabled: bool = True
    snapshot_max_per_gw: int = Field(default=48, ge=2, le=168)
    watch_progress: float = Field(default=0.55, ge=0.0, le=1.0)
    likely_progress: float = Field(default=0.85, ge=0.0, le=1.0)
    min_snapshots_for_likely: int = Field(default=2, ge=2, le=10)
    hysteresis: float = Field(default=0.05, ge=0.0, le=0.2)
    rise_base_net: int = Field(default=40_000, gt=0)
    fall_base_net: int = Field(default=50_000, gt=0)
    ownership_scale_k: float = Field(default=3.0, ge=0.0)
    allow_hit_for_price: bool = False
    allow_last_ft_for_price: bool = False
    max_hours_ahead_to_spend_ft: float = Field(default=36.0, gt=0)
    bank_floor_tenths_after: int = Field(default=0, ge=0)
    webhook_url: str = ""
    external_predictor_url: str = ""
    model_version: str = "prices-v1.0.0"

    @model_validator(mode="after")
    def _progress_order(self) -> PricesSettings:
        if self.watch_progress >= self.likely_progress:
            raise ValueError("watch_progress must be < likely_progress")
        for name, url in (
            ("webhook_url", self.webhook_url),
            ("external_predictor_url", self.external_predictor_url),
        ):
            if url and not url.startswith("https://"):
                raise ValueError(f"{name} must be empty or HTTPS")
        return self


class CadenceSettings(BaseModel):
    """When to run price-only daily vs full pre-deadline review."""

    predeadline_hours_before: float = Field(default=24.0, gt=0, le=72)
    predeadline_early_hours: float = Field(default=36.0, gt=0, le=96)
    predeadline_late_hours: float = Field(default=6.0, gt=0, le=48)

    @model_validator(mode="after")
    def _window_order(self) -> CadenceSettings:
        if not (
            0 < self.predeadline_late_hours < self.predeadline_hours_before <= self.predeadline_early_hours
        ):
            raise ValueError(
                "require 0 < predeadline_late_hours < predeadline_hours_before <= predeadline_early_hours"
            )
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FPL_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    manager: ManagerSettings
    planning: PlanningSettings = Field(default_factory=PlanningSettings)
    freshness: FreshnessSettings = Field(default_factory=FreshnessSettings)
    publishing: PublishingSettings = Field(default_factory=PublishingSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    cost: CostSettings = Field(default_factory=CostSettings)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    alerts: AlertsSettings = Field(default_factory=AlertsSettings)
    prices: PricesSettings = Field(default_factory=PricesSettings)
    cadence: CadenceSettings = Field(default_factory=CadenceSettings)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_yaml_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise AgentError(
            f"settings file not found: {path}",
            code=AgentErrorCode.INVALID_CONFIGURATION,
            exit_code=ExitCode.INVALID_CONFIG,
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise AgentError(
            "settings root must be a mapping",
            code=AgentErrorCode.INVALID_CONFIGURATION,
            exit_code=ExitCode.INVALID_CONFIG,
        )
    return data


def load_dotenv_files() -> None:
    """Load project-root .env if present. Does not override already-set env vars."""
    load_dotenv(Path(".env"), override=False)


def default_settings_path() -> Path:
    load_dotenv_files()
    env = os.environ.get("FPL_SETTINGS_PATH")
    if env:
        return Path(env)
    local = Path("config/settings.yaml")
    if local.exists():
        return local
    return Path("config/settings.example.yaml")


def load_settings(path: Path | None = None) -> Settings:
    settings_path = path or default_settings_path()
    raw = load_yaml_settings(settings_path)
    try:
        return Settings(**raw)
    except Exception as exc:  # noqa: BLE001 — surface as config exit
        raise AgentError(
            f"invalid configuration: {exc}",
            code=AgentErrorCode.INVALID_CONFIGURATION,
            exit_code=ExitCode.INVALID_CONFIG,
            details={"cause": str(exc)},
        ) from exc


def settings_to_safe_dict(settings: Settings) -> dict[str, Any]:
    return settings.model_dump(mode="json")
