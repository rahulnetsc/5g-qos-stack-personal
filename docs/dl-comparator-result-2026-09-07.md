# Step 3 (B1) — the downlink comparator, measured for the first time

**2026-09-07.** `sweeps/dltrace-2026-09-07/traces.json`, 4 cells × 3 arms × 10
seeds, **bit-identical with the hooks off on 120 of 120 cells**.

**The change was one sink, not one line.** The rank hook already fired for both
directions — it is called from the direction loop in both QoS arms — and only
`LossPointTally` filtered on `snap.direction`. So **every decisive-term number
this project has published was uplink**, including the "four dead ranking
tiers" result, and TwoTier's `has_gbr`/`pdb_ms` tiers are **DL-only terms that
therefore appeared in no tally at all.**

---

## The result

| direction | arm | adjacencies | decisive terms |
|---|---|---|---|
| **UL** | PF | 6,022,026 | `-metric` 99.99 % · TIED 0.01 % |
| | Reservation | 5,598,120 | `-coef` 66.34 % · `pdb_ms` 21.77 % · `has_gbr` 11.53 % · TIED 0.36 % |
| | TwoTier | 5,299,905 | `-coef` 96.64 % · TIED 3.36 % · `floor_fire` 0.00 % |
| **DL** | PF | 43,355 | `-metric` 99.68 % · TIED 0.32 % |
| | **Reservation** | 38,642 | **TIED 80.40 %** · `-coef` 18.91 % · `pdb_ms` 0.69 % · **`has_srb` 0** |
| | **TwoTier** | 39,346 | **TIED 98.36 %** · `pdb_ms` 1.64 % · **`has_gbr` 0 · `-coef` 0** |

## What it says

**On downlink, both QoS arms are ordered by DECLARATION ORDER — 98.4 % on
TwoTier and 80.4 % on Reservation — against PF's 0.3 %.**

Declaration order is flow-list position. It has **no physical referent**; it is
the same artefact that stopped G12's ordering being promoted to a scheduler
property. **TwoTier's downlink `has_gbr` and `-coef` tiers decide nothing at
all**, and its whole DL ranking reduces to `pdb_ms` on 1.6 % of adjacencies and
a tie on the rest.

**And it corrects P1-4's headline.** *"Both QoS arms rank on
`coef → pdb_ms → has_gbr`"* is now measured to be **uplink-only, and true only
of Reservation**. TwoTier's uplink comparator is `-coef` alone at 96.6 %; its
downlink comparator is a coin-flip on declaration order.

## Why — and it makes Step 4 (CFG-2) load-bearing rather than tidy

Two conditions co-occur on downlink and both are scenario choices, not fidelity
gaps:

1. **The DL link is idle.** Every 5QI-9 background flow in every built scenario
   is uplink, so only ~160-214 slots per run carry any DL grant, and the DL
   adjacency count is **~1/140th** of uplink's. Few candidates per slot.
2. **`snr_spread_db = 0.0` in every artefact the scorecard reads**, so every UE
   has the same mean SNR. With identical channels the coefficient terms
   **cannot separate candidates**, and a lexicographic comparator falls through
   to the tie.

**So the 98 % tie rate is the measurable consequence of CFG-2**, and it is the
first direct evidence that equal channels are not a harmless simplification.

## What this does and does not license

**Does:** it answers Step 3's own question — **B3's DL half matters, but not
yet.** A 4-UE-per-slot DL cap applied to a comparator that is 98 % ties would
be capping an essentially arbitrary order. **The DL background flow and
`snr_spread_db` must come first**, or M-6's DL half measures the cap's
interaction with a coin flip.

**Does not:** it says nothing about which DL tier would dominate on a contended,
channel-diverse downlink — that is exactly what the trace will answer once the
scenario exists. **It is not evidence that the DL comparator is broken**; it is
evidence that this evidence base never exercised it.

**And it bears directly on G1**, whose clause names a **downlink** command: the
scored statistic is uplink telemetry (P2-2), and the downlink flow it is
actually about is ordered by declaration order 98 % of the time.
