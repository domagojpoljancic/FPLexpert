"""Map FPL app card names to official element ids (no guessing).

Screenshot cards are matched by printed name, then checked against the next
fixture printed under the name (opponent + H/A). Kits and last-season clubs
are ignored. Unreadable names may be filled only from the saved squad when
that remaining player's fixture and price uniquely match the card.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

POSITION_LABELS = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

MatchStatus = Literal["OK", "AMBIGUOUS", "NONE"]


def normalize_name(value: str) -> str:
    """Fold accents and strip punctuation so 'B. Fernandes' == 'B.Fernandes' == 'Guéhi'/'Guehi'."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in stripped.lower() if ch.isalnum())


def normalize_team(value: str) -> str:
    return normalize_name(value).upper()


@dataclass(frozen=True)
class CatalogPlayer:
    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_id: int
    team_short: str
    position: str
    now_cost_tenths: int

    @property
    def cost_label(self) -> str:
        return f"£{self.now_cost_tenths / 10:.1f}m"


@dataclass(frozen=True)
class NextFixture:
    opponent: str
    ha: Literal["H", "A"]

    @property
    def label(self) -> str:
        return f"{self.opponent} ({self.ha})"


@dataclass(frozen=True)
class CardQuery:
    name: str
    opponent: str | None = None
    ha: Literal["H", "A"] | None = None
    cost_tenths: int | None = None
    position: str | None = None
    raw: str = ""

    @property
    def display(self) -> str:
        return self.raw or self.name or "?"


@dataclass(frozen=True)
class NameMatch:
    query: str
    status: MatchStatus
    player: CatalogPlayer | None
    candidates: tuple[CatalogPlayer, ...]
    note: str = ""


def players_from_bootstrap(bootstrap: dict[str, Any]) -> list[CatalogPlayer]:
    teams = {
        int(t["id"]): str(t.get("short_name") or t.get("name") or t["id"])
        for t in bootstrap.get("teams") or []
        if "id" in t
    }
    out: list[CatalogPlayer] = []
    for el in bootstrap.get("elements") or []:
        if "id" not in el:
            continue
        element_type = int(el.get("element_type") or 0)
        team_id = int(el.get("team") or 0)
        out.append(
            CatalogPlayer(
                player_id=int(el["id"]),
                web_name=str(el.get("web_name") or ""),
                first_name=str(el.get("first_name") or ""),
                second_name=str(el.get("second_name") or ""),
                team_id=team_id,
                team_short=teams.get(team_id, "?"),
                position=POSITION_LABELS.get(element_type, f"?{element_type}"),
                now_cost_tenths=int(el.get("now_cost") or 0),
            )
        )
    return out


def next_fixtures_by_team(
    *,
    bootstrap: dict[str, Any],
    fixtures: list[dict[str, Any]],
    event_id: int,
) -> dict[int, NextFixture]:
    teams = {
        int(t["id"]): str(t.get("short_name") or t.get("name") or t["id"])
        for t in bootstrap.get("teams") or []
        if "id" in t
    }
    out: dict[int, NextFixture] = {}
    for row in fixtures:
        if int(row.get("event") or 0) != event_id:
            continue
        home = int(row.get("team_h") or 0)
        away = int(row.get("team_a") or 0)
        if home and away:
            out[home] = NextFixture(opponent=teams.get(away, "?"), ha="H")
            out[away] = NextFixture(opponent=teams.get(home, "?"), ha="A")
    return out


def parse_card_token(token: str) -> CardQuery:
    """Parse 'Name' or 'Name|OPP|H|6.0|DEF'. Use ? when the printed name is unreadable."""
    parts = [part.strip() for part in token.split("|")]
    raw_name = parts[0] if parts else ""
    name = "" if raw_name in {"", "?", "-", "???"} else raw_name
    opponent = parts[1].upper() if len(parts) > 1 and parts[1] else None
    ha_raw = parts[2].upper()[:1] if len(parts) > 2 and parts[2] else None
    ha: Literal["H", "A"] | None = ha_raw if ha_raw in {"H", "A"} else None
    cost_tenths = _parse_cost(parts[3]) if len(parts) > 3 and parts[3] else None
    position = parts[4].upper() if len(parts) > 4 and parts[4] else None
    if position and position not in POSITION_LABELS.values():
        position = None
    return CardQuery(
        name=name,
        opponent=opponent,
        ha=ha,
        cost_tenths=cost_tenths,
        position=position,
        raw=token,
    )


def _parse_cost(raw: str) -> int | None:
    cleaned = raw.lower().replace("£", "").replace("m", "").strip()
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        digits = re.sub(r"[^0-9.]", "", cleaned)
        if not digits:
            return None
        value = float(digits)
    if value >= 20:
        return int(round(value))
    return int(round(value * 10))


def _score(query_norm: str, player: CatalogPlayer) -> int:
    if not query_norm:
        return 0
    web = normalize_name(player.web_name)
    first = normalize_name(player.first_name)
    second = normalize_name(player.second_name)
    full = f"{first}{second}"
    if web == query_norm:
        return 100
    if full == query_norm:
        return 90
    if second == query_norm:
        return 80
    if first == query_norm:
        return 70
    return 0


def match_name(query: str, catalog: list[CatalogPlayer]) -> NameMatch:
    query_norm = normalize_name(query)
    scored = [(player, _score(query_norm, player)) for player in catalog]
    scored = [(player, score) for player, score in scored if score > 0]
    if not scored:
        return NameMatch(query=query, status="NONE", player=None, candidates=())
    exact = [(player, score) for player, score in scored if score == 100]
    pool = exact if exact else scored
    best = max(score for _, score in pool)
    top = tuple(player for player, score in pool if score == best)
    if len(top) == 1:
        return NameMatch(query=query, status="OK", player=top[0], candidates=top)
    return NameMatch(query=query, status="AMBIGUOUS", player=None, candidates=top)


def match_names(queries: list[str], catalog: list[CatalogPlayer]) -> list[NameMatch]:
    return [match_name(query, catalog) for query in queries]


def _club_pool(
    catalog: list[CatalogPlayer],
    fixtures_by_team: dict[int, NextFixture],
    opponent: str | None,
    ha: Literal["H", "A"] | None,
) -> list[CatalogPlayer] | None:
    if not opponent or not ha:
        return None
    want = normalize_team(opponent)
    allowed = {
        team_id
        for team_id, fixture in fixtures_by_team.items()
        if normalize_team(fixture.opponent) == want and fixture.ha == ha
    }
    return [player for player in catalog if player.team_id in allowed]


def _narrow(players: tuple[CatalogPlayer, ...] | list[CatalogPlayer], query: CardQuery) -> list[CatalogPlayer]:
    narrowed = list(players)
    if query.cost_tenths is not None:
        priced = [player for player in narrowed if player.now_cost_tenths == query.cost_tenths]
        if priced:
            narrowed = priced
    if query.position:
        positioned = [player for player in narrowed if player.position == query.position]
        if positioned:
            narrowed = positioned
    return narrowed


def _name_in_pool(query: CardQuery, pool: list[CatalogPlayer]) -> NameMatch:
    if not query.name:
        return NameMatch(query=query.display, status="NONE", player=None, candidates=())
    hit = match_name(query.name, pool)
    if hit.status == "OK" and hit.player is not None:
        return NameMatch(
            query=query.display,
            status="OK",
            player=hit.player,
            candidates=hit.candidates,
            note="name",
        )
    if hit.status == "AMBIGUOUS":
        narrowed = _narrow(hit.candidates, query)
        if len(narrowed) == 1:
            return NameMatch(
                query=query.display,
                status="OK",
                player=narrowed[0],
                candidates=tuple(narrowed),
                note="name+fixture",
            )
        return NameMatch(
            query=query.display,
            status="AMBIGUOUS",
            player=None,
            candidates=tuple(narrowed or hit.candidates),
            note="name+fixture",
        )
    return NameMatch(query=query.display, status="NONE", player=None, candidates=())


def match_cards(
    queries: list[CardQuery],
    catalog: list[CatalogPlayer],
    *,
    fixtures_by_team: dict[int, NextFixture] | None = None,
    saved_ids: list[int] | None = None,
) -> list[NameMatch]:
    fixtures_by_team = fixtures_by_team or {}
    by_id = catalog_by_id(catalog)
    results: list[NameMatch | None] = [None] * len(queries)
    claimed: set[int] = set()

    for index, query in enumerate(queries):
        pool = _club_pool(catalog, fixtures_by_team, query.opponent, query.ha)
        search = pool if pool is not None else catalog
        if pool is not None and not pool:
            results[index] = NameMatch(
                query=query.display,
                status="NONE",
                player=None,
                candidates=(),
                note="unknown fixture",
            )
            continue
        hit = _name_in_pool(query, search)
        if hit.status == "OK" and hit.player is not None:
            results[index] = hit
            claimed.add(hit.player.player_id)
        elif hit.status == "AMBIGUOUS":
            results[index] = hit

    saved_left = [by_id[pid] for pid in saved_ids or [] if pid in by_id and pid not in claimed]
    for index, query in enumerate(queries):
        if results[index] is not None and results[index].status == "OK":
            continue
        pool = _club_pool(catalog, fixtures_by_team, query.opponent, query.ha)
        if pool is None:
            if results[index] is None:
                results[index] = _name_in_pool(query, catalog)
            continue
        remaining = [player for player in saved_left if player.player_id in {p.player_id for p in pool}]
        remaining = _narrow(remaining, query)
        if len(remaining) == 1:
            player = remaining[0]
            results[index] = NameMatch(
                query=query.display,
                status="OK",
                player=player,
                candidates=(player,),
                note="saved+fixture",
            )
            saved_left = [item for item in saved_left if item.player_id != player.player_id]
        elif remaining:
            results[index] = NameMatch(
                query=query.display,
                status="AMBIGUOUS",
                player=None,
                candidates=tuple(remaining),
                note="saved+fixture",
            )
        elif results[index] is None:
            results[index] = NameMatch(
                query=query.display,
                status="NONE",
                player=None,
                candidates=(),
                note="printed name not in that fixture club",
            )
    return [item if item is not None else NameMatch(query="?", status="NONE", player=None, candidates=()) for item in results]


def format_player(player: CatalogPlayer, fixture: NextFixture | None = None) -> str:
    extra = f" {fixture.label}" if fixture is not None else ""
    return (
        f"id={player.player_id} {player.position} {player.team_short} "
        f"{player.web_name} {player.cost_label}{extra}"
    )


def format_matches(
    matches: list[NameMatch],
    *,
    fixtures_by_team: dict[int, NextFixture] | None = None,
) -> str:
    lines: list[str] = []
    for item in matches:
        fixture = None
        if item.player is not None and fixtures_by_team:
            fixture = fixtures_by_team.get(item.player.team_id)
        if item.status == "OK" and item.player is not None:
            note = f"  ({item.note})" if item.note else ""
            lines.append(f"OK         {item.query:<22} {format_player(item.player, fixture)}{note}")
        elif item.status == "NONE":
            extra = f" {item.note}" if item.note else "no catalog match"
            lines.append(f"NONE       {item.query:<22} {extra}")
        else:
            lines.append(f"AMBIGUOUS  {item.query}")
            for candidate in item.candidates:
                cand_fx = fixtures_by_team.get(candidate.team_id) if fixtures_by_team else None
                lines.append(f"           {format_player(candidate, cand_fx)}")
    return "\n".join(lines)


def catalog_by_id(catalog: list[CatalogPlayer]) -> dict[int, CatalogPlayer]:
    return {player.player_id: player for player in catalog}


def format_saved_squad(
    *,
    player_ids: list[int],
    catalog: dict[int, CatalogPlayer],
    bank_tenths: int,
    free_transfers: int,
    captain_id: int | None,
    vice_id: int | None,
    starters: list[int] | None,
    bench_order: list[int] | None,
    as_of_label: str,
    gameweek: int,
    fixtures_by_team: dict[int, NextFixture] | None = None,
) -> str:
    def label(pid: int) -> str:
        player = catalog.get(pid)
        if player is None:
            return f"id={pid}"
        fixture = fixtures_by_team.get(player.team_id) if fixtures_by_team else None
        extra = f" {fixture.label}" if fixture is not None else ""
        return f"{player.web_name}{extra}"

    lines = [
        f"Saved squad  GW{gameweek}  last saved {as_of_label}",
        f"Bank £{bank_tenths / 10:.1f}m   Free transfers: {free_transfers}",
        f"Captain: {label(captain_id) if captain_id else 'unset'}   "
        f"Vice: {label(vice_id) if vice_id else 'unset'}",
        "",
    ]
    order = starters or player_ids
    extra_ids = [pid for pid in player_ids if pid not in order]
    shown = [*order, *extra_ids]
    if starters:
        lines.append("XI: " + ", ".join(label(pid) for pid in starters))
        bench = bench_order or extra_ids
        if bench:
            lines.append("Bench: " + ", ".join(label(pid) for pid in bench))
    else:
        lines.append("Players: " + ", ".join(label(pid) for pid in shown))
    unknown = [pid for pid in player_ids if pid not in catalog]
    if unknown:
        lines.append(f"Unmapped ids: {unknown}")
    return "\n".join(lines)
