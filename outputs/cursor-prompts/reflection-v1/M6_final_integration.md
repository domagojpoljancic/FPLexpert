# reflection-v1 M6 — Final integration, docs, and README truth-check

Continue from M5. All of M1–M5 should be merged/implemented before this milestone.

## First action

Run the full test suite (`uv run pytest`) and note the total test count and pass/fail split.
Run `uv run fpl-agent predeadline --offline` (or `--live-ai`) at least twice in a row, the same
way a real user would (matching the many-reruns pattern already visible in `reports/`), to
confirm reflection content is stable and idempotent across reruns within the same window.

## Scope

1. Full-suite pass, including a real end-to-end run against whatever data is available in this
   environment (offline fixtures at minimum; live if `OPENAI_API_KEY`/network access permits).
2. Docs updated to match what actually shipped — no aspirational claims.
3. `README.md` bullet(s) finalized (M2 added a first cut; confirm it still matches the shipped
   behavior after M3–M5, and add short mentions of the charts / past-transfer table / adjustment
   proposals if those are now real).
4. A short retro on this plan itself: note anywhere the implementation deviated from
   `INVENTORY.md`'s assumptions, so the next person doesn't trust stale file:line citations.

## 1. Docs

`docs/evaluation-plan.md`: add a subsection, e.g.:

```
## Reflection / retrospective (reflection-v1)

Each predeadline report now reflects on the most recently *finalized* gameweek (never a
provisional one) — recommended transfer vs actual outcome, captain call, process/outcome grade,
and a short "what could've been done better" line sourced only from recorded alternatives.
Still no historical backtest of the projection *ranking* against past seasons. reflection-v1
adds one narrow, sample-gated backtest solely to validate proposed *calibration* adjustments
(e.g. "FWD mid-price projections have run high") before they're even surfaced as a proposal —
this never changes production numbers automatically; applying a proposal requires a separate,
explicit, human-approved change.
```

Adjust the wording to match whatever was actually built if M4/M5 ended up scoped differently
than planned — this doc must describe reality, not this plan's intent.

`docs/assumptions-register.md`: if M1's finality-gate implementation had to deviate from the
09:00-UK-next-day + `data_checked` policy (e.g. FPL's API shape differs from what
`rules/season.py:143-146` assumed), record the verified replacement here, per this repo's
existing convention for assumption changes.

## 2. README

Confirm/finalize the "What you get" bullet(s) added across M2–M5. Keep it terse, consistent with
the existing bullet style (see `README.md`'s current "### What you get" list). Do not add a
"WIP" banner — this repo's README doesn't use one, and reflection-v1 should read as a normal
shipped capability once M1–M5 are actually merged, gated correctly, and tested.

If this repo's README "Latest results" auto-refresh block
(`<!-- recent-runs:start -->` / `<!-- recent-runs:end -->`, populated by
`reporting/readme_index.py` per the grep hits found during `INVENTORY.md`'s research) would
benefit from also surfacing the reflection short-summary line next to each predeadline entry,
propose that as a small follow-up here — implement it only if it's a low-risk, additive change
to `readme_index.py`; otherwise leave it as a noted opportunity for a future turn rather than
scope-creeping this milestone.

## 3. Regression sweep

- Confirm `fpl-agent scorecard` (the pre-existing standalone command) still works unmodified —
  reflection-v1 must not have repurposed or broken it.
- Confirm `fpl-agent replay` still works unmodified.
- Confirm the season-plan doc (`reports/plan-gw{N}.md` via `plan_doc.py`) is unchanged in content
  and still gets written by `write_daily_artifact` — reflection content must be a strict addition
  to the predeadline report, not a fork of the season-plan doc.
- Confirm the automation workflows referenced in `README.md`'s "### Automation" section
  (`fpl-prices.yml`, `fpl-prices-watchdog.yml`) are untouched — reflection-v1 is entirely inside
  the predeadline path, never the nightly price-watch path.

## Acceptance criteria

- `uv run pytest` green, full suite, with the new test files from M1–M5 all present and passing.
- A real (or offline-fixture) predeadline run, executed twice in the same window, produces
  byte-for-byte-stable reflection content between the two runs for any GW whose underlying data
  didn't change (no nondeterminism — no unseeded randomness, no wall-clock-dependent text baked
  into a "final" GW's numbers).
- `README.md` and `docs/evaluation-plan.md` describe exactly what shipped — re-read both against
  the actual current code once more before finishing, the same way `INVENTORY.md` was built
  against real file:line citations rather than assumptions.
- A closing checkpoint that explicitly states: total milestones completed (should be all of
  M1–M6), any milestone whose scope changed from this plan and why, and any follow-up ideas
  intentionally deferred (e.g. the README "Latest results" enrichment above, or promoting a
  `backtested_pass` lesson to an actual applied adjustment in a future, separate plan).

This is the last file in the pack. No further milestone to hand off after this one.
