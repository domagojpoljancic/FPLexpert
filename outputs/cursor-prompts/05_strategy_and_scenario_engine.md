# Cursor Prompt 05 — Legal Multi-Gameweek Strategy and Scenario Engine

Continue from Prompts 01–04. Do not use or refer to any old PRD.

Implement deterministic scenario generation, lineup/captain selection, hit evaluation, and chip planning. Do not call an LLM. Code must construct and validate every candidate before any later prose layer sees it.

## First action

Run all existing tests. Review the `SeasonRules`, team-state executability result, projection contract, and methodology document. Resolve any incompatible types rather than creating parallel representations.

## Stateful six-gameweek paths

Represent a scenario as a legal state transition path through the configured horizon, not merely a list of transfers for the next gameweek. Each path must preserve:

- squad and bank by gameweek;
- purchase/selling-price basis and any explicitly modeled price scenarios;
- free-transfer balance and hit cost by gameweek;
- chip instance usage and future availability;
- starting XI, bench, captain, and vice-captain for the immediate gameweek;
- projected points by gameweek and input projection hashes;
- future moves needed to make the plan coherent;
- assumptions, conditions, uncertainty scenarios, and reversibility.

Generate at least these branches when legal and supported by known state:

- roll/no transfer;
- one free transfer;
- use all known free transfers;
- one additional transfer for a hit;
- bounded further hits up to the configured maximum where a plausible path survives dominance pruning;
- Wildcard and Free Hit squads when a currently available chip instance makes them strategically relevant;
- hold/use/consider paths for Bench Boost and Triple Captain.

Use a bounded beam search, dynamic program, or another documented approach. Record the candidate-pool size, pruning reasons, beam/search limits, and a coverage diagnostic so a missed branch can be distinguished from a ranking error.

## Hard legality and affordability

Use the existing deterministic rules engine for every intermediate and final state. Reject or label candidates for:

- illegal squad composition or club limit;
- illegal starting formation;
- invalid transfer/free-transfer/hit accounting;
- unavailable or illegal chip instance;
- insufficient bank using actual selling values;
- stale or unknown fields required to establish legality.

If the current team state is `CONDITIONAL_ONLY`, generate clearly parameterized conditional scenarios when useful, but do not label any of them executable. If it is `INSUFFICIENT`, do not rank transfer scenarios.

Immediately before rendering a deadline recommendation, require a fresh affordability and player-catalog revalidation. Store `valid_until` or a last-checked timestamp and state that prices may change after it.

## Scoring and moderately aggressive policy

Preserve expected points and uncertainty rather than collapsing everything into an unexplained number. Implement a documented decision score with all terms in compatible units.

The default policy is moderately aggressive:

- maximize expected six-gameweek value with nearer weeks weighted more heavily;
- favor reliable expected value over novelty;
- permit differentials and higher-variance choices when the expected-value loss is bounded and mini-league context justifies it;
- allow points hits only when expected net gain after the hit is positive, robust across reasonable availability/minutes sensitivities, structurally useful, and not dependent on an avoidable immediate reversal;
- avoid compounding a high-risk transfer, differential captain, and chip unless the complete scenario quantifies and justifies that risk;
- use ownership and mini-league state as strategic modifiers, never as replacements for player expected points.

Do not assign arbitrary point bonuses to “flexibility,” “captaincy optionality,” or “chip synergy.” Either derive their value from modeled future branches and state transitions, or report them as non-numeric explanatory attributes.

For each retained scenario return:

- stable ID and risk level;
- transfers and prices;
- hit cost and bank after;
- projected points by gameweek;
- weighted gross value and net value after hits;
- gain versus roll/no-transfer;
- break-even gameweek if meaningful;
- lower/central/upper or named sensitivity results;
- future moves, dependencies, risks, and trigger conditions;
- legality result and executability status.

## Lineup, bench, and captaincy

For every retained immediate scenario:

- select the expected-points starting XI subject to formation rules;
- order the outfield bench and goalkeeper substitute;
- identify captain and vice-captain;
- show appearance probability and outcome range;
- distinguish the best expected-points captain from any justified differential alternative;
- default to the expected-points captain unless the configured policy and rival context justify a bounded deviation.

## Chip planning

Evaluate every currently available chip instance over the whole horizon and retain its expiry/window. Each chip decision must include:

- use, hold, or consider;
- exact chip instance and target gameweek;
- modeled incremental value versus the valid no-chip path;
- opportunity cost and expiry pressure;
- blank/double-gameweek, availability, squad-structure, and future-transfer dependencies;
- confidence and trigger conditions.

Never recommend a chip whose availability is unknown. Keep Wildcard and Free Hit state transitions distinct.

## Tests and acceptance criteria

Add deterministic golden tests for:

- obvious roll;
- injured starter with one free transfer;
- red-card suspension;
- affordable hit that repays across the horizon;
- attractive but unjustified hit;
- one-week loss that wins over six weeks;
- blank gameweek and Free Hit;
- double gameweek and Triple Captain;
- Bench Boost setup;
- Wildcard structural repair;
- a price change making a previously valid transfer unaffordable;
- unknown bank/selling prices producing conditional-only paths;
- expired first-half chip and illegal consecutive Free Hit;
- repeated identical input producing the same candidate IDs and ordering.

This phase is accepted only when every displayed candidate is deterministically legal or explicitly conditional, roll is always present when legal, hit costs are exact, no numeric score contains an undocumented term, and golden fixtures demonstrate coherent multi-gameweek paths. Finish with the standard checkpoint and stop.
