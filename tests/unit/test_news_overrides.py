"""News override consumption tests."""

from __future__ import annotations

from datetime import UTC, datetime

from fpl_agent.evidence.models import ClaimCategory, EvidenceClaim
from fpl_agent.evidence.overrides import apply_official_overrides
from fpl_agent.projections.preseason import PlayerProjection


def _proj(pid: int) -> PlayerProjection:
    return PlayerProjection(
        player_id=pid,
        web_name=f"P{pid}",
        team_id=1,
        element_type=3,
        price_tenths=60,
        p_start=0.9,
        expected_minutes=80.0,
        points_per_90=4.0,
        xp_by_gw=(5.0,) * 6,
        weighted_xp=20.0,
    )


def test_official_out_vetoes_candidate() -> None:
    claims = [
        EvidenceClaim(
            claim_id="c1",
            category=ClaimCategory.INJURY,
            text="injured",
            source_url="https://fantasy.premierleague.com/",
            source_tier="official",
            player_ids=[10],
            retrieved_at=datetime.now(UTC),
            confidence=0.9,
            proposed_override={"availability": "out"},
        )
    ]
    result = apply_official_overrides(
        claims=claims,
        projections={10: _proj(10)},
        allowed_player_ids={10},
    )
    assert 10 not in result.projections
    assert 10 in result.removed_player_ids


def test_community_claim_does_not_mutate_numbers() -> None:
    claims = [
        EvidenceClaim(
            claim_id="c2",
            category=ClaimCategory.OTHER,
            text="rumour",
            source_url="https://reddit.com/r/FantasyPL",
            source_tier="community",
            player_ids=[10],
            retrieved_at=datetime.now(UTC),
            confidence=0.35,
            proposed_override={"availability": "out"},
        )
    ]
    before = _proj(10)
    result = apply_official_overrides(
        claims=claims,
        projections={10: before},
        allowed_player_ids={10},
    )
    assert result.projections[10].weighted_xp == before.weighted_xp
    assert not result.warnings


def test_override_emits_provenance() -> None:
    claims = [
        EvidenceClaim(
            claim_id="c3",
            category=ClaimCategory.INJURY,
            text="out",
            source_url="https://fantasy.premierleague.com/",
            source_tier="official",
            player_ids=[5],
            retrieved_at=datetime.now(UTC),
            confidence=0.9,
            proposed_override={"availability": "out"},
        )
    ]
    result = apply_official_overrides(claims=claims, projections={5: _proj(5)}, allowed_player_ids={5})
    assert any("official" in w for w in result.warnings)


def test_override_never_adds_player() -> None:
    result = apply_official_overrides(
        claims=[],
        projections={1: _proj(1)},
        allowed_player_ids={1},
    )
    assert set(result.projections) == {1}
