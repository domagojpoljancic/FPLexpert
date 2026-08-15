"""Resolve current team state with explicit per-field provenance."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fpl_agent.config import Settings
from fpl_agent.domain.models import (
    POSITION_FROM_ELEMENT_TYPE,
    ChipHalf,
    ChipInstanceState,
    ChipKind,
    Executability,
    FieldSourceType,
    Provenanced,
    ResolvedTeamState,
    SeasonId,
    SquadPlayer,
)
from fpl_agent.domain.provenance import is_fresh
from fpl_agent.team_state.private import PrivateTeamState


def _prov(value: Any, source: FieldSourceType, observed: datetime | None, *, fresh: bool, conf: float) -> Provenanced[Any]:
    return Provenanced(
        value=value,
        source_type=source,
        observed_at=observed,
        confidence=conf,
        fresh=fresh,
        warnings=[],
    )


def resolve_team_state(
    *,
    settings: Settings,
    season: SeasonId,
    gameweek: int,
    now: datetime | None = None,
    private: PrivateTeamState | None = None,
    public_picks: dict[str, Any] | None = None,
    public_entry: dict[str, Any] | None = None,
    catalog: dict[int, dict[str, Any]] | None = None,
    local_snapshot: ResolvedTeamState | None = None,
) -> ResolvedTeamState:
    """Field-level resolver with precedence: private > public post-deadline > local > unknown."""
    now = now or datetime.now(UTC)
    warnings: list[str] = []
    catalog = catalog or {}

    squad_val: list[SquadPlayer] | None = None
    squad_src = FieldSourceType.UNKNOWN
    squad_obs: datetime | None = None
    squad_conf = 0.0

    bank_val: int | None = None
    bank_src = FieldSourceType.UNKNOWN
    bank_obs: datetime | None = None
    bank_conf = 0.0

    ft_val: int | None = None
    ft_src = FieldSourceType.UNKNOWN
    ft_obs: datetime | None = None
    ft_conf = 0.0

    chips_val: list[ChipInstanceState] | None = None
    chips_src = FieldSourceType.UNKNOWN
    chips_obs: datetime | None = None
    chips_conf = 0.0

    cap_val: int | None = None
    vice_val: int | None = None
    cap_src = FieldSourceType.UNKNOWN
    vice_src = FieldSourceType.UNKNOWN

    if private is not None:
        if private.season != season:
            warnings.append("private state season mismatch")
        elif private.applies_before_gameweek != gameweek:
            warnings.append("private state gameweek mismatch")
        else:
            fresh_squad = is_fresh(
                private.as_of,
                now=now,
                max_age=timedelta(hours=settings.freshness.private_squad_max_age_hours),
            )
            fresh_fin = is_fresh(
                private.as_of,
                now=now,
                max_age=timedelta(hours=settings.freshness.financial_state_max_age_hours),
            )
            players: list[SquadPlayer] = []
            for pid in private.player_ids:
                meta = catalog.get(pid, {})
                et = int(meta.get("element_type", 0) or 0)
                pos = POSITION_FROM_ELEMENT_TYPE.get(et)
                if pos is None:
                    warnings.append(f"unknown position for player {pid}; defaulting DEF")
                    from fpl_agent.domain.models import Position

                    pos = Position.DEF
                purchase = private.purchase_prices_tenths[str(pid)]
                current = int(meta.get("now_cost", purchase))
                players.append(
                    SquadPlayer(
                        player_id=pid,
                        position=pos,
                        club_id=int(meta.get("team", 0) or 0),
                        purchase_price_tenths=purchase,
                        current_price_tenths=current,
                        selling_price_tenths=None,
                    )
                )
            squad_val, squad_src, squad_obs, squad_conf = players, FieldSourceType.PRIVATE_SYNC, private.as_of, 0.95
            if not fresh_squad:
                squad_conf = 0.4
                warnings.append("private squad stale")
            bank_val, bank_src, bank_obs, bank_conf = private.bank_tenths, FieldSourceType.PRIVATE_SYNC, private.as_of, 0.95 if fresh_fin else 0.4
            ft_val, ft_src, ft_obs, ft_conf = private.free_transfers, FieldSourceType.PRIVATE_SYNC, private.as_of, 0.95 if fresh_fin else 0.4
            chips_val = [
                ChipInstanceState(
                    kind=c.kind,
                    half=c.half,
                    available=c.available,
                    used_in_gameweek=c.used_in_gameweek,
                )
                for c in private.chip_instances
            ] or _default_chips()
            chips_src, chips_obs, chips_conf = FieldSourceType.PRIVATE_SYNC, private.as_of, 0.95 if fresh_fin else 0.4
            cap_val, cap_src = private.captain_id, FieldSourceType.PRIVATE_SYNC
            vice_val, vice_src = private.vice_id, FieldSourceType.PRIVATE_SYNC

    # Public picks only prove post-deadline / historical identity — never unsubmitted pre-deadline.
    if squad_val is None and public_picks and public_picks.get("post_deadline_confirmed"):
        picks = public_picks.get("picks") or []
        players = []
        for p in picks:
            pid = int(p["element"])
            meta = catalog.get(pid, {})
            et = int(meta.get("element_type", p.get("position", 1)))
            from fpl_agent.domain.models import Position

            pos = POSITION_FROM_ELEMENT_TYPE.get(et, Position.MID)
            players.append(
                SquadPlayer(
                    player_id=pid,
                    position=pos,
                    club_id=int(meta.get("team", 0) or 0),
                    purchase_price_tenths=None,
                    current_price_tenths=int(meta.get("now_cost", 0) or 0),
                )
            )
        if len(players) == 15:
            squad_val = players
            squad_src = FieldSourceType.PUBLIC_POST_DEADLINE
            squad_obs = now
            squad_conf = 0.7
            warnings.append("squad from public post-deadline picks only")

    if bank_val is None and public_entry and public_entry.get("post_deadline_confirmed"):
        # last_deadline_bank is not always present; only use when explicitly provided
        if "bank_tenths" in public_entry:
            bank_val = int(public_entry["bank_tenths"])
            bank_src = FieldSourceType.PUBLIC_POST_DEADLINE
            bank_obs = now
            bank_conf = 0.6

    if squad_val is None and local_snapshot is not None and local_snapshot.squad.value:
        ttl = timedelta(hours=settings.freshness.private_squad_max_age_hours)
        if is_fresh(local_snapshot.as_of, now=now, max_age=ttl):
            squad_val = local_snapshot.squad.value
            squad_src = FieldSourceType.LOCAL_SNAPSHOT
            squad_obs = local_snapshot.as_of
            squad_conf = 0.5
            warnings.append("squad from local snapshot TTL")

    squad_fresh = is_fresh(
        squad_obs,
        now=now,
        max_age=timedelta(hours=settings.freshness.private_squad_max_age_hours),
    ) if squad_obs else False
    fin_fresh = is_fresh(
        bank_obs,
        now=now,
        max_age=timedelta(hours=settings.freshness.financial_state_max_age_hours),
    ) if bank_obs else False

    selling_known = bool(
        squad_val
        and all(p.purchase_price_tenths is not None or p.selling_price_tenths is not None for p in squad_val)
    )

    if squad_val is None or not squad_fresh:
        executability = Executability.INSUFFICIENT
    elif bank_val is None or ft_val is None or chips_val is None or not fin_fresh or not selling_known:
        executability = Executability.CONDITIONAL_ONLY
    else:
        executability = Executability.EXECUTABLE

    return ResolvedTeamState(
        season=season,
        applies_to_gameweek=gameweek,
        as_of=now,
        squad=_prov(squad_val or [], squad_src, squad_obs, fresh=squad_fresh, conf=squad_conf),
        bank_tenths=_prov(bank_val, bank_src, bank_obs, fresh=fin_fresh and bank_val is not None, conf=bank_conf),
        free_transfers=_prov(ft_val, ft_src, ft_obs, fresh=fin_fresh and ft_val is not None, conf=ft_conf),
        chip_instances=_prov(chips_val, chips_src, chips_obs, fresh=fin_fresh and chips_val is not None, conf=chips_conf),
        captain_id=_prov(cap_val, cap_src, squad_obs, fresh=squad_fresh, conf=squad_conf),
        vice_id=_prov(vice_val, vice_src, squad_obs, fresh=squad_fresh, conf=squad_conf),
        executability=executability,
        executable_advice_allowed=executability == Executability.EXECUTABLE,
        warnings=warnings,
    )


def _default_chips() -> list[ChipInstanceState]:
    out: list[ChipInstanceState] = []
    for kind in ChipKind:
        for half in ChipHalf:
            out.append(ChipInstanceState(kind=kind, half=half, available=True))
    return out
