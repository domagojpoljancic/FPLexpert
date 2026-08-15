# Cursor Prompt 02 — Versioned 2026/27 FPL Rules Engine

Continue in the repository produced by Prompt 01. Do not use or refer to any old PRD.

## First action and verification requirement

Inspect the existing foundation and run its tests. Then verify every temporally unstable FPL rule below against current primary Premier League/FPL sources. Record the checked URLs, check date, and any discrepancies in `docs/assumptions-register.md` before implementing.

Start with these official sources:

- 2026/27 changes: <https://www.premierleague.com/en/news/4679873/all-you-need-to-know-about-changes-to-fpl-for-202627>
- 2026/27 chips: <https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627>
- transfers and selling value: <https://www.premierleague.com/en/news/2174907/1000>
- lineup, captain and autosubs: <https://www.premierleague.com/en/news/2174899/fpl-basics-managing-your-team>
- defensive contributions: <https://www.premierleague.com/en/news/4361991/whats-happening-with-defensive-contribution-points-in-202627-fantasy>
- live rules metadata: <https://fantasy.premierleague.com/api/bootstrap-static/>

If a rule conflicts with a current official source, use the current rule, cite it, add a regression fixture, and report the discrepancy. Do not silently guess.

## Implement `SeasonRules`

Create a versioned, immutable `SeasonRules` contract and a loader for `2026-27`. Separate:

1. official documented rules;
2. values observed in the live bootstrap payload;
3. application policy.

Do not hard-code historical assumptions throughout the codebase. Rule consumers must receive a `SeasonRules` object. A new or materially changed season must fail closed with exit code 8 until its rule manifest passes review and conformance tests.

The current manifest must represent at least:

- £100.0m initial budget;
- 15-player squad: 2 goalkeepers, 5 defenders, 5 midfielders, 3 forwards;
- maximum 3 players per Premier League club;
- starting XI: exactly 1 goalkeeper, 3–5 defenders, 2–5 midfielders, and 1–3 forwards;
- one free transfer after each gameweek, bankable to a maximum of five total free transfers;
- extra transfers costing 4 points each;
- purchase, current and selling prices in integer tenths;
- selling-value behavior: retain £0.1m for each complete £0.2m rise while price falls pass through fully;
- captain double points, vice-captain fallback, and ordered autosubs subject to a legal formation;
- one playing goalkeeper autosub rule and outfield bench ordering;
- all standard point categories needed for validation/documentation, including current defensive-contribution scoring;
- deadlines derived from event metadata; do not calculate them from fixture dates;
- official results remaining provisional until the official season-specific lock condition.

## Model the eight chip instances correctly

For 2026/27 there are two time-bounded instances of each of:

- Wildcard;
- Free Hit;
- Bench Boost;
- Triple Captain.

Represent chip identity separately from chip instance/window. The first set expires at the GW19 deadline and cannot roll into the second half; the second set applies from GW20 to GW38. Only one chip may be active in a gameweek.

Include verified rules for:

- Wildcard and Free Hit availability around GW1;
- the prohibition on consecutive Free Hits, including GW19 followed by GW20;
- cancellation behavior before the deadline for the relevant chips;
- permanent Wildcard transfers versus the one-gameweek Free Hit squad restoration;
- preservation of banked free transfers across Wildcard and Free Hit where the current official rules state it;
- Bench Boost scoring the bench;
- Triple Captain tripling instead of doubling the captain's points.

Do not represent availability as a single list such as `['wildcard', 'freehit', ...]`.

## Pure deterministic functions

Implement and test pure functions for:

- full squad validation;
- lineup and formation validation;
- selling-price calculation;
- budget after a transfer set;
- free-transfer rollover and hit calculation;
- chip availability and transition rules;
- captain/vice multipliers;
- autosub resolution;
- manager gameweek total from official per-player FPL points, selected lineup, multipliers, chip state, autosubs, and hit cost.

For retrospective replay, official per-player FPL points are inputs. Do not recalculate official player awards from goals, assists, Opta events, BPS, or raw match data.

## Defensive contributions and season changes

The projection system will later estimate defensive-contribution potential, so expose current thresholds and awarded points in the rule manifest. Keep the raw-stat definition separate by position. Do not add these points a second time when official FPL player totals are being replayed.

Add a `rules diff` or equivalent CLI command that compares a stored manifest with live bootstrap rule metadata and emits:

- no material change;
- non-breaking observed change;
- material unreviewed change requiring safe shutdown.

## Tests and acceptance criteria

Use example-based and property-based tests where useful. Cover at least:

- every valid formation and representative invalid formations;
- squad size/position/club-limit violations;
- price rises of 0.1m, 0.2m, 0.3m and 0.4m and all price falls;
- zero through five banked free transfers and transfers beyond the allowance;
- Wildcard and Free Hit transitions and restoration;
- both instances of every chip and first-half expiry;
- illegal consecutive Free Hits;
- captain absence, vice-captain fallback, goalkeeper autosub, outfield autosubs, and formation-preserving bench skips;
- Bench Boost and Triple Captain replay;
- a season-rule drift fixture that causes fail-closed behavior.

This phase is accepted only when all rule tests pass at 100%, the current source check is recorded, and no LLM or prose layer can override a deterministic rule result. Finish with the standard checkpoint and stop.
