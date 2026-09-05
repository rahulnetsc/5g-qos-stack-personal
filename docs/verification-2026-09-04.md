# Verification pass — every guarantee re-measured on current code

**2026-09-04. Supersedes `docs/phase2-results.md`**, whose numbers predate the
population fix, MFBR configuration, M03's slow-vs-degraded predicate, the
handshake accounting, the 5QI priority table, the per-axis scoring dispatch,
`g12_score`'s four decompose sites and G6's estimator change.

**The "Phase 2" label is retired.** It meant *fast numbers to check the
plumbing*, and that is what those numbers were: the core-cell row set is
**n=3**, drawn from *two different runs*, and one of its claims is
contradicted by the file it came from. This pass is the re-measurement.

---

## THE COMPLETION CRITERION, ANSWERED FIRST

The criterion was: **a full pass that finds nothing new.** Every pass so far
has found defects, and the question was whether the rate has fallen.

**It has not. This pass found five new things**, listed below and none of
them cosmetic. One reverses a published conclusion, one is a published claim
contradicted by the artefact it came from, one is a check that can never pass
again, one is a regression this session itself introduced, and one is the
category search the second of those obliged.

**What DID hold is the code.** Re-run at the published configuration, the
published verdicts reproduce; three guarantees reproduce byte-identically.
Every new finding is about **measurement design or documentation**, not about
the simulator computing something different. That distinction is the useful
part of the result.

---

## The list

**PROVENANCE FOR EVERY ROW — artefact, n and horizon**, because a figure
without them is the defect finding 1 is about. All under
`sweeps/verification-2026-09-04/` unless named otherwise.

| G | artefact | n | horizon |
|---|---|---|---|
| G1 | `core_40k_n1.json` (reproduction) + `core_40k_n10.json` + `core.json` | 1, 10, 10 | 40k, 40k, 20k |
| G3 | `core.json` | 10 | **20k** |
| G4 | `g4.json` | 10 | 20k |
| G5 | `core.json` | 10 | **20k** |
| G6 | `stage6_g6_n40_records.jsonl` | 40 | 20k |
| G8 | `core_40k_n1.json` + `core_40k_n10.json` | 1, 10 | 40k |
| G10 | `g10_rows.csv` | 10 | 20k |
| G11 | `g11_c1_n10.json` (**re-measured**) | **10** | 400k |
| G12 | `g12.json` | 10 | 20k |

**TWO INCONSISTENCIES THIS TABLE MAKES VISIBLE, and neither was intended.**

1. **G3 and G5 are read at h=20,000 while G1 and G8 are read at h=40,000.**
   The horizon matters: TwoTier's M20 median is **238.62 ms at 20k and
   266.25 ms at 40k**, and G1's TwoTier p98 breaches 2/10 at 20k and 0/10 at
   40k. Neither verdict changes, but the rows are not on one configuration
   and say so here rather than implying they are.
2. **G11's row WAS the only one still on an n≤3 artefact.** Re-measured at
   n=10 on 2026-09-05 — the exposure is closed and the result is below.

**Every row now quotes an n≥10 figure**, and where a row also cites a low-n
number (G1's and G8's n=1 reproductions) that number is labelled as a
reproduction of the published cell, never as the result.

| G | status | result, and whether it moved |
|---|---|---|
| **G1** | **measured** | M01 p98 protected, n=1/h=40k (the published cell) on current code: PF **28.00** / Reservation **22.00** / TwoTier **90.75** ms against 100 ms — **all pass, as published** (published: 24.83 / 24.42 / 94.51). At n=10, h=40k: **0/10 fail on every arm**. **NEW — horizon sensitivity:** at h=20,000, TwoTier's median rises to 98.12 and **2/10 seeds breach**. The bound holds at the published horizon and is knife-edge at the sweep's standard one. |
| **G2** | **NOT MEASURED — out of scope, unchanged** | Two independent blockers, both structural: TB-size quantisation is planned and unbuilt, **and** the E-STOP flow is DL (`sim/fleet.py:179`) while the BSR/SR desync is an uplink mechanism. Deferred for this delivery; the reason is a finding, not a gap. |
| **G3** | **measured (bound); delta deferred** | The 500 ms bound passes **0/10 on every arm** (M20 protected, medians PF 132.25 / Reservation 122.75 / TwoTier 238.62 ms). The **delta** clause is G6's and is unresolvable at this precision — see G6 and `sweeps/phase2/sca-convergence-2026-09-04/`. Deferred for this delivery. |
| **G4** | **measured — BYTE-IDENTICAL** | duty 0.1: PF **106.56** / Reservation **117.50** / TwoTier **112.42** ms; Reservation−PF **+10.94** [+5.93, +16.20], TwoTier−PF **+5.86** [+4.50, +7.25]. Every figure reproduces the published one exactly. |
| **G5** | **measured — reproduces** | M05 completeness, protected, n=10: PF **0/10** fail, Reservation **7/10**, TwoTier **4/10**, Reservation's median **0.0000**. The published failure ("median worst-flow PDU-set completeness 0.0000 on both QoS-aware arms") holds. |
| **G6** | **NOT PUBLISHABLE — a second specification defect** | **NEW.** The clause names no estimator over runs, and the three defensible readings give **PASS, INCONCLUSIVE and FAIL on the same cell**. See below. |
| **G7** | **NOT MEASURED — structurally out, unchanged** | No MFBR *enforcement* anywhere in `sim/`; containment is observable, clipping is not, and clipping is half the criterion. |
| **G8** | **FAILS at n=10 — and the published row is contradicted by its own source** | **NEW.** `core_mfbr.json` (n=3) records Reservation starving `ue8_qfi9` for **10.0 s** on 1 of 3 seeds, under a row reading *"0 on all arms"*. At n=10 both conjuncts fail on both QoS-aware arms. See below. |
| **G9** | **NOT MEASURED — named cause, deferred** | `g9_campaign.py`'s count guard refuses to score a partially-degenerate run. Unchanged; deferred for this delivery. |
| **G10** | **measured — BYTE-IDENTICAL** | Admissible fleet **PF 8 / Reservation 4 / TwoTier 4**, per-seed at N=8 **PF 10/10, Reservation 3/10, TwoTier 6/10**. Every number reproduces. |
| **G11** | **C1 re-measured at n=10 — the pass SURVIVES; four clauses still unscored** | **The n≤3 exposure is closed.** C1 = **1.000 on all three arms**, 0 failing windows, 0 unscoreable, **10/10 seeds pass on every arm**, over **20 windows** against 6 at n=3. **This does NOT clear G11:** the horizon is still **400,000 slots — 1.7 min — against GT-7.1's specified ≥30 min**, so it is a pass at 1/18th of the specified duration. C2–C5 remain unscored and are deferred for this delivery. |
| **G12** | **TWO cells; the bar is applied and NEITHER CLAUSE FIRES** | **NEW:** a second cell (`drone_heavy_n8`) Phase 2 never reached, and a **fifth pooling defect in `g12_score`** — in the clause that decides promotion. The registered conclusion stands: the ordering is **not** established as a scheduler property. Its E3 failure is filed under **G1/G3**. See below. |

---

## The four new findings

### 1. G8's published row is CONTRADICTED BY ITS OWN SOURCE FILE

> **CORRECTION to this document's first version and to commit `17d6211`.**
> Both said *"G8's published pass rests on n=1"* on the strength of
> `core_fast.json` being `seeds=1`. **That file is not the source of the
> published row.** Traced by arithmetic: G8's figures reconcile to
> `core_mfbr.json` (**n=3**), and G1's TwoTier 94.51 ms reconciles to
> `core_fixed.json` (**n=3**, pre-MFBR) — *two different runs presented as
> one row set*. The seed-count framing was right in direction and wrong in
> instance, and the real defect is worse than low n.

**The published claim is false against the artefact it came from.** G8's row
reads *"M22 starvation epochs … **0 on all arms** at the core cell"*.
`core_mfbr.json`, n=3:

| seed | arm | M22 all-flow | M22 protected | longest |
|---|---|---|---|---|
| 1826701614 | all three | 0 | 0 | 0.0 s |
| 1367864806 | all three | 0 | 0 | 0.0 s |
| **1097657231** | **Reservation** | **3** | **2** | **10.0 s** |

**One seed of three shows Reservation starving `ue8_qfi9` for ten seconds**,
against a 1 s bar — in the file the row was written from. It was not read.

**And the M09 figures mix estimators within one row.** *"PF 0.9995 /
Reservation 0.9998 / TwoTier 0.9654"*: TwoTier's 0.9654 is the 3-seed mean,
but Reservation's mean is **0.9719** — 0.9998 is seed 1 alone. A single-seed
value and a mean sit side by side with no marking.

**So there are three defects in one row**: a claim contradicted by its
source, two estimators presented as one, and two source files presented as
one run. **None is a code defect** — which the isolation below establishes,
and which is why the row is corrected rather than the simulator.

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

### 1a. THE CATEGORY SEARCH — which other verdicts rest on n ≤ 3

G8 is the instance that proves the question is worth asking, so it was asked
of every committed artefact, derived rather than recalled:

| artefact | seeds | what it backs |
|---|---|---|
| `phase2/core_fast.json` | **1** | nothing published (superseded by the two below) |
| `phase2/core_fixed.json` | **3** | **G1's TwoTier 94.51 ms** |
| `phase2/core_mfbr.json` | **3** | **G8's row, G3's and G5's core figures** |
| `phase2/g11_c1_mfbr.json` | **3** | **G11's C1 "1.000 pass rate, 3/3 seeds"** |
| `phase2/blackout_*.json` | 20 | the blackout table |
| `phase2/g10_rows_mfbr.csv` | 10 | G10 |
| `wp9/stage6_g4.json` | 10 | G4 |
| `wp9/stage6_g6_n40.csv` | 40 | G6 |
| `wp9/stage{1,2,4,5}_rows.csv`, `part_c_rows.csv` | 10–40 | the sweep |

**Four artefacts at n ≤ 3, and they back G1, G3, G5, G8 and G11's C1** — the
entire core-cell row set plus the one G11 clause that was scored.

**G11's C1 was the other candidate, and it was re-measured rather than
assumed.** Registered in advance that it would *not* survive — G8's shape
exactly, and the asymmetry runs one way, since more seeds means more windows
and more chances for any of five conjuncts to breach.

**It survived.** 1.000 on all three arms at n=10, over 20 windows against 6.
**The prediction was a MISS and that is the useful outcome**
(`PREDICTIONS.md`): it establishes that the n≤3 exposure is **not general**,
and that G8's reversal was specific to a starvation counter rather than a
property of low-n passes.

**So the category search found one real instance and cleared the other by
measurement.** Clearing a candidate is the cheaper half of a category search
and the half that usually goes unreported; it is reported here because
without it "four artefacts at n≤3" reads as four open exposures when it is
one.

**Everything else is n ≥ 10.** The exposure is bounded and named.

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

**REGISTERED DISPOSITION — NO G6 VERDICT IS PUBLISHED, AND THAT IS THE
FINDING.** Not "we could not decide", and not a caveat on a number: **a
guarantee whose verdict depends on a choice the guarantee declines to make
cannot be scored by anyone.** It is not that this project lacks the data or
the estimator — it is that the specification admits three readings and the
data separates them. A different team, on different code, with a different
simulator, would face the same three answers.

**This is the fourth specification finding and the strongest of them**,
because the other three are about a guarantee being hard to score and this
one is about it being *undecidable as written*:

| # | finding | shape |
|---|---|---|
| 1 | G6's +20 % bar is undefined at a zero baseline | the bar has no value in a reachable case |
| 2 | GT-7.3's ramp does not reach its own failure condition | the test runs outside the regime its evidence needs |
| 3 | G10's all-pass criterion cannot distinguish 1/10 from 6/10 | a binary criterion over a non-binary quantity |
| **4** | **G6 names no estimator, and the three readings disagree** | **the verdict is a property of an unmade choice** |

**Findings 1 and 4 are both G6, in one sentence of specification.**

**What would make G6 publishable:** its owner ratifying **an estimator and a
run count** — both, since the per-run reading's verdict moves with n. Until
then the tool reports all three readings side by side and marks the
disagreement, and this project publishes no G6 verdict. Choosing in code
would be the tool deciding what the specification declined to.

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

### THE PROMOTION BAR: NEITHER CLAUSE FIRES — and a correction

> **CORRECTION.** An earlier report of this pass said *"the promotion bar now
> fires"* and called it a reversal. **It does not fire.** That claim came from
> `g12_score.apply_promotion_bar`'s output, and the scorer's clause 1 was
> weaker than the criterion §35.13 registered. **Reporting a scorer's output
> without checking the scorer implements the registered bar is the failure
> this project keeps recording, committed here on the bar itself.**

**The fifth pooling defect in `g12_score.py`, and the one that decides
promotion.** Clause 1 as registered is *"the arms' order distributions differ
**in the same direction** under **every** permutation tested, canonical
included."* The implementation collapsed every permutation into one **set**
per arm and asked only whether the arms' sets differ — PF `{[4,2]}` against
Reservation `{[4,2],[2,4]}` differ, so it returned True. **A pooled set
cannot see a direction, and direction is the whole criterion.** Fixed; a tie
is now explicitly not a lean, because two arms cannot differ in a direction
if one has none.

**Applied as written, per condition:**

| condition | PF | Reservation | TwoTier |
|---|---|---|---|
| canonical / `drone_heavy_n8` | `[4,2]` | `[4,2]` | `[4,2]` |
| canonical / `mixed_n8` | `[4,2]` | `[4,2]` | **TIE** |
| perm 101 | `[4,2]` | `[4,2]` | `[2,4]` |
| perm 102 | `[4,2]` | **`[2,4]`** | `[2,4]` |
| perm 103 | `[4,2]` | **`[2,4]`** | `[2,4]` |
| perm 104 | `[4,2]` | **`[2,4]`** | `[2,4]` |

| pair | differs in | same direction throughout |
|---|---|---|
| PF – Reservation | 3/6 conditions | **False** |
| PF – TwoTier | 4/6 conditions | **False** |
| Reservation – TwoTier | 1/6 conditions | **False** |

**⇒ CLAUSE 1 DOES NOT FIRE.**

**And the trace answers clause 2 in the direction the bar anticipated.**
Asked first, because it is the cheapest discriminator and the data was
already in the campaign: *does the order depend on list position at all?*

- **PF does not.** `[4,2]` under the canonical order and under **all four
  permutations**, 5/5 each.
- **Reservation does.** `[4,2]` under canonical and perm 101; **`[2,4]` under
  102, 103 and 104** — unanimous 5/5 under 104, the opposite of canonical.
- **TwoTier does.** Tied 5/5 under canonical, leaning `[2,4]` under every
  permutation.

**The effect moves with list position on exactly the two arms that show it.**
Per the bar's own edge — *"tracing the effect to any of the three candidates
CONFIRMS the artefact; it does not refute it"* — **this confirms the
artefact.** It does not promote the finding, and the bar said so in advance,
before these numbers existed.

**⇒ NEITHER CLAUSE FIRES. The registered conclusion applies verbatim:** the
Region-2 ordering is **not established as a scheduler property and is
consistent with a declaration-order artefact.**

**One thing genuinely changed, and it is not a promotion.** §35.5's pre-fix
data had **PF** as the position-sensitive arm (*"PF's permutation 104 gives
the opposite first-violation order from 101/102/103"*). After the
`priority_level` fix, **PF is the stable one** and the sensitivity has moved
to Reservation. The artefact did not go away; it changed which arm carries
it. Recorded as an observation — characterising a distribution over
permutations is out of bounds on four of them (§35.13's own limit).

**And E3 is worse on the new cell:** TwoTier's telemetry M02 reaches 1.000
from **×1.0 — nominal load** — on `drone_heavy_n8`, against ×1.6 on
`mixed_n8`, with 5QI 9 still carrying 17.4 Mbps.

**E4's decomposition earned itself immediately.** Per (cell, arm): 16.8–17.4
Mbps on `drone_heavy_n8` against **0.345 Mbps** on `mixed_n8/Reservation` — a
50× spread that a pooled median across two cells would have reported as one
number. The four sites were fixed one commit before the run that needed them.

---

## G12's E3 — filed under G1/G3, and worse on the new cell

**G12's clause 4 fails inside the guarantee's own ramp, and the new
composition makes it worse.** Filed here as a **G1/G3** finding because that
is what it is about — telemetry latency and liveness — not about degradation
ordering.

| cell | arm | earliest telemetry M02 = 1.000 | 5QI 9 at that point |
|---|---|---|---|
| `mixed_n8` | PF | ×2.3 | — |
| `mixed_n8` | Reservation | ×2.3 | — |
| `mixed_n8` | **TwoTier** | **×1.6** | — |
| `drone_heavy_n8` | PF | ×2.3 | — |
| `drone_heavy_n8` | Reservation | ×2.3 | — |
| **`drone_heavy_n8`** | **TwoTier** | **×1.0 — NOMINAL LOAD** | **17.4 Mbps** |

**On `drone_heavy_n8`, TwoTier's telemetry reaches M02 = 1.000 — every
resolved byte PDB-violated — at ×1.0, with no overload applied at all**,
while the best-effort 5QI-9 class still carries **17.4 Mbps**. That is
GT-7.3's own worked FAIL example, at nominal load, on the deployed arm.

Every one of the six groups degrades on **10/10 seeds**, and every earliest
point is **inside** the guarantee's ramp.

**And the gap statistic is blind on 240 ramp points** — a flow that has
stopped completing has no gap between completions to measure — so M02 is the
instrument with range here and M03/M20 must not be read alone on a starved
flow. That is the same blindness G3's row already carries; this pass doubles
the count of ramp points it affects.

**Two qualifications travel with it**, unchanged: the arm difference in the
*ordering* is not established (the bar does not fire, above), and this is a
**telemetry** reading while E1's clean-control check covers M13's GBR
classes — 5QI 1 is `Delay`, so the control does not cover it.

## G11's horizon question — PRICED, MEASURED, and running

The seed half closed (C1 survives at n=10); the horizon half was the only
thing between C1 and a real answer. It is now measured rather than projected.

**MEASURED at 7,200,000 slots (30 min sim), N=4, on the campaign path:**

| arm | wall | peak RSS | windows |
|---|---|---|---|
| PF | 15.1 min | 1,912 MB | 30 |
| Reservation | 18.9 min | 1,935 MB | 30 |
| **TwoTier** | **33.4 min** | **1,960 MB** | 30 |

**Against the projection, which was extrapolated 4.5× beyond its largest
measured point:** the affine fit over 0.4–1.6 Mslot (461 MB + 186 MB/Mslot,
R² = 0.998) predicted **1,800 MB**; measured **1,960 MB** — **+8.9 %**.

**The fit is usable and OPTIMISTIC, and 8.9 % lands exactly where it
matters.** At the projected figure W=12 needs 21.1 GiB of ~24 usable; at the
measured one it needs **23.0 GiB — 0.9 GiB of headroom**. The error does not
change whether the soak fits; it changes whether W=12 is a safe operating
point. **§37's rule — measure at the horizon you will run — paid again, and
not by refuting the fit.** It paid by showing the fit optimistic at the
margin where the worker count is decided.

| W | total at 1,960 MB/run | |
|---|---|---|
| 16 | 30.6 GiB | exceeds |
| **12** | **23.0 GiB** | fits, 0.9 GiB spare |
| **10** | **19.1 GiB** | **the operating point** |
| 8 | 15.3 GiB | fits |

**Campaign cost: 11.2 h CPU; ~1.3 h wall at W=10** (LPT floor 0.56 h, one
TwoTier run).

**So C1 at the specified horizon is affordable, and it is running** — n=10,
W=10, banked per run, launched detached (`setsid`) so a session compaction
cannot take it. When it lands, C1 stops being a 1/18th-duration pass and
becomes 30 windows per run against 2. **C2–C5 remain deferred.**

**One thing that measurement exposed, and it qualifies every C1 result so
far:** at 400,000 slots **three of GT-7.1's four scripted ingredients are
absent** — no firmware push, no STOP drill, no waypoint pause. C1's existing
pass is not merely short; it is short *and* missing most of its schedule.
`docs/wp9-defects-log.md` #23, now refused at construction.

## What this pass did not cover

**G2, G9, G11's remaining clauses, and G3's delta clause are deferred for
this delivery**, each with a structural reason recorded above rather than
left as a gap. No work was started on any of them.

**Artefacts:** `sweeps/verification-2026-09-04/`.
