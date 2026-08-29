# WP9 regime map — the bridge artefact for the hardware campaign

**Audience:** the team executing `IA_P5G_Factory_Guarantee_Test_Plan.md`.
This is the characterisation output that plan's §0 and §10 reference. It
says where the boundaries are, which guarantees are scheduler-limited
versus fault-model-limited, and where to spend the rule-of-three budget and
the real-RF window.

**Evidence base:** stage 1 (59 cells, 1,770 runs) and stage 2 (252 cells,
7,560 runs, full factorial, contiguity-checked), 10 paired seeds per cell,
all 19 panel metrics scored per run. `docs/wp9-plan.md` §8b–§8d carries the
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

**The eight dropped axes are live candidates, not tested-and-rejected**:
`sr_period_slots` (152.579), `min_rb` (152.579), `snr_spread_db` (4.689),
`pdb_ms` (2.927), `duty_cycle` (2.663), `bg` (2.648), `mfbr_multiple`
(1.778), `inf_scenario` (did not qualify). **`mfbr_multiple` and `min_rb`
now carry specific named reasons to run next** — §0.2 and §0.3.

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
| **G2** | **Not answered by WP9** | Needs an event-triggered STOP flow and trial accumulation; no WP9 cell models it. GT-1.2 remains **RF**. |
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
| **H2** (two-tier wins as traffic becomes bursty) | **Not tested** | `duty_cycle` qualified (2.663) and was dropped by the cap. |
| **H3** (two-tier wins as channel spreads) | **Not tested** | `snr_spread_db` qualified (4.689) and was dropped by the cap. |
| **H4** (Tier-1 mismatched to factory deadlines) | **Not tested** | `pdb_ms` qualified (2.927) and was dropped by the cap. |
| **H5** (two-tier degrades as flows-per-LCG grows) | **Untestable as configured** | §0.2. |
| **H6** (overload outcome is metric-dependent) | **CONFIRMED** | §0.1 — the clearest positive result in the sweep, and it was *not* predicted in advance. |
| **H7** (liveness decided by the UL access path) | **Not tested** | `sr_period_slots` qualified (152.579) and was dropped by the cap. |

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
2. **GT-2.2 / GT-2.3 remain the only test of the UL floor.** WP9 never
   exercised it: the floor needs a BSR/SR desync fault **and**
   `mfbr_bps > 0`, and `sim/bsr.py` cannot express the fault at all
   (`docs/wp9-plan.md` §8a). WP9 offers no prediction for the floor-OFF
   delta GT-2.2 measures.
3. **GT-4.3 (MFBR clamp) is unmodelled**, per §0.2/G7 — hardware only.
4. **GT-7.3 (degradation ordering) is where H6 bites.** Expect the
   first-violation order to depend on which metric the pass criterion
   reads; specify that metric before running.
