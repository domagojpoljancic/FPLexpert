"""Compare a saved weekly plan to official per-player GW points."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fpl_agent.ingestion.client import FplClient, LiveAdapter


@dataclass(frozen=True)
class Scorecard:
    gameweek: int
    model_xi_points: int
    model_captain_points: int
    model_captain_name: str
    saved_captain_points: int | None
    saved_captain_name: str | None
    transfer_out_points: int | None
    transfer_in_points: int | None
    transfer_delta: int | None
    notes: tuple[str, ...]

    def as_payload(self) -> dict[str, Any]:
        return {
            "gameweek": self.gameweek,
            "model_xi_points": self.model_xi_points,
            "model_captain_points": self.model_captain_points,
            "model_captain_name": self.model_captain_name,
            "saved_captain_points": self.saved_captain_points,
            "saved_captain_name": self.saved_captain_name,
            "transfer_out_points": self.transfer_out_points,
            "transfer_in_points": self.transfer_in_points,
            "transfer_delta": self.transfer_delta,
            "notes": list(self.notes),
        }


def points_from_live_payload(payload: dict[str, Any]) -> dict[int, int]:
    """Map element id -> total points for the gameweek live feed."""
    out: dict[int, int] = {}
    for row in payload.get("elements") or []:
        if not isinstance(row, dict):
            continue
        pid = int(row.get("id") or 0)
        stats = row.get("stats") or {}
        if not pid:
            continue
        out[pid] = int(stats.get("total_points") or 0)
    return out


def scorecard_from_plan(
    *,
    gameweek: int,
    weekly_plan: dict[str, Any],
    player_points: dict[int, int],
) -> Scorecard:
    xi = list(weekly_plan.get("xi") or [])
    cap = weekly_plan.get("model_captain") or {}
    cap_id = int(cap.get("player_id") or 0)
    cap_name = str(cap.get("web_name") or cap_id or "?")
    xi_points = 0
    notes: list[str] = []
    for row in xi:
        pid = int(row.get("player_id") or 0)
        if not pid:
            continue
        pts = int(player_points.get(pid, 0))
        xi_points += pts
        if pid not in player_points:
            notes.append(f"missing live points for {row.get('web_name') or pid}")
    cap_raw = int(player_points.get(cap_id, 0)) if cap_id else 0
    cap_scored = cap_raw * 2 if cap_id else 0

    saved_id = weekly_plan.get("saved_captain_id")
    saved_pts: int | None = None
    saved_name: str | None = None
    if saved_id:
        saved_id = int(saved_id)
        saved_pts = int(player_points.get(saved_id, 0)) * 2
        saved_row = next((p for p in xi if int(p.get("player_id") or 0) == saved_id), None)
        saved_name = str((saved_row or {}).get("web_name") or saved_id)
        if saved_id != cap_id:
            notes.append(
                f"saved captain {saved_name} scored {saved_pts}; model captain {cap_name} scored {cap_scored}"
            )

    best = weekly_plan.get("best_affordable") or {}
    out_id = int(best.get("out_id") or 0) if best else 0
    in_id = int(best.get("in_id") or 0) if best else 0
    out_pts = int(player_points[out_id]) if out_id and out_id in player_points else None
    in_pts = int(player_points[in_id]) if in_id and in_id in player_points else None
    delta = None
    if out_pts is not None and in_pts is not None:
        delta = in_pts - out_pts
        notes.append(
            f"recommended {best.get('out_name')} ({out_pts}) → {best.get('in_name')} ({in_pts})"
        )

    return Scorecard(
        gameweek=gameweek,
        model_xi_points=xi_points,
        model_captain_points=cap_scored,
        model_captain_name=cap_name,
        saved_captain_points=saved_pts,
        saved_captain_name=saved_name,
        transfer_out_points=out_pts,
        transfer_in_points=in_pts,
        transfer_delta=delta,
        notes=tuple(notes),
    )


def load_latest_predeadline_plan(reports_dir: Path, gameweek: int) -> dict[str, Any] | None:
    paths = sorted(reports_dir.glob(f"predeadline-gw{gameweek}-*.json"), reverse=True)
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        plan = payload.get("weekly_plan")
        if isinstance(plan, dict) and plan.get("ok"):
            return plan
    return None


def fetch_live_points(gameweek: int, *, client: FplClient | None = None) -> dict[int, int]:
    own = client is None
    http = client or FplClient()
    try:
        snap = LiveAdapter(http).fetch(gameweek)
        return points_from_live_payload(snap.payload)
    finally:
        if own:
            http.close()


def build_previous_scorecard(
    *,
    previous_gameweek: int,
    reports_dir: Path = Path("reports"),
    player_points: dict[int, int] | None = None,
    client: FplClient | None = None,
) -> Scorecard | None:
    if previous_gameweek < 1:
        return None
    plan = load_latest_predeadline_plan(reports_dir, previous_gameweek)
    if plan is None:
        return None
    points = player_points if player_points is not None else fetch_live_points(previous_gameweek, client=client)
    return scorecard_from_plan(gameweek=previous_gameweek, weekly_plan=plan, player_points=points)
