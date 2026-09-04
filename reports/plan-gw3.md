# Season plan — Gameweek 3

Locked move: **Shaw → De Cuyper** (plan **REVISE**).

## Why this move over the next weeks

Selling **Shaw** for **De Cuyper** changes the XI projection across the planning horizon (GW3 +3.4, GW4 +1.0, GW5 +0.6, GW6 +0.5, GW7 +0.9, GW8 +0.3; +5.7 weighted overall). Adds +3.4 pts to the XI this GW and keeps paying later (GW4 +1.0, GW5 +0.6, GW6 +0.5; +5.7 weighted overall).

| GW | Hold XI xP | After XI xP | Delta |
| --- | ---: | ---: | ---: |
| 3 | 41.89 | 45.27 | +3.38 |
| 4 | 25.65 | 26.63 | +0.98 |
| 5 | 25.75 | 26.37 | +0.62 |
| 6 | 26.66 | 27.11 | +0.45 |
| 7 | 25.75 | 26.64 | +0.90 |
| 8 | 26.90 | 27.21 | +0.31 |

```mermaid
xychart-beta
    title "XI xP: hold vs Shaw to De Cuyper"
    x-axis [GW3, GW4, GW5, GW6, GW7, GW8]
    y-axis "XI xP" 23 --> 47
    line [41.9, 25.6, 25.8, 26.7, 25.8, 26.9]
    line [45.3, 26.6, 26.4, 27.1, 26.6, 27.2]
```

## Spend now vs bank the free transfer

**Bank vs spend verdict: Bank the FT.** Bank the FT (1→2 next GW). Bank for 2 FT: dual-move horizon EV 10.1 beats act-now 5.6 (delta +4.5). (FT now 1 → 1 if you transfer, 2 if you roll; sequence bank_for_2ft (act-now 5.599, roll-to-2FT 10.089, hit 4.413); deferred dual-move upside +4.49; net after FT penalty +5.25; locked pick Shaw→De Cuyper.)

```mermaid
flowchart LR
    A["GW3 locked: Shaw to De Cuyper"]
    B["Bank FT"]
    C["Next GW: 2 FT if rolled"]
    D["Chips: hold chips"]
    A --> B
    B --> C
    C --> D
```

## Bank and value after the move

The locked swap sells at £4.5m and buys at £4.7m, leaving **£0.3m** in the bank. Free transfers after acting: 1; after rolling: 2. Future affordability is this residual bank plus selling prices — not a forecast of price changes.

```mermaid
flowchart TD
    N0["FT now: 1"]
    N1["If transfer: FT 1 / £0.3m after move"]
    N2["If roll: FT 2"]
    N0 --> N1
    N0 --> N2
```

## Confirmed DGW / BGW in the horizon

Confirmed fixtures in horizon (GW3, GW4, GW5, GW6, GW7, GW8): no DGW/BGW flags from the feed.

```mermaid
flowchart LR
    G0["GW3 SGW"]
    G1["GW4 SGW"]
    G2["GW5 SGW"]
    G3["GW6 SGW"]
    G4["GW7 SGW"]
    G5["GW8 SGW"]
    G0 --> G1
    G1 --> G2
    G2 --> G3
    G3 --> G4
    G4 --> G5
```

## DGW / BGW priors (not confirmed)

No labelled DGW/BGW priors on this report (none invented by default).

## Chip timing

**3xc**: hold (available) — Captain mean xP 7.47 lacks ceiling for TC (haul proxy 0.00, need ≥0.25); hold until a genuine haul week (DGW detection pending). **bboost**: hold (available) — Bench xP 2.32 (need ≥8) or outfield start risk (min 10%) is not enough to spend Bench Boost. **freehit**: hold (available) — This week's XI xP 41.9 is close enough to the horizon median 25.8; hold Free Hit. **wildcard**: hold (available) — Only 0 XI player(s) have start chance below 40%; keep Wildcard.

_Recommend only — you make all FPL changes. Numbers from the locked weekly primary; no second ranking._
