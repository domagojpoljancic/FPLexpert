# reflection-v1 M2 — Wire the reflection into the real predeadline report

Continue from M1. `evaluation/reflection.py` (`reflection_gate`, `build_reflection`,
`ReflectionSummary`) must exist and be tested before starting this.

## First action

Run the full test suite. Re-read `daily.py:151-210` (`run_predeadline`) and `daily.py:1348-1411`
(`render_daily_text`) to confirm the section order and splice points from `INVENTORY.md` still
hold. Re-read `daily.py:1414-1424` (`write_daily_artifact`) to see where the JSON report is
written, since the reflection payload needs to land there too.

## Scope

1. Compute the reflection once per `run_predeadline` call (not once per render) and attach it to
   `DailyReport`.
2. Render a **short** line near the top of the markdown (next to the existing `Plan:`/`AI:`
   lines) and a **detailed** `## Reflection: how last week's advice did` section further down —
   both entirely absent when the gate says skip.
3. Include the same data in the saved JSON report so downstream tooling (M4/M5, and the existing
   `fpl-agent scorecard`) can consume it without re-deriving it.

## 1. `DailyReport` and `run_predeadline`

In `daily.py`:

- Add a field to `DailyReport` (near `weekly_plan`, `daily.py:63`):
  `reflection: dict[str, Any] | None = field(default_factory=lambda: None)`. Store the
  `ReflectionSummary` as a plain dict (`asdict`/`model_dump`) so `asdict(report)` (used at
  `write_daily_artifact`, `daily.py:1420`) serializes it for free.
- In `run_predeadline`, right after `bootstrap, fixtures = load_public_data(...)` and
  `gw, deadline = next_deadline(bootstrap)` (`daily.py:166-167`), call:

  ```python
  from fpl_agent.evaluation.reflection import build_reflection, reflection_gate

  subject_gw, finality_status = reflection_gate(bootstrap, fixtures)
  reflection = (
      build_reflection(gameweek=subject_gw, reports_dir=reports_dir, bootstrap=bootstrap)
      if finality_status == GwFinality.FINAL
      else None
  )
  ```

  Wrap this in a broad `try/except Exception` that logs (via whatever this module already uses
  for warnings — check `observability.py`) and falls back to `reflection = None`. **A reflection
  failure must never fail or change the substance of the predeadline run.**
- Pass `reflection=reflection.as_dict() if reflection else None` into every `DailyReport(...)`
  construction path that reaches the "normal" (non-early-return, non-skipped) case. The early
  `not allowed` return (`daily.py:170-188`, before the deadline gate even opens) does not need a
  reflection — leave it `None` there; that path already produces its own short-circuited report.

## 2. Rendering — short line

In `render_daily_text` (`daily.py:1348` onward), after the existing header block
(`daily.py:1370-1376`: `# Pre-deadline…`, `Plan:`, `_ai_line`, optional `Price:`) and before
`## Do this`:

```python
if report.reflection and report.reflection.get("short_summary"):
    lines.append(report.reflection["short_summary"])
```

No heading — it reads as one more header line, consistent with how `Price:` is conditionally
appended today (`daily.py:1375-1376`). When `report.reflection` is falsy, this block contributes
nothing — no blank line artifact, no placeholder text.

## 3. Rendering — detailed section

Add a new section between `## Watch` (`daily.py:1403-1409`) and `## Sources`
(`daily.py:1410`), guarded the same way:

```python
if report.reflection:
    lines += ["", *_reflection_section(report.reflection)]
```

New helper `_reflection_section(reflection: dict[str, Any]) -> list[str]` in `daily.py` (keep it
next to `_sources_section`/`_weekly_plan_section` for consistency; move it into
`reporting/reflection_section.py` in M3 once charts are added, if that keeps `daily.py` from
growing past a reasonable size — your call, but do not duplicate logic across both places).
Minimum content for M2 (M3 adds charts on top of this):

```
## Reflection: how last week's advice did

<detail_summary prose>

| | Predicted | Actual |
| --- | ---: | ---: |
| XI points | {predicted_xi_xp} | {actual_xi_points} |
| Captain ({model_captain_name}) | {predicted captain xp *2} | {model_captain_points} |
| {transfer_out_name} → {transfer_in_name} | +{transfer_predicted_delta} | +{transfer_actual_delta} |

Process: **{process_quality}** · Outcome: **{outcome_quality}** ({root_cause, in plain language})

{what_could_have_been_better}
```

Keep every number sourced from `reflection` verbatim — this function formats, it does not
compute.

## 4. Skip behavior — the hard requirement

When `reflection_gate` returns anything other than `FINAL` (mid-gameweek, provisional, unknown,
not-applicable, or `build_reflection` itself returned `None`):

- The rendered markdown must contain **zero** occurrences of the word "Reflection" and zero
  occurrences of the short-summary line.
- The JSON report's `reflection` key must be `null`/absent-equivalent.
- No warning should be added about this — silently skipping is the correct, expected behavior,
  not a degraded state. (Contrast with e.g. `news_search_empty`, which *is* surfaced as a
  warning today — reflection-skipped is not analogous; do not add it to the `hide` set at
  `daily.py:1366-1367` by mistake, it should simply never be present.)

## Tests

Extend `tests/unit/test_daily.py`:

- Mid-gameweek fixture (some fixture for `subject_gw` unfinished) → rendered text has no
  "Reflection" anywhere, JSON `reflection` is `None`.
- Final + a saved prior-GW plan + live points fixture present → rendered text contains the short
  header line and the `## Reflection` section with the expected numbers (golden-style assertion
  on key substrings/values, not full-string equality, to stay resilient to prose tweaks).
- `build_reflection` raising internally (monkeypatch it to raise) → `run_predeadline` still
  returns a normal, non-erroring `DailyReport` with `reflection=None` and unrelated sections
  (`## Do this`, `## Why`, …) unchanged from before this milestone.
- GW1 (no prior GW) → `reflection=None`, no crash.

Also run the **existing** predeadline/report tests (`test_daily.py`, `test_plan_doc.py`,
`test_cli.py`) to confirm nothing about the pre-existing report content shifted — reflection must
be strictly additive, appended at the two specified splice points and nowhere else.

## README / docs note (do this now, not deferred to M6)

Per this repo's own habit of keeping `README.md` matching current reality: once this milestone
actually changes what a real report looks like, add one short bullet under "What you get" in
`README.md` describing the new reflection section (one line — mirror the existing bullet style
at `README.md`'s "### What you get" list). Do not describe M3–M5 capabilities (charts, learning
loop, transfer-thesis tracking) until those milestones actually ship — keep the README claim
scoped to exactly what M2 shipped.

## Acceptance criteria

- `uv run pytest` passes in full.
- A manually triggered `uv run fpl-agent predeadline --offline` (or `--live-ai` if credentials
  are available) against a state where the prior GW is genuinely final shows the new section;
  against a state where it isn't, the section is fully absent. Paste both outcomes into your
  checkpoint.
- No change to `## Do this`, `## This week`, `## Why`, `## Watch`, `## Sources`, or the
  transfer/lineup/captain recommendation itself, for either code path.

Finish with the standard checkpoint and stop.
