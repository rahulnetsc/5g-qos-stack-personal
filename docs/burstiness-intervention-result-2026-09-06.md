# Burstiness: LEVER, not symptom — result

**Registered** `docs/burstiness-intervention-registration.md`, before the run.
**Artefact** `sweeps/burstiness-2026-09-06/burst.json` — α ∈ {0, 0.25, 0.5,
0.75}, k = 4 slots, n = 10 paired seeds, 20,000 slots, N = 8, parametric mix.
**Probe** `scripts/burstiness_probe.py`.

## Verdict: registered outcome **O1 — burstiness is a LEVER.**

---

## 1. Manipulation check — read first, and it passes

| α | burstiness (p98/p50) | gap p50 ms | gap p98 ms | UL grants |
|---|---|---|---|---|
| **0.0** (control) | **23.00** | 1.25 | 161.62 | 9,424 |
| 0.25 | 4.58 | 32.00 | 151.00 | 9,918 |
| 0.5 | 5.00 | 12.50 | 122.75 | 10,119 |
| **0.75** | **5.00** | 17.00 | 116.50 | 9,959 |

**Burstiness 23.00 → 5.00, a 78.3 % reduction** against a registered
threshold of 30 %. The damper does what it is named for, so the outcome below
is about the hypothesis and not about an inert knob.

## 2. Outcome — paired within-seed difference in the protected flow's p98

| α | median p98 | **paired mean Δ** | 95 % CI | better/worse |
|---|---|---|---|---|
| 0.25 | 92.12 ms | **−16.79 ms** | **[−40.57, −1.58]** | **8 / 2** |
| 0.5 | 98.12 ms | **−13.22 ms** | **[−24.85, −2.02]** | **8 / 2** |
| 0.75 | 91.50 ms | −18.31 ms | [−48.16, +9.82] | 7 / 3 |

Control (α = 0) median p98: **98.62 ms**, against a 100 ms PDB.

**At α = 0.25 and α = 0.5 the interval excludes zero.** At α = 0.75 it does
not — the largest damping is *not* the best-evidenced, and reporting it as
the headline would be picking the biggest number over the tightest one.

## 3. It is not paid for — O4 does not fire

| α | M07 met | UL bytes delivered |
|---|---|---|
| 0.0 | 8.00 | 41,715,910 |
| 0.75 | 8.00 | **42,270,006** |

**GBR delivery is unchanged (8.00 at every α) and total UL throughput is
slightly HIGHER, not lower.** So this is not a latency-for-throughput trade.

## 4. The unplanned confirmation, and it is the most useful part

**The damper reduced burstiness while INCREASING grant count** — 9,424 →
9,959 — and the protected flow's p98 improved.

**That is an independent, interventional refutation of the grant-density
claim I published on 2026-09-05 and retracted on 2026-09-06.** The retraction
rested on a change of units (ρ = +0.794 in grants, +0.115 p = 0.21 in
milliseconds), which is an observational argument. This is the same
conclusion reached by moving the variable: **more grants, less bursty, better
latency.** Grant count and latency are not merely uncorrelated in time — they
move in *opposite* directions under an intervention that targets regularity.

## 5. No dose-response beyond α = 0.25 — reported, not smoothed

Paired means are −16.79, −13.22, −18.31 for α = 0.25, 0.5, 0.75: the same
sign and overlapping intervals, with **no monotone trend**. Burstiness itself
saturates identically (4.58 → 5.00 → 5.00).

**Read as: the effect is close to binary in this range** — damping at all
captures it, and damping harder does not add. Registered outcome O5
(non-monotone) is **not** fired, since the sign is stable and the intervals
overlap; but the absence of a dose-response is recorded because a reader
expecting one would misread the α = 0.75 row.

## 6. What this establishes, and what it does not

**Establishes.** Service regularity is a **cause** of the protected flow's
tail latency on this workload, not a co-symptom. `docs/two-tier-settled-
2026-09-06.md` §1.1 stands, and its rank-5 entry ("reduce TwoTier's service
burstiness — measured correlation, **untested** intervention") is now
**tested**.

**Does not establish.** That this damper should ship. Per the registration's
§7: the Python model matches the deployed scheduler, and a divergence probe
that wins on one metric on one workload is not an argument for changing the
product. **`anti_hysteresis` stays off by default and is byte-identical to
the shipped scheduler when off** — asserted, not assumed.

**Also not established:** that it transfers to `sensor_dense` (where TwoTier
is already the most regular arm at 1.4 and already wins), or to any workload
without a saturating sibling. **One workload, one fleet size, one k.**

## 7. What it changes for the product argument

The strongest prior claim was that TwoTier's latency disadvantage was
attributable to a UE-side mechanism no scheduler could reach. **That is now
too strong.** The LCP deferral is real and is not the arm differentiator; the
*temporal pattern of the gNB's own ranking* is, and it is scheduler-side and
demonstrably movable — **−13 to −17 ms of a 98 ms p98, at no measured cost in
GBR delivery or throughput.**

**This also strengthens §4 of the settled document**: a configuration or
slot-budget formulation delivers regularity *by construction*, and regularity
is now a demonstrated cause rather than a correlate.
