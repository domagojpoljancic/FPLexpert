# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

## Projection evidence

The agent optimises **forward-looking** expected points (xP) for upcoming gameweeks. We do not run historical backtests in this repo — advice is judged on whether the next GW plan is sensible given fixtures, minutes, and your squad, not on replaying past seasons.

After each deadline, use `fpl-agent scorecard` and `fpl-agent replay` to compare what we recommended vs what actually happened (process vs luck), one gameweek at a time.

## Reflection / retrospective (reflection-v1)

Each predeadline report reflects on the most recently *finalized* gameweek (never a provisional one) — recommended transfer vs actual outcome, captain call, process/outcome grade, and a short "what could've been done better" line sourced only from recorded `also_considered` alternatives (or the saved captain). Prior-GW machine plans are persisted under `data/plans/gw{N}-weekly-plan.json` (git-tracked) so reflection works on a fresh checkout without local `reports/*.json`.

The detailed section charts predicted-vs-actual XI calibration and transfer payoff trends from `data/evaluation/reflection-gw*.json` history, surfaces sample-gated calibration lessons, and tracks how locked transfers age across their original horizon via versioned transfer theses.

**Live learning:** when enabled (default), (1) `backtested_pass` segment lessons multiply this week's projections by `position:price_tier`, and (2) prior-GW transfer alternatives that beat the pick get a bounded projection boost (the missed pick is gently dampened). Notes appear under **This week → Learning from prior GW**. Still no historical backtest of projection *ranking* against past seasons.

## Release stages

| Stage | Status |
| --- | --- |
| Private offline pilot | Provisional — core gates tested in unit/integration |
| Scheduled dry-run | Price snapshots scheduled; Issue email on act-now; watchdog comments if last-success > 26h |
| Full-season unattended | Prices on GitHub cron (may skip). Pre-deadline is manual. External ping not configured yet |

## Ownership

Repository owner maintains gates; do not weaken a gate to go green.
