"""Tests for live GW form loading used by xp-v2.2 haul resistance."""

from __future__ import annotations

import json
from pathlib import Path

from fpl_agent.projections.live_form import load_recent_points_by_player


def test_load_recent_points_offline_uses_matching_cache(tmp_path: Path) -> None:
    bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": False}]}
    cache = tmp_path / "live-gw-points.json"
    cache.write_text(
        json.dumps(
            {
                "event_ids": [1],
                "points_by_player": {"426": [2.0, 23.0, 2.0]},
            }
        ),
        encoding="utf-8",
    )
    got = load_recent_points_by_player(bootstrap, offline=True, cache_path=cache)
    assert got == {426: [2.0, 23.0, 2.0]}


def test_load_recent_points_offline_skips_mismatched_cache(tmp_path: Path) -> None:
    bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": True}]}
    cache = tmp_path / "live-gw-points.json"
    cache.write_text(
        json.dumps({"event_ids": [1], "points_by_player": {"1": [5.0]}}),
        encoding="utf-8",
    )
    assert load_recent_points_by_player(bootstrap, offline=True, cache_path=cache) == {}


def test_load_recent_points_offline_empty_without_cache(tmp_path: Path) -> None:
    bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": False}]}
    cache = tmp_path / "missing.json"
    assert load_recent_points_by_player(bootstrap, offline=True, cache_path=cache) == {}


def test_load_recent_points_skips_preseason() -> None:
    bootstrap = {"events": [{"id": 1, "finished": False, "is_next": True}]}
    assert load_recent_points_by_player(bootstrap, offline=False) == {}


def test_load_recent_points_skips_after_early_window() -> None:
    bootstrap = {
        "events": [{"id": i, "finished": True} for i in range(1, 8)]
        + [{"id": 8, "finished": False}]
    }
    assert load_recent_points_by_player(bootstrap, offline=False) == {}
