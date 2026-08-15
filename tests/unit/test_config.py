"""Configuration validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fpl_agent.config import load_settings
from fpl_agent.errors import AgentError, ExitCode


def test_example_config_loads() -> None:
    settings = load_settings(Path("config/settings.example.yaml"))
    assert settings.manager.team_id == 1
    assert settings.planning.horizon == 6
    assert len(settings.planning.weights) == 6


def test_rejects_non_positive_team_id(tmp_path: Path) -> None:
    raw = yaml.safe_load(Path("config/settings.example.yaml").read_text())
    raw["manager"]["team_id"] = 0
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(raw))
    with pytest.raises(AgentError) as exc:
        load_settings(path)
    assert exc.value.exit_code == ExitCode.INVALID_CONFIG


def test_rejects_weight_horizon_mismatch(tmp_path: Path) -> None:
    raw = yaml.safe_load(Path("config/settings.example.yaml").read_text())
    raw["planning"]["weights"] = [1.0, 0.9]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(raw))
    with pytest.raises(AgentError):
        load_settings(path)


def test_rejects_safety_floor_not_inside_window(tmp_path: Path) -> None:
    raw = yaml.safe_load(Path("config/settings.example.yaml").read_text())
    raw["alerts"]["safety_floor_minutes"] = 180
    raw["alerts"]["deadline_window_minutes"] = 180
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(raw))
    with pytest.raises(AgentError):
        load_settings(path)


def test_rejects_invalid_timezone(tmp_path: Path) -> None:
    raw = yaml.safe_load(Path("config/settings.example.yaml").read_text())
    raw["manager"]["timezone"] = "Not/AZone"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.dump(raw))
    with pytest.raises(AgentError):
        load_settings(path)
