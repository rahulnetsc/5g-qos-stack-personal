# Sim gap or scheduler shortfall? — the classification table

**2026-09-06. Built from what exists, before running anything**, so that the
third column is an honest audit rather than a summary written after the fact.

The question every row answers: **does this result transfer to hardware, and
if not, what specifically does hardware have that this does not?**

---

## 0. How to read column three

The point of this document is column three. A classification is only as good
as what it rests on, and several of ours currently rest on a story.

| tag | what it means | why it is trustworthy or not |
|---|---|---|
| **T — trace** | per-slot / per-grant instrumented evidence from a run | the strongest thing here. It observed the mechanism firing (or not) rather than inferring it. |
| **C — read of the deployed C** | the mechanism was located in `oai-branches/` source | strong for *structure* ("this gate exists and is reachable only under X"). Says nothing about *frequency* on hardware. |
| **X — registered control** | a pre-declared A/B whose falsifier could have fired | strong for causal attribution within the sim. Scope-limited to what the control actually varied. |
| **I — inference** | a plausible mechanism nobody has checked | **not evidence.** This project has recorded four separate cases of an unchecked forward note being wrong, in four different ways. |

**A row whose classification rests on `I` alone is a story.** There are
**six** of them below, and the largest unexplained result is one.

---

## 1. Settled and citable

| # | observation | classification | rests on |
|---|---|---|---|
| **S1** | **The cold-start lock-out.** A UE whose `estimated_ul_buffer_per_lcg` is all-zero enters the UL sort with `has_gbr=False` / `pdb_ms=9999`, loses to every UE holding QoS state, and cannot earn the grant that would repopulate the array. | **Split: scheduler gap in MECHANISM, sim gap in FREQUENCY.** | **T + C + X.** Trace: the joiner carries positive `bytes_reported` with an all-zero array on **51.3 %** of its slots; Tier-1.5's floor fires **0 times in 32,000 evaluations** per starved UE. C: its gate reads `has_pending_gbr` (`ia_p5g_scheduler.c:2325`), set only inside the loop that skips zero entries — the exact condition its own comment names as the fault. X: supplying an attach BSR clears **four** separate observations at once, and `n_never_granted > 0 ⟺ M08 floored` has **zero counterexamples in 144 runs**. |
| **S2** | **G2's BSR/SR desync does not latch.** | **Not a defect in either — the fault self-clears.** | **C + code read.** The per-LCG array is zeroed only inside `on_ul_grant`, which then refills it. There is no state in which it stays stale across grants. This is why G2 has no verdict rather than a failing one. |
| **S3** | **Configured Grants / SPS absent.** | **Deliberate sim gap.** Deleted at Phase 2 two-tier commit 1 to match the deployed scheduler, which defers SPS to a phase never built. | **Repo history + C.** Not an inference at all. |

**S1's hardware verdict, stated precisely because it is the one most likely to
be over-read:** the *mechanism* is the product's and transfers whole — the
gate, the sort, and the dead rescue are all in the deployed C. The *frequency*
does not: hardware reaches the fault only through cold attach, and hardware
always grants at attach (RA/msg3, which this simulator has no path for). **So
the right statement to a hardware audience is "your Tier-1.5 floor cannot arm
in the fault it names", not "your scheduler starves UEs at the rate we
measured".**

---

## 2. Not settled — ranked, with what each currently rests on

| # | observation | current classification | rests on | honest status |
|---|---|---|---|---|
| **U1** | **The workload inversion.** TwoTier is **worst by 3.5×** on the parametric mix (M01 p98 protected: PF 25.25 / Res 23.00 / **TT 87.78** ms) and **best** on `sensor_dense` (PF 13.50 / Res 14.25 / **TT 11.00** ms). | *"Tier-1's objective favours periodic flows over saturating ones."* | **I — nothing.** | **A story.** The largest unexplained result in the campaign, and it bears directly on *"is two-tier needed"*. No trace has been taken. |
| **U2** | **G7's inversion.** Both QoS arms deliver **2.0–2.1× MFBR**; **PF, which has no MFBR concept at all, contains the aggressor at 1.05×**. | Two halves, and only one is established. **(a)** *Why the QoS arms overflow*: the MFBR clamp limits `_target` (the GBR obligation); the excess is reclassified best-effort and stays deliverable. **(b)** *Why PF contains it*: unknown. | **(a) C — established.** **(b) I — nothing.** | **Half a story.** (b) is the half the client will ask about, because it is the one that reads as "your QoS scheduler is beaten by the naive one". Whether PF's containment is a **fairness property** (transfers) or an **artefact of this traffic mix** (does not) is exactly what is unknown. |
| **U3** | **The attach path makes TwoTier worse on latency.** The same intervention that clears four lock-out observations takes TwoTier's M06 failures from **14/40 to 40/40**. | *"It returns locked-out UEs to contention."* | **I — nothing.** | **A story, and an uncomfortable one:** our own remedy degrades a metric by 3×. If the mechanism is real it is a genuine scheduler finding; if it is an artefact of seeding a *full* BSR estimate rather than a realistic one, it is ours. |
| **U4** | **G5's residual after the lock-out clears.** | — | **T (the numbers are measured).** | **The premise needs correcting before this is worth tracing.** Pre-attach: Res **7/10**, TT **4/10** seeds failing M05. Post-attach: Res **1/10 marginal**, TT **0/10**. So the residual is *one marginal Reservation seed*, not 4/10 — the 4/10 is the pre-attach figure. **This item is very nearly empty and should drop below U5.** |
| **U5a** | **G9 clause 4's sign.** Neighbour p98 is **worse** in the treatment on TwoTier (+3.08 ms [+2.22, +4.05] warm) — backwards from the control's own logic, since the control keeps the joiner transmitting *continuously*, so neighbours should be *better* when it is intermittently absent. PF and Reservation show the expected sign (−0.62 to −1.77). | Four candidates, **none tested**: (a) re-join perturbs Tier-1's demand vector, forcing capped SCA re-solves; (b) `reset_ue()` clears the joiner's fairness ledger so it outranks neighbours; (c) `due_this_slot()`'s shared insertion order; (d) **the re-join seed itself**. | **I ×4.** | **A story with a confound.** (d) is not separable today: clause 4 *had* to be measured with the seed on, because without it the count guard refuses and no neighbour delta exists. **Treatment and instrument cannot currently be told apart.** |
| **U5b** | **G12 clause 4.** Telemetry (5QI 1) reaches **M02 = 1.000** — every resolved byte PDB-violated — while 5QI 9 still carries **11.6 Mbps**. PF/Res degrade from 102 % of ceiling; **TwoTier from nominal load on 9/10 seeds**. | Filed as a **G1/G3** finding (a telemetry flow PDB-violated at nominal load is drive-command latency), not a G12 one. | **T for the measurement.** **I for the arm difference.** | **The measurement is solid; the arm attribution is not.** Two qualifications already on the row: the arm difference is **untested under flow-list permutation**, and G12's clean ramp-bottom control **structurally cannot cover telemetry** (it reads M13's GBR classes; 5QI 1 is `Delay`). |

---

## 3. The rest of the results, same treatment

Included so that "which of our claims are stories" has a complete answer
rather than a ranked excerpt.

| # | observation | classification | rests on | hardware transfer |
|---|---|---|---|---|
| **R1** | **G12's ordering is a declaration-order artefact.** Permutations 101/102/103 give `[2,4]` on all 5 seeds; **104 gives `[4,2]` on all 5**. | Not a scheduler property. | **X — a registered control that fired.** The strongest negative result here. | **Does not transfer — and must not be quoted as a scheduler behaviour.** Also additively biased by provisioning: 4 of 5 camera flows are offered **below their own GFBR** (3.879 vs 4.000 Mbps). |
| **R2** | **G8's M09 fairness failures** (parametric: Res 1/10, TT 3/10 below 0.90; `sensor_dense`: Res **10/10**). | Scheduler shortfall, workload-conditional. | **T.** | **Transfers as an ordering.** The millisecond does not (`SIM→RF`); the *ranking* is the claim. |
| **R3** | **G10's admissible fleet is a common boundary of 8** on all three arms once the attach path is supplied (was PF 8 / Res 4 / TT 4). | **Upper bound, not capacity** — and the pre-attach spread was the lock-out, not a scheduler difference. | **X.** | **The spread does not transfer** (it was S1's frequency). The boundary itself is a sim number. |
| **R4** | **PDCCH binds on `sensor_dense`**: U-slots at **92.2 % of achievable**, **40.7 % of slots at the per-slot cap** (parametric: 4.4 %, 0 %). | Real regime, correctly modelled. | **T.** | **Transfers — and is the sharpest thing we have**, because it is the regime the adoption study credits Configured Grants for. **The regime exists here and the mechanism does not** (S3). We therefore *cannot* reproduce the 30/30-vs-2/30 win the study rests on. |
| **R5** | **Crumb fraction 4.96 %** against hardware's **48–52 %**, with crumb size 146 B outside hardware's 72–107 B. | **Sim gap, quantified against hardware** — the only row here with a direct hardware comparison. | **T + a counterfactual probe.** TB quantisation was *measured* not to close it (13,214 of 13,214 grants at padding 0, unchanged). | **This is the honest statement of how far the UL model is from the deployed one, and it is ~10× on the headline statistic.** |
| **R6** | **Tier-1's SCA loop hits its 150-iteration cap on 82 % of solves**, so targets are where the damped sequence stood, not a fixed point. | **Faithful** — the cap is ground truth (`IA_P5G_TIER1_SCA_MAXITERS`). | **T + C.** | **Structure transfers; the numerics may not.** Unknown whether the deployed C converges where this does not — GLPK's vertex selection is not HiGHS's. **Not a defect to fix; a fidelity limit to state.** |
| **R7** | **G6 fails clause 1 on every arm.** | **Specification gap, not a result.** The clause names no estimator; we chose the median and documented it. | **T for the numbers; the clause is silent.** | **Owner: the test-plan author.** Not verdict-determining here, but it would be on data where clause 1 passes. |
| **R8** | **G11 C1 PASS** (900 windows, 0 failing, 7.2 M slots); **C3 PASS**. | Scheduler property, within the scripted workload. | **T.** | **Transfers as far as the workload does** — which is scripted, not measured from a deployment. |
| **R9** | **G3 inconclusive** (M20 TwoTier +21.34 % [−2.81, +50.02]). | Underpowered, not null. | **T.** | Interval spans zero at n=10. **Do not report as "no difference".** |

---

## 4. What this audit found

**Six rows rest on inference alone** — U1, U2(b), U3, U5a (four candidates),
U5b's arm attribution. Two of them (U1, U2b) are the ones a client would ask
about first, because both read as *"the QoS scheduler loses to the naive
one"*.

**Three rows are stronger than they are currently being reported.** R1 is a
control that fired — a genuine negative result, and the discipline that
produced it is the best evidence here that the campaign can tell an artefact
from a property. R4 and R5 are the two places we compare against something
outside the simulator.

**One row needs its premise corrected before anyone spends time on it** (U4).

**And one row is the campaign's real limit** (R4): the regime that motivates
the whole two-tier adoption argument is present in this simulator, and the
mechanism the adoption argument credits for winning it is not.

---

## 5. Order of work

U1 first — largest, most decision-relevant, and the **rank-trace hook already
exists for exactly this question**. Then U2(b), then U3. U5a and U5b after.
U4 drops to last on the corrected premise.

Each gets registered before it is traced.
