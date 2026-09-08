"""Materiality, notify fingerprints, optional webhook. Dry-run by default."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fpl_agent.config import PublishingSettings
from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.prices.snapshot import dumps_notify_state, load_notify_state
from fpl_agent.prices.types import (
    ActionClass,
    PriceAction,
    PriceDirection,
    PricePrediction,
    ReportStatus,
)


def fingerprint(
    *,
    season: str,
    gameweek: int,
    player_id: int,
    direction: PriceDirection | str,
    action_class: ActionClass | str,
    related_scenario_id: str | None,
) -> str:
    return "|".join(
        [
            season,
            str(gameweek),
            str(player_id),
            str(direction),
            str(action_class),
            related_scenario_id or "",
        ]
    )


def action_fingerprint(action: PriceAction, *, season: str, gameweek: int, direction: str) -> str:
    pid = action.player_ids[0] if action.player_ids else 0
    return fingerprint(
        season=season,
        gameweek=gameweek,
        player_id=pid,
        direction=direction,
        action_class=action.action_class,
        related_scenario_id=action.related_scenario_id,
    )


def should_notify(action: PriceAction) -> bool:
    return action.action_class in {
        ActionClass.ACT_NOW_RECOMMENDED,
        ActionClass.ACT_NOW_CONDITIONAL,
    }


def should_comment_issue(
    *,
    status: ReportStatus,
    notified: list[Any],
    market_likely_count: int = 0,
) -> bool:
    """Email-worthy GitHub Issue comment: act-now alerts or likely market movers."""
    if market_likely_count > 0:
        return True
    if not notified:
        return False
    return status in {ReportStatus.ACT_TONIGHT, ReportStatus.ACT_TONIGHT_CONDITIONAL}


def select_new_notifications(
    actions: list[PriceAction],
    *,
    season: str,
    gameweek: int,
    directions: dict[int, str],
    state_path: Path,
) -> tuple[list[PriceAction], list[str]]:
    prior = set(load_notify_state(state_path))
    fresh: list[PriceAction] = []
    all_prints = list(prior)
    for action in actions:
        if not should_notify(action):
            continue
        pid = action.player_ids[0] if action.player_ids else 0
        fp = action_fingerprint(
            action,
            season=season,
            gameweek=gameweek,
            direction=directions.get(pid, "none"),
        )
        if fp in prior:
            continue
        fresh.append(action)
        all_prints.append(fp)
    dumps_notify_state(state_path, all_prints)
    return fresh, all_prints


def maybe_post_webhook(
    *,
    url: str,
    dry_run: bool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """POST allowlisted JSON. Never echo secrets. HTTPS only."""
    meta = {
        "attempted": bool(url) and not dry_run,
        "dry_run": dry_run or not url,
        "ok": True,
    }
    if not url or dry_run:
        return meta
    import httpx

    body = {
        "action_class": payload.get("action_class"),
        "player_ids": payload.get("player_ids"),
        "gameweek": payload.get("gameweek"),
        "summary": payload.get("summary"),
        "report_hash": payload.get("report_hash"),
    }
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.post(url, json=body)
        meta["status"] = response.status_code
        meta["ok"] = 200 <= response.status_code < 300
    except httpx.HTTPError as exc:
        meta["ok"] = False
        meta["error"] = type(exc).__name__
    return meta


def issue_comment_ops(
    *,
    publishing: PublishingSettings,
    actions: list[PriceAction],
    gameweek: int,
    body: str,
) -> list[dict[str, Any]]:
    if publishing.dry_run or not publishing.issue_publishing:
        return []
    if not actions:
        return []
    return [
        {
            "op": "comment_current_gw_issue",
            "gameweek": gameweek,
            "body_hash": stable_json_hash(body),
        }
    ]


def prediction_by_id(predictions: list[PricePrediction]) -> dict[int, PricePrediction]:
    return {p.player_id: p for p in predictions}


def notify_payload(action: PriceAction, *, gameweek: int, report_hash: str) -> dict[str, Any]:
    return {
        "action_class": action.action_class.value,
        "player_ids": action.player_ids,
        "gameweek": gameweek,
        "summary": action.summary,
        "report_hash": report_hash,
        "as_of": datetime.now(UTC).isoformat(),
    }
