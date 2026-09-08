"""Mermaid charts for the predeadline reflection section.

History is read from the recomputable ``data/evaluation/reflection-gw*.json``
cache (M1) — never from live FPL fetches.
"""

from __future__ import annotations

import re
from pathlib import Path

from fpl_agent.evaluation.reflection import ReflectionSummary, load_reflection_summary


def load_reflection_history(
    root: Path,
    *,
    through_gameweek: int,
    max_gws: int = 6,
) -> list[ReflectionSummary]:
    """Load cached reflections ending at ``through_gameweek``, oldest first.

    Skips missing GWs without erroring. Returns ``[]`` when nothing is cached.
    """
    if through_gameweek < 1 or max_gws < 1:
        return []
    start = max(1, through_gameweek - max_gws + 1)
    out: list[ReflectionSummary] = []
    for gw in range(start, through_gameweek + 1):
        path = root / f"reflection-gw{gw}.json"
        if not path.exists():
            continue
        try:
            out.append(load_reflection_summary(path))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def mermaid_calibration_trend(history: list[ReflectionSummary]) -> str | None:
    """Two-line xychart of predicted XI xP vs actual XI points.

    Returns ``None`` unless at least two GWs have both values.
    """
    points: list[tuple[int, float, float]] = []
    for row in history:
        if row.predicted_xi_xp is None or row.actual_xi_points is None:
            continue
        points.append((row.gameweek, float(row.predicted_xi_xp), float(row.actual_xi_points)))
    if len(points) < 2:
        return None
    labels = ", ".join(f"GW{gw}" for gw, _, _ in points)
    predicted = ", ".join(f"{pred:.1f}" for _, pred, _ in points)
    actual = ", ".join(f"{act:.1f}" for _, _, act in points)
    y_vals = [p for _, p, _ in points] + [a for _, _, a in points]
    y_min = max(0, int(min(y_vals) - 2))
    y_max = int(max(y_vals) + 2)
    return "\n".join(
        [
            "```mermaid",
            "xychart-beta",
            '    title "XI predicted xP vs actual points"',
            f"    x-axis [{labels}]",
            f'    y-axis "Points" {y_min} --> {y_max}',
            f"    line [{predicted}]",
            f"    line [{actual}]",
            "```",
        ]
    )


def mermaid_transfer_payoff_trend(history: list[ReflectionSummary]) -> str | None:
    """Transfer actual-delta trend for GWs that had a recommended transfer.

    Hold weeks (no transfer) are omitted, not plotted as zero. Uses a ``line``
    series (not ``bar``) so GitHub-flavored Mermaid renders reliably — matching
    the existing ``plan_doc`` xychart convention.
    """
    points: list[tuple[int, int]] = []
    for row in history:
        if row.transfer_out_name is None or row.transfer_in_name is None:
            continue
        if row.transfer_actual_delta is None:
            continue
        points.append((row.gameweek, int(row.transfer_actual_delta)))
    if len(points) < 2:
        return None
    labels = ", ".join(f"GW{gw}" for gw, _ in points)
    deltas = ", ".join(str(delta) for _, delta in points)
    y_vals = [d for _, d in points]
    y_min = int(min(y_vals) - 2)
    y_max = int(max(y_vals) + 2)
    return "\n".join(
        [
            "```mermaid",
            "xychart-beta",
            '    title "Transfer payoff (IN − OUT actual pts)"',
            f"    x-axis [{labels}]",
            f'    y-axis "Delta pts" {y_min} --> {y_max}',
            f"    line [{deltas}]",
            "```",
        ]
    )


_LINE_RE = re.compile(r"line\s*\[([^\]]+)\]")


def parse_mermaid_line_series(chart: str) -> list[list[float]]:
    """Extract numeric series from generated ``line [...]`` rows (for tests)."""
    series: list[list[float]] = []
    for match in _LINE_RE.finditer(chart):
        series.append([float(part.strip()) for part in match.group(1).split(",") if part.strip()])
    return series
