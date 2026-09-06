# The grant-density mechanism — one mechanism, four observations

> **SUPERSEDED IN PART, 2026-09-06 (same day), BY
> `docs/two-tier-settled-2026-09-06.md`. READ THAT FIRST.**
>
> **The central claim below is refuted on its own data by a change of units.**
> The correlation between grant count and the deferral tail is **ρ = +0.794
> when the tail is counted in GRANTS** and **ρ = +0.115, p = 0.21 — not
> significant — when it is measured in MILLISECONDS** (n = 120). "Skipped
> grants" has grant count in its own definition, so correlating the two is
> correlating a rate against its denominator. **Latency is in milliseconds,
> and in milliseconds the protected flow waits 105–135 ms (p98) on every arm
> in every cell**, whether that arm issued 2,048 grants or 25,221.
>
> **What survives:** intra-UE LCP deferral is real and measured (the flow
> rides on 0.5–3.3 % of its own UE's grants; zero deferral on `sensor_dense`,
> which has no sibling), the disadvantaged UE is **not** under-granted
> (1.003× the fleet median), and §2's refutation of *"Tier-1's objective
> favours periodic flows"* stands. **What does not survive is the claim that
> grant density explains the ARM differences.**
>
> **The replacement mechanism is service REGULARITY**, which survives in
> milliseconds: burstiness (gap p98/p50) predicts the protected flow's p98
> within each workload at ρ = +0.646 (parametric) and +0.698
> (`sensor_dense`), and TwoTier is the burstiest arm where it loses and the
> most regular where it wins.
>
> Kept unedited below for the record.

**2026-09-06.** Stated once, here, the way the cold-start lock-out is stated
in `docs/STATE.md` §3. **Four results previously carried as separate,
unexplained scheduler behaviours are one mechanism**, and the explanations
those four rows carried before are now either wrong or absent.

**Artefact** `sweeps/rerun-2026-09-06/traces.json` — 4 cells × 3 arms × 10
paired seeds, rank stream and grant stream, **bit-identical with the hooks off
on 120 of 120 cells**. **Probe** `scripts/trace_cells.py`, read by
`scripts/trace_read.py`.

---

## 1. The mechanism

A gNB grant is a transport block for a **UE**, not for a flow. Which of that
UE's flows the TB actually carries is decided **inside the UE**, by
logical-channel prioritisation (TS 38.321 §5.4.3.1), and **the gNB cannot see
that split** — a standing invariant of this repo and a property of the air
interface, not of this model.

So an arm does not choose how much of a UE's protected flow gets carried. It
chooses **how often that UE is granted at all**, and the LCP does the rest.

**Measured, and monotone in one direction:** the more grants an arm issues a
UE, the **smaller the share of them that carries the UE's small periodic
flow**, and the **longer that flow waits between the grants that do**.

| cell | arm | the UE's UL grants | % carrying 5QI 1 | skipped p50 | **skipped p98** |
|---|---|---|---|---|---|
| G7 aggressor | **PF** | 2,048 | **2.74 %** | 39 | **46** |
| G7 aggressor | Reservation | 11,084 | 0.64 % | 208 | 261 |
| G7 aggressor | **TwoTier** | 11,902 | **0.54 %** | 226 | **284** |
| attach control | PF | 2,048 | 2.73 % | 39 | 46 |
| attach control | Reservation | 6,366 | 1.01 % | 118 | 164 |
| attach control | TwoTier | 11,163 | 0.78 % | 174 | 286 |
| **attach** | PF | 2,156 | 2.54 % | 39 | 74 |
| **attach** | Reservation | 6,462 | 0.97 % | 126 | 154 |
| **attach** | **TwoTier** | 10,865 | 0.79 % | 124 | **340** |
| G5 residual | PF | 3,286 | 3.29 % | 31 | 41 |
| G5 residual | Reservation | 13,680 | 1.02 % | 132 | 171 |
| G5 residual | TwoTier | 25,221 | 0.77 % | 92 | 314 |

*"Skipped" counts grants the UE itself received that carried this flow
nothing* — the quantity that separates **"the flow waited because its UE was
not scheduled"** (a sort loss) from **"it waited through grants that carried
only its sibling's bytes"** (inside the TB). Every row here is the second.

**Spearman, stated because a monotone table can be eyeballed into anything:**

| relationship | per cell (n=12) | per run (n=120) |
|---|---|---|
| grants vs % carrying | **ρ = −0.760**, p = 0.004 | **ρ = −0.707**, p = 1.8e−19 |
| grants vs skipped p98 | **ρ = +0.795**, p = 0.002 | **ρ = +0.794**, p = 2.8e−27 |
| % carrying vs skipped p98 | **ρ = −0.839**, p = 0.0006 | — |

The arm ordering is the same in every cell: **PF grants least, TwoTier most**,
Reservation between — and the deferral tail follows in that order.

## 2. The four observations it explains

| # | observation | what its row said before | what the mechanism says |
|---|---|---|---|
| **1** | **The workload inversion.** TwoTier worst by 3.5× on the parametric mix (M01 p98 87.78 ms vs PF's 25.25), best on `sensor_dense` (11.00 vs 13.50). | *"Tier-1's objective favours periodic flows over saturating ones"* — **an unchecked inference, and refuted.** | Not a scheduler-ranking property. TwoTier's worst UE gets **1.003× the fleet median** UL bytes and is byte-rank 5.5 of 10 — it is not losing the sort. Its flow waits through **310 (p98) of its own UE's grants**. `sensor_dense` has one flow per UE, **no sibling, deferral tail 0** — which is why the arm that grants most wins there and loses on the mix. `docs/u1-inversion-result-2026-09-06.md` |
| **2** | **G7's inversion.** Both QoS arms deliver 2.0–2.1× MFBR; **PF, with no MFBR concept, contains at 1.05×**. | The overflow half was read from the C (the clamp bounds `_target`, not throughput). **Why PF contains better was unknown.** | **PF contains because it grants ~5.8× less** (2,048 vs 11,902), so its protected flow rides on **5.1× more** of the grants it does issue (2.74 % vs 0.54 %). **Not a fairness property of PF's ranking** — the same grant-density effect, seen from the side where it helps. |
| **3** | **The attach path makes TwoTier worse on latency**, M06 failures 14/40 → 40/40. | *"It returns locked-out UEs to contention"* — **plausible, unverified.** | Measurable now: the attach path takes TwoTier's grants to that UE from **11,163 → 10,865** while the deferral tail goes **286 → 340**, and against its own control the failing-seed count rises. More contention returns more UEs to being granted; the tail is where the cost lands. **Note the median worst-flow M06 p95 slightly *improves* (50.8 → 47.4 ms)** — the damage is in the tail across seeds, not the central value, which is exactly what a count-of-failing-seeds metric reads and a median does not. |
| **4** | **G5's residual after the lock-out clears.** | Carried as an open item at *"4/10"*. | **The item is empty, and the premise was wrong.** 4/10 is the **pre**-attach figure. Post-attach M05 is **0.993–0.997 on all three arms**; Reservation is 1/10 marginal and TwoTier 0/10. Nothing remains to explain. |

## 3. The attributional statement

**A headline that reads as a scheduler result is a UE-side LCP effect
identical across all three arms, and no scheduler change reaches it.**

The three arms are being compared on a statistic whose between-arm variance,
on any workload where a UE carries a small periodic flow beside a saturating
one, is dominated by how each arm's **grant pattern** interacts with a
mechanism that is **the same code in every arm** and that the scheduler
**cannot observe**.

This does not make the numbers wrong. TwoTier really does produce that p98 on
that workload. **It makes the attribution wrong**, and the attribution is what
*"is two-tier needed"* turns on.

## 4. Transfer to hardware

**The mechanism transfers; the magnitude does not.** LCP is real 3GPP
(`Bj` token buckets, PBR, BSD), and the gNB's blindness to the split is a
property of the air interface. A real gNB granting a UE in many small TBs
rather than few large ones will interact with that UE's LCP the same way.

**What does not transfer:** the size of the tail. It is a function of this
repo's `sim/ue_lcp.py` parameterisation and of the parametric mix's own
provisioning (5QI 1 is **0.3 % of its UE's UL bytes**), neither calibrated
against hardware. **310 skipped grants is this simulator's number, not a
prediction about a deployment.**

**And note what is *not* missing:** this is one of the few results where the
simulator is not short a mechanism. What is missing is **calibration** of one
it has.

## 5. What would have to be true for this to be wrong

Named so the next person can attack it cheaply rather than re-deriving it:

1. **If the deferral were a sort effect after all**, the deferred flow's UE
   would be under-granted. It is not — 1.003× the fleet median, byte-rank 5.5
   of 10.
2. **If it were specific to one arm's ranking**, the relationship would not
   hold across arms. It holds in all 12 cells, ρ = +0.79 per run over 120.
3. **If it were an artefact of the hook**, the runs would differ with the hook
   off. They do not — 120 of 120 bit-identical on `RunRecord.to_dict()`.
4. **If it were specific to the parametric mix**, `sensor_dense` would show it
   too. It does not: one flow per UE, **deferral tail 0**, and the arm
   ordering inverts.
