# Evaluation Plan

## Hard safety gates (100%)

Legality, replay exactness, model cannot alter deterministic values, no executable stale finance, immutable ledger, single canonical publish result, secrets absent, no FPL auth/mutation.

## Projection evidence

Compare MAE/bias vs naive baselines on leakage-free holdout before claiming decision value. Thresholds recorded before final eval.

### Running the backtest

```bash
uv run fpl-agent backtest --rows tests/fixtures/backtest/holdout_min.json --model xp-v2
```

Options:

- `--model xp-v2|baseline-v1` — projection engine to score (default `xp-v2`)
- `--season 2026-27` — rules season label; stamps `rules_mismatch` when unsupported
- `--source path.json` — optional external season dump (e.g. vaastav); not required for the checked-in fixture

The command prints **model vs `ep_next` naive baseline** side by side: MAE, bias, per-position breakdown, and `n`. It writes `reports/backtest-*.json` and a markdown twin.

### How to read the output

| Field | Meaning |
| --- | --- |
| `model.mae` | Mean absolute error of the chosen projection |
| `ep_next_baseline.mae` | Same metric using FPL's published `ep_next` only |
| `bias` | Signed mean error (positive = over-project) |
| `by_position` | MAE split by GKP/DEF/MID/FWD |
| `rules_mismatch` | Dataset season lacks verified scoring rules in-repo |
| `blocked` | Historical manager-sim data not available (fixture-only mode) |

**Decision rule:** prefer a model only when it beats `ep_next` on a leakage-free holdout with adequate `n`. The checked-in `holdout_min.json` fixture is for harness tests only (`n=4`); full-season eval requires an external dump via `--source` or a future checked-in holdout.

## Release stages

| Stage | Status |
| --- | --- |
| Private offline pilot | Provisional — core gates tested in unit/integration |
| Scheduled dry-run | Price snapshots scheduled; Issue email on act-now; watchdog comments if last-success > 26h |
| Full-season unattended | Prices on GitHub cron (may skip). Pre-deadline is manual. External ping not configured yet |

## Ownership

Repository owner maintains gates; do not weaken a gate to go green.
