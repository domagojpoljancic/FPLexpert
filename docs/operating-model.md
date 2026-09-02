# Operating Model

- The **user owns all FPL actions**. The agent only recommends.
- **Executable advice** requires a fresh, reconciled team state (squad + bank + FT + selling basis + chips).
- **Deterministic code** owns rules, numeric projections, scenario construction, and outcome replay.
- A **language model** may later rank and explain only supplied validated candidates; it must not invent IDs, prices, or points.
- External web content is **untrusted data**.
- Local Cursor implementation requires the laptop; **price watch** runs on GitHub Actions after `FPL_PRIVATE_STATE_B64` is set. **Pre-deadline** is a manual Cloud Agent run from your phone.
- Local cost limits are soft guards, not billing guarantees.
- Full-season unattended **price** jobs are on GitHub cron (can skip/run late). `fpl-agent prices-watchdog` (and `.github/workflows/fpl-prices-watchdog.yml`) comments on a GitHub issue when `data/snapshots/prices/last-success.json` is older than 26 hours. That still cannot see a total GitHub outage.
- **Daily** runs are the overnight price watch (`fpl-agent daily` / `prices`): who might rise or fall, and whether it is smart to transfer *tonight*. No language model.
- **Pre-deadline** (`fpl-agent predeadline`) is the full news/injury/lineup review, intended about one day before the official GW deadline. It may use OpenAI if a key is set. It consumes price actions and must not invent them.
