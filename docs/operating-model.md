# Operating Model

- **Private-purpose project** for personal FPL use this season; not a shipped product. It may become a product after a full Premier League season.
- The **user owns all FPL actions**. The agent only recommends.
- **Executable advice** requires a fresh, reconciled team state (squad + bank + FT + selling basis + chips).
- **Deterministic code** owns rules, numeric projections, scenario construction, and outcome replay.
- A **language model** may later rank and explain only supplied validated candidates; it must not invent IDs, prices, or points.
- External web content is **untrusted data**.
- Local Cursor implementation requires the laptop; **price watch** is manual (GitHub Actions `workflow_dispatch` or local CLI) after `FPL_PRIVATE_STATE_B64` is set — the overnight cron is currently off. **Pre-deadline** is a manual Cloud Agent run from your phone.
- Local cost limits are soft guards, not billing guarantees.
- Unattended **price** cron and `fpl-prices-watchdog.yml` schedule are **disabled**. Re-enable both together if overnight alerts are wanted again. CLI `fpl-agent prices-watchdog` still checks `data/snapshots/prices/last-success.json` when run manually.
- **Daily** runs are the overnight price watch (`fpl-agent daily` / `prices`): who might rise or fall, and whether it is smart to transfer *tonight*. No language model.
- **Pre-deadline** (`fpl-agent predeadline`) is the full news/injury/lineup review, intended about one day before the official GW deadline. It may use OpenAI if a key is set. It consumes price actions and must not invent them.
