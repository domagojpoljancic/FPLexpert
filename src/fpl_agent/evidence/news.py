"""Build normalized evidence from FPL bootstrap news + optional LLM search sources."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fpl_agent.domain.run_state import stable_json_hash
from fpl_agent.evidence.models import ClaimCategory, EvidenceClaim, SearchRequest

OFFICIAL_HOST_FRAGMENTS = (
    "premierleague.com",
    "fantasy.premierleague.com",
)
ESTABLISHED_HOST_FRAGMENTS = (
    "bbc.",
    "skysports.",
    "theguardian.",
    "nytimes.",
    "theathletic.",
    "goal.com",
    "standard.co.uk",
    "telegraph.co.uk",
)


def source_tier_for_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if any(h in host for h in OFFICIAL_HOST_FRAGMENTS):
        return "official"
    if "reddit.com" in host:
        return "community"
    if any(h in host for h in ESTABLISHED_HOST_FRAGMENTS):
        return "established"
    return "community"


def claims_from_bootstrap_news(
    *,
    elements: list[dict[str, Any]],
    player_ids: set[int],
    now: datetime | None = None,
) -> list[EvidenceClaim]:
    """Official-ish FPL status/news fields for the user's squad (no web needed)."""
    now = now or datetime.now(UTC)
    claims: list[EvidenceClaim] = []
    for element in elements:
        pid = int(element["id"])
        if pid not in player_ids:
            continue
        status = str(element.get("status") or "a")
        news = str(element.get("news") or "").strip()
        chance = element.get("chance_of_playing_next_round")
        if status == "a" and not news and chance in (None, 100):
            continue

        if status in {"i", "d"} or (chance is not None and float(chance) < 100):
            category = ClaimCategory.INJURY if status in {"i", "d"} else ClaimCategory.AVAILABILITY
        elif status == "s":
            category = ClaimCategory.SUSPENSION
        else:
            category = ClaimCategory.OTHER

        text = news or f"FPL status={status} chance_of_playing_next_round={chance}"
        claim_id = stable_json_hash({"pid": pid, "status": status, "news": news, "chance": chance})[:16]
        claims.append(
            EvidenceClaim(
                claim_id=f"fpl-{claim_id}",
                category=category,
                text=text[:2000],
                source_url="https://fantasy.premierleague.com/",
                source_tier="official",
                player_ids=[pid],
                team_ids=[int(element.get("team") or 0)],
                retrieved_at=now,
                confidence=0.85 if status in {"i", "s"} else 0.65,
                expires_at=now + timedelta(hours=24),
                proposed_override={
                    "availability": "out"
                    if status in {"i", "u", "n", "s"} or chance == 0
                    else "limited"
                    if status == "d" or (chance is not None and float(chance) < 75)
                    else "available"
                },
            )
        )
    return claims


def claims_from_search_sources(
    sources: list[dict[str, str]],
    *,
    player_ids: list[int],
    now: datetime | None = None,
) -> list[EvidenceClaim]:
    """Map web-search URL sources into low-precision evidence placeholders."""
    now = now or datetime.now(UTC)
    claims: list[EvidenceClaim] = []
    for src in sources:
        url = src.get("url") or ""
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        claim_id = "web-" + stable_json_hash(url)[:14]
        claims.append(
            EvidenceClaim(
                claim_id=claim_id,
                category=ClaimCategory.OTHER,
                text=f"Web source consulted during daily search: {url[:300]}",
                source_url=url,
                source_tier=source_tier_for_url(url),
                player_ids=list(player_ids),
                retrieved_at=now,
                confidence=0.35 if source_tier_for_url(url) == "community" else 0.55,
                expires_at=now + timedelta(hours=12),
            )
        )
    return claims


def build_squad_search_request(
    *,
    player_ids: list[int],
    club_ids: list[int],
    player_names: list[str],
    budget: int,
) -> SearchRequest:
    assumptions = [
        f"injury OR availability OR suspension OR press conference: {name}"
        for name in player_names[:12]
    ]
    return SearchRequest(
        request_id=stable_json_hash({"players": player_ids, "clubs": club_ids})[:16],
        player_ids=player_ids,
        club_ids=club_ids,
        assumptions=assumptions,
        budget=budget,
    )
