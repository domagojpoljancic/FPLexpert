"""Deterministic snapshot comparison and material-change classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fpl_agent.domain.run_state import stable_json_hash

TIMESTAMP_KEYS = {
    "timestamp",
    "timestamps",
    "retrieved_at",
    "as_of",
    "generated_at",
    "data_cutoff",
}


@dataclass
class MonitorSummary:
    material: bool
    changes: list[str]
    heartbeat_hash: str
    change_types: list[str] = field(default_factory=list)


def _change_type(key: str, before: Any, after: Any) -> str:
    if key in {"now_cost", "now_cost_tenths"}:
        return "now_cost_observed"
    if key in {"likelihood", "likelihood_band"}:
        return "likelihood_band"
    if key == "action_class":
        after_s = str(after)
        before_s = str(before)
        if after_s.startswith("act_now") and not before_s.startswith("act_now"):
            return "action_class_escalation"
        return "action_class"
    if key in {"prediction_hit", "prediction_miss", "prediction_outcome"}:
        return "prediction_outcome"
    return "field_changed"


def classify_material_change(before: dict[str, Any], after: dict[str, Any]) -> MonitorSummary:
    changes: list[str] = []
    change_types: list[str] = []
    keys = set(before) | set(after)
    for key in sorted(keys - TIMESTAMP_KEYS):
        if before.get(key) != after.get(key):
            changes.append(key)
            change_types.append(_change_type(key, before.get(key), after.get(key)))
    material = bool(changes)
    payload = {"material": material, "changes": changes, "change_types": change_types}
    return MonitorSummary(
        material=material,
        changes=changes,
        heartbeat_hash=stable_json_hash(payload),
        change_types=change_types,
    )


def run_monitor(
    *,
    offline: bool = True,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before = before or {}
    after = after or before
    summary = classify_material_change(before, after)
    return {
        "offline": offline,
        "material": summary.material,
        "changes": summary.changes,
        "change_types": summary.change_types,
        "heartbeat_hash": summary.heartbeat_hash,
    }
