"""Classic mini-league rival context (sampled exposure, not global EO)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RivalContext:
    manager_rank: int | None
    rivals_above: list[dict[str, Any]]
    rivals_below: list[dict[str, Any]]
    sampled_exposure: dict[int, float]
    warnings: list[str]


def select_rivals(standings: list[dict[str, Any]], manager_entry_id: int, n: int = 5) -> RivalContext:
    warnings: list[str] = []
    ordered = sorted(standings, key=lambda r: int(r.get("rank") or 10**9))
    idx = next((i for i, r in enumerate(ordered) if int(r.get("entry", -1)) == manager_entry_id), None)
    if idx is None:
        return RivalContext(None, [], [], {}, ["manager not found in standings; continuing without rivals"])
    above = list(reversed(ordered[max(0, idx - n) : idx]))
    below = ordered[idx + 1 : idx + 1 + n]
    return RivalContext(int(ordered[idx].get("rank") or 0), above, below, {}, warnings)


def sampled_captain_exposure(rival_picks: list[dict[str, Any]]) -> dict[int, float]:
    """Fraction of sampled rivals captaining each player — not global EO."""
    if not rival_picks:
        return {}
    counts: dict[int, int] = {}
    for picks in rival_picks:
        for p in picks.get("picks") or []:
            if p.get("is_captain"):
                pid = int(p["element"])
                counts[pid] = counts.get(pid, 0) + 1
    n = len(rival_picks)
    return {pid: c / n for pid, c in counts.items()}
