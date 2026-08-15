"""CLI entrypoint for the FPL decision-support agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from fpl_agent import __version__
from fpl_agent.config import load_settings
from fpl_agent.errors import AgentError, ExitCode
from fpl_agent.observability import configure_logging, redact_value

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Read-only FPL decision-support agent")
team_state_app = typer.Typer(help="Local private team-state synchronization (no FPL login)")
rules_app = typer.Typer(help="Season rules utilities")
app.add_typer(team_state_app, name="team-state")
app.add_typer(rules_app, name="rules")


def _exit(code: ExitCode) -> None:
    raise typer.Exit(int(code))


@app.command("validate-config")
def validate_config(
    path: Path = typer.Option(
        Path("config/settings.example.yaml"),
        "--path",
        help="Path to YAML settings",
    ),
) -> None:
    """Validate configuration file and environment overlays."""
    try:
        settings = load_settings(path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(f"OK team_id={settings.manager.team_id} horizon={settings.planning.horizon}")
    _exit(ExitCode.SUCCESS)


@app.command("doctor")
def doctor(
    path: Path = typer.Option(Path("config/settings.example.yaml"), "--path"),
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

    try:
        settings = load_settings(path)
        typer.echo(f"config readable: {path}")
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
        "deadline": ["OPENAI_API_KEY"],
        "weekly_review": ["OPENAI_API_KEY"],
    }
    required = required_by_mode.get(mode, [])
    for name in required:
        present = bool(__import__("os").environ.get(name))
        typer.echo(f"env {name}: {'present' if present else 'missing'}")

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
    from fpl_agent.team_state.private import load_and_validate_private_state

    if not path.exists():
        typer.echo("no private state file")
        _exit(ExitCode.INSUFFICIENT_OR_STALE_TEAM_STATE)
    try:
        state = load_and_validate_private_state(path)
    except AgentError as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        _exit(exc.exit_code)
    typer.echo(f"as_of={state.as_of.isoformat()} gw={state.applies_before_gameweek}")
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
