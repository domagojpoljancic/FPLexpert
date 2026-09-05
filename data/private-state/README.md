# Your squad file (`current.json`)

Private-purpose personal FPL state for this season (not a product yet). This folder holds a **manual snapshot** of your FPL team. The app never logs into FPL, so it only knows what you put here.

`current.json` is gitignored. On your phone, the pre-deadline agent lists this squad and asks for a screenshot only if something changed.

| Field | Meaning |
| --- | --- |
| `as_of` | When you last copied the team. After **24 hours** the app treats it as stale and will **not** call transfer advice executable. |
| `applies_before_gameweek` | Which GW this snapshot is for (the next deadline). |
| `player_ids` | Your 15 FPL player IDs. |
| `bank_tenths` | Money in the bank, in tenths of £1m. **15 = £1.5m**. |
| `free_transfers` | Unused free transfers. |
| `purchase_prices_tenths` | What you paid for each player (same tenths). Needed for selling price. |
| `captain_id` / `vice_id` | Captain and vice. |
| `starters` / `bench_order` | Optional XI and bench. |
| `chip_instances` | Which chips you still have. |
| `watchlist_player_ids` | Optional extras for the price watch. |

**INSUFFICIENT** in a report means: this file is missing, incomplete, or older than 24 hours. News notes can still be useful; do not treat suggested transfers as “do this now.”

After you update `current.json`, local `predeadline` uses it immediately. The GitHub evening price job needs `uv run fpl-agent team-state encode-for-github data/private-state/current.json` as well.

Check the file with: `uv run fpl-agent team-state status`

From a screenshot, map each card as **printed name | opponent | H/A | price** (the fixture line under the name is the club; ignore kits):

```bash
uv run fpl-agent team-state lookup -- "Raya|COV|H|6.0|GKP" "Senesi|BRE|A|6.0|DEF" "B.Fernandes|HUL|A|12.0|MID"
uv run fpl-agent team-state names
```
