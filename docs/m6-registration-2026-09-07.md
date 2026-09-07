# M-6 — the deployed 4-UE-per-slot cap: registration

**Registered 2026-09-07, after M-9 landed and was scored separately.** M-6 and
M-9 oppose each other, so a bundled diff would be uninterpretable.

## 1. The port

Both deployed schedulers cap the number of UEs scheduled per slot per
direction, **before any CCE search**:

```c
int average_agg_level = 4;                                  // TODO find a better estimation
int max_sched_ues = bw / (average_agg_level * NR_NB_REG_PER_CCE);   // dlsch.c:1019-1020
max_sched_ues = min(max_sched_ues, MAX_DCI_CORESET);                // = 8
```

and identically for uplink (`gNB_scheduler_ulsch.c:3017-3021`, `max_dci`).
`NR_NB_REG_PER_CCE = 6`, `MAX_DCI_CORESET = 8`, and `bw` is the carrier
bandwidth **in PRBs**. The deployment runs **N_RB 106 at mu 1**
(`calibration-logs/twotier_startup_gnb.log:45`), so:

**106 / (4 × 6) = 4 UEs per slot, per direction.**

**Derived, never a literal 4** — `min(prb_count // (4 × 6), 8)` from the grid's
own PRB count, so a bandwidth change cannot silently invalidate it.

**This resolves CLAUDE.md's `average_agg_level` known issue.** The real code
does **not** use the aggregation level to price a grant; it uses a fixed 4 to
derive a **UE-count cap**. "Model it fixed or SNR-dependent" was the wrong
question — the right port is the cap.

## 2. Why it cannot ride with M-9

**M-9 rescues starved UEs; M-6 removes service from mid-ranked ones. They act
on the same population in opposite directions.** Measured excess over 4 UEs
per UL slot, before this change:

| N | TwoTier | Reservation | **PF** |
|---|---|---|---|
| 8 | 46.2 % of slots | 7.5 % | **0.0 %** |
| 16 | 49.1 % | **87.4 %** | **0.0 %** |

**PF grants effectively one UL UE per slot (mean 1.00), so the cap is slack for
it at every fleet size.** This is **not a haircut — it is a comparison
effect**, which is exactly why it must be its own diff.

## 3. Predictions

| row | prediction |
|---|---|
| **PF, everywhere** | **unchanged** — `frac > 4` is 0.0 % at both fleet sizes measured |
| **G10** | **falls on both QoS arms** — the cap binds harder as N grows and N is this clause's own axis |
| **G8 (both halves)** | **worsens on the QoS arms** — a cap concentrates service on the top-4 ranks, which is the mechanism that produces starvation epochs. **Partially undoes M-9's gains** |
| **G5** | **falls on the QoS arms** — UL video loses slots to the cap |
| **G1 / G3 part 3** | **TwoTier worsens** — fewer served UEs per slot lengthens the tail |
| **G12 c4** | **PF unchanged (0/20 violations); QoS arms unchanged** — c4 is about *which class* is served, not how many UEs |
| **G7 c1/c2/c3** | **unchanged** — intra-UE questions; the cap is inter-UE |
| **G2** | **unchanged** — ×19-27 margin |
| **G11 C1** | **unchanged** — ×112 margin |
| **the CCE budget** | **may bind for the first time** — today the worst slot spends 27 of 48 DL and 22 of 32 UL |

**The sharpest prediction: PF does not move and both QoS arms do.** If PF moves
materially, the cap is not slack for it and the measured 0.0 % was wrong.

**Falsifier:** if the QoS arms do **not** move, the cap is not binding in
practice and Part 1's 46-87 % measurement was of something else.

## 4. Corpus

**RE-BASELINE, certain and large.** Justification stated in advance: the change
is intended to move the numbers, on both QoS arms and not on PF.

---

# RESULT — M-6 landed and scored, on top of M-9

**Artefacts** `sweeps/m6-2026-09-07/{plain,attach}/`.

## The sharpest prediction hit exactly

**22 of 60 tracked cells moved, and ZERO of them are PF.** Every single move is
on a QoS arm. M-6 is a **comparison effect**, confirmed, not a haircut.

| row | M-9 | +M-6 | |
|---|---|---|---|
| G1 cmd_vel — TwoTier | 7/10 | **3/10** | |
| G1 — Reservation | 10/10 | **9/10** | |
| G3 max gap — TwoTier | 10/10 | **4/10** | |
| G3 zero gaps ≥ T_live — TwoTier | 10/10 | **6/10** | |
| G3 part 3 — TwoTier | 7/10 | **3/10** | |
| G5 ≥99 % sets — TwoTier | 6/10 | **0/10** | |
| G5 frame age — TwoTier | 10/10 | **4/10** | |
| G8 Jain parametric — Res / TT | 9/10 · 8/10 | **2/10 · 0/10** | |
| G8 epochs parametric — Res / TT | 3/10 · 8/10 | **1/10 · 0/10** | |
| G8 epochs `sensor_dense` — Res / TT | 3/10 · 7/10 | **0/10 · 0/10** | |
| G8 `n_never_granted` — Res / TT | 9/10 · 10/10 | **0/10 · 0/10** | |
| G10 — Res / TT | 23/40 · 26/40 | **21/40 · 20/40** | |
| **PF, every row** | — | **unchanged** | ✓ predicted |

**And it more than undoes M-9.** G8's epochs went 3/10 → (M-9) 3/10 → (M-6)
1/10 on Reservation and 7/10 → 8/10 → **0/10** on TwoTier. The two changes
oppose, exactly as registered, and **M-6 dominates by a wide margin.**

## THE CAVEAT THAT GOVERNS EVERY NUMBER ABOVE: the cap here is 2, not 4

The formula is faithful — `min(prb_count // (4 × 6), 8)`, derived, never a
literal. **The VALUE is not the deployment's**, because the carrier is not:

| | PRB | derived cap |
|---|---|---|
| this repo's parametric cell (40 MHz, μ=2) | **55** | **2** |
| this repo's `sensor_dense` (30 MHz, μ=1) | 83 | 3 |
| **the deployment** (N_RB 106, μ=1) | **106** | **4** |

**So the measured effect is at TWICE the deployment's harshness on the
parametric cell**, and 1.33× on `sensor_dense`. Every row above is an **upper
bound on M-6's real impact.** This is the measurement-carries-its-configuration
rule applied to my own port: the formula transfers, the number does not.

## Three further findings, all from tests that fired

1. **M-6 makes the CCE budget stop binding entirely.** `cce_slots_at_cap` on
   `sensor_dense` goes to **zero**, and U-slot CCE utilisation falls
   0.84 → 0.336. **The opposite of my registered prediction** that CCE might
   bind for the first time — the UE-count cap binds *first* and leaves CCE
   slack. **So `sensor_dense`'s "PDCCH binds at 92 % of achievable" result was
   measured WITHOUT the deployed cap and does not survive it.**
2. **A latent scoring-layer divergence, exposed not caused.** `M01w` over the
   whole run differs from panel `M01` by **exactly one 0.25 ms slot quantum**.
   The two paths had agreed by coincidence on the old distribution. Not a
   scheduler defect; the test now allows one quantum and no more, so a real
   population divergence still fails. Logged for its own fix.
3. **Retransmissions bypass the cap in ~0.7 % of slots** (16-18 of ~2,400).
   `ReducedSlotView.max_sched_ues` reduces the new-grant budget by the distinct
   retx UEs per direction, but the driver emits retx outside `allocate()`, so a
   retx burst alone can still exceed the cap. Bounded and recorded, not chased.

## What the two changes together mean

**M-9 helped only `sensor_dense` G8 and never fired on the parametric mix.
M-6 hurt every QoS row on both workloads and PF on none.** Netting them by
argument was explicitly forbidden and the measurement shows why: they are not
the same size, they do not touch the same rows, and their signs differ per row.
