# reflection-v1 M4 — Cross-GW learning ledger + bounded adjustment proposals

Continue from M3. This is the "check how accurate past suggestions were and adjust the
algorithm for the future" part of the request — implemented as a transparent, sample-gated,
**proposal-only** loop. Nothing in this milestone is allowed to change a live projection number
automatically. Re-read `outputs/cursor-prompts/07_decision_ledger_and_retrospectives.md`'s
"Multi-gameweek decisions and lessons" section before starting — this milestone must not violate
it.

## First action

Run the full test suite. Confirm the `data/evaluation/reflection-gw*.json` cache from M1 is
still the right shape; if you extended it in M2/M3, re-read those diffs.

## Scope

1. Extend the M1 reflection payload to capture **per-player** predicted-vs-actual for the whole
   XI (not just the aggregate), tagged with position and a price tier — needed to compute bias
   by segment. Do this as an additive field, not a breaking change to the M1/M2/M3 shape.
2. A deterministic aggregator that computes calibration bias (mean predicted − actual) by
   segment across the accumulated history.
3. A minimum-sample, minimum-distinct-GW gate below which nothing is proposed — only an
   "observation" is surfaced (informational, explicitly not a lesson).
4. A narrow, leakage-free backtest that checks whether a proposed adjustment would have reduced
   error on strictly-prior GWs before it's shown as `backtested_pass`. If it fails, mark
   `backtested_fail` and show the failure plainly rather than hiding it.
5. Surface currently-live proposals in the detailed reflection section, clearly labeled as not
   yet applied.

## 1. Per-player predicted-vs-actual on the reflection payload

In `evaluation/reflection.py`, add to `ReflectionSummary` (or a nested object):

```python
@dataclass(frozen=True)
class PlayerCalibrationRow:
    player_id: int
    web_name: str
    position: str          # "GKP" | "DEF" | "MID" | "FWD"
    price_tier: str        # e.g. "budget" (<5.0), "mid" (5.0-8.0), "premium" (>8.0) — pick real
                            # breakpoints from the actual price distribution in bootstrap, not
                            # arbitrary guesses; document whatever you choose.
    predicted_xp: float
    actual_points: int
```

Populate one row per XI player (from `plan["xi"]`, matching predicted xp already on that row per
`daily.py:80-89`'s pattern, against `player_points` already fetched in `build_reflection`).
Persist alongside the existing fields in `data/evaluation/reflection-gw{N}.json`.

## 2. Calibration aggregator

New module `src/fpl_agent/evaluation/lessons.py`:

```python
def aggregate_calibration(history: list[ReflectionSummary]) -> dict[str, SegmentStats]:
    """Group all PlayerCalibrationRow entries across `history` by (position, price_tier).
    For each segment: sample_size, distinct_gameweeks, mean_bias (predicted - actual),
    mean_abs_error. Segments with 0 rows are omitted."""
```

## 3. Sample gate

```python
MIN_SAMPLE = 20          # rows
MIN_DISTINCT_GWS = 4     # distinct finalized gameweeks contributing those rows

def eligible_for_proposal(stats: SegmentStats) -> bool:
    return stats.sample_size >= MIN_SAMPLE and stats.distinct_gameweeks >= MIN_DISTINCT_GWS
```

Make both constants configurable via `config.py` (new `ReflectionSettings` or similar, following
the existing `CadenceSettings` pattern) rather than hardcoded, so the operator can tighten them
without a code change — but ship with these defaults, and do not lower them without the operator
explicitly asking.

Segments below the gate still appear in the reflection section, but only as a plain observation
("FWD mid-price projections have run high by ~0.6 pts across the 2 weeks measured so far — too
little history yet to propose an adjustment") — never as a `Lesson`.

## 4. Leakage-free backtest

```python
@dataclass(frozen=True)
class Lesson:
    lesson_id: str                    # stable hash of segment + proposal + as-of GW
    created_at: str
    as_of_gameweek: int               # last finalized GW included in the evidence
    segment: str                      # "{position}:{price_tier}"
    sample_size: int
    distinct_gameweeks: int
    observed_bias: float
    proposed_adjustment: dict[str, Any]  # e.g. {"target": "xp_multiplier", "segment": "FWD:mid", "factor": 0.94}
    backtest_status: str              # "pending" | "backtested_pass" | "backtested_fail"
    backtest_detail: str
    status: str                       # "proposed" | "rejected" | "expired" — never "applied" in v1
    review_after_gw: int
    expires_after_gw: int

def propose_adjustment(stats: SegmentStats, *, as_of_gameweek: int) -> Lesson | None:
    """Only returns a Lesson when eligible_for_proposal(stats) is True. The
    proposed_adjustment factor is a small, bounded shrink/boost toward 1.0
    (cap the factor within e.g. [0.85, 1.15] — never propose swinging a segment
    by more than 15% off its current output from one reflection cycle)."""

def backtest_adjustment(lesson: Lesson, history: list[ReflectionSummary]) -> Lesson:
    """Recompute mean_abs_error for that segment across `history`'s prior-to-as_of_gameweek
    rows twice: once with predicted_xp as-is, once with predicted_xp * proposed factor.
    Mark backtested_pass only if the adjusted MAE is strictly lower AND flipping the
    factor does not change which player would have been the picked transfer IN in any
    recorded also_considered comparison for that segment in the history (i.e. it must not
    have silently changed a real decision in hindsight) — otherwise backtested_fail with
    a specific reason string."""
```

Persist lessons **append-only** to `data/evaluation/lessons.jsonl` — one JSON object per line,
never rewritten in place. A later reflection cycle that wants to change a lesson's status writes
a **new** line referencing the same `lesson_id` with an updated `status`/`created_at`; the
"current" view is "the most recent line for each `lesson_id`," computed at read time, exactly
mirroring the decision ledger's correction-via-new-record pattern in `ledger.py`.

## 5. Surfacing in the report

In the detailed `## Reflection` section (extend `_reflection_section` / the M2/M3 module), add:

```
### Suggested adjustments for future reports (not applied automatically)

- **FWD (mid-price)**: projections have run ~0.6 pts high over 5 weeks (n=24). Proposed:
  shrink FWD mid-price xP by 6% for upcoming reports. Backtest: **pass** — would have cut mean
  error from 0.9 to 0.4 pts/GW over the same window without changing any recorded transfer
  pick. Not yet applied — needs an explicit config change and human sign-off.
```

Only list `status == "proposed"` (or `backtested_pass`) lessons whose `as_of_gameweek` matches
the current subject GW (avoid repeating a stale proposal verbatim every single week — if it's
still current, restate it plainly; if superseded by a newer lesson for the same segment, show
only the newest).

## Tests (`tests/unit/test_lessons.py`, new file)

- `aggregate_calibration`: correct grouping/means on synthetic multi-GW history.
- `eligible_for_proposal`: exact boundary behavior at `MIN_SAMPLE`/`MIN_DISTINCT_GWS`.
- `propose_adjustment`: returns `None` below threshold; returns a bounded factor within
  `[0.85, 1.15]` above threshold; factor moves in the correct direction relative to
  `observed_bias`'s sign.
- `backtest_adjustment`: constructs a synthetic history where the adjustment provably reduces
  MAE without changing any recorded pick → `backtested_pass`; a second synthetic history where
  it would have flipped a recorded `also_considered` comparison → `backtested_fail` with that
  reason.
- Append-only ledger: writing two lessons for the same `lesson_id` leaves the first line's bytes
  untouched (hash the file before/after the second write, or read the first line back
  explicitly) and both lines round-trip.
- Report rendering test: with a `backtested_pass` lesson present for the current GW, the section
  text is present and correctly labeled "not applied automatically"; with none eligible, the
  section shows only observations (or nothing) — never a false "applied" claim.

## Acceptance criteria

- `uv run pytest` passes in full.
- Grep the diff for this milestone: no line anywhere writes a `Lesson`'s `proposed_adjustment`
  into any code path that actually feeds `projections/preseason.py` or `strategy/transfers.py`.
  This must be verifiably true by inspection, not just by test coverage — search for any new
  import of `lessons.py` from either of those modules and reject the change if one exists.
- A `backtested_fail` case is rendered honestly (not hidden) if you choose to surface pending/failed
  attempts at all; if you decide v1 only surfaces `backtested_pass` + plain observations, say so
  explicitly in your checkpoint and confirm the tests match that choice.

Finish with the standard checkpoint and stop.
