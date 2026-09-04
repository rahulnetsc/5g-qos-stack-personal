# Verification pass — every guarantee re-measured on current code

**2026-09-04. Supersedes `docs/phase2-results.md`**, whose numbers predate the
population fix, MFBR configuration, M03's slow-vs-degraded predicate, the
handshake accounting, the 5QI priority table, the per-axis scoring dispatch,
`g12_score`'s four decompose sites and G6's estimator change.

**The "Phase 2" label is retired.** It meant *fast numbers to check the
plumbing*, and that is what those numbers were — one of them literally
`--seeds 1`. This pass is the re-measurement.

---

## THE COMPLETION CRITERION, ANSWERED FIRST

The criterion was: **a full pass that finds nothing new.** Every pass so far
has found defects, and the question was whether the rate has fallen.

**It has not. This pass found four new things**, listed below and none of
them cosmetic. One reverses a published conclusion, one shows a published
verdict rests on n=1, one is a check that can never pass again, and one is a
regression this session itself introduced.

**What DID hold is the code.** Re-run at the published configuration, the
published verdicts reproduce; three guarantees reproduce byte-identically.
Every new finding is about **measurement design or documentation**, not about
the simulator computing something different. That distinction is the useful
part of the result.

---

## The list

| G | status | result, and whether it moved |
|---|---|---|
| **G1** | **measured** | M01 p98 protected, n=1/h=40k (the published cell) on current code: PF **28.00** / Reservation **22.00** / TwoTier **90.75** ms against 100 ms — **all pass, as published** (published: 24.83 / 24.42 / 94.51). At n=10, h=40k: **0/10 fail on every arm**. **NEW — horizon sensitivity:** at h=20,000, TwoTier's median rises to 98.12 and **2/10 seeds breach**. The bound holds at the published horizon and is knife-edge at the sweep's standard one. |
| **G2** | **NOT MEASURED — out of scope, unchanged** | Two independent blockers, both structural: TB-size quantisation is planned and unbuilt, **and** the E-STOP flow is DL (`sim/fleet.py:179`) while the BSR/SR desync is an uplink mechanism. Deferred for this delivery; the reason is a finding, not a gap. |
| **G3** | **measured (bound); delta deferred** | The 500 ms bound passes **0/10 on every arm** (M20 protected, medians PF 132.25 / Reservation 122.75 / TwoTier 238.62 ms). The **delta** clause is G6's and is unresolvable at this precision — see G6 and `sweeps/phase2/sca-convergence-2026-09-04/`. Deferred for this delivery. |
| **G4** | **measured — BYTE-IDENTICAL** | duty 0.1: PF **106.56** / Reservation **117.50** / TwoTier **112.42** ms; Reservation−PF **+10.94** [+5.93, +16.20], TwoTier−PF **+5.86** [+4.50, +7.25]. Every figure reproduces the published one exactly. |
| **G5** | **measured — reproduces** | M05 completeness, protected, n=10: PF **0/10** fail, Reservation **7/10**, TwoTier **4/10**, Reservation's median **0.0000**. The published failure ("median worst-flow PDU-set completeness 0.0000 on both QoS-aware arms") holds. |
| **G6** | **NOT PUBLISHABLE — a second specification defect** | **NEW.** The clause names no estimator over runs, and the three defensible readings give **PASS, INCONCLUSIVE and FAIL on the same cell**. See below. |
| **G7** | **NOT MEASURED — structurally out, unchanged** | No MFBR *enforcement* anywhere in `sim/`; containment is observable, clipping is not, and clipping is half the criterion. |
| **G8** | **FAILS at n=10 — the published pass was n=1** | **NEW.** See below. |
| **G9** | **NOT MEASURED — named cause, deferred** | `g9_campaign.py`'s count guard refuses to score a partially-degenerate run. Unchanged; deferred for this delivery. |
| **G10** | **measured — BYTE-IDENTICAL** | Admissible fleet **PF 8 / Reservation 4 / TwoTier 4**, per-seed at N=8 **PF 10/10, Reservation 3/10, TwoTier 6/10**. Every number reproduces. |
| **G11** | **one clause of five — deferred** | Unchanged; deferred for this delivery. |
| **G12** | **TWO cells, and the promotion bar now FIRES** | **NEW — a reversal.** See below. |

---

## The four new findings

### 1. G8's published pass rests on n=1, and at n=10 both conjuncts fail

`sweeps/phase2/core_fast.json` is **`seeds=1`**. The published G8 row — *"M09
per-1s Jain protected: PF 0.9995 / Reservation 0.9998 / TwoTier 0.9654 — all
pass ≥ 0.90. M22 starvation epochs: 0 on all arms"* — is one seed, reported
as a cell result.

**The code is not the cause, and that was isolated rather than assumed.** Run
at the published configuration exactly (n=1, h=40,000) on current code, the
published verdicts reproduce: M09 0.9995 / 0.9998 / 0.9992, M22 zero
everywhere. Only the seed count was then changed:

| n=10, h=40,000 | M09 protected ≥ 0.90 | M22 epochs = 0 |
|---|---|---|
| PF | 0/10 fail | 0/10 seeds with epochs |
| **Reservation** | **1/10 fail** (min 0.8333) | **7/10 seeds**, worst 4 |
| **TwoTier** | **3/10 fail** (min 0.7499) | **3/10 seeds**, worst 6 |

**G8 is a conjunction and both halves fail on both QoS-aware arms.** The
starvation victim is consistently a 5QI-9 flow (`ue7/ue8_qfi9`) with epochs up
to 5.00 s against a 1 s bar.

### 2. G6 names no estimator — and the three readings disagree

Registered in full in `docs/phase2-results.md` (specification finding 1a) and
summarised here because it is why G6 has no verdict.

The clause is *"every G1/G3/G5 statistic stays within its bound and shifts by
≤ ▷ +20 % relative"*. It fixes a number and says nothing about aggregation
across runs — **and the plan names a run-rule wherever it means one** (G10:
*"all-pass in 5/5 runs"*; open item §7: *"defaults are 5 runs (P0) / 3 runs
(P1+)"*). Measured on the protected fleet, M03 max gap, n=40:

| arm | median | mean | per-run |
|---|---|---|---|
| PF | −0.30 % PASS | +0.44 % PASS | 36/40 **FAIL** |
| Reservation | +0.10 % PASS | +1.84 % PASS | 38/40 **FAIL** |
| **TwoTier** | **−1.39 % PASS** | **+21.34 % INCONCLUSIVE** | **29/40 FAIL** |

The all-flow row disagrees the same way, so restricting to the protected
fleet — the population G6 binds to — does **not** stabilise it. And the
per-run reading depends on the run count, which §7 lists as unconfirmed:
Reservation **passes at n=3 and fails at n=5**.

**No single G6 verdict is published.** Choosing an estimator in code would be
the tool deciding what the specification declined to.

### 3. G6's control can never pass again — a cannot-PASS check

`g6_seed_extension.py` reads first, before any effect size: *do stage 1's own
10 seeds reproduce?* It compares against `stage1_rows.csv`, **stored numbers
from superseded code**. On current code it fails, and the magnitude is the
code movement itself: TwoTier's M03 max gap **1835.0 → 759.25 ms**.

The guard behaved correctly — it refused to read the extension and reported
`control_passed: false` rather than scoring anyway. But the check is now
structurally unpassable: its reference is an artefact of code that no longer
exists, so **it can only ever report FAIL, and a check that cannot pass is as
uninformative as one that cannot fail.** It needs re-baselining against a
current stage-1 run, or replacing with a control that does not reference
frozen numbers. Not fixed here — it is a decision about what G6's control is
*for*.

### 4. A record-schema regression this session introduced

`g6_seed_extension.py`'s parallelisation (`fe3e5b1`) replaced its
`PersistingRecordSink` with an inline sink and **dropped the
`{"axis_values": …, "record": …}` envelope**. Every reader of those files
unwraps it; none was run in that commit. Found here when
`g6_fleet_restricted_m03.py` raised `KeyError('axis_values')` on a fresh file.

**The serial-vs-parallel identity check did not catch it, and could not:** it
compares NEW code against NEW code, so it binds on the axis it was built for
(ordering under a pool) and not on the one that moved (the schema). **An
identity check establishes that two paths agree with each other, never that
either agrees with what came before.**

Fixed, with `sim/tests/test_g6_records_schema.py` pinning the envelope and
asserting the two writers of that format cannot drift apart again.

---

## G12 — two cells now, and the promotion bar fires

Phase 2 reached **one** cell before timing out and wrote nothing. With the
parallelisation and per-run banking the campaign completes: **`mixed_n8` and
`drone_heavy_n8`**, 60 groups, plus the full permutation control.

`mixed_n8` reproduces the published orders exactly (PF `[4,2]`×10;
Reservation `[4,2]`×6, `[2,4]`×4; TwoTier `[4,2]`×5, `[2,4]`×4, `[2]`×1).

**THE REVERSAL.** Phase 2 concluded *"NEITHER CLAUSE FIRES … the Region-2
ordering is NOT ESTABLISHED as a scheduler property and is CONSISTENT WITH A
DECLARATION-ORDER ARTEFACT."* That conclusion was a consequence of the
campaign not completing — the permutation control never ran. It now has:

- arms differ under the canonical order in **both** cells;
- **the difference survives permutation in the same direction**;
- ⇒ **clause 1 FIRES.** The arm difference is a **candidate scheduler
  finding** that needs the mechanism trace to confirm.

Clause 2 is untouched and its edge still holds: all three candidate
mechanisms are position-dependent, so tracing to any of them **confirms the
artefact rather than promoting it**.

**And E3 is worse on the new cell:** TwoTier's telemetry M02 reaches 1.000
from **×1.0 — nominal load** — on `drone_heavy_n8`, against ×1.6 on
`mixed_n8`, with 5QI 9 still carrying 17.4 Mbps.

**E4's decomposition earned itself immediately.** Per (cell, arm): 16.8–17.4
Mbps on `drone_heavy_n8` against **0.345 Mbps** on `mixed_n8/Reservation` — a
50× spread that a pooled median across two cells would have reported as one
number. The four sites were fixed one commit before the run that needed them.

---

## What this pass did not cover

**G2, G9, G11's remaining clauses, and G3's delta clause are deferred for
this delivery**, each with a structural reason recorded above rather than
left as a gap. No work was started on any of them.

**Artefacts:** `sweeps/verification-2026-09-04/`.
