"""Payload compaction must keep the locked primary, never corrupt JSON."""

from __future__ import annotations

import json

from fpl_agent.llm.client import (
    PAYLOAD_CORE_TOO_LARGE,
    _compact_payload,
)


def _base_payload() -> dict:
    return {
        "mode": "predeadline",
        "gameweek": 3,
        "bank_tenths": 0,
        "free_transfers": 1,
        "weekly_plan": {
            "ok": True,
            "primary_move": {
                "action": "transfer",
                "out_id": 539,
                "in_id": 277,
                "out_name": "O'Nien",
                "in_name": "Egan",
            },
            "best_affordable": {"out_id": 539, "in_id": 277},
            "model_vice": {"web_name": "Raya", "player_id": 1},
            "model_captain": {"web_name": "B.Fernandes", "player_id": 426},
            "after_transfer": {"in_id": 277, "out_id": 539},
            "alternatives": [{"action": "hold"}],
            "veto_watchlist": [{"player_id": 277, "web_name": "Egan"}],
        },
        "price_actions": [],
        "policy": {"recommend_only": True},
        "squad": [],
        "sources": [],
    }


def test_normal_payload_unchanged() -> None:
    payload = _base_payload()
    text, warnings = _compact_payload(payload, max_chars=24_000)
    assert warnings == []
    assert json.loads(text) == json.loads(json.dumps(payload, sort_keys=True, default=str))


def test_oversized_elastic_lists_keep_primary_and_valid_json() -> None:
    payload = _base_payload()
    payload["squad"] = [{"player_id": i, "web_name": f"Pad{i}", "blurb": "x" * 200} for i in range(200)]
    payload["sources"] = [{"claim_id": f"c{i}", "text": "y" * 200} for i in range(200)]
    text, warnings = _compact_payload(payload, max_chars=4_000)
    parsed = json.loads(text)  # must be valid JSON
    assert isinstance(parsed, dict)
    weekly = parsed["weekly_plan"]
    assert weekly["primary_move"]["in_id"] == 277
    assert weekly["model_vice"]["web_name"] == "Raya"
    assert PAYLOAD_CORE_TOO_LARGE not in warnings or weekly["primary_move"]["in_id"] == 277


def test_core_too_large_emits_warning_still_valid_json() -> None:
    payload = _base_payload()
    # Make weekly_plan itself huge while keeping lock keys.
    payload["weekly_plan"]["also_considered"] = [
        {"in_name": f"Alt{i}", "reason": "z" * 500} for i in range(200)
    ]
    text, warnings = _compact_payload(payload, max_chars=800)
    parsed = json.loads(text)
    assert PAYLOAD_CORE_TOO_LARGE in warnings
    assert "...\"}" not in text
    assert parsed["weekly_plan"]["primary_move"]["in_id"] == 277
