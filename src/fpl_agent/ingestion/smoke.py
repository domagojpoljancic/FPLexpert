"""Opt-in live smoke checks."""

from __future__ import annotations

from typing import Any

from fpl_agent.ingestion.client import BootstrapAdapter, FplClient, current_and_next_gameweek


def live_smoke_check() -> dict[str, Any]:
    with FplClient() as client:
        snap = BootstrapAdapter(client).fetch()
        events = snap.payload.get("events") or []
        current, nxt = current_and_next_gameweek(events)
        return {
            "ok": True,
            "content_hash": snap.content_hash,
            "current_gw": current,
            "next_gw": nxt,
            "teams": len(snap.payload.get("teams") or []),
            "elements": len(snap.payload.get("elements") or []),
        }
