# Running log: corrections to TEST DEFINITIONS (not to schedulers)

Changes to what a guarantee procedure *measures*, kept apart from scheduler
work so a moved number is never ambiguous between "the scheduler changed" and
"the test changed". Every entry says what was wrong, what it now does, and the
**measured effect on existing artefacts**.

**These are re-scorings, not re-runs.** The runners in this repo emit RAW
statistics and compute verdicts in a separate `score()` pass, precisely so a
definition can be corrected without re-simulating. Where that holds it is
stated per entry.

---

## 1. G6 (GT-4.1 / GT-4.2) — two defects, 2026-09-16

G6 asks: *with a saturating 5QI-9 flood added, does every G1/G3/G5 statistic
stay inside its bound (part A) and shift by no more than +20 % in the
direction of harm (part B)?*

### 1.1 Part A had no control-health gate — FIXED

**The defect.** Part A tested the *treatment* row against its bound with no
reference to whether the **control** (same seed, same fleet, NO flood) already
failed that same bound. An arm broken at a fleet size for reasons that have
nothing to do with isolation was scored as a G6 failure, attributing a
pre-existing capacity fault to the aggressor.

**The fix.** A cell is scored only if its control is healthy — the treatment's
bound result is meaningless otherwise. Mirrors `g9_stress._cell_broken_pre_join`,
which gates on the incumbents' health *before* the joiner arrives. Gated cells
are **emitted** (`control_healthy`, `scored`), never silently dropped.

**Measured effect** (campaign artefact, 540 deltas per arm):

| arm | gated (control already broken) | part-A failures before | after |
|---|---|---|---|
| ConfigSched | 86 | 86 | 8 |
| PF | 88 | 89 | 11 |
| ProtoRRageD2 | 50 | 62 | 26 |
| Reservation | 120 | 132 | 27 |
| TwoTier | 180 | 222 | 46 |

**TwoTier's part-A failures fall 222 → 46: four fifths of what G6 called an
isolation failure was the cell already failing with no flood at all.** The
gated cells are almost entirely the camera statistics
(`g5_cam_window_floor`, `g5_cam_complete`, `g5_cam_age_p95_ms`).

### 1.2 Part B compared a ratio with no absolute floor — FIXED

**The defect.** A +20 % relative bound on a small quantity is not a measure of
harm. Measured on the campaign artefact, every part-B failure of
`g1_cmd_p98_ms` is a move of **1.5–4.0 ms against a 95 ms bound** — shifts of
+55 % to +114 % that consume 6–9 % of the deadline — while a flow sitting at
90.0 ms and moving to 90.1 ms **passes** at +0.1 %. The ratio reported the
opposite of the danger.

**The fix.** A shift counts as harm only if the absolute move also consumes at
least `FLOOR_FRACTION = 0.05` of the statistic's **own bound**, derived from
`BOUNDS` rather than chosen per metric.

**A first attempt at this is recorded because it was wrong.** It used
hand-picked per-statistic epsilons (1.0 ms, 10 ms, 2.0 ms, 0.005) and
reclassified **zero** rows — the smallest failing move cleared the floor on all
eight statistics. That is a check that could not fail, this project's
most-recorded defect shape, and it was caught by measuring the reclassification
count instead of assuming the guard worked.

**Measured effect:** reclassifies **46 rows, all `g1_cmd_p98_ms`**. Two
statistics sit close to the line — `g3_tele_gap_worst_ms` smallest kept failure
26.0 ms against a 25.0 ms floor, `g5_cam_age_p95_ms` 3.42 against 3.33 — so the
fraction is **a judgement at the margin, not a derivation**, and is labelled so
in the code.

### 1.3 No re-run was required

`g6_isolation.py`'s runner emits raw statistics and `score()` computes both
parts from the paired rows. Both corrections are re-scorings of the existing
`g6.json` artefacts. **43 M slots were not re-simulated.**

### 1.4 STILL OPEN — G6's fleet axis runs past capacity

`UE_AXIS = (4, 7, 12)` was chosen to bracket G10's boundaries
(PF 12 / Reservation 6 / TwoTier 7). The consequence, visible now that the gate
counts it: broken-pre-flood cells for TwoTier are **12 at N=4, 54 at N=7, 114 at
N=12**. At N=12 most arms are past their admissible fleet, so the camera cannot
be served *with no flood at all* and two thirds of the grid cannot answer an
isolation question.

**Not changed yet**, because narrowing the axis changes which cells exist rather
than how they are scored, and would need a re-run. Registered as the next G6
decision: either run the axis per-arm inside each arm's own admissible boundary,
or keep the wide axis and report the gate count as a first-class result.
