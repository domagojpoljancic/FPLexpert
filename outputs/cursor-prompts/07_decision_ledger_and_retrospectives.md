# Cursor Prompt 07 — Immutable Decision Ledger and Fair Retrospectives

Continue from Prompts 01–06. Do not use or refer to any old PRD.

Implement the immutable ex-ante record, official result ingestion, deterministic replay, rolling multi-gameweek evaluation, and correction behavior. Do not call an LLM and do not use perfect hindsight as the primary evaluation.

## First action

Run all tests. Review the rules engine's official-point replay, run-manifest types, scenario outputs, source hashes, and current official 2026/27 result-lock behavior.

For 2026/27, official FPL guidance says scores remain provisional until 09:00 UK time on the day after the final match of the gameweek. Implement this through season-specific finality policy plus observed event metadata such as `data_checked`, not a fixed six-hour delay. If current official guidance has changed, record the verified replacement.

## Immutable pre-deadline decision record

Before any deadline report is published, atomically create a machine-readable record under a structure equivalent to:

```text
data/decision-ledger/{season}/gw-{NN}/{decision_id}.json
```

The record must include:

- season, gameweek, official deadline, generation time, and data cutoff;
- content-addressed decision ID and schema version;
- resolved team state with per-field provenance, freshness, and executability status;
- `SeasonRules`, player catalog, prices, fixtures, projection, news, rival, configuration, code, and prompt/model version hashes as applicable;
- roll/no-transfer baseline;
- primary recommendation when one exists;
- every displayed alternative and its original search/legality evidence;
- projected points by gameweek, uncertainty/sensitivity paths, hit, bank, free transfers, chip instance, XI, bench, captain, and vice;
- source records, assumptions, warnings, and trigger conditions;
- a hash linking the record to the eventual rendered report.

Do not overwrite a pre-deadline record after its deadline. Corrections or regenerated analyses must be separate, timestamped records that link to the original and retain its hash. Mark one record canonical through a manifest; never rewrite history to imply a different recommendation.

## Actual action reconstruction

After the deadline, reconstruct only what public post-deadline data proves:

- transfers and transfer cost;
- chip used;
- starting XI, bench order, captain, and vice;
- autosubs and official manager points;
- rank and mini-league movement when available.

If actual user action cannot be recovered, mark it unknown. Never assume the user followed the agent.

## Official result finality

The canonical review preflight must require:

- all relevant fixtures complete;
- the official gameweek finality/lock condition for the active season;
- successful retrieval and hashing of official per-player points and manager outcome data.

Before finality, a run may create a clearly provisional preview but not the canonical retrospective. When official result hashes later change, append a corrected outcome/review version, retain the prior version, and recompute affected aggregates.

## Deterministic counterfactual replay

Use official per-player FPL points as immutable inputs and apply recorded lineup, bench, captain, chip, autosub, and hit rules deterministically. Replay only scenarios that were recorded as legal/conditional before the deadline; conditional scenarios must be included only when their required conditions are proven to have held.

Compute:

- actual manager net score when observable;
- actual gross lineup/squad components and hit cost;
- realized primary recommendation score;
- realized roll/no-transfer score;
- realized score of every valid recorded alternative;
- transfer in-versus-out delta, net of hit, for the latest week and cumulatively through the original horizon;
- captaincy delta versus recorded captain alternatives;
- lineup/bench/autosub delta where attribution is valid;
- chip delta versus the recorded no-chip path where comparable;
- projection error, MAE, bias, and sample size.

Do not select an unrecorded hindsight player and call those “missed points.” An optional perfect-hindsight oracle may exist only as `diagnostic_only`, behind a disabled-by-default setting, with a precisely defined player pool, price, transfer, and information constraint. It must never grade process or change policy automatically.

## Process versus outcome

Every reviewed decision gets two independent labels:

- process quality: `good`, `mixed`, `poor`, or `insufficient_evidence`, using only pre-deadline information;
- outcome quality: `positive`, `neutral`, or `negative`, using realized results.

Use closed root-cause enums:

- `sound_process_normal_variance`;
- `projection_or_minutes_miss`;
- `news_or_data_freshness_miss`;
- `scenario_generation_gap`;
- `ranking_or_reasoning_miss`;
- `rules_or_calculation_bug`;
- `user_execution_difference`;
- `unavoidable_late_event`;
- `insufficient_evidence`.

The deterministic layer should calculate evidence features and rule/calculation facts. A later LLM may explain or propose a classification but may not alter numeric results.

## Multi-gameweek decisions and lessons

Keep a transfer/chip thesis open for its original horizon. Update `latest_gw_delta` and `cumulative_horizon_delta` each week. Close only when the recorded horizon ends, the relevant player is sold/plan invalidated, or a documented terminal condition occurs. Avoid double-counting overlapping decisions in rolling summaries.

Lessons must link to decision IDs, evidence, confidence, and review/expiry date, and propose a bounded reversible adjustment. Never change objective weights, risk profile, hit cap, or chip rules automatically. Default v1 behavior is proposal-only. Require a configured sample minimum and a documented leakage-free backtest before applying any numeric projection adjustment.

## Tests and acceptance criteria

Test:

- decision record immutability after the deadline;
- stable content hashes and report linkage;
- unknown actual action;
- exact captain, vice, bench, autosub, hit, Bench Boost, and Triple Captain replays;
- conditional alternative included/excluded based on proven conditions;
- good process/bad outcome and poor process/lucky outcome;
- a transfer losing in week one and winning over six weeks;
- overlapping open decisions without aggregate double-counting;
- provisional result refusing canonical review;
- official correction creating a new version and recomputed aggregates;
- missing decision record producing a limited factual review without invented counterfactuals.

This phase is accepted only when frozen fixtures exactly reproduce official manager totals, the original pre-deadline record cannot be mutated, primary comparisons use recorded ex-ante alternatives, and multi-week decisions remain open through their original horizon. Finish with the standard checkpoint and stop.
