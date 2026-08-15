"""Public-data loading helpers for squad suggestion (read-only, no FPL login)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fpl_agent.errors import AgentError, AgentErrorCode, ExitCode
from fpl_agent.projections.preseason import PlayerProjection, project_all

CACHE_DIR = Path("data/cache")
BOOTSTRAP_CACHE = CACHE_DIR / "bootstrap-static.json"
FIXTURES_CACHE = CACHE_DIR / "fixtures.json"


def load_public_data(*, offline: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load bootstrap and fixtures, refreshing the local cache when online."""
    if offline:
        if not BOOTSTRAP_CACHE.exists() or not FIXTURES_CACHE.exists():
            raise AgentError(
                "offline requested but no cached FPL snapshots found",
                code=AgentErrorCode.FPL_UNAVAILABLE,
                exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
            )
        bootstrap = json.loads(BOOTSTRAP_CACHE.read_text(encoding="utf-8"))
        fixtures = json.loads(FIXTURES_CACHE.read_text(encoding="utf-8"))
        return bootstrap, fixtures

    from fpl_agent.ingestion.client import BootstrapAdapter, FixturesAdapter, FplClient

    with FplClient() as client:
        bootstrap = BootstrapAdapter(client).fetch().payload
        fixtures_payload = FixturesAdapter(client).fetch().payload

    fixtures = fixtures_payload.get("items", fixtures_payload)
    if not isinstance(fixtures, list):
        raise AgentError(
            "unexpected fixtures payload shape",
            code=AgentErrorCode.SCHEMA_DRIFT,
            exit_code=ExitCode.UPSTREAM_DATA_FAILURE,
        )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_CACHE.write_text(json.dumps(bootstrap), encoding="utf-8")
    FIXTURES_CACHE.write_text(json.dumps(fixtures), encoding="utf-8")
    return bootstrap, fixtures


def next_gameweek(bootstrap: dict[str, Any]) -> int:
    events = bootstrap.get("events") or []
    for event in events:
        if event.get("is_next"):
            return int(event["id"])
    for event in events:
        if not event.get("finished"):
            return int(event["id"])
    return 1


def projections_for_horizon(
    *,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    weights: list[float],
) -> tuple[list[PlayerProjection], list[int]]:
    start = next_gameweek(bootstrap)
    gameweeks = list(range(start, start + len(weights)))
    projections = project_all(
        bootstrap=bootstrap,
        fixtures=fixtures,
        gameweeks=gameweeks,
        weights=weights,
    )
    return projections, gameweeks
