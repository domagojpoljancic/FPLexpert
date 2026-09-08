# reflection-v1 M3 — Charts for the detailed reflection section

Continue from M2. The `## Reflection` section must already exist and be gated correctly before
starting this.

## First action

Run the full test suite. Re-read `reporting/plan_doc.py`'s Mermaid helpers (search for
`_mermaid_` in that file) to copy the existing conventions — chart title casing, axis label
style, `xychart-beta` usage — rather than inventing a new visual language for this one section.

## Scope

Add two small Mermaid charts to the detailed reflection section, using the **history** of
already-computed `data/evaluation/reflection-gw*.json` files from M1 (do not refetch live points
per historical GW on every predeadline run — read the cached files):

1. **Calibration trend** — predicted XI xP vs actual XI points, one line each, over the last up
   to 6 finalized gameweeks (rolling window, oldest to newest, ending at the subject GW).
2. **Transfer payoff trend** — actual points delta (IN − OUT) of the recommended transfer, per
   finalized GW that had a transfer recommendation, over the same window. Weeks with no
   transfer recommended (a genuine "hold" week) are simply omitted from this series, not
   plotted as zero — zero would misleadingly read as "transfer that flopped."

## Implementation

New module `src/fpl_agent/reporting/reflection_charts.py` (keep chart-building out of
`daily.py`, matching how `plan_doc.py` already keeps season-plan charts separate):

```python
def load_reflection_history(root: Path, *, through_gameweek: int, max_gws: int = 6) -> list[ReflectionSummary]:
    """Read data/evaluation/reflection-gw{N}.json for the last up to max_gws GWs
    ending at through_gameweek, oldest first, skipping any GW with no cached file."""

def mermaid_calibration_trend(history: list[ReflectionSummary]) -> str | None:
    """xychart-beta with two lines (predicted, actual). Returns None if fewer than 2
    GWs have both values available — a 1-point chart is not a trend."""

def mermaid_transfer_payoff_trend(history: list[ReflectionSummary]) -> str | None:
    """xychart-beta bar chart of transfer_actual_delta per GW that had a recommended
    transfer. Returns None if fewer than 2 such GWs exist in the window."""
```

Wire both into `_reflection_section` (from M2): call `load_reflection_history` using the
subject GW from the current `reflection` payload, append whichever chart functions return a
non-`None` string, and when a chart is skipped for lack of history, add a single explanatory
line instead (e.g. "Not enough finalized weeks yet to chart a trend.") — never an empty heading
with nothing under it.

Follow the exact Mermaid syntax already proven to render in this repo's reports (see
`reports/plan-gw3.md` for a working `xychart-beta` example with two `line` series). For the bar
chart, confirm current Mermaid `xychart-beta` bar syntax against the pinned/observed Mermaid
version this repo's GitHub rendering actually uses (check how GitHub renders existing
`reports/plan-gw*.md` charts today, or check `pyproject.toml`/CI for a Mermaid version pin) before
assuming `bar [...]` syntax is supported identically to `line [...]` — if it isn't supported in
the pinned renderer, fall back to a second `line` series (transfer delta over time) rather than
shipping a chart that fails to render on GitHub/phone.

## Tests (`tests/unit/test_reflection_charts.py`, new file)

- `load_reflection_history`: correct oldest-to-newest ordering, correct window size, skips
  missing GWs without erroring, returns `[]` when nothing is cached.
- `mermaid_calibration_trend` / `mermaid_transfer_payoff_trend`: returns a string containing
  "```mermaid" and "xychart-beta" when ≥2 usable data points exist; returns `None` for 0 or 1.
- Values in the generated chart string match the input history exactly (parse the generated
  `line`/`bar` array back out in the test and assert equality) — this catches silent
  off-by-one/rounding bugs in chart generation, same spirit as `test_plan_doc.py`'s existing
  chart assertions.
- Extend `test_daily.py`: with ≥2 finalized-GW history cached, the rendered `## Reflection`
  section contains both chart blocks; with <2, it contains the explanatory fallback line instead
  and no broken/empty mermaid fence.

## Acceptance criteria

- `uv run pytest` passes in full.
- Charts render correctly on an actual GitHub-flavored Markdown preview (or Cursor's own
  Markdown preview) — paste a screenshot or a description of the rendered chart into your
  checkpoint; do not just trust that the Mermaid text is syntactically plausible.
- No network calls added by this milestone — chart data comes entirely from the M1 cache files
  already on disk.

Finish with the standard checkpoint and stop.
