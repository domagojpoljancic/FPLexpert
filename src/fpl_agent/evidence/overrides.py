"""Consume official-tier news overrides deterministically."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fpl_agent.evidence.models import EvidenceClaim
from fpl_agent.projections.preseason import PlayerProjection

OFFICIAL_OVERRIDE_MIN_CONFIDENCE = 0.85


@dataclass(frozen=True)
class OverrideResult:
    projections: dict[int, PlayerProjection]
    removed_player_ids: tuple[int, ...]
    warnings: tuple[str, ...]


def apply_official_overrides(
    *,
    claims: list[EvidenceClaim],
    projections: dict[int, PlayerProjection],
    allowed_player_ids: set[int],
    min_confidence: float = OFFICIAL_OVERRIDE_MIN_CONFIDENCE,
) -> OverrideResult:
    """Veto/downgrade only — never add players."""
    removed: list[int] = []
    warnings: list[str] = []
    updated = dict(projections)
    for claim in claims:
        if claim.confidence < min_confidence:
            continue
        if claim.source_tier != "official":
            continue
        override = claim.proposed_override or {}
        for pid in claim.player_ids:
            if pid not in allowed_player_ids or pid not in updated:
                continue
            availability = str(override.get("availability") or "")
            if availability == "out":
                removed.append(pid)
                updated.pop(pid, None)
                warnings.append(f"removed {pid}: ruled out (official)")
            elif availability == "limited" and pid in updated:
                proj = updated[pid]
                updated[pid] = PlayerProjection(
                    player_id=proj.player_id,
                    web_name=proj.web_name,
                    team_id=proj.team_id,
                    element_type=proj.element_type,
                    price_tenths=proj.price_tenths,
                    p_start=min(proj.p_start, 0.5),
                    expected_minutes=proj.expected_minutes * 0.5,
                    points_per_90=proj.points_per_90,
                    xp_by_gw=tuple(x * 0.75 for x in proj.xp_by_gw),
                    weighted_xp=proj.weighted_xp * 0.75,
                    availability_note="news_override_limited",
                    warnings=proj.warnings + ("news_override_limited",),
                )
                warnings.append(f"downgraded {pid}: limited availability (official)")
    return OverrideResult(
        projections=updated,
        removed_player_ids=tuple(sorted(set(removed))),
        warnings=tuple(warnings),
    )
