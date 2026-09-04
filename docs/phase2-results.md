# Phase 2 — complete results

**2026-09-04.** Every guarantee, with a verdict or a named cause. This is the
artefact Phase 3 diffs against, so it is written to be readable without the
conversation that produced it.

---

## READ THIS BEFORE ANY NUMBER BELOW

**1. All results are on the PARAMETRIC MIX, whose tightest PDB is 100 ms.**

| | classes present | tightest PDB |
|---|---|---|
| parametric mix (what Phase 2 ran) | 5QI 1 (100 ms), 2 (150 ms), 9 (300 ms), 82 (100 ms) | **100 ms** |
| fleet builder (not run here) | the same **plus 5QI 83 (10 ms) and 5QI 85 (5 ms)** | 5 ms |

**The workload contains no latency-critical flow.** Every latency-critical
conclusion is **structurally unavailable from this pass, however clean it
reads** — including `docs/wp9-plan.md` §15.5's tight-PDB-density hypothesis,
which cannot be tested on a workload with no tight-PDB flows. It bites
hardest on **G1**, whose 100 ms bound is evaluated against a mix whose
tightest configured budget *equals that bound*, and on **G3**, whose liveness
numbers come from flows whose slowest cadence is 300 ms.

**2. These numbers supersede every pre-fix figure.** Six commits changed what
prior results mean: `priority_level` derivation, the required population
argument, MFBR configuration, M03's slow-vs-degraded predicate, handshake
arrival accounting, and the 5QI table upgrade. **Any number from before
`8f9ad34` is measured on different code.**

**3. Two guarantees and four G11 clauses are NOT MEASURED, each with a named
cause** — listed as such below, never omitted. A guarantee absent from a
results table is indistinguishable from one that failed to produce a number.

---

## The list

| G | status | result or cause |
|---|---|---|
| **G1** | **measured** | M01 p98 **protected fleet**: PF 24.83 / Reservation 24.42 / TwoTier **94.51 ms** against a 100 ms bound — all pass, 3.8× arm separation. **The all-flow reading is saturated and must not be quoted**: ~300 ms on every arm, won by the 5QI-9 filler, pinned at that filler's own PDB, three arms agreeing to 0.25 ms. |
| **G2** | **NOT MEASURED — out of scope** | Two independent blockers. TB-size quantisation is planned and unbuilt. **And separately** the E-STOP flow is **DL** (`sim/fleet.py:179`) while G2's named failure mode — the BSR/SR desync — is an **uplink** mechanism, so the flow cannot reach the failure even once the mechanism exists. Building only the first would not produce a scoreable G2. |
| **G3** | **measured** | M20 protected-fleet liveness gap, n=40: PF **+0.44 % PASS**, Reservation **+1.84 % PASS**, TwoTier **+21.34 %** [−2.81, +50.02] **INCONCLUSIVE**. Unblocked by the M03 slow-vs-degraded fix (`2a4b382`), which previously silenced real breaches. |
| **G4** | **pending** | run in flight |
| **G5** | **measured** | M05 completeness: PF FAIL 3/40, Reservation FAIL 30/40, TwoTier FAIL 34/40 under 0.99. M06 frame age: PF and Reservation PASS 0/40, **TwoTier FAIL 14/40** over 67 ms. |
| **G6** | **measured** | Clause 1 within-bound and clause 2 shift ≤ +20 %, n=40 paired, protected fleet. **PF and Reservation byte-identical to the published values** — the control holds, so TwoTier's movement is attributable. TwoTier **worse**: M03 2→4/40, M06 12→14/40, M02 clause 2 PASS→**FAIL**. **And G6 remains unscoreable as written** — see specification findings. |
| **G7** | **NOT MEASURED — structurally out** | No MFBR *enforcement* anywhere in `sim/`. Containment is observable; **clipping is not**, and clipping is half the pass criterion. |
| **G8** | **measured** | **Both** conjuncts. M09 per-1s Jain protected: PF 0.9995 / Reservation 0.9998 / TwoTier 0.9654 — all pass ≥ 0.90. **M22 starvation epochs** (added this pass, G8's second conjunct previously had no instrument): 0 on all arms at the core cell. |
| **G9** | **NOT MEASURED — named cause** | `g9_campaign.py` refused to score and exited non-zero: *"GT-6.1_warm/TwoTier: 2 'warm' events but the scenario schedules 10."* The count guard is the result — it declined a partially-degenerate run whose survivors are self-selected. **M19/M21's `p95 = 0.0` were therefore never quoted**, and the M02 cross-read that distinguishes an eviction artefact from real instant recovery waits for a scoreable run. |
| **G10** | **measured** | **Admissible fleet: PF 8 / Reservation 4 / TwoTier 4 — unchanged.** The seed counts moved and are the evidence: at N=8, PF **10/10**, TwoTier **6/10** (was 1/10), Reservation **3/10**. TwoTier's 6× improvement changes no verdict — see the criterion finding. |
| **G11** | **ONE CLAUSE OF FIVE, at a horizon 18× shorter than specified** | see below |
| **G12** | **pending** | run in flight, 720 runs |

### G11 in full — the absence is the headline

**C1 passes 1.000 on all three arms. That is not G11 passing.**

| clause | status | cause |
|---|---|---|
| **C1** | **measured** — 1.000 pass rate, 3/3 seeds, 0 failing windows, all arms | 6 windows at the **400k-slot smoke horizon**, not the 7.2 M-slot soak GT-7.1 specifies |
| **C2** | **NOT SCORED** | never wired — commit 7 built the drift detector, commit 8 never collected its inputs (defects-log #16) |
| **C3** | not scoreable | CoV needs ≥ 5 seeds per GT-7.4; run at n=3 |
| **C4** | **not scoreable, self-declared** | the scorer reports `scoreable: false` on all arms — *"every window has the same verdict on every seed, so consistency is satisfied by construction"* |
| **C5** | not scoreable | bimodality undetectable at 3 points |

C1's pass is still a real result: before the fixes it was a **constant FAIL in
every window on every arm** at 8,050 ms — the scripted teleop off-period
scored as a liveness breach. The scripted-silence subtraction removed that.

---

## Open threads

### The camera UL loss at N=8 — the only unexplained thing bounding G10

Three of TwoTier's four failing seeds at N=8 have **zero dead flows** and
still miss contract: worst GBR **0.8875 / 0.5458 / 0.4498**, always
`*_qfi2`, the camera, with M07 missing 3–4 of 8 contracts.

**Ruled out by measurement:** starvation (zero dead flows), provisioning (the
0.9697 ceiling sits *above* the 0.95 line and passes at N=2 and N=4 —
`prediction-journal.md` P17), channel variance (margins of 0.11–0.55 are far
too large and land on the same class every time).

**Three candidates, with the discriminator named in advance:**

| candidate | signature in a per-slot trace |
|---|---|
| PRB lost to **other flows on the same UE** | UE granted; camera's share of each TB small while siblings take the rest |
| PRB lost to **other UEs** | the UE itself granted rarely; its share fine when it is |
| capacity lost to **retransmissions** | grants issued, bytes not delivered; `bytes_harq_lost` non-zero |

One per-slot trace of one failing seed separates all three. Registered as an
outcome→meaning map before any trace runs.

### R1 — the UL floor gap is ESTABLISHED, and it is the deployed C's

After the second re-attach the joiner's per-LCG estimate is **zero in 2,000
of 2,000 slots** and it receives **zero grants** — estimate reset → no grant →
no BSR → estimate stays zero, and the floor cannot arm because arming reads
that estimate. **Severity varies by event** (the first re-attach shows 8
grants and 85 % zero), so quote the per-event view, not the run aggregate.

**This is `gNB_scheduler_ulsch.c:48-66`, and the port reproduces both
conditions exactly.** The hardware team is being told about their own
product's join path — which every deployment exercises on every attach and
recovery — not about a limitation of this model.

### Specification findings — these belong to the test plan's owner

Properties of the guarantees' **definitions**, not of any scheduler. None
surfaced until someone executed the clause literally.

1. **G6 is unscoreable as written.** Its *"shifts by ≤ +20 % relative"* bar is
   undefined when the baseline is legitimately zero, and one of G6's own
   bound statistics is exactly that.
2. **GT-7.3's ramp does not reach its own failure condition.**
3. **G10's all-pass criterion cannot distinguish 1/10 from 6/10.** An
   all-pass requirement is binary in a quantity that is not, so a **6×
   improvement is invisible** and the arms read 4 = 4 when the seed counts
   are 6 vs 3. **Recommendation: report the admissible N *and* the per-seed
   pass fraction at the first failing N** — the second is already computed on
   the way to the first.
