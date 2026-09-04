"""Single ranking authority: primary move locked by weighted horizon."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fpl_agent.projections.preseason import PlayerProjection
from fpl_agent.strategy.transfers import (
    RANKING_KEY_WEIGHTED_HORIZON,
    select_primary_move,
    this_week_upgrade,
    rank_transfer_candidates,
    rank_transfer_plans,
)


def _proj(
    player_id: int,
    *,
    element_type: int,
    team_id: int,
    price: int,
    weighted: float,
    gw: float,
    p_start: float = 0.9,
    name: str = "X",
) -> PlayerProjection:
    return PlayerProjection(
        player_id=player_id,
        web_name=name,
        team_id=team_id,
        element_type=element_type,
        price_tenths=price,
        p_start=p_start,
        expected_minutes=80.0,
        points_per_90=4.0,
        xp_by_gw=(gw, gw, gw, gw, gw, gw),
        weighted_xp=weighted,
    )


def _gw3_shaped_conflict() -> tuple[list[int], dict[int, dict], dict[int, PlayerProjection]]:
    """Ajayi wins this-GW ranking; Egan wins weighted-horizon ranking."""
    types = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    owned = list(range(1, 16))
    catalog: dict[int, dict] = {}
    projections: dict[int, PlayerProjection] = {}
    for pid, et in zip(owned, types, strict=True):
        catalog[pid] = {
            "id": pid,
            "web_name": f"P{pid}",
            "team": pid,
            "element_type": et,
            "now_cost": 50,
            "status": "a",
        }
        if pid == 5:
            catalog[5]["web_name"] = "Onien"
            projections[5] = _proj(5, element_type=2, team_id=5, price=50, weighted=2.0, gw=1.0, p_start=0.40, name="Onien")
        elif pid == 6:
            catalog[6]["web_name"] = "Virgil"
            projections[6] = _proj(6, element_type=2, team_id=6, price=50, weighted=5.5, gw=2.0, p_start=0.90, name="Virgil")
        else:
            projections[pid] = _proj(
                pid,
                element_type=et,
                team_id=pid,
                price=50,
                weighted=6.0 if et != 1 else 4.0,
                gw=2.5 if et != 1 else 3.0,
                name=f"P{pid}",
            )
    catalog[100] = {"id": 100, "web_name": "Egan", "team": 16, "element_type": 2, "now_cost": 50, "status": "a"}
    projections[100] = _proj(100, element_type=2, team_id=16, price=50, weighted=8.5, gw=3.8, p_start=0.85, name="Egan")
    catalog[101] = {"id": 101, "web_name": "Ajayi", "team": 17, "element_type": 2, "now_cost": 50, "status": "a"}
    projections[101] = _proj(101, element_type=2, team_id=17, price=50, weighted=6.8, gw=5.5, p_start=0.90, name="Ajayi")
    return owned, catalog, projections


def test_select_primary_prefers_horizon_over_this_gw() -> None:
    owned, catalog, projections = _gw3_shaped_conflict()
    affordable, _ = rank_transfer_candidates(
        owned_ids=owned,
        bank_tenths=0,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    this_gw = this_week_upgrade(affordable)
    assert this_gw is not None
    assert this_gw.in_name == "Ajayi"

    primary = select_primary_move(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    assert primary.action == "transfer"
    assert primary.ranking_key == RANKING_KEY_WEIGHTED_HORIZON
    assert primary.plan is not None
    assert primary.plan.moves[-1].in_name == "Egan"
    assert primary.runner_up is not None
    assert primary.runner_up.moves[-1].in_name == "Ajayi"
    # Prove the conflict still exists in raw lists
    plans = rank_transfer_plans(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    assert plans[0].moves[-1].in_name == "Egan"


def _one_move_plan(
    *,
    out_id: int,
    in_id: int,
    out_name: str,
    in_name: str,
    weighted: float,
    gw: float,
) -> TransferPlan:
    from fpl_agent.strategy.transfers import TransferCandidate, TransferPlan

    move = TransferCandidate(
        out_id=out_id,
        in_id=in_id,
        out_name=out_name,
        in_name=in_name,
        element_type=2,
        sell_tenths=50,
        buy_tenths=50,
        bank_after_tenths=0,
        bank_shortfall_tenths=0,
        affordable=True,
        delta_weighted_xp=weighted,
        delta_gw_xp=gw,
        out_p_start=0.4,
        in_p_start=0.9,
        in_starts=True,
    )
    return TransferPlan(
        moves=(move,),
        free_transfers_used=1,
        hit_cost=0,
        delta_weighted_xp=weighted,
        delta_gw_xp=gw,
        net_gw_xp=gw,
        bank_after_tenths=0,
        affordable=True,
    )


def test_epsilon_keeps_sort_key_winner_and_ignores_insertion_order() -> None:
    from fpl_agent.strategy.transfers import PRIMARY_EPSILON_WEIGHTED_XP

    # Within epsilon on net-horizon; this-GW tie-break prefers Alpha (higher gw).
    alpha = _one_move_plan(out_id=1, in_id=10, out_name="Out", in_name="Alpha", weighted=4.0, gw=3.0)
    beta = _one_move_plan(out_id=2, in_id=11, out_name="Out2", in_name="Beta", weighted=4.0 - 0.1, gw=2.0)
    assert abs(alpha.delta_weighted_xp - beta.delta_weighted_xp) <= PRIMARY_EPSILON_WEIGHTED_XP

    owned, catalog, projections = _gw3_shaped_conflict()
    base = dict(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    first = select_primary_move(**base, plans=[beta, alpha])
    second = select_primary_move(**base, plans=[alpha, beta])
    assert first.plan is not None and second.plan is not None
    assert first.plan.moves[-1].in_name == "Alpha"
    assert second.plan.moves[-1].in_name == "Alpha"
    assert first.is_close is True
    assert second.is_close is True
    assert first.runner_up is not None
    assert first.runner_up.moves[-1].in_name == "Beta"


def test_outside_epsilon_higher_horizon_wins() -> None:
    from fpl_agent.strategy.transfers import PRIMARY_EPSILON_WEIGHTED_XP

    winner = _one_move_plan(out_id=1, in_id=10, out_name="Out", in_name="Horizon", weighted=5.0, gw=2.0)
    loser = _one_move_plan(
        out_id=2,
        in_id=11,
        out_name="Out2",
        in_name="ThisGw",
        weighted=5.0 - PRIMARY_EPSILON_WEIGHTED_XP - 0.5,
        gw=4.0,
    )
    owned, catalog, projections = _gw3_shaped_conflict()
    primary = select_primary_move(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
        plans=[loser, winner],
    )
    assert primary.plan is not None
    assert primary.plan.moves[-1].in_name == "Horizon"
    assert primary.is_close is False
    assert primary.runner_up is not None
    assert primary.runner_up.moves[-1].in_name == "ThisGw"


def test_also_considered_marks_runner_up(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    from fpl_agent.config import load_settings
    from fpl_agent.daily import run_predeadline
    from fpl_agent.llm.client import FakeOpenAIClient

    owned, catalog, projections = _gw3_shaped_conflict()
    elements = []
    for pid, el in catalog.items():
        row = dict(el)
        row.setdefault("chance_of_playing_next_round", 100)
        row.setdefault("news", "")
        elements.append(row)
    teams = [{"id": i, "short_name": f"T{i}"} for i in range(1, 21)]
    deadline = (datetime.now(UTC) + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bootstrap = {
        "events": [{"id": 3, "is_next": True, "deadline_time": deadline}],
        "elements": elements,
        "teams": teams,
    }
    private = {
        "schema_version": "1.0.0",
        "season": "2026-27",
        "applies_before_gameweek": 3,
        "as_of": datetime.now(UTC).isoformat(),
        "player_ids": owned,
        "bank_tenths": 0,
        "free_transfers": 1,
        "purchase_prices_tenths": {str(i): 50 for i in owned},
        "chip_instances": [],
        "captain_id": 8,
        "vice_id": 1,
    }
    private_path = tmp_path / "current.json"
    private_path.write_text(__import__("json").dumps(private), encoding="utf-8")
    monkeypatch.setattr("fpl_agent.daily.load_public_data", lambda offline=False: (bootstrap, []))
    monkeypatch.setattr(
        "fpl_agent.prices.run.run_prices",
        lambda **kwargs: SimpleNamespace(status=SimpleNamespace(value="NO ACTION"), warnings=[]),
    )
    monkeypatch.setattr(
        "fpl_agent.prices.run.prices_payload_for_llm",
        lambda report: {"price_actions": [], "price_status": "NO ACTION"},
    )
    monkeypatch.setattr("fpl_agent.daily.project_all", lambda **kwargs: list(projections.values()))
    monkeypatch.setattr("fpl_agent.projections.preseason.configure_from_settings", lambda settings: None)
    monkeypatch.setattr("fpl_agent.daily.build_client", lambda **kwargs: FakeOpenAIClient())

    report = run_predeadline(
        settings=load_settings(),
        offline=True,
        force=True,
        private_path=private_path,
        reports_dir=tmp_path / "reports",
        snapshot_root=tmp_path / "snaps",
    )
    also = report.weekly_plan.get("also_considered") or []
    assert also
    picked = [r for r in also if r.get("picked")]
    not_picked = [r for r in also if not r.get("picked")]
    assert len(picked) == 1
    assert picked[0]["in_name"] == "Egan"
    assert not_picked
    assert any(r.get("in_name") == "Ajayi" and r.get("reason") for r in not_picked)


def test_primary_payload_ids_agree_and_are_stable() -> None:
    owned, catalog, projections = _gw3_shaped_conflict()
    kwargs = dict(
        owned_ids=owned,
        bank_tenths=0,
        free_transfers=1,
        purchase_prices_tenths={str(i): 50 for i in owned},
        catalog=catalog,
        projections=projections,
    )
    a = select_primary_move(**kwargs)
    b = select_primary_move(**kwargs)
    assert a.as_payload()["in_id"] == b.as_payload()["in_id"] == 100
    assert a.as_payload()["out_id"] == b.as_payload()["out_id"]


def test_predeadline_weekly_plan_primary_ids_agree(tmp_path: Path, monkeypatch) -> None:
    """Offline FakeOpenAI path: best_affordable / best_plan / primary_move share IN id."""
    from types import SimpleNamespace

    from fpl_agent.config import load_settings
    from fpl_agent.daily import run_predeadline

    owned, catalog, projections = _gw3_shaped_conflict()
    # Expand catalog into bootstrap-shaped elements list
    elements = []
    for pid, el in catalog.items():
        row = dict(el)
        row.setdefault("chance_of_playing_next_round", 100)
        row.setdefault("news", "")
        elements.append(row)
    teams = [{"id": i, "short_name": f"T{i}"} for i in range(1, 21)]
    deadline = (datetime.now(UTC) + timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    bootstrap = {
        "events": [{"id": 3, "is_next": True, "deadline_time": deadline}],
        "elements": elements,
        "teams": teams,
    }
    private = {
        "schema_version": "1.0.0",
        "season": "2026-27",
        "applies_before_gameweek": 3,
        "as_of": datetime.now(UTC).isoformat(),
        "player_ids": owned,
        "bank_tenths": 0,
        "free_transfers": 1,
        "purchase_prices_tenths": {str(i): 50 for i in owned},
        "chip_instances": [],
        "captain_id": 8,
        "vice_id": 1,
    }
    private_path = tmp_path / "current.json"
    private_path.write_text(__import__("json").dumps(private), encoding="utf-8")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "fpl_agent.daily.load_public_data",
        lambda offline=False: (bootstrap, []),
    )

    monkeypatch.setattr(
        "fpl_agent.prices.run.run_prices",
        lambda **kwargs: SimpleNamespace(status=SimpleNamespace(value="NO ACTION"), warnings=[]),
    )
    monkeypatch.setattr(
        "fpl_agent.prices.run.prices_payload_for_llm",
        lambda report: {"price_actions": [], "price_status": "NO ACTION"},
    )
    monkeypatch.setattr("fpl_agent.daily.project_all", lambda **kwargs: list(projections.values()))
    monkeypatch.setattr(
        "fpl_agent.projections.preseason.configure_from_settings",
        lambda settings: None,
    )
    from fpl_agent.llm.client import FakeOpenAIClient

    monkeypatch.setattr(
        "fpl_agent.daily.build_client",
        lambda **kwargs: FakeOpenAIClient(),
    )

    settings = load_settings()
    r1 = run_predeadline(
        settings=settings,
        offline=True,
        force=True,
        private_path=private_path,
        reports_dir=tmp_path / "reports",
        snapshot_root=tmp_path / "snaps",
    )
    r2 = run_predeadline(
        settings=settings,
        offline=True,
        force=True,
        private_path=private_path,
        reports_dir=tmp_path / "reports",
        snapshot_root=tmp_path / "snaps",
    )
    wp = r1.weekly_plan
    assert wp.get("primary_move")
    assert wp["primary_move"]["in_id"] == 100
    assert wp["best_affordable"]["in_id"] == 100
    assert wp["best_plan"]["moves"][-1]["in_id"] == 100
    assert wp["best_affordable"]["in_id"] == wp["best_plan"]["moves"][-1]["in_id"] == wp["primary_move"]["in_id"]
    assert r2.weekly_plan["primary_move"]["in_id"] == r1.weekly_plan["primary_move"]["in_id"]
    assert r2.weekly_plan["primary_move"]["out_id"] == r1.weekly_plan["primary_move"]["out_id"]
