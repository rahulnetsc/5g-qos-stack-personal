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

### 0.4a And this document has made the OPPOSITE error too — do not merge the two

§0.4 above corrects an **overstatement**: a result was presented as
better-supported than it was. Stage 6 Part A found the reverse in §2 and §3
— an **understatement of coverage**. H2's and H3's rows read "not tested"
and "not tested as an axis", but the `duty_cycle` and `snr_spread_db`
excursion cells **were run in stage 1 and have been on disk since**, 30
paired rows per level, and both hypotheses are now confirmed from them with
**zero new runs** (`docs/wp9-plan.md` §22.2-§22.3).

**The two errors have opposite failure modes in a reader, which is why they
must not be written up as one "the coverage claims were imprecise".** §0.4's
makes someone **trust a result more than they should**. This one makes
someone **commission work that is already on disk**. A reader needs to know
which mistake they are at risk of making.

**And confirming G6's row is part of the same correction.** G6's
"computable from stage-1 rows but was not computed" was **exactly
accurate**; saying so is what makes the H2/H3 correction legible as
specific, rather than as a general loss of confidence in this section.

**The qualifier that now travels with H2/H3, permanently:** each row states
**one cell, paired, n=30 per level**, never a bare "tested". Same reason as
§0.1's two-number rule and G11's inline seed count — a depth qualifier that
lives only in a methods section is a qualifier that will be dropped.

---

## 0.6 FOR THE CAMPAIGN — two things to settle about G6's own wording before it is run

Both were found by measuring against G6 as written
(`IA_P5G_Factory_Guarantee_Test_Plan.md:100`), and both are the kind of
thing that otherwise surfaces mid-campaign.

### 0.6.1 The +20 % relative bar is UNDEFINED when the denominator can be zero

G6 says every G1/G3/G5 statistic *"shifts by ≤ ▷ +20 % relative"*. **A
relative bound has no meaning for a statistic whose baseline is legitimately
zero, and one of G6's own bound statistics is exactly that.** Measured, on
the protected fleet at n_seeds=40:

- **PF's M02 (PDB-violation rate) is exactly 0.0 in BOTH conditions on every
  seed** — the relative shift is `0/0`, not a pass and not a fail;
- **TwoTier's M02 relative mean reads +4271 %** off a near-zero base, while
  its **median is −0.21 %** and its **absolute** delta is **+0.0010** with a
  CI containing zero. The relative form reports a catastrophe where the
  absolute form reports nothing.

**Recommendation for ratification: state G6's bar for rate-type statistics
in ABSOLUTE terms** (e.g. "the PDB-violation rate rises by ≤ X percentage
points"), keeping the relative form only for statistics with a
strictly-positive baseline such as latency percentiles and gap maxima.
**The bar is `▷`-provisional (line 91), so this is input to ratifying it —
not a defect anyone has patched unilaterally.**

### 0.6.2 G6 is a CONJUNCTION and only its second clause had ever been tested

G6 requires each statistic to **stay within its bound AND** shift by
≤ +20 %. Every G6 result before `docs/wp9-plan.md` §28 tested the shift
clause only, on **three** of the **ten** statistics G6 binds (the ten are
derivable from `config/metric_panel.yml`'s own `guarantees:` fields:
M01–M06, M15–M17, M19).

With the first clause now evaluated: **4 of the 10 are NOT EVALUABLE at all**
(M04 and M19 are `pending`, M16 is a study-layer call needing a named flow
pair, M15/M17 report dicts with no stated scalar bound), and **only 5 have a
numeric bound stated anywhere in the test plan.** M02 has none.

**Consequence for the campaign: G6 cannot currently be scored as written.**
Six of its ten statistics either lack a bound or lack a value. Ratification
should either name bounds for them or narrow G6's wording to the statistics
it can actually bind.

### 0.6.3 "Stays within its bound" has no rule for a statistic that breaches MORE OFTEN

G6's first conjunct is a state, not a rate: *"stays within its bound"*.
Measured, TwoTier's M06 (frame age p95 ≤ 67 ms) breaches on **7 of 40
seeds without the aggressor and 12 of 40 with it** — it did not start
breaching, it breaches more often.

**G6's text cannot classify that.** It is not "aggressor-created" (the
statistic already breached), and it is not "unaffected" (the rate rose by
71 %). **Ratification needs to say whether the first conjunct is about the
bound being crossed at all, or about the frequency with which it is
crossed** — and if the latter, by how much.

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

#### CORRECTION — this result does NOT contradict H2, and the reason is mechanistic

**This document previously said, in §3's H2 row, that stage 5's transient
"contradicts H2's direction".** It does not. Corrected by measurement
(`docs/wp9-plan.md` §22.4, `scripts/f2_duty_cycle_trace.py`) — the same
class of correction as §12.2's flow-count claim and §13.2's rejected
horizon, where a committed claim was withdrawn because someone ran the
thing rather than reasoned about it further.

TwoTier's uplink ranking composite is `(base_q + urg) × hyp_tbs_bytes`.
`base_q` comes from `vq_ul`, a virtual queue that **integrates while a flow
is starved**; `urg` is a delay barrier that needs **live backlog** to grow.
Only `base_q` can accumulate across an idle period — and the two regimes
load opposite terms:

| regime | `base_q` median | `base_q` share of the composite |
|---|---|---|
| no idle periods (`duty_cycle` 1.0) | 0.000 | 0.385 |
| **recurring idle periods** (`duty_cycle` 0.1) | **4,678** | **0.851** |
| stage-5 `ugv_heavy` N=16, control | 8.017 | 0.423 |
| **stage-5 lidar activated** | **0.000** | **0.337** |

**A duty cycle FEEDS `base_q`; a permanent step STARVES it and `urg` takes
over.** Duty-cycled traffic gives the virtual queue idle periods to
integrate across, and TwoTier's ranking becomes `base_q`-dominated — which
is precisely the mechanism H2 was registered on
(`sim/parametric.py::_burstify`: *"accumulates credit across idle
periods"*). A lidar activation is a one-off step to a permanently higher
load: there is no idle period, `base_q`'s median falls to zero, and the
delay barrier becomes the majority term.

**So the two results measure different mechanisms and coexist without
tension.** H2 is confirmed in its registered direction (§3), and stage 5's
"the QoS-aware arms lose the most" stands exactly as written above. What
was wrong was only the inference joining them.

**The general lesson, and it is why this sits in the map's own text rather
than in a findings section:** "a transient is just extreme burstiness" is
the intuition that produced the retracted sentence, and it is wrong for
this scheduler. **Burstiness and step-load are different axes here**, and
any future claim that transfers a result from one to the other has to name
which term of the composite it thinks is carrying it.

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

> **Interval provenance for the G6, H2 and H3 rows below (and §3's).**
> Their bootstrap bounds came from `analyse_stage6.py` /
> `g6_seed_extension.py` before `e95d6ee`, which seeded the resample with
> `hash(...)` — salted per process. **Every verdict, point estimate and
> median is unaffected**, and re-running under the fixed seed flips no
> verdict; **the CI bounds themselves will not reproduce exactly**, moving
> by ≈0.01–0.05 in the metric's own units. Quote the verdicts freely; treat
> a quoted *bound* from these three rows as ±0.05 rather than exact.

## 2. G1–G12 bridge table, filled in

| G | Status | Evidence / what is missing |
|---|---|---|
| **G1** | **Sim-informative** | M01 p98 / M15 across the core plane. Ordering only; the millisecond is not certifiable (`SIM→RF`). |
| **G2** | **Not answered by WP9 — and the reason is now STRUCTURAL, not scenario coverage** | Needs an event-triggered STOP flow and trial accumulation; no WP9 cell models it. GT-1.2 remains **RF**. **Sharpened by `docs/wp9-plan.md` §19.5:** G2's *real* failure class is the BSR/SR desync, and it is unreachable here for a reason that is about the model's structure rather than its scenarios. Truncated BSR is now built, wired to 38.321's Padding BSR trigger, and unit-tested — **and still cannot fire**. **CORRECTED by `docs/wp9-plan.md` §20 — this row previously named TB-size quantisation as the blocker, and that is wrong.** Measured counterfactually (`scripts/tbs_counterfactual.py`): quantising the TB changes the padding distribution by **nothing** at the load the claim was measured at (13,214/13,214 grants at padding 0 before and after), and *reduces* lawful Truncated BSRs at light load (5 → 4). **The blocker is the magnitude of the gNB's BSR error at grant time** — on that same run, 99.70 % of grants DO have ≥2 LCGs backlogged (the scenario was built so they would), and the gNB's estimate is off by a median **12,194 bytes** on them; on `factory_robots` it is **13,387**. Against a window **2–5 bytes** wide, a 5–64 byte TBS lattice step is nowhere near the operative scale. The shape any future attempt must defeat is an **anti-correlation**: loading a UE until three LCGs are backlogged makes its grants PRB-limited, and a PRB-limited grant is filled exactly (padding 0 at any TB size); unloading it until the grant has spare room drains all but one LCG, and 38.321 says report a *Short* BSR then, never a truncated one. So the sim measures STOP latency under ordinary contention only — the easy case — and closing the real one is a BSR-accuracy item, not a TB-sizing one and not another scenario. |
| **G3** | **Sim-informative, conditional** | M03/M14 scored at `t_live_s` ∈ {1, 2, 4} — reported as a function of it, since `T_live` is `[OPEN: HARDWARE]` and unmeasured. |
| **G4** | **ANSWERED at one cell — resume is prompt; the number is entangled with message size** | `scripts/g4_postsilence.py`, a study-layer read of the live WP7 message ledger (`docs/wp9-plan.md` §23). Post-silence p98 on T1 telemetry (the liveness instrument) at `duty_cycle` 0.1 is **77.23 / 64.87 / 74.79 ms** (PF / Reservation / TwoTier) against a steady state of 21.62 / 20.58 / 33.82. **SCOPE NOTE, and a reader must not quote the number without it: the size confound is NOT incidental to this guarantee.** Under `sim/parametric.py::_burstify` the post-silence message **is larger by construction** — mean offered rate is held constant by stretching the period and growing the burst by the same 1/duty — so a 10× longer silence carries a 10× larger message. Measured against that baseline the latency grew **sub-proportionally on every arm** (×3.57 / ×3.15 / ×2.21 against ×10), leaving **no residual for an SR/BSR cold-start penalty to explain**. So resumption is prompt on this workload — but **on this workload the guarantee's own question is entangled with message size in a way a real deployment need not be**: a real robot that goes quiet for a second then sends one 300-byte telemetry frame has a long silence and a *normal-sized* message. `_burstify`'s constant-mean-rate design is correct for H2, whose axis must not smuggle in a load change, and is the wrong shape for G4, which wants silence varied at **constant message size**. A reader taking "post-silence p98 = 77 ms" without this is reading a number about size as a number about silence. |
| **G5** | **FAILS at the base cell on BOTH QoS-aware arms — no aggressor involved** | M05/M06/M17 present on every run via the `xr_video` instrument. **Evaluated against G5's own bar for the first time by `docs/wp9-plan.md` §29** (the bar is *"≥ 99 % of PDU sets complete within PDB"*, test plan line 99), at n_ues=8, offered load ×1.0, n_seeds=40, protected fleet: **PF passes** (worst seed 0.9868, 4/40 marginally under). **Reservation fails on 33/40 seeds and TwoTier on 35/40, with a MEDIAN worst-flow completeness of 0.0000 on both** — i.e. on more than half of all seeds a video flow completes **none** of its PDU sets within the 150 ms PDB. **Not a thin-sample artefact:** those flows carry frame_count 147–148 against sibling video flows at 152, so ~148 frames were produced and none completed in time. **Concentrated, not diffuse:** the 33 Reservation breaches come from **2 distinct flows** (`ue8_qfi2` ×24, `ue7_qfi2` ×9) and TwoTier's 35 from 4, one accounting for 30 — a breach count is over SEEDS, not over flows. **This is §0.1's concentrate-vs-spread split arriving on a GUARANTEE BAR rather than a comparative metric:** PF spreads and every video flow clears 98.7 %; the QoS-aware arms concentrate and one video flow per run gets nothing. **It surfaced inside the G6 work and is filed here, not there** — no aggressor is involved and the failure is present at the base point. **Qualifier:** ONE CELL (n_ues=8, load ×1.0); whether it persists across N and load is unrun. |
| **G6** | **PASSES on the protected fleet — every arm, both statistics** | Computed from stage-1 records, extended to **n_seeds=40** paired with a pre-registered one-look rule, then re-evaluated on the **protected fleet** (`docs/wp9-plan.md` §22.1a/§27/§28). **Background traffic does not impair the fleet.** M02 (PDB-violation rate) protected-fleet delta: PF **−0.0019** [−0.0075, +0.0041], Reservation **−0.0022** [−0.0075, +0.0036], TwoTier **+0.0010** [−0.0109, +0.0133] — **every interval contains zero**. M03 (worst liveness gap) passes on PF and Reservation and is INCONCLUSIVE on TwoTier (median −0.44 %). **An earlier reading of this row reported a TwoTier FAILURE at +136.84 % and a ~24-point M02 rise on all arms; both were the AGGRESSOR MEASURED AS THE FLEET**, by two different mechanisms — M03 takes a max over *every* flow and M02 byte-weights over *every* flow, so a 50 Mbps best-effort flood being correctly starved scored as fleet damage. Since a QoS-aware scheduler starves such a flood **by design**, the better an arm contained it the worse it scored: the causal direction was inverted. Fixed by binding G6 to **M20** (`protected_fleet_liveness_gap`) rather than by editing M03, whose all-flow domain is deliberate. **Two qualifiers travel with this row:** it is **ONE CELL** (n_ues=8, offered load ×1.0 — depth not bought), and G6's **first conjunct** ("stays within its bound") is now also evaluated (`docs/wp9-plan.md` §29): **no statistic goes from zero breaches at base to non-zero under the aggressor**, so G6 passes that clause too. The bound breaches that exist are **pre-existing** and belong to G1/G3/**G5** — see G5's row, which fails at the base cell independently of G6. One statistic (M06 on TwoTier, 7→12 seeds) widens under the aggressor without crossing from zero, and **G6's wording supplies no rule for how much widening counts** — §0.6.3. |
| **G7** | **NOT ANSWERABLE IN SIM** | No MFBR enforcement exists anywhere in `sim/` (`sim/config_loader.py:16`). Containment is observable; **clipping is not**, and clipping is half of G7's pass criterion. GT-4.3 is the only test. |
| **G8** | **Sim-answerable** | M09 per-second Jain across 186 scored cells. **PF-arm contaminated** by `pf.py`'s declaration-order tie-break (README §8) — Reservation-vs-TwoTier is the trustworthy pair. |
| **G10** | **Sim-answerable — the headline** | **Admissible N is bounded by 8 at load ≥ 1.0 and by 16 below it**, on this RAN at `min_rb=5`. This is what simulation buys that the N=2 testbed cannot. §0.1 and §0.3 apply. |
| **G11** | **NOT RUN** | The soak sub-campaign was budgeted (§6.3, 3 seeds, ~6.5 h) and **never launched or implemented**. No WP9 evidence. |
| **G12** | **NOT ANSWERABLE from any workload this WP ran — a stronger and more useful statement than "not analysed"** | This row previously said M13 "was computed for stage 1's core plane only and not analysed", which invites a reader to go and extract it. **Extraction cannot answer G12.** Measured across all 1,770 stage-1 and all 1,440 stage-4 records (`docs/wp9-plan.md` §22.5): the GBR 5QI classes present are **`[2]` — exactly one**. `first_violation_order` orders 5QI classes against each other, so with one class every group's "order" is a one-element list, which is not an ordering. **And the fix is not to widen M13**: the delay-critical classes here (5QI 1/82/83/85) are `flow_class="Delay"`, which the metric does not read, and widening a pre-registered metric until it separates something is exactly what `config/metric_panel.yml`'s multiplicity guard forbids. **G12 needs a workload with ≥ 2 GBR classes** — scenario work, not analysis. |
| **G9** | **NOT RUN** | The 50-cycle join campaign was budgeted (§6.3, ~72 min) and **never launched or implemented**. M18/M19 mechanism exists (WP-Join); WP9 produced no cycle data. |

**Honest summary of coverage, revised by stage 6 Part A: WP9 answers G10
well, G1/G3/G5/G8 partially, **G6 at one cell** (no arm fails, only PF
cleanly passes), G4 uncomputed, **G12 and G7 structurally unanswerable**,
and G9/G11 not run at all.** The gap between "the metric exists" and "WP9
produced the number" is larger than the plan implied, and is stated here
rather than papered over — **but it is not uniformly larger.** Part A
computed G6, H2 and H3 from records already on disk with zero new runs
(§0.4a), so part of what read as a coverage gap was an accounting gap. The
two that moved the other way are G12, which no amount of extraction can
answer (one GBR class exists), and M19/M18, which have read `pending` on
**every row of every stage** — 1,770 + 7,560 + 1,440 — because no WP9
scenario configures `UEConfig.join`, so no join event can occur. **Nothing
except G9's campaign can move them**, which is the first measured argument
for building it rather than an assumed one.

---

## 3. H1–H7 scored

| H | Verdict | Basis |
|---|---|---|
| **H1** (reservation collapses above a UE count) | **Confirmed, bound identified** | Boundary at N=8 / N=16, matching the PDCCH bound. §0.3 limits it to `min_rb=5`. |
| **H2** (two-tier wins as traffic becomes bursty) | **CONFIRMED at one cell, and the "contradiction" was a DIFFERENT MECHANISM** | **Two corrections here, and they are separate.** (1) *"Not tested as an axis" was an UNDERSTATEMENT of coverage*: the `duty_cycle` excursion rows were run in stage 1 and are on disk — 30 rows per level (3 arms × 10 seeds), paired within seed against the base cell. Computed (`docs/wp9-plan.md` §22.3, zero new runs), at `duty_cycle=0.1` **PF loses nearly twice as many GBR contracts as TwoTier (M07 −7.0 vs −4.0) and is the only arm whose worst-flow GFBR fraction falls, while TwoTier's rises (+0.384, interval excluding zero)**. H2 holds in its registered direction, on both metrics. (2) *Stage 5's transient does NOT contradict it.* A direct-cause trace (`scripts/f2_duty_cycle_trace.py`, §22.4) shows the two regimes are driven by **different terms of the same formula, in opposite directions**: duty-cycling makes TwoTier's UL composite `base_q`-dominated (the virtual queue integrating across idle periods — median 0 → 4,678, share 0.385 → **0.851**), while a lidar activation makes it `urg`-dominated (median `base_q` 8.0 → **0.000**, share 0.423 → 0.337), because a one-off step to a permanently higher load contains no idle period to integrate across. The two coexist without tension. **Depth beyond the base point: bought but not yet run** (§21.5). |
| **H3** (two-tier wins as channel spreads) | **CONFIRMED at one cell, in its registered direction** | *"Not tested" was an UNDERSTATEMENT of coverage* — the `snr_spread_db` excursion rows were run in stage 1 and are on disk, 30 rows per level, paired within seed. Computed (`docs/wp9-plan.md` §22.2, zero new runs): **TwoTier improves on BOTH panel metrics as the channel spreads** — M08.fraction +0.676 [+0.425, +0.886] at 6 dB and +0.698 [+0.453, +0.939] at 12 dB, M07.met +1.60 [+0.80, +2.30] at 12 dB — while PF and Reservation do not move. Note this is a case where §0.1's both-numbers rule does not bite: there is no metric split, TwoTier wins both. **One cell only** (N=8, load ×1.0); depth bought but not yet run. |
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
