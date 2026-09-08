# reflection-v1 M1 — Finality gate + deterministic reflection builder

Continue from `INVENTORY.md`. Do not touch `daily.py`'s report rendering yet (that's M2) — this
milestone only adds the gate and the data builder, plus tests, so M2 has something solid to
call.

## First action

Re-run the checks in `INVENTORY.md`: confirm `finality.is_final` is still unused, confirm
`predeadline_ev_positive`/`recommendation_net`/`roll_net` are still never set on a real
`weekly_plan`, and re-read `daily.py:151-210` (`run_predeadline`) to confirm `bootstrap` and
`fixtures` are still both in scope before the private-squad check. If any of this has changed,
adjust the plan below accordingly and note the drift in your checkpoint.

## Scope

1. A pure gate: given `bootstrap` + `fixtures` (+ current time), decide whether the gameweek
   immediately before the one being planned is genuinely official/final, still in progress, or
   unknown/ambiguous.
2. A pure builder: given that a prior GW is final, assemble a `ReflectionSummary` — the
   predicted-vs-actual XI/captain/transfer facts, process/outcome/root-cause grade, and a
   deterministic (non-LLM) "what could have been done better" line sourced only from the
   recorded `also_considered` shortlist.
3. Persist the summary as a small JSON cache so M3/M4/M5 can build history without recomputing
   or re-fetching live points every run.

## 1. The finality gate

New module `src/fpl_agent/evaluation/reflection.py`.

```python
from enum import StrEnum

class GwFinality(StrEnum):
    FINAL = "final"            # official, data_checked — safe to reflect on
    IN_PROGRESS = "in_progress"  # fixtures exist for this GW and at least one hasn't finished
    PROVISIONAL = "provisional"  # all fixtures finished, but not yet past the 09:00 UK lock
                                  # or data_checked is still false
    UNKNOWN = "unknown"          # no fixtures found for this GW, or malformed data
    NOT_APPLICABLE = "not_applicable"  # gameweek <= 0 (e.g. running predeadline for GW1)
```

`gw_finality_status(*, bootstrap: dict, fixtures: list[dict], gameweek: int, now: datetime | None = None) -> GwFinality`:

- `gameweek <= 0` → `NOT_APPLICABLE`.
- Find the matching entry in `bootstrap["events"]` where `event["id"] == gameweek`; read
  `data_checked` (bool) and `finished` (bool) off it. If the event is missing entirely →
  `UNKNOWN`.
- Filter `fixtures` (raw FPL `/api/fixtures/` shape — `event`, `finished`, `kickoff_time`) to
  `event == gameweek`. If empty → `UNKNOWN`. If any `finished` is falsy → `IN_PROGRESS`.
- Otherwise compute `final_match_end = max(kickoff_time for those fixtures)` (parse via the
  existing `cadence.parse_deadline` helper — reuse it, don't reimplement ISO parsing) and call
  `finality.is_final(now=now or utc_now(), final_match_end=final_match_end, data_checked=bool(event["data_checked"]))`.
  `True` → `FINAL`; `False` → `PROVISIONAL`.
- Treat any fixture list where `kickoff_time` is missing/unparseable as `UNKNOWN` rather than
  guessing — this is a "skip reflection" case, not a "assume it's fine" case.

`reflection_gate(bootstrap, fixtures, *, now=None) -> tuple[int, GwFinality]`:

- `subject_gw = next_gameweek(bootstrap) - 1` (reuse `suggest.next_gameweek`; this is "the GW we
  are reflecting on" — the one immediately before the one predeadline is currently planning).
- Return `(subject_gw, gw_finality_status(bootstrap, fixtures, subject_gw, now=now))`.
- Only `FINAL` means "build and show the reflection." Every other status means "skip" — the
  caller (M2) must treat `IN_PROGRESS`, `PROVISIONAL`, `UNKNOWN`, and `NOT_APPLICABLE` identically
  (no partial section for any of them).

## 2. The reflection builder

Extend `evaluation/reflection.py` with:

```python
@dataclass(frozen=True)
class AlternativeReviewed:
    in_name: str
    in_id: int
    predicted_delta: float | None   # xp vs the sold player, at decision time
    actual_delta: int | None        # official points vs the sold player, once known
    beat_the_pick: bool | None      # True only if actual_delta_for_this > actual_delta_for_pick

@dataclass(frozen=True)
class ReflectionSummary:
    schema_version: str
    gameweek: int                       # the GW being reflected on
    computed_at: str
    finality: str                       # GwFinality value, always "final" if this object exists
    report_path: str | None
    predicted_xi_xp: float | None
    actual_xi_points: int | None
    model_captain_name: str
    model_captain_points: int
    saved_captain_name: str | None
    saved_captain_points: int | None
    transfer_out_name: str | None
    transfer_in_name: str | None
    transfer_out_points: int | None
    transfer_in_points: int | None
    transfer_predicted_delta: float | None
    transfer_actual_delta: int | None
    process_quality: str
    outcome_quality: str
    root_cause: str
    alternatives_reviewed: tuple[AlternativeReviewed, ...]
    short_summary: str                  # one sentence, for the report header line
    detail_summary: str                 # 2-4 sentences, for the detailed section
    what_could_have_been_better: str    # cites only alternatives_reviewed / saved_captain
```

`build_reflection(*, gameweek: int, reports_dir: Path = Path("reports"), bootstrap: dict, client: FplClient | None = None) -> ReflectionSummary | None`:

1. `plan = load_latest_predeadline_plan(reports_dir, gameweek)` (reuse from `scorecard.py`). If
   `None`, return `None` — no saved plan means nothing to reflect on; this must degrade
   silently, not raise.
2. `player_points = fetch_live_points(gameweek, client=client)` (reuse). If it raises (network,
   FPL down), catch and return `None` — reflection failing must never break the predeadline run
   that calls it (M2 must treat this the same as "gate said skip").
3. Reuse `scorecard_from_plan(gameweek=gameweek, weekly_plan=plan, player_points=player_points)`
   for the XI/captain/transfer numbers and the process/outcome grade — do not recompute those by
   hand. **Do not** rely on `weekly_plan.get("predeadline_ev_positive")` /
   `recommendation_net` / `roll_net` being populated (per `INVENTORY.md`, they usually are not on
   a real plan today, which forces `grade_process_outcome` into `INSUFFICIENT_EVIDENCE`). Before
   calling it, if those three fields are absent, backfill sensible values derived from fields
   that *are* populated on a real plan:
   - `predeadline_ev_positive = bool((plan.get("best_affordable") or {}).get("delta_weighted_xp", 0) > 0)`
     when a transfer was actually recommended (`plan.get("after_transfer")` present); if the plan
     recommended holding (no transfer), there is no transfer thesis to grade this way — leave
     `predeadline_ev_positive=None` and let the XI/captain comparison stand on its own.
   - This backfill lives in `reflection.py`, not in `scorecard.py` (keep `scorecard.py`'s
     existing contract — used by the standalone `fpl-agent scorecard` command — unchanged; this
     milestone is additive).
4. For each row in `plan.get("also_considered") or []`, build an `AlternativeReviewed`: predicted
   delta from the row's own `xp`/horizon fields relative to the pick, actual delta from
   `player_points.get(row["in_id"])` minus the sold player's actual points (same OUT for every
   row, since `also_considered` is same-position/same-OUT alternatives — verify this invariant
   against `daily.py:684-704` and note in your checkpoint if it no longer holds).
5. Build `short_summary` and `detail_summary` as plain deterministic sentences (Python
   string templates, not free text) — mirroring the tone of `daily.py`'s existing `_para_*`
   helpers style used in `plan_doc.py`, e.g.:
   - short: `f"Last week (GW{gameweek}): {process_word} process, {outcome_word} outcome — {transfer_out_name} → {transfer_in_name} was {sign}{delta} pts."`
   - detail: 2-4 sentences covering XI predicted-vs-actual, captain call, transfer delta, and the
     process/outcome/root-cause label in plain language (spell out the enum, e.g.
     `sound_process_normal_variance` → "the process was sound; this is normal week-to-week
     variance, not a mistake").
6. Build `what_could_have_been_better` strictly from `alternatives_reviewed` and
   `saved_captain_name`:
   - If any alternative's `beat_the_pick` is `True`, name the single best one and its actual
     delta vs the pick's actual delta — phrase it as "was in the shortlist and would have scored
     more," never as a new suggestion.
   - Else if `saved_captain_name` differs from `model_captain_name` and scored more, mention that
     specifically (this is about what the user actually did differently, not hindsight).
   - Else, state plainly that no recorded alternative would have done better — do not manufacture
     a lesson where there isn't one.
7. Persist: `data/evaluation/reflection-gw{gameweek}.json` via `model_dump_json`/`asdict` +
   `json.dumps`. This file is **not** the immutable decision ledger — it's a derived, safely
   recomputable cache (official points can be corrected later per `finality.py`'s policy; when
   that happens this cache is simply overwritten with a fresh `computed_at`). Say this explicitly
   in a module docstring so a future contributor doesn't confuse it with `ledger.py`'s
   write-once contract.

## Tests (`tests/unit/test_reflection.py`, new file)

- `gw_finality_status`: in-progress (some fixture unfinished) → `IN_PROGRESS`; all finished but
  before the 09:00 UK lock or `data_checked=False` → `PROVISIONAL`; all finished + past the lock
  + `data_checked=True` → `FINAL`; no fixtures for that event → `UNKNOWN`; `gameweek=0` →
  `NOT_APPLICABLE`. Use small synthetic bootstrap/fixtures fixtures (follow the shape of
  `tests/fixtures/bootstrap_static_reduced.json`), not live network calls.
- `reflection_gate`: derives `subject_gw = next_gameweek - 1` correctly at a season boundary
  (e.g. `next_gameweek=1` → `subject_gw=0` → `NOT_APPLICABLE`, never a negative/garbage GW).
- `build_reflection`: with a saved plan fixture + a live-points fixture (reuse/extend the
  fixtures already used by `tests/unit/test_scorecard.py` / `test_scorecard_extended.py`),
  returns a populated `ReflectionSummary` whose `transfer_actual_delta`,
  `what_could_have_been_better`, and process/outcome fields match hand-computed expected values.
- `build_reflection` returns `None` (not an exception) when: no saved plan exists for that GW;
  the live-points fetch raises; the plan's `weekly_plan.ok` is falsy.
- Round-trip: the persisted `data/evaluation/reflection-gw{N}.json` deserializes back into an
  equivalent `ReflectionSummary`.

## Acceptance criteria

- `gw_finality_status` and `reflection_gate` are pure functions with no network access and no
  reliance on `datetime.now()` unless `now` is explicitly passed (tests must be deterministic).
- `build_reflection` never raises out of a network/missing-data failure — always degrades to
  `None`.
- `what_could_have_been_better` text, in tests, never references a player id/name that is absent
  from `also_considered` or `saved_captain_id` on the same plan.
- `uv run pytest tests/unit/test_reflection.py` passes; `uv run pytest` (full suite) still
  passes — this milestone must not change any existing report output yet.

Finish with the standard checkpoint (summary, files touched, tests run, risks, pass/fail) and
stop — do not start M2 in the same turn unless explicitly asked to.
