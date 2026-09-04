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


> **A NOTE ON COUNTS IN THIS DOCUMENT.** Any "N metrics", "N cells", "N
> records" written in prose below is **as-of-writing**. This project has five
> recorded instances of a restated count going stale, and the panel's own size
> has been wrong three times (19 → 21 → 22). **Derive every count from the
> thing that produces it** — `len(load_panel()["metrics"])`,
> `len(regression_corpus._cases())`, `sum(len(v) for v in EXCURSIONS.values())`
> — and treat a number in prose as a claim about code at a past date.


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

> **`min_rb`'s exclusion is CONFIRMED as a cap decision, 2026-09-04 — and it
> was missing from the record that documents it.** `wp9_gate.select_for_stage_2`
> built its `dropped` list from a slice of the *unsorted* excursion list
> indexed by the *count* of promoted axes, so it discarded the first element
> whether or not that was the promoted one. **Both committed verdicts list 8
> dropped axes where the accounting requires 9, and the missing axis in both
> is `min_rb`** — under a docstring reading "Nothing is silently omitted."
>
> Regenerated from the committed `stage1_rows.csv` with the fix
> (`scripts/regen_gate_verdict.py`): **every score and the promoted set
> reproduce exactly**, so the decision was never in doubt — only its record.
> `min_rb` qualified at **152.579** and was dropped *"not promoted: only one
> excursion axis fits the stage-2 budget"*, which is what this section says.
> **The claim stands; the evidence for it now exists.**
>
> **One thing the regeneration exposed that this section should carry.** The
> gate ranks by `|mean delta| / sd`, so it is maximised by **saturation**
> rather than by effect size: `min_rb=1` and `sr_period_slots=1` score an
> identical 152.579 because both pin Reservation's worst-flow GFBR fraction
> at exactly **0.0000 on all 10 seeds** (PF sits at 0.9618 in every cell of
> every axis). The `inf` scores above them are sd exactly zero on `M07.met`.
> So *"it separated the arms strongly"* is literally what the score measures
> and is accurate — but it is **not** a statement that the axis has a large
> effect on the boundary, which §0.3 already records as untested. This is the
> mechanism behind §0.4's observation that 11 of 12 axes cleared the bar.

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

**AMENDMENT (Part C) — the qualifier survives, but its FORCE is reduced.**
The worry this section encodes is that the promoted axes might not have
been the important ones, so a result found on them might be an artefact of
*which* axes the cap happened to keep. **Part C ran depth on two axes the
cap DROPPED — `duty_cycle` and `snr_spread_db` — and §0.1's
concentrate-vs-spread split reproduces on both, at every fleet size above
4** (`docs/wp9-plan.md` §30.1). At n_ues=32, `snr_spread_db` 12:
Reservation meets **15.0** GBR contracts and PF meets **0.0**, while PF
holds a **0.289** max-min floor and both QoS-aware arms sit at exactly
**0.000**.

**So the headline structural result is NOT an artefact of the promotion
mechanism** — it holds on promoted and dropped axes alike. What remains
true, and is why the qualifier is not withdrawn: the cap still did the
narrowing rather than the score, 11 of 12 axes still cleared the threshold,
and **nothing here shows the promoted axes were the *best* choice** — only
that the split does not depend on having chosen them. **Read this as: the
selection mechanism is still unrepaired, but the principal finding no
longer rests on it.**

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
  its **median is −0.21 %** and its **absolute** delta is **−0.0270**
  [−0.0724, +0.0191], a CI containing zero. The relative form reports a
  catastrophe where the absolute form reports nothing.

> **This passage carried the §28.1 mislabel until 2026-09-03.** It read
> `+0.0010` under the words *"Measured, on the protected fleet"* — but
> +0.0010 is the **aggressor-excluded** row (`no qfi 8`), one population
> short of `Scorecard.NON_PROTECTED_5QI = {8, 9}`. The protected-fleet value
> is **−0.0270**. The correction was applied to §28.1 and to the G6 rows in
> `1cc4dbc` and this site was missed, which is why the fix pass that found it
> searched for **old values still LABELLED protected-fleet**, not just for
> the presence of the new ones — the latter check passes while the former
> fails, and the latter is the one that had been run.

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


> ## ⚠ KNOWN-WRONG, NOT SUSPECT — G1 AND G8 (2026-09-03)
>
> **Every worst-flow number for G1 and G8 in this document was computed over
> a population nobody chose.** `Scorecard`'s worst-flow metrics ranged over
> EVERY flow in the record, so the per-UE best-effort filler (5QI 9) and the
> saturating aggressor (5QI 8) — flows a QoS-aware scheduler is SUPPOSED to
> starve — entered contests the guarantees bind to the protected fleet.
>
> **Measured on `sweeps/wp9/stage2/stage2_rows.csv`, 7,560 rows:** the 5QI-9
> filler wins M01's contest in **85.4 %** of runs; the 5QI-1 telemetry bearer
> G1 is actually about wins it in **6** (0.08 %).
>
> **On a fresh N=8 run the VERDICT inverts, in opposite directions:**
>
> | | all-flow (as published here) | protected fleet |
> |---|---|---|
> | **G1** M01 p98 vs 100 ms | 300.00 / 300.25 / 300.00 → **FAIL every arm**, three arms agreeing to 0.25 ms because the value is pinned at 5QI 9's own 300 ms PDB | 28.00 / 22.00 / 96.75 → **PASS every arm**, 4.4× separation |
> | **G8** M09 Jain vs 0.90 | 0.9446 / 0.9419 / 0.8783 → **TwoTier FAILS** | 0.9995 / 0.9998 / 0.9584 → **TwoTier PASSES** |
>
> **G3, G5, G6 and G10 are NOT affected** — G6 already restricted via M20,
> G10's M07/M08 select `flow_class == "GBR"` which excludes both
> non-protected 5QIs by construction, and G3's and G5's winners were already
> protected bearers. That asymmetry is what makes this a defect rather than a
> framing preference, and it is pinned by
> `sim/tests/test_population_is_explicit.py`.
>
> **Fixed in the code (`9c23327`): the scoring layer now REFUSES to compute a
> worst-flow statistic without an explicit population.** The replacement
> VALUES do not exist yet — they arrive with the Phase 2 re-run. **These rows
> are marked before their replacements exist deliberately: a wrong number
> sitting unmarked is worse than a gap.**

## 2. G1–G12 bridge table, filled in

| G | Status | Evidence / what is missing |
|---|---|---|
| **G1** | **Sim-informative — and it now carries a MEASURED telemetry PDB failure that ARRIVED FROM G12's CAMPAIGN** | M01 p98 / M15 across the core plane. Ordering only; the millisecond is not certifiable (`SIM→RF`). **The failure, filed here rather than under G12** (`docs/wp9-plan.md` §36.2): on G12's ramp workload the 5QI 1 telemetry flow reaches **M02 = 1.000** — every resolved byte PDB-violated — **while background 5QI 9 still carries 11.6 Mbps**. PF and Reservation from 102 % of the measured ceiling; **TwoTier from NOMINAL LOAD on 9 of 10 seeds**. It surfaced as G12's clause 4 and belongs here, the same way G5's failure surfaced inside the G6 work. **Two qualifications travel with it, both stated on G12's row:** the arm difference is **untested under flow-list permutation**, and G12's clean ramp-bottom control **does not cover telemetry** — it reads M13's GBR classes and 5QI 1 is `Delay`. |
| **G2** | **Not answered by WP9 — and the reason is now STRUCTURAL, not scenario coverage** | Needs an event-triggered STOP flow and trial accumulation; no WP9 cell models it. GT-1.2 remains **RF**. **Sharpened by `docs/wp9-plan.md` §19.5:** G2's *real* failure class is the BSR/SR desync, and it is unreachable here for a reason that is about the model's structure rather than its scenarios. Truncated BSR is now built, wired to 38.321's Padding BSR trigger, and unit-tested — **and still cannot fire**. **CORRECTED by `docs/wp9-plan.md` §20 — this row previously named TB-size quantisation as the blocker, and that is wrong.** Measured counterfactually (`scripts/tbs_counterfactual.py`): quantising the TB changes the padding distribution by **nothing** at the load the claim was measured at (13,214/13,214 grants at padding 0 before and after), and *reduces* lawful Truncated BSRs at light load (5 → 4). **The blocker is the magnitude of the gNB's BSR error at grant time** — on that same run, 99.70 % of grants DO have ≥2 LCGs backlogged (the scenario was built so they would), and the gNB's estimate is off by a median **12,194 bytes** on them; on `factory_robots` it is **13,387**. Against a window **2–5 bytes** wide, a 5–64 byte TBS lattice step is nowhere near the operative scale. The shape any future attempt must defeat is an **anti-correlation**: loading a UE until three LCGs are backlogged makes its grants PRB-limited, and a PRB-limited grant is filled exactly (padding 0 at any TB size); unloading it until the grant has spare room drains all but one LCG, and 38.321 says report a *Short* BSR then, never a truncated one. So the sim measures STOP latency under ordinary contention only — the easy case — and closing the real one is a BSR-accuracy item, not a TB-sizing one and not another scenario. |
| **G3** | **Sim-informative, conditional — and G12's campaign supplies a telemetry-liveness failure it should be read against** | M03/M14 scored at `t_live_s` ∈ {1, 2, 4} — reported as a function of it, since `T_live` is `[OPEN: HARDWARE]` and unmeasured. **Arrived from G12's campaign** (`docs/wp9-plan.md` §36.2): on that ramp the telemetry flow stops completing messages entirely, so its liveness gap becomes **unmeasurable on 116 ramp points** — a flow with no completions has no gap between completions. **That is the M19-shaped blindness on M03's own currency**: the gap statistic goes silent exactly where the failure is total, and M02 is the instrument with range. Any G3 reading on a starved flow must be taken with its M02, never alone. See G1's row for the failure itself. |
| **G4** | **ANSWERED at one cell — resume is prompt; the number is entangled with message size** | `scripts/g4_postsilence.py`, a study-layer read of the live WP7 message ledger (`docs/wp9-plan.md` §23). Post-silence p98 on T1 telemetry (the liveness instrument) at `duty_cycle` 0.1 is **77.23 / 64.87 / 74.79 ms** (PF / Reservation / TwoTier) against a steady state of 21.62 / 20.58 / 33.82. **SCOPE NOTE, and a reader must not quote the number without it: the size confound is NOT incidental to this guarantee.** Under `sim/parametric.py::_burstify` the post-silence message **is larger by construction** — mean offered rate is held constant by stretching the period and growing the burst by the same 1/duty — so a 10× longer silence carries a 10× larger message. Measured against that baseline the latency grew **sub-proportionally on every arm** (×3.57 / ×3.15 / ×2.21 against ×10), leaving **no residual for an SR/BSR cold-start penalty to explain**. So resumption is prompt on this workload — but **on this workload the guarantee's own question is entangled with message size in a way a real deployment need not be**: a real robot that goes quiet for a second then sends one 300-byte telemetry frame has a long silence and a *normal-sized* message. `_burstify`'s constant-mean-rate design is correct for H2, whose axis must not smuggle in a load change, and is the wrong shape for G4, which wants silence varied at **constant message size**. A reader taking "post-silence p98 = 77 ms" without this is reading a number about size as a number about silence. |
| **G5** | **MEASURED FAILURE — both QoS-aware arms, and it reproduces across workloads** | **The measurement.** Evaluated against G5's own bar (*"≥ 99 % of PDU sets complete within PDB"*, test plan line 99) for the first time by `docs/wp9-plan.md` §29, at n_ues=8, offered load ×1.0, n_seeds=40 paired, protected fleet: **on more than half of all seeds both QoS-aware arms have a video flow completing NONE of its PDU sets within the 150 ms PDB** — Reservation **33/40** seeds under the bar, TwoTier **35/40**, both with a **median worst-flow completeness of 0.0000**. **PF: 4/40 marginally under, and NO zero cells at all** (worst seed 0.9868). **It is a real zero, not a thin sample** — checked before quoting: the zero flows carry **frame_count 147–148** against sibling video flows at **152**, so ~148 frames were produced and none completed in time. **And it is concentrated, not diffuse:** Reservation's 33 breaches come from **2 distinct flows**, TwoTier's 35 from 4 with one accounting for 30 — a breach count is over SEEDS, not over flows. **The mechanism is §0.1's concentrate-vs-spread split, arriving on a GUARANTEE BAR rather than a comparative metric.** Not a separate discovery — the same phenomenon §0.1 documents, and the generality is the point: PF spreads capacity so every video flow clears 98.7 %, the QoS-aware arms concentrate so one video flow per run gets nothing. §0.1 has always said neither arm is simply better; **on G5's own pass criterion, PF passes and both QoS-aware arms fail.** **SCOPE, checked rather than assumed.** The signature reproduces on stage 4's fleet compositions, and the ONSET is workload-dependent: at `video_tier` 1.0 all compositions are clean to n_ues=16 (0–4/10 seeds under, **zero** zero-cells), while **at n_ues=32 all three arms breach 10/10 — but zero-completeness flows appear ONLY on Reservation and TwoTier** (10/10 on `drone_heavy` and `ugv_heavy`; PF has none anywhere). So the concentrate-vs-spread signature generalises; the fleet size at which it bites does not — n_ues=8 on the parametric `factory` mix, n_ues=32 on the lighter fleet compositions. **What it is NOT: a G6 finding.** It is present at the BASE cell with **no aggressor**, and surfaced inside the G6 work only because Step 3 evaluated a conjunct nobody had evaluated before. Filed here. |
| **G6** | **PASSES on the protected fleet on the MISS RATE (M02) — every arm. On the LIVENESS GAP (M20): PF and Reservation PASS, TwoTier INCONCLUSIVE** | Computed from stage-1 records, extended to **n_seeds=40** paired with a pre-registered one-look rule, then re-evaluated on the **protected fleet** (`docs/wp9-plan.md` §22.1a/§27/§28). **Background traffic does not impair the fleet.** M02 (PDB-violation rate) protected-fleet delta: PF **+0.0000**, Reservation **−0.0104** [−0.0284, +0.0049], TwoTier **−0.0270** [−0.0724, +0.0191] — **every interval contains zero**. *(This row previously quoted −0.0019 / −0.0022 / +0.0010, which is the **aggressor-excluded** row; the protected fleet drops the best-effort filler too, per `Scorecard.NON_PROTECTED_5QI = {8, 9}` — `docs/wp9-plan.md` §28.1's correction box.)* **M20 (worst protected-fleet liveness gap) passes on PF (+0.44 %) and Reservation (+1.84 %) and is INCONCLUSIVE on TwoTier: mean +29.35 % [+4.81, +56.18], median −0.44 %, 17/40 seeds worse.** The interval **EXCLUDES zero** — a real telemetry-side residual survives the restriction — and **straddles the +20 % bar**, so whether it breaches is unresolved (§27.2). **"Every interval contains zero" is an M02 statement only**, and this row's headline previously said "both statistics"; note also that `INCONCLUSIVE` means the interval contains **the bar**, not zero. **An earlier reading of this row reported a TwoTier FAILURE at +136.84 % and a ~24-point M02 rise on all arms; both were the AGGRESSOR MEASURED AS THE FLEET**, by two different mechanisms — M03 takes a max over *every* flow and M02 byte-weights over *every* flow, so a 50 Mbps best-effort flood being correctly starved scored as fleet damage. Since a QoS-aware scheduler starves such a flood **by design**, the better an arm contained it the worse it scored: the causal direction was inverted. Fixed by binding G6 to **M20** (`protected_fleet_liveness_gap`) rather than by editing M03, whose all-flow domain is deliberate. **Two qualifiers travel with this row:** it is **ONE CELL** (n_ues=8, offered load ×1.0 — depth not bought), and G6's **first conjunct** ("stays within its bound") is now also evaluated (`docs/wp9-plan.md` §29): **no statistic goes from zero breaches at base to non-zero under the aggressor**, so G6 passes that clause too. The bound breaches that exist are **pre-existing** and belong to G1/G3/**G5** — see G5's row, which fails at the base cell independently of G6. One statistic (M06 on TwoTier, 7→12 seeds) widens under the aggressor without crossing from zero, and **G6's wording supplies no rule for how much widening counts** — §0.6.3. |
| **G7** | **NOT ANSWERABLE IN SIM** | No MFBR enforcement exists anywhere in `sim/` (`sim/config_loader.py:16`). Containment is observable; **clipping is not**, and clipping is half of G7's pass criterion. GT-4.3 is the only test. |
| **G8** | **Sim-answerable** | M09 per-second Jain across 186 scored cells. **PF-arm contaminated** by `pf.py`'s declaration-order tie-break (README §8) — Reservation-vs-TwoTier is the trustworthy pair. |
| **G10** | **Sim-answerable — the headline, and it is PER ARM** | **Admissible fleet size: PF 8 robots, Reservation 4, TwoTier 4** — the pre-registered per-seed all-pass read, computed by `scripts/g10_admissible.py` (§8d D4-3a). Four robots run clean on every arm; at eight, PF passes 10/10 seeds while Reservation passes 3/10 and TwoTier 1/10. This is what simulation buys that the N=2 testbed cannot. **The 8/16 pair previously written here is D4-3's arm-SEPARATION boundary — a different quantity, and not per-arm.** §0.1 and §0.3 apply. |
| **G11** | **NOT RUN — and not runnable as specified** | The soak sub-campaign was budgeted (§6.3, 3 seeds, ~6.5 h) and **never launched or implemented**; the budget was taken on time while the binding constraint was memory (§2.1's row, `docs/wp9-plan.md` §37). **THE FLEET SIZE IT WILL RUN AT, AND A SPECIFICATION FINDING ABOUT THE ONE GT-7.1 SPECIFIES.** The soak is planned at **N=4**, and the reason is **discovery versus re-measurement, not fairness**: C1's conjunction passes **10/10 on every arm at N=4** and is **0/10 on TwoTier / 3/10 on Reservation at N=8** (computed from `stage2_rows.csv`, `docs/wp9-g11-plan.md` §7.4), so N=4 is the only fleet size where a 30-minute soak can **discover** a failure rather than re-measure a known 5-second one. A second cell at N=8, **Reservation only**, carries the reproducibility clauses — its 3/10 is the only place in the grid where C1's verdict varies across seeds. **But GT-7.1 as written specifies “both assets” — N=2 — and that reading cannot produce the evidence the test is meant to give.** N=2 sits **4× below the binding PDCCH bound** (`32 CCE ÷ AL 4 = 8`, §0.3/§1.1), D4-4 measured **zero qualifying arm separations at N=4** with N=2 as an excluded-cell control, and C1 passes 10/10 on every arm there. A GT-7.1 pass at two robots is therefore **structurally guaranteed**, cannot distinguish the deployed scheduler from the baseline, and is **uninformative about the deployed fleet size**. **Same shape as G12's specification finding one row over: the test as written puts itself outside the regime where its own evidence exists** — G12's ramp stops below the load that produces an ordering, GT-7.1's soak runs below the fleet size that produces a discriminating result. Owned by whoever owns the test plan. **Fix:** run the soak at the admissible N of the arm under test (**4** for the deployed product, 8 for PF), or state that GT-7.1 certifies a two-robot shift and that fleet-size evidence comes from GT-5.2 alone. |
| **G12** | **RUN — and its most consequential result is a CLAUSE-4 FAILURE, not an ordering** | 10 seeds × 3 arms × an 8-point committed-load ramp on `mixed`/N=8 (`docs/wp9-plan.md` §35–§36; `sim/scenarios/g12.py`, `scripts/g12_campaign.py`). **(1) CLAUSE 4 FAILS, ON EVERY ARM, INSIDE GT-7.3's OWN RAMP — the only measured guarantee failure this item produced and the only result of it inside the guarantee's specified range.** G12's fourth clause is *"never 5QI 1 (telemetry/commands) while any lower class still has throughput"*, and GT-7.3 spells the FAIL out: *"telemetry gap grows while bg still moves bytes"*. Measured: telemetry **M02 reaches 1.000** — every resolved telemetry byte PDB-violated — **while 5QI 9 is still carrying 11.6 Mbps**. PF and Reservation degrade from ×2.3 of the committed-load ramp (**102 % of the measured 63.4 Mbps ceiling**); **TwoTier degrades from ×1.0 — NOMINAL LOAD — on 9 of 10 seeds** (M02 0.009–0.068), reaching **0.92–0.98 by ×1.6**. **(2) TWO QUALIFICATIONS TRAVEL WITH THAT NUMBER.** *(a)* **Whether the arm difference survives permutation is UNTESTED**: the D4 declaration-order control measures M13's output, not telemetry M02, so nothing here rules out the same flow-list-order sensitivity in this statistic. *(b)* **A SCOPE BOUNDARY OF THE CONTROL, not a caveat on the finding: E1's control pass checks M13's GBR classes (5QI 2 and 4) for a breach at ramp index 0, and 5QI 1 is `flow_class="Delay"`, structurally invisible to it. "The ramp bottom is clean" therefore means CLEAN FOR THE ORDERING and says nothing whatever about telemetry.** A reader who takes the clean control as covering clause 4 is reading a check that never looked. **(3) FILED AS A G1/G3 FINDING, not a G12 one** — a telemetry flow PDB-violated at nominal load is drive-command latency and false-failsafe territory; G12's clause 4 is only where it surfaced. Same disposition as G5's row, which arrived from G6's campaign. **(4) THE ORDERING RESULT, which is context for why the campaign looked here at all.** Inside GT-7.3's ramp only **3 of 30** groups produce a ≥2-element order, so **G12's specified degradation order is not observable at the load G12 specifies** — a **specification** finding, owned by whoever owns the test plan. **It is NOT F4's earlier result** (this row's previous text): F4's cause was one GBR class on disk with nothing to order, fixed by building a workload — done, and the workload now carries 5QI 2 and 5QI 4 at every ramp point. This one is fixed by changing GT-7.3's ramp top or accepting G12 is not testable as written. Different cause, different fix, different owner. **(5) BEYOND 145 % the order is `[2, 4]` on all 30 groups — G12's own inversion — and it is NOT REPORTED AS A SCHEDULER FINDING.** The registered control settles it: PF's permutation 101/102/103 give `[2,4]` on all 5 seeds each and **permutation 104 gives `[4,2]` on all 5**, so the order is a *deterministic* function of flow-list position; Reservation likewise shows two distinct orders; and **7 of TwoTier's 20 permuted runs cannot produce a clean ramp bottom at all**. Neither promotion clause of §35.13 fires, so the pre-registered conclusion stands verbatim: **not established as a scheduler property, consistent with a declaration-order artefact.** **(5a) AND A STRUCTURAL COMPETING EXPLANATION THE CAMPAIGN DID NOT DISCLOSE: the two GBR classes do not start the ramp on equal terms.** 4 of the 5 5QI-2 camera flows are provisioned with an offered rate **below their own GFBR** — 16,000 B / 33.0 ms = **3.879 Mbps** against **4.000 Mbps**, an arithmetic ceiling of ~**0.970** — so they begin the ramp only ~**0.007** above the 0.95 contract line, while both 5QI-4 lidar flows are provisioned offered = guarantee (ceiling 1.000) and begin ~**0.05** above it. **"Camera degrades first" is therefore biased by the workload's own provisioning, independently of any scheduler and of flow-list order.** Additive to the artefact rather than replacing it — permutation 104 flips the order with provisioning byte-identical — but any future promotion of the ordering must defeat both. This is §35.4's own trap (c) recurring at a scale small enough to survive the guard built for it (`docs/wp9-plan.md` §36.3). **(6) E1's own control MISSED**: 12/90 (cell, arm, seed) groups breach at ramp index 0, and `ugv_heavy`/`drone_heavy` are excluded **whole** — cell-level, because dropping only the failing seeds would leave the survivors self-selected (G9's §34.5 trap). The ordering therefore rests on **one** cell, not three. |
| **G9** | **RUN — and its four clauses have four DIFFERENT answers, stated separately** | 10 paired seeds × 3 arms × 3 cases (`docs/wp9-plan.md` §31–§34). This row is deliberately clause-by-clause: a single verdict would average four different epistemic situations, and G9 is the first guarantee precise enough to show why that matters. **(1) Warm app re-handshake — PRODUCIBLE, SCORED.** M18 warm p95 **16.6 ms (PF) / 21.0 (Reservation) / 79.6 (TwoTier)** against the ▷ 1 s bar. **Read with §34.5a, which REFUTES §34.5's mechanism:** TwoTier recorded only 3.8 of 10 scripted restarts — **not because its handshake outruns the scripted period** (no completed handshake ever collides with its successor; the longest is 1,086 slots against a 1,600-slot period) but because **the handshake terminally stalls and every later scripted event is discarded**. On the COLD case it is worse and it changes the verdict: **0 of 50 scheduled cold attaches completed, on every seed**, against 50 of 50 on PF and Reservation — so TwoTier's cold numbers are not a smaller sample but a **measurement of an absent UE**, and M19/M21's 0.0 ms reads as *instant recovery* for a robot that never came back. The survivors are still self-selected — **its 79.6 ms is biased optimistic and the gap to PF is wider than shown.** **(2) Full attach-to-streaming — NOT PRODUCIBLE HERE AT ALL.** `JoinConfig`'s RACH/cell-search/reestablish delays are sampled between this deployment's own t300/t301/t311 ceilings and **one** RACH trace, with `sim/join.py` recording the reestablishment floor as *"a BORROW from the one RACH trace"*. A p95 restates the configuration. **A third kind of gap: not "no mechanism" (G7) and not "blocked upstream" (G2) — the mechanism runs and the INPUT is not independent evidence.** GT-6.2's 15 s number has exactly one source and it is hardware. **(3) Post-RLF time-to-SLO — PRODUCIBLE, but NOT via M19.** M19 reads **0.0 ms on every arm and case**: `expire()` caps head-of-line age at `pdb_ms` by construction, so M19 cannot report red (§32.1). **M21** (`slo_recovery_time_by_delivery`) supplies the number — **PF 130.1 ms / Reservation 142.1 ms** from RF-restore. Never quote M19 here. **(4) Neighbours unaffected — ANSWERABLE IN THE WEAK FORM ONLY.** The weak form — *no neighbour statistic degrades with an interval excluding zero* — **PASSES on all nine arm-cases**. **The strong form is not answerable with this design**, and a reader must not take the pass as the strong claim: the paired control removes the join SCHEDULE, which also removes the joiner's OUTAGES, so the comparison is *"joiner sometimes absent"* vs *"joiner always present"* and cannot separate the cost of the join PROCEDURE from the effect of the UE being gone. **Being off IS the outage**, so no control of this scenario shape can hold offered load constant while varying whether it joins. Two cells did shift with intervals excluding zero and both moved the *improving* direction (TwoTier cold Δp98 −8.995 ms [−14.234, −3.085]); a trace over the campaign's own seeds found **r = −0.028** between joiner-absence and neighbour improvement, so absence does not explain it and the cause is **UNEXPLAINED** (§34.2). Also note ΔM02 is **floored at zero** on the neighbours even at 0.876 UL utilisation — Δp98 is the only instrument with dynamic range here (§33.3). |

> **Standing rule for any M19 number this document ever quotes.** M19's
> "SLO green" test is head-of-line age, and `sim/buffer.py::expire()` evicts
> a queue head before it can age past `pdb_ms` — **so head-of-line age is
> capped at `pdb_ms` BY CONSTRUCTION and a never-delivering flow reads
> GREEN, always.** Measured: **0 of 30,000 slots** exceed PDB on a UE
> dropping **1,396,203 bytes**. **M19 has no red state for this class at
> all**, so M21 (`slo_recovery_time_by_delivery`) or M02 is REQUIRED beside
> it, not merely advisable. The panel registers this as an M19
> caveat (`config/metric_panel.yml`), and `Scorecard.score()` attaches it to
> every M19 result, so it travels automatically with the value. **It must
> also travel with any M19 figure quoted in prose here: every M19 number is
> reported beside that UE's M02 for the same window.** This is the same
> shape as the failure §29 found on M05 — a metric reading well because the
> traffic it measures is absent rather than served.

> **⚠ G1 and G8's rows below are KNOWN-WRONG — see the banner above §2.**

## 2.1 GUARANTEE INVENTORY — one status per guarantee, with its reason

Replaces the prose coverage summary. Five statuses, chosen so a reader can
tell *what would change each one*.

| G | status | what that means here |
|---|---|---|
| **G1** | **partially answered — plus a MEASURED telemetry PDB failure from G12's campaign** | M01 p98 / M15 across the core plane; ordering only, the millisecond is not certifiable (`SIM→RF`). TwoTier breaches its own PDB bound on 6/40 base-cell seeds (§29) — a G1 finding, unexamined. **And G12's ramp produced telemetry M02 = 1.000 with bg still flowing — TwoTier from nominal load (§36.2).** |
| **G2** | **blocked on a named mechanism** | The BSR/SR desync. Blocker identified and measured: the gNB's **BSR-error magnitude at grant time** (median 12,194–13,387 B against a 2–5 **byte** window), *not* TB granularity — which was disproved counterfactually before being built (`wp9-plan.md` §20). |
| **G3** | **partially answered, conditional** | M03/M14 at `t_live_s` ∈ {1,2,4}, reported as a function of it since `T_live` is `[OPEN: HARDWARE]`. M03 now carries a **cadence caveat** where a flow's own period exceeds the bound (Step 4). **From G12's campaign: the liveness gap is UNMEASURABLE on a flow that has stopped completing** — 116 ramp points — so it goes blind precisely where the failure is total (§36.2). Read with M02. |
| **G4** | **ANSWERED at one cell** | Post-silence resume is **prompt**: latency grows *sub-proportionally* to a 10× message-size step (×3.57/×3.15/×2.21), leaving no residual for an SR/BSR cold-start penalty. **Scope note travels with it**: `_burstify` makes the post-silence message larger by construction, so the number is entangled with size (§23.5). |
| **G5** | **MEASURED FAILURE** | Both QoS-aware arms; median worst-flow PDU-set completeness **0.0000**. Reproduces across workloads with a workload-dependent onset. See G5's row. |
| **G6** | **ANSWERED — passes, with one cell unresolved** | Clause 1 ("stays within its bound") passes on every arm. Clause 2 passes on **M02** on every arm; on **M20** it passes on PF and Reservation and is **INCONCLUSIVE on TwoTier** (+29.35 % [+4.81, +56.18] — interval excludes zero, straddles the +20 % bar). Protected fleet, n_seeds=40 paired, one cell. **And G6 as *written* is unscoreable** — §0.6.1–0.6.3. |
| **G7** | **structurally out** | No MFBR enforcement anywhere in `sim/`; containment is observable, **clipping is not**, and clipping is half the pass criterion. GT-4.3 is the only test. |
| **G8** | **partially answered** | M09 per-second Jain across the sweeps; **PF arm contaminated** by `pf.py`'s declaration-order tie-break — Reservation-vs-TwoTier is the trustworthy pair. |
| **G9** | **run — 1 clause scored, 1 scored via a companion metric, 1 weak-form only, 1 not producible** | The four clauses have four different answers and the row above states them separately. §21.2a's argument is discharged: M18/M19 flip out of `pending` the moment a join event exists, and M18/M21 now carry real numbers. **Open, each needing its own commit:** **(a) why TwoTier's app handshake never completes** — 0 of 50 cold attaches, the joiner receiving zero UL grants after re-attach while its flow is reported and backlogged (§34.5a); this REPLACES the former "self-selected event shortfall", whose overlap mechanism is refuted, and the instruction changes from *lengthen the restart period* to *find why the handshake never completes*. **(b) two silent-stall defects in `sim/join.py`** — `APP_HANDSHAKE` has no ceiling and no retransmission, and scripted events are consumed-by-index regardless of phase, so later cycles are discarded rather than deferred. **(c) the unexplained neighbour Δp98** (§34.2) — which now has a *candidate*, the joiner being radio-gated out of the cell for 86 % of the horizon, though §34.2's own correlation test (r = −0.028) is not overturned by it. |
| **G10** | **ANSWERED — the headline, and it is PER ARM** | **Admissible fleet size: PF 8 robots, Reservation 4, TwoTier 4** — the pre-registered per-seed all-pass read (`M07.met == M07.total` and `M08.fraction ≥ 0.95` on **every** seed), emitted by `scripts/g10_admissible.py` from `stage2_rows.csv`, load ×1.0. **Four robots run clean on every scheduler; eight is where the QoS-aware arms fail and PF does not** — per-seed pass counts at N=8 are PF 10/10, Reservation 3/10, TwoTier 1/10. **The deployed product admits half the fleet PF does.** *"The schedulers separate at 8"* is the supporting detail, not the headline — and the **8/16 figure this row previously carried is D4-3's ARM-SEPARATION boundary, a different quantity worn as the admissible fleet** (`docs/wp9-plan.md` §8d D4-3a). **TwoTier is last on both metrics at 8 and 16 robots** (at N=16 on M08 it is *joint*-last — Reservation and TwoTier are at exactly 0.0000 on all 10 seeds); above 16 the ranking inverts, so that statement must not be carried upward. **PF's 8 is knife-edge** (worst seed M08 = 0.9503 against a 0.95 bar); the QoS-aware arms' 4 is not. §0.1 and §0.3 apply. |
| **G11** | **unrun — and NOT RUNNABLE AS SPECIFIED, measured** | The soak was budgeted and never implemented, and the budget was taken on the wrong resource. **RETRACTED 2026-09-03 — see `docs/wp9-defects-log.md` #17.** This row read *"one run needs ~48 GiB with `record_timeseries=True` … and ~24 GiB with it off"*. Both figures come from a probe that builds `sweep_scenario` at **N=8** with **no window sink**; the campaign builds `build_g11_scenario` at **N=4, windowed**. On the campaign's own path, measured, the retained completion batches were ~85 % of a run and have been removed — a 7.2 M-slot run is now expected at **≈2 GB** (extrapolated from 240k/480k, not yet measured at the real horizon) (`docs/wp9-plan.md` §37). Confirmed by a guarded run: the cheapest arm reached **21.8 GiB and was killed with 2.4 GB left**. Half the footprint is per-message bookkeeping that no flag disables, and it is **not** a saturation artefact (halving `load_mult` moves it 2.6 %). **So the 3-seed deviation solved a TIME budget while the blocker was MEMORY, and cutting seeds cannot fix an OOM in a single run** — 3 seeds and 10 OOM identically, on run one. Needs two mechanisms (per-window ledger eviction, per-second timeseries fold) before it can run at all; with them the 10-seed campaign fits in ≈2.15 h. **Scope: measured at the 32-flow base cell; GT-7.1's literal two-asset reading is ~7–12 flows and untested.** Plan: `docs/wp9-g11-plan.md`. **THE FLEET SIZE IT WILL RUN AT, AND A SPECIFICATION FINDING ABOUT THE ONE GT-7.1 SPECIFIES.** The soak is planned at **N=4**, and the reason is **discovery versus re-measurement, not fairness**: C1's conjunction passes **10/10 on every arm at N=4** and is **0/10 on TwoTier / 3/10 on Reservation at N=8** (computed from `stage2_rows.csv`, `docs/wp9-g11-plan.md` §7.4), so N=4 is the only fleet size where a 30-minute soak can **discover** a failure rather than re-measure a known 5-second one. A second cell at N=8, **Reservation only**, carries the reproducibility clauses — its 3/10 is the only place in the grid where C1's verdict varies across seeds. **But GT-7.1 as written specifies “both assets” — N=2 — and that reading cannot produce the evidence the test is meant to give.** N=2 sits **4× below the binding PDCCH bound** (`32 CCE ÷ AL 4 = 8`, §0.3/§1.1), D4-4 measured **zero qualifying arm separations at N=4** with N=2 as an excluded-cell control, and C1 passes 10/10 on every arm there. A GT-7.1 pass at two robots is therefore **structurally guaranteed**, cannot distinguish the deployed scheduler from the baseline, and is **uninformative about the deployed fleet size**. **Same shape as G12's specification finding one row over: the test as written puts itself outside the regime where its own evidence exists** — G12's ramp stops below the load that produces an ordering, GT-7.1's soak runs below the fleet size that produces a discriminating result. Owned by whoever owns the test plan. **Fix:** run the soak at the admissible N of the arm under test (**4** for the deployed product, 8 for PF), or state that GT-7.1 certifies a two-robot shift and that fleet-size evidence comes from GT-5.2 alone. |
| **G12** | **RUN — clause 4 FAILS inside the guarantee's own ramp; the ordering is unobservable there** | Telemetry M02 **1.000** with 5QI 9 still moving 11.6 Mbps — GT-7.3's own worked FAIL example. PF/Reservation from 102 % of ceiling, **TwoTier from nominal load on 9/10 seeds**. Filed as **G1/G3**. Two qualifications inline on G12's row: the arm difference is **untested under permutation**, and **E1's clean control does not cover telemetry** (it reads GBR classes; 5QI 1 is Delay). The order itself is not observable in range, and the beyond-range `[2,4]` inversion is **not established as a scheduler property and is consistent with a declaration-order artefact** — §35.13's registered wording, restored here after this row had hardened it into "is a property of declaration order", a positive causal claim the control does not license. **A third qualification: 4 of 5 camera flows are provisioned BELOW their own GFBR (3.879 vs 4.000 Mbps, ceiling ~0.970), beginning the ramp ~0.007 above the 0.95 line against the lidar class's ~0.05 — so "camera degrades first" is partly the workload's own provisioning, independent of any scheduler (`docs/wp9-plan.md` §36.3).** |

**Read as a whole: 3 answered (G4, G6, G10), 1 measured failure (G5),
3 partially answered (G1, G3, G8), 2 run with clause-level answers
(G9, G12), 1 unrun (G11), 1 blocked on a named mechanism
(G2), 1 structurally out (G7).**

**Derived, and now actually derivable:** `uv run python
scripts/regime_map_rollup.py` parses the rows above and emits this
sentence; `--check` exits non-zero if the two disagree, and an
unrecognised status is a hard error rather than a guarantee silently
dropping out of the count.

> **This sentence was wrong until the commit that added the deriver, and the way it was wrong is
> worth keeping.** It read *"3 unrun-but-buildable (G9, G11, G12)"* —
> **while the G9 row above it said `run` and the G12 row said `RUN`** — under
> the words *"Counts derived from the rows above, not carried separately."*
> The count went stale the moment those two campaigns closed, and **the
> claim of derivation was itself the restatement.**
>
> That makes this the fifth instance of CLAUDE.md's restated-count rule and
> the only one with an aggravating feature: **the earlier four failed
> loudly by disagreeing with something a reader could check** — the
> "22-record" corpus against `_cases()`, §6.3's timing table against the
> real run, stage 1's "56 cells" against the runner's own printed count.
> **This one asserted its own immunity**, so a reader had no reason to look.
> A restated count is bad; a restated count wearing a derivation claim is
> worse, because it disarms the check.
>
> Note also that the correct roll-up was **already sitting in
> `docs/HANDOVER-new-machine.md` §6**, written after G9 and G12 closed. Two
> documents disagreed for as long as this one went unread.

**And read §2.2 before quoting any single row: it states the aggregate
across the deployed arm's results, which no individual row can.**

**The three entries a reader should not skip** are G5 — the most
operationally serious thing WP9 has found, and a *base-cell* failure with
no aggressor — G6, which passes on measurement **on M02 while leaving one
TwoTier cell unresolved on M20** and is **unscoreable as specified** — and
**G11, which is not RUNNABLE as specified**, for reasons that were
measurable at any point in the last six months and were not measured.

**G6 and G11 are the same shape one level apart, and that is worth naming.**
G6's finding is that a guarantee can be *unscoreable* as written — its bar
is undefined when the denominator can be zero. G11's is that a guarantee can
be *unrunnable* as written — its horizon and its required instrument
together exceed the machine. **Both are findings about the guarantee
document rather than about the schedulers**, and neither surfaced until
someone tried to execute the clause literally. A campaign plan that only
ever asks "what did the arms do" will not find either.

---

## 2.2 THE TWO-TIER PATTERN — an aggregate nobody had stated

Every row above states its own finding. **This section states what they say
together**, because the aggregate is visible only to a reader who works
through all of them, and the arm it concerns is **the deployed product**.

**This is a finding for the campaign — where to look and what to carry to
hardware — not a scheduler indictment.** §2.2.3 says what the evidence does
*not* support, and it is as long as what it does.

### 2.2.1 What the corrected results say, together

| guarantee | statistic | PF | Reservation | **TwoTier** |
|---|---|---|---|---|
| **G10** | admissible fleet (all-pass, every seed) | **8** | 4 | **4** |
| **G10** | rank on M07 / M08 at N=8 | 1 / 1 | 2 / 2 | **3 / 3** |
| **G10** | rank on M07 / M08 at N=16 | 1 / 1 | 2 / 2= | **3 / 2=** |
| **G9** | cold attaches completed, of 50 scheduled | 50 | 50 | **0** |
| **G6** | M20 liveness residual under the flood | +0.44 % PASS | +1.84 % PASS | **+29.35 % [+4.81, +56.18]** — the only interval excluding zero |
| **G1** (§28.4) | M01 p98 ≤ 100 ms, base cell | 0/40 | 0/40 | **8/40 FAIL** |
| **G3** (§28.4) | M03 gap ≤ 500 ms, base cell | 0/40 | 0/40 | **2/40 FAIL** |
| **G5** (§28.4) | M06 frame age p95 ≤ 67 ms, base cell | 0/40 | 0/40 | **12/40 FAIL** |
| **G5** (§28.4) | M05 completeness ≥ 0.99, base cell | 3/40 FAIL | 30/40 FAIL | **35/40 FAIL** |
| **G3** (§24.6) | M03 gap ≤ 500 ms at `duty_cycle` 0.5 | 0/10 | — | **5/10 FAIL** |
| **G1/G3** (§36.2) | load at which telemetry M02 degrades | ×2.3 (102 % of ceiling) | ×2.3 | **×1.0 — NOMINAL, on 9/10 seeds** |

**The single strongest element is §28.4's clause-1 row set, because it is
one cell, one population and all three arms at once.** Of the **five**
statistics that carry a numeric bound there, **three fail on TwoTier and on
no other arm** (M01, M03, M06), and the fourth (M05) fails on every arm with
TwoTier worst. That is not five independent coincidences; it is one table.

### 2.2.2 And the counter-evidence, which is real

**TwoTier is not uniformly worst, and two results run the other way.**

- **On G6's own currency it is the BEST arm.** The protected-fleet M02 delta
  is PF **+0.0000**, Reservation **−0.0104**, TwoTier **−0.0270** — lower is
  better for a violation rate, so under a 50 Mbps flood TwoTier's protected
  bearers *improve most*. The G6 residual in §2.2.1 is on M20, a different
  statistic.
- **Above N=16 the G10 ranking inverts and TwoTier stops being last.** At
  N=24/32 PF meets **zero** GBR contracts while holding the best max-min
  floor. On contracts TwoTier is **2nd at N=24** (6.7 against Reservation's
  10.4) and **1st at N=32** (**6.4 against 6.2**). §0.1's rule applies with
  full force: any single-metric claim about who wins at high N is false by
  construction, and "TwoTier last" is a statement about **N ∈ {8, 16}** that
  must not be carried upward.

  *(An earlier draft of this bullet said TwoTier "ties or beats Reservation"
  at N=24 as well. It does not — Reservation leads 10.4 to 6.7 there. The
  phrasing came from the deck and was corrected against
  `scripts/g10_admissible.py`'s own rank output, which is the point of
  having the deriver.)*

### 2.2.3 What this does NOT establish — read before quoting §2.2.1

1. **No mechanism has been traced across any two of these.** They are
   separate measurements on separate guarantees, and nothing here shows a
   common cause. A reader who converts the table into "TwoTier is broken"
   has added a claim the evidence does not contain.
2. **Several rows carry their own unresolved confound**, each already on its
   own row above:
   - **G5's lever is unisolated** — the failure is present at the base cell
     with no aggressor, and which mechanism produces it is not established.
   - **G12's declaration-order confound is untested on this statistic.**
     The permutation control measured M13's ordering, not telemetry M02, and
     **7 of TwoTier's 20 permuted runs could not produce a clean ramp bottom
     at all** — so flow-list position demonstrably reaches this arm harder
     than the others, and the ×1.0 result is not known to survive it.
   - **G6's residual is one cell** (N=8, load ×1.0, uplink aggressor only),
     and its verdict is INCONCLUSIVE — the interval straddles the bar.
   - **G10's PF 8 is knife-edge** (worst seed M08 = 0.9503 against a 0.95
     bar); the gap to TwoTier's 4 is real, but PF's own 8 is not robust.
   - **G9's cold result has a traced proximate cause and an untraced root
     one** — the joiner receives zero UL grants after re-attach, but *why*
     is a lead (`reset_ue(scope="full")` / Tier-1 re-solve), not a finding.
3. **Three of the eleven rows are the same underlying video failure.** M05,
   M06 and G10's M08 at N≥8 all read the same chronically-incomplete
   `xr_video` flows — and §29 established the breach counts are over
   **seeds, not flows** (TwoTier's 35 come from **4 flows, one accounting
   for 30**). Counting them as three independent signals overstates the
   pattern's breadth.
4. **It is not a comparison the campaign was designed to make.** WP9's arms
   exist to locate regime boundaries, not to rank products, and no cell was
   chosen to be fair to TwoTier specifically.

### 2.2.4 Why it is worth stating anyway, and what would settle it

**Because the deployed scheduler is the one a reader most needs the
aggregate for**, and because two of these — G9's cold attach and G1/G3's
nominal-load telemetry degradation — are **operationally serious on their
own** and would each justify a hardware test without the pattern.

**The pattern is a prompt, and it makes two things worth doing:**

- **The cheapest discriminator is the permutation control widened.** If
  TwoTier's results move under flow-list reordering where the other arms'
  do not, a large part of §2.2.1 is an artefact of position, and §36.1
  already shows this arm is the one position reaches hardest. If they do
  **not** move, the pattern survives its most likely confound and becomes
  much harder to dismiss. Either outcome is worth more than another cell.
- **Carry G9's cold path and G12's nominal-load telemetry to hardware
  first**, per §5 — they are the two with a measured failure and an
  operational meaning, and neither depends on the aggregate being real.

**What would refute it:** a traced mechanism showing a shared artefact (flow
declaration order is the standing candidate), or the rows dissolving
individually as their own confounds are closed. **What would confirm it:**
the same ordering reproducing on a workload the arms were not tuned
against, with position controlled.

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

### 4.1 Two guarantees have now produced their most consequential finding for a DIFFERENT row

An observation about how this campaign is structured, not about either
guarantee.

- **G6's work produced G5's failure.** Step 3 evaluated G6's first conjunct,
  which nobody had evaluated before, and found PDU-set completeness of
  0.0000 on both QoS-aware arms — **at the base cell, with no aggressor**,
  so it was never a G6 result at all (§29).
- **G12's campaign produced G1/G3's failure.** Its clause 4 is the only
  clause of G12 with a *safety* meaning, and scoring it found telemetry
  M02 = 1.000 with background still flowing — a drive-command/false-failsafe
  result that G12 merely happened to look at (§36.2).

**Both were found by evaluating a clause of a guarantee that had been
carried for a long time without being scored, and in both cases the clause
belonged to a different guarantee's subject matter than the campaign's own
headline.** The transferable point for the next campaign's design: **a
guarantee's clauses are not all about the same thing, and the one most
likely to be unscored is the one whose instrument differs from the
guarantee's headline instrument.** G6's headline was a delta and its
unscored clause was a bound; G12's headline was an ordering (M13) and its
unscored clause was a PDB rate (M02). **Scoring a guarantee clause-by-clause
with each clause's own instrument named — the discipline G9's row
introduced — is what surfaced both**, and it should be the default rather
than something adopted when a guarantee turns out to be complicated.

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
