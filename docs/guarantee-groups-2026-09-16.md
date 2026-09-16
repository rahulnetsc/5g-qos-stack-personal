# Guarantee groups, and the regression contract for tuning a scheduler

**Decided 2026-09-16 (user).** The objective is a QoS-aware scheduler
proposal, and the two candidates being tuned are **`ProtoRRageD2`** and
**`ConfigSched`**. Every experiment reports all five arms; increments are
applied only to those two. This file is the contract the tuning runs
against: what the groups are, what each isolates, how they couple, and the
rule that decides whether an increment is kept.

## 0. Scope

**In scope, nine guarantees:** G1, G2, G3, G5, G6, G7, G9, G10, G12.

**Deferred to the end, three:** G4 (its only procedure is GT-2.3, unbuilt —
`g4_postsilence.py` answers a different question, and the test plan calls
real RF essential for the clause), G8 (no runner exists in `scripts/`) and
G11 (the shift-long soak). Nothing in this file's tables covers them, and
no verdict should be quoted for them.

The nine in scope are exactly the nine steps
`sweeps/cs2-increments/run_increment.sh` already runs, so a one-arm
increment measurement covers the whole in-scope set in about 20 minutes.

## 1. The groups

Each group is one functional requirement with its own failure mechanism,
its own runners, and its own place to look when it breaks.

| group | guarantees (procedure) | runners | what it isolates | 5 arms | 1 arm |
|---|---|---|---|---|---|
| **A — Downlink deadline** | G1 (GT-1.1), G2 (GT-1.2) | `g1_stress.py`, `g2_stress.py` | DL ordering, the per-slot DCI cap, and how many HARQ retries fit inside a short PDB | ~34 min | ~8 min |
| **B — Uplink liveness** | G3 (GT-2.2) | `g3_stress.py` | *when* a small periodic UL flow is next served — service interval, silence, cadence | ~9 min | ~1 min |
| **C — Uplink video** | G5 (GT-3.1/3.2/3.3) | `g5_video.py` | sustained byte rate and frame assembly: PDU-set completeness, frame age, GFBR per 2 s window | ~8 min | ~1 min |
| **D — Isolation & containment** | G6 (GT-4.1/4.2), G7 (GT-4.3) | `g6_isolation.py`, `g7_aggressor.py` | harm from a bad actor: a non-GBR flood (G6, a within-seed delta test) and a GBR bearer over-driven past MFBR (G7) | ~8 min | ~1 min |
| **E — Capacity & degradation** | G10 (GT-5.2), G12 (GT-7.3) | `g5_consolidation.py`, `g12_stress.py` | the cell at and past its limit: admissible fleet, and the order classes break in | ~7 min | ~1 min |
| **F — Transitions** | G9 (GT-6.1/6.2/6.3) | `g9_stress.py` | join, re-join and RLF recovery — the only group whose stimulus is a UE arriving or leaving | ~12 min | ~2 min |

Flags per group, as the campaign script passes them, are in
`sweeps/cell-2026-09-16-linux/run_campaign.sh`; a single-arm run of all six
groups is `sweeps/cs2-increments/run_increment.sh`.

## 2. How the groups couple

They are **not orthogonal**, and the point of writing the couplings down is
that a tuning change must re-check the groups it can reach, not only the one
it targets.

| coupling | why | consequence for tuning |
|---|---|---|
| **A ↔ B, C, E** | `HarqProcessPool.due_this_slot()` iterates one shared dict across every (UE, direction) pool, so a DL-only change can reorder UL retry draws and vice versa (CLAUDE.md, measured on Phase-2 commit 3) | small but real; A must be re-run after uplink work, and a 1–2-seed move in A after a UL change is expected, not a defect |
| **B ↔ D** | G6's telemetry instrument **is** G3's flow, measured under a flood | any cadence change moves D's telemetry half; D's camera half is independent |
| **C ↔ E** | both spend the same uplink bytes — G5's frames and G10's GBR floors are the same resource seen two ways | a sizing, floor or shedding change moves both; never tune one without reading the other |
| **F ↔ E** | G9's occupancy axis is derived from G10's admissible boundary | if E's boundary moves, F's axis is stale (it already is: the axis came from the previous cell, so F's top two points are past capacity) |
| **A ↔ D** | G6's G1 instrument is the `cmd_vel` flow of A | D's part-B shift test sees any DL deadline change |

## 3. The regression contract

For every increment, on the arm being tuned:

1. **Name the target group and register the expectation before the run** —
   what should move, in which direction, and what would falsify it.
2. **Run all six groups for that arm** (`run_increment.sh`, ~20 min), never
   just the target. The couplings above are the reason.
3. **Compare against that arm's previous kept state** with
   `sweeps/cs2-increments/compare.py <inc> --before <prev> --arm-before <arm>`.
4. **Keep the increment only if:** the target group's *verdict* improves
   (boundary, pass count, or the clause's own statistic) **and no other
   group's verdict degrades**. A within-group metric that moves without
   changing a verdict is recorded, not a veto.
5. **Score the registered expectation honestly** — a miss is written down
   with its number, and the increment's note says what the miss taught.
6. **A reverted increment stays in the log** with its measurement. Four of
   the first nine were reverted; the reasons are the most reusable part of
   the record.

**And the standing rule from the user, 2026-09-16: if a bug is found, every
result it affects is re-run before anything from it is reported.** A known
bug plus a published number is not an acceptable combination at any point.


## 3a. THE CONTRACT HAS A HOLE: guarantees in no group are silently exempt

Found 2026-09-16, after nine increments had been scored against it.

§1's six groups cover **G1, G2, G3, G5, G6, G7, G9, G10, G12** — nine of the
twelve guarantees. **G4, G8 and G11 belong to no group**, and the regression
contract in §3 is expressed per group. So "no regression in the other groups",
the expectation every increment in
`docs/configsched2-diagnosis-2026-09-16.md` was registered against, **could
never have covered them.**

That is not a theoretical gap. **G4 regressed monotonically across the entire
increment series and nobody saw it**: post-silence resume p98 at duty 1.0 went
22.00 ms (`ConfigSched+CG`) → 29.47 (`ConfigSched2+CG`) → 47.25
(`ConfigSched2X7+CG`), leaving the recommended arm the worst of any arm
measured. `sweeps/cs2-increments/run_increment.sh` does not run G4 — its runner
takes no `--arms` — so nine increments were scored over **eight** guarantees
while the contract was written as though it covered everything outside the
group under test.

**A deferral became an exemption, silently.** G4 was deferred early as one of
three "come back to these at the end". Deferring a *measurement* is a schedule
decision; dropping it from the *contract* is a scope decision, and the first
quietly made the second.

### 3a.1 The rule this adds

**Every guarantee is either in a group, or named in the contract as exempt with
a reason.** There is no third state. Concretely, as of now:

| guarantee | status |
|---|---|
| G1, G2, G3, G5, G6, G7, G9, G10, G12 | in groups A–F, covered by §3 |
| **G4 (GT-2.3)** | **not in a group, and NOT exempt** — measured for all 24 arm/CG combinations 2026-09-16, and it must be scored per increment or the runner must be given `--arms` |
| **G8, G11** | **not in a group, deferred, and unmeasured on this cell** — no arm has a result, so no increment's effect on them is known in either direction |

**For G8 and G11 the honest statement is not "they pass" or "they are
unaffected" — it is that nothing is known.** Any claim about an arm's overall
standing is a claim over nine of twelve guarantees, and the write-ups say so.


## 3b. FLEET COMPOSITION IS A STANDING AXIS (2026-09-16)

Every result in this evaluation before this date was measured on **one fleet
composition**. `sim/fleet.py` defines four — `mixed`, `ugv_heavy`,
`drone_heavy`, `sensor_dense` — over five UE roles, and argues in its own
docstring that composition is a primary axis because *"'N=16' is not an index in
a heterogeneous deployment"*. Only `sim/scenarios/g12.py` imports it, and G12
itself had only ever run `mixed`.

**Probed and it earned its place** (`docs/composition-probe-2026-09-16.md`,
2 640 runs, 6 cells x 2 arms x 10 seeds x 2 tie-break):

* it does **not** change which arm wins — clause 4 holds 10/0/0 on all 24 cells
  and no ranking inverts;
* it **does** change the degradation order in 45–60 % of seeds, paired
  within-seed, on both arms;
* and it exposed a **3x best-effort throughput deficit** in the recommended arm
  that `mixed` had kept below the threshold where any guarantee notices it.

### 3b.1 The rule

**A result quoted without its composition is incomplete**, in the same way a
measurement quoted outside its configuration is (CLAUDE.md's category-error
rule). Concretely:

1. Any new increment measured on G12 runs **`mixed`, `ugv_heavy` and
   `drone_heavy`** at the sizes under test. `sensor_dense` is **unscoreable** for
   G12's ordering test at any practical N — a 3 % UGV share means no 5QI-4 — and
   `g12_stress.py` now excludes such a cell by name rather than crashing in a
   worker.
2. Guarantees whose builders take no composition parameter (G1, G2, G3, G5, G6,
   G9) state that limitation beside their result. **G5's admissible-fleet
   headline is the one that matters most**, and plumbing composition into
   `build_gt31_scenario` is the registered next step if that number is to be
   relied on.
3. Order comparisons across compositions are scored **paired within-seed**. A
   set comparison of `orders_seen` cannot distinguish composition from an arm's
   own seed-to-seed instability, and on this data it concealed a real effect.

## 4. Where each tuning target stands per group, before any of this work

From the campaign (`docs/results-cell-2026-09-15.md`) and the ConfigSched2
increments (`docs/campaign-cell-2026-09-16-linux.md` §8). ConfigSched shows
prototype → rebuilt where they differ.

| group | ProtoRRageD2 | ConfigSched | the reference to beat |
|---|---|---|---|
| A | = TwoTier; G1 pass, G2 263 at cap 2 | G1 cap 2 10.5–20.5 → **5–15 ms**; G2 1 390 → **291** | deadline arms 247–263; every arm fails G2 on the retry budget |
| B | boundary **10**, silences ≤ 494 ms | **10**; part-1s boundary 16 → **24**, silences ≤ 294 ms | PF 10 |
| C | **8 / no knee to ×1.5** | 7 / ×1.1 → **6 / ×1.0** ← weak | PF 8 / ×1.4 |
| D | G7 **0.82×** | G7 0.92× → **1.04×** ← weak | G6 fails on every arm (shift test) |
| E | G10 **7** ← weak | G10 **10**, G12 fine | PF 8 |
| F | **12/12** | 9/12 → **12/12** | PF 11/12 |

**So the grouping localises each target to a small number of groups:**
ProtoRRageD2 to **E** alone, and ConfigSched2 to **C and D** — which share
one traced cause (the table gives a contracted flow with backlog any free
DCI beyond its plan, so an over-driven camera exceeds MFBR and a competing
camera takes the instrument's bytes). One increment addresses both.


## 4a. Where each tuning target stands, updated 2026-09-16 (after D1 and the E-series)

Supersedes §4, which predates this work.

| group | baseline `ConfigSched2` | best variant found | cost |
|---|---|---|---|
| **A — DL deadline** (G1, G2) | G2 cap-4 202/18300 | **X7: 176** | none measured |
| **B — UL liveness** (G3) | **boundary 10** | nothing beats the baseline | every density variant pays here (None → 8) |
| **C — UL video** (G5) | fleet 6, knee 1.0 | **X7: fleet 8, knee 1.3** | group B |
| **D — isolation** (G6, G7) | G6 217/216; G7 containment +9.0 ms | **X7: G6 222/221, containment +0.8 ms** | none, once controls are used |
| **E — capacity** (G10, G12) | adm. 10, clause 4 10/0/0 | X7 holds both | G12 telemetry M02 worsens on every density variant |
| **F — transitions** (G9) | 12/12 | X7 holds 12/12 | none |

**The Proto side:** `ProtoRRageD2` remains the divergence candidate; its tuned
increment **D1 was rejected** (won G10 7 → 8, regressed five groups). With G7's
new controls, `ProtoRRageD2`'s camera containment measures **−1.1 ms** — the
aggressor is indistinguishable from no aggressor at all — which is the strongest
containment figure of any arm.

**The open structural item** is that group B and group C compete for the
per-slot DCI cap on this cell, and no encoding has created capacity. The live
question is whether configured grants remove group B from the contest entirely.

## 5. Group E, diagnosed before any code (2026-09-16)

**The artefact cannot answer "which flow missed", so a probe was built and
gated.** `g10.json` records `M08_fraction` but no flow identity. The probe
re-scores a run with the scorecard's own M07/M08 over the runner's own
population (`Population.protected_fleet()`, `g5_consolidation.py:76`) and
is **gated on reproducing the artefact's value before anything is read** —
0 mismatches in 10 of 10 seeds on both arms. Two earlier attempts are
recorded as not quotable: one used a `FlowRecord` field that does not
exist and one omitted `record_timeseries=True`, and that one returned
0.000 for every flow on both arms — an empty selection wearing a
measurement.

**What it found.** At N = 8, every protected GBR flow is a **4 Mbps
camera** — one contract, eight instances — so there is no "largest flow"
to blame. Proto's failure is **unequal treatment of identical contracts**:

| | worst flow (median over 10 seeds) | worst seed | spread across the identical contracts, median / max |
|---|---|---|---|
| PF | 0.988 | 0.982 | 0.023 / 0.030 |
| ProtoRRageD2 | **0.917** | **0.782** | **0.096 / 0.230** |

On the worst seed two cameras sit at 0.782 and 0.939 while four others are
at 0.986–0.995. **Grant sizing is refuted as the cause** — the contracts
are identical, so size cannot separate them. Pure slots-since-last-grant
equalises *visits*, and bytes per visit then diverge; nothing in the arm's
uplink key carries the GBR deficit, because `denial_ordered_periodic`
REPLACES Tier 2 with `-age` rather than refining it
(`two_tier_proto.py::_ul_rank_key`).

**So group E's increment is a GBR-deficit tie-break inside the age order,
not a rate-aware term** — confirmed by construction rather than
correlation: G10 runs at `snr_spread_db = 0.0`, so the cameras are
identical in channel as well as contract, and the spread cannot be a
channel effect.

## 6. Group D: M1 is refuted, and stays refuted

`TwoTierProto` already carries an MFBR mechanism (`mfbr_enforced`, arm
`ProtoM1`) and it is **not** group D's lever. `_m1_view` caps
`bytes_reported` — the gNB's BSR *estimate* — and the UE fills the granted
block from its real queue, so shrinking the estimate shrinks the block
asked for without capping delivery (`docs/g7-slide-source.md` §5;
`docs/HANDOVER-2026-09-12.md` lists it under "edits tried and REFUTED —
do not retry without new evidence", together with the process note that
its first measurement was of an unwired no-op). Enforcement has to act on
`tbs_bytes` after sizing, or on eligibility.

That is exactly the shape of ConfigSched2's increment 10 (a contracted
flow over its planned bytes for the window drops to best-effort rank), so
group D is carried by that increment on the ConfigSched side, and on the
Proto side there is no new evidence to justify retrying M1.



## 7. Degradation must be ordered by importance (standing requirement, 2026-09-16)

**When the cell cannot satisfy everything, the scheduler must fail in a
chosen order, not an arbitrary one: critical flows stay satisfied as far as
capacity allows, and non-critical flows degrade gracefully rather than
cliff-edge.** This is a requirement on every arm and every increment from here
on, and it is the standing lens for reading any result past the admissible
boundary.

**Why it is a separate requirement and not implied by the guarantees.** Each
guarantee is scored PASS/FAIL at its own bound, so a scheduler that holds
every bound until capacity runs out and then loses *the safety flow first*
scores identically, at the boundary, to one that sheds the video first. The
guarantees say what must hold *inside* the boundary; they say almost nothing
about the ORDER things break in outside it. G12 (GT-7.3) is the only procedure
that looks at break order directly, which makes it load-bearing rather than a
tail-end check.

**What this implies for the checklist, per increment:**

1. **Past the boundary, report WHICH class degraded first**, not only that the
   fleet failed. M07 / M08 at N beyond the admissible point already carry this
   if read per class instead of as a scalar.
2. **A tuning change that improves an aggregate by sacrificing a critical
   class is a REGRESSION**, even when the headline number improves. The
   protected population (`Population.protected_fleet()`) is the set that must
   not be traded.
3. **Graceful means monotone and proportional**: a non-critical flow should
   lose throughput progressively as load rises, not collapse to zero at one
   step. A cliff in a best-effort class is a finding, not an acceptable
   outcome.
4. **Safety / STOP traffic (5QI 85) is never the shed candidate**, at any load,
   on any arm.

**Where it bites first.** G6 and G7 are the isolation procedures — they ask
whether a bad actor's harm is contained — and G10/G12 are where the ordering
past capacity is visible. The config scheduler's formulation is the natural
place to make this explicit rather than emergent: an active-set decomposition
already ranks by contract, so the shed order is a property that can be
*designed* instead of observed.

---

## DL SPS — the downlink analogue of CG, NOT IMPLEMENTED (registered 2026-09-16)

**Status: not built, not measured, no code. This is a registered candidate,
not a result.** **It belongs to group A (Downlink deadline)** as a candidate mechanism,
alongside the staged camera CG in group C. Recorded here so it is not rediscovered as a new idea, and so
the next person knows what is already settled about it.

### What it is, from the Rel-16 text (read, not recalled)

Semi-Persistent Scheduling is the downlink's configured grant: a periodic
**downlink assignment** the UE keeps without a PDCCH per occasion.

* **TS 38.321 V16.22.0 §5.8.1** — SPS is configured by RRC per Serving Cell
  per BWP; *"Multiple assignments can be active simultaneously in the same
  BWP"*; a DL assignment is provided by PDCCH and stored or cleared on L1
  signalling (activation / deactivation); activation is independent per
  Serving Cell. RRC supplies `cs-RNTI`, `nrofHARQ-Processes`,
  `harq-ProcID-Offset`, `periodicity`, and the N-th assignment lands at
  `(numberOfSlotsPerFrame x SFN + slot) = (... start time ...) + N x periodicity
  x numberOfSlotsPerFrame / 10` modulo `1024 x numberOfSlotsPerFrame`.
* **TS 38.331 V16.22.0 `SPS-Config`** — `periodicity` ENUMERATED
  {ms10, ms20, ms32, ms40, ms64, ms80, ms128, ms160, ms320, ms640};
  `nrofHARQ-Processes` INTEGER (1..8); Rel-16 extensions `sps-ConfigIndex-r16`,
  `harq-ProcID-Offset-r16` (0..15), `periodicityExt-r16` (1..5120 **slots**),
  `pdsch-AggregationFactor-r16`. `BWP-DownlinkDedicated` carries
  `sps-ConfigToAddModList-r16` / `-ToReleaseList-r16` /
  `sps-ConfigDeactivationStateList-r16`.
* **The bound that differs from CG:** `maxNrofSPS-Config-r16 = 8` SPS
  configurations per BWP, against `maxNrofConfiguredGrantConfig-r16 = 12` for
  CG. A staged-configuration design on the downlink therefore has **8**
  phases to play with, not 12.

So **SPS is fully inside the Rel-16 compliance baseline** — the constraint the
deployment imposes is satisfied, and `docs/rel16-baseline-2026-09-15.md`
§2.1/§2.2 already carries the clause rows (survey row B2, *"Rel-16, keep as a
candidate"*).

### Why it is worth exploring: CG moved uplink and left downlink untouched

The 2026-09-16 campaign measured configured grants on every arm. **CG closed
the entire uplink heartbeat class on every arm, and nothing in the downlink
moved** — G1 and G2 are where they were without it. That is not a surprise
(CG is an uplink mechanism), but it does mean the downlink has had **no
equivalent intervention at all**, on any arm. SPS is the one Rel-16 lever that
is structurally the same shape.

### What it would and would NOT fix — stated before building, so it can be wrong

* **It attacks the DCI / per-slot-cap axis, not the retry axis.** SPS removes
  the PDCCH for the *initial* transmission only; **TS 38.300 §10.2 is explicit
  that retransmissions are scheduled on PDCCH**. So the honest expectation is
  that SPS relieves the M-6 per-slot UE cap (4 at 106 PRB) and the DCI budget.
* **It is therefore NOT an obvious fix for G2.** G2 fails on every arm on the
  **retry budget** (the BLER^2 floor inside a 5 ms PDB), and SPS adds no
  retries. Anyone picking this up should not expect G2 to move, and should
  register that expectation before measuring rather than after.
* **G1 passes today**, so SPS there is a *margin* measurement, not a fix.
* The real candidate is the one the survey already names: a standing DL lane
  for a periodic downlink flow, freeing DCI for the download and for retries.

### Where it would be built — `sim/`, not `scheduler/`

**CLAUDE.md's invariant "Do not add SPS / Configured Grant to the schedulers"
governs `scheduler/` files and is NOT a ban on this work.** Configured grants
were built as a **MAC feature in `sim/`** (`sim/configured_grant.py`) that runs
*ahead of* every scheduler and reaches them only as pre-scheduler occupancy
(`sim/pre_sched.py::Occupancy`) plus a reduced buffer view. SPS follows that
same pattern exactly:

* a `sim/` module owning the SPS configurations and their phases;
* occasions added to the ONE `Occupancy` map, so the DL path cannot diverge
  from the CG path;
* every arm — faithful ports included — runs it through one driver flag, and
  any arm with it on is **labelled in its name and in every table**, exactly as
  `+CG` is;
* `scheduler/two_tier.py` and `scheduler/reservation.py` stay the port, with
  no SPS mechanism re-added (the deleted `_SPSReservation` / `_allocate_sps`
  must not come back).

### Open questions to settle before building

1. **Does the HARQ mask compose?** `HarqAwareBufferView` fully masks a flow
   with a pending process; a standing DL assignment interacts with that the
   way a restricted CG TB did (`HarqProcess.cg_qfi`, build 2c). The DL analogue
   is unbuilt and is the first thing to get right.
2. **Does an SPS occasion suppress anything the way CG suppressed SR?** The
   unrestricted-CG result (it broke G5 on every arm by suppressing SR for every
   channel) is the cautionary precedent. The downlink has no SR, so the naive
   answer is no — which is exactly the kind of naive answer this project has
   been wrong about before, and it should be measured, not assumed.
3. **8 configurations per BWP** is the budget for any staged design.
