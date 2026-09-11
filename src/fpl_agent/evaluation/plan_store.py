"""Git-trackable slim weekly plans so reflection can load prior GWs without local JSON reports.

Full ``reports/predeadline-gw*.json`` dumps stay gitignored (noisy, may include extras).
Each predeadline run also writes ``data/plans/gw{N}-weekly-plan.json`` with only the fields
reflection / scorecard / learning need. Those slim files are safe to commit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_PLANS_DIR = Path("data/plans")

# Keys reflection + learning need from weekly_plan (see evaluation/reflection.py).
_SLIM_TOP_LEVEL = (
    "ok",
    "xi",
    "model_captain",
    "saved_captain_id",
    "best_affordable",
    "after_transfer",
    "also_considered",
    "predeadline_ev_positive",
    "recommendation_net",
    "roll_net",
    "horizon",
)


def plan_path(gameweek: int, plans_dir: Path | None = None) -> Path:
    root = plans_dir if plans_dir is not None else DEFAULT_PLANS_DIR
    return root / f"gw{int(gameweek)}-weekly-plan.json"


def slim_weekly_plan(weekly_plan: dict[str, Any]) -> dict[str, Any]:
    """Copy only machine fields needed to score and reflect on a past plan."""
    out: dict[str, Any] = {"ok": bool(weekly_plan.get("ok"))}
    for key in _SLIM_TOP_LEVEL:
        if key == "ok":
            continue
        if key in weekly_plan:
            out[key] = weekly_plan[key]
    return out


def save_weekly_plan(
    gameweek: int,
    weekly_plan: dict[str, Any],
    *,
    plans_dir: Path | None = None,
) -> Path | None:
    """Persist a slim plan for ``gameweek``. Returns path, or None if plan not ok."""
    if not isinstance(weekly_plan, dict) or not weekly_plan.get("ok"):
        return None
    root = plans_dir if plans_dir is not None else DEFAULT_PLANS_DIR
    root.mkdir(parents=True, exist_ok=True)
    path = plan_path(gameweek, root)
    payload = {
        "schema_version": "plan-store-v1",
        "gameweek": int(gameweek),
        "weekly_plan": slim_weekly_plan(weekly_plan),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_weekly_plan(
    gameweek: int,
    *,
    plans_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Load a persisted slim weekly_plan for ``gameweek``, or None."""
    path = plan_path(gameweek, plans_dir)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    plan = payload.get("weekly_plan") if isinstance(payload, dict) else None
    if isinstance(plan, dict) and plan.get("ok"):
        return plan
    return None
