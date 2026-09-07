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

## Why — MEASURED, and it refutes half of my own first explanation

I first attributed the tie rate to two scenario choices: an idle DL link and
`snr_spread_db = 0`. **Tested by varying the spread directly** (one seed,
6,000 slots, N=8):

| spread | Reservation TIED | TwoTier TIED |
|---|---|---|
| 0 dB | **80.3 %** | 97.7 % |
| 6 dB | 72.4 % | 98.1 % |
| 12 dB | **50.5 %** | **98.6 %** |

**Right for Reservation — 80 % → 50 %, so channel spread genuinely explains a
large part of its DL ties.** `-coef` rises from 19.3 % to 49.5 % as channels
separate, which is exactly the opportunism CFG-2 says is switched off.

**Wrong for TwoTier — its tie rate does not fall, it slightly RISES.** So the
explanation had to be somewhere else, and it is:

**TwoTier's DL coefficient is 0.0 for EVERY candidate, in EVERY snapshot,
across an entire run — exactly one distinct value.** Dumped from the rank
stream at spread 12, where `hyp_tbs_bytes` plainly differs (30, 30, 41, 52):

```
ue1 key=(1, 100, -0.0)  coef=0.0  hyp_tbs=30.0  has_gbr=0.0
ue2 key=(1, 100, -0.0)  coef=0.0  hyp_tbs=30.0  has_gbr=0.0
ue3 key=(1, 100, -0.0)  coef=0.0  hyp_tbs=41.0  has_gbr=0.0
ue4 key=(1, 100, -0.0)  coef=0.0  hyp_tbs=52.0  has_gbr=0.0
```

**All three tiers of TwoTier's DL key are degenerate on this workload:**

| tier | value | why |
|---|---|---|
| `has_gbr` | **False for every candidate** | the only DL flow is 5QI 82, `Delay` class, **GFBR 0** |
| `pdb_ms` | identical for most | one periodic flow, same period and PDB on every UE |
| `-coef` | **0.0 for every candidate** | `coef = sum_q × hyp_tbs_bytes`, and `sum_q` is Tier-1's virtual queue — **zero for a flow with no GBR target**, so the channel term is multiplied by nothing |

**So TwoTier's downlink comparator is a CONSTANT on every built scenario, and
its ordering is declaration order by construction — not by tie-breaking luck,
and not fixable by adding channel spread.** `-coef` decides 0 % of DL
adjacencies because it cannot decide anything: `0.0 × anything = 0.0`.

## What this does and does not license

**Does:** it answers Step 3's own question — **B3's DL half matters, but not
yet, and for a sharper reason than I first gave.** A 4-UE-per-slot DL cap
applied to TwoTier would be capping an order that is a **constant**, not merely
a noisy one. For Reservation the DL cap is meaningful once channels differ
(its `-coef` reaches 49.5 % at 12 dB). **So CFG-2 unblocks Reservation's DL
half; TwoTier's needs a DL flow with a GBR target**, which no built scenario
has — every DL flow in the repo is `Delay` class with GFBR 0.

**Does not:** it says nothing about which DL tier would dominate on a contended,
channel-diverse downlink — that is exactly what the trace will answer once the
scenario exists. **It is not evidence that the DL comparator is broken**; it is
evidence that this evidence base never exercised it.

**And it bears directly on G1**, whose clause names a **downlink** command: the
scored statistic is uplink telemetry (P2-2), and the downlink flow it is
actually about is ordered by declaration order 98 % of the time.
