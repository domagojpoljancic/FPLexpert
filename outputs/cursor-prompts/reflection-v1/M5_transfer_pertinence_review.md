# reflection-v1 M5 — "How did that transfer age?" multi-week pertinence review

Continue from M4. This milestone is the direct answer to: "reflect how previous transfer
suggestions were, how those players pertained, and what could've been done better" — tracked
across each transfer's **original recommended horizon**, not just the first week after it was
made. Re-read `07_decision_ledger_and_retrospectives.md`'s "Multi-gameweek decisions and lessons"
section again — `latest_gw_delta` / `cumulative_horizon_delta` / open-until-horizon-ends is
specified there and is the contract for this milestone.

## First action

Run the full test suite. Re-read `daily.py:1427-1459` (`_write_decision_ledger`) — per
`INVENTORY.md` this currently writes a near-empty `DecisionRecord` (empty hashes, no OUT/IN ids,
no `also_considered`, no horizon window). This milestone must enrich that write before it can
build theses on top of it.

## 1. Enrich the decision ledger write

In `_write_decision_ledger` (`daily.py`), when `report.weekly_plan.get("after_transfer")` is
present, populate `DecisionRecord.primary` with the actual locked pick, not just
`{"plan_action": ...}`:

```python
best = weekly_plan.get("best_affordable") or {}
primary = {
    "plan_action": report.plan_action,
    "out_id": best.get("out_id"),
    "out_name": best.get("out_name"),
    "in_id": best.get("in_id"),
    "in_name": best.get("in_name"),
    "delta_gw_xp": best.get("delta_gw_xp"),
    "delta_weighted_xp": best.get("delta_weighted_xp"),
    "horizon_gameweeks": [row.get("gameweek") for row in (weekly_plan.get("horizon_impact") or {}).get("by_gw") or []],
}
record = DecisionRecord(..., primary=primary, alternatives=list(weekly_plan.get("also_considered") or []), ...)
```

Do **not** relax the existing overwrite protection at `ledger.py:47-49` — if a record already
exists for this exact `decision_id` (content hash), that's expected (reruns of the same
predeadline within a window produce the same content hash) and should be treated as
"already recorded," not an error to propagate. Confirm `write_decision_record`'s existing
`FileExistsError` handling at `daily.py`'s call site (right after `_write_decision_ledger`)
still swallows this correctly once `primary` is richer (the content hash will now include real
data, so verify the hash still collides only on genuinely identical content).

## 2. Transfer thesis tracking

New module `src/fpl_agent/evaluation/transfer_pertinence.py`:

```python
@dataclass(frozen=True)
class TransferThesis:
    decision_id: str
    version: int                       # 1, 2, 3... each update is a new version, never a mutation
    out_id: int
    out_name: str
    in_id: int
    in_name: str
    gameweek_made: int
    horizon_gameweeks: tuple[int, ...]  # the original recorded horizon, fixed at version 1
    predicted_delta_by_gw: dict[int, float]   # fixed at version 1, from the recorded horizon_impact
    actual_delta_by_gw: dict[int, int]        # grows as each GW in the horizon finalizes
    cumulative_predicted_delta: float
    cumulative_actual_delta: int
    status: str                        # "open" | "closed_horizon_complete" | "closed_player_sold"
                                        # | "closed_plan_invalidated"

def open_theses_from_ledger(root: Path, season: str) -> list[TransferThesis]:
    """Scan data/decision-ledger/{season}/gw-*/ for canonical records with a
    populated `primary.in_id`/`out_id`; build one version-1 thesis per unique
    decision content that represents a real transfer (skip 'hold' weeks)."""

def update_theses_for_gameweek(
    theses: list[TransferThesis], *, gameweek: int, player_points: dict[int, int],
    current_squad_ids: set[int],
) -> list[TransferThesis]:
    """For each open thesis whose horizon_gameweeks includes `gameweek` and doesn't
    already have that GW filled in actual_delta_by_gw: add
    player_points[in_id] - player_points[out_id] for that GW. Recompute cumulative
    fields. Close with closed_horizon_complete once every horizon GW is filled.
    Close with closed_player_sold if `in_id` is no longer in `current_squad_ids`
    at a later gameweek (the thesis's premise no longer holds — say so plainly,
    don't keep pretending it's still tracking a player who left the squad)."""
```

Persist as append-only versions to `data/evaluation/transfer-theses.jsonl` (one line per
version, same pattern as M4's `lessons.jsonl`) plus a `data/evaluation/transfer-theses-latest.json`
pointer keyed by `decision_id` → latest version's full record, for cheap reads by the report
renderer (rebuild this pointer file deterministically from the jsonl on every write — treat it
as a derived index, not a second source of truth).

Wire `update_theses_for_gameweek` into the same place `build_reflection` (M1) already fetches
`player_points` for the subject GW — do not fetch live points twice.

## 3. Report section

Extend the detailed `## Reflection` section with:

```
### How past transfer calls have aged

| Move | Made | Weeks tracked | Predicted (so far) | Actual (so far) | Verdict |
| --- | --- | --- | --- | --- | --- |
| Shaw → De Cuyper | GW3 | 2 / 6 | +4.4 | +8 | Paying off — ahead of plan, 4 GWs left in its horizon |
| O'Nien → Egan | GW2 | 6 / 6 | +2.1 | -1 | Closed — net -1 pt over its 6-GW horizon |
```

Only list theses that are `open` or closed within roughly the last few weeks (avoid an
ever-growing table — cap to, say, the last 6 relevant theses; older closed ones remain in the
data files for M4's aggregation, just not repeated in every report). For each thesis, reuse the
same "what could've been done better" discipline as M1: only cite `alternatives` actually
recorded on that `DecisionRecord` — never a live re-rank.

## Tests (`tests/unit/test_transfer_pertinence.py`, new file)

- Build a synthetic 3-GW sequence of decision-ledger records (GW3 transfer with a 3-GW horizon)
  and synthetic live points for GW3, GW4, GW5. Assert: thesis opens at GW3 with the full horizon
  and predicted deltas already fixed; after applying GW3's points it has 1/3 filled and status
  `open`; after GW4 it's 2/3; after GW5 it closes `closed_horizon_complete` with the correct
  cumulative actual delta.
- A thesis whose `in_id` disappears from `current_squad_ids` mid-horizon closes
  `closed_player_sold` at that point and does not continue accumulating further GWs.
- Immutability: after a thesis reaches version N, re-running `update_theses_for_gameweek` for an
  already-filled GW does not create a version N+1 with different numbers for that GW (idempotent
  re-runs — critical since predeadline can run multiple times per window, as the real
  `README.md` run history shows for GW3).
- Report rendering: the table only shows recorded alternatives, verified the same way as M1/M2's
  "what could have been done better" tests (no player id in the text that isn't in that
  decision's own recorded `alternatives`).

## Acceptance criteria

- `uv run pytest` passes in full.
- No mutation of a decision-ledger record after it's written (`ledger.py:47-49`'s guarantee is
  untouched); all thesis progress lives in the new, explicitly-versioned `transfer-theses.jsonl`.
- A thesis's `horizon_gameweeks` and `predicted_delta_by_gw`, once set at version 1, never change
  in a later version — only `actual_delta_by_gw`/`cumulative_actual_delta`/`status` do.
- Re-running predeadline multiple times within the same pre-deadline window (as this repo
  routinely does — see the many `predeadline-gw3-*` timestamps in `reports/`) does not spam
  duplicate thesis versions for GWs whose data hasn't changed.

Finish with the standard checkpoint and stop.
