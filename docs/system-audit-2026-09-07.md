# System and scenario audit — running document

**Started 2026-09-07. Appended as findings arrive, not written at the end.**
Build nothing. Findings are recorded where found and ranked at the end.

**THE FILTER.** This simulator models the **MAC scheduler**. PHY is abstracted
deliberately; RLC/PDCP/SDAP are absent by design. An absence is a **finding
only if a guarantee's clause depends on it to be answered correctly.**
`has_srb` passes that test — a dead top ranking tier changes every arm's
ordering. RLC segmentation does not. Each entry says which side it falls on.

**Reference:** the deployed source at
`/home/smart/projects/Oai_Ran_QoS_Supported_MultiDRB`, branches `twotier`
(two-tier MAC) and `rrc-qos-handling-v0.1.1` (reservation). `twotier` is
branched from reservation and changes only MAC, so the diff isolates
two-tier's additions.

**Two corrections that postdate earlier documents and are used throughout:**
- **G10 without-attach is PF 30/40, Reservation 23/40, TwoTier 26/40.** The
  published 31/32 were with-attach mislabelled.
- **G3 is 10/10 on every arm.**

---

## Log

### P1-1 — RA is absent, AND on hardware it has PRIORITY over the data plane (ADMITTED: G10 depends)

Known: no PRACH, no RAR, no Msg3, no contention resolution. **New here is the
scheduling order.** `gNB_scheduler.c:225-252`, in one slot, in this order:

```
schedule_nr_prach(...)          // PRACH occasions reserved
nr_csirs_scheduling(...)        // CSI-RS
nr_csi_meas_reporting(...)
nr_schedule_srs(...)            // SRS
nr_schedule_RA(...)             // <-- RA, writes vrb_map_UL
nr_schedule_ulsch(...)          // THEN uplink data
nr_schedule_ue_spec(...)        // THEN downlink data
```

`nr_schedule_RA` writes `vrb_map_UL` (`gNB_scheduler_RA.c:337-342`) — **the
same VRB map the UL data scheduler then allocates from.** So RA, PRACH, SRS
and CSI-RS all take PRB and CCE **before** data, unconditionally.

**The sim gives 100 % of the grid to data**, less a flat
`overhead_factor = 0.85` (`sim/config.py:36`) — a static 15 % haircut standing
in for every control-plane cost. No PRACH, SRS, CSI-RS or PUCCH resource
consumption is modelled (grep: zero hits in `sim/` for prach/csi-rs; the
"pucch" hits are the SR *timing* path, not a resource reservation).

**Filter — ADMITTED, on one guarantee.** For a fixed fleet the haircut is a
constant and shifts all three arms together, so it does not touch an
*ordering* claim. **But G10's clause IS capacity** ("the cell hosts a stated
fleet size"), and hardware's overhead is **load-dependent** — PUCCH scales
with UE count, RA bursts when UEs join, SRS is per-UE periodic — while the
sim's 15 % does not. **So G10's admissible-N boundary is optimistic, and
increasingly so at the large-N end, which is exactly the axis it sweeps.**

**Results affected:** G10 (PF 30/40, Res 23/40, TT 26/40 without attach) —
the boundary is an upper bound. **Not** G1/G3/G5/G8 ordering claims.

**Inert because of it:** nothing in the ranking. The sim has no code path
that reserves control resources, so there is no dormant mechanism here — this
is an absence, not a dead branch.

### P1-2 — DRX: absent here AND unused on hardware (NOT a finding)

`gNB_scheduler_dlsch.c:1349` passes `255, // no drx`. The deployment does not
use DRX either, so its absence is a **correct abstraction**. Recorded so it is
not re-raised.

### P1-3 — RESERVATION IS RUNNING THE BOTTOM HALF OF ITS OWN COMPARATOR (ADMITTED)

`has_srb` was known. **It is not alone.** The deployed reservation comparator
(`gNB_scheduler_dlsch.c:687-703`, `gNB_scheduler_ulsch.c:2005-2016`) is:

| | DL tiers | UL tiers |
|---|---|---|
| T1 | `has_srb` — SRB1/SRB2 RLC bytes | `has_srb` — LCG-0 carrying non-DRB |
| T2 | **`liveness` = `ta_apply && !has_srb`** | **`liveness`** |
| T3 | `has_gbr` | `has_gbr` |
| T4 | `pdb_ms` / coef | **`sched_inactive`** |
| T5 | — | `pdb_ms` / coef |

`scheduler/reservation.py:23,30` records that **`has_srb`, `liveness` and
`sched_inactive` are all inert** — the first hardcoded `False`, the other two
because "they need a TA model" that does not exist. **So DL ranking effectively
begins at T3 and UL at T3, with T4 also dead.** Every Reservation number this
project has produced comes from a comparator whose **top two tiers never
fire**.

**Magnitude, measured from the source rather than asserted.** TA is armed by
`if (frame == sched_ctrl->ta_frame) sched_ctrl->ta_apply = true;`
(`gNB_scheduler_dlsch.c:757-759`) — **once per 1024-frame wrap, i.e. once per
~10.24 s per UE.** A 40,000-slot run is 10 s, so `liveness` would fire roughly
**once per UE per run** — about 8 promotions across 40,000 slots at N=8.

**Filter — ADMITTED but LOW-MAGNITUDE, and the two halves differ:**
- **`liveness`/TA: admitted, small.** It is a genuine dead top-2 tier, but it
  would fire ~8 times per run. It cannot plausibly move a 10-seed success
  rate. **Also affects the DL overhead byte count** — the real
  `oh = 3*4 + (ta_apply ? 2 : 0)` is a flat `12` here (`reservation.py:88`).
- **`has_srb`: admitted, and its magnitude is unknowable until Part 4.** SRB
  traffic exists only at RRC events — attach, reconfiguration, measurement
  reporting — **none of which this simulator has**. So it is dead for a
  *consistent* reason: there is no SRB traffic to rank. Building RA+SRB
  (Part 4) makes it live, and it is the **top** tier in both directions.

**Results affected:** every Reservation row. **The direction is knowable:**
both dead tiers would *promote* UEs above GBR, so the sim's Reservation is a
**more purely QoS-ordered** scheduler than the deployed one.

**This is the `has_srb` shape found twice more.** The lesson generalises: a
ported comparator's dead tiers must be enumerated **as a set**, because
finding one says nothing about the others.

### P1-4 — FOUR RANKING TIERS ARE MEASURABLY DEAD, across 16.9 M adjacencies (ADMITTED)

Not read from docs — counted from the rank stream
(`sweeps/rerun-2026-09-06/traces.json`, every decisive-term tally summed):

| term | times decisive | share |
|---|---|---|
| `-coef` (TwoTier composite) | 8,835,770 | 52.22 % |
| `-metric` (PF's single scalar) | 6,021,444 | 35.59 % |
| `pdb_ms` | 1,218,603 | 7.20 % |
| `has_gbr` | 645,622 | 3.82 % |
| TIED (declaration order) | 198,585 | 1.17 % |
| **`floor_fire`** (Tier-1.5 UL floor) | **27** | **0.0002 %** |
| **`has_srb`** | **0** | **0 %** |
| **`sched_inactive`** | **0** | **0 %** |
| **`-floor_sil`** | **0** | **0 %** |

**Three tiers never decide anything, and the fourth decides 27 of 16.9
million.** Both QoS arms are effectively ranking on `coef → pdb_ms → has_gbr`.

**Filter — ADMITTED**, and it reframes the whole comparison: **the QoS arms as
evaluated are not the QoS arms as deployed**. Their top tiers are structurally
unreachable because the inputs (SRB traffic, TA, `do_sched`, `cp_floor`) do not
exist here. This is the `has_srb` shape, now enumerated as a **set** and
**measured**, and it is the single largest fidelity gap the audit found.

---

## PART 2 — per-guarantee scenario audit

### P2-1 — MOST CLAUSES HAVE 2-3 PARTS AND THE SCORECARD SCORES ONE (ADMITTED, largest Part 2 finding)

Read from the test plan, L95-L106. **Parts scored / parts stated:**

| guarantee | the clause's parts | scored |
|---|---|---|
| G1 | p98 ≤ 95 ms · *p99.9 reported* | 1 of 2 |
| G2 | 100 % of STOPs ≤ 100 ms · *miss-rate bound per §5.3* | 1 of 2 |
| **G3** | max gap ≤ 500 ms · **zero gaps ≥ T_live** · **p98 ≤ PDB** | **1 of 3** |
| G4 | p99 ≤ 300 ms at silence **1 s / 5 s / 60 s** | 0 of 3 |
| **G5** | ≥ 99 % sets complete · **frame age p95 ≤ 67 ms** · **goodput ≥ GFBR every 2 s** | **1 of 3** |
| G6 | within bound · **and shifts ≤ +20 %** | 0 of 2 |
| G7 | A unchanged within ε · B clipped at MFBR | 2 of 2 |
| **G8** | Jain ≥ 0.9 · **zero starvation epochs ≥ 1 s** | **1 of 2** |
| G9 | warm ≤ 1 s · attach ≤ 15 s · post-RLF ≤ 10 s · neighbours unaffected | 0 of 4 |
| G10 | largest N with **G1-G8** all-pass | GBR contract only |
| G11 | every window · CoV ≤ 15 % · consistent PASS/FAIL | 1 of 3 |
| G12 | first-violation order · never 5QI 1 | 1 of 2 |

**And the unscored halves are not decorative — one of them fails.**

#### G8's second half FAILS, and it is in the artefact already

*"zero starvation epochs ≥ 1 s"* (L102). `G8_M22_epochs_prot` and
`G8_M22_longest_s` are recorded and were never scored:

| arm | runs with ≥ 1 starvation epoch | longest epoch |
|---|---|---|
| PF | **0/10** | 0.0 s |
| **Reservation** | **7/10** | **10.0 s — the entire run** |
| **TwoTier** | **3/10** | 2.67-4.18 s |

**On the full clause G8 is PF 10/10, Reservation 3/10, TwoTier 7/10** — against
the Jain-only 10/10, 9/10, 7/10. **Reservation drops from 9/10 to 3/10**, and
a 10.0 s longest epoch on a 10 s run means a UE received **nothing for the
whole run**.

**Deployment consequence:** a robot that gets no uplink service for an entire
shift on 7 shifts in 10, while the fairness metric the row reports reads 9/10.

#### The other available halves pass, and are now checked rather than assumed

- **G3's third part** (zero gaps ≥ T_live): **0/10 breaches on every arm** —
  passes, now measured.
- **G5's second part** (frame age p95 ≤ 67 ms): **10/10 on every arm**
  (PF 25.1, Res 21.6, **TwoTier 45.1 ms** median). Passes, but TwoTier sits at
  **67 % of the bound** against PF's 37 % — the margin is much thinner and a
  stress axis would find it first.
- **G1's second part** is *"p99.9 reported"* — a **reporting** requirement, not
  a bound. The artefact carries p98 only, so **the guarantee's own reporting
  obligation is unmet**, though no verdict depends on it.

**Unavailable without a re-run:** G5's per-2 s-window goodput, G6's +20 %
relative shift (needs the unperturbed baseline), G9's three time bounds
(artefact stores per-arm medians), G11's CoV and PASS/FAIL consistency,
G12's ordering, G4's three silence lengths.

### P2-2 — G1 SCORES UPLINK TELEMETRY; ITS CLAUSE IS ABOUT A DOWNLINK COMMAND (ADMITTED)

The test plan's G1 is *"Every drive command reaches the robot in time"*, and
GT-1.1 specifies **"M1-DL cmd_vel 20 Hz on 5QI 1 DL"** — the drive command is
**downlink**.

The parametric mix:

| 5QI | dir | class | kind | PDB |
|---|---|---|---|---|
| **1** | **UL** | Delay | `periodic_control` | 100 ms |
| 2 | UL | GBR | `xr_video` | 150 ms |
| 9 | UL | PF | `poisson` | 300 ms |
| **82** | **DL** | Delay | `periodic_control` | 100 ms |

**The sim's 5QI 1 is UPLINK telemetry.** The downlink command is 5QI 82.

The row reads M01's **worst flow** over the protected fleet {1, 2, 82}, and
measured, **it lands on `qfi1` 26/30 times and `qfi2` 4/30 — never on
`qfi82`.** So the downlink drive command **has never set G1's number in any
run**, and its own p98 is not surfaced anywhere.

**Filter — ADMITTED.** The verdict is not wrong (the command flow is passing
comfortably, or it would win the worst-flow contest), but **the row answers
"is any protected flow late" rather than "is the drive command late"**, which
is the question the guarantee is named for. **Deployment consequence: we
cannot currently answer "how late does a drive command get" at all.**

Behaviourally 82 and 1 are near-identical here (both `Delay`, both 100 ms
PDB), so this is a **reporting/naming** mismatch rather than a physics one.

### P2-3 — THE SCENARIOS SPECIFIED FOR G2 AND G4 WERE NEVER BUILT (ADMITTED)

**G2, from GT-1.2:** *"both assets at full committed profile; cell **saturated
both directions** with 5QI-9 (**worst legal case**). Trigger: scripted
master-disconnect → **simultaneous** STOP datagrams to A and B."* And GT-7
adds a **mass-event**: *"both assets emit event bursts (5 × 300 B) within the
same 10 ms window on 5QI 1 UL, cell saturated; simultaneously the DL STOP
pair. **50 storms/run.** KPIs: **100 % of event packets and STOPs ≤
deadline**."*

**What was measured: one STOP flow, nominal load, no saturation, no
simultaneity, no storms.** That is why it reads 10/10 with ~25× margin
(2-4 ms against 100 ms). **The scenario built is not the scenario specified**,
and the specified one is the adversarial case — simultaneous STOPs are
precisely when a per-UE argmax scheduler "is most tempted to serialise badly",
in the plan's own words.

**G4, from GT-2.3:** silences of **{1 s, 10 s, 60 s}** (the KPI line says
1 s/5 s/60 s — **the plan disagrees with itself**, worth raising with its
owner). The built sweep varies `duty_cycle` ∈ {1.0, 0.5, 0.1}, **a different
axis**: duty cycle changes message size under `_burstify`'s constant-mean-rate
design, so silence and payload move together — the confound already recorded
for G4.

### P2-4 — provenance and inert mechanisms

**Banked evidence.** All ten scorecard artefacts are from **today**, after the
ledger-key fix; only `core.json` carries a ledger and its ledger was cleared
before the final run. **`g11_c1_soak.json` and `g12.json` predate the fix**,
but neither had a flag flipped against the same `--out`, so the defect's
precondition did not occur. **Low risk, stated rather than assumed.**

**MFBR is not universally zero** (an earlier concern): the parametric mix
carries **8 Mbps** on its GBR flows and `sensor_dense` carries **0.0** on all.
So two-tier's MFBR-dependent protections are **inert on `sensor_dense` only**,
not project-wide.

---

## PART 3 — does each sweep reach its stress region?

### P3-1 — G10 is the template, and pooling destroys it

Per fleet size, seeds **inside** the point, never pooled:

| arm | N=2 | N=4 | N=8 | N=16 | **boundary** |
|---|---|---|---|---|---|
| **without attach** | | | | | |
| PF | 10/10 | 10/10 | **10/10** | 0/10 | **8** |
| Reservation | 10/10 | 10/10 | **3/10** | 0/10 | **4** |
| TwoTier | 10/10 | 10/10 | **6/10** | 0/10 | **4** |
| **with attach** | | | | | |
| PF | 10/10 | 10/10 | 10/10 | 0/10 | **8** |
| Reservation | 10/10 | 10/10 | **10/10** | 1/10 | **8** |
| TwoTier | 10/10 | 10/10 | **10/10** | 2/10 | **8** |

**Pooled, this is 30/40 · 23/40 · 26/40 — "near-identical arms". Per point,
PF holds twice the fleet the QoS arms do**, and the entire deficit is the
cold-start lock-out: with an attach grant all three reach 8.

**The sweep is too coarse above 8** — every arm goes 10/10 → 0-2/10 between
N=8 and N=16, so the true boundary is unresolved in a 2× gap. **Cost to
resolve: N ∈ {10, 12} = 2 points × 30 runs × 5.2 s ≈ 5 CPU-min, ~1 min wall.**

### P3-2 — the axis per guarantee, and whether the current sweep reaches it

| guarantee | right axis | current sweep | reaches separation? | cost to reach |
|---|---|---|---|---|
| **G1** commands | offered load × fleet size | **one point** (N=8, ×1.0) | **partially** — TwoTier already 7/10 there, PF and Res 10/10 | 4 load points × 30 runs × 13.9 s ≈ **28 CPU-min, ~3 min wall** |
| **G2** STOP | **saturation + simultaneity + storm count** (GT-1.2/GT-7) | **one point, nominal, single STOP** | **no** — 10/10 with 25× margin | needs the specified scenario **built**, not just swept |
| **G3** liveness | offered load × fleet size | one point | **no** — 10/10 everywhere | shares G1's sweep, **free** alongside it |
| **G4** post-silence | **silence length {1, 10, 60 s}** at constant message size | `duty_cycle` {1.0, 0.5, 0.1} — **a different axis**, confounded with payload | **no** | a scenario change (decouple silence from size) |
| **G5** video | video bitrate, then fleet size | one point | **yes** — 10/3/6 already separates | extend for PF's boundary: ≈ **10 CPU-min** |
| **G6** background | background rate | one point | unknown — clause unscoreable | needs the baseline arm first |
| **G7 c2** MFBR | **aggressor multiple 1.0 → 3.0** | one point (2.1×) | **inverted** — 0/10 at 2.1×, so sweep **downward** to find where clipping starts. PF's ratios cluster 1.02-1.12, i.e. PF nearly passes | 5 points × 30 × 6.6 s ≈ **17 CPU-min** |
| **G8** fairness | fleet size × **channel spread** (`snr_spread_db`) | one point | **yes on the second half** (Res 3/10 on epochs) | ≈ **28 CPU-min** with G1's |
| **G9** join | **join rate** — UEs joining per second into a loaded cell | fixed schedule | **no** | scenario parameterisation |
| **G10** fleet | fleet size | 4 points | **yes**, but too coarse above 8 | **5 CPU-min** |
| **G11** shift | simulated duration | **already at it** — 7.2 M slots | n/a | **do not re-run** |
| **G12** overload | ramp **resolution near the knee** | ×1.0 → ×8.0, 8 points | **overshoots** — everything dies by the top; the knee is between ×1.0 and ×2.3 | finer points in ×1.0-×2.5 |

**Correcting the reading offered:** G12's problem is **not** a ramp top that is
too low — the ramp already runs past the point where every arm's telemetry
floors. It is **resolution near the knee**, where the arms actually separate
(TwoTier floors at ×1.6, the others at ×2.3).

### P3-3 — the four guarantees with no axis

- **G2 — the sharpest, and the plan already specifies it.** Axis: **number of
  simultaneous STOPs × background saturation**, i.e. GT-1.2's "worst legal
  case" plus GT-7's 50 storms/run. Today's result — *"the STOP lands within
  100 ms at 8 robots under nominal load"* — is a smoke test for the
  safety-critical path.
- **G4** — silence length at **constant message size**, decoupling the two.
- **G6** — background offered rate, with the **unperturbed baseline** run as
  the paired control the clause's "+20 % relative" requires.
- **G9** — **join rate into a loaded cell**. The lock-out is a joining
  phenomenon (measured: the attach path is inert when all UEs start at slot 0
  and decisive when they stagger), so joins-per-second is the axis that makes
  G9 discriminating.

---

## PART 4 — RA + SRB costed as one build (NOT started)

**Scope.** PRACH occasions and their resource reservation; preamble selection,
collision and backoff; the RAR window; Msg3 with HARQ; contention resolution;
SRB1/SRB2 traffic; LCG-0 mapping so `has_srb` has an input.

**What it changes across the system — not per guarantee:**

1. **It makes four dead ranking tiers live** (P1-3, P1-4). `has_srb` is the
   **top** tier in both directions on Reservation; today it is decisive **0
   times in 16.9 M adjacencies**. Every Reservation ordering result could
   move, and the direction is knowable (SRB traffic **promotes** a UE above
   GBR), but the magnitude is not.
2. **It puts a competing consumer ahead of the data plane.** RA is scheduled
   **before** `nr_schedule_ulsch` and `nr_schedule_ue_spec` and writes the same
   `vrb_map_UL`. Capacity available to data falls, and falls **more** as more
   UEs join — so **G10's admissible-N boundary would move down**, and G10 is
   the guarantee whose clause is capacity.
3. **It removes the cold-start lock-out's simulator-specific frequency.** The
   attach path currently supplies its effect through a flag; RA would supply it
   through the mechanism, and the `attach_seed_slots` divergence could retire.
4. **It makes G9 answerable.** Attach-to-streaming ≤ 15 s is a bound on a
   procedure that does not exist here.

**Cost estimate — and it is a lower bound.** Six mechanisms, each with its own
RNG stream, state machine and tests: PRACH occasion scheduling, preamble
collision/backoff, RAR window, Msg3+HARQ, contention resolution, SRB traffic
generation + LCG-0 mapping. On this project's own rate — WP-Join delivered a
comparable per-UE FSM plus a buffer view in one work package — **this is one
full work package, not a commit**, and it carries a **deliberate corpus
re-baseline** because it changes what every arm is ranking on.

**The honest risk:** it would make the QoS arms' *deployed* comparators live
for the first time, so **it may invalidate more published results than any
other single change available.** That is an argument for doing it, but with a
before/after column, not in place.

---

# FINDINGS, RANKED BY HOW MUCH THEY TOUCH

**Nothing was built. No finding made the rest of the audit unsound**, so it
ran to completion.

| # | finding | touches | invalidates |
|---|---|---|---|
| **1** | **Four ranking tiers are measurably dead** — `has_srb` 0, `sched_inactive` 0, `-floor_sil` 0, `floor_fire` 27 of 16.9 M. Both QoS arms rank on `coef → pdb_ms → has_gbr` only | **every result on both QoS arms** | Nothing numerically, but it **reframes every arm comparison**: the schedulers evaluated are not the schedulers deployed. Their top tiers are unreachable because SRB traffic and TA do not exist here |
| **2** | **G8's second half is unscored and FAILS.** "Zero starvation epochs ≥ 1 s" is in the artefact: PF 0/10 runs affected, **Reservation 7/10 with a 10.0 s epoch on a 10 s run**, TwoTier 3/10 | **G8's verdict** | **G8 becomes PF 10/10, Reservation 3/10, TwoTier 7/10** — Reservation falls from 9/10. The published G8 row is materially wrong |
| **3** | **Most clauses have 2-3 parts; the scorecard scores one.** G3 1 of 3, G5 1 of 3, G8 1 of 2, G9 0 of 4, G11 1 of 3, G4 0 of 3 | **the whole scorecard** | No single number, but **every "PASS" understates what was required**. Two available halves were checked today (G3's third: passes; G5's second: passes with TwoTier at 67 % of bound) |
| **4** | **G2's and G4's specified scenarios were never built.** G2's clause requires a **saturated cell, simultaneous STOPs, 50 storms/run**; what ran was one STOP at nominal load | **G2 entirely**, G4's axis | G2's 10/10 with 25× margin is **a smoke test result presented as a safety guarantee** |
| **5** | **Pooling destroys G10's real finding.** Per fleet size: **PF holds to 8 robots, both QoS arms to 4** without attach; with attach all three reach 8 | **G10's headline** | The pooled 30/23/26 of 40 reads "near-identical arms"; the truth is a **2× capacity difference** entirely caused by the cold-start lock-out |
| **6** | **RA is absent and on hardware it has priority over data** — scheduled before both data schedulers, writing the same VRB map. The sim gives data 100 % of the grid less a flat 0.85 | **G10's boundary** | G10's admissible-N is an **upper bound**, increasingly so at large N |
| **7** | **G1 scores uplink telemetry; its clause is about a downlink command.** The worst-flow statistic lands on `qfi1`/`qfi2` (UL) 30/30 times, never on the DL command flow `qfi82` | **G1's interpretation** | Verdict stands, but **"how late does a drive command get" is currently unanswerable** |
| **8** | **Nine of twelve rows sit in a comfortable zone.** Only G5, G8 and G10 separate the arms at their measured point | **all reported margins** | A margin at one operating point is not a boundary. Four rows have **no failure anywhere in the evidence base** |
| **9** | DRX absent here **and unused on hardware** (`255, // no drx`) | nothing | **Not a finding** — recorded so it is not re-raised |

## THE CORRECTED GUARANTEE TABLE

Every row: the question in plain terms, the result, and what an operator would
experience. **A row without its consequence is not reportable.**

| guarantee | the question | result (without attach) | **deployment consequence** |
|---|---|---|---|
| **G1** | does a drive command reach the robot in time? | PF 10/10 · Res 10/10 · **TT 7/10** | On a cold cell TwoTier misses on 3 shifts in 10 — by 2-4 ms over a 95 ms bound. **Teleop feels momentarily sticky, not broken.** But the number is measured on *uplink telemetry*; the command flow's own latency is unreported |
| **G2** | does a STOP always land? | 10/10 all arms, 25× margin | **Not yet evidence.** The clause requires a saturated cell and simultaneous STOPs; this is one STOP at nominal load. **The safety-critical path is untested at its specified condition** |
| **G3** | can the network make a healthy robot look dead? | **10/10 all arms** | No robot appears dead. Corrected today — the earlier TwoTier 8/10 was scoring a background flood's starvation |
| **G5** | do operators see fresh, complete video? | PF 10/10 · **Res 3/10** · **TT 6/10** | **Reservation delivers unusable video on 7 shifts in 10** — severity 1.000, i.e. nothing complete. **Vision-guided work stops.** An attach grant fixes it entirely (both arms 10/10) |
| **G7 c1** | is the victim protected? | 10/10 all arms | A misbehaving robot does not damage its neighbours' video |
| **G7 c2** | is the offender clipped? | PF 1/10 · Res 0/10 · **TT 0/10** | **No arm limits the aggressor**; both QoS arms pass **2.03× MFBR**. A deployment expecting a rate limiter does not have one — MFBR bounds entitlement, not throughput |
| **G8** | do equal robots get equal service? | **corrected: PF 10/10 · Res 3/10 · TT 7/10** | **Reservation leaves a robot with no uplink for an entire shift on 7 shifts in 10.** The Jain-only row (9/10) hid this completely |
| **G10** | how many robots fit? | **PF to 8 · Res to 4 · TT to 4** | **The QoS arms host half the fleet PF does** on a cold-starting cell. With an attach grant all three reach 8. **Fleet size is a commissioning question, not only a scheduler one** |
| **G11** | do the guarantees hold for a shift? | 10/10 all arms, 100× margin | Over 30 simulated minutes nothing degrades |
| **G12** | does overload degrade safely? | **PF 0/20** · Res 20/20 · TT 20/20 | **PF keeps serving 8.6 Mbps of background while telemetry dies.** Both QoS arms starve background first, correctly. **The clearest argument against PF for safety-critical telemetry** |
| G4, G6, G9 | — | **not scoreable** | No verdict; see Part 3 for the axis each needs |
