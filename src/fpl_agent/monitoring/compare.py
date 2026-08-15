"""Deterministic snapshot comparison and material-change classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpl_agent.domain.run_state import stable_json_hash


@dataclass
class MonitorSummary:
    material: bool
    changes: list[str]
    heartbeat_hash: str


def classify_material_change(before: dict[str, Any], after: dict[str, Any]) -> MonitorSummary:
    changes: list[str] = []
    # timestamps alone must not create material change
    keys = set(before) | set(after)
    ignore = {
        "timestamp",
        "timestamps",
        "retrieved_at",
        "as_of",
        "generated_at",
        "data_cutoff",
    }
    for key in sorted(keys - ignore):
        if before.get(key) != after.get(key):
            changes.append(key)
    material = bool(changes)
    payload = {"material": material, "changes": changes}
    return MonitorSummary(
        material=material,
        changes=changes,
        heartbeat_hash=stable_json_hash(payload),
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
        "heartbeat_hash": summary.heartbeat_hash,
    }
