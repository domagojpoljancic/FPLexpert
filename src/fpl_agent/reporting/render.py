"""Escape and render actionable Markdown reports."""

from __future__ import annotations

import html
from typing import Any


def escape_md(text: str) -> str:
    return html.escape(text, quote=True)


def render_deadline_report(payload: dict[str, Any]) -> str:
    status = escape_md(str(payload.get("executability", "UNKNOWN")))
    primary = payload.get("primary") or {}
    lines = [
        f"# FPL Agent — GW {payload.get('gameweek')}",
        "",
        "## Decision summary",
        f"- Status: **{status}**",
        f"- Primary plan: {escape_md(str(primary.get('summary', 'no executable recommendation')))}",
        f"- Hit: {primary.get('hit_cost', 0)}",
        f"- Bank after: {primary.get('bank_after')}",
        f"- Freshness: {escape_md(str(payload.get('freshness', '')))}",
        f"- Captain: {primary.get('captain_id')} / Vice: {primary.get('vice_id')}",
        f"- Chip: {escape_md(str(primary.get('chip', 'none')))}",
        "",
        "## Six-gameweek table",
    ]
    for row in payload.get("horizon_table") or []:
        lines.append(f"- GW{row.get('gw')}: {row.get('xp')}")
    lines += ["", "## Warnings"]
    for wmsg in payload.get("warnings") or []:
        lines.append(f"- {escape_md(str(wmsg))}")
    lines += ["", f"Run ID: `{escape_md(str(payload.get('run_id', '')))}`"]
    return "\n".join(lines)
