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

---

## 2. Audit: does the same defect class exist in the other runners? (2026-09-16)

Prompted by the standing instruction to re-check finished runs whenever a new
defect is found. G6's two defects were (a) scoring a treatment without asking
whether the **control** was already failing, and (b) a **ratio with no absolute
floor**. Every runner that scores a comparison was checked for both.

| runner | control-health gate | ratio without a floor | verdict |
|---|---|---|---|
| `g6_isolation.py` | was MISSING | was PRESENT | **both fixed** (§1) |
| `g9_stress.py` | `_cell_broken_pre_join` | n/a | **clean** — it is the precedent G6's fix mirrors |
| `g12_stress.py` | `_gate` + `assert_ramp_bottom_clean` | n/a | **clean**, and it reasons explicitly about what *not* to gate on |
| `g5_video.py` | n/a (absolute-bound test, no control condition) | no | **clean** |
| `g7_aggressor.py` | **MISSING, and cannot be added by rescoring** | no — the 10 % tolerance is declared as a judgement in the source | **OPEN, see below** |

### 2.1 G7 clause 1 has no control — OPEN, needs a run not a rescore

GT-4.3 clause 1 is *"Asset A entirely within SLO"*, judged against absolute
bounds while Asset B's camera is over-driven to 2.1x MFBR. **There is no
paired no-aggressor run**, so the procedure cannot distinguish

* the aggressor harmed Asset A — *containment failed*, which is what the
  clause claims to measure; from
* Asset A was already outside SLO at N = 8 with no aggressor at all —
  *capacity*, which says nothing about containment.

This matters here specifically because G6's corrected scoring showed that
exact confusion was inflating G6: the camera statistics are gated on 43–90
cells per arm because the control already failed. G7 runs at N = 8 with a
camera on every asset, so the precondition for the same confusion is present.

**Why it is not fixed in this commit.** G6's defects were re-scorings — the
runner already recorded the control, so 43 M slots did not have to be repeated.
G7 records no control, so closing this means adding a paired no-aggressor run
per seed and re-running the procedure. That is a scenario and runtime change,
not a scoring change, and it gets its own commit and its own re-measurement.

**Until then**, every G7 clause-1 result — including the ConfigSched2 increment
comparisons and `ProtoRRageD2`'s — is an **upper bound on harm**: it counts
capacity failures as containment failures, and cannot count them the other way.
The clause-2 and clause-3 results are unaffected (clause 2 is a ratio against
the aggressor's own MFBR; clause 3 is internal to Asset B).

---

## 3. G7 clause 1 gains a paired control — REGISTERED BEFORE BUILDING (2026-09-16)

§2.1 found the defect; this specifies the fix before it is written, so the
result cannot be walked back later.

### 3.1 What changes

For every (arm, seed) G7 already runs, run a **paired control**: the identical
scenario with Asset B's camera at its **nominal** rate instead of 2.1× MFBR.
Everything else — fleet, seeds, cap, attach path, horizon — held fixed, so the
comparison is within-seed, the only form that can attribute.

Clause 1 is then scored as G6's part A now is:

* **control fails its own SLO** → the cell is **unscoreable** for containment,
  emitted with a reason and counted, never silently dropped;
* **control passes, treatment fails** → containment genuinely failed;
* **both pass** → clause 1 passes.

Clauses 2 and 3 are untouched: clause 2 is a ratio against the aggressor's own
MFBR, clause 3 is internal to Asset B, and neither asks a victim-health
question.

### 3.2 Cost, and why it is affordable

G7's step is ~4 s of a ~10 min increment, so a paired control roughly doubles
the cheapest step in the suite. There is no reason to approximate this.

### 3.3 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | a non-zero number of cells come back **unscoreable** at N = 8 | zero — then the victim was never pre-broken and §2.1's concern, while structurally right, does not bite on this cell; the gate stays anyway, as G12's does |
| 2 | part of the ConfigSched2X3 clause-1 regression (A telemetry p98 57.8 → 96.5 ms) is revealed as pre-existing rather than caused by the aggressor | the treatment/control gap being as large as the raw regression — then the regression is real containment harm and the E-series verdicts on group D stand unchanged |
| 3 | the arms re-rank on clause 1 once gated, as they did on G6 | no re-ranking |

**Expectation 2 is the one that matters for the scheduler work**, because every
E-series arm is currently judged partly on a clause 1 that cannot separate
containment from capacity. Until this lands, **every G7 clause-1 figure in this
repo — baseline and increments alike — is an upper bound on harm**, and the
increment write-ups say so.

### 3.4 Sequencing

This is a scenario-and-runner change, not a rescore, so it needs its own commit
and its own re-measurement of G7 across the arms. It is deliberately NOT bundled
with the config-scheduler increments: bundling a test-definition change with a
scheduler change makes every moved number uninterpretable, which is the whole
point of the one-change-per-commit rule.

### 3.5 MEASURED, first run with the control (ConfigSched2, N = 8, 10 seeds)

| seed | A telemetry p98 (treatment) | control | A camera p98 (treatment) | control |
|---|---|---|---|---|
| 35492826 | 86.5 | 58.5 | 65.7 | 39.7 |
| 87989972 | 67.0 | 41.0 | 47.9 | 36.6 |
| 1097657231 | 99.5 | 57.0 | 66.2 | 40.2 |
| 1367864806 | 46.0 | 44.0 | 46.0 | 37.6 |
| *(all 10 seeds; PDBs: telemetry 100 ms, camera 150 ms)* | | | | |

**Expectation 1 is FALSIFIED.** It predicted a non-zero number of cells would
come back unscoreable. **0 of 10 are gated** — Asset A's control is inside its
SLO on every seed at N = 8 on this arm. The gate is kept anyway, exactly as
§3.3 said it would be, and for the same reason G12 keeps its own: a gate that
does not fire here still separates capacity from containment the moment an arm
or a fleet size makes the victim pre-broken. What is now established is that
**on `ConfigSched2` at N = 8 it does not**, so clause 1's failures on this arm
are real containment effects, not capacity artefacts.

**Expectation 2 is supported, and it is the consequential one.** The
aggressor's OWN contribution — treatment minus its paired control — is:

* A telemetry p98: **median +7.8 ms**, max +42.5 ms
* A camera p98: **median +9.7 ms**, max +26.0 ms

against raw treatment values of 46.0–99.5 ms. **So roughly four fifths of
clause 1's raw number is load that is present with no aggressor at all.**
Reporting the raw p98 as containment harm overstates it several-fold.

### 3.6 What this obliges, and what is NOT yet claimed

Every E-series G7 clause-1 figure in `docs/configsched2-diagnosis-2026-09-16.md`
was measured **without** controls, since the controls did not exist until this
commit. The reported regressions there (A telemetry p98 57.8 → 96.5/98.0 ms)
therefore mix the arm's own latency under load with containment harm, and
**cannot be decomposed retrospectively** — the control runs were never made.

**Not claimed:** that those regressions are artefacts. The control measured
here is `ConfigSched2`'s, and an arm that serves half as many grants may well
have a worse control too, which would mean MORE of its raw number is
capacity — or less. It has to be run per arm.

**Owed:** re-measure G7 with controls across the arms before any G7 clause-1
comparison between them is quoted again. Until that lands, the upper-bound
caveat in §2.1 stands for every arm except `ConfigSched2` at N = 8.

---

## 4. G9's occupancy axis is anchored to the WRONG CELL — REGISTERED BEFORE BUILDING

### 4.1 The defect

`scripts/g9_stress.py`'s axis is

    OCCUPANCY = ((3, 0.50), (4, 0.75), (5, 1.00), (6, 1.25), (7, 1.50), (8, 2.00))

as `(total_ues, committed_mult)`, and its own comment says levels are *"named by
TOTAL UEs so they can be read straight against G10's admissible boundary."*

**That reading is false for every level except `(5, 1.00)`.**
`sim/workload.py::scale_committed_load` scales each committed flow's offered
load *and its contract fields* by `committed_mult`, so a level's effective
promised load is **n x mult** UE-equivalents — while **G10's boundary is
measured at `committed_mult = 1.0`** (`g5_consolidation.py:56`; the campaign
passes no override). The two quantities are not comparable.

Effective load per level, against this cell's measured boundary:

| level | n x mult | vs boundary 8 (CG arms) | vs boundary 10 (no-CG arms) |
|---|---|---|---|
| (3, 0.50) | 1.5 | 0.19x | 0.15x |
| (4, 0.75) | 3.0 | 0.38x | 0.30x |
| (5, 1.00) | 5.0 | 0.63x | 0.50x |
| (6, 1.25) | 7.5 | 0.94x | 0.75x |
| (7, 1.50) | 10.5 | **1.31x** | 1.05x |
| (8, 2.00) | 16.0 | **2.00x** | **1.60x** |

Boundaries re-derived from the artefacts (`M07_met == M07_total` across all ten
seeds): `ConfigSched2` / `X6` / `X7` = **10**; `ConfigSched2+CG` /
`ConfigSched2X7+CG` = **8**.

**This is where every anomaly landed.** All twelve unscoreable cells on `X7`
and all five join failures on both CG arms occur at `n7_cm1.5` and `n8_cm2` —
i.e. at 1.31x and 2.00x the measured capacity. A failure rate dominated by two
points that are 31 % and 100 % past capacity is not a property of the arm.

### 4.2 The change

Keep the deliberate two-dial design — the docstring's *"an operator does not
experience six robots and 1.5x the committed load as separate facts"* is a real
argument and is not being discarded — but **anchor the levels to this cell's
measured boundary and label them by effective load**:

    OCCUPANCY = ((2, 1.00), (4, 1.00), (6, 1.00), (8, 1.00), (8, 1.25), (8, 1.50))
    #   effective load: 2, 4, 6, 8, 10, 12  =  0.25x 0.50x 0.75x 1.00x 1.25x 1.50x of B=8

Four levels inside capacity, one exactly at the boundary, two past it by a
**controlled** 25 % and 50 % instead of 100 %. The top of the axis still
exercises the gate — that is what the gate is for — without spending a third of
the grid on points nothing can answer.

### 4.3 Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | **zero** CELL ALREADY BROKEN at levels <= 1.00x on the CG arms | any broken cell inside capacity — then the boundary or this arithmetic is wrong, and the axis is not the explanation |
| 2 | join failures, if any, occur only **above** 1.00x | a failure at <= 0.75x — then failures are a property of the arm, not the axis, and §22.2a's reading must be revisited |
| 3 | scoreable cells rise materially against the old axis (12 unscoreable on `X7` → far fewer) | no rise — the axis was not what made cells unanswerable |
| 4 | `ConfigSched2X7+CG` retains at least parity with `ConfigSched2+CG` at matched levels | it falling behind — the recommendation in `docs/qos-scheduler-result-2026-09-16.md` §1 would need revisiting |

**Expectation 2 is the load-bearing one.** If join failures appear inside
capacity, the five failures are real arm behaviour and the standalone doc's
"not yet a property of any arm" caveat becomes a finding instead.

### 4.4 Sequencing, and why no module edit is needed to measure it

`g9_stress.py` already takes `--occupancy 'ues:mult,...'`, so **the
re-measurement is a runner invocation with no code change**. Only promoting the
new default is an edit, and that is its own commit, made *after* the measurement
justifies it. The old artefacts stay as measured.

### 4.5 MEASURED (`sweeps/cs2-increments/g9_newaxis_2026-09-16.json`, 720 runs)

Both CG arms, 3 cases x 2 seed-columns x 6 levels x 10 seeds.

| effective load | xB | `ConfigSched2+CG` P/F | `ConfigSched2X7+CG` P/F |
|---|---|---|---|
| 2.0 | 0.25 | 6 / 0 | 5 / **1** |
| 4.0 | 0.50 | 6 / 0 | 6 / 0 |
| 6.0 | 0.75 | 6 / 0 | 5 / **1** |
| 8.0 | 1.00 | 2 / **4** | 5 / 1 |
| 10.0 | 1.25 | 2 / 4 | 5 / 1 |
| 12.0 | 1.50 | 2 / 4 | 5 / 1 |
| **total** | | **24 / 12** | **31 / 5** |

**Unscoreable cells: 0 of 36 on both arms** (against 12 of 36 on `X7` under the
old axis).

| # | registered (§4.3) | outcome |
|---|---|---|
| 1 | zero unscoreable at <= 1.00xB | **MET** — zero at every level |
| 2 | join failures only above 1.00xB | **FALSIFIED** |
| 3 | scoreable cells rise materially | **MET** — 24 of 36 → **36 of 36** |
| 4 | X7+CG at least at parity | **MET and exceeded** — 31/5 against 24/12 |

**Expectation 2, the load-bearing one, is falsified.** `ConfigSched2X7+CG` fails
a join at **0.25xB** — two UEs at nominal load, deep inside capacity — and again
at 0.75xB, each on 1 seed of 10. `ConfigSched2+CG` fails four cells *at* the
boundary itself. **So the join failures are NOT an axis artefact**, and the
caveat written in `docs/qos-scheduler-result-2026-09-16.md` §5 and
`docs/configsched2-diagnosis-2026-09-16.md` §22.2a — that the failure rate is
"not yet a property of any arm" — is withdrawn. It is partly a property of the
arms, and both documents are corrected.

**And the stale axis was masking a real difference between the arms.** On the
old axis both read an identical 31 PASS / 5 JOIN FAILURE. Anchored, they
separate sharply: **X7+CG 31/5 against the fallback's 24/12**, with the fallback
failing `cold` and `rlf` on both columns at every level from the boundary
upward. That strengthens the recommendation rather than weakening it — but it
was invisible while a third of the grid was unanswerable.

**Still untraced:** X7+CG's two sporadic failures well inside capacity (1 seed
of 10 at 0.25xB and at 0.75xB, both `cold`). A join failure at two UEs is not a
capacity effect and has no explanation yet.

The anchored axis is now `g9_stress.py`'s default, in its own commit, as §4.4
said it would be.
