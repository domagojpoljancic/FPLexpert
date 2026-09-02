"""Deterministic captain/vice selection with floor, ceiling, and nailedness."""

from __future__ import annotations

from typing import Any

from fpl_agent.projections.preseason import PlayerProjection

POSITION_ABBR = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def _gw_xp(player: PlayerProjection, index: int) -> float:
    if index < len(player.xp_by_gw):
        return float(player.xp_by_gw[index])
    return 0.0


def _haul_proxy(player: PlayerProjection, element: dict[str, Any] | None) -> float:
    """Transparent ceiling proxy from price, position, and penalties — not realized hauls."""
    proxy = 0.0
    if player.element_type == 4 and player.price_tenths >= 90:
        proxy += 0.35
    elif player.element_type == 3 and player.price_tenths >= 100:
        proxy += 0.25
    if element:
        if element.get("penalties_order") == 1:
            proxy += 0.20
        try:
            xg = float(element.get("expected_goals") or 0)
            if xg > 0.5:
                proxy += min(0.25, xg * 0.15)
        except (TypeError, ValueError):
            pass
    return min(1.0, proxy)


def captain_components(
    player: PlayerProjection,
    gw_index: int = 0,
    *,
    element: dict[str, Any] | None = None,
) -> dict[str, float]:
    mean_xp = _gw_xp(player, gw_index)
    p_start = player.p_start
    floor = mean_xp * (0.5 + 0.5 * p_start)
    haul = _haul_proxy(player, element)
    ceiling = mean_xp * (1.0 + haul)
    score = mean_xp * (0.4 + 0.6 * p_start) + 0.35 * (ceiling - mean_xp)
    return {
        "mean_xp": mean_xp,
        "p_start": p_start,
        "floor": floor,
        "ceiling": ceiling,
        "haul_proxy": haul,
        "captain_score": score,
    }


def pick_captain_and_vice(
    xi: list[PlayerProjection],
    *,
    gw_index: int = 0,
    catalog: dict[int, dict[str, Any]] | None = None,
) -> tuple[PlayerProjection, PlayerProjection | None, dict[str, Any]]:
    """Captain by score; vice = best nailed backup if captain misses."""
    if not xi:
        raise ValueError("empty XI")
    scored = []
    rationale: dict[str, Any] = {}
    for player in xi:
        element = (catalog or {}).get(player.player_id)
        comp = captain_components(player, gw_index, element=element)
        scored.append((comp["captain_score"], player, comp))
    scored.sort(key=lambda row: (-row[0], -row[2]["ceiling"], -row[1].player_id))
    captain = scored[0][1]
    cap_comp = scored[0][2]
    rationale["captain"] = {
        "player_id": captain.player_id,
        "web_name": captain.web_name,
        **{k: round(v, 3) for k, v in cap_comp.items()},
    }
    vice_pool = [p for p in xi if p.player_id != captain.player_id]
    if not vice_pool:
        return captain, None, rationale
    vice = max(
        vice_pool,
        key=lambda p: (
            p.p_start,
            captain_components(p, gw_index, element=(catalog or {}).get(p.player_id))["captain_score"],
            _gw_xp(p, gw_index),
            -p.player_id,
        ),
    )
    vice_comp = captain_components(vice, gw_index, element=(catalog or {}).get(vice.player_id))
    rationale["vice"] = {
        "player_id": vice.player_id,
        "web_name": vice.web_name,
        **{k: round(v, 3) for k, v in vice_comp.items()},
    }
    return captain, vice, rationale
