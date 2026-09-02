"""Deterministic XI / captain / horizon plan for pre-deadline reports."""

from __future__ import annotations

from typing import Any

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.rules.season import SeasonRules, load_season_rules_2026_27
from fpl_agent.strategy.draft import select_best_xi

POSITION_ABBR = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _gw_xp(player: PlayerProjection, index: int) -> float:
    if index < len(player.xp_by_gw):
        return float(player.xp_by_gw[index])
    return 0.0


def build_weekly_plan(
    *,
    owned_ids: list[int],
    projections: dict[int, PlayerProjection],
    gameweeks: list[int],
    captain_id: int | None = None,
    vice_id: int | None = None,
    rules: SeasonRules | None = None,
    transfer_path: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Lineup, captain, bench, and per-GW XI xP. Safe to embed in reports."""
    rules = rules or load_season_rules_2026_27()
    players = [projections[pid] for pid in owned_ids if pid in projections]
    if len(players) != len(owned_ids):
        return {"ok": False, "reason": "projection_gap"}

    xi, bench, formation = select_best_xi(players, rules, gameweek_index=0)

    def cap_key(player: PlayerProjection) -> tuple[float, int]:
        return (_gw_xp(player, 0) * (0.4 + 0.6 * player.p_start), player.player_id)

    model_captain = max(xi, key=cap_key)
    vice_pool = [p for p in xi if p.player_id != model_captain.player_id]
    model_vice = max(vice_pool, key=lambda p: (p.p_start, _gw_xp(p, 0), p.player_id)) if vice_pool else None

    horizon: list[dict[str, Any]] = []
    for index, gw in enumerate(gameweeks):
        xi_gw, _, _ = select_best_xi(players, rules, gameweek_index=index)
        cap = max(xi_gw, key=lambda p: (_gw_xp(p, index), p.player_id))
        horizon.append(
            {
                "gw": gw,
                "xi_xp": round(sum(_gw_xp(p, index) for p in xi_gw), 2),
                "captain": cap.web_name,
                "captain_xp": round(_gw_xp(cap, index), 2),
            }
        )

    def row(player: PlayerProjection) -> dict[str, Any]:
        return {
            "player_id": player.player_id,
            "web_name": player.web_name,
            "position": POSITION_ABBR.get(player.element_type, "?"),
            "p_start": round(player.p_start, 3),
            "xp_next": round(_gw_xp(player, 0), 2),
            "weighted_xp": round(player.weighted_xp, 2),
        }

    return {
        "ok": True,
        "formation": formation,
        "xi": [row(p) for p in xi],
        "bench": [row(p) for p in bench],
        "model_captain": row(model_captain),
        "model_vice": row(model_vice) if model_vice else None,
        "saved_captain_id": captain_id,
        "saved_vice_id": vice_id,
        "horizon": horizon,
        "transfer_path": transfer_path or [],
    }
