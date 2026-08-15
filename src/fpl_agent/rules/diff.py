"""Compare stored SeasonRules against live bootstrap metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fpl_agent.domain.models import ChipHalf, ChipKind
from fpl_agent.rules.season import SeasonRules


class DriftSeverity(StrEnum):
    NONE = "no_material_change"
    NON_BREAKING = "non_breaking_observed_change"
    MATERIAL = "material_unreviewed_change"


def compare_rules_to_bootstrap(rules: SeasonRules, bootstrap: dict[str, Any]) -> tuple[DriftSeverity, list[str]]:
    gs = bootstrap.get("game_settings") or {}
    notes: list[str] = []
    material = False
    non_breaking = False

    checks = [
        ("squad_squadsize", rules.squad_size, "squad_size"),
        ("squad_squadplay", rules.starters, "starters"),
        ("squad_team_limit", rules.club_limit, "club_limit"),
        ("squad_total_spend", rules.initial_budget_tenths, "initial_budget_tenths"),
    ]
    for key, expected, label in checks:
        if key in gs and gs[key] != expected:
            material = True
            notes.append(f"{label}: stored={expected} live={gs[key]}")

    if "transfers_sell_on_fee" in gs and float(gs["transfers_sell_on_fee"]) != rules.sell_on_fee_fraction:
        material = True
        notes.append(
            f"sell_on_fee: stored={rules.sell_on_fee_fraction} live={gs['transfers_sell_on_fee']}"
        )

    max_extra = gs.get("max_extra_free_transfers")
    if max_extra is not None:
        expected_extra = rules.max_banked_free_transfers - rules.free_transfers_per_gw
        if max_extra != expected_extra:
            material = True
            notes.append(f"max_banked_ft encoding: expected_extra={expected_extra} live={max_extra}")

    live_chips = bootstrap.get("chips") or []
    if live_chips:
        stored = {
            (c.kind.value, c.half.value, c.start_event, c.stop_event) for c in rules.chip_instances
        }
        live = set()
        for c in live_chips:
            half = ChipHalf.FIRST if int(c["stop_event"]) <= 19 else ChipHalf.SECOND
            live.add((c["name"], half.value, int(c["start_event"]), int(c["stop_event"])))
        if stored != live:
            # chip window drift is material
            material = True
            notes.append(f"chip windows differ: stored={sorted(stored)} live={sorted(live)}")
    else:
        non_breaking = True
        notes.append("chips missing from bootstrap payload")

    # element type quotas
    for et in bootstrap.get("element_types") or []:
        # map later in caller; soft check sizes
        if et.get("squad_select") is None:
            non_breaking = True

    if material:
        return DriftSeverity.MATERIAL, notes
    if non_breaking or notes:
        return DriftSeverity.NON_BREAKING, notes
    return DriftSeverity.NONE, notes


# silence unused import warning for ChipKind in type docs
_ = ChipKind
