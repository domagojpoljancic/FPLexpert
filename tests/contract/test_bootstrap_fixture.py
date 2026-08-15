"""Contract fixture for bootstrap required fields."""

from __future__ import annotations

import json
from pathlib import Path

REQUIRED = ["events", "elements", "teams", "element_types", "game_settings"]


def test_bootstrap_fixture_has_required_fields() -> None:
    data = json.loads(Path("tests/fixtures/bootstrap_static_reduced.json").read_text())
    for field in REQUIRED:
        assert field in data
    assert len(data["chips"]) == 8
