# The GBR offered-vs-contract shortfall: category, fix, registration

**2026-09-08.** G12's ordering clause was unscoreable because one GBR class
is pinned below its own contract by construction. This document asks the
category question first, fixes at the source, and registers every prediction
**before** the diff is looked at.

---

## 1. The category question, answered before any fix

**Which guarantees score a metric that reads this flow's contract
attainment?** Two metrics read it, and both are `meets_gbr_contract(0.95)`
(`config/metric_panel.yml: gbr_contract_fraction: 0.95`):

| metric | reads | reached by |
|---|---|---|
| **M07** `gbr_contract_count` | `gfbr_fraction() >= 0.95` per GBR flow | **G10** — *"every GBR flow meets contract (per fleet size × seed)"* |
| **M13** `first_violation_order` | the same predicate, per ramp point | **G12** — the first-violation order |
| M08 `worst_flow_gfbr_fraction` | `gfbr_fraction()` (reported, not thresholded) | severity columns |

**So the answer is: G10 and G12 read the contract. It is not just G12.**

**And the defect is wider than the one flow.** Every GBR flow in every
builder, offered load against its own GFBR:

| 5QI | kind | offered | GFBR | **ratio** | builders |
|---|---|---|---|---|---|
| 2 | `video_frame` | 6.0006 | 6.5000 | **0.9232** | `scenario(3)` — **below the 0.95 threshold: can NEVER meet contract** |
| 2 | `video_frame` | 19.1962 | 20.0000 | **0.9598** | `scenario(1)` |
| 2 | `xr_video` | 3.8788 | 4.0000 | **0.9697** | `fleet[drone_heavy/mixed/ugv_heavy]`, `g12`, `parametric[factory/video_heavy]` |
| 3 | `xr_video` | 3.8788 | 4.0000 | **0.9697** | `parametric[video_heavy]` |
| 2 | `video_frame` | 7.9208 | 8.0000 | **0.9901** | `scenario(6)` — **the regression corpus's own scenario** |
| 2 | `video_frame` | 13.9214 | 14.0000 | **0.9944** | `scenario(6)` |
| 4 | `deterministic` | 3.0000 | 3.0000 | 1.0000 | `g12` |
| 2 | `xr_video` | 6.0606 | 6.0000 | 1.0101 | `fleet`, `g12` |

**Six distinct flow definitions offer below their own contract, across five
builders and three YAML scenarios.** One of them (`scenario(3)`, 0.9232) is
below the 0.95 threshold outright.

**Why it makes G12's ordering unscoreable rather than merely noisy:** 5QI 2
starts with **2 points of headroom** above the threshold and 5QI 4 with
**5 points**. The class the specification says should be sacrificed *second*
is the one that is structurally closest to failing, so it will always appear
to break first. The order was measuring the generator.

**Rows that will MOVE but do not read the contract.** Changing offered bytes
changes the workload, so anything scored on a scenario containing a camera
flow moves numerically even though its clause reads something else: **G5**
(PDU-set completeness, frame age), **G6** (scores G1/G3/G5 statistics with
background), **G7** (the victim is a camera), **G8** (Jain over throughput),
**G1/G3** (telemetry, via contention). Those are *numerical* movement, not
clause exposure — the distinction is kept in §4's predictions.

## 2. The fix, at the source

**`sim/workload.py::min_bytes_per_period_for_gfbr(gfbr_bps, period_ms)`** —
the bytes a periodic GBR flow must carry so its offered load is at least its
own contract, `ceil(gfbr_bps × period_ms / 8000)`. Applied **at every source
that defines a GBR flow** — `sim/fleet.py`'s device profiles,
`sim/parametric.py`'s camera, and the three YAML scenarios — as
`max(authored, minimum)`, so a flow already offering at or above its
contract is untouched and only the shortfall is closed.

**Not fixed at G12's scenario.** Fixing at the site is this project's most
expensive recurring defect; G12 is where the symptom was noticed, not where
the defect lives.

**And the invariant is enforced, not just repaired:**
`sim/tests/test_workload.py::test_no_gbr_flow_offers_below_its_own_contract`
scans **every builder** — the same `_cases()` the flow-key sweep proves
covers them all — and fails on any GBR flow whose offered load is below its
GFBR. The class cannot come back silently.

## 3. Registered predictions — written before the diff

**Corpus (`regression_corpus.py --check`) — a DELIBERATE re-baseline.**

| record set | scenario | prediction |
|---|---|---|
| study 1 (`overload_mult*`) | `scenario(6)` factory_robots | **MOVES.** Its two camera definitions are short by 1.0 % and 0.6 %, so every arm's throughput, delay and utilisation shift |
| study 2 (`pdcch_limited`) | `scenario(4)` sensor_dense | **HOLDS** — no GBR flow in it is short |
| study 3 (`latency_bound`) | `scenario(5)` | **HOLDS** — same reason |

**Verdicts.**

| row | prediction | why |
|---|---|---|
| **G10 boundary (6/6/5)** | **HOLDS.** Possibly +1 on one arm, not −1 | Two effects oppose: each camera gains 5 points of contract headroom (0.9697 → 1.000 against a 0.95 threshold), which makes the clause *easier*; the cell carries 3.1 % more committed load, which makes it *harder*. The headroom gain is the larger, so if it moves it moves up |
| **G12 clause 4** | **HOLDS at PASS 10/10** | Clause 4 is about telemetry starvation, not the camera's contract; the extra 3.1 % of camera load is small against the 50 Mbps background |
| **G12 ordering** | **BECOMES SCOREABLE IN PRINCIPLE, and I expect it to stay mostly degenerate** | The bias is removed — both classes now start at 1.000 — but at cap 4 nothing breached before, so I expect few or no two-element orders. If one appears it is now on merit |
| **G5** (≥ 99 % PDU sets) | **PF holds 10/10; Reservation and TwoTier hold at 0-2/10** | 3.1 % more video bytes makes completeness marginally harder; the QoS arms are already at the floor |
| **G8** (Jain, starvation epochs) | **HOLDS** | Marginal load change |
| **G1 / G3** (telemetry) | **HOLD**, TwoTier's marginal rows the most likely to slip | Only reached through contention |
| **G7 c1** (victim's PDU sets) | **HOLDS** | Same marginal-load reasoning |

**Falsifiable in both directions**: a G10 boundary that *drops* would refute
the headroom argument; a corpus move in study 2 or 3 would mean I mis-scoped
which scenarios carry short flows.

---

## 4. Results — and one prediction badly missed

### 4.1 The test found a seventh instance immediately

`test_no_gbr_flow_offers_below_its_own_contract` failed on **three G9
scenarios** the moment it was written: `sim/scenarios/g9.py`'s own camera
flow carries the identical 16 000 B / 33 ms / 4 Mbps shortfall. **I had not
listed it in §1's census** — I enumerated the builders by reading, and the
test enumerated them by scanning. Fixed at that source too. That is the
whole argument for the invariant being a test rather than a repair.

### 4.2 Corpus — the prediction held exactly

**3 712 values moved, every one of them `study1`** (`factory_robots`, whose
two camera definitions were short by 1.0 % and 0.6 %). **`study2` and
`study3` are byte-identical**, as predicted — neither carries a short GBR
flow. Deliberate re-baseline, captured.

### 4.3 G10 — **PREDICTION MISSED, and this is the finding**

I predicted *"HOLDS. Possibly +1 on one arm, not −1."* The direction was
right and **the magnitude was badly wrong.**

| arm | boundary BEFORE | boundary AFTER |
|---|---|---|
| PF | 6 | **12** |
| Reservation | 6 | **6** |
| TwoTier | 5 | **7** |

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 |
|---|---|---|---|---|---|---|---|---|---|
| PF — before | 10/10 | 10/10 | 10/10 | 10/10 | **9/10** | 10/10 | 10/10 | **9/10** | 0/10 |
| PF — after | 10/10 | 10/10 | 10/10 | 10/10 | **10/10** | 10/10 | 10/10 | **10/10** | 4/10 |
| Reservation — before | 10/10 | 10/10 | 10/10 | 10/10 | 4/10 | 1/10 | 0/10 | 0/10 | 0/10 |
| Reservation — after | 10/10 | 10/10 | 10/10 | 10/10 | 7/10 | 3/10 | 0/10 | 0/10 | 0/10 |
| TwoTier — before | 10/10 | 10/10 | 10/10 | **9/10** | 9/10 | 3/10 | 0/10 | 0/10 | 0/10 |
| TwoTier — after | 10/10 | 10/10 | 10/10 | **10/10** | 10/10 | 9/10 | 0/10 | 0/10 | 0/10 |

**Why the miss, and why it matters more than the prediction.** I reasoned
that 2 points of headroom versus 5 was a small difference. It was not: with
the camera pinned at 0.9697 against a 0.95 threshold, **any** contention at
all pushed it under, so the camera's contract — not the cell's capacity —
was the binding constraint on the boundary. Removing the shortfall did not
shift the boundary a little; **for PF it revealed that the boundary had been
measuring the traffic generator all along.**

**So G10's published 6 / 6 / 5 is withdrawn. The admissible fleet is
PF 12 / Reservation 6 / TwoTier 7** on the corrected workload at cap 4 with
RA and SRB live. **PF's and TwoTier's fleet sizes were under-reported by 2×
and 1.4×**; Reservation's boundary was real and is unchanged — it is capacity
bound, not artefact bound, which is why it did not move.

### 4.4 G12 — clause 4 holds; the ordering is still unanswerable, for a new and honest reason

**Clause 4: PASS 10/10 on every arm, both cells, both caps, both tie-break
settings — unchanged by the fix, as predicted.**

**5QI 2's contract fraction moves 0.965 → 0.995**, and the residual 0.5 % is
now *delivery* (PDB drops, HARQ) rather than arithmetic: the offer is exactly
4.000 Mbps against a 4.000 Mbps GFBR. **5QI 4 stays at 1.000. Both classes
now have real headroom above the 0.95 threshold, so neither is structurally
predisposed to break first — the bias is gone.**

| | cap 4 (deployment) | cap 2 (this carrier) |
|---|---|---|
| PF | `[[]]` — **nothing breaches**, 10/10 | `[[]]` — nothing breaches |
| Reservation | `[[]]` — nothing breaches, 10/10 | `[[]]` — nothing breaches |
| TwoTier | `[[]]` — nothing breaches, 10/10 | `[[], [2]]` at N=6; `[[], [2], [4]]` at N=4 with a seeded tie-break |
| matches 9 → 4 → 2 | **0/10 everywhere** | **0/10 everywhere** |

**At the deployment's cap the ramp ×0.5 → ×2.0 produces no GBR contract
breach at all, on any arm.** So "what breaks first" is still unanswered —
but the reason has changed from *"one class cannot pass by construction"* to
**"nothing breaks in this range"**, which is a statement about the system
rather than about the generator. **The ramp does not reach the knee at cap 4
and would have to extend past ×2.0.**

**At cap 2, only TwoTier breaches**, and **5QI 4 now appears in an order for
the first time** (`[4]`, N=4, seeded tie-break) — it could not before,
because it was the only class with headroom. Orders remain single-element,
so no *sequence* is observable and the specified 9 → 4 → 2 is still 0/10.

**The tie-break control matters more after the fix than before**: at cap 2,
N=4, TwoTier, agreement falls to **5/10** with three distinct order-sets
under a seeded tie-break against 7/10 with position deciding. **A one-element
order at this resolution is not separable from the tie-break**, which is the
third independent reason not to publish an ordering from this ramp.

**Carrying the caveat**: the C ties on the same terms and, on glibc 2.39,
resolves them the same way — measured — but `qsort` is not required to be
stable and glibc has changed algorithms across releases, so any ordering
statement rests on libc behaviour the deployment inherits rather than
specifies.

### 4.5 What was NOT re-scored, and why

**G5, G6, G7, G8, G1 and G3 were predicted to move numerically and have not
been re-run.** They do not read contract attainment, so no clause is exposed
by the fix, but their scenarios all contain a camera flow whose offered load
changed by 0.6-3.1 %, so their numbers are now stale. **Their rows should be
read as pre-fix until re-run** — stated here rather than left for a reader to
discover. The corpus movement (§4.2) is the measure of how much they will
move: study1 only, and confined to that scenario.

## 5. Run times

| campaign | runs | wall |
|---|---|---|
| G10 boundary, cap 4, RA+SRB | 270 | **199 s** |
| G12 stress, cap 4 | 1 320 | **369 s** |
| G12 stress, cap 2 | 1 320 | **368 s** |
| **total** | **2 910** | **~15.6 min** |
