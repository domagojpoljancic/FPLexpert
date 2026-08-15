# FPL Decision-Support Agent

WIP read-only Fantasy Premier League decision-support system. It recommends transfers, hits, lineups, captains, bench order, and chips — **you** always make the FPL changes. It never logs into FPL or mutates a team.

## Status

| Area | Status |
| --- | --- |
| Project foundation / config / CLI | Working |
| 2026/27 rules engine | Working (verified 2026-08-15) |
| FPL adapters + team-state resolver | Working (offline fixtures + opt-in live smoke) |
| Projections v1 baseline | Working (unvalidated empirically) |
| Strategy / scenarios | Working (bounded beam; catalog-backed transfers still thin) |
| Rivals / news / monitor | Working (contracts + classifiers) |
| Decision ledger / replay | Working |
| OpenAI synthesis | Stub client + validation (live SDK optional) |
| Reports / publishing state machine | Working (GitHub mutations dry-run by default) |
| GitHub Actions | Scaffolded; full-season unattended blocked pending external watchdog |
| Evaluation gates | Partial — see `docs/evaluation-plan.md` |

## Quick start

```bash
# requires Python 3.12+
export PATH="$HOME/.local/bin:$PATH"
uv sync
uv run fpl-agent validate-config
uv run fpl-agent doctor
uv run pytest
uv run fpl-agent analyze --mode dry_run --offline
```

Copy `config/settings.example.yaml` and set your real `manager.team_id`. Sync private squad finance via `fpl-agent team-state validate PATH` (no FPL login).

## Non-negotiables

- Deterministic code owns rules, finance, projections, scenarios, and outcome replay.
- A language model may only rank/explain supplied validated candidates.
- Executable advice requires fresh reconciled team state.
- External web content is untrusted data.

See `docs/` and `outputs/cursor-prompts/` for the full build sequence.
