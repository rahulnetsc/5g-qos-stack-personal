# The guarantee table

**2026-09-07.** Every row scored or explicitly not scoreable with its reason.
Regenerate: `scripts/guarantee_scorecard.py` (`--attach`, `--selftest`,
`--denominators`). **90 scored rows across 30 clause parts × 3 arms.**

---

## THE TWO CARRIER CAVEATS — stated once, and they govern every M-6 row

**M-6 is the deployed per-slot UE cap**, `min(prb_count // 24, 8)`, ported from
`gNB_scheduler_dlsch.c:1019-1023`. The formula is faithful; **the value depends
on the carrier, and this repo's carrier is not the deployment's.**

| | PRB | cap |
|---|---|---|
| this repo's parametric cell (40 MHz, μ=2) | **55** | **2** |
| this repo's `sensor_dense` (30 MHz, μ=1) | 83 | 3 |
| **the deployment** (N_RB 106, μ=1) | **106** | **4** |

1. **cap = 2 is this carrier's faithful derivation.**
2. **cap = 4 is the deployment's value on half its bandwidth.**

**Neither is the deployment's system.** Both were run; **cap 4 is the number to
quote**, and the difference is not a uniform softening — **8 rows softer at
cap 4, 4 rows harsher, 66 unchanged.** A looser cap spreads service (helping
fairness and starvation) and lengthens tails (hurting max-gap and frame-age).

**And one headline does not survive M-6 at either value:** `sensor_dense`'s
*"PDCCH binds at 92 % of achievable, 40.7 % of slots at cap"* is **withdrawn**
— `cce_slots_at_cap` is **zero** and U-slot utilisation falls 0.84 → 0.336. The
UE cap binds first and leaves CCE slack. That figure was measured without the
deployed cap.

---

## The table

Success rate = runs in which the clause held, seeds **inside** each point.
Severity = **M02, protected fleet**, one population on every row.

| guarantee | clause part | PF | Res | **TwoTier** | deployment consequence |
|---|---|---|---|---|---|
| **G1** commands | p98 ≤ 95 ms (parametric) | 10/10 | 9/10 | **3/10** | Teleop feels sticky on 7 shifts in 10 on TwoTier. At **cap 4** unchanged at 3/10 |
| | p98 ≤ 15 ms (`sensor_dense`) | 10/10 | 10/10 | 10/10 | Dense sensors hold on every arm |
| **G2** STOP | UL STOP p98 ≤ 100 ms | 10/10 | 10/10 | 10/10 | **×19 margin — but on a scenario the plan does not specify.** See §"not built" |
| | **DL** STOP p98 ≤ 100 ms | 10/10 | 10/10 | 10/10 | GT-1.2's STOP is downlink; this is the clause's own direction |
| **G3** liveness | max gap ≤ 500 ms | 10/10 | 10/10 | **4/10** (cap 4: **2/10**) | Robots start looking dead on TwoTier under the cap |
| | zero gaps ≥ T_live | 10/10 | 10/10 | **6/10** (cap 4: 10/10) | |
| | p98 ≤ PDB *(= G1's statistic)* | 10/10 | 9/10 | **3/10** | The same number scored under two guarantees' names |
| **G5** video | ≥ 99 % PDU sets complete | 10/10 | **1/10** | **0/10** (cap 4: 2/10) | **Neither QoS arm delivers usable video.** Attach recovers Res to 10/10 |
| | frame age p95 ≤ 67 ms | 10/10 | 10/10 | **4/10** (cap 4: **0/10**) | |
| **G6** background | G1 stat within bound **and** shift ≤ +20 % | 24/40 | 25/40 | 20/40 | |
| | G3 stat, same | 37/40 | 38/40 | 33/40 | |
| | **G5 stat, same** | 36/40 | **0/40** | **0/40** | **With background present, neither QoS arm delivers complete video on any seed** |
| **G7** isolation | c1 victim PDU sets ≥ 99 % | 10/10 | 10/10 | 9/10 (cap 4: 6/10) | The victim is protected |
| | c1 victim camera p98 ≤ PDB | 10/10 | 10/10 | 10/10 | |
| | c1 victim telemetry p98 ≤ PDB | 10/10 | 10/10 | 10/10 | |
| | **c3 aggressor's OWN telemetry** ≤ PDB | 10/10 | 10/10 | 10/10 | Containment holds *inside* the misbehaving asset — GT-4.3's third part, never previously reported |
| | **c2 excess clipped at MFBR** | **1/10** | **0/10** | **0/10** | **No arm limits the aggressor**; both QoS arms pass 2.03× MFBR. MFBR bounds entitlement, not throughput — **a deployment expecting a rate limiter does not have one** |
| **G8** fairness | Jain ≥ 0.90 (parametric) | 10/10 | **2/10** (cap 4: 7/10) | **0/10** (cap 4: 5/10) | |
| | Jain ≥ 0.90 (`sensor_dense`) | 10/10 | **0/10** | **0/10** | |
| | **zero starvation epochs ≥ 1 s** (parametric) | 10/10 | **1/10** | **0/10** (cap 4: 6/10) | **A robot gets no uplink for an entire shift.** The Jain-only row read 9/10 and hid this |
| | same (`sensor_dense`) | 10/10 | **0/10** | **0/10** | |
| | no UE never granted (`sensor_dense`) | 10/10 | **0/10** | **0/10** | |
| **G9** join | warm re-handshake p95 ≤ 1 s | 1/1 · 16.5 ms | 1/1 · 19.1 | **1/1 · 168.4** | Passes on all arms; **TwoTier is 10× the others** |
| | attach-to-streaming ≤ 15 s | 1/1 · 145 ms | 1/1 · 148 | 1/1 · 282 | **Measures the APP handshake — there is no RA procedure**, so it is not attach |
| | post-RLF time-to-SLO ≤ 10 s | 1/1 · 1.17 s | 1/1 · 1.18 s | **0/1 — NO COMPLETION** | **TwoTier registers its RLF event and completes none.** A robot that loses radio does not come back |
| | neighbours unaffected | 1/1 | 1/1 | **0/1 · +3.08 ms [+2.22, +4.05]** | **A joining robot degrades its neighbours on TwoTier**, interval excluding zero |
| **G10** fleet | GBR contract met, per fleet size | **boundary 6** | **6** | **5** | §2 below |
| **G11** shift | every 60 s window conformant | 10/10 | 10/10 | 10/10 | Holds over 7.2 M slots, ×112 margin |
| | CoV(p98) ≤ 15 % across repeats | 1/1 · 0.014 | 1/1 · 0.052 | 1/1 · 0.015 | Reproduces run to run |
| **G12** safety order | **c4 never starve telemetry** | 10/10 | 10/10 | **10/10 — severity 0.98** | **TwoTier passes while 98 % of telemetry bytes are PDB-violated.** The predicate treats "starved" as M02 ≥ 0.99 and TwoTier sits at 0.98 — **a threshold artefact, not a clean pass** |
| | **first-violation order** | `[4]`×8 — **matches** | `[]`×10 — nothing breaches | **`[2,4]`×10 — INVERTED** | Specified order is 9 → 4 → 2. **TwoTier degrades camera before lidar**, the wrong way round |

## 2. G10's axis — the row that changed most

`n_ues ∈ {2,4,5,6,7,8,10,12,16}`, 10 seeds inside each point.

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | **9** | 10 | 10 | 9 | 0 | **6** · NON-MONOTONE |
| Reservation | 10 | 10 | 10 | 10 | 2 | 1 | 0 | 0 | 0 | **6** |
| TwoTier | 10 | 10 | 10 | **2** | 0 | 0 | 0 | 0 | 0 | **5** |

At **cap 4** the boundaries are identical (6 / 6 / 5) but TwoTier's decline is a
**slope** (10 → 9 → 6 → 2) rather than a cliff.

> **The cell hosts 5-6 robots, not the 8 previously published.** The arms are
> **near-identical, not 2× apart.** **A fleet sized on 8 is over-provisioned by
> ~30 %.** PF's non-monotonicity (9/10 at N=7, 10/10 at N=8) is reported, not
> smoothed; the boundary is the last passing point before the first failure.

## 3. G12's re-based ramp

The shipped ramp had **no verdict at all** under M-6 — 10-12 of 30 groups
breached at its own origin. Re-based by measurement (GT-3.2's certified-ceiling
rule applied to the capped cell): **×0.5 is the largest clean origin**; ×0.6
breaks. New ramp **×0.5 → ×2.0**. Every breach at every point is TwoTier's.

## 4. NOT SCOREABLE — with the reason, not a gap

| guarantee | part | why |
|---|---|---|
| **G4** | p99 ≤ 300 ms at 1 s / 5 s / 60 s — **0 of 3** | **Three independently fatal reasons.** (a) the artefact records **p98, not p99**, and p98 ≤ p99 so substituting is *optimistic*; (b) the axis is `duty_cycle`, not silence length, and under `_burstify` duty cycle moves message **size** with it — confounded; (c) `GAP_BUCKETS_MS` tops out at `[1000, inf)`, so **1 s and 60 s land in the same bucket** — the instrument cannot resolve the clause's own buckets even if the axis existed |
| **G11** | C2 drift | counters never wired; **6 of the C's 9 skip-reasons cannot exist here** |
| **G11** | C4 PASS/FAIL consistency | **satisfied by construction** — every run reports 0 failing windows, so it cannot fail |
| **G1** | p99.9 reported | a **reporting** obligation, not a bound; the artefact carries p98 only |
| **G2** | 100 % of STOPs (the **maximum**) and the §5.3 miss-rate bound | the artefact carries p98; p98 is weaker than the clause and is labelled, not equated |
| **G5** | per-2 s-window goodput ≥ GFBR | no windowed goodput recorded |
| **G10** | 7 of its 8 sub-clauses | only M07 is emitted per fleet size |
| **G6** | the **DL** half (GT-4.2, **P0**) | no DL background flow exists in any scenario |

## 5. WHAT IS NOT BUILT, and what it would cost

**Reported rather than expanded, per the standing instruction.**

- **The `committed_mult` load axis for G1/G3/G5/G8** — `committed_mult` exists
  only in `sim/scenarios/g12.py`; `sim/parametric.py` has no equivalent.
  Porting it is **~1 day**. Without it those four rows have a **fleet-size**
  boundary (§2, shared with G10) and no **load** boundary.
- **GT-1.2's saturated STOP scenario for G2** — needs a simultaneous-STOP
  trigger, UL+DL saturation, and GT-7.2's 50 storms/run, plus emitting the
  **maximum** rather than p98. **~1-2 days.** Until then G2's ×19 margin is on
  a scenario the plan does not specify, and it is the row most likely to be
  challenged.

**Both were in the order and neither was started. The four G9 parts and G4's
enumeration (item 5) were completed instead, since they cost minutes and
converted G9 from "no number" to a full row.**
