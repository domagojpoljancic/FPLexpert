"""CLI entrypoint for the FPL decision-support agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from fpl_agent import __version__
from fpl_agent.config import default_settings_path, load_dotenv_files, load_settings
from fpl_agent.errors import AgentError, ExitCode
from fpl_agent.observability import configure_logging, redact_value

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Read-only FPL decision-support agent")
team_state_app = typer.Typer(help="Local private team-state synchronization (no FPL login)")
rules_app = typer.Typer(help="Season rules utilities")
app.add_typer(team_state_app, name="team-state")
app.add_typer(rules_app, name="rules")


def _exit(code: ExitCode) -> None:
    raise typer.Exit(int(code))


def _refresh_readme() -> None:
    from fpl_agent.reporting.readme_index import refresh_readme_recent_runs

    refresh_readme_recent_runs()


load_dotenv_files()


@app.command("validate-config")
def validate_config(
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Path to YAML settings (defaults to config/settings.yaml if present)",
    ),
) -> None:
    """Validate configuration file and environment overlays."""
    settings_path = path or default_settings_path()
    try:
        settings = load_settings(settings_path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(f"OK team_id={settings.manager.team_id} horizon={settings.planning.horizon}")
    _exit(ExitCode.SUCCESS)


@app.command("doctor")
def doctor(
    path: Path | None = typer.Option(None, "--path"),
    mode: str = typer.Option("dry_run", "--mode"),
) -> None:
    """Environment and workspace health checks without printing secrets."""
    configure_logging()
    typer.echo(f"fpl-agent {__version__}")
    typer.echo(f"python {sys.version.split()[0]}")

    try:
        import httpx
        import pydantic
        import yaml  # noqa: F401

        typer.echo(f"pydantic {pydantic.__version__}")
        typer.echo(f"httpx {httpx.__version__}")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"dependency check failed: {exc}", err=True)
        _exit(ExitCode.INVALID_CONFIG)

    settings_path = path or default_settings_path()
    try:
        settings = load_settings(settings_path)
        typer.echo(f"config readable: {settings_path}")
        typer.echo(f"team_id configured: {settings.manager.team_id > 0}")
    except AgentError as exc:
        typer.echo(f"config error: {exc}", err=True)
        _exit(exc.exit_code)

    for rel in ("data/snapshots", "data/decision-ledger", "data/outcomes", "reports"):
        p = Path(rel)
        p.mkdir(parents=True, exist_ok=True)
        probe = p / ".doctor_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            typer.echo(f"writable: {rel}")
        except OSError as exc:
            typer.echo(f"not writable: {rel} ({exc})", err=True)
            _exit(ExitCode.INVALID_CONFIG)

    required_by_mode = {
        "dry_run": [],
        "manual": [],
        "daily": [],
        "prices": ["FPL_PRIVATE_STATE_B64"],
        "predeadline": [],
        "deadline": ["OPENAI_API_KEY"],
        "weekly_review": ["OPENAI_API_KEY"],
    }
    required = required_by_mode.get(mode, [])
    for name in required:
        present = bool(__import__("os").environ.get(name))
        typer.echo(f"env {name}: {'present' if present else 'missing'}")
    if mode in {"prices", "daily", "predeadline"}:
        squad_present = bool(__import__("os").environ.get("FPL_PRIVATE_STATE_B64")) or Path(
            "data/private-state/current.json"
        ).exists()
        typer.echo(f"private_squad: {'present' if squad_present else 'missing'}")

    # Never print secret values even if present
    fake = __import__("os").environ.get("OPENAI_API_KEY")
    if fake:
        typer.echo(f"openai_key_redacted={redact_value(fake, literal_secrets=[fake])[:20]}")

    typer.echo("doctor complete")
    _exit(ExitCode.SUCCESS)


@rules_app.command("diff")
def rules_diff(
    bootstrap: Path = typer.Option(
        Path("tests/fixtures/bootstrap_static_reduced.json"),
        "--bootstrap",
        help="Bootstrap JSON path",
    ),
) -> None:
    """Compare stored SeasonRules with bootstrap rule metadata."""
    from fpl_agent.rules.diff import DriftSeverity, compare_rules_to_bootstrap
    from fpl_agent.rules.season import load_season_rules_2026_27

    rules = load_season_rules_2026_27()
    payload = json.loads(bootstrap.read_text(encoding="utf-8"))
    severity, notes = compare_rules_to_bootstrap(rules, payload)
    typer.echo(severity.value)
    for note in notes:
        typer.echo(f"- {note}")
    if severity == DriftSeverity.MATERIAL:
        _exit(ExitCode.UNSUPPORTED_SEASON_RULES)
    _exit(ExitCode.SUCCESS)


def _load_bootstrap_payload(*, bootstrap: Path | None, offline: bool) -> dict[str, Any]:
    if bootstrap is not None:
        return json.loads(bootstrap.read_text(encoding="utf-8"))
    from fpl_agent.suggest import load_public_data

    payload, _fixtures = load_public_data(offline=offline)
    return payload


@team_state_app.command("lookup")
def team_state_lookup(
    names: list[str] = typer.Argument(..., help="Names as printed on FPL cards (include initials)"),
    bootstrap: Path | None = typer.Option(None, "--bootstrap", help="Bootstrap JSON; default live/cache"),
    offline: bool = typer.Option(False, "--offline", help="Use cached/fixture bootstrap only"),
) -> None:
    """Map screenshot / card names to official FPL ids. Does not guess."""
    from fpl_agent.errors import AgentError
    from fpl_agent.team_state.lookup import format_matches, match_names, players_from_bootstrap

    try:
        payload = _load_bootstrap_payload(bootstrap=bootstrap, offline=offline)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    catalog = players_from_bootstrap(payload)
    matches = match_names(names, catalog)
    typer.echo(format_matches(matches))
    if any(item.status != "OK" for item in matches):
        typer.echo(
            "Unresolved names: ask the user. Do not invent ids. Copy the printed card name including initials.",
            err=True,
        )
        _exit(ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE)
    ids = [item.player.player_id for item in matches if item.player is not None]
    typer.echo("ids " + " ".join(str(pid) for pid in ids))
    _exit(ExitCode.SUCCESS)


@team_state_app.command("names")
def team_state_names(
    path: Path = typer.Option(Path("data/private-state/current.json"), "--path"),
    bootstrap: Path | None = typer.Option(None, "--bootstrap"),
    offline: bool = typer.Option(False, "--offline"),
) -> None:
    """Print the saved squad as FPL web_name values (not raw ids)."""
    from datetime import UTC

    from fpl_agent.config import load_settings
    from fpl_agent.errors import AgentError
    from fpl_agent.team_state.lookup import (
        catalog_by_id,
        format_saved_squad,
        players_from_bootstrap,
    )
    from fpl_agent.team_state.private import load_and_validate_private_state

    if not path.exists():
        typer.echo(f"No squad file at {path}")
        typer.echo("Create it from the FPL app (15 players, bank, free transfers). See data/private-state/README.md")
        _exit(ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE)
    try:
        state = load_and_validate_private_state(path)
        payload = _load_bootstrap_payload(bootstrap=bootstrap, offline=offline)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    catalog = catalog_by_id(players_from_bootstrap(payload))
    settings = load_settings()
    as_of = state.as_of if state.as_of.tzinfo else state.as_of.replace(tzinfo=UTC)
    try:
        from zoneinfo import ZoneInfo

        local = as_of.astimezone(ZoneInfo(settings.manager.timezone)).strftime("%d %b %Y %H:%M %Z")
    except Exception:  # noqa: BLE001
        local = as_of.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    typer.echo(
        format_saved_squad(
            player_ids=list(state.player_ids),
            catalog=catalog,
            bank_tenths=state.bank_tenths,
            free_transfers=state.free_transfers,
            captain_id=state.captain_id,
            vice_id=state.vice_id,
            starters=list(state.starters) if state.starters else None,
            bench_order=list(state.bench_order) if state.bench_order else None,
            as_of_label=local,
            gameweek=state.applies_before_gameweek,
        )
    )
    _exit(ExitCode.SUCCESS)


@team_state_app.command("validate")
def team_state_validate(path: Path) -> None:
    from fpl_agent.team_state.private import load_and_validate_private_state

    try:
        state = load_and_validate_private_state(path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(
        f"OK season={state.season} gw={state.applies_before_gameweek} players={len(state.player_ids)}"
    )
    _exit(ExitCode.SUCCESS)


@team_state_app.command("status")
def team_state_status(
    path: Path = typer.Option(Path("data/private-state/current.json"), "--path"),
) -> None:
    from datetime import UTC, datetime

    from fpl_agent.config import load_settings
    from fpl_agent.team_state.private import load_and_validate_private_state

    if not path.exists():
        typer.echo(f"No squad file at {path}")
        typer.echo("Create it from the FPL app (15 players, bank, free transfers). See data/private-state/README.md")
        _exit(ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE)
    try:
        state = load_and_validate_private_state(path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    settings = load_settings()
    now = datetime.now(UTC)
    as_of = state.as_of if state.as_of.tzinfo else state.as_of.replace(tzinfo=UTC)
    age_hours = (now - as_of.astimezone(UTC)).total_seconds() / 3600
    max_age = settings.freshness.private_squad_max_age_hours
    stale = age_hours > max_age
    try:
        from zoneinfo import ZoneInfo

        local = as_of.astimezone(ZoneInfo(settings.manager.timezone)).strftime("%d %b %Y %H:%M %Z")
    except Exception:  # noqa: BLE001
        local = as_of.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    typer.echo(f"File: {path}")
    typer.echo(f"Last saved: {local}  ({age_hours:.0f} hours ago)")
    typer.echo(f"Trust window: {max_age:.0f} hours  →  {'STALE' if stale else 'fresh'}")
    typer.echo(f"For gameweek: {state.applies_before_gameweek}")
    typer.echo(f"Bank: £{state.bank_tenths / 10:.1f}m   Free transfers: {state.free_transfers}")
    typer.echo(f"Players: {len(state.player_ids)}")
    if stale:
        typer.echo("")
        typer.echo(
            "Reports will say INSUFFICIENT (cannot treat transfers as executable). "
            "Update this file from the FPL app. Field meanings: data/private-state/README.md"
        )
    _exit(ExitCode.SUCCESS)


@team_state_app.command("encode-for-github")
def team_state_encode(path: Path) -> None:
    """Encode private state for GitHub secret set. Does not print the payload."""
    import base64
    import subprocess

    raw = path.read_bytes()
    # Validate first
    from fpl_agent.team_state.private import load_and_validate_private_state

    try:
        load_and_validate_private_state(path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)

    payload = base64.b64encode(raw)
    typer.echo(
        "Base64 is encoding, not encryption. GitHub encrypts stored secrets at rest."
    )
    typer.echo("Writing payload to gh secret FPL_PRIVATE_STATE_B64 via stdin (payload not echoed).")
    try:
        subprocess.run(
            ["gh", "secret", "set", "FPL_PRIVATE_STATE_B64"],
            input=payload,
            check=True,
        )
    except FileNotFoundError:
        typer.echo("gh CLI not found; payload not printed. Install gh or set the secret manually.", err=True)
        _exit(ExitCode.INVALID_CONFIG)
    except subprocess.CalledProcessError as exc:
        typer.echo(f"gh secret set failed with code {exc.returncode}", err=True)
        _exit(ExitCode.PUBLISHING_FAILURE)
    typer.echo("secret set attempted")
    _exit(ExitCode.SUCCESS)


@team_state_app.command("materialize-from-env")
def team_state_materialize(
    dest: Path = typer.Option(Path("data/private-state/current.json"), "--dest"),
) -> None:
    """Decode FPL_PRIVATE_STATE_B64 to dest. Never prints the payload."""
    import base64
    import os

    load_dotenv_files()
    raw = os.environ.get("FPL_PRIVATE_STATE_B64", "").strip()
    if not raw:
        typer.echo("FPL_PRIVATE_STATE_B64 missing", err=True)
        _exit(ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE)
    try:
        payload = base64.b64decode(raw, validate=False)
    except Exception:  # noqa: BLE001
        typer.echo("FPL_PRIVATE_STATE_B64 is not valid base64", err=True)
        _exit(ExitCode.INVALID_CONFIG)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    from fpl_agent.team_state.private import load_and_validate_private_state

    try:
        state = load_and_validate_private_state(dest)
    except AgentError as exc:
        dest.unlink(missing_ok=True)
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(f"OK dest={dest} gw={state.applies_before_gameweek} players={len(state.player_ids)}")
    _exit(ExitCode.SUCCESS)


@app.command("daily")
def daily(
    offline: bool = typer.Option(False, "--offline", help="Use cached FPL snapshots only"),
    save: bool = typer.Option(True, "--save/--no-save", help="Write report under reports/"),
    notify: bool = typer.Option(False, "--notify/--no-notify", help="Attempt notify channels (still dry-run unless publishing enabled)"),
    universe: str = typer.Option("all-relevant", "--universe", help="squad|plan|watchlist|all-relevant"),
    private: Path = typer.Option(Path("data/private-state/current.json"), "--private"),
) -> None:
    """Daily price watch: who might rise/fall and whether it is smart to act tonight. No OpenAI."""
    from fpl_agent.prices.run import Universe, run_prices, write_prices_artifact

    if universe not in {"squad", "plan", "watchlist", "all-relevant", "catalog"}:
        typer.echo("invalid --universe", err=True)
        _exit(ExitCode.INVALID_CONFIG)
    kind: Universe = universe  # type: ignore[assignment]
    try:
        report = run_prices(offline=offline, universe=kind, notify=notify, save=False, private_path=private)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(report.markdown)
    if save:
        path = write_prices_artifact(report)
        typer.echo(f"\nSaved {path}")
        _refresh_readme()
    _exit(ExitCode.SUCCESS)


@app.command("prices")
def prices(
    offline: bool = typer.Option(False, "--offline", help="Use cached FPL snapshots only"),
    save: bool = typer.Option(True, "--save/--no-save", help="Write report under reports/"),
    notify: bool = typer.Option(False, "--notify/--no-notify"),
    universe: str = typer.Option("all-relevant", "--universe"),
    private: Path = typer.Option(Path("data/private-state/current.json"), "--private"),
) -> None:
    """Alias for daily price watch."""
    daily(offline=offline, save=save, notify=notify, universe=universe, private=private)


@app.command("predeadline")
def predeadline(
    offline: bool = typer.Option(False, "--offline", help="Use cached FPL snapshots only"),
    live_ai: bool = typer.Option(
        False,
        "--live-ai",
        help="Require live OpenAI (fail if OPENAI_API_KEY missing)",
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Write report under reports/"),
    force: bool = typer.Option(False, "--force", help="Run even if more than ~1 day before the deadline"),
) -> None:
    """Full news/squad review, intended ~1 day before the GW deadline."""
    from fpl_agent.daily import render_daily_text, run_predeadline, write_daily_artifact

    try:
        report = run_predeadline(offline=offline, require_live_ai=live_ai, force=force)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    text = render_daily_text(report)
    typer.echo(text)
    if save and not report.skipped:
        path = write_daily_artifact(report)
        typer.echo(f"\nSaved {path}")
        _refresh_readme()
    _exit(ExitCode.SUCCESS)


@app.command("analyze")
def analyze(
    mode: str = typer.Option("dry_run", "--mode"),
    offline: bool = typer.Option(False, "--offline"),
) -> None:
    """Run analysis modes. Full pipeline wired in later phases."""
    from fpl_agent.pipeline import run_pipeline

    try:
        result = run_pipeline(mode=mode, offline=offline)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    except NotImplementedError as exc:
        typer.echo(str(exc), err=True)
        _exit(ExitCode.INVALID_CONFIG)
    typer.echo(json.dumps(result, indent=2, default=str))
    _exit(ExitCode.SUCCESS)


@app.command("monitor")
def monitor(offline: bool = typer.Option(False, "--offline")) -> None:
    from fpl_agent.monitoring.compare import run_monitor

    summary = run_monitor(offline=offline)
    typer.echo(json.dumps(summary, indent=2, default=str))
    _exit(ExitCode.SUCCESS)


@app.command("suggest-squad")
def suggest_squad(
    path: Path | None = typer.Option(None, "--path", help="Settings path"),
    offline: bool = typer.Option(False, "--offline", help="Use cached snapshots only"),
    budget: float = typer.Option(100.0, "--budget", help="Budget in £m"),
) -> None:
    """Suggest a legal initial 15-player squad for the next gameweek."""
    from fpl_agent.strategy.draft import optimise_initial_squad
    from fpl_agent.suggest import load_public_data, projections_for_horizon

    settings = load_settings(path or default_settings_path())
    from fpl_agent.rules.season import load_season_rules_2026_27

    rules = load_season_rules_2026_27()
    try:
        bootstrap, fixtures = load_public_data(offline=offline)
    except AgentError as exc:
        typer.echo(f"FAILED: {exc}", err=True)
        _exit(exc.exit_code)

    projections, gameweeks = projections_for_horizon(
        bootstrap=bootstrap,
        fixtures=fixtures,
        weights=settings.planning.weights,
    )
    squad = optimise_initial_squad(projections, rules, budget_tenths=int(round(budget * 10)))

    teams = {int(t["id"]): str(t["short_name"]) for t in bootstrap.get("teams") or []}
    labels = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    xi_ids = {p.player_id for p in squad.xi}

    typer.echo(f"Suggested squad for GW{gameweeks[0]} (horizon GW{gameweeks[0]}-{gameweeks[-1]})")
    typer.echo(f"Formation {squad.formation} | cost £{squad.total_cost_tenths / 10:.1f}m | bank £{squad.bank_tenths / 10:.1f}m")
    typer.echo("")
    typer.echo(f"{'POS':<4}{'PLAYER':<18}{'TEAM':<6}{'PRICE':>6}{'GW1':>7}{'6GW':>8}  ROLE")
    for player in squad.players:
        role = "XI" if player.player_id in xi_ids else "bench"
        if player.player_id == squad.captain.player_id:
            role = "XI (C)"
        elif player.player_id == squad.vice_captain.player_id:
            role = "XI (V)"
        gw1 = player.xp_by_gw[0] if player.xp_by_gw else 0.0
        typer.echo(
            f"{labels[player.element_type]:<4}{player.web_name[:17]:<18}"
            f"{teams.get(player.team_id, '?'):<6}{player.price_tenths / 10:>6.1f}"
            f"{gw1:>7.1f}{player.weighted_xp:>8.1f}  {role}"
        )
    typer.echo("")
    typer.echo("Projections are an unvalidated preseason baseline; you make all FPL changes.")
    _exit(ExitCode.SUCCESS)


@app.command("live-smoke")
def live_smoke() -> None:
    """Opt-in live FPL contract smoke (network)."""
    from fpl_agent.ingestion.smoke import live_smoke_check

    try:
        report = live_smoke_check()
    except AgentError as exc:
        typer.echo(f"SMOKE FAILED: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(json.dumps(report, indent=2))
    _exit(ExitCode.SUCCESS)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
