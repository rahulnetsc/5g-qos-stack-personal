# What holds TwoTier back — the settled account

**2026-09-06.** One document, replacing an account spread across four and
**revised three times as mechanisms were traced**. Every claim carries its
artefact or its C citation. Where something is an inference nobody has
checked, it says so.

**Read §0 first.** The reason the answers have been confusing is that two of
the three previous attributions were wrong, **and this document retires the
second of them — which was mine, published two days ago.**

---

## 0. The three attributions, and which survive

| # | attribution | status |
|---|---|---|
| 1 | *"Tier-1's objective favours periodic flows over saturating ones"* | **REFUTED 2026-09-06.** All 10 parametric UEs carry an identical flow mix, so the UE-level sort cannot express a preference between flow kinds. The disadvantaged UE receives **1.003× the fleet median** UL bytes, byte-rank 5.5 of 10. `sweeps/phase2/u1_trace.json` |
| 2 | *"Grant density: more grants → smaller share carrying the protected flow → longer deferral"* | **REFUTED HERE, and it was my own.** The correlation is **ρ = +0.794 in grant COUNTS** and **ρ = +0.115, p = 0.21 — not significant — in MILLISECONDS** (n = 120, `sweeps/rerun-2026-09-06/traces.json`). "Skipped grants" scales with grant count almost by construction. **Latency is in milliseconds, and in milliseconds the wait is the same on every arm: p98 gap 105–135 ms in every cell, every arm.** |
| 3 | **Service REGULARITY** | **SURVIVES.** §1.1 |

**Why (2) looked right.** Density and regularity are confounded across these
workloads: TwoTier grants **most** on the parametric mix (where it is
burstiest) and **fewest** on `sensor_dense` (where it is most regular). Only
regularity survives when the statistic is expressed in the units latency is
measured in.

**The transferable lesson is this project's own, applied to me:** a
correlation of **+0.79** collapsed to **+0.115** under a change of units,
because the quantity I correlated (skipped *grants*) has grant count in its
own definition. **Correlating a rate against its own denominator is the
population defect wearing a correlation coefficient.**

---

## 1. What actually holds it back

### 1.1 The scheduler's own doing

| effect | evidence | class |
|---|---|---|
| **Service burstiness of the UE-level ranking — the one that survives.** TwoTier serves a UE's protected flow in **clusters then long gaps**: gap p50 **1.12 ms**, p98 **121.6 ms** — a burstiness ratio of **125**, against PF's **1.3** and Reservation's **1.2**. Within a workload, burstiness predicts the protected flow's p98: **ρ = +0.646, p = 1.2e−4** (parametric) and **ρ = +0.698, p = 1.8e−5** (`sensor_dense`), n = 30 each. | `sweeps/phase2/u1_trace.json` | **MEASURED** |
| **And it explains the inversion without any other mechanism.** Same scheduler, opposite regularity, opposite result: parametric burstiness **125 → p98 92.1 ms (worst arm)**; `sensor_dense` burstiness **1.4 → p98 11.2 ms (best arm)**. Reservation is the most regular arm on parametric (1.2) and has the best p98 (29.1). | same | **MEASURED** |
| **Grant fragmentation.** For the same ~15,000 delivered bytes, TwoTier uses **99 services at 148 B** against PF's **62 at 240 B**; fleet-wide, **11,804 grants at 353 B mean vs PF's 1,630 at 2,544 B** — 7.2× more, 7.2× smaller, for the same total. | `sweeps/phase2/u1_trace.json` | **MEASURED.** Its *latency* consequence is **not** established — see §3 |
| **Tier-1's SCA loop does not converge**: 41 of 50 solves hit `_SCA_MAXITERS = 150`; 82 % of targets are where a damped sequence stood, not a fixed point. | `docs/tier1-lp-analysis-2026-09-05.md` | **MEASURED**, and **faithful** — the cap is ground truth (`IA_P5G_TIER1_SCA_MAXITERS`) |
| **Declaration order decides 14.6 % of TwoTier's UL adjacencies in G7's aggressor cell** (0.3–5.7 % elsewhere). | `sweeps/rerun-2026-09-06/traces.json` | **MEASURED; its effect is UNCHECKED** — registered, not investigated (`docs/declaration-order-in-g7-registration.md`) |

### 1.2 Not the scheduler's doing — UE-side or workload, and wrongly attributed

| effect | evidence | why it is not the scheduler |
|---|---|---|
| **Intra-UE LCP deferral EXISTS.** The protected flow rides on **0.5–3.3 %** of its own UE's grants; on `sensor_dense`, with one flow per UE, **99.5 % and a deferral tail of zero**. | `traces.json` | The gNB **cannot see a UE's intra-TB split** — standing invariant, and a property of the air interface. **But it does not differentiate the arms in time** (§0 row 2), so it explains the *workload* difference, not the *arm* difference |
| **The cold-start lock-out's FREQUENCY.** | `docs/attach-path-result-2026-09-05.md` | Hardware always grants at attach (RA/msg3); this simulator has no such path. **Every blackout rate and admissible-fleet figure measured without it is an upper bound** |
| **G12's ordering** | permutation 104 flips it on all 5 seeds | a deterministic function of flow-list position, with no physical referent |
| **G12's published clause-4 figures** | `docs/g12-collision-fix-result-2026-09-06.md` | a DL/UL flow pair shared one buffer; most of the published background throughput was DL grants draining a UL queue |
| **The parametric M01 comparison itself** | 100 ms PDB vs `sensor_dense`'s 15 ms | absolute milliseconds across workloads is a category error; the inversion survives normalisation (0.878 vs 0.733 of budget) and is reported that way |

### 1.3 Simulator gaps

| gap | size | evidence |
|---|---|---|
| **Configured Grants / SPS absent** | the mechanism the adoption study credits for **30/30 vs 2/30** on `sensor_dense` | deleted at Phase 2 two-tier commit 1, deliberately, to match the deployed scheduler |
| **Crumb fraction 4.96 % against hardware's 48–52 %**, crumb size 146 B against 72–107 B | **~10× on the headline UL statistic** | the only direct hardware comparison here; TB quantisation was *measured* not to close it (13,214 of 13,214 grants at padding 0, unchanged) |
| **LCP parameterisation uncalibrated** | the deferral tail's magnitude is this repo's `sim/ue_lcp.py`, not a prediction | **INFERENCE — nobody has compared it to hardware** |
| **No RA/msg3 attach path** | drives 1.2's frequency row | — |

### 1.4 Product findings — the C's own, faithfully reproduced

**These are not simulator problems and must not be "fixed" here.**

| finding | citation | measured |
|---|---|---|
| **Tier-1.5's UL floor cannot arm in the fault it exists for.** Its gate reads `has_pending_gbr`, set only inside the loop that skips every zero per-LCG entry — the condition defining the fault. | `ia_p5g_scheduler.c:2325` | **0 firings in 32,000 evaluations** per starved UE |
| **Reservation has no floor at all** — the complement | — | same fault, no remedy even in principle |
| **MFBR bounds entitlement, not throughput.** The clamp limits `_target`; the overflow is reclassified best-effort and stays deliverable. | — | **2.0–2.1× MFBR delivered on both QoS arms** |
| **The per-LCG array's cold-start deadlock** | `gNB_scheduler_ulsch.c:41-70` | joiner carries positive `bytes_reported` with an all-zero array on **51.3 %** of slots |

---

## 2. What would actually make it better — ranked by evidence

| rank | change | type | evidence | expected gain |
|---|---|---|---|---|
| **1** | **Arm Tier-1.5's floor on a condition that can be true in the fault.** Gate it on *"UL backlog reported AND per-LCG estimate empty"* rather than on `has_pending_gbr`. | **PRODUCT CODE CHANGE** (the deployed C) | **measured**: 0 of 32,000 | Removes the only designed remedy's dead gate. **Not a sim change** — this repo must keep reproducing the fault |
| **2** | **Supply a BSR at attach.** | **PRODUCT CONFIGURATION** — hardware already does this via RA/msg3 | **measured**: starvation clears at every fleet size, arm and seed; G5 Reservation 7/10 → 1/10, TwoTier 4/10 → 0/10; G10's boundary becomes common at 8 | Largest measured effect of any change tried |
| **3** | **Decide what MFBR is for.** It bounds entitlement, not throughput — so G7 clause 2 fails by construction. | **SPECIFICATION** | **measured**: 2.0–2.1× delivered; the C read is established | Either the guarantee's wording changes or the C gains a rate limiter. **Owner: the test-plan/design owner** |
| **4** | **Give Reservation a floor** | **PRODUCT CODE** | the complement of #1 | Unknown — no floor exists to measure |
| **5** | **Reduce TwoTier's service burstiness** (§3) | **PRODUCT CODE** | **measured** correlation, **UNTESTED** intervention | ρ ≈ 0.65–0.70 within workload; the causal step is unverified |
| **6** | `array("d")` for `hol_delay_samples_s` | sim only | measured ~12 % of residual | Not a scheduler improvement; listed so it is not mistaken for one |

**Deliberately absent:** the direct-HiGHS swap and the Tier-1 reformulation.
A **free** LP buys only **1.60×** on TwoTier's driver, and `_OBJ_SCALE`
already took the correctness case (**11.3 % → 98.7 %** exact). Re-opening
either needs a new measurement.

---

## 3. Is grant density tunable? — the question answered directly

**Short answer: grant density is not the lever, so tuning it is not the
question. Service REGULARITY is the lever, and it IS scheduler-side.**

**Why density is not the lever.** §0 row 2: the density correlation is
ρ = +0.794 in grant counts and **+0.115, p = 0.21 in milliseconds**. A UE's
protected flow waits **105–135 ms (p98) on every arm in every cell**
regardless of whether that arm issued 2,048 or 25,221 grants.

**There IS a real density knob, and it is worth naming so it is not
rediscovered as a lever:** `nrmac->min_grant_prb` — a **static gNB config
constant**, default 5, and a deliberate deployment choice for the
calibration campaign (486/486 `NPRB 5` lines in
`calibration-logs/twotier_startup_gnb.log`). Raising it makes grants fewer
and larger. **On the evidence above it should not be expected to move
latency**, and predicting that it would is exactly the inference this
document retires.

**What the evidence supports instead.** Burstiness predicts p98 within each
workload (ρ = +0.646 / +0.698) and the arm ordering follows it in both
directions. TwoTier's ranking has **hysteresis**: `coef = (base_q + urg) ·
hyp_tbs_bytes` grows with a UE's virtual queue and urgency, so once a UE
wins it keeps winning until drained (gap p50 **1.12 ms** — consecutive
slots), then loses for a long stretch (p98 **121.6 ms**). PF's EWMA
inherently rotates and produces a near-constant cadence (ratio **1.3**).

**So the honest answer to "is it a scheduler question at all": yes — but not
the question that was being asked.** It is not "how many grants" but "how
evenly spaced". That is a property of the ranking's temporal dynamics, and
a scheduler can change it — by damping the urgency term, by an anti-hysteresis
penalty on a UE served in the previous slot, or by a service-interval target.

**What is NOT established, stated plainly:** that reducing burstiness
*improves* p98. The correlation is measured; **the intervention has never
been run.** It is rank 5 in §2 for exactly that reason. **The cheapest test
is a diagnostic arm with a per-UE anti-hysteresis penalty, and a
within-seed comparison of burstiness and M01 — roughly one campaign, ~20
minutes at n=10.**

**And LCP is not the answer here.** Deferral exists (0.5–3.3 % carrying) but
does not differentiate the arms in time, so LCP parameterisation explains the
*workload* difference (sibling vs no sibling) and not the *arm* difference.

---

## 4. The configuration approach, revisited

**The case changes, and for a better reason than the one that closed it.**

**What closed it:** *"PDCCH never binds at the fleet sizes measured"* — CCE
utilisation **7–9 %** while UL PRB sat at **93 %** on the parametric mix.
The analysis recorded its own re-open condition: *"a workload that moves CCE
utilisation could reopen the gate."*

**That condition is met.** On `sensor_dense`, PDCCH **binds**: U-slots at
**92.2 % of achievable** and **40.7 % of slots at the per-slot cap**, against
the parametric mix's 4.4 % and 0 % (`docs/cce-binding-2026-09-06.md` — and
note the achievable ceiling is **0.70**, not 1.0, for a UL-only workload;
reading 0.6357 against 1.0 gives the opposite conclusion).

**But the stronger argument is the new one.** A configuration-plus-slot-budget
formulation assigns a UE a **periodic, pre-agreed** transmission opportunity.
Its defining property is not that it uses fewer PDCCH resources — it is that
service becomes **regular by construction**, and regularity is the lever this
document establishes. **Configured Grants are the mechanism that guarantees
the property the measurement points at**, which is a substantially better
case than the PDCCH-budget one and is independent of whether PDCCH binds.

**Note what this also does: it supplies a mechanism for a result the adoption
study asserts and this branch cannot reproduce** — 30/30 vs 2/30 on
`sensor_dense`, credited to Configured Grants, which are deleted here.

### What it would need

**Objective.** Maximise served GBR entitlement subject to meeting each
configured flow's service interval — i.e. the decision variable is *which
flows get a periodic allocation and at what period*, not *who wins this
slot*.

**Constraints, and the third is the one this repo can now supply:**
1. **PRB per slot** — already binding at 93 % on the parametric mix.
2. **CCE per slot, per slot-kind** — binding on `sensor_dense`; the
   direction-gated per-slot-kind breakdown already exists
   (`cce_utilization_by_slot_kind`), and the **per-slot distribution**, not
   the mean, is what a binding claim needs (2,308 slots at the cap).
3. **A service-interval target per flow** — the constraint that makes it a
   *regularity* formulation rather than a throughput one.

**Cost to test as a divergence arm.** It is a **new scheduler arm**, not a
tweak: a periodic allocator plus an admission rule, composed like the
existing arms so `regime_sweep.run_cells` scores it unchanged. **It does not
require restoring SPS to `two_tier.py`** — and must not, since the rule is
that the Python model matches the deployed scheduler. It is a **divergence
arm**, labelled as such, whose purpose is to measure what the deployed
scheduler gives up.

**Estimated: one scheduler module + one registration + one campaign.**
Against measured comparators, a campaign of this shape is **~20 min at n=10
on both workloads**. The build is the cost, not the run.

**And the acceptance criterion should be regularity, not throughput** — a
divergence arm that wins on throughput and not on burstiness would not be
testing the mechanism this document identifies.

---

## 5. What remains unchecked, listed so nothing here is over-read

1. **That reducing burstiness improves latency.** Correlation measured;
   intervention never run. §3.
2. **Whether G7's inversion survives a flow-list permutation.** Registered.
3. **Whether this repo's LCP parameterisation matches hardware.** Uncalibrated.
4. **Whether the deployed C converges where this port's SCA does not.** There
   is **no Tier-1 ground truth in this repo** (zero `IA-P5G` lines in
   `calibration-logs/`), so it is unanswerable by measurement here.
5. **G9's clause-4 sign**, where treatment and instrument cannot be separated.
