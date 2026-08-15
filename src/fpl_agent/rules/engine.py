"""Pure deterministic FPL rule functions for 2026/27."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from fpl_agent.domain.models import ChipHalf, ChipKind, Position
from fpl_agent.rules.season import SeasonRules


class ValidationStatus(StrEnum):
    OK = "ok"
    INVALID = "invalid"


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == ValidationStatus.OK


@dataclass(frozen=True)
class SquadMember:
    player_id: int
    position: Position
    club_id: int


@dataclass(frozen=True)
class LineupPick:
    player_id: int
    position: Position
    is_starter: bool
    bench_order: int | None  # 0 = GK sub, 1..3 outfield order for bench
    is_captain: bool = False
    is_vice: bool = False


def validate_squad(members: list[SquadMember], rules: SeasonRules) -> ValidationResult:
    errors: list[str] = []
    if len(members) != rules.squad_size:
        errors.append(f"squad size {len(members)} != {rules.squad_size}")
    ids = [m.player_id for m in members]
    if len(ids) != len(set(ids)):
        errors.append("duplicate player ids")
    by_pos = Counter(m.position for m in members)
    for pos, quota in rules.position_quotas.items():
        if by_pos.get(pos, 0) != quota.squad_count:
            errors.append(f"{pos} count {by_pos.get(pos, 0)} != {quota.squad_count}")
    by_club = Counter(m.club_id for m in members)
    for club_id, n in by_club.items():
        if n > rules.club_limit:
            errors.append(f"club {club_id} has {n} > limit {rules.club_limit}")
    return ValidationResult(
        ValidationStatus.OK if not errors else ValidationStatus.INVALID,
        tuple(errors),
    )


def validate_lineup(picks: list[LineupPick], rules: SeasonRules) -> ValidationResult:
    errors: list[str] = []
    if len(picks) != rules.squad_size:
        errors.append(f"lineup size {len(picks)} != {rules.squad_size}")
    starters = [p for p in picks if p.is_starter]
    bench = [p for p in picks if not p.is_starter]
    if len(starters) != rules.starters:
        errors.append(f"starters {len(starters)} != {rules.starters}")
    if len(bench) != rules.squad_size - rules.starters:
        errors.append(f"bench size {len(bench)} invalid")
    by_pos = Counter(p.position for p in starters)
    for pos, quota in rules.position_quotas.items():
        n = by_pos.get(pos, 0)
        if n < quota.min_starters or n > quota.max_starters:
            errors.append(f"illegal formation for {pos}: {n}")
    captains = [p for p in picks if p.is_captain]
    vices = [p for p in picks if p.is_vice]
    if len(captains) != 1:
        errors.append("exactly one captain required")
    if len(vices) != 1:
        errors.append("exactly one vice-captain required")
    if captains and vices and captains[0].player_id == vices[0].player_id:
        errors.append("captain and vice must differ")
    gk_bench = [p for p in bench if p.position == Position.GKP]
    outfield_bench = [p for p in bench if p.position != Position.GKP]
    if len(gk_bench) != 1:
        errors.append("exactly one goalkeeper on bench required")
    if len(outfield_bench) != 3:
        errors.append("exactly three outfield bench players required")
    orders = sorted(p.bench_order for p in outfield_bench if p.bench_order is not None)
    if orders != [1, 2, 3]:
        errors.append("outfield bench_order must be 1,2,3")
    if gk_bench and gk_bench[0].bench_order not in (0, None):
        # allow 0 for GK sub identity
        pass
    return ValidationResult(
        ValidationStatus.OK if not errors else ValidationStatus.INVALID,
        tuple(errors),
    )


def selling_price_tenths(purchase_tenths: int, current_tenths: int, rules: SeasonRules) -> int:
    """Retain floor(rise * sell_on_fee) of rises; falls pass through fully.

    With sell_on_fee 0.5: +1 -> +0, +2 -> +1, +3 -> +1, +4 -> +2 (in tenths).
    """
    if current_tenths <= purchase_tenths:
        return current_tenths
    rise = current_tenths - purchase_tenths
    retained = int(rise * rules.sell_on_fee_fraction)
    return purchase_tenths + retained


def budget_after_transfers(
    *,
    bank_tenths: int,
    sells: list[tuple[int, int]],  # (purchase, current) for each sold
    buys_current_tenths: list[int],
    rules: SeasonRules,
) -> int:
    proceeds = sum(selling_price_tenths(p, c, rules) for p, c in sells)
    cost = sum(buys_current_tenths)
    return bank_tenths + proceeds - cost


def free_transfer_rollover(
    *,
    previous_ft: int,
    transfers_made: int,
    rules: SeasonRules,
    wildcard_or_free_hit: bool = False,
) -> tuple[int, int]:
    """Return (next_ft, hit_points).

    Official 2026/27: FT preserved across Wildcard/Free Hit when rules say so;
    hits still apply when not on those chips.
    """
    if wildcard_or_free_hit and rules.preserve_ft_across_wildcard_and_free_hit:
        next_ft = min(rules.max_banked_free_transfers, previous_ft + rules.free_transfers_per_gw)
        # chip absorbs transfer cost; do not spend FT
        return next_ft, 0

    usable = previous_ft
    paid = max(0, transfers_made - usable)
    hit = paid * rules.hit_cost_points
    remaining_after = max(0, usable - transfers_made)
    next_ft = min(
        rules.max_banked_free_transfers,
        remaining_after + rules.free_transfers_per_gw,
    )
    # Special case: if you used none and were at max, stay at max after +1 capped
    return next_ft, hit


def chip_half_for_event(event: int) -> ChipHalf:
    return ChipHalf.FIRST if event <= 19 else ChipHalf.SECOND


def available_chip_instances(
    *,
    event: int,
    used: set[tuple[ChipKind, ChipHalf]],
    rules: SeasonRules,
    previous_event_chip: ChipKind | None = None,
) -> list[tuple[ChipKind, ChipHalf]]:
    half = chip_half_for_event(event)
    out: list[tuple[ChipKind, ChipHalf]] = []
    for inst in rules.chip_instances:
        if inst.half != half:
            continue
        if not (inst.start_event <= event <= inst.stop_event):
            continue
        key = (inst.kind, inst.half)
        if key in used:
            continue
        if inst.kind == ChipKind.FREE_HIT and event in rules.free_hit_forbidden_events:
            continue
        if (
            inst.kind == ChipKind.FREE_HIT
            and rules.no_consecutive_free_hit_across_halves
            and previous_event_chip == ChipKind.FREE_HIT
            and event == 20
            and previous_event_chip is not None
        ):
            # GW19 FH blocks GW20 FH
            continue
        out.append(key)
    # explicit consecutive FH check when previous was FH in GW19 and event is 20
    if previous_event_chip == ChipKind.FREE_HIT and event == 20:
        out = [(k, h) for (k, h) in out if k != ChipKind.FREE_HIT]
    return out


def captain_multiplier(
    *,
    player_id: int,
    captain_id: int | None,
    vice_id: int | None,
    played_ids: set[int],
    triple_captain: bool,
    rules: SeasonRules,
) -> int:
    active_captain = None
    if captain_id is not None and captain_id in played_ids:
        active_captain = captain_id
    elif rules.vice_captain_fallback and vice_id is not None and vice_id in played_ids:
        active_captain = vice_id
    if active_captain is None or player_id != active_captain:
        return 1
    return rules.triple_captain_multiplier if triple_captain else rules.captain_multiplier


@dataclass(frozen=True)
class AutosubResult:
    final_starters: tuple[int, ...]
    final_bench: tuple[int, ...]
    substitutions: tuple[tuple[int, int], ...]  # (out_id, in_id)


def resolve_autosubs(
    picks: list[LineupPick],
    *,
    minutes: dict[int, int],
    rules: SeasonRules,
) -> AutosubResult:
    """Ordered autosubs preserving legal formation; one playing GK rule."""
    starters = [p for p in picks if p.is_starter]
    gk_bench = next(p for p in picks if not p.is_starter and p.position == Position.GKP)
    outfield_bench = sorted(
        [p for p in picks if not p.is_starter and p.position != Position.GKP],
        key=lambda p: p.bench_order or 99,
    )

    current = list(starters)
    bench_remaining = list(outfield_bench)
    subs: list[tuple[int, int]] = []

    # GK autosub first if starting GK played 0
    start_gk = next(p for p in current if p.position == Position.GKP)
    if minutes.get(start_gk.player_id, 0) == 0 and minutes.get(gk_bench.player_id, 0) > 0:
        current = [gk_bench if p.player_id == start_gk.player_id else p for p in current]
        subs.append((start_gk.player_id, gk_bench.player_id))

    def formation_ok(team: list[LineupPick]) -> bool:
        by_pos = Counter(p.position for p in team)
        for pos, quota in rules.position_quotas.items():
            n = by_pos.get(pos, 0)
            if n < quota.min_starters or n > quota.max_starters:
                return False
        return True

    # Outfield: for each non-playing starter, try bench in order
    changed = True
    while changed:
        changed = False
        for idx, starter in enumerate(list(current)):
            if starter.position == Position.GKP:
                continue
            if minutes.get(starter.player_id, 0) > 0:
                continue
            # already subbed out effectively if not in "did not play" — still 0 minutes
            for b_idx, cand in enumerate(list(bench_remaining)):
                trial = list(current)
                trial[idx] = cand
                if formation_ok(trial) and minutes.get(cand.player_id, 0) > 0:
                    subs.append((starter.player_id, cand.player_id))
                    current = trial
                    bench_remaining.pop(b_idx)
                    changed = True
                    break
            if changed:
                break

    final_starter_ids = tuple(p.player_id for p in current)
    all_ids = {p.player_id for p in picks}
    bench_final = tuple(i for i in all_ids if i not in final_starter_ids)
    return AutosubResult(final_starter_ids, bench_final, tuple(subs))


def manager_gameweek_total(
    *,
    player_points: dict[int, int],
    picks: list[LineupPick],
    minutes: dict[int, int],
    hit_cost: int,
    bench_boost: bool,
    triple_captain: bool,
    rules: SeasonRules,
) -> int:
    autosub = resolve_autosubs(picks, minutes=minutes, rules=rules)
    scoring_ids = set(autosub.final_starters)
    if bench_boost:
        scoring_ids |= set(autosub.final_bench)

    captain = next((p.player_id for p in picks if p.is_captain), None)
    vice = next((p.player_id for p in picks if p.is_vice), None)
    played = {pid for pid, m in minutes.items() if m > 0}

    total = 0
    for pid in scoring_ids:
        base = player_points.get(pid, 0)
        mult = captain_multiplier(
            player_id=pid,
            captain_id=captain,
            vice_id=vice,
            played_ids=played,
            triple_captain=triple_captain,
            rules=rules,
        )
        total += base * mult
    return total - hit_cost
