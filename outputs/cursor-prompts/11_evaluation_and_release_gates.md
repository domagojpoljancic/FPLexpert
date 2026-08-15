# Cursor Prompt 11 — Adversarial Evaluation, Product Metrics, and Release Gates

Continue from Prompts 01–10. Do not use or refer to any old PRD.

Build the evaluation system that decides whether the product is safe and useful enough to advance. Do not weaken a gate merely to make the build green. If evidence is unavailable, mark the gate unproven and block the relevant release stage.

## First action

Run all tests and inventory current coverage against rules, data, projections, strategy, retrospectives, model behavior, security, publishing, and operations. Create `docs/evaluation-plan.md` with metric definitions, datasets, thresholds, ownership, and rollback rules.

## Test layers

Maintain distinct suites for:

- unit tests for pure rules, finance, projections, state transitions, and replay;
- contract tests for every observed FPL route and OpenAI schema;
- offline integration tests for daily, deadline, and review modes;
- golden football-decision and retrospective cases;
- prompt/model evaluations with repeated samples;
- security/adversarial tests;
- publishing/concurrency/recovery tests;
- opt-in live FPL, OpenAI, and GitHub smoke tests;
- workflow syntax/permission tests.

Frozen tests must be deterministic and runnable without network access. Live tests must be isolated, cheap, and never make an FPL change.

## Required adversarial cases

Create at least one automated or explicitly scripted test for each:

1. FPL route schema changes or is temporarily unavailable.
2. Public picks do not reveal the user's pre-deadline squad.
3. Bank, selling prices, free transfers, or chip instances are unknown.
4. A recommended transfer becomes unaffordable after a price change.
5. Conflicting injury reports appear shortly before the deadline.
6. A malicious source contains prompt-injection instructions.
7. A GitHub deadline workflow runs late or twice.
8. A fixture is postponed after the deadline.
9. A late injury, red card, or unexpected benching occurs.
10. The user ignores the recommendation or makes different transfers.
11. A transfer loses in week one but wins across its recorded six-gameweek horizon.
12. A good process produces a bad result through variance.
13. A poor process produces a lucky haul.
14. Official FPL points are corrected after the retrospective is published.
15. A blank/double gameweek changes the best chip plan.
16. OpenAI, web search, FPL, and GitHub publishing fail independently.
17. A new season changes transfer, chip, scoring, or settlement rules.
18. Repeated/overlapping runs try to create conflicting reports, commits, issues, or reviews.

Also include normal football cases: obvious roll, injury transfer, justified/unjustified hit, Wildcard structure repair, Free Hit, Bench Boost, Triple Captain, captain/vice/autosub, and mini-league chase/protect contexts.

## Hard safety gates

These must be 100% with no averaging:

- displayed executable squads, transfers, chips, lineups, and budgets are legal;
- official replay totals match deterministic expected fixtures exactly;
- model output conforms to schema and cannot alter deterministic values;
- no stale/unknown squad or critical finance is labeled executable;
- no original ex-ante record is overwritten;
- repeated logical runs create one canonical result;
- secrets are absent from logs, reports, commits, artifacts, snapshots, and exception messages;
- untrusted PRs cannot receive production secrets or write permissions;
- no code path authenticates to or modifies FPL.

A failure in any hard gate blocks private pilot and release.

## Projection and strategy evidence

On leakage-free holdout data:

- compare projection MAE/bias and minutes probability score with defined naive baselines;
- require sample sizes and segmented results;
- require the implemented baseline to beat or at least match the agreed naive baseline before claiming decision value;
- evaluate interval/scenario coverage before calling uncertainty calibrated;
- report hit, captaincy, and scenario ranking performance without optimizing on the evaluation set;
- preserve a season/version boundary so a new rules season cannot reuse a stale pass.

Do not choose an absolute MAE threshold without inspecting the data distribution. Record the threshold before evaluating the final candidate to prevent goalpost movement.

## Model-quality gates

Create a labeled rubric for:

- legal supplied scenario selection;
- numerical consistency;
- evidence and citation coverage;
- uncertainty preservation;
- six-gameweek awareness;
- hit break-even reasoning;
- hindsight discipline;
- process/outcome separation;
- root-cause attribution;
- actionability and brevity;
- repeated-run stability.

Required minimums:

- 100% legal/executable selection and numeric consistency;
- 100% of material current claims map to supplied source IDs;
- 100% hindsight-discipline pass on the dedicated cases;
- at least 90% of expert-labeled golden cases meet all critical rubric items;
- repeated runs choose the same primary scenario at least 90% of the time when one scenario has a material deterministic advantage; ties inside a documented tolerance may vary but must remain legal and transparently close;
- no evaluated fallback model is enabled until it passes the same hard gates.

Store evaluation date, model ID/returned model, prompt/schema version, repetitions, aggregate score, failures, and cost.

## Product success and noise metrics

Add a lightweight pilot feedback/evaluation record with predefined metrics:

- report arrives before the deadline safety floor;
- team-state freshness and executability are understood by the user;
- primary action, alternative, and trigger are comprehensible;
- recommendation-follow status is captured without pressure to follow;
- useful-report rating and reason;
- false/stale warning count;
- no-change Issue/comment count;
- user trust incidents, especially confident but incorrect data claims.

Set pilot targets before the pilot. Suggested starting targets, adjustable only with documented approval:

- zero stale-state executable recommendations;
- zero illegal/unaffordable executable recommendations;
- at least 95% of due deadline analyses complete before the safety floor during the pilot, with every miss alerted;
- at least 80% of sampled reports rated useful and understandable;
- zero comments for deterministic no-material-change daily runs;
- 100% of material current claims visibly sourced.

Do not use realized FPL points alone as the success metric.

## Objective release gates

### Build completion

- all hard safety gates pass;
- every 2026/27 rule has source and conformance coverage;
- all route/model assumptions are registered with fallback behavior;
- clean install, lint, type check, unit, contract, and offline integration suites pass.

### Dry-run readiness

- all 18 adversarial scenarios have expected results;
- deterministic daily/deadline/review runs work offline;
- concurrency, partial publishing, and recovery drills pass;
- live smoke tests verify configured account/repository access;
- cost estimator is within a documented tolerance of recorded API usage.

### Private pilot

- hard gates remain at 100%;
- three consecutive live gameweeks meet freshness/finality requirements;
- every due run is timely or produces a visible alert;
- user product metrics meet the predefined pilot targets;
- rollback has been exercised.

### Full-season unattended operation

- at least eight consecutive live gameweeks meet the timeliness/freshness SLO;
- independent liveness monitoring detects a deliberately dropped/disabled primary schedule;
- rule drift, FPL schema drift, OpenAI failure, GitHub partial publish, official correction, and restore drills pass;
- the system can rebuild canonical reports from ledgers, manifests, source fixtures, and versioned code/configuration;
- season rollover fails closed until the new manifest is reviewed.

## Rollback

Define rollback triggers for any hard safety failure, repeated missed deadline, source/projection regression, model-eval regression, unexplained cost increase, or publishing inconsistency. Rollback must disable recommendation/publishing safely while retaining immutable history and allowing deterministic diagnostics.

## Acceptance criteria

This phase is accepted only when the evaluation command produces a machine-readable and human-readable gate report, every gate has evidence, failure blocks advancement automatically where feasible, and rollback has a tested command/runbook. Finish with the standard checkpoint and stop.
