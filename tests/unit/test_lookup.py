"""Name-to-id mapping for FPL screenshot dumps."""

from __future__ import annotations

from fpl_agent.team_state.lookup import (
    CatalogPlayer,
    match_name,
    match_names,
    normalize_name,
    players_from_bootstrap,
)


def _p(
    pid: int,
    web: str,
    *,
    first: str = "",
    second: str = "",
    team: str = "ARS",
    pos: str = "MID",
    cost: int = 50,
) -> CatalogPlayer:
    return CatalogPlayer(
        player_id=pid,
        web_name=web,
        first_name=first,
        second_name=second,
        team_short=team,
        position=pos,
        now_cost_tenths=cost,
    )


CATALOG = [
    _p(1, "Raya", first="David", second="Raya Martín", pos="GKP", cost=60),
    _p(67, "Rayan", first="Rayan", second="Rocha", team="BOU", cost=65),
    _p(4, "Gabriel", first="Gabriel", second="Magalhães", pos="DEF", cost=80),
    _p(18, "Martinelli", first="Gabriel", second="Martinelli", cost=65),
    _p(27, "G.Jesus", first="Gabriel", second="Jesus", pos="FWD", cost=60),
    _p(426, "B.Fernandes", first="Bruno", second="Fernandes", team="MUN", cost=120),
    _p(525, "Fernandes", first="Mateus", second="Fernandes", team="TOT", cost=60),
    _p(388, "Guéhi", first="Marc", second="Guéhi", team="MCI", pos="DEF", cost=60),
    _p(356, "Virgil", first="Virgil", second="van Dijk", team="LIV", pos="DEF", cost=65),
    _p(539, "O'Nien", first="Luke", second="O'Nien", team="SUN", pos="DEF", cost=40),
    _p(106, "Thiago", first="Igor", second="Thiago", team="BRE", pos="FWD", cost=80),
]


def test_normalize_folds_accents_and_punctuation() -> None:
    assert normalize_name("B. Fernandes") == normalize_name("B.Fernandes")
    assert normalize_name("Guéhi") == normalize_name("Guehi")
    assert normalize_name("O'Nien") == normalize_name("O’Nien")
    assert normalize_name("Raya") != normalize_name("Rayan")


def test_raya_does_not_steal_rayan() -> None:
    hit = match_name("Raya", CATALOG)
    assert hit.status == "OK"
    assert hit.player is not None
    assert hit.player.player_id == 1


def test_printed_initials_select_bruno_not_mateus() -> None:
    bruno = match_name("B. Fernandes", CATALOG)
    assert bruno.status == "OK"
    assert bruno.player is not None
    assert bruno.player.player_id == 426
    mateus = match_name("Fernandes", CATALOG)
    assert mateus.status == "OK"
    assert mateus.player is not None
    assert mateus.player.player_id == 525


def test_gabriel_uses_web_name_not_first_name() -> None:
    hit = match_name("Gabriel", CATALOG)
    assert hit.status == "OK"
    assert hit.player is not None
    assert hit.player.player_id == 4


def test_guehi_and_virgil_and_onien() -> None:
    assert match_name("Guehi", CATALOG).player is not None
    assert match_name("Guehi", CATALOG).player.player_id == 388  # type: ignore[union-attr]
    assert match_name("Virgil", CATALOG).player.player_id == 356  # type: ignore[union-attr]
    assert match_name("O’Nien", CATALOG).player.player_id == 539  # type: ignore[union-attr]


def test_unknown_is_none_not_a_guess() -> None:
    hit = match_name("NotAPlayer", CATALOG)
    assert hit.status == "NONE"
    assert hit.player is None


def test_ambiguous_when_two_share_exact_web_name() -> None:
    catalog = [_p(1, "Smith", team="ARS"), _p(2, "Smith", team="CHE")]
    hit = match_name("Smith", catalog)
    assert hit.status == "AMBIGUOUS"
    assert {p.player_id for p in hit.candidates} == {1, 2}


def test_batch_screenshot_names() -> None:
    queries = ["Raya", "Gabriel", "B.Fernandes", "Guéhi", "Thiago"]
    matches = match_names(queries, CATALOG)
    assert [m.status for m in matches] == ["OK"] * 5
    assert [m.player.player_id for m in matches if m.player] == [1, 4, 426, 388, 106]


def test_players_from_bootstrap_reduced_fixture() -> None:
    import json
    from pathlib import Path

    boot = json.loads(Path("tests/fixtures/bootstrap_static_reduced.json").read_text())
    catalog = players_from_bootstrap(boot)
    hit = match_name("Raya", catalog)
    assert hit.status == "OK"
    assert hit.player is not None
    assert hit.player.player_id == 1
    assert hit.player.position == "GKP"
