"""Team state resolution and private schema tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fpl_agent.config import load_settings
from fpl_agent.domain.models import Executability, SeasonId
from fpl_agent.errors import AgentError
from fpl_agent.team_state.private import PrivateTeamState, load_and_validate_private_state
from fpl_agent.team_state.resolve import resolve_team_state


def _private_payload(player_ids: list[int] | None = None) -> dict:
    ids = player_ids or list(range(1, 16))
    return {
        "schema_version": "1.0.0",
        "season": "2026-27",
        "applies_before_gameweek": 1,
        "as_of": datetime.now(UTC).isoformat(),
        "player_ids": ids,
        "bank_tenths": 15,
        "free_transfers": 1,
        "purchase_prices_tenths": {str(i): 50 for i in ids},
        "chip_instances": [],
    }


def test_private_state_requires_15(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    payload = _private_payload(list(range(1, 14)))
    path.write_text(json.dumps(payload))
    with pytest.raises(AgentError):
        load_and_validate_private_state(path)


def test_private_state_ok(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(_private_payload()))
    state = load_and_validate_private_state(path)
    assert isinstance(state, PrivateTeamState)
    assert len(state.player_ids) == 15


def test_executable_with_fresh_private(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(_private_payload()))
    private = load_and_validate_private_state(path)
    settings = load_settings(Path("config/settings.example.yaml"))
    catalog = {
        i: {"element_type": 1 if i <= 2 else 2 if i <= 7 else 3 if i <= 12 else 4, "team": i, "now_cost": 50}
        for i in range(1, 16)
    }
    resolved = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=1,
        private=private,
        catalog=catalog,
    )
    assert resolved.executability == Executability.EXECUTABLE
    assert resolved.executable_advice_allowed is True


def test_unknown_finance_conditional(tmp_path: Path) -> None:
    settings = load_settings(Path("config/settings.example.yaml"))
    # private with squad but we strip finance by resolving without private bank — use public picks confirmed
    resolved = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=1,
        public_picks={
            "post_deadline_confirmed": True,
            "picks": [{"element": i, "position": 1} for i in range(1, 16)],
        },
        catalog={i: {"element_type": 3, "team": (i % 10) + 1, "now_cost": 50} for i in range(1, 16)},
    )
    assert resolved.executability == Executability.CONDITIONAL_ONLY


def test_missing_squad_insufficient() -> None:
    settings = load_settings(Path("config/settings.example.yaml"))
    resolved = resolve_team_state(
        settings=settings,
        season=SeasonId.S2026_27,
        gameweek=1,
    )
    assert resolved.executability == Executability.INSUFFICIENT
    assert resolved.executable_advice_allowed is False
