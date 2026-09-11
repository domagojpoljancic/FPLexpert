# Season plan — Gameweek 4

Locked move: **Tzolis → Ødegaard** (plan **REVISE**).

## Why this move over the next weeks

Selling **Tzolis** for **Ødegaard** changes the XI projection across the planning horizon (GW4 +2.5, GW5 +0.7, GW6 +1.1, GW7 +0.6, GW8 +1.1, GW9 +0.8; +5.4 weighted overall). Adds +2.5 pts to the XI this GW and keeps paying later (GW5 +0.7, GW6 +1.1, GW7 +0.6; +5.4 weighted overall).

| GW | Hold XI xP | After XI xP | Delta |
| --- | ---: | ---: | ---: |
| 4 | 41.73 | 44.29 | +2.55 |
| 5 | 26.20 | 26.89 | +0.69 |
| 6 | 26.77 | 27.92 | +1.15 |
| 7 | 26.44 | 26.99 | +0.55 |
| 8 | 26.93 | 28.02 | +1.09 |
| 9 | 24.70 | 25.49 | +0.78 |

```mermaid
xychart-beta
    title "XI xP: hold vs Tzolis to Ødegaard"
    x-axis [GW4, GW5, GW6, GW7, GW8, GW9]
    y-axis "XI xP" 22 --> 46
    line [41.7, 26.2, 26.8, 26.4, 26.9, 24.7]
    line [44.3, 26.9, 27.9, 27.0, 28.0, 25.5]
```

## Spend now vs bank the free transfer

**Bank vs spend verdict: Bank the FT.** Bank the FT (1→2 next GW). Bank for 2 FT: dual-move horizon EV 7.4 beats act-now 4.1 (delta +3.2). (FT now 1 → 1 if you transfer, 2 if you roll; sequence bank_for_2ft (act-now 4.147, roll-to-2FT 7.364, hit None); deferred dual-move upside +3.22; net after FT penalty +3.80; locked pick Tzolis→Ødegaard.)

```mermaid
flowchart LR
    A["GW4 locked: Tzolis to Ødegaard"]
    B["Bank FT"]
    C["Next GW: 2 FT if rolled"]
    D["Chips: hold chips"]
    A --> B
    B --> C
    C --> D
```

## Bank and value after the move

The locked swap sells at £6.4m and buys at £6.7m, leaving **£0.0m** in the bank. Free transfers after acting: 1; after rolling: 2. Future affordability is this residual bank plus selling prices — not a forecast of price changes.

```mermaid
flowchart TD
    N0["FT now: 1"]
    N1["If transfer: FT 1 / £0.0m after move"]
    N2["If roll: FT 2"]
    N0 --> N1
    N0 --> N2
```

## Confirmed DGW / BGW in the horizon

Confirmed fixtures in horizon (GW4, GW5, GW6, GW7, GW8, GW9): no DGW/BGW flags from the feed.

```mermaid
flowchart LR
    G0["GW4 SGW"]
    G1["GW5 SGW"]
    G2["GW6 SGW"]
    G3["GW7 SGW"]
    G4["GW8 SGW"]
    G5["GW9 SGW"]
    G0 --> G1
    G1 --> G2
    G2 --> G3
    G3 --> G4
    G4 --> G5
```

## DGW / BGW priors (not confirmed)

No labelled DGW/BGW priors on this report (none invented by default).

## Chip timing

**3xc**: hold (available) — Captain mean xP 5.98 lacks ceiling for TC (haul proxy 0.00, need ≥0.25); hold until a genuine haul week (DGW detection pending). **bboost**: hold (available) — Bench xP 2.82 (need ≥8) or outfield start risk (min 10%) is not enough to spend Bench Boost. **freehit**: hold (available) — This week's XI xP 41.7 is close enough to the horizon median 26.4; hold Free Hit. **wildcard**: hold (available) — Only 0 XI player(s) have start chance below 40%; keep Wildcard.

_Recommend only — you make all FPL changes. Numbers from the locked weekly primary; no second ranking._
