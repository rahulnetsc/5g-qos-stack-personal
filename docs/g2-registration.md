# G2's UL STOP flow — registered before building

**2026-09-05.** Per the standing rules and the queue's call: **build the UL
STOP flow; TB-size quantisation stays unbuilt with §20.1's measurement as
the reason.**

## What changed since G2's blockers were written, and it matters

G2's row names two blockers: the E-STOP flow is **DL** (`sim/fleet.py:179`,
qfi 85, PDB **5 ms**) while the named failure mode — the **BSR/SR desync** —
is uplink; and TB-size quantisation is unbuilt.

**Both are now better understood, and one of them is dissolved:**

1. **§20.1 measured that TB-size quantisation would not close G2** — replaying
   every UL grant through OAI's own `nr_find_nb_rb`/`nr_compute_tbs` left the
   padding distribution unchanged, **13,214 of 13,214 grants at padding 0**.
   It stays unbuilt for that reason.
2. **`docs/bsr-desync-result-2026-09-05.md` established that the desync route
   DOES NOT LATCH.** Truncation never fires (`short_trunc`/`long_trunc`: 0
   occurrences in every configuration), the emptiness route never fires
   (`fmt=="none"`: 0), and structurally a served UE's array is emptied only
   inside `on_ul_grant` — the same call that refills it.

**So G2's named failure mode cannot occur for an already-served UE, and
adding a UL STOP flow will not exhibit it.** That is a real finding about
G2's specification, not a build failure.

## What a UL STOP flow CAN measure, and it is the operative question

**The SR → grant → BSR round-trip against a 5 ms PDB.** The app co-design
guide states the cost directly: *"dynamic-scheduling latency (~4–8 ms BSR +
DCI round-trip on UL)"*, and recommends either a permanent CG occasion or
accepting that latency. **4–8 ms against a 5 ms budget is the whole question**
— and it is measurable here without any new mechanism.

## Expectations — statistic, level, direction, falsifier

| # | statistic | level | prediction | falsifier |
|---|---|---|---|---|
| **1** | UL STOP flow's **p98 delay** vs its **5 ms** PDB | per-arm ms | **FAILS on all three arms** — the SR round-trip alone (`sr_period_slots=10` at μ=2 = 2.5 ms, plus grant and BSR) is comparable to the entire budget | any arm holding p98 ≤ 5 ms on ≥ 8/10 seeds |
| **2** | the **DL** STOP flow's p98, same runs | per-arm ms | **PASSES on all three** — DL needs no SR and no BSR; the gNB schedules directly | DL failing while UL passes |
| **3** | the **UL−DL gap** on the same UE, same event rate | ms | **≥ 2 ms and dominated by the access chain**, not by contention | a gap under 1 ms, which would mean the round-trip is not the cost |
| **4** | `n_never_granted` on the STOP UE | count | **0** — a 0.2 Hz aperiodic flow shares a UE with continuous flows, so the UE is never cold | any non-zero |

**Prediction 2 is the control.** If DL also fails, the cost is contention
rather than the uplink access chain, and prediction 3's reading is void.

## The disposition this is expected to produce

**G2 will still not be scoreable as written**, and the reason will have
changed from *"the flow cannot reach the failure mode"* to **"the failure
mode does not occur, and the flow measures a different cost instead"**. If
that is what the data shows, the honest output is a **specification finding**
— G2 names a mechanism this simulator has now shown to be self-clearing —
rather than a G2 verdict.
