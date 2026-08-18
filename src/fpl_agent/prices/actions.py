"""Smart-to-act policy. Price movement is not itself a recommendation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fpl_agent.config import AlertsSettings, PricesSettings
from fpl_agent.domain.models import Executability, ResolvedTeamState, SquadPlayer
from fpl_agent.prices.model import is_unavailable_for_buy
from fpl_agent.prices.types import (
    ActionClass,
    LikelihoodBand,
    MoveType,
    PriceAction,
    PriceDirection,
    PricePrediction,
)
from fpl_agent.rules.engine import budget_after_transfers, selling_price_tenths
from fpl_agent.rules.season import SeasonRules
from fpl_agent.strategy.engine import TransferMove


@dataclass
class PlanView:
    transfers: list[TransferMove] = field(default_factory=list)
    scenario_id: str | None = None
    gain_vs_roll: float = 0.0
    hit_cost: int = 0
    legality_ok: bool = False
    football_beats_roll: bool = False

    @property
    def in_ids(self) -> set[int]:
        return {t.in_id for t in self.transfers if t.in_id}

    @property
    def out_ids(self) -> set[int]:
        return {t.out_id for t in self.transfers if t.out_id}


def _squad_by_id(team: ResolvedTeamState) -> dict[int, SquadPlayer]:
    return {p.player_id: p for p in (team.squad.value or [])}


def _hypothetical_sell(
    player: SquadPlayer,
    *,
    new_current: int,
    rules: SeasonRules,
) -> tuple[int, int]:
    purchase = player.purchase_price_tenths or player.current_price_tenths or 0
    current = player.current_price_tenths or purchase
    before = selling_price_tenths(purchase, current, rules)
    after = selling_price_tenths(purchase, new_current, rules)
    return before, after


def classify_action(
    *,
    prediction: PricePrediction,
    team: ResolvedTeamState,
    rules: SeasonRules,
    plan: PlanView,
    watchlist: set[int],
    settings: PricesSettings,
    alerts: AlertsSettings,
    hours_to_deadline: float | None,
    now: datetime | None = None,
) -> PriceAction:
    now = now or datetime.now(UTC)
    owned = _squad_by_id(team)
    pid = prediction.player_id
    is_owned = pid in owned
    in_plan_in = pid in plan.in_ids
    in_plan_out = pid in plan.out_ids
    in_watch = pid in watchlist
    codes: list[str] = []
    related = plan.scenario_id if (in_plan_in or in_plan_out) else None
    valid_until = now + timedelta(minutes=alerts.safety_floor_minutes)

    bank = team.bank_tenths.value
    ft = team.free_transfers.value
    executable = team.executability == Executability.EXECUTABLE
    last_ft = ft == 1
    needs_hit = ft is not None and ft < 1 and len(plan.transfers) >= 1

    affordability_risk = False
    sell_value_at_risk = False
    wait_sell_increases = False
    counterfactual = False

    player = owned.get(pid)
    if is_owned and player is not None and prediction.direction == PriceDirection.FALL:
        current = player.current_price_tenths or prediction.now_cost_tenths
        before, after_one = _hypothetical_sell(player, new_current=current - 1, rules=rules)
        _b2, after_two = _hypothetical_sell(player, new_current=current - 2, rules=rules)
        counterfactual = True
        if after_one < before or after_two < before:
            sell_value_at_risk = True
            codes.append("sell_value_at_risk")

    if is_owned and player is not None and prediction.direction == PriceDirection.RISE:
        current = player.current_price_tenths or prediction.now_cost_tenths
        before, after_one = _hypothetical_sell(player, new_current=current + 1, rules=rules)
        _b2, after_two = _hypothetical_sell(player, new_current=current + 2, rules=rules)
        counterfactual = True
        if after_one > before:
            wait_sell_increases = True
            codes.append("wait_for_rise_increases_sell")
        else:
            codes.append("plus_one_sell_unchanged")
        if after_two > before:
            codes.append("plus_two_may_increase_sell")

    planned_buy = next((t for t in plan.transfers if t.in_id == pid), None)
    if planned_buy is not None and bank is not None:
        out = owned.get(planned_buy.out_id)
        buy_now = prediction.now_cost_tenths
        sells = []
        if (
            out is not None
            and out.purchase_price_tenths is not None
            and out.current_price_tenths is not None
        ):
            sells = [(out.purchase_price_tenths, out.current_price_tenths)]
        after_now = budget_after_transfers(
            bank_tenths=bank,
            sells=sells,
            buys_current_tenths=[buy_now],
            rules=rules,
        )
        after_plus = budget_after_transfers(
            bank_tenths=bank,
            sells=sells,
            buys_current_tenths=[buy_now + 1],
            rules=rules,
        )
        counterfactual = True
        floor = settings.bank_floor_tenths_after
        unaffordable_now = after_now < floor
        unaffordable_plus = after_plus < floor
        if unaffordable_plus and not unaffordable_now:
            affordability_risk = True
            codes.append("affordability_risk")
        elif unaffordable_now:
            codes.append("already_unaffordable")
        elif not unaffordable_plus:
            codes.append("counterfactual_plus_one_still_affordable")

    too_late = False
    if hours_to_deadline is not None:
        if hours_to_deadline * 60 <= alerts.safety_floor_minutes:
            too_late = True
            codes.append("inside_safety_floor")
        if hours_to_deadline > settings.max_hours_ahead_to_spend_ft and not affordability_risk:
            codes.append("too_far_before_deadline")

    likely = prediction.likelihood == LikelihoodBand.LIKELY_NEXT_WINDOW
    watch_band = prediction.likelihood in {LikelihoodBand.WATCH, LikelihoodBand.LIKELY_NEXT_WINDOW}
    none_or_unlikely = prediction.likelihood in {
        LikelihoodBand.UNLIKELY,
        LikelihoodBand.UNAVAILABLE,
    } or prediction.direction == PriceDirection.NONE

    injured_buy = (not is_owned) and is_unavailable_for_buy(prediction)
    if injured_buy:
        codes.append("injured_target")

    football_ok = plan.legality_ok and (plan.football_beats_roll or plan.gain_vs_roll > 0)
    vanity_tv = (
        is_owned
        and prediction.direction == PriceDirection.RISE
        and not in_plan_out
        and not wait_sell_increases
    )
    if vanity_tv:
        codes.append("team_value_only")

    long_term_hold = (
        is_owned
        and prediction.direction == PriceDirection.FALL
        and not in_plan_out
        and not (plan.football_beats_roll and sell_value_at_risk)
    )
    if long_term_hold:
        codes.append("long_term_hold")

    last_ft_blocked = last_ft and not settings.allow_last_ft_for_price
    hit_blocked = needs_hit and not settings.allow_hit_for_price and not (
        football_ok and plan.hit_cost > 0
    )
    if last_ft_blocked:
        codes.append("last_ft_protected")
    if hit_blocked:
        codes.append("hit_not_justified")
    if not executable:
        codes.append("non_executable")

    def _action(
        cls: ActionClass,
        move: MoveType,
        summary: str,
        extra: list[str] | None = None,
    ) -> PriceAction:
        return PriceAction(
            action_class=cls,
            move_type=move,
            summary=summary,
            rationale_codes=list(dict.fromkeys(codes + (extra or []))),
            player_ids=[pid] + ([planned_buy.out_id] if planned_buy else []),
            related_scenario_id=related,
            valid_until=valid_until,
            affordability_risk=affordability_risk,
            sell_value_at_risk=sell_value_at_risk,
            counterfactual=counterfactual,
        )

    name = prediction.web_name

    # --- ignore (first match) ---
    if none_or_unlikely and not affordability_risk and prediction.likelihood != LikelihoodBand.ALREADY_MOVED:
        return _action(ActionClass.IGNORE, MoveType.NONE, f"{name}: no likely price move.")
    if prediction.likelihood == LikelihoodBand.ALREADY_MOVED and not affordability_risk:
        codes.append("already_moved")
        return _action(ActionClass.IGNORE, MoveType.HOLD, f"{name}: price already moved; logged for calibration.")
    if vanity_tv:
        return _action(ActionClass.IGNORE, MoveType.HOLD, f"{name}: owned rise is team-value only — not an action.")
    if (not is_owned) and (not in_plan_in) and (not in_watch):
        codes.append("not_in_plan")
        return _action(ActionClass.IGNORE, MoveType.NONE, f"{name}: not in squad, plan, or watchlist.")
    if long_term_hold and not sell_value_at_risk:
        return _action(ActionClass.IGNORE, MoveType.HOLD, f"{name}: likely fall on a long-term hold.")
    if hit_blocked and not affordability_risk:
        return _action(ActionClass.IGNORE, MoveType.NONE, f"{name}: would require a hit solely for price.")
    if injured_buy:
        return _action(ActionClass.IGNORE, MoveType.NONE, f"{name}: do not buy before a rise while unavailable.")
    if too_late:
        return _action(
            ActionClass.IGNORE,
            MoveType.NONE,
            f"{name}: inside the deadline safety floor — do not treat in-app timing as timely.",
        )

    # --- act_now_recommended (all must hold) ---
    material_ok = affordability_risk or (
        sell_value_at_risk and in_plan_out
    ) or (wait_sell_increases and in_plan_out)
    far = "too_far_before_deadline" in codes
    recommended_ok = (
        likely
        and "stale_public_data" not in prediction.warnings
        and executable
        and football_ok
        and material_ok
        and not injured_buy
        and not too_late
        and not last_ft_blocked
        and not hit_blocked
        and not far
        and team.executable_advice_allowed
    )
    if recommended_ok and in_plan_in and prediction.direction == PriceDirection.RISE:
        return _action(
            ActionClass.ACT_NOW_RECOMMENDED,
            MoveType.BUY_BEFORE_RISE,
            f"{name}: likely to rise and the planned buy may become unaffordable — transfer in FPL yourself if you still want this move.",
        )
    if recommended_ok and in_plan_out and prediction.direction == PriceDirection.FALL:
        return _action(
            ActionClass.ACT_NOW_RECOMMENDED,
            MoveType.SELL_BEFORE_FALL,
            f"{name}: likely to fall and a planned sell would lose selling value — sell in FPL yourself if the plan still holds.",
        )
    if recommended_ok and in_plan_out and wait_sell_increases:
        return _action(
            ActionClass.ACT_NOW_RECOMMENDED,
            MoveType.WAIT_FOR_RISE_THEN_SELL,
            f"{name}: planned sell; waiting for a rise that actually increases selling price may be better than selling now.",
        )

    # --- conditional ---
    if (affordability_risk or (sell_value_at_risk and in_plan_out)) and (
        not executable
        or last_ft_blocked
        or prediction.likelihood == LikelihoodBand.WATCH
        or not football_ok
        or not team.executable_advice_allowed
    ):
        missing = []
        if not executable:
            missing.append("sync bank/FT")
        if last_ft_blocked:
            missing.append("confirm spending the last free transfer")
        if not football_ok:
            missing.append("confirm you still want this football move")
        if prediction.likelihood != LikelihoodBand.LIKELY_NEXT_WINDOW:
            missing.append("price band is only watch")
        return _action(
            ActionClass.ACT_NOW_CONDITIONAL,
            MoveType.BUY_BEFORE_RISE if in_plan_in else MoveType.SELL_BEFORE_FALL,
            f"{name}: price timing may matter ({'; '.join(missing) or 'condition missing'}).",
        )

    # last FT + likely + affordability → conditional (never silent recommended)
    if last_ft_blocked and affordability_risk and watch_band:
        return _action(
            ActionClass.ACT_NOW_CONDITIONAL,
            MoveType.BUY_BEFORE_RISE,
            f"{name}: planned buy may become unaffordable, but this would spend your last free transfer.",
        )

    # --- watch ---
    if watch_band:
        if in_plan_in and "counterfactual_plus_one_still_affordable" in codes:
            return _action(
                ActionClass.WATCH,
                MoveType.HOLD,
                f"{name}: may rise but the planned buy still looks affordable after +0.1.",
            )
        if last_ft_blocked:
            return _action(
                ActionClass.WATCH,
                MoveType.HOLD,
                f"{name}: price watch only — last free transfer is protected.",
            )
        return _action(
            ActionClass.WATCH,
            MoveType.HOLD,
            f"{name}: {prediction.direction.value} possible; not smart to act on price alone.",
        )

    return _action(ActionClass.IGNORE, MoveType.NONE, f"{name}: no action.")


def classify_all(
    *,
    predictions: list[PricePrediction],
    team: ResolvedTeamState,
    rules: SeasonRules,
    plan: PlanView,
    watchlist: set[int],
    settings: PricesSettings,
    alerts: AlertsSettings,
    hours_to_deadline: float | None,
    now: datetime | None = None,
) -> list[PriceAction]:
    return [
        classify_action(
            prediction=p,
            team=team,
            rules=rules,
            plan=plan,
            watchlist=watchlist,
            settings=settings,
            alerts=alerts,
            hours_to_deadline=hours_to_deadline,
            now=now,
        )
        for p in predictions
    ]
