# M-9 — the 100 ms `high_inactivity` rescue: registration

**Registered 2026-09-07, before implementation and before any run.**

---

## 1. The port

`nr_UE_is_to_be_scheduled` (`gNB_scheduler_ulsch.c:1735-1766`), called by
**both** deployed schedulers (`_ulsch.c:2159`, `ia_p5g_scheduler.c:2300`):

```c
const bool has_data = sched_ctrl->estimated_ul_buffer > sched_ctrl->sched_ul_bytes
                    || sched_ctrl->ul_has_unfulfilled_gbr;
const bool high_inactivity = diff >= (ulsch_max_frame_inactivity > 0
                                      ? ulsch_max_frame_inactivity * n
                                      : num_slots_per_period);
return has_data || sched_ctrl->SR || high_inactivity;
```

`ulsch_max_frame_inactivity = 10` frames = **100 ms**, both as the config
default (`MACRLC_nr_paramdef.h:125`) and in **two deployment `.conf` files**
(`gnb-vnf.sa.cbrs.aerial.conf:191`, `...273prb.aerial.conf:212`). `diff` runs
from the UE's **last UL-scheduled slot**.

This port implements **only** `has_data` today. `high_inactivity` is absent
entirely.

## 2. A CORRECTION TO MY OWN BUILD PLAN, found by reading the C first

Part 4's B2 proposed implementing M-9 as a **report floor**, arguing it is
faithful because *"a `do_sched`-only UE in the deployed C gets one min_rb CTRL
grant, which is what a report floor produces."*

**The deployed source's own v2 revision says that path does not rescue**
(`ia_p5g_scheduler.c:580-596`):

> *"it OR-ed the fire into `do_sched`, which routed the UE to the
> control-plane class, whose grant is a hardcoded min_rb crumb (~120 B at
> fallback MCS — **it cannot carry even one 200 B MAVLink packet, and leaves
> no padding room for the BSR MAC CE the crumb was supposed to deliver**). The
> measured trickle phase of the UGV stall is itself **~275 consecutive min_rb
> crumbs that failed to restore service**, bounding per-crumb resync
> probability at ≤ 0.01 — so v1's rescue had already been empirically
> falsified by the run that motivated it."*

**So on hardware the 100 ms rescue makes a UE a CANDIDATE and then hands it a
crumb that is documented, with measurements, not to restore service.**

### And the simulator will behave BETTER than the deployment, for a reason this audit already found

**This sim charges nothing for the BSR MAC CE.** `sim/ue_lcp.py::fill` is
handed the whole `bytes_capacity` and splits it entirely across data flows
(Part 1, finding **M-3**, recorded there as *absent-and-filtered-out* because
it is <1 % of a 1,000-byte TB).

**It is no longer filtered out — it becomes load-bearing exactly here.** The
deployed crumb fails *because there is no padding room for the BSR CE*. In this
simulator a crumb has all 120 bytes available and the BSR rides free, so the
crumb **will** deliver a report and **will** restore service.

**This is registered in advance rather than discovered afterwards:** M-9's
numbers below will be **optimistic relative to the deployment**, and the size
of the optimism is exactly the BSR-CE cost. Building the CE cost is a separate
fidelity change and is **not** bundled here (one change per commit).

## 3. Predictions

**Expected to MOVE, and why:**

| row | today | prediction |
|---|---|---|
| **G8 part 2, epochs (`core`)** | Res 3/10 · TT 7/10 | **collapses** — a 10.0 s epoch needs 100 consecutive 100 ms exclusions and the rescue forbids exclusion. Res → ≥ 8/10 |
| **G8 part 2, epochs (`sensor_dense`)** | Res 0/10 · TT 4/10 | **collapses** — Res → ≥ 8/10 |
| **G8 part 2b, `n_never_granted`** | Res 7/10 | **→ 10/10.** A UE never granted all run is the purest case the rescue forbids |
| **G8 part 1, Jain** | Res 9/10 · TT 7/10 | **improves** — a starved UE is the largest possible Jain penalty |
| **G5 ≥99 % PDU sets** | Res 3/10 · TT 6/10 | **rises sharply** — the failure mechanism is the cold-start lock-out, a candidacy fault |
| **G6's G5 conjunction** | Res 10/40 · TT 6/40 | **rises** — same population, same mechanism |
| **G10** | Res 23/40 · TT 26/40 | **rises**; `n_never_granted` at N=8 (median 1.0 on Res) → 0 |
| **G12 c4** | PF 0/20 violations | **PF's violations should FALL** — telemetry dying is a candidacy outcome and this is the deployed candidacy rescue. Direction is toward PF |
| **G1 / G3 part 3** | TT 7/10 | **small improvement at most** — TwoTier's 3 misses are 2-4 ms over a 95 ms bound, and this is a candidacy fix, not a latency one |

**Expected NOT to move, and this is the half that tests the prediction:**

| row | why not |
|---|---|
| **G2 (UL and DL STOP)** | ×19-27 margin at 2-5 ms; the STOP flow is never starved |
| **G7 c1, c1-camera, c1-telemetry, c3** | all 10/10, and the mechanism is **intra-UE LCP**, not candidacy — M-9 cannot reach an intra-TB split |
| **G7 c2** | a rate-limiting question. MFBR bounds entitlement, not throughput; candidacy is irrelevant |
| **G3 parts 1-2** | already 10/10 on every arm; the rescue can only push further from failure |
| **G5 part 2 (frame age)** | 10/10, and frame age is a delivery-timing statistic on a flow that is being served |
| **G11 C1 / C3** | ×112-141 margin over 7.2 M slots |
| **PF, almost everywhere** | PF does not suffer the lock-out — `n_never_granted` is 0 on PF at every fleet size measured |

**Falsifier:** if G8's epochs do **not** collapse, the starvation is not a
candidacy fault and the whole M-9 → G8 chain in Parts 1-2 is wrong.

## 4. Does it make the attach-seed flag inert?

**Predicted: largely yes, and that is a RESULT, not a failure.**

The attach seed supplies one BSR at attach; M-9 supplies a candidacy rescue
every 100 ms thereafter. They attack the same fault by different routes. **If
the with/without-attach columns collapse to near-identical, then every
conclusion drawn from that column becomes a statement about a mechanism M-9
supersedes** — including *"the attach path clears G5 entirely"* and *"G10's
capacity deficit is entirely the cold-start lock-out."*

**Registered as a check, not an assumption:** the two columns will be scored
and the number of rows that still differ reported.

## 5. Expected DL drift, and it is not a leak

More UL grants perturb `HarqProcessPool.due_this_slot()`'s shared insertion
order, so DL numbers on some records will move with no DL-side change. **This
is CLAUDE.md's documented cross-direction invariant, not a boundary leak**, and
it is registered here so it is not investigated as one.

## 6. Corpus

**RE-BASELINE, certain.** It creates UL grants that do not exist today.
Justification stated in advance: *the change is intended to move the numbers.*

---

# RESULT — M-9 landed and scored

**Artefacts** `sweeps/m9-2026-09-07/{plain,attach}/`. Full 22-row scorecard
re-scored in both columns.

## The headline: my central prediction FAILED

**7 of 60 tracked cells moved, all of them G8, and mostly on `sensor_dense`.**
G8's starvation epochs did **not** collapse; G5, G10, G1, G3 and G12 did not
move at all.

| row | pre-M-9 | M-9 | predicted |
|---|---|---|---|
| G8 Jain, parametric — TwoTier | 7/10 | **8/10** | improves ✓ (barely) |
| G8 Jain, `sensor_dense` — Res | 0/10 | **1/10** | improves ✓ (barely) |
| G8 Jain, `sensor_dense` — TT | 9/10 | **10/10** | improves ✓ |
| G8 epochs, parametric — TT | 7/10 | **8/10** | **collapses ✗** |
| G8 epochs, parametric — Res | 3/10 | **3/10** | **collapses ✗ — unmoved** |
| G8 epochs, `sensor_dense` — Res | 0/10 | **3/10** | **collapses ✗** |
| G8 epochs, `sensor_dense` — TT | 4/10 | **7/10** | partial |
| G8 `n_never_granted` — Res | 7/10 | **9/10** | → 10/10 ✗ (close) |
| **G5, G10, G1, G3 part 3** | — | **unmoved** | **all predicted to move ✗** |

**The "expected NOT to move" set was 100 % correct** — G2 (both directions),
all four G7 rows, G3 parts 1-2, G5 part 2, G11. That half of the registration
held perfectly; the half predicting movement did not.

## Why — measured, and it is not the crumb

**The mechanism fires, and the rate is the answer:**

| workload | arm | rescue fired | of evaluations |
|---|---|---|---|
| parametric N=8 | Reservation | **0** | 32,814 |
| parametric N=8 | TwoTier | **0** | 6,545 |
| `sensor_dense` | Reservation | **9,833** | 35,070 (**28.0 %**) |
| `sensor_dense` | TwoTier | 1,088 | 92,274 (1.2 %) |

**On the parametric mix the rescue NEVER FIRES — 0 of 32,814.** Every UE there
carries a saturating 5QI-9 background flow, so **no UE ever goes 100 ms without
a grant**. The UE is always a candidate; the protected flow starves **inside
the TB**, after the scheduler has handed it over.

**So M-9 cannot address the parametric failures by construction. They are not
candidacy failures at all** — which is exactly the intra-UE LCP result this
project measured earlier (the disadvantaged UE receives 1.003× the fleet median
and its protected flow waits through its own UE's grants).

On `sensor_dense`, where each UE carries exactly **one** flow, UE-level
candidacy **is** the fault — and there the rescue fires and helps.

**This refutes a chain Parts 1-2 asserted.** M-9 was predicted to unlock
**G3, G5, G8, G10 and G12 c4**. It touches **G8, and mostly on one workload.**

## The attach flag is NOT inert — and that answers the registered question

**14 rows still differ between M-9-only and M-9+attach**, and the attach column
is far stronger:

| row | M-9 only | M-9 + attach |
|---|---|---|
| G5 ≥99 % PDU sets — Reservation | **3/10** | **10/10** |
| G5 — TwoTier | **6/10** | **10/10** |
| G8 epochs parametric — Reservation | 3/10 | **10/10** |
| G8 Jain `sensor_dense` — Reservation | 1/10 | **10/10** |
| G1 / G3 part 3 — TwoTier | 7/10 | **9/10** |

**M-9 does NOT supersede the attach path.** They are not substitutes: the
attach seed supplies a BSR to a UE that has *never* been granted at all, before
any inactivity horizon can elapse; M-9 rescues a UE that *stops* being granted.
**Every conclusion drawn from the with/without-attach column stands.**

## Two published claims moved, and one is a degradation

- **G8.M09.n10.twotier**: TwoTier's count below Jain 0.90 **3 → 2** — the
  improvement the scorecard shows as 7/10 → 8/10.
- **G1.M01.n10.twotier.median**: **87.78 → 91.5 ms — WORSE by 3.7 ms.**
  Rescuing previously-excluded UEs puts more UL grants into contention. The
  success rate holds at 7/10, so no verdict moves, but **the direction is a
  cost, and I predicted "small improvement at most".**

Both updated in `config/published_claims.yml` as part of the registered
re-baseline.

## A guard fired correctly and was updated, not tuned

`test_sr_retires_the_cold_start_deadlock_without_it` builds a "no SR
replacement" baseline it expects to be the ~0 % deadlock. It now measures
**15.3 %**, because **M-9 is a second, independent route out of the deadlock**.
The bound was raised with that reason stated, and the companion `10 ×`
assertion was **retired rather than loosened** — its denominator was the ~0 %
deadlock and a 10× multiple of 15.3 % is arithmetically unreachable for a
ratio. The absolute floor below it is the assertion that can still fail.

## And a near-miss worth recording

The first re-score reported **0 of 60 moved**. The `sed` repointing `SEV_DIR`
had failed on an unescaped `/` and the scorecard was still reading the pre-M-9
artefacts. **"Nothing moved" was indistinguishable from "M-9 did nothing"** —
defect #31's symptom a fourth time. Caught only because `sed` printed an error.
The repoint is now an asserted Python replacement, and the artefacts were
checked to differ before anything was read.
