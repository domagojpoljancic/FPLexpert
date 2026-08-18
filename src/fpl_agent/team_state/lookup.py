"""Map FPL app card names to official element ids (no guessing)."""

from __future__ import annotations

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


@dataclass(frozen=True)
class CatalogPlayer:
    player_id: int
    web_name: str
    first_name: str
    second_name: str
    team_short: str
    position: str
    now_cost_tenths: int

    @property
    def cost_label(self) -> str:
        return f"£{self.now_cost_tenths / 10:.1f}m"


@dataclass(frozen=True)
class NameMatch:
    query: str
    status: MatchStatus
    player: CatalogPlayer | None
    candidates: tuple[CatalogPlayer, ...]


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
                team_short=teams.get(team_id, "?"),
                position=POSITION_LABELS.get(element_type, f"?{element_type}"),
                now_cost_tenths=int(el.get("now_cost") or 0),
            )
        )
    return out


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


def format_player(player: CatalogPlayer) -> str:
    return (
        f"id={player.player_id} {player.position} {player.team_short} "
        f"{player.web_name} {player.cost_label}"
    )


def format_matches(matches: list[NameMatch]) -> str:
    lines: list[str] = []
    for item in matches:
        if item.status == "OK" and item.player is not None:
            lines.append(f"OK         {item.query:<16} {format_player(item.player)}")
        elif item.status == "NONE":
            lines.append(f"NONE       {item.query:<16} no catalog match")
        else:
            lines.append(f"AMBIGUOUS  {item.query}")
            for candidate in item.candidates:
                lines.append(f"           {format_player(candidate)}")
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
) -> str:
    def label(pid: int) -> str:
        player = catalog.get(pid)
        return player.web_name if player is not None else f"id={pid}"

    lines = [
        f"Saved squad  GW{gameweek}  last saved {as_of_label}",
        f"Bank £{bank_tenths / 10:.1f}m   Free transfers: {free_transfers}",
        f"Captain: {label(captain_id) if captain_id else 'unset'}   "
        f"Vice: {label(vice_id) if vice_id else 'unset'}",
        "",
    ]
    order = starters or player_ids
    extra = [pid for pid in player_ids if pid not in order]
    shown = [*order, *extra]
    if starters:
        lines.append("XI: " + ", ".join(label(pid) for pid in starters))
        bench = bench_order or extra
        if bench:
            lines.append("Bench: " + ", ".join(label(pid) for pid in bench))
    else:
        lines.append("Players: " + ", ".join(label(pid) for pid in shown))
    unknown = [pid for pid in player_ids if pid not in catalog]
    if unknown:
        lines.append(f"Unmapped ids: {unknown}")
    return "\n".join(lines)
