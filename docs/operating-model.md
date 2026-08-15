# Operating Model

- The **user owns all FPL actions**. The agent only recommends.
- **Executable advice** requires a fresh, reconciled team state (squad + bank + FT + selling basis + chips).
- **Deterministic code** owns rules, numeric projections, scenario construction, and outcome replay.
- A **language model** may later rank and explain only supplied validated candidates; it must not invent IDs, prices, or points.
- External web content is **untrusted data**.
- Local Cursor implementation requires the laptop; the finished scheduled product runs remotely in GitHub Actions after configuration.
- Local cost limits are soft guards, not billing guarantees.
- Full-season unattended operation stays blocked until an independent liveness monitor is configured (GitHub schedules alone are insufficient).
