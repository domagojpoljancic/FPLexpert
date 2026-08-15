# Cursor Prompt 04 — Transparent Expected-Points and Uncertainty Model

Continue from Prompts 01–03. Do not use or refer to any old PRD.

This phase implements a deterministic, versioned baseline projection model. Do not call an LLM. Do not disguise arbitrary constants as validated football truth.

## First action

Run the current test suite and inspect the available normalized FPL fields and recorded fixtures. Write `docs/projection-methodology.md` before or alongside code so every calculation has a defined unit, source, and version.

If historical data needed for validation is not present, implement the interface and transparent baseline, add a data-import/backtest command, and mark empirical thresholds as unvalidated. Do not fabricate backtest results.

## Projection contract

For every player and future gameweek, output a versioned record containing at least:

- expected minutes;
- probability of starting, substitute appearance, and no appearance;
- conditional minutes for start and substitute states;
- expected FPL points;
- component contributions where supportable;
- lower/central/upper scenario or calibrated interval;
- availability, rotation, and postponement scenario identifiers;
- input source hashes, feature timestamp, model version, and warnings.

Use integer IDs and full-precision internal values; round only for display.

## Baseline methodology

Implement a documented, inspectable v1 method using the strongest available free/public inputs. It should include:

- long-term and recent minutes/start history with small samples shrunk toward team/position baselines;
- recent FPL performance without simply extrapolating last week's points;
- home/away and opponent-strength effects;
- team attacking and defensive strength proxies;
- blank and double gameweeks as zero or multiple fixture components, not special prose adjustments;
- current availability status and a structured news/minutes override interface for a later phase;
- current defensive-contribution potential by position, without double-counting official historic points;
- an optional projection-provider adapter disabled by default.

Avoid applying separate “rotation penalties” or “availability penalties” after expected minutes if those risks are already represented in the minutes distribution. Any additional penalty must represent a distinct outcome, use points as its unit, and be documented.

Do not use ownership as a base expected-points feature. Ownership belongs in later mini-league/risk decisions.

## Uncertainty

Model disputed availability through named scenarios, for example `available`, `limited`, and `out`, with explicit probabilities or user-configurable weights. Propagate these scenarios into player and squad projections.

Support sensitivity analysis that shows how a recommendation-relevant projection changes when:

- start probability moves within a defined range;
- an injury report is treated as resolved or unresolved;
- a fixture is postponed;
- a double-gameweek player starts one or both matches;
- an assumed set-piece role changes.

Do not claim confidence intervals are calibrated until a holdout evaluation proves coverage.

## Six-gameweek representation

Use the configured horizon and weights. Preserve unweighted expected points by gameweek and calculate weighted totals separately. The score must not hide the immediate hit cost; strategy will apply hit costs in the next phase.

Store enough information for the later decision ledger to reproduce each projection exactly from versioned inputs and configuration.

## Calibration and backtesting

Implement a deterministic backtest command operating on frozen historical fixtures. It must avoid future leakage: every prediction uses only data that would have been available before the corresponding deadline.

Calculate at least:

- player/gameweek MAE;
- signed bias;
- minutes/start probability Brier score or log loss;
- interval/scenario coverage when applicable;
- errors by position, price band, minutes-security band, home/away, and blank/double gameweek;
- sample size for every aggregate.

Store the dataset cutoff, code/model version, feature version, and result hash. Do not automatically tune strategic objective weights from one or a few gameweeks.

## Tests and acceptance criteria

Test:

- blank and double-gameweek aggregation;
- horizon weights and no rounding drift;
- small-sample shrinkage;
- minutes-state probabilities summing to one;
- postponed fixture behavior;
- uncertainty scenario propagation;
- no ownership input in base xP;
- no future data leakage in a constructed fixture;
- identical inputs/version producing identical outputs;
- documented handling of missing optional features.

This phase is accepted only when frozen inputs generate deterministic, component-auditable six-gameweek projections; every coefficient/default is documented; the backtest command works on a small fixture; and the documentation distinguishes implemented methodology, empirically validated behavior, and unvalidated assumptions. Finish with the standard checkpoint and stop.
