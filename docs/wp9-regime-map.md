# WP9 regime map — the bridge artefact for the hardware campaign

**Audience:** the team executing `IA_P5G_Factory_Guarantee_Test_Plan.md`.
This is the characterisation output that plan's §0 and §10 reference. It
says where the boundaries are, which guarantees are scheduler-limited
versus fault-model-limited, and where to spend the rule-of-three budget and
the real-RF window.

**Evidence base:** stage 1 (59 cells, 1,770 runs), stage 2 (252 cells,
7,560 runs, full factorial, contiguity-checked), stage 4 (48 cells, the
Category-2 fleet grid) and **stage 5 (48 cells, 1,440 runs, the
lidar-activation excursion)**, 10 paired seeds per cell, all 19 panel
metrics scored per run. `docs/wp9-plan.md` §8b–§8d, §15 and §17 carry the
detail; this document is the roll-up.

---

## 0. Four qualifiers that travel with every number below

**Read these before quoting anything from this document.** Each is a
qualifier a reader will be tempted to drop, and each changes what a number
means.

### 0.1 Any single-metric claim about who wins at high N is wrong by construction

At **N ≥ 24, load 1.0**:

| | M07 contracts met | M08 worst-flow GFBR fraction |
|---|---|---|
| PF | **0.0** (N=24), **0.0** (N=32) | **0.636**, **0.470** |
| Reservation | 10.4, 6.2 | 0.000, 0.000 |
| TwoTier | 6.7, 6.4 | 0.000, 0.000 |

**PF meets ZERO GBR contracts and still wins the max-min floor.** It spreads
capacity so every flow gets something and none reaches 95 % of GFBR; the
QoS-aware arms concentrate it so some flows meet contract and others get
nothing. This is H6 confirmed directly.

**Rule for this document and anything derived from it: quote both numbers
together, every time either is quoted.** A "PF wins at high N" claim built
on M08 alone, or a "PF collapses at high N" claim built on M07 alone, is
false in the same cell.

### 0.1.1 The winner flips between workloads AND within one grid — the lesson generalises, the ranking does not

| | leads on M07 contracts | PF's M07 | PF's M08 |
|---|---|---|---|
| **stage 2** (uniform fleet) | **Reservation** | 0.0 at N≥24 | 0.636 / 0.470 |
| **stage 4** (`ugv_heavy`, N=32) | **TwoTier** (4.9) | **0.0** | **0.453** |

Same structural result both times — one QoS-aware arm concentrates and
meets contracts while PF spreads, meets none, and wins the max-min floor —
**with the arms swapped.**

**So the LESSON generalises and the RANKING does not.** This is a sharper
statement than either result alone, and it is the strongest available
support for §0.1's rule: a reader who took "Reservation wins on contracts"
from stage 2 would have been **wrong on stage 4's workload while quoting a
real number**. Any single-metric claim about who wins at high N is false
by construction, now demonstrated across two workloads with **opposite
winners**.

**Stage 5 adds a third demonstration, and it is stronger than the first
two: the ranking inverts WITHIN ONE GRID, as a function of N.** Under a
lidar activation (`docs/wp9-plan.md` §17.6):

| cell | M07w winner (contracts) | M08w winner (floor) |
|---|---|---|
| `ugv_heavy` N=16 | **PF** | **TwoTier** |
| `drone_heavy` N=16 | **PF** | **TwoTier** |
| `ugv_heavy` N=32 | **TwoTier** | **PF** |
| `drone_heavy` N=32 | **Reservation** | **PF** |

At N=32 the familiar pattern holds — a QoS-aware arm concentrates and
meets contracts, PF spreads and wins the max-min floor. **At N=16 it runs
backwards.** M08w at `ugv_heavy` N=16, control → `lidar_ues=2`: PF
**0.949 → 0.155**, TwoTier **0.945 → 0.601** — PF's worst non-lidar GBR
flow keeps 15 % of its GFBR where TwoTier's keeps 60 %.

So the split itself (H6) survives every workload tried; **which arm sits
on which side of it is not stable even across two fleet sizes of the same
composition.** A single-metric claim is now demonstrably false in *both
directions inside one experiment*.

### 0.2 H5 is untestable as configured — which is not the same as unconfirmed

Stage 2 varied `shared_lcg` and found **no measurable effect on any arm**
(paired within-seed: 0/42 cells for PF, 0/42 Reservation, 1/42 TwoTier, that
one marginal). But `gbr_bytes_slot` — the sub-mechanism most likely to carry
H5 — requires shared-LCG **and** `mfbr_bps > 0` (README §7, cause D), and
stage 2 held `mfbr_multiple` at its 0 base.

So H5 is **neither confirmed nor refuted**. **What would test it:** cells
crossing `shared_lcg=True` with `mfbr_multiple > 0`. No cell in either stage
ran that combination.

### 0.3 The boundary is located at the deployed `min_rb` only

`min_rb` was held at its base 5 throughout stage 2. So §1.1's *sharper*
claim — that `min_rb` has no effect on the boundary below ≈ 7, because the
PDCCH bound (32/4 = 8) binds before the follower-budget bound (55/`min_rb`)
— is **untested**. Stage 1 swept `min_rb` ∈ {1, 5, 20} and it separated the
arms strongly (score 152.579), but the cap dropped it from stage 2.

### 0.4 The cap did the narrowing, not the score

**11 of 12 axes cleared** stage 1's pre-registered threshold of 1.0. The
threshold did not discriminate; the "at most one excursion axis" cap (later
recomputed to two) is what narrowed the grid. Stage 2 therefore confirms
that differences **reproduce** on a dense contiguous grid — it does **not**
establish that the promoted axes were the most important ones.

**Of the eight dropped axes, FOUR were never live candidates** — they are
Category 1 (§0.5), deployment conditions rather than environmental
variables: `min_rb` (152.579), `sr_period_slots` (152.579), `pdb_ms`
(2.927, 5QI-derived as of `ad6ba54`) and `mfbr_multiple` (1.778, a
provisioned QoS-profile field, now set as base config).

**Genuinely untested Category-2 axes: `snr_spread_db` (4.689),
`duty_cycle` (2.663), `bg` (2.648), `inf_scenario` (did not qualify).**

**What this correction does NOT change.** The cap still did the narrowing
rather than the score; **11 of 12 axes cleared the 1.0 threshold**; and a
stage-2 result on a cap-selected axis remains **weaker evidence than §6.4
assumed**. Reclassifying four axes **shrinks the coverage gap; it does not
repair the selection mechanism that produced it.** Read only as "the
qualifier was overstated" this would be the wrong lesson — the qualifier
was **mis-shaped**, and those are different corrections.

---

## 0.5 The three-category taxonomy (added by the re-scope)

The scoping error this corrects: three categories were treated as one axis
space.

- **Cat 1 — fixed by the deployment.** Core/gNB config, not chosen at run
  time. A **condition** of the map, not an axis in it.
- **Cat 2 — what the environment does.** Encountered, not chosen. What the
  map should be indexed by: it varies in the field, and an operator can
  observe it.
- **Cat 3 — scheduler internals.** Meaningful only as arms.

| stage-1 axis | cat | justification |
|---|---|---|
| `n_ues` | 2 | fleet size |
| `load_mult` | 2 | offered load |
| `duty_cycle` | 2 | burstiness (H2) |
| `snr_spread_db` | 2 | channel spread (H3) |
| `bg` | 2 | elephant / background traffic |
| `inf_scenario` | 2 | deployment RF environment |
| `shared_lcg` | 2* | a **consequence** of composition, not a knob — see H5 |
| `min_rb` | **1** | `nrmac->min_grant_prb` = 5, gNB config |
| `mfbr_multiple` | **1** | QoS-profile field, provisioned per bearer |
| `pdb_ms` | **1** | 5QI-derived (`ad6ba54`); not free to choose |
| `sr_period_slots` | **1** | RRC / gNB config |
| `k2_slots` | **1** | TDA table / numerology |

**Consequence:** a Category-1 parameter is a *deployment variant*, not an
axis in a regime map. Sweeping one answers a counterfactual about a
different deployment. That is why §2's `min_rb` crossover is recorded as
untested **by choice**, and why H4 and H7 are re-tagged below.

---

## 1. The regime map

Contiguity was read before any effect size (`docs/wp9-plan.md` §6.4 rule 5).
186 of 252 cells scored; 66 uninformative (zero loss on every arm). Isolated
winners 0–2 per metric (0–1.1 %), so the regions below are contiguous
regimes rather than chance.

### 1.1 Where the schedulers separate

| N | load 0.5–0.75 | load ≥ 1.0 |
|---|---|---|
| 2, 4 | no separation | no separation |
| 8 | no separation | **separation** |
| 16, 24, 32 | **separation** | **separation** |

**The boundary is N=8 at load ≥ 1.0, moving to N=16 at low load.** The load
dependence is mechanistic, not noise: `n_followers_need` counts
*simultaneously backlogged* UEs, so at low load the effective follower count
sits below nominal N and the boundary moves up. N=8 matches the predicted
PDCCH bound (`U-slot CCE / AL = 32/4`).

**Below N=8 the arms are indistinguishable on the guarantee-relevant
metrics** — which is consistent with, and now explains, the hardware
campaign's own N=2 null result (`README.md` §7). N=2 sits 4× below either
bound; that measurement could not have differentiated the schedulers
however carefully it was run.

### 1.1a Onset by composition (stage 4) — and an OPEN hypothesis

Separation onset is **not** a function of fleet size alone (tier 1.0):

| composition | flows/UE | onset N | flows at onset |
|---|---|---|---|
| `sensor_dense` | 2.0 | none ≤32 | — |
| `mixed` | 3.2 | 32 | 96 |
| `drone_heavy` | 3.8 | 32 | 111 |
| `ugv_heavy` | 4.0 | **16** | **63** |

Two arms of a "denser fleets separate earlier" reading both fail to
survive: onset is not a function of N (else `sensor_dense` and `ugv_heavy`
would agree), **and it is not a function of flow count either** —
`ugv_heavy` separates at 63 flows where `drone_heavy` needs 111.

**OPEN HYPOTHESIS, not a finding.** The UGV profile carries three
tight-PDB flows — odometry (10 ms), drive control (10 ms), e-stop
(**5 ms**) — **co-located on LCG 3**, where the drone's are looser and
spread. Onset may be driven by **tight-PDB density and LCG co-location**
rather than candidate count.

It is logged as open because it was **not pre-registered**, comes from
**one grid**, and the two compositions differ in **several ways at once**
(flow count, GBR fraction, UL share, tight-PDB density, LCG occupancy) —
so it fits the data without being isolated by it. **What would test it: a
composition set holding flow count and GBR fraction FIXED while varying
tight-PDB density and LCG co-location independently.** Naming that
experiment is what separates an open hypothesis from a story that fits.

### 1.1b The TRANSIENT boundary (stage 5) — composition stops predicting it

Stage 4's onset above is a **steady-state** boundary. Stage 5 ran the one
regime where a large GBR demand arrives suddenly: a duty-cycled 12 Mbps
lidar on 1–2 UGVs, concurrency capped at 2 as a factory-workflow bound.

| composition | steady-state onset (§1.1a) | **transient breaking N** |
|---|---|---|
| `sensor_dense` | none ≤32 | none ≤32 |
| `mixed` | 32 | **16** |
| `drone_heavy` | 32 | **16** |
| `ugv_heavy` | 16 | **16** |

**The headline is not that the boundary moves down — it is that it goes
FLAT.** Under steady contention onset was composition-dependent
(16/32/32); under a transient all three break at **N=16**. Composition
predicts the steady-state boundary and does **not** predict the transient
one.

Effect sizes at N=16 are large, not marginal (M07w contracts met, paired
per-seed delta vs control): `ugv_heavy` PF −1.9 / Reservation −5.3 /
TwoTier **−9.9**; `drone_heavy` −2.2 / −4.6 / **−9.4**. **The QoS-aware
arms lose the most**, consistently.

**Three qualifiers travel with this table, all load-bearing:**

1. **It is a COMPOUND treatment.** Control C4 fired its *different*
   branch: the pre-window differs between lidar-on and lidar-off cells
   (M02w +0.00057, CI excluding zero), so each contrast measures
   *provisioning + activation*, not activation alone. The correct phrasing
   is **"adding a provisioned-and-activated lidar bearer breaks flows at
   N=16"**. The activation term dominates the compound by 70–240×, and
   separating the two needs the named follow-up: a third level with the
   bearer provisioned but never activated.
2. **The breaking-N numbers are POST-HOC.** The pre-registered criterion
   had no confidence interval and fired on one seed losing one contract
   (`docs/wp9-plan.md` §17.5); these come from re-scoring with the paired
   bootstrap CI E1 was registered with. The registered criterion's own
   output (4/8/8) is recorded there and is what pre-registration entitles
   anyone to.
3. **Run-aggregate metrics from a lidar-on cell are excluded, not
   caveated.** At 5 s a 2 s activation is 40 % of the run; every number
   here is windowed to the activation interval or comes from a control.

### 1.2 Who wins where — with §0.1 applied

- **N ≤ 4**: nobody. Zero loss on all arms at low load; at N=4 loads 1.5–3.0
  the cells are informative and separation is still absent (max effect size
  0.30–0.36 against a 1.0 bar).
- **N = 8–16**: PF leads on both M07 and M08.
- **N ≥ 24**: **split by metric.** Reservation and TwoTier meet real GBR
  contracts (6–10) where PF meets none; PF holds the max-min floor where
  they are at zero. Neither statement alone is the result — the pair is.

---

## 2. G1–G12 bridge table, filled in

| G | Status | Evidence / what is missing |
|---|---|---|
| **G1** | **Sim-informative** | M01 p98 / M15 across the core plane. Ordering only; the millisecond is not certifiable (`SIM→RF`). |
| **G2** | **Not answered by WP9 — and the reason is now STRUCTURAL, not scenario coverage** | Needs an event-triggered STOP flow and trial accumulation; no WP9 cell models it. GT-1.2 remains **RF**. **Sharpened by `docs/wp9-plan.md` §19.5:** G2's *real* failure class is the BSR/SR desync, and it is unreachable here for a reason that is about the model's structure rather than its scenarios. Truncated BSR is now built, wired to 38.321's Padding BSR trigger, and unit-tested — **and still cannot fire**, because this model sizes transport blocks continuously against demand, so padding is either exactly 0 (28,580/28,580 grants, saturated) or large (42–235 bytes), never the 2–5 bytes truncation needs. **38.321's truncated formats exist to handle a TB-size quantisation artifact this simulator does not model.** So the sim measures STOP latency under ordinary contention only — the easy case — and the case the guarantee is actually about needs TB-size quantisation (`sim/resource.py`, `scheduler/link.py`), not another scenario. |
| **G3** | **Sim-informative, conditional** | M03/M14 scored at `t_live_s` ∈ {1, 2, 4} — reported as a function of it, since `T_live` is `[OPEN: HARDWARE]` and unmeasured. |
| **G4** | **Not answered by WP9** | The duty-cycle axis was dropped by the cap (score 2.663). Post-silence first-packet latency needs a study-layer read that stage 2 did not produce. |
| **G5** | **Sim-informative** | M05/M06/M17 present on every run via the `xr_video` instrument. Not analysed per-regime in this pass. |
| **G6** | **Not answered by WP9** | `bg` (the saturating aggressor) qualified at 2.648 and was dropped by the cap. The ≤ +20 % delta statistic is computable from stage-1 rows but was not computed. |
| **G7** | **NOT ANSWERABLE IN SIM** | No MFBR enforcement exists anywhere in `sim/` (`sim/config_loader.py:16`). Containment is observable; **clipping is not**, and clipping is half of G7's pass criterion. GT-4.3 is the only test. |
| **G8** | **Sim-answerable** | M09 per-second Jain across 186 scored cells. **PF-arm contaminated** by `pf.py`'s declaration-order tie-break (README §8) — Reservation-vs-TwoTier is the trustworthy pair. |
| **G10** | **Sim-answerable — the headline** | **Admissible N is bounded by 8 at load ≥ 1.0 and by 16 below it**, on this RAN at `min_rb=5`. This is what simulation buys that the N=2 testbed cannot. §0.1 and §0.3 apply. |
| **G11** | **NOT RUN** | The soak sub-campaign was budgeted (§6.3, 3 seeds, ~6.5 h) and **never launched or implemented**. No WP9 evidence. |
| **G12** | **Not answered by WP9** | M13 (`first_violation_order`) was computed for stage 1's core plane only and not analysed. The load ramp exists in both stages; the ordering was not extracted. |
| **G9** | **NOT RUN** | The 50-cycle join campaign was budgeted (§6.3, ~72 min) and **never launched or implemented**. M18/M19 mechanism exists (WP-Join); WP9 produced no cycle data. |

**Honest summary of coverage: WP9 answers G10 well, G1/G3/G5/G8 partially,
and leaves G2/G4/G6/G12 uncomputed, G7 structurally unanswerable, and
G9/G11 not run at all.** The gap between "the metric exists" and "WP9
produced the number" is larger than the plan implied, and is stated here
rather than papered over.

---

## 3. H1–H7 scored

| H | Verdict | Basis |
|---|---|---|
| **H1** (reservation collapses above a UE count) | **Confirmed, bound identified** | Boundary at N=8 / N=16, matching the PDCCH bound. §0.3 limits it to `min_rb=5`. |
| **H2** (two-tier wins as traffic becomes bursty) | **Not tested as an axis — but a transient now contradicts its direction** | `duty_cycle` qualified (2.663) and was dropped by the cap, so H2 proper is still unrun. Stage 5's lidar activation is the burstiest workload in this project, and TwoTier **lost the most** there (M07w −9.9 vs PF −1.9 at `ugv_heavy` N=16, §1.1b). That is one transient shape, not the `duty_cycle` sweep H2 asks for, so it does not refute H2 — but H2 should no longer be written as though its direction were the expected one. |
| **H3** (two-tier wins as channel spreads) | **Not tested** | `snr_spread_db` qualified (4.689) and was dropped by the cap. |
| **H4** (Tier-1 mismatched to factory deadlines) | **Re-tagged — not an environmental question** | Driven by `pdb_ms`, which is **Cat 1** (5QI-derived, `ad6ba54`). Testable only as a **deployment variant**, not as an axis in this map. It did qualify (2.927) and was dropped by the cap, but that framing implied a gap the map could close; it cannot. |
| **H5** (two-tier degrades as flows-per-LCG grows) | **Now TESTABLE BY COMPOSITION** | Shared-LCG arises from the UGV profile's own `FIVE_QI_LCG` assignment — odometry (83), drive control (82), e-stop (85) all on **LCG 3** — rather than a synthetic override. **A stronger test than stage 1's**: co-location follows from a realistic device's QoS classes, not a flag set to make the mechanism fire. Still conditional on `FIVE_QI_LCG`, which remains invented (`[OPEN: HARDWARE/DECISION]`); §0.2's `mfbr_bps > 0` half is now supplied by base config. |
| **H6** (overload outcome is metric-dependent) | **CONFIRMED ON THREE STRUCTURALLY DIFFERENT WORKLOADS, INCLUDING A TRANSIENT** | §0.1. Stage 2 (uniform 3-flow fleet, synthetic filler), stage 4 (heterogeneous device profiles, no filler) and **stage 5 (a transient lidar activation)** all show it — so the construction is **not** a steady-state property, which was stage 5's registered falsifier and it did not fire. Predicted in advance only the third time (E3, `docs/wp9-plan.md` §17.6), and deliberately **without** naming an arm. **The winner flips between workloads AND between two fleet sizes of the same composition — see §0.1.1 — which is what makes the lesson, not the ranking, the result.** |
| **H7** (liveness decided by the UL access path) | **Re-tagged — not a regime-map hypothesis** | Driven by `sr_period_slots`, a **Cat-1** parameter, so it is a fixed property of the deployment. To be re-scoped or retired, **not** left as an untested hypothesis implying a gap this map could close. |

Five of seven hypotheses are untested because the cap admitted two
excursion axes out of eleven qualifying ones. That is §0.4's consequence
stated at the hypothesis level.

---

## 4. A methodological finding that belongs in the next sweep's design

**An unpaired comparison produced a confident answer opposite to the paired
one.** Testing H5, an unpaired look at cell means showed Reservation losing
2.4 GBR contracts at N=32 / load 1.0 under `shared_lcg=True` — which reads
as "Reservation degrades most", the *opposite* of H5's direction, and would
have been reported as a refutation of the hypothesis's direction.

Computed **paired within-seed**, that effect disappears entirely: it was
cross-seed variance in unpaired means, not a shared-LCG effect at all. The
paired result is 0/42 cells for Reservation.

**This is the strongest evidence in this project for why paired seeds were
non-negotiable** (`docs/p5g-sim-plan.md` §5.3, `regime_sweep.paired_seeds`).
The unpaired number was not noisy-looking — it was a clean, large,
plausible, wrong answer. Anyone designing the next sweep should treat
within-seed pairing as a correctness requirement, not a variance-reduction
technique.

---

## 5. Where to spend the hardware budget

1. **GT-5.2 (admissible N) is the test WP9 most sharpens.** Expect the knee
   between N=4 and N=8 at full load, and later at partial load. Testing
   N=2 again would reproduce a null this map now explains.
2. **GT-2.2 / GT-2.3 remain the only test of the UL floor, and WP9 can now
   say precisely why.** The floor needs `mfbr_bps > 0` to ARM and a BSR/SR
   desync to FIRE. **The arming half is now satisfied and measured at
   scale: `gate_passes ≈ 65,200, fires = 0`** — armed, never fired, with no
   desync present (`docs/wp9-plan.md` §19.5). The firing half is
   unreachable *structurally*: truncated BSR is built and correctly wired
   and still cannot fire, because continuous grant sizing means padding
   never lands in the 2–5 byte window the mechanism needs. WP9 therefore
   offers **no prediction** for the floor-OFF delta GT-2.2 measures, and
   hardware remains the only instrument. Stage 3's `fires=9` is superseded
   and unreproduced — do not carry it forward.
3. **GT-4.3 (MFBR clamp) is unmodelled**, per §0.2/G7 — hardware only.
4. **GT-7.3 (degradation ordering) is where H6 bites.** Expect the
   first-violation order to depend on which metric the pass criterion
   reads; specify that metric before running.
5. **A transient bound now sits alongside GT-5.2's steady-state one.** If
   the campaign will ever enable a high-rate sensor on a moving robot
   while the fleet is live, **N=16 is the fleet size to test it at**, for
   every composition — §1.1b's boundary is flat, so a single N covers all
   three rather than needing one per composition. Test it at N=16 rather
   than at the steady-state onset, which is 32 for two of the three and
   would miss the effect entirely.
6. **The cheapest experiment WP9 leaves undone is the third lidar level:
   bearer provisioned, never activated.** It needs no new mechanism (a
   `LidarActivation` whose `start_s` exceeds the horizon) and it is what
   converts §1.1b's compound "provisioned-and-activated" claim into a
   clean one. Until it runs, every transient number in this document is a
   compound treatment.
