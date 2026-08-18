"""Name-to-id mapping for FPL screenshot dumps."""

from __future__ import annotations

from fpl_agent.team_state.lookup import (
    CatalogPlayer,
    NextFixture,
    match_cards,
    match_name,
    match_names,
    normalize_name,
    parse_card_token,
    players_from_bootstrap,
)


def _p(
    pid: int,
    web: str,
    *,
    first: str = "",
    second: str = "",
    team_id: int = 1,
    team: str = "ARS",
    pos: str = "MID",
    cost: int = 50,
) -> CatalogPlayer:
    return CatalogPlayer(
        player_id=pid,
        web_name=web,
        first_name=first,
        second_name=second,
        team_id=team_id,
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


def test_parse_card_token_name_and_fixture() -> None:
    card = parse_card_token("O'Nien|IPS|A|4.0|DEF")
    assert card.name == "O'Nien"
    assert card.opponent == "IPS"
    assert card.ha == "A"
    assert card.cost_tenths == 40
    assert card.position == "DEF"
    blank = parse_card_token("?|CHE|H|4.5|FWD")
    assert blank.name == ""
    assert blank.cost_tenths == 45


def test_fixture_line_blocks_wrong_club_gomez() -> None:
    catalog = [
        _p(99, "Gomez", first="Joe", second="Gomez", team_id=10, team="LIV", pos="DEF", cost=50),
        _p(498, "Senesi", first="Marcos", second="Senesi", team_id=19, team="TOT", pos="DEF", cost=60),
    ]
    fixtures = {
        10: NextFixture(opponent="NEW", ha="A"),
        19: NextFixture(opponent="BRE", ha="A"),
    }
    matches = match_cards(
        [parse_card_token("Gomez|BRE|A|6.0|DEF")],
        catalog,
        fixtures_by_team=fixtures,
    )
    assert matches[0].status == "NONE"
    assert matches[0].player is None


def test_saved_squad_recovers_hallucinated_screenshot_names() -> None:
    catalog = [
        _p(1, "Raya", team_id=1, team="ARS", pos="GKP", cost=60),
        _p(498, "Senesi", team_id=19, team="TOT", pos="DEF", cost=60),
        _p(388, "Guéhi", team_id=3, team="MCI", pos="DEF", cost=60),
        _p(397, "Semenyo", team_id=3, team="MCI", pos="MID", cost=85),
        _p(539, "O'Nien", team_id=20, team="SUN", pos="DEF", cost=40),
        _p(272, "Kusi-Asare", team_id=8, team="FUL", pos="FWD", cost=45),
        _p(99, "Gomez", team_id=10, team="LIV", pos="DEF", cost=50),
    ]
    fixtures = {
        1: NextFixture(opponent="COV", ha="H"),
        19: NextFixture(opponent="BRE", ha="A"),
        3: NextFixture(opponent="BOU", ha="H"),
        20: NextFixture(opponent="IPS", ha="A"),
        8: NextFixture(opponent="CHE", ha="H"),
        10: NextFixture(opponent="NEW", ha="A"),
    }
    queries = [
        parse_card_token("Raya|COV|H|6.0|GKP"),
        parse_card_token("Gomez|BRE|A|6.0|DEF"),
        parse_card_token("Akanji|BOU|H|6.0|DEF"),
        parse_card_token("Bernardo|BOU|H|8.5|MID"),
        parse_card_token("D'Shea|IPS|A|4.0|DEF"),
        parse_card_token("Kud-Roza|CHE|H|4.5|FWD"),
    ]
    matches = match_cards(
        queries,
        catalog,
        fixtures_by_team=fixtures,
        saved_ids=[1, 498, 388, 397, 539, 272],
    )
    assert [m.status for m in matches] == ["OK"] * 6
    assert [m.player.player_id for m in matches if m.player] == [1, 498, 388, 397, 539, 272]
    assert matches[0].note == "name"
    assert matches[1].note == "saved+fixture"
    assert matches[2].player is not None and matches[2].player.web_name == "Guéhi"
    assert matches[3].player is not None and matches[3].player.web_name == "Semenyo"
