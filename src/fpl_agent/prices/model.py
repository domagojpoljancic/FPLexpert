"""Uncalibrated price-change scoring. LLM must not call this."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fpl_agent.config import PricesSettings
from fpl_agent.prices.types import (
    LikelihoodBand,
    PlayerPriceRow,
    PriceDirection,
    PricePrediction,
    PriceSnapshot,
)

UNAVAILABLE_STATUSES_FOR_BUY = frozenset({"i", "s", "u", "n"})
REVERSE_FRACTION = 0.20
EVENT_EARLY_HOURS = 24.0
OVERWHELMING_PROGRESS = 0.95


def net_transfers(row: PlayerPriceRow) -> int | None:
    if row.transfers_in_event is None or row.transfers_out_event is None:
        return None
    return row.transfers_in_event - row.transfers_out_event


def ownership_threshold(ownership_pct: float, direction: PriceDirection, settings: PricesSettings) -> float:
    base = settings.rise_base_net if direction == PriceDirection.RISE else settings.fall_base_net
    return float(base) * (1.0 + settings.ownership_scale_k * (ownership_pct / 100.0))


def _band_from_progress(
    progress: float,
    *,
    settings: PricesSettings,
    previous: LikelihoodBand | None,
    reversing: bool,
) -> LikelihoodBand:
    watch_t = settings.watch_progress
    likely_t = settings.likely_progress
    if previous == LikelihoodBand.LIKELY_NEXT_WINDOW:
        likely_t = settings.likely_progress - settings.hysteresis
    if progress < watch_t:
        band = LikelihoodBand.UNLIKELY
    elif progress < likely_t:
        band = LikelihoodBand.WATCH
    else:
        band = LikelihoodBand.LIKELY_NEXT_WINDOW
    if reversing and band == LikelihoodBand.LIKELY_NEXT_WINDOW:
        band = LikelihoodBand.WATCH
    elif reversing and band == LikelihoodBand.WATCH:
        band = LikelihoodBand.UNLIKELY
    return band


def score_player(
    *,
    snapshots: list[PriceSnapshot],
    player_id: int,
    web_name: str,
    settings: PricesSettings,
    now: datetime | None = None,
    public_max_age: timedelta,
    previous_likelihood: LikelihoodBand | None = None,
    event_started_at: datetime | None = None,
    catalog_status: str | None = None,
    catalog_chance: float | None = None,
) -> PricePrediction:
    now = now or datetime.now(UTC)
    warnings: list[str] = []
    used = [s for s in snapshots if any(p.player_id == player_id for p in s.players)]
    used.sort(key=lambda s: s.retrieved_at)
    if not used:
        return PricePrediction(
            player_id=player_id,
            web_name=web_name,
            now_cost_tenths=0,
            direction=PriceDirection.NONE,
            likelihood=LikelihoodBand.UNAVAILABLE,
            snapshot_count_used=0,
            model_version=settings.model_version,
            as_of=now,
            warnings=["no_snapshots"],
        )

    latest = used[-1]
    latest_row = next(p for p in latest.players if p.player_id == player_id)
    prev_row: PlayerPriceRow | None = None
    if len(used) >= 2:
        prev_row = next(p for p in used[-2].players if p.player_id == player_id)

    age = now - latest.retrieved_at
    stale = age > public_max_age
    if stale:
        warnings.append("stale_public_data")

    already_tenths = 0
    if prev_row is not None and latest_row.now_cost != prev_row.now_cost:
        already_tenths = latest_row.now_cost - prev_row.now_cost
    elif (
        prev_row is not None
        and latest_row.cost_change_event is not None
        and prev_row.cost_change_event is not None
        and latest_row.cost_change_event > prev_row.cost_change_event
    ):
        already_tenths = latest_row.cost_change_event - prev_row.cost_change_event

    net = net_transfers(latest_row)
    prev_net = net_transfers(prev_row) if prev_row is not None else None
    delta_net = None if net is None or prev_net is None else net - prev_net

    if net is None:
        warnings.append("transfers_event_missing")
        return PricePrediction(
            player_id=player_id,
            web_name=web_name,
            now_cost_tenths=latest_row.now_cost,
            direction=PriceDirection.NONE,
            likelihood=LikelihoodBand.UNAVAILABLE,
            net_transfers_event=None,
            net_transfers_since_prev_snapshot=delta_net,
            snapshot_count_used=len(used),
            model_version=settings.model_version,
            as_of=now,
            warnings=warnings,
            already_moved_tenths=already_tenths,
        )

    if already_tenths > 0:
        direction = PriceDirection.RISE
    elif already_tenths < 0:
        direction = PriceDirection.FALL
    elif net > 0:
        direction = PriceDirection.RISE
    elif net < 0:
        direction = PriceDirection.FALL
    else:
        direction = PriceDirection.NONE

    ownership = latest_row.selected_by_percent
    if ownership is None:
        warnings.append("ownership_missing")

    progress: float | None = None
    reversing = False
    if direction != PriceDirection.NONE and ownership is not None:
        threshold = ownership_threshold(ownership, direction, settings)
        if threshold > 0:
            progress = min(1.0, abs(net) / threshold)
        if prev_row is not None and delta_net is not None and net != 0:
            hours = (latest.retrieved_at - used[-2].retrieved_at).total_seconds() / 3600.0
            if hours > 0 and (delta_net * net) < 0 and abs(delta_net) > REVERSE_FRACTION * abs(net):
                reversing = True
                warnings.append("velocity_reversed")

    if already_tenths != 0:
        likelihood = LikelihoodBand.ALREADY_MOVED
        # second tick only if new velocity independently supports likely
        if (
            progress is not None
            and progress >= settings.likely_progress
            and not reversing
            and not stale
            and len(used) >= settings.min_snapshots_for_likely
            and ownership is not None
        ):
            warnings.append("already_moved_second_tick_unsupported")
        return PricePrediction(
            player_id=player_id,
            web_name=web_name,
            now_cost_tenths=latest_row.now_cost,
            direction=direction,
            likelihood=likelihood,
            progress_uncalibrated=progress,
            net_transfers_event=net,
            net_transfers_since_prev_snapshot=delta_net,
            snapshot_count_used=len(used),
            model_version=settings.model_version,
            as_of=now,
            warnings=warnings,
            already_moved_tenths=already_tenths,
        )

    if len(used) < settings.min_snapshots_for_likely:
        warnings.append("single_snapshot_weak")

    event_early = False
    if event_started_at is not None and (now - event_started_at) < timedelta(hours=EVENT_EARLY_HOURS):
        event_early = True
        warnings.append("event_early")

    if progress is None:
        likelihood = LikelihoodBand.WATCH if net != 0 else LikelihoodBand.UNLIKELY
        if direction == PriceDirection.NONE:
            likelihood = LikelihoodBand.UNLIKELY
    else:
        likelihood = _band_from_progress(
            progress,
            settings=settings,
            previous=previous_likelihood,
            reversing=reversing,
        )

    if likelihood == LikelihoodBand.LIKELY_NEXT_WINDOW:
        if len(used) < settings.min_snapshots_for_likely:
            likelihood = LikelihoodBand.WATCH
        if stale:
            likelihood = LikelihoodBand.WATCH
        if ownership is None:
            likelihood = LikelihoodBand.WATCH
        if event_early and (progress or 0) < OVERWHELMING_PROGRESS:
            likelihood = LikelihoodBand.WATCH

    status = catalog_status if catalog_status is not None else latest_row.status
    chance = catalog_chance if catalog_chance is not None else latest_row.chance_of_playing_next_round
    if status in UNAVAILABLE_STATUSES_FOR_BUY or chance == 0:
        warnings.append("unavailable_status")

    return PricePrediction(
        player_id=player_id,
        web_name=web_name,
        now_cost_tenths=latest_row.now_cost,
        direction=direction,
        likelihood=likelihood,
        progress_uncalibrated=progress,
        net_transfers_event=net,
        net_transfers_since_prev_snapshot=delta_net,
        snapshot_count_used=len(used),
        model_version=settings.model_version,
        as_of=now,
        warnings=warnings,
        already_moved_tenths=already_tenths,
    )


def is_unavailable_for_buy(prediction: PricePrediction) -> bool:
    return "unavailable_status" in prediction.warnings
