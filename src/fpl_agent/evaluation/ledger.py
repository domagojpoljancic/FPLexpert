"""Immutable pre-deadline decision ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fpl_agent.domain.run_state import stable_json_hash, utc_now


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    decision_id: str
    season: str
    gameweek: int
    official_deadline: str | None = None
    generated_at: str
    data_cutoff: str
    team_state: dict[str, Any]
    executability: str
    rules_hash: str
    catalog_hash: str
    projection_hash: str
    config_hash: str
    code_version: str
    roll: dict[str, Any]
    primary: dict[str, Any] | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    report_hash: str | None = None
    replaces: str | None = None
    canonical: bool = True


def decision_path(root: Path, season: str, gameweek: int, decision_id: str) -> Path:
    return root / season / f"gw-{gameweek:02d}" / f"{decision_id}.json"


def write_decision_record(root: Path, record: DecisionRecord) -> Path:
    path = decision_path(root, record.season, record.gameweek, record.decision_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"refusing to overwrite decision record: {path}")
    # atomic write
    tmp = path.with_suffix(".tmp")
    tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    # canonical pointer
    manifest = path.parent / "canonical.json"
    if record.canonical:
        manifest.write_text(json.dumps({"decision_id": record.decision_id, "hash": record.decision_id}), encoding="utf-8")
    return path


def build_decision_id(payload: dict[str, Any]) -> str:
    return stable_json_hash(payload)[:24]


def new_generation_timestamp() -> str:
    return utc_now().isoformat()
