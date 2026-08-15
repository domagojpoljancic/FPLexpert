# Cursor Prompt 12 — Final Integration Audit and Build-Ready Handoff

Continue from Prompts 01–11. Do not use or refer to any old PRD. The repository, current prompt pack requirements, current primary-source assumptions, and implemented tests are the source of truth.

Perform an adversarial end-to-end audit, fix in-scope defects, and produce an evidence-backed handoff. Do not declare the system complete merely because the repository is detailed or the test suite is large.

## First action

Inspect the full repository and current working-tree state. Preserve unrelated user changes. Run the fastest foundational checks first, then the full offline suite. Inventory unfinished markers such as `TODO`, `FIXME`, placeholder values, skipped tests, expected failures, unimplemented CLI paths, permissive schemas, and undocumented defaults.

Do not enable a feature whose acceptance gate is unproven. It is acceptable to leave full-season unattended mode explicitly blocked; it is not acceptable to imply it is ready.

## Traceability audit

Create a concise traceability matrix mapping each product requirement to:

- implementation module;
- deterministic or model owner;
- test/evaluation evidence;
- failure/degradation behavior;
- operational owner/runbook;
- release gate status.

Cover:

- current-team ingestion and synchronization;
- public/observed FPL route behavior and schema drift;
- squad, budget, selling price, free transfers, hits, formation, lineup, captaincy, autosubs, and both chip sets;
- fixtures, blanks/doubles, injury, suspension, rotation, postponement, and price changes;
- six-gameweek projections and uncertainty;
- scenario search and justified hits;
- rival analysis and moderately aggressive policy;
- daily monitoring and deadline analysis;
- immutable ex-ante decisions and deterministic retrospectives;
- actual versus recommended versus roll versus recorded alternatives;
- multi-gameweek decision horizons and lessons;
- OpenAI structured synthesis, web-search citations, model policy, and cost controls;
- Markdown/GitHub publishing and correction history;
- GitHub Actions without an always-on app server;
- security, observability, recovery, testing, and release gates.

## Cross-component invariants

Verify and add missing tests for these invariants:

- one `SeasonRules` version flows through ingestion, strategy, replay, and reports;
- one player/catalog identity system is used everywhere;
- every recommendation links to exact team-state, projection, source, scenario, and rules hashes;
- every report links to an immutable decision/outcome record;
- no model-generated value becomes deterministic truth;
- conditional-only analysis cannot be rendered or published as executable;
- every official correction creates a new version without rewriting history;
- every publisher retry resumes the same prepared bundle;
- stale delayed runs cannot replace newer canonical results;
- dry run performs no GitHub mutation and no FPL mutation exists in any mode;
- model/news/publisher failure still yields the designed safe result;
- all user-visible current claims have visible sources.

## Current-assumption recheck

Re-run the documented current checks for:

- 2026/27 FPL rules and chip windows;
- live FPL route contracts;
- official result finality;
- GitHub scheduling, concurrency, token permissions, and inactivity behavior;
- OpenAI models, Responses API features, structured outputs, web search, and pricing.

Update the assumptions register. A material difference must trigger the existing fail-closed behavior and a clear blocker, not an improvised patch that bypasses review.

## End-to-end drills

Run offline end-to-end fixtures for:

1. normal fresh deadline recommendation;
2. stale private squad blocking advice;
3. unknown finance producing conditional-only analysis;
4. conflicting injury news producing sensitivity paths;
5. price change invalidating affordability;
6. blank/double gameweek changing chip plan;
7. OpenAI failure using deterministic fallback;
8. duplicate and delayed publishers converging;
9. user action differing from recommendation;
10. good process/bad outcome and poor process/lucky outcome;
11. a six-gameweek transfer thesis remaining open;
12. official point correction creating a new review version.

Where credentials and explicit test configuration exist, run opt-in live smoke tests for FPL, OpenAI, GitHub dry-run/publishing in a safe test target, and GitHub-hosted execution independent of the laptop. Never publish into the user's real gameweek Issue without explicit publish configuration.

## README and operator experience

Make the README usable by a new technical user. It must include:

- architecture and safety boundary;
- installation from the lockfile;
- configuration reference;
- local private team-state preparation and validation;
- offline dry run;
- GitHub variables, secrets, permissions, and Actions setup;
- how scheduled cloud runs continue while the laptop is off;
- how to verify the last successful run and deadline freshness;
- cost controls;
- manual fallback before a deadline;
- recovery, rollback, key rotation, rule/schema drift, and season rollover;
- current limitations, especially public pre-deadline state and GitHub schedule punctuality.

Do not instruct the user to commit secrets or private raw state.

## Final gate report

Run the evaluation command from Prompt 11 and produce:

- exact commands/checks run;
- test counts and skipped-test reasons;
- hard-gate results;
- current dry-run, private-pilot, and full-season-unattended status;
- unresolved blockers ranked P0–P3;
- current monthly cost estimate with source/check date;
- operational next actions in order.

No unresolved P0/P1, hard-gate failure, or unknown critical team-state path may coexist with `pilot-ready`. Full-season unattended operation requires the independent liveness monitor drill; ordinary GitHub scheduling alone is insufficient.

## Acceptance criteria

This prompt is complete only when:

- all in-scope defects found by the audit are fixed and tested;
- the full offline test/evaluation suite passes or the exact blocker is documented;
- the traceability matrix has no silent requirement gaps;
- setup from a clean checkout to local dry run is reproducible;
- GitHub-hosted operation is clearly distinguished from local Cursor work;
- the final status is evidence-based and does not overclaim readiness.

End with the standard checkpoint plus the final gate report. Do not begin an unrelated v2 feature.
