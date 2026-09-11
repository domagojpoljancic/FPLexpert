"""Tests for live GW form loading used by xp-v2.2 haul resistance."""

from __future__ import annotations

from fpl_agent.projections.live_form import load_recent_points_by_player


def test_load_recent_points_skips_offline() -> None:
    bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": False}]}
    assert load_recent_points_by_player(bootstrap, offline=True) == {}


def test_load_recent_points_skips_preseason() -> None:
    bootstrap = {"events": [{"id": 1, "finished": False, "is_next": True}]}
    assert load_recent_points_by_player(bootstrap, offline=False) == {}


def test_load_recent_points_skips_after_early_window() -> None:
    bootstrap = {
        "events": [{"id": i, "finished": True} for i in range(1, 8)]
        + [{"id": 8, "finished": False}]
    }
    assert load_recent_points_by_player(bootstrap, offline=False) == {}
