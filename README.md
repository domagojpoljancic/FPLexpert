# FPL Decision-Support Agent

WIP read-only Fantasy Premier League decision-support system. It recommends transfers, hits, lineups, captains, bench order, and chips — **you** always make the FPL changes. It never logs into FPL or mutates a team.

## Status

| Area | Status |
| --- | --- |
| Project foundation / config / CLI | Working |
| 2026/27 rules engine | Working (verified 2026-08-15) |
| FPL adapters + team-state resolver | Working (offline fixtures + opt-in live smoke) |
| Projections v1 baseline | Working (unvalidated empirically) |
| Preseason projections + initial squad optimiser | Working (`suggest-squad`, exact XI knapsack) |
| Strategy / scenarios | Working (bounded beam; catalog-backed transfers still thin) |
| Rivals / news / monitor | Working (contracts + classifiers) |
| Decision ledger / replay | Working |
| OpenAI synthesis | Live Responses client on **pre-deadline** review (`predeadline`); needs `OPENAI_API_KEY` for web/Reddit search |
| Daily price watch | Working (uncalibrated) — GitHub `fpl-prices.yml` + local `daily` / `prices`; Issue email on act-now; no Hub scrape |
| Reports / publishing state machine | Working (GitHub mutations dry-run by default) |
| GitHub Actions | **Prices** scheduled (`fpl-prices.yml`); emails via a standing GitHub Issue. Pre-deadline is **manual** (phone Cloud Agent). Independent watchdog ping still TBD |
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

# Suggest a legal 15-player squad for the next gameweek
uv run fpl-agent suggest-squad

# Daily price watch (no OpenAI)
uv run fpl-agent daily --offline

# Full news/squad review ~1 day before the GW deadline
uv run fpl-agent predeadline --offline
# (use --force to run the full review outside that window)
```

Copy `config/settings.example.yaml` and set your real `manager.team_id`. Sync private squad finance via `fpl-agent team-state validate PATH` (no FPL login).

## Overnight prices (GitHub)

1. Repo secret `FPL_PRIVATE_STATE_B64` (encode with `uv run fpl-agent team-state encode-for-github PATH`). Re-set it after you change your squad.
2. **Watch** the GitHub repo (or the standing issue **FPL price alerts**) with email notifications on. You get mail only when the job thinks you should act tonight — not every quiet snapshot.
3. Workflow `.github/workflows/fpl-prices.yml` runs once at **21:00 Europe/Zagreb** in summer (19:00 UTC). GitHub can skip or run late; this is not a promise it will beat FPL’s overnight job.
4. After each real run, open **Actions → fpl-prices → that run** — the Summary tab shows the report. A line is also appended to [`run-log.md`](run-log.md) on `main`.

## Pre-deadline from your phone

About a day before the official GW deadline:

1. In the Cursor mobile app, start a **Cloud Agent** on this repo (not a local session on a sleeping laptop).
2. Cloud Agent secrets/env: `OPENAI_API_KEY` and `FPL_PRIVATE_STATE_B64`. Environment should have Python 3.12 and `uv`.
3. Prompt: `Run the pre-deadline review.` The project rule will run `team-state materialize-from-env` then `fpl-agent predeadline --live-ai`.
4. Leave Cursor’s model on Auto. OpenAI is used inside that CLI command, not as the Cursor picker.
5. You still make the transfers in the FPL app.

Fallback: GitHub → Actions → **fpl-prices** → Run workflow is prices only. Pre-deadline stays a Cloud Agent (or a local `uv run fpl-agent predeadline --live-ai`).

## Non-negotiables

- Deterministic code owns rules, finance, projections, scenarios, and outcome replay.
- A language model may only rank/explain supplied validated candidates.
- Executable advice requires fresh reconciled team state.
- External web content is untrusted data.

See `docs/` and `outputs/cursor-prompts/` for the full build sequence.
