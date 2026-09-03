# WP9 plan — the characterisation sweep (Phase 3)


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


> **A NOTE ON COUNTS IN THIS DOCUMENT.** Any "N metrics", "N cells", "N
> records" written in prose below is **as-of-writing**. This project has five
> recorded instances of a restated count going stale, and the panel's own size
> has been wrong three times (19 → 21 → 22). **Derive every count from the
> thing that produces it** — `len(load_panel()["metrics"])`,
> `len(regression_corpus._cases())`, `sum(len(v) for v in EXCURSIONS.values())`
> — and treat a number in prose as a claim about code at a past date.


## 0. What this work package is, and what it is not

Phase 2 is complete (`a5f6baa`). Both schedulers are ported from verified OAI
C, the regression corpus is re-baselined and `--check`-clean, and
`docs/phase2-plan.md` §7 hands forward four open threads, five dormancy
categories, and two shared unswept parameters.

**WP9 is a study-design work package, not a porting one.** There is no C to
read and no ground truth to check against. Every prior WP in this branch
answered "does this match what shipped?"; WP9 answers "under what conditions
do these two schedulers differ, and by how much?" The disciplines that
carry over are the methodological ones — plan approved before code,
one change per commit, predictions stated before running and scored
afterwards (hits *and* misses), the frozen pre-registered panel — not the
ground-truth ones, which have nothing to attach to here.

**What WP9 produces.** The regime map, and specifically the three things
`docs/IA_P5G_Factory_Guarantee_Test_Plan.md` §0 and §10 reference this suite
for:

1. where the regime boundaries are, in (N, offered load, `min_rb`) terms;
2. which guarantees are **scheduler-limited** versus **fault-model-limited**
   — the distinction that tells the campaign whether a red GT row is a
   policy problem or a missing-mechanism problem;
3. where to spend the rule-of-three trial budget and the scarce real-RF
   window.

**What WP9 does not produce.** It does not validate G1–G12 in simulation.
`README.md` §5's "sim-answerable" column means *the simulator can produce an
informative pass/fail*, never *the number is certifiable*. §5 below draws
that line explicitly, per guarantee, in the same SIM / SIM→RF / RF vocabulary
the hardware plan uses (Test Plan §4.5), so the two documents can be read
against each other without translation.

### 0.1 Two corrections to this WP's own scoping inputs

Both were stale summary carried into WP9's scoping, corrected here against
the repo before any design rests on them.

1. **`sim/parametric.py` does not exist.** The sweep infrastructure is
   `scripts/regime_sweep.py` alone (paired seeds, bootstrap CIs, the
   contiguity check, `regime_selection_excluded`, a tidy-CSV writer), plus
   `sim/scorecard.py`, `sim/run_record.py` and `config/metric_panel.yml`.
   A parametric scenario builder is a WP9 **build** item (§2, B4), not a
   reuse.
2. **The panel is 19 metrics (M01–M19), not 12.** `Scorecard.score()`
   auto-computes 17 per run; **M13** (`first_violation_order`, a cross-run
   load-ramp metric) and **M16** (`ul_dl_shared_bearer_correlation`, needs a
   named UL/DL flow pair) are study-layer calls, deliberately outside the
   per-run scan (`sim/scorecard.py:106-141`). "Score every metric, every
   run" therefore means **17 automatic + 2 explicitly invoked by the sweep
   runner**, and a runner that forgets the second pair silently under-reports
   two guarantees (G12, and the shared-bearer half of G1/G2/G3).

---

## 1. The base point, and the base RAN

Every axis excursion and every effect size below is measured from one base
point. Stated once, here, because "all else equal" is otherwise undefined.

| | Value | Source |
|---|---|---|
| RAN | `dsuuu_40mhz` — 55 PRB, μ=2, 0.25 ms slots, DSUUU | `factory_robots_scenario`'s own default RAN |
| PDCCH | D-slot CCE 48, U-slot 32, S-slot 16; `average_agg_level` = 4 | `sim/resource.py:33-57`; the hardcoded AL is CLAUDE.md's own known issue |
| N | 8 UEs | §3 |
| Offered load | **×1.0** (was ×1.5 pre-fix), **UL-load-scaled, not capacity-scaled** | §3, exclusions; **re-derived post-fix, §1.2** |
| `min_rb` | 5 | the calibration campaign's deployed value |
| `mfbr_bps` | 0 (off) | never configured on any flow anywhere in this repo |
| Mix | per UE: UL GBR video + UL telemetry (10 Hz) + DL command (20 Hz) | maps onto T1/T2/T3 of the hardware plan §1 |
| SNR | 20 dB uniform, `coherence_slots=2000` | corpus convention |
| `sr_period_slots` / `k2_slots` / `harq_round_max` / `k1_slots` | 10 / 2 / 4 / 4 | `sim/driver.py::run` defaults |
| `cqi_delay_slots` | **8 — pinned, never swept** | `scheduler_study.py::CQI_DELAY_SLOTS`; §3 exclusions |
| Horizon | **20,000 slots = 5.0 s sim time** | §6 |
| `record_timeseries` | **True, always** | measured free: 1.39 s vs 1.58 s per run |

**Why 20,000 slots and not the corpus's 4,000.** At this RAN 4,000 slots is
1.0 s, in which a 10 Hz telemetry flow emits *ten* messages — far too few for
any rule-of-three statement (§6). 20,000 slots gives 50 messages per telemetry
flow per seed, which pools to a defensible bound. **The regression corpus
horizon stays at 4,000**; it is a drift detector, not a statistics engine, and
changing it would invalidate the `a5f6baa` baseline for no benefit.

**`record_timeseries=True` unconditionally.** M04, M09 and M19 report
`pending` without it — three of nineteen metrics silently absent from every
cell. It was measured, not assumed, to be free.

### 1.2 Base-point re-derivation, post-fix (amendment)

§1's base point was chosen against measurements taken **under the
SR-trigger defect** (`docs/oai-port-map.md` row 79). Those measurements are
what motivated the pause; these are what justify the base point that
replaces it. Re-measured post-fix, same workload shapes, N=8, 4,000 slots,
UL PRB utilisation, `(pre-fix)` in parentheses:

| variant | PF | Reservation | TwoTier | (pre-fix PF/Res/TT) |
|---|---|---|---|---|
| BE only, poisson | 0.905 | 0.931 | 0.934 | (0.008 / 0.006 / 0.006) |
| BE only, bursty, same mean rate | 0.937 | 0.933 | 0.937 | (0.123 / 0.038 / 0.015) |
| BE only (1 UL/UE) | 0.907 | 0.932 | 0.933 | (0.008 / 0.006 / 0.006) |
| BE + video (2 UL/UE) | 0.937 | 0.936 | 0.937 | (0.937 / 0.338 / 0.014) |
| BE + telemetry (2 UL/UE) | 0.911 | 0.929 | 0.933 | (0.009 / 0.001 / 0.001) |
| BE + video + telemetry (3 UL/UE) | 0.936 | 0.925 | 0.934 | (0.936 / 0.015 / 0.014) |

**The collapse is gone entirely, and so is the utilisation ordering.** Every
arm now sits at 0.905-0.937 on every shape; the pre-fix
PF > Reservation > TwoTier spread of up to 60x was the defect, reproducing
the worktree patch's own 0.928/0.924/0.934 near-parity. TwoTier is now
marginally *highest* on most shapes -- the reverse of the pre-fix ordering.
`_BE_PER_UE_BPS = 8e6` is **retained**: post-fix it puts load ×1.0 at
~96 Mbps offered against a cell that saturates near there, so the axis
spans genuine underload to genuine overload.

**Does an arm ordering survive? On utilisation, no. On the outcome metrics,
yes — and that changes what the base point means.** Post-fix load curve at
the real 20,000-slot horizon:

| load | arm | UL util | deliv/off | loss (M02) | GBR met |
|---|---|---|---|---|---|
| 0.75 | PF / Res / TT | 0.936 / 0.919 / 0.936 | 0.848 / 0.818 / 0.838 | 0.116 / 0.146 / 0.136 | 8/8 / 8/8 / 8/8 |
| **1.0** | PF / Res / TT | 0.936 / 0.921 / 0.932 | 0.699 / 0.670 / 0.623 | **0.261 / 0.289 / 0.356** | **8/8 / 7/8 / 5/8** |
| 1.25 | PF / Res / TT | 0.936 / 0.920 / 0.934 | 0.592 / 0.573 / 0.575 | 0.365 / 0.382 / 0.384 | 8/8 / 7/8 / 5/8 |

Utilisation is saturated (~0.93) across the whole band and **is not a
discriminator post-fix**, so the base point is chosen on outcome metrics
instead. **The base cell is therefore not neutral ground: the arms already
separate there**, PF > Reservation > TwoTier on both loss and GBR contracts.

Stated carefully, because it is pre-registration-relevant: this is a
**single-seed observation, not a result**. It has no paired-seed effect size
and no bootstrap CI, and it is exactly what §6.4's gate exists to confirm or
reject. It does **not** pre-answer D4-4 -- but it does mean stage 1 starts
from a cell where a candidate signal is already visible, which is good for
informativeness (the base and its excursions will pass `is_informative`) and
which must not be mistaken later for a result the sweep produced. If the
gate does not confirm it at 10 seeds, that is the finding.

**A correction to this module's own earlier reasoning, found while
re-measuring.** `sim/parametric.py` originally justified putting the load on
the best-effort filler with a *mechanical* claim -- that periodic instrument
flows cannot keep a cell occupied, evidenced by the 195-vs-3131 grant-count
gap. **That claim was the defect talking, and post-fix it is false**:
re-measured, the instrument flows alone deliver **98.7% of what they offer at
~49% UL utilisation on all three arms**. Nothing collapses. The design
survives, but for two more ordinary reasons that are now the ones stated in
the code: methodological (load_mult must not change the quantity G1/G3/G5
measure -- the same instrument/load split GT-3.2 and GT-7.3 use), and
arithmetic (at profile rates the instruments offer ~32 Mbps against a
~100 Mbps cell, so they cannot reach overload without being distorted past
what they represent). Recorded rather than quietly re-worded, since a comment
whose stated reason has been falsified is exactly the kind of stale
justification this project keeps catching.

**Base load ×1.5 → ×1.0**, on three grounds: non-zero loss on all three arms
so `is_informative` passes; the widest arm spread in the band (loss 0.261 →
0.356, and GBR-met 8/7/5, where 0.75 separates on neither contract count and
1.25 is already compressing); and ~96 Mbps offered against a ~100 Mbps cell,
i.e. a natural "100% load" reference matching the hardware sweep's own
framing.

**§4's axis levels re-checked against the new base, not left inherited:**

- **Load axis amended: 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0** (was 0.5, 0.75,
  1.0, 1.5, 2.0, 3.0). **×0.25 dropped** -- measured zero loss on all arms,
  so `regime_selection_excluded` would discard it and the cell is wasted
  budget. **×1.25 added** to densify the 0.75-1.5 band, which is where the
  arms actually separate. ×0.5 retained as the last near-zero-loss anchor
  (loss 0.000 at 4k but it does separate on GBR-met 8/7/6, so it is not
  uninformative in the panel's wider sense). ×3.0 retained for M13's load
  ramp even though the arms converge there -- G12's first-violation order
  needs genuine overload. Core plane becomes 6 N x 7 load = **42 cells**
  (was 36); stage 1 ≈ 56 cells, still ~1.5 h single-core, inside the 4 h
  ceiling.
- **N axis unchanged (2, 4, 8, 16, 24, 32).** §1.1's boundary prediction is
  a function of `prb_count`, CCE budget and `min_rb` only -- no traffic term
  -- so the fix does not touch it. **Worth stating explicitly**: because the
  BE filler is per-UE, total offered load scales with N, so at N=32 / load
  ×1.0 the cell is ~4x overloaded. That is deliberate and correct for G10 --
  "admissible fleet size" *is* "at what N do the guarantees break" -- but it
  means N and load are not orthogonal, and the core plane must be read as a
  plane rather than two independent lines.
- **Base N=8 unchanged**, `min_rb`=5, `mfbr`=0, SNR, `sr_period`, `k2`,
  `cqi_delay`, horizon, `record_timeseries` all unchanged -- none was chosen
  against a defect-affected measurement.
- **`min_rb` / `mfbr` / SNR-spread / PDB / `sr_period` / `k2` / InF /
  shared-LCG / bg excursion levels survive unchanged**: each is a config or
  channel knob whose levels were picked from ground truth or from the axis's
  own hypothesis, not from a measured base value.
- **One known limitation, recorded rather than fixed:** `_burstify` now
  applies only to the instrument flows (telemetry, video, DL command), since
  the BE filler is `poisson` and carries the load. So H2's duty-cycle axis
  varies the burstiness of the *instruments* at constant mean rate, not of
  the offered load as a whole. That is a narrower test of H2 than "the cell's
  traffic becomes burstier", and the H2 result must be reported in those
  terms.

**The go/no-go rule (§6.4), the D4-4 N=2 control, and the five primary
metrics are unaffected by this recalibration and stand exactly as
committed.**

### 1.1 The predicted regime boundary, computed before anything runs

H5's sibling H1 (`docs/p5g-sim-plan.md:334`) predicts reservation degrades
above `N_crit ≈ min(bwpSize/min_rb, CCE_budget/AL)`, and states explicitly
that **which of the two bounds binds is itself a result**. At the base RAN, in
the uplink:

- follower-budget bound: `prb_count / min_rb` = 55 / 5 = **11**
- PDCCH bound: `U-slot CCE / AL` = 32 / 4 = **8**

So at the deployed `min_rb=5` the **PDCCH bound binds first (8)**, and the
follower budget does not become the binding constraint until
`min_rb > 55/8 = 6.875`. Two consequences, both load-bearing:

1. A sharp pre-registered prediction with a named crossover at
   **`min_rb ≈ 7`** (§4, D4-3): `min_rb` should have **no** effect on the
   boundary in the 1–6 range.
2. A quantitative reason the N axis must span 2 → 32. **The hardware
   measurement's N=2 sits 4× below either bound**, which is why that campaign
   could not have differentiated the schedulers regardless of how carefully it
   was run — consistent with, and now numerically explaining, its own author's
   conclusion (`README.md` §7).

---

## 2. What exists, what gets built

**Reused unchanged.** `scripts/regime_sweep.py`'s `paired_seeds`,
`bootstrap_ci`, `aggregate`, `check_contiguity`, `regime_selection_excluded`
and `write_csv`; `sim/scorecard.py::Scorecard`; `sim/run_record.py::RunRecord`;
`sim/driver.py::run`; the three arms; and **`config/metric_panel.yml`,
unedited** — WP9 adds, removes and redefines nothing in the panel.

**Built — six items.**

- **B1 — `Reservation` `min_rb` plumbing** *(pre-sweep commit 0, §7)*.
  `Reservation.configure(flows, slot_duration_s, grid, min_rb=5)` assigns
  `self.min_rb = min_rb` (`scheduler/reservation.py:707-716`), and
  `sim/driver.py:157` calls `configure(...)` with three positional arguments —
  so a constructor-time or post-construction `min_rb` is **clobbered back to 5
  on every run**. TwoTier's is a constructor kwarg (`two_tier.py:904`) and
  survives. **The `min_rb` axis is unrunnable on the Reservation arm until
  this is fixed**, which is why it is commit 0 and not a detail.
- **B2 — `sweep()` axis plumbing.** `regime_sweep.sweep()` passes axis values
  only to `build_scenario`, and takes one fixed `driver_kwargs` for the whole
  grid. But `min_rb` is an *arm-config* axis and `sr_period_slots`/`k2_slots`
  are *driver* axes. Extend `sweep()` so scheduler factories and driver kwargs
  can each be a function of the cell's axis values.
- **B3 — RunRecord persistence.** `sweep()` deliberately discards RunRecords
  (its own docstring says so). WP9 needs them: M13/M16 and every
  scoring-parameter variation (§3) are computable post-hoc from a stored
  record via `RunRecord.to_dict`/`from_dict`. Re-running 30 runs to re-score at
  a different `t_live_s` is pure waste. One JSONL per cell.
- **B4 — `sim/parametric.py`.** The parametric scenario builder §0.1 found
  absent. One function returning a `ScenarioConfig` from `(n_ues, load_mult,
  mix, snr_spread_db, pdb_ms, shared_lcg, mfbr_multiple, seed)`. Its docstring
  states it is a WP9 sweep factory and **not** a member of
  `sim/scenarios/`'s YAML registry, whose own contract is "drop a YAML file".
- **B5 — `scripts/wp9_sweep.py`.** The stage runner, **and the §6 go/no-go
  rule implemented as code**, committed before stage 1 runs so it cannot be
  re-cut after results are visible.
- **B6 — M13/M16 study-layer calls.** `first_violation_order()` over the load
  column of each N row; `correlate_flows()` on each UE's T1/T2 shared-bearer
  UL/DL pair.

---

## 3. Decision 1 — Axes

### Stage 1, core plane (dense, two-dimensional)

The plane this project exists to map. `n_followers_need` counts *per-slot
backlogged* candidates, so N and offered load interact — this must be a plane,
not two independent lines.

| Axis | Levels | Why |
|---|---|---|
| **N** (UEs) | 2, 4, 8, 16, 24, 32 | Spans §1.1's predicted boundary (8–11) in both directions. **N=2 is a positive control, not a data point** (§4, D4-4). |
| **Offered load** | ×0.5, 0.75, 1.0, 1.5, 2.0, 3.0 | H6; G12's degradation ordering; and the exclusion rule's own requirement to push until loss appears on at least one arm. |

**36 cells.**

### Stage 1, excursions (one axis at a time from the base point)

| Axis | Levels | Discharges |
|---|---|---|
| `min_rb` | 1, 5, 20 | `[OPEN: WP9]` min_rb; §1.1's two-bound crossover. **Moves both arms** — stated on every claim it touches. |
| `mfbr_bps` | 0, 2× GFBR | `[OPEN: WP9]` mfbr; activates `gbr_bytes_slot` / `gbr_below` in both arms at once |
| Burst duty cycle | continuous, 50 %, 10 % | **H2** |
| SNR spread | 0, 6, 12 dB across UEs | **H3** |
| PDB / Tier-1-period ratio | `pdb_ms` 10, 100, 1000 (Tier-1 = 100 ms) | **H4** — the hypothesis the charter says runs first |
| `sr_period_slots` | 1, 10, 40 | **H7**; the UL-access-chain dominance cluster (Facets 1–4) |
| Flows-per-LCG | 1 vs 2 same-class UL flows sharing an `lcg` | **H5** |
| `k2_slots` | 1, 2, 4 | discharges README §8 Facet 3's own "the sensitivity WP9 should sweep" |
| InF sub-scenario | none, `InF-DL`, `InF-DH` | `[OPEN: WP9]` sub-scenario choice |
| bg (non-GBR flood) | off, on | **G6**; the GT-4.1/4.2 analogue |

Base level shared across excursions ⇒ **≈ 14 cells**. **Stage 1 total: 50.**

### Included as *scoring* variations — free, no extra runs

`Scorecard.score(record, **overrides)` re-scores a stored record, so these
sweep at zero run cost off B3's persisted records, and each discharges an open
item:

- `survival_miss_n` ∈ {2, 3, 5} — M04; discharges `[OPEN: WP9]` "start at 3,
  **report H6 as a function of N**".
- `t_live_s` ∈ {1, 2, 4} — M03/M14. `T_live` is `[OPEN: HARDWARE]` and
  unmeasured, so **every G3 row is reported as a function of it**, never at a
  single assumed value.
- `gbr_contract_fraction` ∈ {0.90, 0.95, 0.99} — M07/M08.
- `slo_green_dwell_s` ∈ {0.5, 1.0, 2.0} — M19.

### Excluded, with reasons

- **Capacity scaling (`_scale_capacity`, Study 1's own axis) — excluded as
  the load axis; `_scale_ul_load` used instead.** Capacity scaling changes
  `prb_count`, which **moves §1.1's own predicted boundary
  (`bwpSize/min_rb`) cell by cell** — it would confound the exact quantity the
  sweep exists to locate. Study 1's published numbers stay valid for what they
  measured; they are not a load axis. **This has a direct consequence for
  D4-2** (§4).
- **`cqi_delay_slots` — excluded, pinned at 8.** CLAUDE.md's own invariant
  makes it load-bearing for every time-varying-channel × HARQ interaction, and
  every real study in this branch runs at 8. Sweeping it moves HARQ behaviour
  in all three arms simultaneously, for a question about link adaptation
  rather than scheduling policy. A fixed condition of the whole map, recorded
  as such.
- **`harq_round_max`, `harq_combining_mode`, `k1_slots` — excluded, pinned.**
  Simulator-fidelity knobs that move all three arms identically. `k2_slots` is
  the deliberate exception (included above) because README §8 explicitly
  commits WP9 to it.
- **`FIVE_QI_LCG` as a swept mapping — excluded.** It is
  `[OPEN: HARDWARE/DECISION]`: invented, with nothing to validate it against.
  H5 is reached instead through an **explicit per-flow `lcg` override** in
  B4's builder — a declared scenario-author choice, not a claim about the
  default table. The open item **stays open**: WP9 routes around it rather
  than pretending to settle it, and H5's result is reported as conditional on
  the override.
- **SPS / Configured Grant — not an axis.** Absent from both arms by design
  (CLAUDE.md). WP9 can *motivate* CG as the next feature ask if H7 holds
  (Test Plan §10's own forward-look), never test it.
- **Correlated multi-UE blockage and mobility — excluded**, per WP6
  Decision 7's standing disposition, unrevisited.

---

## 4. Decision 2 — Arms

**Three arms, paired on identical seeds**:
`ProportionalFair(ewma_window_slots=200)`, `Reservation()`,
`TwoTier(min_rb=…)`.

- **PF is the baseline arm**, corresponding to the hardware campaign's
  "original scheduler" attribution arm (Test Plan §4.3).
- **RoundRobin is excluded** — it answers no G-row and no hypothesis, and
  would cost +33 % of the entire compute budget.

### Two standing PF confounds, printed on every PF-involving claim

Otherwise the sweep will "discover" them as regimes:

1. **`pf.py::_r_avg` is one EWMA per UE, shared across that UE's UL and DL
   flows** — a UL-only axis step moves PF's DL numbers (CLAUDE.md invariant,
   confirmed causally in WP4).
2. **PF's identical-score tie-break is flow-declaration order**
   (`[OPEN: DECISION]`, README §8), producing persistent starvation for a
   fixed UE subset under SR-gated eligibility. **M09 (per-second Jain) on the
   PF arm is contaminated by this.** A fairness "regime" found against PF must
   be re-checked on Reservation-vs-TwoTier directly before it is claimed.

### The floor-ON / floor-OFF TwoTier pair — excluded now, revisit-if

There is no floor-disable knob: the ported `TwoTier.__init__` takes exactly
one kwarg, `min_rb` (`scheduler/scheduler_config.yaml` records this as
settled, not provisional). Ground truth's own floor-OFF arm is a compile flag,
`-DIA_P5G_UL_FLOOR_ENABLE=0`, which is what GT-2.2 uses for attribution.

**Decision: no floor arm in WP9.** It would be bit-identical to floor-ON
anyway, because the floor cannot fire on this corpus for **two independent
reasons, and the revisit condition is their conjunction, not either half**:

> **Revisit condition: a BSR/SR-desync fault model AND `mfbr_bps > 0`.**
> The fault alone is not sufficient — `_ul_has_pending_gbr`'s own MFBR gate
> means the floor fails to arm with `mfbr_bps` at its `0.0` default even when
> the desync it exists to catch is present. `mfbr_bps > 0` alone is not
> sufficient either — with no fault there is nothing to rescue. Both, or
> neither.

**Stated in GT-2.2's own terms, for the hardware campaign to read directly:**

> GT-2.2's floor-OFF arm has no simulation counterpart. The v2.1
> service-interval floor — the mechanism most specific to two-tier's design,
> born from the documented 2026-08-04 production incident
> (`ia_p5g_scheduler.c:555-644`) — is **never exercised anywhere in WP9's
> regime map**. Any WP9 statement about two-tier's liveness behaviour under a
> neighbour's flood describes two-tier **with its signature starvation guard
> inert**. GT-2.2 and GT-2.3 on hardware remain the only test of that failure
> mode, and the floor-OFF delta they measure has **no sim prediction to check
> it against**. WP9 cannot tell the campaign whether that delta will be large
> or small; it can only confirm that the guard is not what produced any effect
> WP9 does report.

---

## 5. Decision 3 — The G1–G12 bridge table

Three categories, following the hardware plan's own environment-honesty
discipline (Test Plan §4.5). **This table is the bridge artefact between WP9
and the hardware campaign** and is filled in for real at commit 4.

### (a) Sim-answerable — a cell and a metric

| G | Sweep cell | Metric(s) | Notes |
|---|---|---|---|
| **G1** | core plane, all cells; PDB excursion | M01 p98 (worst flow), M15 | Ordering/relative claims only; the millisecond is not certifiable (`SIM→RF`) |
| **G3** | core plane + `sr_period` excursion | M03, M14 | Reported as a function of `t_live_s` ∈ {1,2,4}; never at one assumed value |
| **G4** | duty-cycle excursion (silence buckets) | M01 over the post-silence message subset, read from WP7's message ledger | **A study-layer read, not a panel metric.** No M20 is added; the panel stays exactly as pre-registered |
| **G5** | mix levels containing `xr_video` | M05, M06, M17 | |
| **G6** | bg on/off excursion | Δ on M01/M03/M05, ≤ +20 % relative | The G6 delta-statistic exactly as GT-4.1 defines it |
| **G8** | core plane | M09 (per-second Jain) | **PF arm contaminated** (§4); Reservation-vs-TwoTier is the trustworthy pair |
| **G10** | the N axis | M07, M08 all-pass at 5/5 seeds → admissible N | **This is what simulation buys that hardware cannot** — the headline deliverable |
| **G12** | the load column, per N row | **M13** via `first_violation_order()` | Requires the ordered-run study-layer call (B6) |

### (b) Sim-informative, not certifiable

| G | What sim gives | What it cannot give |
|---|---|---|
| **G2** | Ordering, regression detection, a demonstrated bound at the *simulated* trial count | The certifiable 100 ms bound — Test Plan tags GT-1.2 **RF** |
| **G9** | Real M18/M19 numbers for warm/cold/reestablish paths across a GT-6.1-style 50-cycle campaign (§6) | A **ratified** verdict: blocked on `T_live` (`[OPEN: HARDWARE]`) and the plan's own ▷-marked provisional thresholds |
| **G11** *(3 seeds, no CI — see the inline-qualifier rule below)* | One soak cell with GT-7.1's actual KPI — monotonic drift in internals, a within-run check. Three runs reported individually | A shift-length claim (30 min sim ≠ 60 min RF), and **no cross-seed claim of any kind**: n=3 supports no bootstrap CI |
| **G1/G5 absolute ms** | Shape, crossover, ordering | Certifiable latency — the rfsim OWD floor and real RF are both outside this model |

**A simulator limitation found building the runner, and what it costs
M16.** `sim/run_record.py::flow_key` keys a flow by `(ue_id, qfi)` with **no
direction term**, so a UL and a DL flow sharing a 5QI collide and one
silently disappears from every metric. The hardware plan §1's T1/T2
construct — DL commands riding the UL telemetry bearer in reverse — is
therefore **not representable here**. Caught by measurement, not review: the
first base scenario configured 8 flows and reported 6.

Consequence, stated rather than worked around: WP9 models T2 as its own
5QI (82, delay-critical GBR — the same one `factory_robots` uses for its DL
control loop), so **M16's "shared-bearer correlation" is a correlation
between two bearers, not within one**. The UL/DL-degrade-together question
(G1/G2/G3's shared-bearer half, and `IA_P5G_Guarantee_Validation_Suite.md`
T2's "a robot both blind and unresponsive at once") is answered here only to
that approximation, and the G1/G2/G3 rows above carry it. Fixing it properly
means adding a direction term to flow keying, which touches `RunRecord`,
`Metrics`, every scenario and the frozen corpus — out of scope for WP9, and
its own commit if ever taken up.

**Inline-qualifier rule for G11 (and any other reduced-seed row).** Every G11
row — in this table, in commit 4's regime map, and in any roll-up derived from
either — **states its own seed count and "no CI" inline**, exactly the way the
rule-of-three rows state their own n. The surrounding table's default is 10
seeds with a bootstrap CI; a G11 row that silently inherits that default is a
row that will be quoted without its qualifier once §6 is no longer in front of
the reader. This is a formatting requirement on the deliverable, not a note in
the method section.

### (c) Not answerable in simulation

| G | Why |
|---|---|
| **G7** (one misbehaving UE contained) | **There is no MFBR enforcement anywhere in `sim/`.** `grep mfbr_bps` hits only `scheduler/` (deficit-spread caps); `sim/config_loader.py:16` states it directly — "no rate-cap enforcement". `FlowConfig.aggressor_multiplier` can offer 2× MFBR, so sim can show **containment** (asset A unaffected) but **not clipping** (B's excess clipped at MFBR), which is half of G7's pass criterion. GT-4.3 is the only test of the clamp path. |
| **G2/G3 pass lines** | `T_live` is unmeasured (`[OPEN: HARDWARE]`); no MEC liveness loop exists to model |
| **The GT-0 class** | The 5QI-4 N6 blackhole is a gNB SDAP/GTP-U or UPF PDR/FAR fault — no model, and none in scope |
| **The whole GT-2 failure class** | No BSR/SR-desync fault model (§4; §7's commit 0b) |
| **G10 mixed-fleet (UGV+UAV) / T9** | RTSP/TCP UL↔DL coupling deliberately unbuilt (`[OPEN: DECISION]`, WP7 Decision #2) |

---

## 6. Decisions 4 and 5 — Open threads, scoring, and the run-count arithmetic

### 6.1 Decision 4 — the four open threads as falsifiable expectations

Each states its expectation **and its falsifier**, before running, and is
scored afterwards — hits and misses both, per the standing rule.

**D4-1 — Study 2's bimodal per-UE p99 (Reservation, `sensor_dense`).**
*Expectation:* it is follower-budget saturation. Bimodality should
**strengthen monotonically as `n_followers_need × min_rb` approaches and
exceeds `prb_count`**, and **collapse at `min_rb=1`** (where the budget ≈
`bwpSize` for every tested N). Measured as: per-UE p99 delta vs PF, cluster
gap divided by within-cluster sd, as a function of (N, `min_rb`).
*Falsifier:* bimodality persists essentially unchanged at `min_rb=1`, or
appears at (N, `min_rb`) products far below `prb_count`. Either falsifies the
one named candidate mechanism, and the thread stays open with a narrowed
suspect list rather than a closed one.

**D4-2 — UL PRB utilization falls as offered load rises (TwoTier).**
*Expectation, and the order of tests matters:* the original four data points
(0.617 → 0.432 across `study1` mult2.0→3.0) were taken on the **capacity**
axis, which §3 excludes as a load axis. **Step one is therefore to reproduce
the shape on the real load axis at all.** If it does not reproduce, the
finding was a capacity-scaling artifact — which is itself the answer, and a
cheap one. If it does reproduce, the expectation is that the mechanism is
`B_eff`'s frozen-per-LCG sum exceeding the BSR-independent-draining scalar
(confirmed live through a scheduler path at two-tier commit 4b), so it should
be **TwoTier-only** and should **weaken as `sr_period_slots` shortens** (more
frequent BSR refresh ⇒ less freeze time).
*Falsifier:* Reservation shows the same fall (⇒ not `B_eff` — it is the load
axis or the traffic model); or the shape is insensitive to `sr_period_slots`.

**D4-3 — The follower-budget regime boundary.**
*Expectation, quantitative and sharp, from §1.1:* Reservation degrades
relative to PF above `N_crit = min(55/min_rb, 8)`. Because the PDCCH bound (8)
binds first at the deployed `min_rb=5`, **`min_rb` should have no effect on
the boundary below `min_rb ≈ 7`, and should move it below 8 only above that.**
*Falsifier:* the boundary moves with `min_rb` anywhere in the 1–6 range (⇒ the
follower budget binds by a route the formula does not capture); or no boundary
appears anywhere in N ≤ 32 (⇒ H1 refuted on this RAN, and the map says so).
Either outcome answers H1's own "which bound binds is itself a result."

**D4-4 — Can any cell distinguish the schedulers where the hardware's N=2
could not? (the project's founding question).**
*Expectation, amended pre-stage-1 (see below):* **Yes at N ≥ 8** on M07/M08,
and — equally load-bearing — **No at N=2 on any primary metric.**

**Amendment, made BEFORE stage 1 ran and prompted by §1.2's base-point
re-derivation, not by sweep output.** The re-derivation put the base cell at
N=8, and its single-seed observation there already shows GBR contracts
8/8, 7/8, 5/8 — separation on M07, the exact metric this expectation names,
at the exact N it names. That is *consistent* with the expectation as
written, but it means the base point probably sits **inside** the regime
rather than below it, and the original wording anticipates only one of two
genuinely different findings. The interesting question moves from "does
separation appear by N=8" to "**where below 8 does it start**".

So the expectation is resolved one level finer, on the levels the N axis
already carries (2, 4, 8 — unchanged):

- **N=8: separation expected**, on M07/M08. Effectively already indicated;
  the gate's job here is to confirm it survives 10 paired seeds with a CI
  excluding 0, not to discover it.
- **N=4: genuinely open, and this is now the informative cell.** §1.1 puts
  the PDCCH bound at 8 and the follower-budget bound at 11, so N=4 is below
  both. Separation at N=4 would mean the arms diverge for a reason those two
  bounds do not explain — a finding about the ranking policies themselves
  rather than about a capacity boundary. No separation at N=4, with
  separation at N=8, would place the boundary in (4, 8] and put it near the
  predicted PDCCH bound, corroborating §1.1.
- **N=2: no separation expected** — unchanged, and still the positive
  control and stop condition below.

**A boundary between 4 and 8 and a boundary below 4 are different findings,
and both are now anticipated in writing rather than one of them being
explained after the fact.**

*Unchanged by this amendment, deliberately:* the falsifier below, the five
primary metrics, the §6.4 gate, and the N=2 stop condition. Only the
expectation's resolution moved, and only before any stage-1 cell executed —
the commit that made this change predates the commit that runs stage 1, which
is what makes that claim checkable rather than asserted.

**The N=2 cell is a positive control on the whole sweep design, and a stop
condition — not a data point and not a caveat.** The hardware measurement's
own author settled that the schedulers do not differentiate at N=2. If this
sweep separates them there, the *simulator* disagrees with the one hardware
fact available, and **stage 2 does not start** (§8). What happens instead is
an investigation of why, routed through §6.4's pause path as its own work —
not a paragraph appended to a sweep that ran anyway. **This is the dangerous
direction and is read first, before anything else in stage 1's output.**
*Falsifier of the positive half:* no cell separates the arms anywhere, on any
primary metric, with `is_informative` satisfied. That is the **publishable
negative result** — stronger than the N=2 tie precisely because the exclusion
rule proves the grid reached real loss — and it is reported as the finding.

### 6.2 Decision 5 — scoring and validity

- **All 19 metrics, every run, no cherry-picking.** 17 via
  `Scorecard.score()`; M13 and M16 via the study layer (B6). `pending` rows
  are emitted with a reason, never omitted.
- **`config/metric_panel.yml` is not edited by WP9.** Nothing added, removed
  or redefined. G4's post-silence read is a study-layer computation, not a new
  metric.
- **10 paired seeds per cell** (`regime_sweep.paired_seeds`), identical across
  all three arms — the comparison is within-seed, never between independently
  sampled runs.
- **`is_informative` gate, applied before any effect-size test.**
  `regime_selection_excluded(loss_PF, loss_arm)` with loss = M02
  (`pdb_violation_rate`). A cell with zero loss on both arms carries no
  information and is dropped from the map.
- **Worst asset, never the mean** (Test Plan §4.2) wherever the panel offers
  both: M01 worst flow, M08 (a min over GBR flows by definition), M05/M06/M17
  worst flow. M10/M11/M12 are aggregate by definition and are reported as
  context, never as pass/fail.
- **Rule of three, per cell, never pooled across cells.** Pooled n =
  10 seeds × (flows of that role) × (messages per flow per run). At N=8
  telemetry over a 5 s horizon: 10 × 8 × 50 = 4,000 ⇒ a zero-miss claim of
  **≤ 7.5 × 10⁻⁴**. At N=2: 10 × 2 × 50 = 1,000 ⇒ only **≤ 3 × 10⁻³**.
  **Low-N cells therefore carry weaker claims than high-N cells**, and every
  bound-stating row carries its own n and its own bound — never a tighter one.

### 6.3a AMENDMENT — the arithmetic below was wrong by 5-7x (measured)

**§6.3's table is superseded.** It produced a 1.27 h stage-1 projection;
the real run reached 756 of ~1,680 records before dying, and re-measured
post-fix (`6b31af3`, on a machine with no swap pressure) the true costs are:

| N | driver.run (PF/Res/TT) | score (19 metrics) | 12 variations | **cell (3 arms x 10 seeds)** | §6.3 predicted |
|---|---|---|---|---|---|
| 2 | 1.10 / 1.34 / 3.41 s | 0.06 s | 0.66-0.72 s | **81 s** | — |
| 8 | 3.63 / 5.74 / 10.88 s | 0.25 s | ~3.1 s | **303 s** | ~62 s (**4.9x low**) |
| 32 | 16.82 / 22.39 / 27.18 s | ~1.1 s | ~13 s | **1093 s** | ~150 s (**7.3x low**) |

Corroboration that these are sound and that the dead run's early data was
clean: the pre-thrash rate measured during the first (N=2) cells was
0.367 rec/s ⇒ **~82 s/cell**, against **81 s/cell** measured here.

**Stage 1, re-derived: ~7.1 h serial** (core plane ~5.9 h interpolating
N=4/16/24 between the measured points, plus ~1.2 h for the 14 excursion
cells at the N=8 base) — **against its own 4 h ceiling**. Stage 1 was never
going to fit serially, leak or no leak.

#### How this was measured — and how the original failed

Recorded as a category, because any future budget in this project will be
built the same way unless the failure mode is written down. Three causes,
all of which generalise:

1. **Measured at one horizon, scaled linearly to another.** The original
   timings were taken at horizon 4,000 and multiplied by 5 for 20,000.
   Allocation and GC cost do not scale with the slot loop; at N=8 TwoTier
   the real 20,000-slot run is 10.88 s against the ~3.6 s that scaling
   predicted.
2. **Measured with a flag off that the real run has on.**
   `record_timeseries=True` was checked once, on one scenario at horizon
   4,000, and recorded in §1 as "measured free: 1.39 s vs 1.58 s". At the
   real horizon with up to 32 flows the arrays are 5x longer and there are
   4x more of them, and it is not free.
3. **A cost model that counted `driver.run()` and nothing else.** Scoring
   was omitted entirely — yet `Scorecard.score()` runs **13 times per
   record** (once for the panel, plus 12 scoring-parameter variations), and
   at N=8 that is 3.4 s against the run's 10.9 s, i.e. ~24% of per-record
   cost. `sim/tests/test_wp9_sweep_memory.py` pins the variation count at 12
   so this term cannot drift silently and invalidate the budget again.

**The rule this leaves behind: time the thing you are actually going to
run — same horizon, same flags, same post-processing — or state explicitly
that the number is a lower bound.**

### 6.3 The run-count arithmetic (SUPERSEDED by §6.3a — kept for the record)

Measured on this machine, `record_timeseries=True`, at 20,000 slots (cost is
linear in slots and near-linear in N, both measured, not assumed):

| N | TwoTier | Reservation | PF | 3 arms × 10 seeds |
|---|---|---|---|---|
| 8–10 | ~3.6 s | ~1.3 s | ~1.25 s | **~62 s / cell** |
| 32 | ~7.5 s | ~3.8 s | ~3.5 s | **~150 s / cell** |

- **Stage 1: 50 cells ≈ 1.3 h single-core** — inside the ≤ 4 h ceiling with
  room for a full re-run after a fix.
- **Stage 2: ≤ 3 axes, ~256 cells ≈ 7 h** — inside the ≤ 24 h ceiling, leaving
  budget for both sub-campaigns below. **SUPERSEDED: at §6.3a's measured
  costs this is ~35-55 h serial, far outside 24 h — see §6.3b.**
- Cells are embarrassingly parallel; `multiprocessing` (stdlib, no new
  dependency) over cells gives roughly N-core headroom. **Every budget above
  is stated single-core**, so the plan does not depend on that headroom
  existing.
- **G9 sub-campaign** (GT-6.1's 50 cycles and GT-6.2's 10, deferred to WP9 by
  README §5): 50 join cycles ≈ 400 k slots ≈ 2.4 min/run × 3 arms × 10 seeds
  ≈ **72 min**. Fits.
- **G11 soak — the one place the standing 10-seed rule is broken,
  deliberately.** 30 min of sim time is 7.2 M slots ≈ 43 min/run; 3 arms × 10
  seeds = **21 h**, which does not fit alongside stage 2. **Deviation, with
  its consequence stated:** the soak runs **3 seeds, not 10** (3 arms × 3
  seeds ≈ 6.5 h); no bootstrap CI is reported; the three runs are reported
  individually. Defensible *only* because GT-7.1's actual KPI is monotonic
  drift in internals — a within-run check — not a cross-seed mean. **Any
  cross-seed claim from the soak is out of bounds**, and the qualifier travels
  with the number per §5's inline-qualifier rule, not with this section.

### 6.3b Stage 2's budget, re-derived — parallelism is a precondition

§6.3's ≤24 h stage-2 ceiling was computed from the same superseded table, so
it is void. At §6.3a's measured costs, ~256 cells at an average around
500 s/cell is **~35 h serial, and up to ~55 h** if the surviving subgrid
skews toward high N. Stage 1 is ~7.1 h serial against a 4 h ceiling.

**So parallelism is a precondition for either stage fitting its budget at
all, not an optimisation**, and §6.3's "every budget above is stated
single-core so the plan does not depend on that headroom existing" no longer
holds — the plan now does depend on it.

This machine has **24 cores and 30 GB RAM**, and memory is the binding
constraint rather than CPU: each worker holds one record in flight
(~33 MB at N=32) plus its own simulator state. At **12 workers** — chosen to
leave headroom rather than saturate — stage 1 is **~35 min** and stage 2
**~3 h**, both comfortably inside their ceilings. The worker count is set
from measured per-worker RSS at the largest N, not assumed.

Cells are independent, so parallelising over cells changes no result: within
a cell, seeds and arms stay ordered, `paired_seeds` is drawn up front, and
every run is a pure function of `(scenario, seed)`.

### 6.4a AMENDMENT — the tie, the cap, and what stage 2's result is worth

Written **before any stage-2 cell runs**, prompted by stage 1's verdict.

**What stage 1 actually showed about its own rule.** **11 of 12 axes cleared
the bar** at the pre-registered threshold of 1.0. The threshold therefore did
not discriminate in practice — nearly everything separates the arms
*somewhere*, on *some* primary metric, once ten paired seeds make small
differences significant. Reported per rule 7, **not re-cut**. The consequence
is structural: with almost every axis qualifying, **the "at most one
excursion" cap was doing all of the narrowing, not the score.**

**And at the top, the ranking was not a ranking.** `shared_lcg` and
`k2_slots` both scored `inf` (a perfectly consistent `M07.met` difference,
`sd=0` across ten seeds). `shared_lcg` won solely because it appears earlier
in the `EXCURSIONS` dict literal. Dict insertion order is not a selection
criterion, and stage 2's entire excursion axis rested on it.

**Resolution: both tied axes are promoted, and the cap is RECOMPUTED, not
relaxed.** Rule 3's cap was never a primitive — its stated justification is
the compute ceiling, and the ceiling it was derived from came from §6.3's
timing table, which §6.3a superseded as wrong by 5-7x. Recomputing it against
measured cost is the same correction, applied to the same stale source:

| stage 2 grid | cells | serial | wall @10 workers | ceiling |
|---|---|---|---|---|
| `shared_lcg` only | 84 | 11.8 h | 1.7 h | 24 h |
| `k2_slots` only | 126 | 17.7 h | 2.6 h | 24 h |
| **both** | **252** | **35.3 h** | **5.2 h** | **24 h** |

(Serial costs from §6.3a's measured per-cell figures; the 6.75x effective
speedup is stage 1's own measured wall time — 7.32 h serial-equivalent
completed in ~65 min on 10 workers — not an assumed efficiency.)

So the cap is **not binding** and the tie dissolves rather than being broken.
Stage 2 is `n_ues`(6) x `load_mult`(7) x `shared_lcg`(2) x `k2_slots`(3) =
**252 cells**.

**Tie rule, stated now so it is not invented next time:** *all axes tied at
the maximum score are promoted, provided the recomputed budget admits them;
if it does not, fall back to a stated substantive criterion — prior
expectation, preferring an axis with a pre-registered hypothesis and a named
mechanism (`shared_lcg` is H5) over a sensitivity sweep (`k2_slots`).*

**The honesty risk in this, named rather than left implicit.** Recomputing a
budget cap *after* seeing which axes tied can look like motivated reasoning.
Two things bound it: the recomputation is driven by stage 1's measured wall
time, which is independent of which axes tied and would have produced the
same number whatever they were; and the outcome **removes** an arbitrary
choice rather than making one. Had the budget not admitted both, the
fallback above — not a re-derived cap — is what would have applied.

**What this means for reading stage 2, which the plan previously did not
account for.** A confirmatory result on an axis selected by a *cap* rather
than by a discriminating *score* is weaker evidence than §6.4 assumed. Stage
2 confirms that a difference reproduces on a denser grid with contiguity; it
does **not** establish that the promoted axes were the most important ones,
because the selection step did not rank them credibly. Any stage-2 claim
must carry that qualifier, and the eight dropped axes (§6.4's own record,
with scores) remain live candidates rather than tested-and-rejected ones.

### 6.4 The stage-1 → stage-2 go/no-go rule

**Pre-registered, implemented as code (B5), and committed before stage 1
runs.** Stage 1 is exploratory; stage 2 is confirmatory; this rule is what
keeps that distinction honest, and it is frozen before the first cell
executes.

1. **Primary metrics — five, declared now:** M07, M08, M01 (p98, worst flow),
   M02, M09. Chosen because they map onto G10 / G8 / G1 / G12, the guarantees
   the map exists to serve. All 19 are still scored and written; these five
   only gate promotion.
2. **Gate, per axis.** The axis qualifies if, at **at least one level**, on
   **at least one primary metric**, all three hold:
   (i) the cell passes `is_informative`;
   (ii) the paired within-seed effect size `|mean Δ| / sd(Δ)` **≥ 1.0** across
   the 10 seeds (Δ = arm − arm, per seed);
   (iii) `bootstrap_ci(Δ)`'s 95 % interval **excludes 0**.
3. **At most three axes carry into stage 2** — the core plane's N × load plus
   at most one excursion axis — so stage 2's factorial stays inside 24 h. If
   more than one excursion axis qualifies, rank by `|mean Δ| / sd(Δ)` and take
   the top one; **the dropped axes are recorded by name and score**, never
   silently omitted.
4. **No claim is made from stage 1.** With 5 primaries × 10 axes × ~2 levels
   ≈ 100 tests, stage 1's job is selection only. Every reported regime claim
   comes from stage 2.
5. **Stage 2 requires contiguity.** `check_contiguity` needs grid-adjacent
   cells; stage 1's one-axis-at-a-time excursions structurally cannot supply
   them, so a regime-boundary claim from stage 1 is **impossible by
   construction**, not merely discouraged. A stage-2 cell whose winner has no
   agreeing neighbour is flagged isolated and is not a boundary.
6. **Stage 2 must confirm on the same primary metric that selected the axis.**
   A different metric separating in stage 2 is a new hypothesis for a future
   sweep, not a confirmation of this one.
7. **If zero axes qualify**, that is D4-4's negative result and it is reported
   as the finding. **The rule is not re-cut to manufacture a qualifier** — no
   sixth primary metric, no relaxed threshold, no extended axis list. This is
   the entire reason the rule is code, committed before stage 1: it will be
   harder to honour at hour four than it is now, and §6.4(3)'s
   "dropped axes recorded by name and score" is what makes a quiet relaxation
   visible as a diff rather than a judgement call.

---

## 7. Decision 6 — corpus discipline in a sweep phase

- **`regression/baseline_studies_1_3.json` stays frozen at `a5f6baa`.**
  `--check` is run and confirmed clean **before stage 1 and again before
  stage 2**. No `--capture` happens anywhere in WP9 except as part of a
  paused-and-fixed scheduler commit's own explicit re-baseline decision.
- **Sweep outputs live outside the corpus**, under `sweeps/wp9/`. Scored CSVs
  and aggregates are committed; raw per-cell RunRecord JSONL is committed only
  if a stage's total stays under ~50 MB — **measured at stage 1's first cell,
  not guessed** — and otherwise stays local with the exact re-run command
  recorded so it remains reproducible.
- **If the sweep surfaces a scheduler bug, the sweep pauses.** It does not
  absorb the fix. The fix is its own commit with the full Phase 2 discipline:
  a falsifiable prediction of which `--check` records move and how, a
  `docs/oai-port-map.md` row correction citing the C, `--check` run and
  **scored — hits and misses both**, and an explicit re-baseline decision
  stated in the commit message.
- **Any stage already run against the pre-fix code is invalidated for the
  affected arm and re-run.** Results are never merged across a fidelity
  change — that is exactly the attribution the one-fidelity-change-per-commit
  rule exists to protect, and a half-old/half-new sweep would destroy it
  silently.
- **The same pause path carries D4-4's stop condition** (§6.1): an N=2
  separation is a fidelity finding about the simulator, handled as its own
  investigation commit, not as an annotation on a sweep that continued.
- **Commit 0b (§8) is read-only** and produces no code, so it cannot
  invalidate anything.

---

## 8. Commit checklist

| # | Commit | Predicted `--check` movement | Outcome |
|---|---|---|---|
| 0 | `Reservation` `min_rb` plumbing (B1) | **None** — `OK — no drift` | **Landed. Prediction HIT**, on the stated grounds: `OK -- no drift`, 516 passed (3 new). Verified both directions — the corpus path is byte-identical, *and* `Reservation(min_rb=20)` through the driver now produces genuinely different output, so the fix does something rather than only being accepted. **One real trap found, not hypothetical**: `configure()`'s fallback must test `is None`, not truthiness — `test_reservation.py`'s two follower-budget fixtures pass `min_rb=0` deliberately, and the truthiness variant was written and run, failing 3 tests. `docs/oai-port-map.md` row 78. |
| 0b | BSR-desync fault-model feasibility check (read-only, no code) | n/a — no code | **Landed. Result NEGATIVE** — quantisation ruled out empirically, short-BSR aliasing ruled out structurally (format keyed to active-LCG count, not grant size — the truncated-BSR route is unmodeled), frozen-array route real but bounded by three independent re-arming paths. §8a for the full trace and the two named candidate mechanisms. |
| — | **PAUSED (D6): arm-divergence investigation** | n/a — docs only | **Landed. Answer: DEFECT, in `sim/ul_access.py`, not either scheduler.** §8b. |
| 1 | Sweep infrastructure (B2–B6), incl. the §6.4 rule as code | **None** — no `sim/`/`scheduler/` behaviour touched | Blocked on §8c's fix |
| 2 | Stage 1 (screening), ≤ 4 h; **N=2 control read first** | n/a | |
| 3 | Stage 2 (confirmatory), ≤ 24 h; + G9 cycles, G11 soak (3 seeds) | n/a | |
| 4 | The regime map + §5's bridge table filled in; D4-1…D4-4 scored | n/a | |

**Commit 0 — the real pre-sweep commit.** The only scheduler-file change in
WP9, and it takes full Phase 2 discipline. `Reservation.__init__(min_rb: int =
5)`, and `configure`'s `min_rb` parameter defaults to the constructor's value
rather than a hardcoded 5, so a constructor-time choice survives
`driver.py:157`'s three-positional-argument call.
*Falsifiable prediction, stated before running:* **completely inert**,
`--check` reports `OK — no drift`. Grounds: the default stays 5, and nothing
in the corpus (`scripts/regression_corpus.py`, `scripts/scheduler_study.py`)
constructs `Reservation` with a non-default `min_rb` — **verified by grep
before landing, not assumed**. Full suite plus `--check`; the prediction is
scored either way. A port-map row cites `nrmac->min_grant_prb` and records
that this is plumbing, not a behaviour change. **No sweep cell executes before
this lands and `--check` is clean.**

**Commit 0b — BSR-desync fault-model feasibility check (read-only).**
Deliverable: the answer to README §7's open question — *can `sim/bsr.py`'s
existing quantisation / loss / aliasing model express
`estimated_ul_buffer_per_lcg == 0` while true backlog stays non-zero, at all?*
The mechanism is traced either way; nothing is built.

**The write-up must state which of two distinguishable things it
establishes** — the same discipline two-tier commit 4's `has_pending_gbr`
finding had to observe (README §7: *"this establishes only that the port
matches ground truth, NOT that real hardware has the gap"*). The two claims:

- **(i) This simulator cannot produce the fault** — a fact about
  `sim/bsr.py`'s **expressive range**. This is what a negative result means.
- **(ii) The fault is unreachable in principle, or hardware does not have
  it** — **not** what a negative result means, and **contradicted by evidence
  already on record**: the hardware campaign observed this failure mode, and
  it is what produced the UL floor in the first place (the documented
  2026-08-04 production incident, `ia_p5g_scheduler.c:555-644`).

So if the answer is negative, the sentence this commit commits to is:
**"`sim/bsr.py` lacks a mechanism that would produce this state; the fault is
real on hardware and outside this model's expressive range."** The future
fault-model WP is then scoped as **"add a mechanism `sim/bsr.py` does not
have"**, not **"enable a path it already has"** — a materially larger WP, and
that sentence is what a later reader will size it from. If the answer is
positive, the write-up names the exact parameter combination that produces the
state, and the scope flips to the smaller shape.

Either way the standing consequence is stated plainly here and in §4's GT-2.2
wording: **WP9's map does not exercise two-tier's signature mechanism, and
GT-2 on hardware remains the only test of that failure mode.**

---

## 8a. Commit 0b — the BSR-desync feasibility check (result)

**Read-only. No code was written. Result: NEGATIVE — and §8's discipline
about which of two things that establishes is applied below, not assumed.**

**Question** (README §7's own open item): can `sim/bsr.py`'s existing
quantisation / aliasing / event-triggering model express
`estimated_ul_buffer_per_lcg[L] == 0` while the true backlog on LCG `L`
stays non-zero — the BSR/SR desync the UL service-interval floor exists to
rescue?

### The three candidate routes, checked individually

**Route A — quantisation. Ruled out, empirically rather than by reading.**
`_locate_bsr_index` returns index 0 only for `true_bytes == 0` (a
`bisect_left` on a table whose first entry is 0), and `_overestim_index`
only ever increases an index. Checked directly across every backlog in
1..20,000 against both transcribed tables: **zero cases** map to a 0
estimate. `quantise_short(1) = 14`, `quantise_long(1) = 11`. Quantisation
structurally cannot zero a live backlog.

**Route B — short-BSR aliasing (the `[0] * LCG_COUNT` memset). Ruled out,
and this is the load-bearing finding.** The memset genuinely does leave
every unreported LCG at 0. But the format is selected by
**`len(active_lcgs) == 1`** (`sim/bsr.py`, `on_ul_grant`) — the short form
is used *exactly when only one LCG has any backlog at all*, so every entry
it zeroes belongs to a genuinely empty LCG. **The real-hardware route to
this state is a *truncated* BSR** — several LCGs hold data, the grant is too
small to carry a Long BSR, so only a prefix of them is reported and the rest
stay zero with live backlog. **That mechanism is not modeled**: format
selection here reads the active-LCG count and **never the grant size**.
`Truncated` appears in this module only inside two docstrings noting that
the tables are shared with the truncated formats — there is no selection
branch for them.

**Route C — the frozen array between BSRs. Real, but bounded, and that is
the whole difference.** The array genuinely is stale between reports, so an
arrival onto an LCG that was empty at the last BSR *does* produce
`entry == 0` with live backlog. But its duration is bounded by three
independent re-arming paths, any one of which closes it:
1. that same arrival sets `pending` (the regular trigger's
   previously-empty-LCG condition, `on_arrivals`);
2. `tick_timers` re-arms `pending` every slot past the periodic (5 ms) or
   retx (80 ms) deadline, idempotently;
3. `on_ul_grant` assembles the report on **any** grant once `pending` is set
   — a `min_rb` crumb does it as well as a full grant.
And the grant those paths need is supplied by `sim/ul_access.py`'s SR path,
which models SR *timing* (prohibit timer, `sr-TransMax`, RACH-fallback
timing) but **no SR loss** — the request is always eventually delivered.

### What this establishes, and what it does not

- **(i) It establishes that THIS SIMULATOR cannot produce the fault** — a
  fact about `sim/bsr.py`'s **expressive range**. The state is reachable but
  only transiently; the model contains no mechanism whose *duration* is
  unbounded, and the persistent desync the floor exists for (the incident's
  own "zero grants for 55 s") has no route here.
- **(ii) It does NOT establish that the fault is unreachable in principle,
  or that hardware does not have it.** That reading is contradicted by
  evidence already on record: the hardware campaign observed this failure
  mode, and it is what produced the UL floor in the first place
  (`ia_p5g_scheduler.c:555-644`, the documented 2026-08-04 incident).

**The sentence this commit commits to:** *`sim/bsr.py` lacks a mechanism
that would produce this state; the fault is real on hardware and outside
this model's expressive range.*

> **SUPERSEDED IN ITS SECOND HALF by §19.5 — read this before scoping from
> 0b's framing.** The mechanism 0b named (grant-size-keyed truncated-BSR
> format selection) has since been **built, correctly wired to the Padding
> BSR trigger, and unit-tested — and it still cannot fire.** So "`sim/bsr.py`
> lacks a mechanism" was true but pointed one layer too high: adding it
> there was necessary and not sufficient. The blocker is **continuous grant
> sizing**, not the BSR model. TB sizes here track demand continuously, so
> padding is bimodal — exactly 0 on 28,580 of 28,580 grants in a saturated
> run, or large (42-235 bytes) in a light one — and never the 2-5 bytes a
> truncated format needs. **38.321's truncated formats exist to handle a
> TB-size quantisation artifact this simulator does not model.** A later
> reader scoping from 0b alone would rebuild what §18/§19 already built;
> the work that remains is in `sim/resource.py` / `scheduler/link.py`.

### Consequence for scoping the future fault-model WP

That WP is **"add a mechanism `sim/bsr.py` does not have"**, not **"enable a
path it already has"** — the materially larger of the two shapes. This check
also names the two candidate mechanisms concretely, which is the part a
later reader can size work from:

1. **Grant-size-keyed truncated-BSR format selection** (TS 38.321's Short
   Truncated / Long Truncated). The closest to ground truth, and the
   cheapest in one respect — the quantisation tables are already
   transcribed and byte-checked. It needs the *grant size* threaded into
   the BSR-assembly decision, which today reads only the active-LCG count.
2. **SR loss / PUCCH failure**, suppressing Route C's bounding path so the
   transient state can persist. Independently motivated: GT-2.3 is tagged
   **RF-essential** precisely because "SR fragility does not manifest in
   rfsim" (Test Plan §7), so this is a known-real effect this branch models
   the timing of but not the failure of.

Either mechanism, plus `mfbr_bps > 0`, is what §4's floor-arm revisit
condition requires — **the conjunction, not either half**.

**Standing consequence, unchanged:** WP9's regime map does not exercise
two-tier's signature mechanism, and GT-2 on hardware remains the only test
of that failure mode.

---

## 8b. Investigation — the arm divergence (D6 pause, no fix in this commit)

**Question:** is `PF > Reservation > TwoTier` on non-corpus workloads a real
scheduling property or a defect?

**Answer: a defect, in `sim/`, not in either scheduler.** Traced to a
confirmed mechanism by per-slot trace, not inferred from aggregates. **One
root cause explains both effects this investigation was scoped to keep
apart** — that is a finding in itself, since the scoping assumed two.

### The mechanism

`sim/ul_access.py::on_arrivals` (line ~165) gates the Scheduling Request on
an **empty→non-empty transition**:

```python
total_now = sum(... .bytes_queued for f in flows)
if total_now - arrived <= 0:
    st.pending = True
```

A UL flow whose backlog never returns to zero therefore **can never raise
another SR**. That matters because of what it interacts with: the
`sched_ul_bytes` crumb-collapse gate reports
`B = estimated_ul_buffer - sched_ul_bytes`, floored at 0. Once
`sched_ul_bytes` overruns the estimate — which the gate is *designed* to
allow — `bytes_reported` clamps to 0; and `sched_ul_bytes` is reset only
inside `BsrModel.on_ul_grant`, which needs a grant, which needs
`bytes_reported > 0`. The BSR's own re-arming works and is irrelevant:
`pending` is `True` from the periodic timer onward with nothing able to
consume it.

Per-slot trace, N=1, one deterministic UL flow, no contention (so all three
arms are byte-identical here):

| slot | bytes_queued | bytes_reported | per-LCG estim | estimated_ul_buffer | sched_ul_bytes | pending |
|---|---|---|---|---|---|---|
| 13 | 6280 | 1291 | 28581 | 14861 | 13570 | False |
| 14 | 4989 | **0** | 28581 | 13570 | 14861 | False |
| 21 | 4989 | **0** | 28581 | 13570 | 14861 | True |
| 799 | **184989** | **0** | 28581 | 13570 | 14861 | True |

The flow is permanently starved from slot 14 to the end of the run; backlog
grows to 184,989 bytes and never receives another grant.

**Ground truth is unambiguous that this is wrong.** TS 38.321 triggers an SR
on *a pending regular BSR with no UL grant available* — and retxBSR-Timer
expiry is itself a regular-BSR trigger. That is exactly the safety valve
this deadlock needs, and `BsrModel` already computes the state
(`pending=True`); nothing connects it to the SR path. `sim/ul_access.py`'s
own docstring records that it simplified away two per-LCID conditions from
`nr_update_sr` as a judgment call; **this is a third, unrecorded
divergence**, and unlike those two it is not conservative.

### Why both effects are one cause

- *Arm-independent low utilisation* (195 UL grants vs `factory_robots`' 3131
  at identical mean grant size): flows starve as soon as the overrun
  happens; only flows that keep emptying survive.
- *The arm ordering*: the arms differ only in **how fast their grant sizing
  drives `sched_ul_bytes` past the estimate**. TwoTier's deficit-accumulated
  `B_eff` sizes largest, overruns soonest, starves most — hence lowest
  utilisation. It was never a policy difference.

**Confirmed by worktree diagnostic**, not argued. Adding the TS 38.321
trigger as a throwaway patch (never committed; worktree removed):

| N | PF | Reservation | TwoTier |
|---|---|---|---|
| 8, as-is | 0.123 | 0.038 | 0.015 |
| 8, diagnostic | 0.928 | 0.924 | 0.934 |

The 8x spread collapses to under 1%, and **the ordering reverses** (TwoTier
becomes marginally highest) — a spread that inverts under a `sim/`-layer
patch was measuring the defect, not policy.

### Blast radius — this is not confined to WP9's new scenarios

`regression_corpus.py --check` under the diagnostic: **5,470 mismatches
across 15 of 20 records** — every UL-carrying study, all four arms.
(*Corrected: the corpus is 20 records, not the "22" README §9 and
CLAUDE.md carried; see §8c.*)
**96 flow-records move `delivery_ratio` by more than 0.5**, i.e. were
near-totally starved and become served. The sharpest single case:
`study2/pdcch_limited/TwoTier` UE9's UL flow, `delivery_ratio`
**0.0486 → 0.9994**, with that record's `ul_prb_utilization` 0.597 → 0.930.

**Hypothesis, flagged not asserted — D4-1 may be downstream of this.**
Study 2's unexplained bimodal per-UE p99 split ("roughly half the UEs
+7.5-9.5 ms worse, half unchanged-to-better") has the shape a
some-flows-permanently-starved mechanism produces. It survived the EWMA fix,
which ruled out coefficient staleness but not this. Not traced — D4-1 stays
open, and its expectation in §6.1 must be re-scored **after** the fix, not
before.

### Correction to commit 0b

0b's headline answer stands: the per-LCG array is **not** the route — it
reads 28,581 here, frozen, never 0. But **0b's boundedness reasoning was
wrong**, and the trace above is the counterexample. 0b claimed three
re-arming paths bound the state, the third being "assembly on any grant once
`pending` is set", and asserted `sim/ul_access.py` always eventually
supplies that grant. It does not — that is precisely the gap. The correct
statement: `bytes_reported` **can** stall at 0 over live backlog
indefinitely, via the `sched_ul_bytes` gate rather than via the per-LCG
array. 0b's answer to the question it was asked survives; its argument for
why does not.

### Consequence for §1's base point — revised, not quietly

**§1's base point does not survive as calibrated**, and this is a plan-doc
amendment with its reasoning stated, not a silent edit:

- Its **structure** survives: instruments at fixed profile rates, load
  carried by a best-effort filler (`sim/parametric.py::_BE_PER_UE_BPS`).
  That separation is right independently of this defect and matches how the
  hardware campaign splits GT-3.2 from GT-7.3.
- Its **calibration** is void. `_BE_PER_UE_BPS = 8 Mbps` and the load levels
  in §3 were picked against measurements taken under the defect, so they
  describe the starved regime. **They must be re-derived after the fix
  lands, and until then no cell in §3 is meaningful.**
- **Neither the fix nor the recalibration happens in this investigation
  commit.** The fix is a `sim/` fidelity change and takes the full
  discipline (§8c).

### What the fix commit must carry (not done here)

1. A falsifiable prediction of `--check` movement — and the honest one is
   *large*, ~5,470 mismatches, stated before running.
2. A citation to TS 38.321's SR trigger and `nr_ue_scheduler.c`'s
   `nr_update_sr`, plus a `docs/oai-port-map.md` row recording this as a
   third divergence in WP4's SR chain.
3. **A re-baseline decision, and it is not automatic.** The corpus is frozen
   at `a5f6baa`; this would be the first sanctioned re-capture since. It
   qualifies under CLAUDE.md's rule — the change is *intended* to move the
   numbers — but the published Study 1-3 figures in `README.md`/
   `docs/phase2-two-tier-delta.md` were produced under the defect, and the
   re-baseline must say so rather than silently replacing them.
4. A guard test reproducing the N=1 stall directly, verified to fail before
   the fix.

---

## 8c. The fix commit — prediction scored, re-baseline, corrections

**Landed.** `sim/ul_access.py::on_arrivals` gains TS 38.321 §5.4.4's real
trigger — a pending regular BSR with no UL-SCH resource available —
evaluated **every slot**, deliberately broader than §8b's worktree
diagnostic (which fired only on slots also carrying an arrival, enough to
prove the mechanism but not the spec condition: a flow that stalls then goes
quiet must still recover). Suite 519 passed (3 new tests, 1 existing fixture
corrected).

### Prediction, stated before running — two hits, one miss

| Prediction | Outcome |
|---|---|
| All four `study3` records unmoved (no UL traffic at all) | **HIT — 0 mismatches.** Structural, and a stop condition had it moved |
| ≥ 5,470 mismatches (superset of the diagnostic) | **HIT — 5,689** |
| `study1/overload_mult1.0/PF` moves, unlike the diagnostic | **MISS — 0 mismatches** |

**The miss, re-derived with numbers before capturing** (the pre-registered
rule blocked the re-baseline until it was). Instrumenting how often the new
trigger actually fires per run:

| | PF | TwoTier | Reservation |
|---|---|---|---|
| mult1.0 | **1** | 14 | 201 |
| mult1.5 | 48 | 129 | 257 |
| mult2.0 | 378 | 271 | 308 |
| mult3.0 | 570 | 538 | 587 |

`study1` scales **capacity**, so mult1.0 is the *most congested* point. PF's
grants there are scarce enough that `sched_ul_bytes` essentially never
overruns the estimate — the trigger fires **once** in the whole run, so there
is nothing for the broader form to fix. TwoTier (14) and Reservation (201)
overrun even there, because their target/deficit-based sizing issues larger
grants.

So the predicted *reason* was wrong — it had nothing to do with arrival
timing — while the superset argument itself is sound. **The miss corroborates
the investigation rather than undermining it**: "the arms differ in how fast
their grant sizing drives the overrun" was §8b's core claim, and this is a
second, independent measurement of it.

### Re-baseline — what it invalidates

First sanctioned re-capture since `a5f6baa`; 20 records; `--check` clean
after. Qualifies under CLAUDE.md's rule (the change is *intended* to move the
numbers). What it invalidates, stated rather than silently replaced:

**`README.md` §7's Study 2 characterisation is partly wrong post-fix.**
Pre-fix vs post-fix:

| | total | on-time | UL util |
|---|---|---|---|
| PF (pre-fix 4.8M / 14 of 30 / 41.1%) | 9.5M | 20/30 | 0.708 |
| Reservation (pre-fix 4.1M / 9 of 30 / 61.7%) | 7.4M | 15/30 | 0.479 |
| TwoTier | 8.8M | 23/30 | 0.930 |

- **Survives**: Reservation is still visibly worse than PF on this scenario.
- **Does not survive**: the specific anomaly §7 calls out — *"UL PRB
  utilization higher than PF's despite delivering fewer bytes"* — **inverts**
  (0.479 vs 0.708). That reading was an artifact of the defect.

**D4-1 (Study 2's bimodal p99) must be re-scored, not carried forward.** §8b
flagged it as plausibly downstream of this defect; the arm ordering it was
measured against has now moved. It stays open with its §6.1 expectation
intact but its *evidence* void.

**`docs/phase2-two-tier-delta.md` gets a dated pre-fix header**, not a
blanket one, because the record split says exactly what is and is not known:
`study3`'s near-parity control row is on records the fix does not touch, so
**the control survives for a checkable reason** and the ordering argument
keeps its anchor; `study2`'s row is on a record that moves hard and is
**unverified**; `study1`'s rows are pre-fix. Re-running the old arm needs
row 77's overlay procedure and is out of scope here.

### Corrections carried in this commit

**The corpus is 20 records, not 22.** `README.md` §9 and `CLAUDE.md` both
carried "22-record numeric snapshot"; the baseline file holds exactly 20 keys
and `_cases()` builds 20. §8b's own "15 of 22" inherited it — the measured
numerator was right, the denominator was not. **15 of 20 moved, 5 unmoved**,
and the 5 are `study1/mult1.0/PF` plus all four `study3` records.

**Commit 0b's boundedness argument is wrong; its headline stands.** The
per-LCG array is not the route — it reads 28,581, frozen, never 0. But 0b
claimed three re-arming paths bound the state, the third being "assembly on
any grant once `pending` is set", asserting `sim/ul_access.py` always
eventually supplies that grant. It did not; that was the defect.
`bytes_reported` **can** stall at 0 over live backlog indefinitely, by the
`sched_ul_bytes` route rather than the per-LCG one.

**Tally**: this is the project's **third self-inflicted finding**, and the
**second** where a forward-looking claim was checked and found wrong — after
`_dl_stamp`'s stale *citation* and port-map row 46's wrong *plan*. 0b's is a
third kind: a wrong *argument* about code that already existed and could have
been read at the time. CLAUDE.md's invariant is extended to cover it, since
its existing wording covers notes about code not yet written.

---

## 8d. Stage 2 — results (252 cells, 7,560 runs, ~70 min at 10 workers)

Re-run: `uv run python scripts/wp9_sweep.py --stage 2 --seeds 10 --horizon
20000 --workers 10 --out sweeps/wp9/stage2`, then `uv run python
scripts/analyse_stage2.py sweeps/wp9/stage2`.

**Grid integrity first**: 0 missing, 0 wrong-sized cells.

### Contiguity, read before any effect size (rule 5)

| metric | scored | isolated | winners |
|---|---|---|---|
| M07.met | 186 | 1 (0.5%) | PF 102, TwoTier 49, Reservation 35 |
| M08.fraction | 186 | 1 (0.5%) | PF 175, Reservation 8, TwoTier 3 |
| M01.p98 | 186 | 2 (1.1%) | PF 104, TwoTier 81, Reservation 1 |
| M02 | 186 | 0 | PF 158, TwoTier 28 |
| M09.worst | 186 | 0 | PF 100, Reservation 58, TwoTier 28 |

66 of 252 cells are uninformative (zero loss on every arm) and carry no
winner. Isolation is 0-1.1%, so the winning regions are contiguous regimes
rather than noise.

### D4-3 — HIT, including the load refinement

PF-vs-Reservation separation by (N, load), base slice
(`shared_lcg=False`, `k2_slots=2`):

| N | 0.5 | 0.75 | 1.0 | 1.25 | 1.5 | 2.0 | 3.0 |
|---|---|---|---|---|---|---|---|
| 2, 4 | . | . | . | . | . | . | . |
| 8 | . | . | **q** | **q** | **q** | **q** | **q** |
| 16, 24, 32 | **q** | **q** | **q** | **q** | **q** | **q** | **q** |

The boundary is **N=8 at load >= 1.0 and N=16 at load 0.5-0.75** — exactly
the predicted shift, and predicted for the stated reason:
`n_followers_need` counts *simultaneously backlogged* UEs, so at low load
the effective follower count is below nominal N and the boundary moves up.
N=8 matches §1.1's PDCCH bound of `32/4 = 8`.

**Qualifier that travels with this claim**: `min_rb` is held at base 5, so
this locates the boundary *at the deployed value only*. §1.1's sharper
claim — that `min_rb` has no effect on the boundary below ~7, because the
PDCCH bound binds first — is **untested**, and testing it needs `min_rb`
as a stage-2 axis.

### D4-3 correction — the winner is METRIC-DEPENDENT (H6 confirmed)

A first reading of the table above credited PF with a 0.5-1.0 lead at
N>=8. That was `M08.fraction` only, and it is misleading. Split by metric,
at load 1.0:

| N | M07.met (PF/Res/TT) | M08.fraction (PF/Res/TT) |
|---|---|---|
| 8 | 8.0 / 7.2 / 5.4 | 0.962 / 0.288 / 0.243 |
| 16 | 13.9 / 10.9 / 6.3 | 0.931 / 0.000 / 0.000 |
| 24 | **0.0** / 10.4 / 6.7 | 0.636 / 0.000 / 0.000 |
| 32 | **0.0** / 6.2 / 6.4 | 0.470 / 0.000 / 0.000 |

**At N >= 24, PF meets ZERO GBR contracts while Reservation meets 10.4/6.2
and TwoTier 6.7/6.4 — yet PF still wins the max-min floor.** PF spreads
capacity so every flow gets some and none reaches 95% of GFBR; the
QoS-aware arms concentrate it so some flows meet contract and others get
nothing. **This is H6 ("contract count and max-min floor pick different
winners in the same cell") confirmed directly**, and it means any
single-metric statement about who wins at high N is wrong by construction.

### D4-3a — ADMISSIBLE FLEET SIZE, computed at last: PF 8, Reservation 4, TwoTier 4

**G10's headline deliverable is the admissible fleet size, and until this
subsection nobody had computed it.** What the documents carried instead —
*"admissible N bounded by 8 at load ≥ 1.0 and by 16 below it"* — is D4-3's
**arm-separation boundary**, the fleet size at which the arms start to
differ. **That is a different quantity**, it is not per-arm, and reading it
as the admissible fleet overstates the two arms that matter operationally.

**The criterion is the pre-registered one** (§5(a): *"M07, M08 all-pass at
5/5 seeds → admissible N"*; test plan G10: *"largest asset count with
G1–G8 all-pass in 5/5 runs"*): a seed passes when `M07.met == M07.total`
**and** `M08.fraction ≥ 0.95`; admissible N is the largest fleet passing on
**every** seed. Emitted by `scripts/g10_admissible.py`, not restated:

| arm | N=2 | N=4 | N=8 | N=16 | N=24 | N=32 | **admissible** |
|---|---|---|---|---|---|---|---|
| PF | 10/10 | 10/10 | **10/10** | 0/10 | 0/10 | 0/10 | **8** |
| Reservation | 10/10 | 10/10 | 3/10 | 0/10 | 0/10 | 0/10 | **4** |
| TwoTier | 10/10 | 10/10 | 1/10 | 0/10 | 0/10 | 0/10 | **4** |

*(load ×1.0, base slice `k2_slots=2`/`shared_lcg=False`, 10 seeds/cell —
the sweep has 10 where the rule registered 5; a first-5-seeds subsample
gives the identical verdict, so the deviation is conservative.)*

**Four robots run clean on every scheduler. Eight is where the QoS-aware
arms fail and PF does not.** "The schedulers separate at 8" — D4-3's
result — is the *supporting detail*; the headline is that **the deployed
product admits half the fleet PF does.**

**And TwoTier is last on both metrics at 8 and 16 robots**, from the same
run (`scripts/g10_admissible.py` prints the ranks):

| N | M07 rank | M08 rank |
|---|---|---|
| 8 | PF 1, Reservation 2, **TwoTier 3** | PF 1, Reservation 2, **TwoTier 3** |
| 16 | PF 1, Reservation 2, **TwoTier 3** | PF 1, then Reservation and **TwoTier tied at exactly 0.000** |

**One word of qualification, because §0.1's rule cuts both ways:** at N=16
on M08 the two QoS-aware arms are at **exactly 0.0000 on all 10 seeds** — a
dead tie, so TwoTier is *joint*-last there, not last. On M07 it is
unambiguously last at both sizes. And above N=16 the ranking inverts (PF
meets zero contracts while holding the best floor), which is D4-3's own
correction — so "TwoTier last" is a statement about N ∈ {8, 16} and must
not be carried upward.

**Two caveats that travel with the number.**

- **PF's 8 is knife-edge; the QoS-aware arms' 4 is not.** PF's worst seed
  at N=8 has `M08.fraction = 0.9503`, a margin of **0.0003** over the bar.
  Across the six `(k2_slots, shared_lcg)` slices the answer is 8/4/4 on
  five of six and flips PF to 4 on one.
- **M08 adds nothing to the conjunct at this bar.** `M07.met == M07.total`
  and `M08.fraction ≥ 0.95` disagree on **0 of 7,560 rows** — M08's min is
  over the same GBR flow set M07 counts, so the registered "M07, M08
  all-pass" is effectively M07 alone. Widening toward the full G1–G8 (adding
  M05 ≥ 0.99 and M09 ≥ 0.9) leaves 8/4/4 unchanged and drops TwoTier's N=8
  from 1/10 seeds to 0/10.

**Scope**, per §0.1/§0.3: stage 2's uniform parametric mix at the deployed
`min_rb=5`, one base slice, 20,000-slot horizon. G5's row records that the
concentrate-vs-spread signature this number is built from has a
**workload-dependent onset**, so 8/4/4 is this workload's answer, not a
fleet-general one.

### D4-4 at N=4 — HIT, and stronger than the N=2 control

Zero qualifying M07/M08 separations at N=4, max effect size 0.30-0.36
against a 1.0 bar. Crucially **loads 1.5 and 3.0 at N=4 ARE informative**
(non-zero loss), so unlike the N=2 control this is a real absence rather
than an excluded cell. Combined with D4-3: **the boundary lies in (4, 8]**,
which is the branch the pre-stage-1 amendment (`eb04266`) named and it
lands on §1.1's predicted PDCCH bound.

### H5 via `shared_lcg` — MISS, traced

Predicted: TwoTier degrades at `shared_lcg=True`, Reservation less so.
Actual, paired **within-seed** across all 42 (N, load) cells per arm:

| arm | cells with a real effect |
|---|---|
| PF | 0 / 42 |
| Reservation | 0 / 42 |
| TwoTier | **1 / 42** (mean -1.1 contracts at N=32/load 0.75, es 1.11 — marginal) |

**The trace mattered.** An unpaired first look showed Reservation dropping
2.4 contracts at N=32/load 1.0, which read as "Reservation degrades most" —
the opposite of H5. Paired within-seed, that effect vanishes: it was
cross-seed variance in unpaired means, not a shared-LCG effect. Had it been
absorbed rather than traced it would have produced a confident and wrong
refutation of H5's direction.

**What this establishes, stated carefully**: at `mfbr_bps = 0`, forcing two
UL flows onto one LCG has **no measurable effect on any arm**. H5 is
therefore **not confirmed and not refuted** — because the sub-mechanism
most likely to carry it, `gbr_bytes_slot`, requires shared-LCG **and**
`mfbr_bps > 0` (README §7's cause D), and stage 2 held `mfbr_multiple` at
its 0 base. My own pre-registered note said row 25's `gbr_bytes_slot` would
stay dormant for exactly this reason; what I failed to draw from it is that
**this makes H5 untestable in stage 2 as configured**. Testing H5 needs
`shared_lcg=True` crossed with `mfbr_multiple>0`, which no cell in either
stage ran.

### Standing qualifier on all of the above

11 of 12 axes cleared the stage-1 threshold, so the **cap** did the
narrowing, not the score (§6.4a). These results confirm that differences
reproduce on a dense contiguous grid; they do **not** establish that the
promoted axes were the most important ones. The eight dropped axes —
`sr_period_slots` (152.579), `snr_spread_db` (4.689), `pdb_ms` (2.927),
`duty_cycle` (2.663), `bg` (2.648), `mfbr_multiple` (1.778), `min_rb`
(152.579), `inf_scenario` (did not qualify) — remain live candidates, not
tested-and-rejected ones. `mfbr_multiple` and `min_rb` are now the two with
a named, specific reason to run next.

---

## 9. Definition of done for WP9

- `uv run pytest sim/tests -q` green after every commit.
- `uv run python scripts/regression_corpus.py --check` → `OK — no drift`
  after commit 0, after commit 1, and again immediately before stage 2.
- Commit 0's inertness **proven, not assumed**: `grep -rn "Reservation("
  scripts/ sim/` shows no non-default `min_rb` construction anywhere in the
  corpus, **and** a scratch run with `Reservation(min_rb=20)` confirms the
  value now actually reaches `allocate()` — i.e. that the fix does something —
  while the corpus path stays byte-identical.
- Stage 1's output is checked for the D4-4 positive control **before** any
  other reading of it. If N=2 separates the arms, stage 2 does not start.
- Every reported cell passes `is_informative`; every reported boundary passes
  `check_contiguity`; every zero-miss claim states its own pooled n and the
  rule-of-three bound that n supports; every G11 row carries its own seed
  count and "no CI" inline.
- H1–H7 each resolved: confirmed, refuted, or inconclusive-with-reason.
- `grep '\[OPEN' README.md`: every `[OPEN: WP9]` item either flipped to
  `[RESOLVED]` with a citation of what closed it, or explicitly re-tagged with
  what it now needs — per README §10's own Phase 3 exit criterion.

---

## 10. Status

**PAUSED at commit 1 under §7's D6 rule.** A `sim/`-layer defect
(§8b) starves UL flows corpus-wide and would contaminate every sweep cell;
the fix is its own commit and the base point recalibrates after it.

**Commits 0 and 0b landed.** 0: prediction hit, `--check` clean, port-map
row 78. 0b: negative result, written up in §8a — the fault is outside this
model's expressive range, and the future WP is scoped as "add a mechanism
`sim/bsr.py` lacks", with two candidates named.
Next: commit 1 (infrastructure + the §6.4 rule as code) → stage 1, N=2
control read first → stage 2 → the map.


---

## 11. Stage 3 — the two named runs (plan, approved before any cell ran)

Stage 3 addresses **two of the eight dropped axes** (`docs/wp9-regime-map.md`
§0.4). **It does not close §0.4's coverage gap**: H2/H3/H4/H7 stay untested,
G2/G4/G6/G12 uncomputed, G7 unanswerable, G9/G11 unrun. §0's four
qualifiers travel with every stage-3 claim.

**The stage-1 gate is deliberately NOT applied.** It exists to *select*
axes when you do not know which matter; these two were selected by named
argument (§0.2, §0.3), and §0.4 showed the threshold does not discriminate
anyway (11 of 12 cleared). Running `select_for_stage_2` would answer a
question nobody asked. Reused instead, as *descriptive statistics for the
stated predictions*: `evaluate_cell`'s paired within-seed effect size,
bootstrap CI and `is_informative`, plus `check_contiguity` before any
boundary claim.

### Grid and budget (from §6.3a's MEASURED timings)

| sub-grid | axes | cells |
|---|---|---|
| **Q1** `min_rb` crossover | N {2,3,4,6,8,12,16} x `min_rb` {1,3,5,7,10,20} x load {1.0,2.0} | **84** |
| **Q2** mfbr / H5 | `mfbr_multiple` {0,1,2,4} x `shared_lcg` {F,T} x N {8,16,32} x load {1.0,2.0} | **48** |

Q1 ~22,548 s + Q2 ~31,456 s = **15.0 h serial -> ~2.2 h wall** at 10
workers (stage 1's measured 6.75x).

### Q2's null control is a STOP CONDITION, read first

`max_burst = int((mfbr_bps/8)/slots_per_sec)*2`, floored at
`obligation*2`. At GFBR 4 Mbps, mu=2: obligation ~125 B/slot, floor 250 B.
So **`mfbr_multiple=1.0` gives `max_burst = int((4e6/8)/4000)*2 = 250` --
exactly the floor, hence a no-op**; x2.0 -> 500 B and x4.0 -> 1000 B raise
the catch-up ceiling.

**x1.0 must be BIT-IDENTICAL to x0** -- byte-equal rows on shared seeds,
not "within tolerance", which the paired-seed determinism property makes
the right test. **Checked before a single effect size is read.** If it
differs, the model of `max_burst` is wrong and every other Q2 cell is
uninterpretable; the run stops rather than being reported.

### Falsifiable expectations, stated before running

**Q1 (`min_rb`).** §1.1 gives `N_crit = min(55/min_rb, 8)`. The boundary is
**pinned at 8 for `min_rb` <= 6** (PDCCH-bound) and **falls above ~7**:
7 -> ~7.9, 10 -> ~5.5, 20 -> ~2.75. *Falsified by* any boundary movement
across `min_rb` in {1,3,5}, or by no movement at 10/20.

**Q2 (`mfbr`).** (i) x1.0 == x0 bit-identical (above). (ii) x2/x4 raise the
cap in **both** arms, so M07/M08 improve where deficits accumulate (high N,
high load) with **arm ordering largely preserved** -- it is a shared
parameter. (iii) `gbr_bytes_slot` becomes live in Reservation for the first
time.

**(iv) The UL floor: predicted ZERO fires, and why that is a test rather
than an absence.** The floor's dormancy has two independent reasons
(README §7): it needs `mfbr_bps > 0` to **arm**, and a BSR/SR-desync fault
to **fire**. Every run in this project has failed the first, so "no fires"
has never distinguished *never armed* from *armed but never fired*.
**Stage 3 is the first run where the arming half is satisfied**, so it
separates them for the first time. Commit 0b established `sim/bsr.py`
cannot express the desync state, so the prediction is `gate_passes > 0`
with `fires == 0` -- which would **confirm** the two-reason dormancy as a
positive result about the fourth dormancy category, not report an absence.

> **Recorded before the real run: the machinery smoke test already
> contradicts (iv).** A 16-cell smoke grid (horizon 1000) returned
> `gate_passes=73285, fires=9`. The prediction is left AS STATED rather
> than revised, per this project's own rule against editing a prediction
> after seeing data -- even implementation-test data. The likely error is
> now identifiable: **I conflated the floor's arming gate with its firing
> condition.** Arming reads the per-LCG estimate (`_ul_has_pending_gbr`);
> firing keys on `floor_rx_lastseen` -- *delivery not moving* -- so a UE
> starved by ordinary contention can fire the floor without any BSR/SR
> desync. If the full run confirms this, the finding is that **the floor's
> firing condition was never actually gated on the desync fault**, which
> is a correction to README §7's own framing of the fourth dormancy
> category, not merely a missed prediction.
>
> **SUPERSEDED BY AN AT-SCALE MEASUREMENT (§19.5), and the prediction is
> scored a HIT.** A full run measured `gate_passes ≈ 65,200, fires = 0` in
> all three `truncated_bsr` modes — not a 16-cell smoke grid at horizon
> 1000. **The two halves DO separate (armed, never fired), and they
> separate with no desync present at all.** The smoke grid's `fires=9` is
> **unreproduced**, and the conflation hypothesis above is neither
> confirmed nor needed — `fires == 0` was right for the reason originally
> given. Stage 3 itself never completed (it died at cell 51/52 and was
> superseded by the re-scope), so the smoke figure was never the stronger
> evidence and should not be cited as though it were.


---

## 12. The re-scope — taxonomy and two findings

### 12.1 The three-category taxonomy

The scoping error corrected here: three categories had been treated as one
axis space.

- **Cat 1 — fixed by the deployment.** Core/gNB config. A **condition** of
  the map, not an axis in it.
- **Cat 2 — what the environment does.** Encountered, not chosen. What the
  map is indexed by.
- **Cat 3 — scheduler internals.** Meaningful only as arms.

| stage-1 axis | cat | justification |
|---|---|---|
| `n_ues` | 2 | fleet size |
| `load_mult` | 2 | offered load |
| `duty_cycle` | 2 | burstiness (H2) |
| `snr_spread_db` | 2 | channel spread (H3) |
| `bg` | 2 | elephant / background traffic |
| `inf_scenario` | 2 | deployment RF environment |
| `shared_lcg` | 2* | a consequence of composition, not a knob (§12.3) |
| `min_rb` | **1** | `nrmac->min_grant_prb` = 5, gNB config |
| `mfbr_multiple` | **1** | QoS-profile field, provisioned per bearer |
| `pdb_ms` | **1** | 5QI-derived (`ad6ba54`) |
| `sr_period_slots` | **1** | RRC / gNB config |
| `k2_slots` | **1** | TDA table / numerology |

Four of the eight axes the stage-1 cap dropped are Cat 1 and were **never
live candidates**; H4 and H7 are re-tagged accordingly
(`docs/wp9-regime-map.md` §0.4, §3). **What that does not change:** the cap
still did the narrowing rather than the score, 11 of 12 axes cleared the
threshold, and a stage-2 result on a cap-selected axis is still weaker
evidence than §6.4 assumed. The gap is **mis-shaped, not overstated**.

### 12.2 Finding — the composition flow-count claim, corrected

**Claimed** in the re-scope: fleet compositions "differ by an order of
magnitude in flow count". **Measured:** the spread is **1.8× across
realistic mixtures** (35–63 flows at N=16) and **3× across pure fleets**
(32 for 16 sensors vs 96 for 16 UGVs). Not ten.

**The compositions were not inflated to fit the claim; the claim was
corrected**, and `sim/tests/test_fleet.py` now asserts the true property
instead of the overstated one.

The replacement argument is stronger, and differently shaped: composition
moves **several dimensions at once**.

| dimension | spread at N=16 |
|---|---|
| GBR fraction | 9% → 23% (**2.6×**) |
| tight-PDB share (≤30 ms) | 38% → 60% |
| UL share | 51% → 68% |
| flow count | 35 → 63 (1.8×) |

Four dimensions moving together is a **better** justification than one
moving 10× would have been, because the joint change is what alters the
scheduling problem. The original claim was not merely overstated — it was
measuring the wrong thing.

### 12.3 Finding — shared-LCG is emergent, and H5's status changes

Stage 1 forced shared-LCG with a synthetic per-flow `lcg` override,
specifically to route around `FIVE_QI_LCG` being invented and unvalidated.
The re-scoped **UGV profile produces the same condition with no override**:
odometry (5QI 83), drive control (82) and e-stop (85) all map to **LCG 3**.

1. **H5 moves from "untestable as configured" to "testable by
   composition"**, and the test is stronger — co-location follows from a
   realistic device's QoS classes rather than a flag set to make the
   mechanism fire.
2. **The result stays conditional on `FIVE_QI_LCG`**, still invented
   (`[OPEN: HARDWARE/DECISION]`). That item does not close. What changes is
   that H5 now inherits a *realistic* mapping's consequence instead of an
   arbitrary one.


---

## 13. The measured probe, and two decisions it settled

Run before any grid, at the real horizon with the real flags and the real
post-processing — §6.3a's rule, whose violation caused the 5–7× miss.

| cell | flows | cell cost (3 arms × 10 seeds) |
|---|---|---|
| N=8 mixed, 5 s | 26 | 163.6 s (2.7 min) |
| N=32 ugv_heavy, 5 s | 124 | 928.6 s (15.5 min) |
| N=32 sensor_dense, 5 s | 69 | 379.4 s (6.3 min) |
| **N=16 lidar activation, 5 s** | 65 | 498.6 s (8.3 min) |
| **N=16 lidar activation, 20 s** | 65 | **4415.2 s (73.6 min)** |

**Cost model, fitted to the three steady-state points: `4.48 × flows^1.09`
s/cell.** Cost scales with **flow count**, near-linearly — so §6.3a's
N-based timings genuinely do not transfer, and N=32 ugv_heavy is expensive
because it is 124 flows, not because it is 32 UEs.

> **SCOPE QUALIFIER (added later, from measurement): this model is fitted
> to FLEET-BUILDER compositions and does not transfer to the parametric
> `factory` mix.** Checked against §6.3a's parametric points (8/32/128
> flows, same 5.0 s horizon), it **under-predicts by 1.23–1.87×**:
>
> | workload | flows | measured s/cell | `4.48 × flows^1.09` | measured/predicted |
> |---|---|---|---|---|
> | fleet (this table) | 26 | 163.6 | 156.2 | 1.048 |
> | fleet | 69 | 379.4 | 452.5 | 0.838 |
> | fleet | 124 | 928.6 | 857.3 | 1.083 |
> | **parametric** | 8 | 81 | 43.2 | **1.874** |
> | **parametric** | 32 | 303 | 195.8 | **1.547** |
> | **parametric** | 128 | 1093 | 887.4 | **1.232** |
>
> **The model is not wrong — a least-squares refit of its own three points
> gives `4.48 × flows^1.086`, essentially identical.** What the parametric
> residuals show is a **workload** difference: at comparable flow counts the
> parametric mix costs **~1.5× more per flow** (9.47 s/flow at 32 flows vs
> 6.29 s/flow at 26), because that mix carries a fragmenting `xr_video` flow
> and a per-UE poisson best-effort flood that the fleet compositions do not
> weight the same way. **`flows` alone is therefore not a sufficient cost
> index across workloads.**
>
> **What this did and did not affect.** Every grid since stage 4 was
> budgeted from this model, on a workload it was never fitted to — and every
> budget held. **That is §16.1.4's "lower bound" framing doing the work, not
> the model being right.** A model quoted as an estimate would have
> under-budgeted the parametric grids by up to 1.87×; quoted as a floor, it
> stayed true across a workload change nobody checked for. **The safety came
> from the framing.**
>
> **A correction that ran in an unusual direction, recorded because the
> direction is the lesson.** The replacement first proposed here —
> `11.50 × flows^0.939`, fitted to the parametric points — would have been
> **wrong**: it would have replaced a model that fits its own data with one
> derived from a workload it was never meant to cover, and §13's own probe
> points would then have been mis-predicted. The premise came from this
> session's own speedup analysis and returned as an instruction to act on.
> `92d9a60`'s rule (*a decision rule is an input to be checked, not
> evidence*) was written for rules arriving from outside; **this is the
> first time it caught one that originated in the session's own work.** The
> obvious reading of that rule is "check what you are told"; the correct
> reading is **"check any decision rule before applying it, including one
> you produced"** — and a self-supplied premise is the harder case, because
> it arrives already carrying the authority of your own measurement. What
> caught it was going back to *what the model was fitted to*; the arithmetic
> was correct throughout.

> **Commit-hygiene note, additive rather than rewritten.** This section's
> commit (`533105a`) also carries **§26**, which was asked for as a separate
> commit. Both sections were written to this file before either was staged,
> so `git add docs/wp9-plan.md` took both, and `533105a`'s message describes
> only the cost-model qualifier — it **under-describes its own diff**.
> Recorded here rather than fixed by a rebase: nothing was pushed, so a
> split would have been clean, but the standing preference is additive over
> rewrite and **the record is what matters, not the shape of history.**

### 13.1 The lidar cell does not interpolate — measuring it was right

At **7.7 s/flow** the activation cell costs ~40% more per flow than
steady-state `sensor_dense` (5.5 s/flow) **despite having fewer flows**. A
transient with one or two large GBR flows arriving at once moves the
deficit spread, VQ growth and follower budget simultaneously, and that
density of code paths does not show up in a steady fleet. Deriving this
cell's cost from the steady-state timings would have under-budgeted it.

### 13.2 The 20 s horizon: REJECTED, and my threshold rule was answering
the wrong question

**Measured 8.86×, not the predicted 4×** — superlinear, because both the
message ledgers and the timeseries the panel walks grow with horizon.

**Decision: keep 5 s.**

**And the rule I wrote to make this decision was itself wrong.** I had
said: take 20 s unless excursion cells exceed about a fifth of the grid.
That rule presumed a 4× cost, where a modest cell fraction makes 4×
affordable. At **8.86×** the trade fails **at any grid fraction** — 73.6
min/cell is unaffordable for a token number of cells, let alone a fifth of
them. The threshold was not a close call decided by measurement; **the
measurement dissolved the question the threshold was asking.**

Recorded because it is the same shape as §12.2's composition correction: a
claim of mine that measurement replaced with a better answer. The value is
in showing the measurement was **allowed to overturn it** rather than
being fitted around it.

**Consequence, as an EXCLUSION not a caveat.** At 5 s a 2 s activation is
40% of the run, so for lidar-activation cells:

- **Interpretable:** M01, M02 evaluated **during the activation window** —
  which is what the operator question ("at what fleet size does one lidar
  activation start breaking other flows' PDBs?") actually asks.
- **NOT interpretable:** M10 and every other run-aggregate metric. A
  throughput or utilisation figure from a transient cell mixes two regimes
  and must not be quoted. This is an exclusion list, not a warning.

**CORRECTED by §16.2 — the framing above was right and the instrument was
assumed.** "M01, M02 evaluated during the activation window" names a
quantity nothing in this repo computes: there is no windowing anywhere in
the scoring layer, so the exclusion list as written could not have been
applied. §16.2 carries the trace and the consequence (stage 5 re-runs its
own controls rather than reusing stage 4's).

### 13.3 Grid budget

Core plane N ∈ {4, 8, 16, 32} × 4 compositions × 3 video tiers = **48
cells, 4.0 h serial → ~0.6 h at 10 workers**. **No cap on the heavy
profiles is needed**: the earlier feasibility worry was about offered
load, which duty-cycling dissolved (§5), and the runtime is affordable.

### 13.4 Finding — the observation channel lied, for the second time

I killed the probe at 615 s believing it had stalled, because its output
file read empty. **It had completed normally**; `python -c` block-buffers
stdout to a file, so the file said nothing about the process.

This is the **second time this session that a READING of instrumentation
produced a false conclusion**, after the `pgrep` false positive that made
a dead run look alive for a full monitor tick. In both cases **the
observation channel, not the run, was the thing that lied** — once saying
"alive" when dead, once "stalled" when finishing.

**Rule (also added to CLAUDE.md, next to the pgrep/spawn-worker entry,
because it is the same class and the same mitigation): an empty or
unchanging output file is evidence about the FILE, not about the process.
Check process state directly — `ps` on the PID, CPU time, RSS — before
concluding anything about liveness.**

The diagnostic I ran in response was still worth having: it separated run
cost (~2.2 s) from scoring cost (~2.0 s across all 13 passes) and showed
the workload is linear. But the "two orders of magnitude pathological"
call it was chasing was an artifact of buffering, not a property of the
run.


---

## 14. Stage 4 — the Category-2 grid (expectations registered before launch)

**Grid.** N ∈ {4, 8, 16, 32} × composition ∈ {drone_heavy, ugv_heavy,
sensor_dense, mixed} × video_tier ∈ {0.5, 1.0, 1.5} = **48 cells**, 10
paired seeds, 3 arms, horizon 20,000 (5 s). ~0.6 h at 10 workers from
§13's measured model.

### 14.1 The control, read FIRST — and a stop condition

**The low-load corner (N=4, `sensor_dense`, tier 0.5) must be
UNINFORMATIVE** — zero loss on all three arms, therefore excluded by
`is_informative`.

This is the design control, the analogue of stage 1's N=2 cell. A fleet of
four sensors and actuators offering a few hundred kbps against a ~100 Mbps
cell **cannot** lose anything; if it does, the workload is mis-scaled and
**every other cell's interpretation is suspect**. **Stop condition: if the
control shows loss on any arm, the rest of the grid is not read** until
the scaling is explained.

### 14.2 Falsifiable expectations

**E1 — composition is worth being a primary axis.** At fixed N, different
compositions produce materially different arm behaviour: different
separation onset, or a different winner.
*Falsifier:* at every N all four compositions give the same arm ordering
and the same separation verdict → composition was not worth promoting, N
alone would have sufficed, and §12.2's justification is wrong.

**E2 — separation onset tracks FLOW COUNT, not UE count.** The sharp one,
and it follows from two independent things: §1.1's PDCCH bound is about
*candidates per slot*, and §13's measured cost model scales with flows
(`flows^1.09`), not N.
*Expectation:* `ugv_heavy` (~4 flows/UE) separates at **lower N** than
`sensor_dense` (~2 flows/UE), and onsets line up at **comparable flow
counts** across compositions rather than at comparable N.
*Falsifier:* onset at the same N regardless of composition → the binding
constraint is per-UE after all, and composition is a weaker index than
claimed. **This is the expectation most likely to be wrong**, because
stage 2's boundary was found on a workload with uniform flows-per-UE,
where N and flow count are indistinguishable.

**E3 — H6 must be re-established, not assumed.** Stage 2 found PF meets
**zero** GBR contracts at N≥24 while still winning M08 (§0.1). The clean
break (§6 decision 2) means that result does **not** transfer.
*Expectation:* the metric-dependent split reappears at the high-N end of
at least one composition.
*Falsifier:* it does not → H6 was specific to stage 2's synthetic
workload. That would be a significant finding **about the earlier
result**, not a null: §0.1 is currently the regime map's headline
construction lesson, and it would need re-scoping to "true of uniform
fleets" rather than stated generally.

### 14.3 Standing rules

Contiguity before effect sizes; paired seeds within-seed; all 19 metrics;
no single-metric high-N claims (§0.1); the stage-1 gate is **not** applied
(these axes were chosen by argument, not score — §11); corpus frozen at
`9963be1`, `--check` clean before and after.


---

## 15. Stage 4 — results, scored against the pre-registered expectations

**1,440 rows across 48 cells, all exactly 30, in 40.6 min** at 10 workers
against the probe's ~36 min prediction — §13's measured cost model held.
Expectations were registered in `2ea4040`, **before the runner existed**,
so this scoring is checkable from history rather than asserted.

### 15.1 Control — PASS, read first

N=4 / `sensor_dense` / tier 0.5: **zero M02 loss on all three arms** (mean
and max 0.000000 over 30 rows). Uninformative exactly as designed, so the
workload is correctly scaled and the grid is readable. Had it shown loss,
nothing else would have been read.

### 15.2 Methodological finding — `check_contiguity` assumes ORDERED axes

`regime_sweep.check_contiguity` walks each axis by **index ±1**. That is
correct for an ordered axis (N, load, tier) and **meaningless for a
categorical one**: applied across `composition` it would treat
`drone_heavy` and `sensor_dense` as adjacent purely because they are
neighbours in a list, and would then "support" each other's winner.

**This is a property of the tool that was not stated when it was written**
(WP0), because every grid until now had only ordered axes. **Stage 4 is
the first grid with a categorical axis.** Contiguity here is therefore
computed **per composition, over the ordered axes only** (N × tier).

Recorded so the next categorical axis does not rediscover it.

| metric | isolated / scored | reliability |
|---|---|---|
| **M07.met** | 0–2 of 12 | clean — can carry a boundary claim |
| M08.fraction | 3 of 12 in three compositions | noisier |
| M02 | 1–4 of 12 (33% in `mixed`) | noisiest — do not quote equally |

`sensor_dense` scores only 6 of 12 cells; half are uninformative, which is
consistent with it being a genuinely light workload.

### 15.3 E1 — composition is worth being a primary axis: **HIT**

Onset ranges from **N=16** (`ugv_heavy`) to **never within the grid**
(`sensor_dense`), and winners differ by composition. At fixed N the
compositions do not behave alike.

### 15.4 E2 — onset tracks flow count, not UE count: **PARTIAL**

| composition | flows/UE | onset N | flows at onset |
|---|---|---|---|
| `sensor_dense` | 2.0 | none ≤32 | — |
| `mixed` | 3.2 | 32 | 96 |
| `drone_heavy` | 3.8 | 32 | 111 |
| `ugv_heavy` | 4.0 | **16** | **63** |

**Ordering half HOLDS:** `ugv_heavy` separates at N=16 while
`sensor_dense` never does — onset is not a function of N alone, which is
what promoting composition was for.

**Stronger half FALSIFIED:** I predicted onsets would align at comparable
flow counts. They do not — **63 flows (`ugv_heavy`) vs 111
(`drone_heavy`)**, nearly 2× apart. Flow count alone does not explain
onset either.

### 15.5 An OBSERVATION with a candidate mechanism — not a result

`ugv_heavy` separates at *fewer* flows than `drone_heavy`. The UGV profile
carries three tight-PDB flows — odometry (10 ms), drive control (10 ms),
e-stop (**5 ms**) — **co-located on LCG 3**, where the drone's flows are
looser and spread across LCGs. So onset may be driven by **tight-PDB
density and LCG co-location** rather than by candidate count.

**This is an observation, not a finding, and the distinction is load-
bearing:**

- it was **not pre-registered**;
- it comes from **one grid**;
- the two compositions differ in **several ways at once** — flow count,
  GBR fraction, UL share, tight-PDB density, LCG occupancy — so the story
  fits the data without being isolated by it.

**The discriminating experiment**, named because naming it is what
separates an open hypothesis from a story that fits: **a composition set
that holds flow count and GBR fraction FIXED while varying tight-PDB
density and LCG co-location independently.** Two profiles with identical
flow counts and GBR ratios, one with its tight-PDB flows co-located on a
single LCG and one with them spread, would separate the two candidate
mechanisms. Until that runs, this is a hypothesis.

### 15.6 E3 — H6 re-established: **HIT**

Tier 1.0, N=32, mean over 10 seeds:

| composition | M07 contracts (PF/Res/TT) | M08 worst-flow GFBR (PF/Res/TT) |
|---|---|---|
| `ugv_heavy` | **0.0** / 0.6 / 4.9 | **0.453** / 0.000 / 0.000 |
| `mixed` | 0.3 / 0.0 / 3.4 | 0.549 / 0.400 / 0.116 |

**PF meets ZERO GBR contracts while winning the max-min floor outright.**
H6 reproduces on a structurally different workload — heterogeneous device
profiles, no synthetic filler — so §0.1's construction lesson
**generalises** rather than being an artefact of stage 2's uniform fleet.
That was the result most at risk from the clean break (§6 decision 2), and
it survived. At N=16 all three arms are indistinguishable
(13.0/12.9/12.7), so the divergence is specifically high-N.

### 15.7 The winner FLIPPED, and that sharpens §0.1

Stage 2: **Reservation** led on contracts met. Stage 4: **TwoTier** leads
(4.9 and 3.4). Same structural result — one QoS-aware arm concentrates and
meets contracts while PF spreads, meets none, and wins the floor — **with
the arms swapped.**

**The LESSON generalises; the RANKING does not.** That is a sharper
statement than either result alone, and it strengthens §0.1 directly: any
single-metric claim about who wins at high N is false by construction, and
now **demonstrably so across two workloads whose winners are opposite**.
A reader who took "Reservation wins on contracts" from stage 2 would have
been wrong on stage 4's workload, having quoted a real number.

---

## 16. Stage 5 — the lidar-activation excursion (plan, registered before the runner exists)

`docs/wp9-regime-map.md` maps where the three schedulers separate under
*steady* conditions: fleet size, composition, offered load. Every cell in
stages 1–4 ran a workload whose shape was constant for the whole run.

The lidar activation is the only regime in this project where a **large,
transient GBR demand arrives suddenly** against a fleet whose telemetry and
control flows must still meet their PDBs. `sim/fleet.py`'s UGV profile
carries a duty-cycled 12 Mbps lidar flow (`LIDAR_ACTIVE_BPS`, Ouster LDRP
class) gated by `LidarActivation`; `sim/traffic.py:197-216` applies the
activation window before the kind dispatch so it composes with every
generator. Both are built and tested (`sim/tests/test_fleet.py`).

**Neither has ever run in a sweep.** `scripts/wp9_sweep.py::_build_fleet_scenario`
(line 610) never passes `lidar=`, so all 48 stage-4 cells ran lidar-off.

Concurrency is capped at 2 UEs as a factory-workflow bound — floor tasks are
serialised, you do not get eight UGVs docking at once — so this is a
**fixed-magnitude perturbation, not a load scale**. That is what makes the
operator question well-posed:

> **At what fleet size does a single lidar activation start breaking other
> flows' PDBs?**

Stage 5 answers it, and hands the hardware campaign a fleet-size bound for a
transient to sit alongside G10's steady-state one.

### 16.1 What carries forward (do not rediscover)

**16.1.1 The 5 s horizon, and its consequence as an exclusion.** The 20 s
option was measured at **8.86×**, not the predicted 4× — superlinear, because
both the message ledgers and the timeseries the panel walks grow with horizon
(§13.2). Rejected; horizon stays 20,000 slots. At 5 s a 2 s activation is
40 % of the run (50 % at 2 staggered UEs), so **run-aggregate metrics from a
lidar-on cell mix two regimes.** This is an exclusion list, not a caveat —
see §16.5.

**16.1.2 Contiguity is per composition, over ORDERED axes only.**
`regime_sweep.check_contiguity` walks each axis by **index ±1**, which invents
adjacency on a categorical axis (§15.2). `composition` is categorical.
Stage 5's ordered axes are `n_ues` and `lidar_ues` (a count, so genuinely
ordered), and contiguity is computed **per composition over N × lidar_ues**,
never across compositions.

**16.1.3 Contiguity reliability differs by metric.** At stage 4: **M07.met was
clean** (0–2 isolated of 12) and can carry a boundary claim; **M08.fraction**
was noisier (3 of 12 in three compositions); **M02 was noisiest** (1–4 of 12,
33 % in `mixed`) and must not be quoted with equal confidence. Stage 5's
windowed variants inherit this ordering as the prior, not as a result — which
matters, because M02w is the metric the operator question most directly asks
for and it is the one stage 4 rated least reliable. **M07w carries the
boundary claim; M02w describes it.**

**16.1.4 The cost model, with its measured transient correction.**
`4.48 × flows^1.09` s/cell (3 arms × 10 seeds), fitted to three steady-state
probe points. **At 65 flows the model gives 424.0 s against the lidar probe's
measured 498.6 s — a 1.176× transient correction**, because a transient with
one or two large GBR flows arriving at once moves the deficit spread, VQ
growth and follower budget simultaneously (§13.1). That factor is **fitted at
tier 1.0 only, from one cell**. Any cell budgeted at the bare
`4.48 × flows^1.09` is a **lower bound**, and so is any tier ≠ 1.0 cell.

**16.1.5 Standing rules.** Paired seeds within-seed (§4 of the regime map: an
*unpaired* comparison produced a confident answer opposite to the paired one).
Contiguity read before any effect size. §0.1's rule — M07w and M08w quoted
**together**, every time either is quoted. Corpus frozen at `9963be1`,
`--check` clean before and after. The stage-1 promotion gate is **not**
applied: these axes were chosen by argument, not score.

### 16.2 A correction to §13.2 — the exclusion named an instrument that does not exist

§13.2 records an approved exclusion list: *"Interpretable: M01, M02 evaluated
during the activation window … NOT interpretable: M10 and every other
run-aggregate metric."*

**The framing was right and the instrument was assumed.** There is no
windowing anywhere in the scoring layer:

- `Scorecard._m01_latency_percentiles` reads `FlowRecord.delay_p*_ms`, which
  the driver computes over the **whole run** (`sim/driver.py:781-787`).
- `Scorecard._m02_pdb_violation_rate` sums `bytes_arrived` /
  `bytes_delivered` / `bytes_dropped_pdb` / `bytes_delivered_late_pdb` —
  all run-total counters.
- The per-message data that *could* support a windowed M01 lives in
  `summary["_message_ledger"]`, which `RunRecord.from_summary` deliberately
  does not carry (it is a live object), and which `regime_sweep.sweep()`
  never hands to `record_sink`.

So the approved exclusion list named a quantity nothing in the repo computes.
This is recorded as a **correction to §13.2**, in the same class as §12.2's
composition flow-count claim and §13.2's own threshold rule: a claim of mine
that reading the code replaced.

**Direct consequence: the controls are re-run, not reused.** Stage 4's cells
are the natural control — same grid coordinates, same `paired_seeds(10, 0)`,
same driver kwargs — but `_strip_timeseries` nulls every per-slot array before
persisting, and no ledger is persisted at all. **The windowed control number
cannot be reconstructed from stage-4 output.** Stage 5 therefore re-runs
`lidar_ues=0` at every coordinate with the windowed instrumentation attached.
Stage 4's rows are demoted from *the control* to a **bit-identity check on the
control** (C5, §16.6).

### 16.3 Grid and budget

**Axes.** `n_ues ∈ {4, 8, 16, 32}` × `composition ∈ {sensor_dense, mixed,
drone_heavy, ugv_heavy}` × `lidar_ues ∈ {0, 1, 2}`. `video_tier` held at
**1.0**. 10 paired seeds, 3 arms, horizon 20,000 (5 s).

- N and composition are stage 4's own levels, so every stage-5 cell reads
  against a stage-4 coordinate and §15.4's onset table (`sensor_dense` none,
  `mixed` 32, `drone_heavy` 32, `ugv_heavy` 16) is directly comparable.
- `video_tier` fixed because the excursion is a fixed-magnitude perturbation;
  holding the background constant is what isolates it.
- `lidar_ues` is a **JSON scalar, not a `LidarActivation`** — `cell_id()`
  json-serialises axis values and `write_csv` needs scalar columns. The
  runner constructs `LidarActivation(n_ues=lidar_ues)` from it.

**`lidar_ues` as a level, and the comment it amends.** `sim/fleet.py:71-74`
says "CONCURRENCY IS A BOUND, NOT AN AXIS … deliberately NOT a parameter
someone might later think to sweep." That stands for load-scaling. 1-vs-2 is
the **two endpoints of the bound itself** — one robot docking versus two —
not a scale. The comment is amended in the same commit to say exactly that,
rather than left reading as though the bound was violated. `build_fleet`'s
`min(lidar.n_ues, LIDAR_MAX_CONCURRENT, len(ugv_ids))` clamp is unchanged, and
`test_lidar_concurrency_is_capped_as_a_bound` keeps pinning it.

**Cell counts — derived, and asserted by the runner, never restated in prose.**
The runner computes and prints these from `build_fleet` at launch and
**aborts if they disagree** with the registered values below:

| quantity | expected |
|---|---|
| total cells | 48 |
| control cells (`lidar_ues=0`) | 16 |
| excursion cells (`lidar_ues>0`) | 32 |
| **degenerate** excursion cells (`n_active < lidar_ues`) | **9** |
| **null** excursion cells (`n_active == 0`) | **4** |

Degeneracy is structural, from largest-remainder allocation over the
compositions' UGV weights: `sensor_dense` (0.03) has **zero** UGVs at N=4 and
N=8 and exactly one at N=16 and N=32; `mixed` has one at N=4; `drone_heavy`
has one at N=4 and N=8. The 4 null cells are C1's stop condition (§16.6).

**Budget, from §16.1.4's model with the 1.176× transient correction applied to
every cell with `n_active > 0`:**

| | value |
|---|---|
| serial | **4.64 h** |
| largest single cell | **1025.8 s** (17.1 min — `ugv_heavy` N=32, `lidar_ues=2`) |
| wall at 10 workers | **≥ 28 min** (bounded below by the largest cell) |

Stage 4's comparable 48-cell grid measured 40.6 min at 10 workers. **These are
lower bounds**: the transient factor is fitted from one cell at tier 1.0. Disk
≈ 1 GB of `records.jsonl` (stage 4: 982 MB / 48 cells); 180 GB free. 10
workers, matching stage 4, on 24 cores / 30 GB.

### 16.4 The windowed instruments — study-layer, panel untouched

`config/metric_panel.yml` is **not edited**. These are excursion-specific
windowed variants computed by the stage-5 runner, the same status as stage 3's
UL-floor tally and M13/M16's study-layer calls.

**Windows.** Derived from `LidarActivation`'s own fields, never hardcoded.
With `start_s=1.5`, `duration_s=2.0` and the 0.5 s stagger:

| name | interval | purpose |
|---|---|---|
| `pre` | [0.0, 1.5) | C4 — nothing has happened yet |
| `during_1` | [1.5, 3.5) | the `lidar_ues=1` window |
| `during_2` | [1.5, 4.0) | the `lidar_ues=2` union window |
| `post` | [4.0, 5.0) | recovery — transient or persistent? |
| `full` | [0.0, 5.0) | C3 calibration only |

Every cell is scored at **all five**, control cells included, so a control
pairs with either excursion level at no extra run cost.

**Flow subsets.** `non_lidar` (everything except a 5QI-4 flow on an activated
UGV), `tight_pdb` (non-lidar, `pdb_ms ≤ 30` — §12.2's own threshold), `estop`
(5QI 85, the 5 ms DL flow), `lidar_only`.

**Definitions.**

- **M01w** — `message_latency_percentiles_ms(completions)` over completions
  whose `message.generation_ts_s` falls in the window, worst flow by p99, with
  M01's own "exclude flows with zero complete messages" rule. **A pure
  restriction of panel M01's population** — same formula, same percentile
  index convention, fewer samples.
- **M02w** — over the same completion selection:
  `(Σ dropped_bytes + Σ delivered_bytes where late) / (Σ delivered_bytes +
  Σ dropped_bytes)`. **A restriction *plus* an accounting change**, and the
  difference must not be glossed: panel M02 counts `bytes_delivered_late_pdb`
  per drained *chunk*, tagged at drain time; M02w counts a whole message's
  delivered bytes when `MessageCompletion.late` is true. A message whose first
  bytes drained on time and last bytes late is counted differently by the two.
  This is why C3 exists.
- **M07w** — per GBR flow, in-window throughput
  `Σ ts_delivered_bytes[window] × 8 / window_s`, counted against
  `gfbr_bps × 0.95` (the panel default). Reported over `non_lidar`; the lidar
  flow's own M07w reported separately (does the activation itself get served?).
- **M08w** — `min` of that fraction over non-lidar GBR flows: the max-min
  floor, in-window.

M01w/M02w need the ledger; M07w/M08w need `ts_delivered_bytes`. Both are
available to the sink and **neither survives persistence** — so both are
computed online and discarded, exactly as `_online_rows_for` already does.

### 16.5 The exclusion list, as an exclusion

**On any cell with `n_active > 0`, no run-aggregate panel metric is quoted.**
That is M01–M19 as emitted by `Scorecard.score()` — not only M10.

Rows are still written in full (the panel's never-omit rule: an omitted row is
indistinguishable from a forgotten one). The runner tags every such row
`transient_excluded=True`, and `scripts/analyse_stage5.py` **raises** if asked
to aggregate an excluded column across lidar-on cells. Only M01w/M02w/M07w/M08w
and the paired-control contrast at the same window carry claims.

Control cells (`n_active == 0`) are **not** excluded — their run-aggregate
metrics are legitimately interpretable and feed C5.

### 16.6 Pre-registered controls and expectations

Registered here, in the plan commit, **before the runner exists** — so the
scoring is checkable from history rather than asserted, the way `2ea4040` was
for stage 4.

#### Controls

**C1 — the null-lidar identity. READ FIRST. STOP CONDITION.**
`sensor_dense` at N=4 and N=8 has **zero** UGVs, so `lidar_ues ∈ {1, 2}` there
activates nothing: the scenario must be identical to `lidar_ues=0`, and every
row must be **bit-identical** at the same seed and arm. If any row differs,
the axis plumbing is wrong — a difference with no lidar can only come from the
plumbing — and **nothing else in the grid is read** until it is explained.

**C2 — the degenerate-cell count.** The runner asserts exactly **9 of 32**
excursion cells have `n_active < lidar_ues`, and **4** have `n_active == 0`,
computed from `build_fleet` at launch. A disagreement means `_allocate` or the
cap changed and the grid's interpretation is suspect. Asserted, not discovered.

**C3 — M02w calibration.** M02w at the `full` window versus panel M02 on the
same record, across all 16 control cells. Reported as a distribution **before
any windowed number is quoted**. If the two diverge systematically, M02w is
reported as a distinct estimator with its bias stated, never as "M02
restricted to a window."

**C4 — the pre-window read. Both branches named in advance, WITH their
different consequences for what the whole grid measures.**
`pre`-window metrics, lidar-on vs lidar-off, same seed and arm.

*Identical* → the perturbation is cleanly localised to the activation window.
E1–E4 are read as written: the contrast measures **activation**.

*Different* → the lidar bearer's mere **provisioning** — a 12 Mbps GBR
contract carrying no traffic — already changes scheduling, plausibly through
TwoTier's Tier-1 LP or Reservation's follower budget. This is not a stop
condition and does not invalidate E1–E4, but it **changes what they say**:
every lidar-on cell's on/off contrast then measures **provisioning +
activation**, a compound treatment, and the wording changes accordingly —

> "the activation breaks flows at N=x" → **"adding a provisioned-and-activated
> lidar bearer breaks flows at N=x"**

which is a materially different claim for the hardware campaign, because
provisioning and activation are **separately controllable in a real
deployment**: an operator can leave a bearer configured and never enable the
sensor.

**Registered now, before the run:** if C4 fires the *different* branch, E1–E4
are reported with the compound wording throughout, and the plan records that
separating the two effects needs a **third level — bearer provisioned, never
activated**. That level is already expressible without new mechanism: a
`LidarActivation` whose `start_s` exceeds the horizon puts the flow in
`scenario.flows` with its full GBR contract while `sim/traffic.py`'s activation
gate emits nothing for the entire run. It is **not** in this grid (it would
take `lidar_ues` to four levels and re-open the "not an axis" question), and
naming it in advance is what keeps a C4-different outcome a **finding with a
named follow-up** rather than a caveat bolted on after the fact.

**C5 — stage-4 bit-identity on the controls.** Stage-5 `lidar_ues=0` rows must
reproduce stage 4's `video_tier=1.0` rows exactly (same `_build_fleet_scenario`,
same `paired_seeds(10, 0)`, same `_driver_kwargs`). Verified against
`sweeps/wp9/stage4/rows.jsonl`. A mismatch means plumbing the lidar axis
changed the lidar-off path — stronger coverage than C1, across all 16 controls.

#### Falsifiable expectations

**All four are worded for C4's *identical* branch.** If C4 fires the
*different* branch, each is restated in the compound "provisioned-and-activated
bearer" form C4 registers above — the hits and misses are unchanged, the claim
they support is narrower.

**E1 — the activation is detectable at all.** At `ugv_heavy` N=32,
`lidar_ues=2`, M02w over `non_lidar` in `during_2` is worse than its paired
control beyond the within-seed bootstrap CI on at least one arm.
*Falsifier:* no cell in the grid shows a windowed degradation outside the
paired CI → 12–24 Mbps against a ~100 Mbps cell is absorbed everywhere in this
fleet range, and the excursion has no operating point here. **That is a real
result, not a failed run**, and it bounds the hardware campaign the other way.

**E2 — the breaking fleet size sits at or below stage 4's separation onset.**
Define *breaking N* per composition as the smallest N at which a non-lidar GBR
flow loses its M07w contract in-window that it holds in the paired control.
*Expectation:* breaking N ≤ stage-4 onset N (`ugv_heavy` 16, `drone_heavy` 32,
`mixed` 32, `sensor_dense` none ≤ 32) wherever both are defined, since the
activation adds fixed GBR demand on top of the same background.
*Falsifier:* breaking N > onset N anywhere → a transient is **easier** to
absorb than steady contention, inverting the intuition this excursion is built
on. This is the expectation most likely to be wrong, because a 40 %-duty
transient may simply be averaged away by an EWMA-based arm.

**If E2 misses, it is TRACED, not absorbed.** A miss gets a direct-cause trace
to a confirmed mechanism — a per-slot trace of the first divergent grant, not
more reading — before it is written up. Precedent from this WP's own history:
stage 4's E2 was the registered "most likely to be wrong" expectation, it
missed, and tracing the miss is what produced §15.5's open hypothesis and its
named discriminating experiment. **The likeliest-wrong expectation has already
once carried the more interesting finding**, so a miss here is worth more
effort than a hit, not less.

**E3 — H6 extends from steady overload to a transient.** At the breaking cell,
expect §0.1's split: one QoS-aware arm holds M07w while PF holds M08w.
*Falsifier:* the same arm wins both → H6's construction is a steady-state
property and does **not** extend to transients, which would narrow §0.1 from a
general construction lesson to one about sustained load. Per §0.1's standing
rule, M07w and M08w are quoted **together**, every time either is quoted.
Given §0.1.1 (the winner flipped between stage 2 and stage 4), **no prediction
is registered about which arm** — only that the split occurs.

**E4 — direction beats PDB tightness. Weak, and explicitly NOT §15.5's
experiment.** The UGV e-stop has the tightest PDB in the panel (5 ms) but is
DL and 40 bytes at 0.2 Hz; the lidar is UL and 150 KB every 100 ms.
*Expectation:* e-stop is not the first flow to break; the first breaks are UL
flows sharing the uplink with the lidar.
*Falsifier:* e-stop breaks first → PDB tightness dominates direction.
**Stated up front, whichever way it lands:** this grid varies flow count, GBR
fraction, UL share and tight-PDB density *together*, so it **cannot** test
§15.5's open hypothesis. §15.5's named discriminating experiment — two profiles
with identical flow counts and GBR ratios, one with tight-PDB flows co-located
on a single LCG and one with them spread — remains **unrun**. E4 is suggestive
at best and must not be reported as bearing on it.

### 16.7 Build items

**B7 — `lidar_ues` plumbed into the stage-5 scenario builder.**
`scripts/wp9_sweep.py`: `_build_fleet_scenario_s5(seed, **axis_values)` passes
`lidar=LidarActivation(n_ues=lidar_ues)` when `lidar_ues > 0`, else `None`.
Records `n_lidar_active` (counted from the returned flows, not from the
request) on every row so degeneracy is visible in the CSV. `lidar_ues=0` must
take a path byte-identical to stage 4's (C5).

**B8 — `regime_sweep.sweep(..., run_sink=...)`.** An optional second sink
called as `run_sink(record, axis_values, summary)`, giving access to
`summary["_message_ledger"]` — the handle whose own docstring at
`sim/driver.py:826-829` says it exists so "a study can inspect raw per-message
completions beyond the percentiles". Purely additive; `record_sink` and every
existing caller are unchanged. **An explicit second parameter, not arity
introspection** — `axis_aware`'s docstring already rejects introspection for
this codebase, for the same reason.

**B9 — `scripts/wp9_window.py`.** `windowed_metrics(ledger, flows_ts, flow_cfgs,
windows, subsets) -> list[dict]`, computing §16.4's four quantities. Pure
function over data it is handed; imports no driver and no config, the same
contract `sim/scorecard.py` holds. Reuses
`sim.messages.message_latency_percentiles_ms` rather than reimplementing the
percentile convention.

**B10 — `run_stage_5` in `scripts/wp9_sweep.py`.** Reuses `_run_resumable`
unchanged (resume semantics, oversized-cell abort, rolling-range ETA). Worker
`_run_one_cell_s5` mirrors `_run_one_cell_s4` plus the `run_sink`. Launch-time
assertion of C2's counts. `--stage 5` added to `main()`.

**B11 — tests.** `sim/tests/test_wp9_window.py`: window selection on a
synthetic ledger (boundary inclusivity, empty-window guard, subset selection);
M01w equals panel M01 when the window is the full run and no flow is excluded.
`sim/tests/test_fleet.py`: assert the degenerate-cell structure directly
(`sensor_dense` has 0 UGVs at N=4/8). Extend
`sim/tests/test_wp9_sweep_memory.py` to cover `_run_one_cell_s5` — per
CLAUDE.md's own invariant, a test on the helper does not prove the pipeline
calling it is clean, which is exactly how commit 1c reintroduced 1b's leak.

**Memory discipline.** The worker computes windowed metrics from the ledger and
**discards it immediately** — it must never retain `summary` (which holds both
`_message_ledger` and `_ue_lcp`) or a live `RunRecord`. Live RSS
instrumentation with a kill threshold during the run, per CLAUDE.md: a green
suite does not prove a long run is clean. `pkill -f` **does not reach
`multiprocessing` spawn workers** — kill children by PID. And per the
observation-channel rule, judge liveness by `ps` on the PID (CPU time, RSS),
never by whether a log file is growing.

### 16.8 Commit sequence

One fidelity change per commit; full suite + `regression_corpus.py --check`
after each.

1. **Plan + expectations** — this document into `docs/wp9-plan.md` as §16,
   including §16.2's correction to §13.2. Registered **before the runner
   exists**.
2. **B8** — `run_sink` in `scripts/regime_sweep.py`, with its test. Additive;
   `--check` must not move.
3. **B9 + B11's window tests** — the windowed instruments, unit-tested against
   a synthetic ledger, before any sweep consumes them.
4. **B7 + B10 + the `sim/fleet.py` comment amendment** — the stage-5 runner
   and the axis. C2's counts asserted at launch.
5. **Launch** — `--stage 5`, controls C1/C5 read first.
6. **Results** — scored against §16.6, hits **and** misses, in the style of
   §15.

`--check` is expected clean at every step: `run_sink` is opt-in, the windowed
metrics are study-layer, and the corpus does not run stage-5 code. If it moves,
that is information — not a reason to `--capture`.

### 16.9 Verification

```bash
uv run pytest sim/tests -q                              # 739 must stay green
uv run python scripts/regression_corpus.py --check      # frozen at 9963be1

# machinery only, before committing to the real grid
uv run python scripts/wp9_sweep.py --stage 5 --smoke --seeds 2 --workers 2 \
    --out sweeps/wp9/stage5-smoke

# the real grid
uv run python scripts/wp9_sweep.py --stage 5 --workers 10 \
    --out sweeps/wp9/stage5 2>&1 | tee sweeps/wp9/stage5.log

uv run python scripts/analyse_stage5.py sweeps/wp9/stage5
```

**Read order, enforced by the analyser, not by discipline alone:**

1. **C1** — the 4 null cells bit-identical. If not, stop; read nothing else.
2. **C2** — 48 / 16 / 32 / 9 / 4, computed from `build_fleet`.
3. **C5** — 16 control cells against `sweeps/wp9/stage4/rows.jsonl`.
4. **C3** — M02w vs panel M02 at the `full` window, distribution reported.
5. **C4** — the pre-window read. Name the branch that fired **before** reading
   E1–E4, since it fixes their wording: the *different* branch makes every
   expectation a claim about a provisioned-and-activated bearer, and triggers
   the "provisioned, never activated" follow-up.
6. **Contiguity**, per composition, over N × `lidar_ues` only (§16.1.2) —
   **before** any effect size.
7. **E1–E4**, scored with hits and misses both recorded, M07w and M08w always
   quoted together.

Finally, the end-of-WP judgment-calls review over stage 5's own diff, looking
for undocumented decisions and silent bugs — the standing step, not an
opportunistic one.

---

## 17. Stage 5 — results, scored against §16.6's pre-registered expectations

48 cells, 1,440 rows (3 arms × 10 paired seeds, all cells exactly 30),
**43.2 min at 10 workers**, 906 MB. Against §16.3's registered lower bound
of ≥28 min and ~1 GB — both held, and the budget was a lower bound as
stated rather than an estimate that happened to be low.

### 17.1 Controls, read in the registered order

| control | result |
|---|---|
| **C1** — null-lidar identity (STOP) | **PASS** — 120 paired rows bit-identical |
| **C2** — cell census from `build_fleet` | **PASS** — 48 / 16 / 32 / 9 / 4 |
| **C5** — controls vs stage 4 | **PASS** (after two analyser fixes, §17.2) — 480 control rows identical |
| **C3** — M02w vs panel M02 | reported below as a distribution |
| **C4** — pre-window read | **DIFFERENT branch fired** |

**C3.** Over 480 control pairs at the `full` window: mean delta **+0.00266**,
median **+0.0000857**, min 0.0, max **+0.0412**, sd 0.00822. So M02w sits
*at or above* panel M02, with a near-zero median and a heavy right tail —
a minority of cells carry the whole difference. **M02w is therefore
reported as a distinct estimator with a small positive bias, never as "M02
restricted to a window",** exactly the disposition §16.6 registered for
this outcome.

**C4 fired the DIFFERENT branch, and it changes what every number below
says.** Pre-window M02w over non-lidar flows: mean **+0.000566**, bootstrap
CI **[+0.000494, +0.000638]**, excluding zero over n=960. M08w showed
exactly 0.0 and did not separate.

Per §16.6's pre-registration, E1–E4 are therefore stated in the compound
form — **"adding a provisioned-and-activated lidar bearer breaks flows at
N=x"**, not "the activation breaks flows at N=x" — and the named follow-up
(a third level: bearer provisioned, never activated) is now owed.

**But the mechanism behind C4's difference is NOT established by this
grid, and must not be asserted.** Two candidates fit: the lidar bearer's
12 Mbps GBR contract genuinely perturbing Tier-1 LP or the follower budget
while carrying no traffic; or a seed-alignment artifact from adding a flow
to the scenario at all. `sim/traffic.py`'s activation gate returns before
the kind dispatch so the gated flow consumes no RNG draws, which weakens
the second — it does not eliminate it. **Scale matters for how much this
qualifier is worth:** the pre-window effect is **+0.00057** while the
in-window effect is **+0.039 to +0.135**, i.e. the activation term is
**70–240× larger** than the provisioning-or-artifact term. The compound
wording is required; the compound is heavily dominated by one component.

### 17.2 Two defects the first real run found in the blind-written analyser

Recorded because the analyser was written blind precisely so its failures
would be its own, not the data's.

1. **C5 compared normalisation, not runs** (`a4cd2b7`). It reported all 480
   control rows as differing on `M04.flow=None vs ''`. Verified outside the
   analyser: **0 real differing cells out of 480**. Two causes — `load_rows`
   mapped `''`→`None` on one side only, and `n_ues`/`composition` were
   type-coerced on one side and raw on the other. A control that cries wolf
   is as useless as one that never fires: read at face value this said the
   stage-5 controls were not stage 4's runs, which would have invalidated
   every paired contrast in the grid.
2. **E2's criterion had no interval** (`cd90676`). E1 was registered with a
   paired bootstrap CI; E2 with a bare `mean(on) < mean(control)`. See
   §17.4 — this is not a cosmetic difference, it changed the headline.

Both are the same shape as §13.4 and §8b: the instrument was wrong, not the
run.

### 17.3 Contiguity, read before any effect size

Per composition, over `n_ues` × `lidar_ues` only (never across the
categorical composition axis, §16.1.2). Isolated cells out of 12:

| metric | drone_heavy | ugv_heavy | sensor_dense | mixed |
|---|---|---|---|---|
| **M07w** | 0 | 2 | 0 (of 9) | 0 |
| **M08w** | 0 | 3 | 0 (of 9) | 4 |
| **M02w** | 1 | 0 | 1 | 2 |

**M07w is cleanest and carries the boundary claim**, as §16.1.3 registered
from the stage-4 prior. **One deviation from that prior:** stage 4 rated
M02 *noisiest*, and here M02w is cleaner than M08w. Noted rather than
explained — one grid, and the windowed variants are not the panel metrics.

### 17.4 E1 — is the activation detectable at all? **HIT**

`ugv_heavy` N=32, `lidar_ues=2`, M02w over non-lidar flows in `during_2`
versus the paired control. All three arms worse beyond the within-seed
bootstrap CI:

| arm | mean Δ M02w | CI |
|---|---|---|
| PF | **+0.0391** | [+0.0379, +0.0405] |
| Reservation | **+0.0650** | [+0.0600, +0.0687] |
| TwoTier | **+0.1346** | [+0.1272, +0.1422] |

The falsifier (absorbed everywhere) did not fire. **TwoTier degrades 3.4×
more than PF** — the first of several places in this grid where the
QoS-aware arm is the one that suffers under a transient.

### 17.5 E2 — breaking fleet size: **HIT**, but the registered criterion was wrong

**As scored by the pre-registered criterion:** breaking N = **4**
(`ugv_heavy`), **8** (`drone_heavy`), **8** (`mixed`), none
(`sensor_dense`).

**That criterion is defective and its numbers must not be carried
forward.** It is `mean(on) < mean(control)` with no interval, so
`ugv_heavy` "breaks" at N=4 on TwoTier going **2.90 → 2.80 contracts** —
one seed losing one contract — while at N=32 the same metric collapses
6.70 → 1.60. E1 was registered *with* a paired CI and E2 without; that
inconsistency is the defect.

**Under E1's own test applied to E2 (POST-HOC, and labelled as such
wherever quoted):**

| composition | breaking N (corrected) | stage-4 onset (§15.4) | holds |
|---|---|---|---|
| `ugv_heavy` | **16** | 16 | ✅ |
| `drone_heavy` | **16** | 32 | ✅ |
| `mixed` | **16** | 32 | ✅ |
| `sensor_dense` | never ≤32 | never | consistent (both undefined) |

E2's expectation — breaking N ≤ onset N wherever both are defined —
**holds everywhere**. The falsifier (a transient being *easier* to absorb
than steady contention) did not fire.

Effect sizes at N=16 are large and unambiguous, not marginal:

| composition | PF | Reservation | TwoTier |
|---|---|---|---|
| `ugv_heavy` | −1.9 | −5.3 | **−9.9** |
| `drone_heavy` | −2.2 | −4.6 | **−9.4** |

**The finding worth carrying forward is not in the pre-registered
prediction at all: breaking N is 16 for ALL THREE compositions that
break.** Stage 4's steady-state onset was composition-dependent (16 / 32 /
32); under a lidar activation that dependence collapses to a flat
boundary. A transient does not merely shift the boundary down — it makes
composition stop predicting where it is. That is a stronger statement for
the hardware campaign than the registered expectation was, and it was not
predicted.

### 17.6 E3 — does H6's split extend to a transient? **HIT, and the polarity inverts with N**

Split observed in 2 of 3 compositions at N=16 and **3 of 3 at N=32**. Per
§0.1's rule, M07w and M08w are quoted together throughout.

| cell | M07w winner | M08w winner | split |
|---|---|---|---|
| `ugv_heavy` N=16 | **PF** | **TwoTier** | ✅ |
| `drone_heavy` N=16 | **PF** | **TwoTier** | ✅ |
| `mixed` N=16 | TwoTier | TwoTier | ✗ |
| `ugv_heavy` N=32 | **TwoTier** | **PF** | ✅ |
| `drone_heavy` N=32 | **Reservation** | **PF** | ✅ |
| `mixed` N=32 | **TwoTier** | **PF** | ✅ |

H6's construction survives the move from sustained load to a transient, so
§0.1 is **not** narrowed to sustained load.

**The new result is the inversion.** At N=32 the familiar pattern holds —
a QoS-aware arm concentrates and meets contracts, PF spreads and wins the
max-min floor. **At N=16 it runs backwards:** PF meets more contracts while
TwoTier holds the floor. M08w at `ugv_heavy` N=16, control → `lidar_ues=2`:
PF **0.949 → 0.155**, TwoTier **0.945 → 0.601**. PF's worst non-lidar GBR
flow keeps 15 % of its GFBR; TwoTier's keeps 60 %.

So §0.1.1's "the lesson generalises, the ranking does not" now has a third
demonstration, and a sharper one: the ranking inverts **within a single
grid as a function of N**, not merely between workloads. Any single-metric
claim about who wins is false by construction — now shown to be false in
*both directions inside one experiment*.

### 17.7 E4 — direction beats PDB tightness: **HIT**, on thin samples

E-stop M02w degradation in `during_2` was **exactly 0.0** in every
composition, while `tight_pdb` degraded most:

| composition (N=16) | estop | tight_pdb | non_lidar |
|---|---|---|---|
| `ugv_heavy` | 0.0 | **0.1615** | 0.1575 |
| `drone_heavy` | 0.0 | **0.2169** | 0.1494 |
| `mixed` | 0.0 | **0.2505** | 0.0479 |

E-stop was never the first flow to break, so the expectation holds and its
falsifier did not fire.

**The 0.0 was checked for being an empty selection before being reported,
and it is not** — 54 of 90 rows at the `ugv_heavy` N=4 cell carry a real
value and every one is 0.0. **But it rests on very little data:** at
0.2 Hz the e-stop generates 1–4 messages per 2.5 s window, 36 of 90 rows
are empty, versus ~426 completions per window for `tight_pdb`. So the
honest statement is **"the e-stop showed zero PDB violations across 54
windows carrying 1–4 messages each"**, not "the e-stop is robustly
unharmed". Three orders of magnitude separate the two subsets' sample
sizes.

**E4 does not bear on §15.5.** This grid varies flow count, GBR fraction,
UL share and tight-PDB density together. §15.5's discriminating experiment
— two profiles with identical flow counts and GBR ratios, tight-PDB flows
co-located on one LCG versus spread — **remains UNRUN**.

### 17.8 What this stage cannot say

- **No run-aggregate panel metric from a lidar-on cell is quoted anywhere
  above**, and `analyse_stage5.py` raises rather than warns if asked
  (§16.5). Every number in §17.4–§17.7 is windowed or a control.
- **Every contrast is a compound treatment** (C4), pending the
  provisioned-never-activated third level.
- **Latency is not certified.** These are estimates; hardware calibrates
  absolute latency (§0).
- The **corrected** E2 numbers are post-hoc. The registered criterion's
  output is in §17.5 and is what pre-registration entitles anyone to.
- `FIVE_QI_LCG` remains invented (§12.3), so anything downstream of LCG
  co-location — including E4's tight-PDB reading — inherits that
  `[OPEN: HARDWARE/DECISION]`.

### 17.9 End-of-stage judgment-calls review

The standing step (CLAUDE.md), run over stage 5's own diff looking for
undocumented decisions and silent bugs. Four found, none changing a number
above; recorded rather than quietly fixed.

1. **§16.5's exclusion is enforced by construction, not by a check in
   `main()`.** `aggregate_panel()` raises and is tested, but `main()` never
   calls it — it never aggregates a panel column across lidar-on cells in
   the first place, so there is nothing to intercept. The guard protects
   the *next* consumer, not this one. §16.5's wording ("the analyser
   raises if asked to aggregate") is true of the function and should not be
   read as a claim that the read path is dynamically checked.

2. **`wp9_window.lidar_windows()` duplicates `LidarActivation`'s defaults
   on its `lidar=None` path** (1.5 / 2.0 / 0.5), because the module
   deliberately imports nothing from `sim.fleet`. The values coincide today,
   so every control cell was scored at the right coordinates. The drift
   hazard is real but **not silent**:
   `test_control_cells_get_the_same_window_coordinates` compares the two
   paths directly and fails the moment a default moves on one side only.
   Left as-is; the alternative (importing `sim.fleet` into the pure metric
   module) costs more than it buys.

3. **C3 compares M02w on the `non_lidar` subset against a panel M02 that
   covers all flows.** Sound only because it runs on control cells, where
   `build_fleet` emits no 5QI-4 flow at all, so the two populations are the
   same set. It would be wrong on any lidar-on cell, and C3 is restricted
   to controls for exactly that reason.

4. **`n_lidar_active` is derived per cell from `build_fleet`, not observed
   per run.** Correct here — the allocation is deterministic in the axis
   values — but it means the column reports what was *provisioned and
   activated*, not what transmitted. That is the intended reading (§16.7
   B7) and is what makes the degenerate-cell census meaningful; a future
   consumer wanting "did it actually send" must not reuse this column.

**Not found:** any retention growth (the worker's summary is discarded and
pinned by a test), any scheduler-file change (none in this stage), any
panel edit (`config/metric_panel.yml` untouched, as §16.4 required), or
any `--capture` of the corpus (frozen at `9963be1` and `--check`-clean at
every one of the seven commits).

---

## 18. Truncated BSR — the mechanism `sim/bsr.py` does not have

### 18.0 Why this item, and what it is not

Commit 0b (§8a) established read-only that `sim/bsr.py` cannot express
`estimated_ul_buffer_per_lcg[L] == 0` while true backlog on `L` persists,
and committed to the sentence *the model lacks a mechanism; the fault is
real on hardware*. That scoping makes this **"add a mechanism"**, not
"enable a path".

Two things it unlocks, and they are separate:

1. **G2's real failure class.** The sim already measures STOP latency under
   ordinary contention — that is not the gap. What it cannot produce is the
   BSR/SR desync the UL service-interval floor exists to rescue, which is
   what GT-2.2 and GT-2.3 are built around. G2 currently has an estimate
   for the easy case and nothing for the case the guarantee is about.
2. **The floor becoming exercisable.** Every grid in this WP describes
   two-tier with its signature starvation guard inert or near-inert, so
   `docs/wp9-regime-map.md`'s scheduler comparison is a comparison of
   **two-tier-without-its-guard**.

### 18.1 TS 38.321 §5.4.5, transcribed from the spec — PRIMARY source

Transcribed from **3GPP TS 38.321 V17.5.0 (2023-06)**, §5.4.5 "Buffer
Status Reporting", Release 17, pages 73-74, via `pdftotext -layout` — the
same method WP6 used for TR 38.901. **Primary, not secondary**: the plan
for this item assumed only OAI's quoted comment block would be available
and pre-marked the provenance as secondary-source; the actual spec text
was obtainable, so that qualifier is withdrawn rather than carried.

Verbatim, for the non-IAB Padding BSR case:

> 1> if the number of padding bits is equal to or larger than the size of
> the Short BSR plus its subheader but smaller than the size of the Long
> BSR plus its subheader:
>
>   2> if more than one LCG has data available for transmission when the
>   BSR is to be built:
>
>     3> if the number of padding bits is equal to the size of the Short
>     BSR plus its subheader:
>
>       4> report Short Truncated BSR of the LCG with the highest priority
>       logical channel with data available for transmission.
>
>     3> else:
>
>       4> report Long Truncated BSR of the LCG(s) with the logical
>       channels having data available for transmission following a
>       decreasing order of the highest priority logical channel (with or
>       without data available for transmission) in each of these LCG(s),
>       and in case of equal priority, in increasing order of LCGID.
>
>   2> else:
>
>     3> report Short BSR.
>
> 1> else if the number of padding bits is equal to or larger than the size
> of the Long BSR plus its subheader:
>
>   2> report Long BSR for all LCGs which have data available for
>   transmission.

And on the timers (§5.4.5, page 74):

> 3> start or restart periodicBSR-Timer except when all the generated BSRs
> are long or short Truncated or Extended long or short Truncated BSRs;
>
> 3> start or restart retxBSR-Timer.

**The ordering rule is the load-bearing sentence** and is the one thing
that must never be written from memory: *decreasing order of the highest
priority logical channel **(with or without data available for
transmission)** in each of these LCG(s), ties by increasing LCGID.* Note
the parenthetical — an LCG's rank comes from its highest-priority channel
whether or not that channel currently has data, which is not the obvious
reading.

### 18.2 What OAI actually does, and where it diverges

Ground truth for the UE side is
`openair2/LAYER2/NR_MAC_UE/nr_ue_scheduler.c:2364-2432` (full checkout, not
the vendored subset — the vendored `nr_ue_scheduler.c` is a different
upstream directory per `oai-branches/README.md`). Sizes from
`NR_MAC_COMMON/nr_mac.h:92-110,137-153`: `NR_BSR_SHORT`=1,
`NR_BSR_LONG`=1, `SUBHEADER_FIXED`=1, `SUBHEADER_SHORT`=2, so
`short_bsr_sz` = **2**, `long_bsr_sz` = `n_lcg_with_data + 3`, and the
long-truncated floor is **3**.

| format | OAI condition | OAI reports | spec says |
|---|---|---|---|
| `b_short` | `n_lcg < 2 && padding ≥ 2` | 1 LCG | same |
| `b_long` | `padding ≥ n_lcg+3` | all 8 entries | LCGs with data (equivalent: empty LCGs encode 0) |
| `b_short_trunc` | `padding == 2` | **1 LCG while n_lcg ≥ 2** | same |
| `b_long_trunc` | `padding ≥ 3` | **all 8 entries** | **a priority-ordered PREFIX** |
| none | `padding < 2` | nothing | — |

**The divergence, anchored to OAI's own acknowledgement.** `b_long_trunc`
loops `for (int lcg_id = 0; lcg_id < 8; lcg_id++)` and fills every entry —
identical to `b_long` — directly under its own comment
(`nr_ue_scheduler.c:2419-2421`):

> `//  Fixme: this should be sorted by (TS 38.321, 5.4.5)`
> `// the logical channels having data available for`
> `// transmission following a decreasing order of the highest priority logical channel ...`

This is a **comment-vs-code finding in the same family as Phase 2's four,
with one difference that matters: here the comment ADMITS the gap** rather
than asserting something the code does not do. CLAUDE.md's rule (*port the
code, not the comment*) still governs what "faithful" means — and the
consequence is sharp: **ported faithfully, `b_long_trunc` cannot produce
the desync at all.** The only shipped path that can is `b_short_trunc`, at
a padding window of exactly 2 bytes.

**Decision (recorded, not resolved silently in either direction): build
both modes.** OAI-faithful is the default behaviour of the flag;
38.321's priority-ordered prefix is the second mode, a **deliberate
documented divergence**. The justification is that they are ground truth
for *different setups*: the calibration campaign's UEs are commercial
modems implementing the spec, while OAI's `nr_ue_scheduler.c` runs only in
rfsim. A real gNB therefore receives spec-truncated BSRs; an rfsim gNB
receives OAI-truncated ones. Building only the OAI path would leave the
desync route at a 2-byte window that may never fire on this corpus —
leaving the floor exactly as inert as it is today, which is the thing this
item exists to fix.

### 18.3 Three findings recorded while scoping

1. **Stage 3's `fires=9` was NEVER confirmed at scale — it is an open
   question, not a premise.** `sweeps/wp9/stage3.log` stops at **cell
   51/52**, `sweeps/wp9/stage3/` holds no artefacts, and this document has
   a stage-3 *plan* (§11) and **no stage-3 results section** — §12 goes
   straight to the re-scope. So `gate_passes=73285, fires=9` is from a
   **16-cell machinery smoke grid at horizon 1000** on a run that died and
   was superseded. §11's own note is properly hedged ("*If* the full run
   confirms this"), but `README.md` §9's "two-tier's UL floor fires and
   disarms correctly under the fruitless-counter logic" carried no marker
   that this is *unit-test* behaviour, which reads as established next to
   §7's statement that the floor never fires on this corpus. **Tightened in
   this commit.** Whether firing keys on `floor_rx_lastseen` (delivery not
   moving) rather than on the desync fault is **open, and §18.5 registers
   it as the thing to settle.**

2. **`tb_size` was already plumbed.** Commit 0b's forward note said
   truncated BSR "needs the *grant size* threaded into the BSR-assembly
   decision, which today reads only the active-LCG count". It does not —
   `on_ul_grant(ue_id, tb_size, ...)` already takes it and `sim/driver.py`
   already passes `alloc.bytes_capacity`. **Third instance of CLAUDE.md's
   forward-looking-note rule**, after `_dl_stamp`'s wrong citation and
   port-map row 46's wrong plan. Same shape as commit 0b's *other* wrong
   item (§8c): an assertion about code that already existed and could have
   been read. The rule already covers it; no new rule is needed. **What is
   actually missing is occupancy, not grant size** — see §18.4.

3. **The `b_long_trunc` Fixme** — §18.2 above; `docs/oai-port-map.md`
   row 4's Divergence cell is amended in this commit to cite it, since it
   is a statement about OAI's shipped code and true independently of what
   this repo builds.

### 18.4 Design

**Where it lives.** `sim/bsr.py::BsrModel.on_ul_grant`, replacing the
`len(active_lcgs)` branch with padding-keyed selection.

**The one real coupling is OCCUPANCY, not grant size.**
`padding_len = tb_size - filled_bytes`. `filled_bytes` is computed at the
call site already (`ue_filled_bytes`, `sim/driver.py`) and is not passed;
one additive parameter, defaulted so every existing caller and
`sim/tests/test_bsr.py` keep working unchanged.

**Modelling decision, stated rather than glossed:** this simulator has no
MAC PDU model — no per-SDU subheaders, no PHR, no LCP multiplexing — so
`padding_len` is an approximation of the real quantity by exactly those
omissions, **all of which make the modelled padding LARGER than reality**.
The bias direction is knowable and recorded here; the magnitude is not.
Consequence: modelled truncation fires *less* often than hardware would,
so a null result under this model is weak evidence about hardware, while a
positive one is not weakened.

**Opt-in and inert by default.** A model-level flag (default off) selects
the current branch byte-for-byte. **Prediction registered here:
`--check` clean on all 20 records.** If it moves, the flag is not inert —
that is information, not a re-baseline trigger. Deliberately *not*
unconditional: bundling a fidelity change of the class that moved 15 of 20
records into the same commit as a new mechanism destroys the attribution
the corpus exists for.

### 18.5 Pre-registered expectations

Registered before the mechanism exists, per §16.6's discipline.

1. **The floor fires under a constructed desync** — *and* the competing
   outcome is named: `_ul_has_pending_gbr` may **block arming in exactly
   the fault**, because it reads the same per-LCG estimate the floor exists
   to route around (README §7, ported faithfully and pinned by
   `test_ul_floor_has_pending_gbr_gate_reads_the_same_estimate_it_exists_to_route_around`).
   **Both outcomes are informative and the second is the more
   interesting** — it would mean the floor cannot rescue the fault it was
   built for, which is a statement about the deployed scheduler, not about
   this model.
2. **Arming and firing separate.** Instrument gate-passes and fires
   separately and attribute each fire to *desync* vs *ordinary starvation
   via `floor_rx_lastseen`*. This settles finding 1's open question at
   scale rather than from a smoke grid.
3. **G2's STOP statistic under the fault**, against the same scenario
   without it.
4. **Desync WIDTH: spec-truncation vs OAI-truncation.** Measured, not
   predicted in magnitude: **how many slots, and how many LCG-slots, hold
   `estimate == 0 while backlog > 0` under each mode.** If OAI-mode's width
   is zero on this corpus, that is the concrete statement of why the floor
   has been inert — and it is what makes the divergence worth having rather
   than an assertion that it is.

### 18.6 Commit sequence

1. **This document + the two doc corrections** (README §9's floor line,
   port-map row 4). Docs only.
2. `filled_bytes` plumbed, flag added, selection refactored — **inert**;
   `--check` prediction scored.
3. Guard test **shown failing first**, then `b_short_trunc`.
4. `b_long_trunc`, both modes.
5. A desync scenario + floor instrumentation; §18.5 scored.

The guard test's discriminating state is commit 0b's: `estimate == 0` with
`backlog > 0`, **persisting** across ≥N slots rather than self-correcting.
Route C already produces the one-slot version, so a single-slot assertion
would pass today and guard nothing.

---

## 19. The Padding BSR trigger — §18's mechanism, wired to the right trigger

### 19.1 The error, as a finding in its own right

§18 built the truncated-BSR formats and wired them to **every** BSR the
model assembles. That is wrong, and TS 38.321 §5.4.5 says so in the
heading of the very block §18.1 quoted verbatim.

The spec splits the format rules by **trigger kind**:

> **For Regular and Periodic BSR**, the MAC entity […] shall:
> 1> if more than one LCG has data available for transmission when the MAC
> PDU containing the BSR is to be built:
>   2> **report Long BSR for all LCGs which have data available for
>   transmission.**
> 1> else: 2> report Short BSR.

> **For Padding BSR**, the MAC entity […] shall: *(the padding-keyed rules,
> and the only place the truncated formats appear)*

And the triggers themselves (§5.4.5, page 73):

> - UL resources are allocated and number of padding bits is equal to or
>   larger than the size of the Buffer Status Report MAC CE plus its
>   subheader, in which case the BSR is referred below to as **'Padding
>   BSR'**;
> - retxBSR-Timer expires […] **'Regular BSR'**;
> - periodicBSR-Timer expires […] **'Periodic BSR'**.

**Truncation is a Padding-BSR phenomenon only.** A Regular or Periodic BSR
always reports a full Long BSR when several LCGs have data — the UE makes
room for it through logical channel prioritisation rather than squeezing
it into leftovers.

`sim/bsr.py`'s `pending` flag is set **exclusively** by regular / periodic
/ retx triggers. So every BSR this model has ever assembled is a Regular
or Periodic one — **precisely the class the spec forbids truncating.**
Applying the padding rules to them meant that in a loaded scenario, where
grants run nearly full, padding fell below 2 bytes, `_select_format`
returned "defer", and **no BSR was assembled at all, ever**.

**THE SELF-ASSESSMENT, KEPT RATHER THAN SOFTENED: the transcription was
correct and the reading of it was wrong.** §18.1 quotes "For Padding BSR"
verbatim, at the top of the block it transcribed, and the mechanism was
still wired to every trigger. **This is a distinct failure mode from this
project's existing comment/citation family** — `_dl_stamp`'s wrong
citation, port-map row 46's wrong plan, commit 0b's wrong argument — where
the source text was wrong, stale, or absent. **Here the source was right,
complete, and on the screen.** Quoting a heading is not the same as
honouring it, and no amount of transcription discipline substitutes for
asking *which of the things this section describes am I actually
building?*

### 19.2 What caught it — and it was not the tests

**An at-scale run producing an arithmetically impossible number.** The
study reported `desync_lcg_slots = 144000` for both truncated modes, and
`144000 = 6 UEs × 3 LCGs × 8000 slots` **exactly** — every LCG desynced in
every slot, with `gate_passes = 0` beside it.

**The unit tests could not have caught this, and the reason generalises.**
All 36 pass, because each one **constructs the padding condition
directly** — it hands `on_ul_grant` a `tb_size`/`filled_bytes` pair chosen
to land in the window under test. **A test that builds the precondition it
is testing cannot discover that the precondition never occurs in
practice.** The tests verified "given a 2-byte padding, the report is
short-truncated", which is true and remains true; what no test asked was
whether a 2-byte padding ever co-occurs with the trigger the model
actually uses. Recorded in `CLAUDE.md` beside the existing guard-test rule,
because it is the same shape as WP9 commit 1b/1c (a test pinning the
helper while the pipeline around it was broken) seen from the other side.

**The impossibility is why it cost minutes rather than a WP.** Both prior
instances of this class in WP9 produced numbers that were **wrong but
plausible** — the gate's `None`-base contamination selecting 1,710 rows,
and the CSV coercion scoring exactly `0.000`. This one factored cleanly
into the grid's own dimensions. **The reusable check is: "does this number
factor into the grid dimensions?"** A count that equals
`n_ues × n_lcgs × n_slots`, or any exact product of the run's shape, is
almost never a measurement — it is a saturated counter or an empty
selection wearing one.

### 19.3 Scope — a new trigger class, not a widened branch

**The machinery built in §18 carries over UNCHANGED.** The size constants
(`SHORT_BSR_SZ`, `LONG_BSR_FIXED_SZ`), the branch thresholds (0,1 → none;
2 → short_trunc; 3,4 → long_trunc; 5 → long), the per-LCG priority ranking
including the "with or without data available for transmission"
parenthetical, and the OAI-vs-spec prefix split are all correct and stay
as they are, with their tests. **This is re-wiring, not rebuilding** — the
formats were attached to the wrong trigger, they were not themselves
wrong.

What is added is the trigger:

| condition | BSR kind | format rules | may truncate? |
|---|---|---|---|
| `pending` | Regular / Periodic | today's branch, unchanged | **never** |
| not `pending`, `padding ≥ SHORT_BSR_SZ` | **Padding BSR (new)** | `_select_format` | **yes** |
| not `pending`, `padding < SHORT_BSR_SZ` | none | — | — |

**Why this is the mechanism and not a detour to reach it.** A Padding BSR
is an *opportunistic* report the UE volunteers because room happened to be
left over. When it is truncated it **overwrites the gNB's per-LCG array
with a partial view** — the memset repopulates only the reported LCGs and
leaves the rest at zero. That overwrite *is* the desync. Anything narrower
leaves truncation unable to fire lawfully, which leaves two-tier's floor
as inert as it has been for the whole WP, which is the hole §18 exists to
close.

**Timer consequences, from §5.4.5 and unchanged in substance:** any BSR
restarts `retxBSR-Timer`; `periodicBSR-Timer` restarts *except* when the
report is truncated. A Padding BSR is a real BSR, so it also clears
`sched_ul_bytes` — which means the crumb-collapse gate sees an extra reset
whenever one fires. That is a real behavioural consequence of the
mechanism, not a side effect to hide, and it is one reason the flag stays
opt-in.

**This repo's own "retx timer restarts on EVERY grant" behaviour
(README §4 WP3, a hardware-measured fact rather than a spec rule) is left
exactly as it is.** It already sits outside the `pending` check and is not
touched.

### 19.4 Unchanged from §18

- **Flag still defaults to `"off"`.** With the flag off no Padding BSR is
  ever generated, so the `pending`-only path is byte-identical to
  pre-§18 behaviour.
- **Corpus prediction unchanged: `--check` clean on all 20 records.**
- §18.5's four expectations stand as written and are scored after the
  re-wiring, not before.

Nothing is published — the §18 commits are local — and the flag has never
been on in any scenario, so this costs rework, not results.

### 19.5 Result — the trigger is right, and truncation still cannot fire

The re-wiring landed and is correct: Regular/Periodic BSRs are no longer
truncated, and the Padding BSR trigger exists. **Truncation still never
fires at scale, for a structural reason one level below the trigger.**

**Measured, on the same at-scale study that caught §19.1:**

| scenario | grants | padding > 0 | padding in 2..5 (the truncation window) |
|---|---|---|---|
| saturated (3 busy UL LCGs × 6 UEs) | 28,580 | **0** | **0** |
| lightly loaded (2 sparse flows × 2 UEs) | 110 | 80 | **0** |

Padding in this simulator is **bimodal: exactly 0, or large.** The
saturated run has backlog ≥ grant on every one of 28,580 grants, so the UE
fills the TB exactly. The light run leaves 42 / 90 / 111 / 126 / 235 bytes
spare — never the 2-5 bytes a truncated format needs.

**Root cause: this model has no TB-size quantisation.** `bytes_capacity`
is sized continuously against demand and capacity, so
`padding = grant − backlog` is either zero or a large remainder. Real
hardware picks a TB size from a **discrete MCS/TBS table**, so the chosen
size almost never equals the backlog exactly and a few bytes of leftover
padding is routine — which is precisely why Padding BSRs are an ordinary
occurrence on a real UE and why 38.321 defines truncated formats at all.
**The truncated formats exist to handle a quantisation artifact this
simulator does not have.**

**So the honest status of §18.5's expectations is: still unscored, and not
because the mechanism is wrong.**

- **E1/E2 (does the floor fire; do arming and firing separate):** measured
  `gate_passes ≈ 65,200, fires = 0` in every mode. The two halves DO
  separate — armed, never fired — which settles the open question from
  §18.3 at scale for the first time, and does so *without* a desync being
  present. Stage 3's `fires=9` is therefore still unreproduced.
- **E3/E4 (STOP statistic, desync width):** not answerable. The desync
  width is identical across `off`/`oai`/`spec` because the truncated path
  is unreachable.

**What would close it, and it is NOT in `sim/bsr.py`:** TB-size
quantisation in the grant-sizing path (`sim/resource.py` /
`scheduler/link.py`), so grants land on discrete TBS values and small
padding becomes routine. That is a new mechanism in a different module,
with its own corpus exposure, and it needs its own plan. It is also
independently motivated — TBS quantisation is a real effect this model
lacks everywhere, not only here.

> **CORRECTION (§20) — this paragraph is wrong twice, and is kept as
> written because it is the fourth link in this item's own chain.**
> (1) TB-size quantisation does **not** close it: measured
> counterfactually before any of it was built, quantising the TB moves the
> padding distribution by nothing at ×1.0 and *reduces* lawful Truncated
> BSRs at light load. The blocker is the **BSR-error magnitude at grant
> time** (§20.1). (2) `sim/resource.py` cannot host it either way —
> `scheduler/` may never import `sim/`, pinned by
> `test_scheduler_package_never_imports_sim` (§20.5). The independent
> motivation in the last sentence survives intact, and is the only reason
> the item still exists (§20.3).

**This is the third correction in this item, each one deeper than the
last**: truncation wired to every BSR (§19.1) → wired to the right trigger
but padding always 0 → padding never lands in the window because TB sizes
are not quantised. **Each was caught by the same check**, the one §19.2
added to `CLAUDE.md`: run it at scale and ask whether the precondition
occurs at all. The rule was written from the first correction and then
immediately caught the next two, which is the strongest evidence available
that it generalises.

**Not done, deliberately:** no scenario was constructed to land grants in
the 2-5 byte window. Tuning a fixture until the mechanism fires would be
fitting the measurement around the claim — the same failure this WP has
twice recorded avoiding.

---

## 20. TB-size quantisation — the mechanism, and the premise it does *not* rescue

### 20.0 The premise, tested BEFORE planning against it — and it does not hold

§19.5 closed with a forward claim: truncated BSR cannot fire because this
model has no TB-size quantisation, and quantisation in the grant-sizing
path is "what would close it". `28e6b36` carried that into the commit
message, README §7 and the regime map's G2 row.

**Measured counterfactually, that claim is wrong.** Per CLAUDE.md's own
forward-looking-note rule, the note was treated as a hypothesis for this
commit to verify, and the cheap discriminator was run first: a read-only
probe that replays every UL grant of a real run through OAI's actual
`nr_find_nb_rb`/`nr_compute_tbs` and recomputes the padding each grant
*would* have had. No repo file was changed to obtain these numbers.

On **`scripts/bsr_desync_study.py`'s own scenario** — the multi-LCG one
§19.5's `28,580/28,580` came from — at 4,000 slots, 6 UEs × 3 UL LCGs:

| offered load | UL grants | padding = 0 today | padding = 0 quantised | ≥2 LCGs with data | median \|BSR error\| there | **lawful Truncated BSRs: today → quantised** |
|---|---|---|---|---|---|---|
| ×1.0 (as measured in §19.5) | 13,214 | 13,214 (100 %) | **13,214 (100 %)** | **99.70 %** | 12,194 B | **0 → 0** |
| ×0.3 | 8,194 | 7,643 (93.3 %) | 7,597 (92.7 %) | 75.90 % | 543 B | **0 → 0** |
| ×0.1 | 6,593 | 3,542 (53.7 %) | 1,993 (30.2 %) | 35.05 % | 192 B | **5 → 4** |
| ×0.03 | 10,057 | 1,623 (16.1 %) | 547 (5.4 %) | 13.97 % | 191 B | **5 → 4** |

**Read the ×1.0 row across, because it contains the whole finding.** The
LCG half of the truncation conjunction passes on **99.70 %** of grants —
this scenario was built to make it pass — and the padding half fails on
**100 %** of them, before and after quantisation, because the median gap
between what the gNB thinks the UE has and what it actually has is
**12,194 bytes** against a window that is **2 to 5 bytes wide**.

**At the load the claim was measured at, quantisation changes the padding
distribution by nothing at all — 13,214 zeros before, 13,214 zeros after.**
At light load it changes it substantially and in the *wrong* direction: it
moves mass *out* of the small-padding buckets into ≥9 bytes, and the count
of lawful Truncated BSRs goes **down**, 5 → 4.

Same result on the corpus scenarios (4,000 slots, TwoTier,
`cqi_delay_slots=8`), padding in the 2–5 byte window:

| scenario | UL grants | 2–5 B today | 2–5 B quantised | ≥2 LCGs with data | median \|BSR error\| there | **lawful Truncated BSR** |
|---|---|---|---|---|---|---|
| `factory_robots` ×1.0 | 3,105 | 0.00 % | **0.00 %** | 19.13 % | 13,387 B | **0** |
| `factory_robots` ×3.0 | 3,648 | 0.44 % | 0.05 % | 15.43 % | 6,490 B | **0** |
| `sensor_dense` | 14,993 | 0.06 % | **8.61 %** | **0.00 %** | — (no such grant) | **0** |
| `factory_robots` ×1.0 / Reservation | 11,246 | 0.03 % | 0.03 % | 26.18 % | 24,504 B | **0** |

Every figure above is reproduced by `uv run python
scripts/tbs_counterfactual.py`, landed in the same commit as this section
so none of them is prose that can drift.

### 20.1 What actually blocks the path — a CONJUNCTION, and its two halves are anti-correlated

A lawful Truncated BSR needs three things at once (§18.1): padding ≥ 2,
**≥ 2 LCGs with data**, and padding < `n_lcg + 3` (or a full Long BSR
fits). The corpus fails a different half in each direction, and the two
halves move against each other:

- **The desync scenario at ×1.0, and `factory_robots`:** the LCG half
  PASSES — 99.70 % and 19.13 % of grants respectively have ≥2 LCGs
  backlogged — and the padding half fails **by three to four orders of
  magnitude**. The gNB's sizing input (`bytes_reported`) differs from true
  backlog by a median **12,194** and **13,387 bytes** on exactly those
  grants. A TBS lattice step of 5–64 bytes cannot bring a 12 kB error into
  a 2–5 byte window; nothing about the lattice is the operative quantity.
- **`sensor_dense`:** the padding half PASSES once TBS is quantised
  (0.06 % → **8.58 %** in the 2–5 window, because its BSR error is a
  median 66 bytes — small enough for the lattice to dominate) and the LCG
  half fails **totally**: all 14,993 granted UEs have exactly one UL flow,
  so 38.321's padding rules say *report Short BSR*, never truncated.

**And they are anti-correlated by construction, not by accident.** Loading
a UE until three LCGs are simultaneously backlogged makes its grants
PRB-limited, and a PRB-limited grant is filled exactly — padding 0,
whatever size the TB is. Unloading it until the grant has spare room
drains all but one LCG. That is the structural statement §19.5 was reaching
for, one level below where it stopped.

**So the binding constraint is the magnitude of the BSR error at grant
time, not the TB-size lattice.** Named here, deliberately not built:
diagnosing *why* `bytes_reported` sits 10¹–10⁴ bytes from truth is its own
item, and it is where G2's unlock now lives.

### 20.2 CORRECTION FOUR, and what is new about it

This is the fourth correction in the truncated-BSR chain (§19.5 recorded
three), and the first **caught before any code was written**. §19.5 wrote
that the rule which caught corrections one to three — *run it at scale and
ask whether the precondition occurs at all* — was the strongest available
evidence it generalises. Applying it to a **forward note** rather than to a
landed mechanism is the new part, and it is the cheaper place to apply it.

It is also the **fourth instance of the forward-looking-note rule**, after
`_dl_stamp`'s wrong citation, port-map row 46's wrong plan and commit 0b's
wrong argument — and a fifth *kind*: a wrong **diagnosis**, an inference
about a mechanism that was never run even in counterfactual. Cheaper to
catch than any of the other three, and only because the discriminator was
run before the plan rested on it.

**§19.5's finding is not withdrawn — it is narrowed.** "This model has no
TB-size quantisation" is true and remains a real fidelity gap. "That is
what blocks truncated BSR" is false.

### 20.3 The item that survives, on its own terms

TBS determination is wrong everywhere in this model, not only in the BSR
path, and that is why this item proceeds with the G2 unlock **removed from
its justification entirely**.

Today, at all six sizing sites:

```
prbs_needed = ceil(target * 8 / bits_per_rb)
prbs_used   = min(prbs_left, max_rb, max(1, prbs_needed))
tbs_bytes   = min(ue_backlog, (prbs_used * bits_per_rb) // 8)     # continuous
```

Ground truth computes `(nb_rb, tb_size)` **jointly**, by binary search over
a discrete table, and does **not** cap the result at the requested bytes.
Three consequences, each independently real:

1. **Grant sizing.** The two rules pick a different PRB count on **8.8 % to
   18.6 % of sizing decisions**, depending on MCS and slot shape — measured
   over `want` = 1..4000 by `scripts/tbs_counterfactual.py --sizing`,
   identical on 3,257/4,000 at 20 dB / 11 symbols (**18.6 %** differ),
   3,648/4,000 at 12 dB / 11 symbols (**8.8 %**), 3,529/4,000 at 20 dB /
   S-slot 7 symbols (**11.8 %**), differing by −1 to +4 PRBs elsewhere.
   The spread runs the other way from the intuition: the **high**-SNR case
   diverges most, because a bigger `bits_per_rb` makes each PRB a coarser
   step for the ceil-div to land on.
2. **Spectral-efficiency accounting.** At a fixed PRB count the quantised
   TB differs from the continuous one by **−1.8 % to +4.5 %** (mean 1.002
   on `factory_robots`, 1.020 on `sensor_dense`) — a per-grant error that
   the corpus currently carries into every throughput and utilisation
   figure.
3. **Every latency figure that depends on how much fits in one
   transmission**, via both of the above.

There is also a consumer already waiting and already flagged: port-map
row 8's Divergence cell says `sim/power.py::shrink_to_power_budget` takes
a caller-supplied `tbs_bits_fn` precisely because "a full Qm/code-rate MCS
table this sim doesn't have" — and that every existing test therefore
drives it with a synthetic non-3GPP table, verifying loop order and never
a real TBS number end to end.

### 20.4 Ground truth

**Mixed provenance, marked per source rather than averaged.**

| what | where | vendored? |
|---|---|---|
| `nr_find_nb_rb` — the binary search returning `(nb_rb, tbs)` | `oai-branches/reservation/gNB_scheduler_primitives.c:655-712` | **yes** |
| `nr_compute_tbs` — 38.214 §5.1.3.2 / §6.1.4.2, and `Tbstable_nr` (93 entries, Table 5.1.3.2-2) | `openair2/LAYER2/NR_MAC_COMMON/nr_compute_tbs_common.c:32-105` | **no — full checkout only** |
| `NR_MAX_PDSCH_TBS = 3824` | `common/utils/nr/nr_common.h:42` | no |
| `CEILIDIV` / `ROUNDIDIV` | `common/utils/nr/nr_common.h:347-348` | no |
| two-tier's own call sites (UL incl. the floor bypass; DL) | `oai-branches/two-tier/ia_p5g_scheduler.c:3250-3266`, `:1759-1792` | **yes** |
| MCS → (Qm, R) tables | `openair2/LAYER2/NR_MAC_COMMON/nr_mac_common.c:1960-2070` | no |

This is the **second confirmed case** of CLAUDE.md's "the vendored subset
is a convenience copy, not the evidence base" rule after
`nrmac->min_grant_prb`: the *caller* is vendored and the *callee* is not.

**Which procedure is modelled: OAI's `nr_compute_tbs`, not the spec prose.**
CLAUDE.md's measured-behaviour rule governs, and the C is what produced the
calibration numbers. Two places where that matters concretely, both to be
ported as written rather than as 38.214 reads:

- `nb_re = min(156, 12·nb_symb_sch − nb_dmrs_prb − nb_rb_oh) · nb_rb` — the
  156-RE cap is 38.214's, but note that at this repo's
  `overhead_factor = 0.85` a full slot is **11** symbols, so `12·11 = 132`
  and **the cap never binds**; DMRS, which the sim does not model, would
  otherwise have been absorbed by it. Recorded because it is the reverse of
  the intuition (at 14 symbols the cap makes DMRS irrelevant; at 11 it
  does not).
- `n = log2(Ninfo − 24) − 5` is a C `uint32_t` truncation of a double, and
  `Np_info = max(24, (Ninfo >> n) << n)` a shift, not a round.

**The split has one consequence with teeth, and it is not cosmetic.**
`sim/tests/test_bsr.py` can re-check the BSR tables byte-for-byte against
the C **on every test run** because `nr_mac_common.c` is vendored.
`Tbstable_nr` is not, so the same guard is impossible in-repo: a test can
only assert the table's own structural invariants (93 entries, strictly
increasing, known anchors) and check against the full checkout
*conditionally*, skipping where it is absent. That is strictly weaker than
what CLAUDE.md's spec-table rule normally buys, so it is stated here rather
than discovered later — and it is an argument for vendoring
`nr_compute_tbs_common.c` into `oai-branches/` as part of whichever commit
eventually builds this, not for weakening the rule.

**Spec cross-check, per the standing table rule.** `Tbstable_nr` is
transcribed from the C, and then checked byte-for-byte against TS 38.214
Table 5.1.3.2-2 obtained from the spec document itself (`pdftotext
-layout`, WP6's method), cited by table and page. If the primary text
cannot be obtained the provenance is marked **secondary-source** in the
module docstring and the test, the way §18.1's was before the spec text
turned out to be obtainable. Either way the table is pinned by a test that
re-checks it against the C on every run, exactly like
`sim/tests/test_bsr.py`'s BSR tables.

### 20.5 Where it lives — and §19.5 named one home that cannot work

§19.5 wrote "`sim/resource.py` / `scheduler/link.py`". **`sim/resource.py`
is ruled out**: a scheduler needs the TB size inside `allocate()`, and
`sim/tests/test_reservation.py::test_scheduler_package_never_imports_sim`
walks every file under `scheduler/` and forbids exactly that import. The
only way to reach it from `sim/` would be to put a `tbs()` method on the
`SlotView` protocol — which would also mean rewriting `ReducedSlotView` and
every `_FakeSlot` fixture, and would model the PHY *telling* the MAC its TB
size, which is not what ground truth does (`nr_compute_tbs` is a MAC-common
library function the scheduler calls).

**Home: a new `scheduler/tbs.py`, re-exported through `scheduler/__init__`.**
Not appended to `link.py`: `link.py` is the SNR→MCS staircase and is
explicitly documented as crude and comparative, whereas this is an exact
port of a spec table. Keeping them in separate files keeps the "crude
staircase" docstring from being read as covering the TBS table too.

**The six sizing sites it changes**, all reachable because
`sim/baselines/*` already import from `scheduler`:

| # | site | note |
|---|---|---|
| 1 | `scheduler/two_tier.py:1382` (B_eff branch) | the main UL/DL path |
| 2 | `scheduler/two_tier.py:1359` (floor branch) | **already structurally correct** — no backlog cap, sizes at `max_rbSize`, matching `ia_p5g_scheduler.c:3250`'s deliberate `nr_find_nb_rb` bypass. Needs only the TB size quantised, not the search. |
| 3 | `scheduler/reservation.py:973` | |
| 4 | `sim/baselines/pf.py:100` | |
| 5 | `sim/baselines/round_robin.py:80` | |
| 6 | `sim/baselines/gradient.py:150` | |

### 20.6 Design decisions

**D1 — Qm and R, which `_MCS_TABLE` does not carry.** `nr_compute_tbs`
needs `(Qm, R)`; `scheduler/link.py::_MCS_TABLE` carries spectral
efficiency only. OAI tabulates `R` as **ten times** the spec's `R×1024`
(`nr_compute_tbs_common.c:70-72`: `R_5 = R/5`, then `>>11`), so
`SE = Qm·R/10240`.

- **Chosen:** add `(Qm, R)` columns to the existing 12 rows, with `Qm`
  taken from 38.214 Table 5.1.3.1-1's own modulation boundaries and `R`
  **back-solved so SE is preserved exactly** (e.g. SE 3.50 → Qm 6,
  R 5973 → SE 3.4998, a 0.006 % residual). This keeps the commit's delta
  purely the quantisation lattice, with **no link-adaptation change
  smuggled in**.
- **Rejected:** replacing `_MCS_TABLE` with the real 29-row 38.214 table.
  More faithful, but it changes SE at every row, bundles link adaptation
  with TBS into one uninterpretable delta, and breaks
  `sim/olla.py::MCS_INDEX_COUNT = 12`, which was built against this table.
  **Named as its own future item, not done here.**
- **Recorded limitation:** back-solved `R` for the two extreme staircase
  rows falls outside any real MCS table's code-rate range (SE 0.15 → 0.075,
  below table 1's 0.117; SE 7.50 → 0.938, above table 2's 0.926). A
  consequence with teeth: `nr_compute_tbs`'s `R <= 2560` branch is then
  reachable only from the lowest rows. Asserted in a test rather than left
  implicit.

**D2 — port `nr_find_nb_rb`'s search, not just `nr_compute_tbs`.** Ground
truth returns `(nb_rb, tb_size)` jointly and both schedulers call it;
quantising the TB at the sim's own ceil-div PRB count would be an
intermediate state matching nothing. It is one fidelity change — "TBS
determination" — but it is landed in **two commits** (a pure, unwired
function first) so the study-level deltas stay attributable.

**D3 — the `min(ue_backlog, …)` cap is dropped, reversing Phase 2's D1.**
It has to be: `nr_find_nb_rb` returns `tbs ≥ want` by construction, and
re-clamping to backlog would put the TB straight back off the lattice,
which *is* the mechanism. D1's rationale — never manufacture bytes beyond
real backlog — is preserved by a different route that already exists:
`sim/ue_lcp.py::fill`, `two_tier._dl_fill`, `reservation._dl_fill` and
`sim/baselines/_mac.py::lcp_fill` all take `min(backlog, remaining)`, so
no over-delivery is reachable. **Pinned by a test rather than asserted**,
since it is now load-bearing. The gNB-side consumers that *should* see the
full `tb_size` — `sched_ul_bytes` credit, `ul_lcg_deficit_bytes` drain,
reservation's `expected_bytes` EWMA — are faithful to the C in taking it
(`gNB_scheduler_ulsch.c:2730`).

### 20.7 Corpus exposure, stated plainly

**Unconditional, this cannot be inert.** It changes the TB size of every
grant and the PRB count of ~9–19 % of them, on all six sites, on all five
arms. It is the class of change that moved 15 of 20 records.

**So it is opt-in, and the mechanism commit predicts `--check` clean.**
The flag is read once at `configure()` as
`getattr(grid, "tbs_model", "continuous")`:

- **no `Scheduler` protocol change** (`configure` keeps its three
  parameters) and **no constructor change on five arms**;
- `getattr` default keeps every existing `_grid()`/`_FakeSlot` fixture
  working untouched;
- it says the right thing: TB determination is a property of the **RAN**,
  which is what `grid` is, not of scheduling policy. Every real gNB
  quantises; `"continuous"` exists only as a corpus-freezing device and the
  docstring will say so.

**Then, separately and without capturing anything:** a one-off `--check`
with the flag forced on, recorded in this document as a **measurement** of
blast radius. That is not a re-baseline and must not be committed as one.

**Recommendation on the default: do not flip it in this item.** Flipping
invalidates the published numbers of stages 1, 2, 4 and 5 — the entire
evidence base of `docs/wp9-regime-map.md` — for a fidelity gain nothing
downstream is currently waiting on. It gets its own decision, with its own
re-run cost stated. **The re-baseline ceremony belongs to that decision,
not to this mechanism.**

### 20.8 The guard test — and the discriminating observable is NOT padding

§19.5's own framing ("today padding is bimodal and must become routinely
small") **would have produced a test that fails forever**, because §20.0
measured that quantisation does not move padding at ×1.0 at all. Writing
that test is how this item would have shipped a mechanism chasing an
observable it does not control.

**The discriminating observable is TB-size lattice membership.**

1. **Verified to fail first**, at scale, before any implementation: over a
   real run, assert that every UL `ue_grant` `Allocation.bytes_capacity` is
   a member of the TBS lattice for its `(prbs, symbols, Qm, R)`. Today TB
   sizes are backlog-valued, so this fails on essentially every grant —
   and the *count* of conforming grants today is recorded in the commit
   message, not just "it failed".
2. **A distribution, not a grant**: assert the conforming fraction over
   thousands of grants, both before (≈0) and after (=1.0).
3. **UL only.** DL `Allocation.bytes_capacity` is a per-flow LCP slice of
   the TB, not the TB — off-lattice by construction and correctly so. The
   test asserting that is part of the same commit, so a future reader does
   not "fix" DL to match.
4. **The precondition check that §19.2's rule demands is already done** —
   §20.0 — and it came back **negative for padding** and **positive for
   lattice membership**. That is the whole reason the observable moved.

### 20.9 Pre-registered expectations

Registered before the mechanism exists. Several are deliberately
**null** predictions: §20.0's counterfactual says so, and a null that is
scored is what tests whether the counterfactual was right.

| # | expectation | competing outcome, named |
|---|---|---|
| **E1** | `--check` clean on all 20 records with the flag off. | Any drift means the flag is not inert — information, **not** a re-baseline trigger. |
| **E2** | Padding on the desync scenario at ×1.0: **13,214 / 13,214 grants at exactly 0, unchanged.** | If padding moves at ×1.0, the probe's model of the LCP fill was wrong, and §20.0's correction needs re-deriving. |
| **E3** | **Truncated BSR still never fires** at ×1.0 (0 → 0), and at ×0.1/×0.03 the count does **not increase** (5 → ≤5). | An increase would mean the lattice reaches further into the window than the counterfactual showed. |
| **E4** | Floor `gate_passes ≈ 65,200`, `fires = 0`, **unchanged** — the two halves still separate, still with no desync present. | A fire would be the first at scale and would supersede §19.5's reading, not confirm it. |
| **E5** | G2's STOP statistic **unchanged** vs. the same scenario without the flag. | — |
| **E6** | *(the one that must move)* With the flag on: **100 %** of UL `ue_grant` TB sizes on the lattice (from ≈0 %); PRB counts differ from today on **8–19 %** of sizing decisions; mean TB size **up**, since the backlog cap is gone. | If TB sizes stay off-lattice anywhere, a sizing site was missed — there are six, and one (the floor branch) needs different treatment. |
| **E7** | Blast radius, measured not predicted: how many of 20 records move with the flag **forced on**, and in which direction on M02 / M11 / M12. | Registered as a measurement, per §18.5's E4 precedent. |

**E2–E5 are null predictions on purpose.** If this item were justified by
the G2 unlock they would be its failure; it is justified by §20.3 instead,
and they are the honest statement of what it does not buy.

### 20.10 Status — PLANNED AND UNBUILT, deliberately, and that is a state

**Only commit 1 below is taken. The mechanism is not built, and that is a
decision rather than a deferral.** The reasoning, recorded so a later
reader does not mistake it for something that ran out of time:

- **The discriminator answered the question the item was proposed on.**
  §20.0 was run before the plan rested on it, and it removed the urgent
  half of the justification.
- **What remains is real but has no consumer.** §20.3's fidelity gap is
  genuine, and nothing downstream is waiting on it.
- **It is opt-in only (§20.7), so building it changes no published
  number** — and flipping the default *would* invalidate stages 1, 2, 4
  and 5, i.e. the entire evidence base of `docs/wp9-regime-map.md`, for a
  fidelity gain with nothing to spend it on.

So the item sits fully specified — ground truth located and its provenance
split marked (§20.4), a home chosen and one candidate ruled out (§20.5),
three design decisions taken with their rejected alternatives (§20.6),
corpus exposure faced (§20.7), a guard test whose observable is settled
and whose precondition is already measured (§20.8), and seven
pre-registered expectations (§20.9). **Anyone taking it up starts at
commit 2, not at scoping.**

**Commit 1 — taken now.** This section, `scripts/tbs_counterfactual.py`
(landed, not left in a scratchpad: a committed document now carries its
numbers, and a count in prose is a claim about code that drifts), and the
three corrections §20.0 forces in already-committed documents — README §7's
fourth-dormancy-category entry and `docs/wp9-regime-map.md`'s G2 row, both
of which currently name TB-size quantisation as what closes G2, and
§19.5's "`sim/resource.py` / `scheduler/link.py`", which names a home that
cannot work. Those are wrong where they stand and do not wait on a build.
Plus CLAUDE.md's line for correction four. **Docs, probe and corrections
only — no mechanism, no flag, no scheduler change.**

**Commits 2-7 — specified, not taken.** For whoever picks this up:

2. `scheduler/tbs.py` — `nr_compute_tbs`, `nr_find_nb_rb`, the 93-entry
   table with the structural + conditional-vs-full-checkout test §20.4
   describes, and `_MCS_TABLE`'s `(Qm, R)` columns. **Unwired, inert by
   construction.** Full suite + `--check`.
3. The guard test **shown failing** with its conforming-grant count
   recorded, then the six sizing sites behind `grid.tbs_model`, default
   `"continuous"`. E1 scored. Port-map rows land here, same commit as the
   mechanism per the standing rule, citing vendored and non-vendored
   sources separately and amending row 8's `tbs_bits_fn` cell.
4. Flag on: the E2–E6 run, scored — hits and misses both.
5. The blast-radius measurement (E7): `--check` with the flag forced on,
   recorded as a number. **No `--capture`.**
6. The default-flip decision, if it is ever wanted, with its re-run cost
   stated. Separate from every commit above.
7. End-of-item judgment-calls review.

### 20.11 What this item does not do

- **It does not unlock G2.** §20.0/§20.1. G2's blocker is now identified as
  the **BSR-error magnitude at grant time**, and that is a separate item
  with its own plan.
- **It does not flip the default** (§20.7), and it does not re-baseline.
- **It does not replace `_MCS_TABLE`** with the real 38.214 table (D1).
- **It does not add a MAC-PDU model.** No subheaders, no RLC segmentation,
  no LCP packing granularity — §18.4's stated omission is unchanged, and
  the bias direction it records (modelled padding **larger** than reality)
  still holds.
- **It does not tune any scenario until the mechanism fires.** §19.5
  declined that and so does this.

---

## 21. Stage 6 — the unrun guarantees (plan, registered before anything runs)

### 21.1 Scope

**In:** G4, G6, G12, and H2/H3's two Category-2 axes (`duty_cycle`,
`snr_spread_db`). These are the ones the regime map records as *unrun or
uncomputed*, not as unbuildable — every mechanism and every axis they need
already exists in `sim/parametric.py` and `scripts/wp9_sweep.py`.

**Out, and separately scoped:** **G9** (a 50-cycle join campaign) and
**G11** (a soak) — both budgeted in §6.3 and never implemented; they need
scenario construction and a runner shape this stage does not have, and
they get their own plan. **§15.5's discriminating experiment** likewise: it
needs two new fleet profiles built to hold flow count and GBR fraction
fixed, which is composition-design work, not a sweep.

### 21.2 THE INVENTORY, TAKEN FIRST — most of this is already run

Measured against the stored artefacts before any grid was designed,
because "unrun" in `docs/wp9-regime-map.md` turns out to mean two
different things and only one of them costs runs.

| what | levels present | rows | verdict |
|---|---|---|---|
| `bg` | `True` (base is `False`, in the core plane) | 30 | **G6 computable now** |
| `duty_cycle` | 0.5, 0.1 | 30 each | **H2 computable now** |
| `snr_spread_db` | 6.0, 12.0 | 30 each | **H3 computable now** |
| per-flow GBR data on stored records | all stages | — | **G12 / M13 computable now** |
| `completion_ts_by_role_s` (WP7 ledger) | all stages | — | **partial for G4** — see §21.4 |

30 rows = 3 arms × 10 seeds, and the excursion cells carry the **identical
seed set** as the base cell (`n_ues=8`, `load_mult=1.0`) — verified, not
assumed — so every one of these is a **within-seed paired** comparison
against the base, which is the strongest form available.

**What is genuinely missing is DEPTH, not the axis.** Each of G6/H2/H3 has
exactly **one cell**, at the base point. That supports "is there an effect
at N=8, load ×1.0" and supports nothing about how the effect moves with
fleet size or load. The regime map's "not tested" is therefore too strong
for H2/H3 and its "computable from stage-1 rows but was not computed" for
G6 is exactly right.

**So Part A is analysis with zero new runs, and it runs FIRST** — because
what it finds determines whether Part C's grid is worth buying at all.

### 21.2a A hypothesis I checked and dropped, recorded rather than quietly discarded

`M09.status` is `proxy` and `M19.status` is `pending` on **1,770/1,770**
stage-1 rows, 7,560/7,560 stage-2 and 1,440/1,440 stage-4. That looks
exactly like §1's `record_timeseries=True, always` guard having failed —
which would have put a full re-run of three stages into this plan's budget.

**It has not failed, and the reading was mine, not the data's.**

- **M09's `proxy` is its registered panel status, not a degradation.** It
  carries a real value on every row (`M09.worst` populated 1,770/1,770,
  `M09.windows` = 5, matching the 5.0 s horizon exactly), and the note says
  why it is `proxy`: *"computed over all flows in the record with
  timeseries data — pass a same-role flow subset upstream if that's what
  the guarantee needs."* A flow-subset caveat, nothing to do with
  timeseries presence.
- **M19's `pending` note is "no join/re-join/re-establishment events
  occurred this run"** — structurally true of every WP9 scenario, and
  precisely what G9's campaign would supply. Not a missing flag.
- **M04's `proxy` is WP7's deliberate disposition**, already in CLAUDE.md.
- Confirmed by direct execution, not by reading: a fresh
  `record_timeseries=True` run populates `ts_delivered_bytes` on **12/12**
  flows and still scores M09 `proxy` / M19 `pending`.

**And the strip is by design, not a leak.** `scripts/wp9_sweep.py`'s
`_RecordSink` scores online *before* persisting and strips the per-slot
arrays from a `to_dict()` **copy**, so the live `RunRecord` the CSV is
scored from is untouched. Its own docstring says so.

Recorded because the wrong reading would have bought three stages of
re-runs that nothing needs — and because it is §20.0's discipline applied
to my own hypothesis rather than to an inherited one.

**And it is the first CONCRETE argument for building G9, so it is written
down here rather than left to be re-derived when G9 gets its own plan.**
M19 (`slo_recovery_time`) has read `pending` on **every row of every stage
this WP has run** — 1,770 + 7,560 + 1,440 — and the reason is not a flag,
a horizon, a scenario-coverage gap or anything a sweep axis can reach: *no
join/re-join/re-establishment event occurs in any WP9 scenario, because
none of them configures `UEConfig.join`*. **Nothing except a join campaign
can move it.** So G9 is not merely "budgeted and never run" — it is the
only thing that turns one of the panel's nineteen metrics from structurally
absent into scored, and M18 with it. That justification is now **measured
rather than assumed**, and G9's own plan should open from it.

### 21.3 Part A — the analysis pass (zero new runs)

| G/H | statistic | source |
|---|---|---|
| **G6** | GT-4.1's own delta: Δ on M01 p98 / M03 / M05, `bg=True` vs base, **≤ +20 % relative**, paired within-seed, bootstrap CI over the 10 pairs | `stage1_rows.csv` |
| **H2** | Δ per arm at `duty_cycle` 0.5 and 0.1 vs base, on the arm-separating metrics (M07/M08), paired | `stage1_rows.csv` |
| **H3** | same at `snr_spread_db` 6 and 12 | `stage1_rows.csv` |
| **G12** | `Scorecard.first_violation_order()` over stage 1's ascending `load_mult` column at each N, **and** over stage 4's fleet profiles — the thing the regime map says was never extracted | `records.jsonl` (stage 1, stage 4) |

**The pairing hazard, named because this project has already been bitten by
it.** Excursion rows carry the **empty string** for every axis they do not
vary — `bg` is `''` on 1,740 of 1,770 rows, `duty_cycle` and
`snr_spread_db` on 1,710. **1,710 is exactly the row count behind
CLAUDE.md's recorded `None`-base contamination bug.** So the analyser
**must**:

1. **coerce at the boundary** — every axis level read from CSV is cast back
   to its declared type against `wp9_sweep.BASE`'s own values (the
   `'True'`-vs-`True` failure is already recorded in CLAUDE.md);
2. **fill blanks from `BASE` explicitly**, never treat `''` as a level;
3. **assert cell size before scoring anything**: `len(cell) == n_arms ×
   n_seeds` = 30, and assert the base and excursion seed sets are *equal*,
   not merely the same size.

A cell that selects 0 or 1,710 rows must raise, not score.

### 21.4 Part B — G4, the one that genuinely needs a run

**Why it cannot come from stored records.** G4's statistic (§5(a)) is *M01
over the post-silence message subset*. The stored ledger field
`completion_ts_by_role_s` gives per-message **completion timestamps**;
per-message **arrival** times are on no record, and `RunRecord` keeps only
aggregate delay percentiles. Completion timestamps alone identify *which*
message follows a silence but not *how long it waited*.

**Rejected: reconstructing arrivals from the traffic config.** For a
`_burstify`-shaped periodic flow the arrival grid is deterministic, so
latency looks recoverable — but it holds only for `periodic_control`, not
for the `poisson` and `xr_video` flows in the same fleet, and it would make
the headline number depend on an inference about the generator rather than
on a measurement. That is the shape of error this WP has recorded three
times.

**Chosen: a `run_sink`.** `regime_sweep.sweep()` already calls
`run_sink(record, axis_values, summary)` with the **live** summary, before
any sink strips anything, and `sim/driver.py` already exposes
`summary["_message_ledger"]` for exactly this ("lets a study inspect raw
per-message completions beyond the percentiles"). So G4's read is a
study-layer `run_sink` that extracts post-silence first-message latency
per flow and discards the ledger — **no panel change, no M20, no
`sim/` change**, exactly as §5(a) pre-registered.

**The cells:** the `duty_cycle` excursion, which is also H2's axis — one
grid buys both, and G4's silence structure *is* the duty cycle.

### 21.5 Part C — depth, and its go/no-go stated BEFORE Part A runs

Registered now so Part A cannot be read to justify whatever grid I want
afterwards:

- **Buy the grid for an axis iff** Part A shows, on that axis, a paired
  effect whose bootstrap CI excludes zero on **at least one arm** for **at
  least one panel metric**, at the single cell available.
- **Otherwise record "no effect at the base point, depth not bought"** and
  stop. A null at N=8/×1.0 is a real result about the base point and is
  reported as one — it is not licence to go looking at other cells until
  something separates.
- **The grid, if bought:** the axis crossed with `n_ues` ∈ {4, 8, 16, 32}
  at `load_mult` ×1.0, plus `load_mult` ∈ {0.75, 1.0, 1.5} at N=8 — a
  cross, not a full factorial, because a full factorial on three axes at
  once is what §0.4's cap existed to prevent.

### 21.6 Pre-registered expectations

| # | expectation | competing outcome |
|---|---|---|
| **F1** | **G6 passes its ≤ +20 % bar on all three arms** at the base point. `bg` scored 2.648 at stage 1's gate — above the 1.0 threshold, so it does *something* — but the guarantee's bar is a 20 % relative delta, which is a much weaker demand than separation. | A fail on any arm is the more interesting outcome and makes `bg` a primary axis, not an excursion. |
| **F2** | **H2 does NOT hold in its registered direction.** The regime map already records stage 5's transient contradicting it (TwoTier lost most on the burstiest workload tried). I expect `duty_cycle` 0.5/0.1 to show either no separation or separation **against** two-tier. | H2 holding as originally written would mean stage 5's transient is not the same phenomenon as burstiness, which is itself worth knowing. |
| **F3** | **H3 separates the arms** — `snr_spread_db` scored 4.689, the highest of the four genuinely-untested Category-2 axes. | A null here would say the gate score was driven by variance, not effect, and would weaken §0.4's "11 of 12 axes cleared" defence of the gate. |
| **F4** | **G12's first-violation order is the same across arms** at a given N, and differs across **fleet profiles** (stage 4) more than across arms. M13 orders 5QI classes by when they first fail; that ordering is mostly a property of the workload's PDB/GFBR spread. | An arm-dependent ordering would be a genuine scheduler-differentiating result and the strongest thing this stage could produce. |
| **F5** | **G4's post-silence first-message latency exceeds the steady-state p98 on at least one arm** at `duty_cycle` 0.1 — the SR/BSR cold-start path is exactly what WP4 rebuilt, and a 90 %-silent flow re-enters it constantly. | No excess would say the `ul_access` SR path fully absorbs resumption, which would be a strong positive result for WP4's mechanism. |
| **F6** | Part A changes **no** committed number — it computes statistics never computed, it does not re-score anything. `--check` untouched, no re-baseline. | Any movement means the analyser is re-scoring rather than reading, which is a defect in the analyser. |

**F2 gets a direct-cause trace if it misses — registered as an obligation,
not left to judgement.** F2 is this stage's registered
most-likely-wrong expectation, and in this WP that slot has twice carried
the more interesting finding than the hits did: stage 4's E2 produced
§15.5's tight-PDB/LCG-co-location hypothesis, and stage 5's E2 produced the
flat transient boundary and the correction that its criterion had no
interval. So if F2 misses — if `duty_cycle` separates the arms *in H2's
originally registered direction* after all — it gets a
**worktree-instrumented direct-cause trace before the write-up**, in the
manner CLAUDE.md's cross-direction invariants require, not another pass of
reading. The competing possibility the trace must distinguish: that stage
5's transient and a duty-cycled steady state are **not the same
phenomenon**, which would mean the regime map's current H2 row is
conflating two different things rather than merely being unrun.

### 21.7 Budget

**Part A: zero runs.** Analysis over `sweeps/wp9/stage{1,4}/`, minutes.

**Part B (G4):** the `duty_cycle` excursion is 3 levels × 3 arms × 10
seeds at N=8. At §6.3a's **measured** 303 s per (3-arm × 10-seed) cell at
N=8, horizon 20,000, `record_timeseries=True` — 2 non-base cells ≈ **10
min serial**, less at 10 workers.

**Part C, if bought:** ~10 cells spanning N=4..32; at §6.3a's measured
81/303/1093 s for N=2/8/32 that is **~1.5-2 h serial**, ~15 min at 10
workers.

**Per §6.3a's own rule — time the thing you are actually going to run.**
Every number above is read off §6.3a's measured table at the same horizon
and flags, not scaled from a smaller one; but Part C's grid gets **one
probe cell timed end-to-end with its real post-processing** before the
full grid launches, because that is the rule that table exists to enforce.

### 21.8 Commit sequence

1. This section. Docs only.
2. **Part A's analyser**, with the §21.3 coercion/cell-size assertions and
   its own tests — including a test that a `''`-blank axis level raises
   rather than selecting the 1,710-row base. Reports G6/H2/H3/G12.
   **F1-F4 and F6 scored.**
3. **Part B's `run_sink`** for G4 + the `duty_cycle` run. **F5 scored.**
4. **Part C**, only if §21.5's go/no-go fires, with the probe cell timed
   first.
5. `docs/wp9-regime-map.md` §2's G4/G6/G12 rows and §3's H2/H3 rows
   rewritten from results — the point of the whole stage.
6. End-of-stage judgment-calls review.

Full suite + `--check` after each. Part A and Part C touch no `sim/` or
`scheduler/` file at all; Part B touches neither either — it is a
study-layer sink, per §5(a)'s "no M20 is added" constraint.

### 21.9 The regime-map correction is TWO-SIDED, and both sides land together

Commit 5 above rewrites `docs/wp9-regime-map.md`'s G4/G6/G12 and H2/H3
rows. **Both halves of the correction go in that one commit, and they are
stated as two different errors rather than folded into one**, because a
reader who acts on them does different things:

- **G6's "computable from stage-1 rows but was not computed" is
  ACCURATE.** The rows are there, the statistic was not run. Nothing to
  correct — it is confirmed, and saying so matters, because confirming one
  half is what makes the other half's correction legible as specific rather
  than as a general loss of confidence in the row.
- **H2/H3's "not tested" is TOO STRONG and is an UNDERSTATEMENT of
  coverage.** The excursion rows exist on disk, paired within-seed against
  the base cell, 30 rows per level. A reader who took "not tested" at face
  value was told the map covers **less** than it does.

**And that is a different error from the one §0.4 already corrects, which
is why they must not be merged.** §0.4 corrects an **overstatement** — the
cap did the narrowing rather than the score, so a stage-2 result on a
cap-selected axis is weaker evidence than §6.4 assumed. This one runs the
other way: an axis reported as absent that is in fact present but shallow.
The two have **opposite failure modes in a reader** — §0.4's makes someone
trust a result more than they should; this one makes someone commission
work that is already on disk. Writing them up as "the coverage claims were
imprecise" would lose exactly the distinction that tells a reader which
mistake they are at risk of making.

The corrected H2/H3 rows therefore say **"tested at one cell, paired,
`n`=30 per level — result X; depth beyond the base point not bought
(§21.5)"**, never a bare "tested" or a bare "not tested"; the depth
qualifier travels with the row for the same reason §0.1's two-number rule
and G11's inline seed-count rule exist.

---

## 22. Stage 6 Part A — results, scored against §21.6

Zero new runs. `scripts/analyse_stage6.py` over `sweeps/wp9/stage{1,4}/`;
every figure below is reproduced by `uv run python
scripts/analyse_stage6.py sweeps/wp9`.

### 22.0 Three defects the first run of the analyser found in itself

Recorded because all three would have produced a plausible published
number, and because two are re-instances of failure modes already in
CLAUDE.md.

1. **The G6 verdict read the point estimate, not the interval.** TwoTier's
   M01.p98 impairment is **+74.9 %** against a +20 % bar — and its CI is
   **[−24 %, +211 %]**. The first version printed **FAIL**. That is reading
   a number the data does not support: the interval spans both zero and the
   bar. Fixed to PASS / FAIL / **INCONCLUSIVE**, tested against the
   interval (`g6_verdict`, pinned by a test built from this exact cell).
2. **G12's ramp axis was assumed, and an empty selection printed a
   plausible summary.** Stage 4 ramps `video_tier`, not `load_mult`;
   passing the wrong axis matched **zero** records and the function printed
   *"distinct orderings across groups: 0"* — the third instance in this WP
   of an empty selection wearing a real-looking number. It now **raises**,
   naming the record count it scanned.
3. **The impairment flip was applied to the point only.** For the
   higher-better M05.fraction the sign flips, and flipping the point while
   leaving `lo`/`hi` alone leaves the bounds reversed — every M05 verdict
   silently inverted. Fixed and pinned (`impairment_interval`).

A fourth, not a defect but a bias that must travel with the number: a
**relative** delta is undefined off a zero base, so seeds whose base value
is 0 are dropped — and for M05.fraction those are exactly the seeds where
the base run was **already failing completely**. 7 of 10 seeds drop on
Reservation and TwoTier. **The drop is not random; it biases M05
optimistic**, and the analyser prints the dropped count on every affected
cell.

> **Interval provenance (added later).** Every bootstrap interval in §22
> and §22.1b was produced by `analyse_stage6.py` / `g6_seed_extension.py`
> **before `e95d6ee`**, when both seeded `bootstrap_ci` with `hash(...)` —
> which Python salts per process. **Point estimates, medians and every
> PASS/FAIL/INCONCLUSIVE verdict are unaffected** (all are deterministic
> functions of the data, and re-running under the fixed crc32 seed flips no
> verdict and no exclude-zero flag). **The CI BOUNDS will not reproduce
> exactly** — recomputed, they move by ≈0.01–0.05 in the metric's own units
> (e.g. §22.2's TwoTier M08 at 12 dB reads [+0.453, +0.939] here and
> [+0.418, +0.893] on recomputation). Not recomputed in place, per the rule
> that a bound is only worth re-deriving when a verdict sits near a
> boundary; none does. **The one cell closest to a boundary is §22.2's
> TwoTier M07 at 6 dB, whose lower bound sits at −0.100 — it is *not*
> marked as excluding zero, and it stays unmarked on recomputation.**

### 22.1 F1 — G6 passes its ≤ +20 % bar: **PARTIAL**

Paired within seed, `bg=True` vs the base point, n=10 (n=3 where noted).

| arm | M01.p98 | M03.max_gap_ms | M05.fraction |
|---|---|---|---|
| **PF** | −0.02 % **PASS** | +3.7 % **PASS** | +0.13 % **PASS** |
| **Reservation** | +0.00 % **PASS** | +9.0 % [−8.3, +28.7] **INCONCLUSIVE** | +0.22 % **PASS** *(7 seeds dropped)* |
| **TwoTier** | **+74.9 %** [−24.3, +210.7] **INCONCLUSIVE** | **+157.0 %** [−14.1, +460.8] **INCONCLUSIVE** | +6.2 % **INCONCLUSIVE** *(7 dropped)* |

**No arm fails, and only PF cleanly passes.** F1 predicted a pass on all
three arms; it holds for PF, is undetermined for TwoTier on every metric,
and is mixed for Reservation. **PARTIAL.**

**The undetermined cells are not a null.** TwoTier's point estimates are
+74.9 % and +157.0 % — many times the bar — with intervals wide enough to
contain zero at n=10. **What this cell needs is more SEEDS, not more
cells**, and that is a different investment from §21.5's grid.

### 22.1a DECISION — buy seeds at the G6 cell, and the stopping rule that makes it legitimate

**This is outside §21.5's registered rule, stated plainly rather than
slipped in as an extension of it.** §21.5's go/no-go governs
**depth-in-cells** — whether to cross an axis with `n_ues`/`load_mult` —
and says nothing about **seed count** at a cell already run. Reading it as
covering both would be widening a pre-registered rule after seeing the
data, which is the thing pre-registration exists to prevent. So this is a
**new decision**, taken here, with its own registration.

**Decision: buy it.** Two reasons, and neither is "the number looked
interesting":

1. **The shape says n is the binding constraint, not the effect.** +74.9 %
   and +157.0 % against a +20 % bar, with intervals spanning zero, is what
   a real effect under-sampled looks like — not what absence looks like.
   Absence would be a point estimate near zero with a tight interval, which
   is exactly what PF shows on the same cell.
2. **G6 is client-facing and its row currently says nothing.** "Not
   answered" on a guarantee the campaign has to make a call about is worse
   than "undetermined at n=40", which is at least a bounded statement.

**Registered BEFORE running, because otherwise this becomes sampling until
the interval excludes zero:**

- **n = 40 total.** `regime_sweep.paired_seeds` is prefix-stable
  (`paired_seeds(40)[:10] == paired_seeds(10)`, verified), so the existing
  10 seeds are reused unchanged and **30 new paired seeds** are run on the
  `bg=True` cell **and** the base cell. n=40 is 4× the current sample, so
  the interval narrows ~2×; it is chosen as an affordable one-shot, not as
  the n that would make the answer come out.
- **ONE LOOK. No interim analysis, no extension.** The verdict is read once
  at n=40 with the same `g6_verdict` on the same three metrics and the same
  paired-within-seed design. **If it is still INCONCLUSIVE at n=40, that is
  the reported result**, G6's row says "undetermined at n=40", and the
  question is closed for this WP rather than resampled.
- **No metric or arm is added or dropped after the fact.** M01.p98 /
  M03.max_gap_ms / M05.fraction, three arms, as already run.
- **The M05 optimistic bias (§22.0) still applies** and is reported with
  the number; more seeds does not fix a non-random drop, it only makes the
  dropped count larger in absolute terms.

**Pre-registered expectation (F7):** at n=40, TwoTier's M01.p98 and
M03.max_gap_ms both resolve to **FAIL** — the point estimates are 3.7× and
7.9× the bar, so if they are real at all the interval should clear +20 %
once it halves. **The competing outcome, named:** they collapse toward zero
instead, which would mean the n=10 point estimates were driven by one or
two extreme seeds — in which case the *seeds*, not the arms, are the
finding, and the per-seed deltas get printed.

### 22.1b G6 at n=40 — RESULT, one look as registered

`scripts/g6_seed_extension.py`. Read in the registered order.

**CONTROL FIRST — stage 1's own 10 seeds reproduce BIT-FOR-BIT.** 30 shared
(arm, seed) pairs × 3 metrics, **worst absolute difference 0.000e+00**.
This was included because re-running seeds 0–9 was nearly free and nothing
in this WP had ever checked that the stage-1 CSV and a fresh runner agree
about the scenario. They do, exactly — which **retroactively validates
every Part A number too**, since all of them were read from that CSV.

**The result, at n=40, one look, no extension:**

| arm | M01.p98 | M03.max_gap_ms | M05.fraction |
|---|---|---|---|
| PF | −0.01 % [−0.02, +0.01] **PASS** | +0.44 % [−4.29, +5.37] **PASS** | −0.00 % **PASS** |
| Reservation | −0.01 % [−0.02, +0.01] **PASS** | +1.84 % [−2.42, +7.20] **PASS** | +0.09 % **PASS** *(33 dropped)* |
| **TwoTier** | **+67.52 % [+14.91, +123.74] INCONCLUSIVE** | **+136.84 % [+35.23, +267.01] FAIL** | +18.10 % **INCONCLUSIVE** *(31 dropped)* |

**TwoTier FAILS G6 on M03.** Background traffic more than doubles the worst
liveness gap, and the entire interval sits above GT-4.1's +20 % bar. This
is a client-facing guarantee failing on one arm, and it is the first
guarantee failure this WP has produced.

**F7 — PARTIAL, and the half that mattered is confirmed.** F7 predicted
*both* M01.p98 and M03.max_gap_ms resolve to FAIL. M03 does; M01.p98 does
not — its lower bound (+14.91 %) sits just below the bar, so it remains
INCONCLUSIVE even at n=40.

**But the competing outcome F7 named did not occur, and that is the more
important reading.** The alternative registered was *"they collapse toward
zero instead, which would mean the n=10 point estimates were driven by one
or two extreme seeds"*. They did not collapse: the point estimates held
(+74.9 → +67.5, +157.0 → +136.8) and both intervals **now exclude zero**
(+14.91 and +35.23 lower bounds, against n=10 lower bounds of −24.3 and
−14.1). **§22.1a's reasoning — that n was the binding constraint rather
than the effect being absent — is confirmed by measurement**, which is
what the extension was bought to settle.

**M05's bias is now larger, not smaller.** 31–33 of 40 seeds drop, against
7 of 10 before, because a relative delta is undefined off a zero base and
more seeds means more zero-base seeds. §22.0's warning stands unchanged and
scales with n; M05's cell should not be read as a near-pass.

**The question is now closed for this WP as registered.** No resampling, no
third look.

### 22.2 F3 — H3 separates the arms: **HIT**

`snr_spread_db` vs base, paired. Both panel metrics quoted together per
§0.1's standing rule.

| level | arm | M07.met Δ | M08.fraction Δ |
|---|---|---|---|
| 6 dB | PF | +0.00 [+0.00, +0.00] | −0.000 [−0.001, +0.000] |
| | Reservation | +0.10 [−0.40, +0.60] | +0.001 [−0.479, +0.480] |
| | **TwoTier** | +1.20 [−0.10, +2.40] | **+0.676 [+0.425, +0.886]** |
| 12 dB | PF | −0.10 [−0.30, +0.00] | **−0.001 [−0.001, −0.000]** |
| | Reservation | −0.10 [−0.60, +0.40] | −0.192 [−0.574, +0.190] |
| | **TwoTier** | **+1.60 [+0.80, +2.30]** | **+0.698 [+0.453, +0.939]** |

**TwoTier improves on BOTH metrics as the channel spreads, with intervals
excluding zero at 12 dB; PF and Reservation do not move.** H3 is confirmed
in its registered direction. And note this is a case where §0.1's
both-numbers rule does *not* bite: there is no metric split here, TwoTier
simply wins both — which is worth saying explicitly, because §0.1 exists to
stop a reader assuming a split, not to manufacture one.

### 22.3 F2 — H2 does NOT hold in its registered direction: **MISS**

| level | arm | M07.met Δ | M08.fraction Δ |
|---|---|---|---|
| 0.5 | PF | **−0.40 [−0.70, −0.10]** | **−0.010 [−0.016, −0.003]** |
| | Reservation | −0.40 [−0.90, +0.10] | −0.098 [−0.480, +0.284] |
| | TwoTier | −0.20 [−1.30, +0.90] | +0.282 [−0.108, +0.632] |
| 0.1 | **PF** | **−7.00 [−7.40, −6.60]** | **−0.115 [−0.133, −0.098]** |
| | Reservation | **−4.10 [−5.50, −2.60]** | +0.093 [−0.246, +0.416] |
| | **TwoTier** | **−4.00 [−5.20, −2.70]** | **+0.384 [+0.152, +0.599]** |

At the burstiest level every arm loses GBR contracts, but **PF loses nearly
twice as many as TwoTier (−7.0 vs −4.0) and is the only arm whose worst-flow
GFBR fraction falls; TwoTier's rises, with an interval excluding zero.**
**H2 holds in its registered direction, on both metrics. F2 MISSES.**

### 22.4 The F2 trace — obligated by §21.6, and it produced more than the miss did

`scripts/f2_duty_cycle_trace.py`. TwoTier's UL composite is
`coef = (base_q + urg) × hyp_tbs_bytes`, where `base_q` comes from `vq_ul`
(a virtual queue that **integrates while starved**) and `urg` from a delay
barrier on `urgency01` (which needs **live backlog** to grow). Only
`base_q` can accumulate across an idle period.

| scenario | `base_q` median | `base_q` share of the composite |
|---|---|---|
| duty 1.0 — no idle periods | **0.000** | 0.385 |
| duty 0.1 — recurring idle periods | **4,678** | **0.851** |
| stage-5 `ugv_heavy` N=16, control | 8.017 | 0.423 |
| stage-5 `ugv_heavy` N=16, lidar activated | **0.000** | **0.337** |

**Finding 1 — the mechanism is confirmed, and it is H2's own.** Duty-cycling
moves TwoTier's ranking from `urg`-shared to **`base_q`-dominated** (median
0 → 4,678, share 0.385 → **0.851**). That is exactly the mechanism
`sim/parametric.py::_burstify`'s docstring registered for H2 — *"the
windowed ceiling accumulates credit across idle periods"* — measured rather
than asserted.

**Finding 2 — a sub-hypothesis of mine, REFUTED by the same trace.** I
expected PF to *lose* discrimination: `ewma_window_slots=200` is 50 ms
against silences of 330–1000 ms, so `_r_avg` should decay to a floor where
every UE looks alike. It does not. The max/min `_r_avg` ratio is **1.608 at
duty 1.0 and 1.599 at duty 0.1**, and the EWMA reaches its floor on **1 of
8,000 slots**. **PF is unchanged by duty-cycling; the entire effect is
TwoTier gaining.** Recorded because it was the more obvious story and it is
wrong.

**Finding 3 — stage 5's transient is NOT the same phenomenon, and this is
the half §21.6 required the trace to settle.** Under a lidar activation
`base_q` moves the **opposite** way — median **8.0 → 0.000**, share
**0.423 → 0.337** — while `urg` becomes the majority term (mean 571 →
3,370). **Duty-cycling makes the composite `base_q`-dominated; a step
activation makes it `urg`-dominated.** Two different terms of one formula,
moving in opposite directions, because a one-off step to a permanently
higher load contains **no idle period to integrate across**.

**Consequence — the regime map's H2 row is wrong in a way that has nothing
to do with H2 being unrun.** It currently reads that stage 5's transient
"contradicts H2's direction". It does not contradict it: it is a different
mechanism, and the two coexist without tension. Corrected in this commit.

### 22.5 F4 — G12's first-violation order: **UNSCOREABLE, and that is the result**

**M13 cannot be computed on any workload this WP has run.** Measured:
across all 1,770 stage-1 records and all 1,440 stage-4 records, the GBR
5QI classes present are **`[2]` — exactly one.** `first_violation_order`
orders 5QI classes against each other, so with one class every group's
"order" is a one-element list, which is not an ordering.

**This corrects the regime map's G12 row, which is accurate about what
happened and misleading about what would fix it.** It says M13 "was
computed for stage 1's core plane only and not analysed", which invites a
reader to extract it. Extraction cannot answer G12 — the data has nothing
to order.

**And the fix is not to widen M13.** The delay-critical classes in these
workloads (5QI 1/82/83/85) are `flow_class="Delay"`, which
`first_violation_order` does not read. Widening it to them would be
redefining a pre-registered metric so that it separates something — exactly
what `config/metric_panel.yml`'s multiplicity guard forbids. **G12 needs a
workload with ≥ 2 GBR classes**, which is scenario work, not analysis.

### 22.6 F6 — Part A changes no committed number: **HIT**

`regression_corpus.py --check` → `OK -- no drift`. Part A reads stored
records and touches no `sim/` or `scheduler/` file.

### 22.7 §21.5's go/no-go, applied as written

| axis | CI excludes zero on ≥1 arm/metric? | verdict |
|---|---|---|
| `snr_spread_db` (H3) | **yes** — TwoTier M08 at both levels, M07 at 12 dB | **depth bought** |
| `duty_cycle` (H2) | **yes** — TwoTier M08 and PF both metrics at 0.1 | **depth bought** |
| `bg` (G6) | **no** — every TwoTier interval spans zero | **depth NOT bought**; more seeds is a separate, non-pre-registered decision (§22.1) |

### 22.8 Scoreboard

| # | expectation | verdict |
|---|---|---|
| F1 | G6 passes on all three arms | **PARTIAL** — PF passes, TwoTier undetermined on all three, none fails |
| F2 | H2 does NOT hold in its registered direction | **MISS** — it holds, on both metrics; trace in §22.4 |
| F3 | H3 separates the arms | **HIT** — TwoTier on both metrics, intervals excluding zero at 12 dB |
| F4 | G12 order same across arms, differs across profiles | **UNSCOREABLE** — one GBR class exists |
| F5 | G4 post-silence excess | **CRITERION HIT / MECHANISM MISS** — exceeds on all three arms, but sub-proportionally to a 10× size step, so nothing is left for the SR path to explain (§23.2) |
| F6 | no committed number moves | **HIT** |
| F7 | G6's TwoTier cells resolve to FAIL at n=40 | **PARTIAL** — M03 FAILs [+35.23, +267.01]; M01.p98 stays INCONCLUSIVE. But the named alternative (collapse toward zero) did NOT occur: both intervals now exclude zero, confirming n was the binding constraint (§22.1b) |

**Final tally across Parts A and B: two hits, two partials, one split
verdict, one miss, one unscoreable — and the miss produced the stage's most
useful result.** That is now the third consecutive time in
this WP the registered most-likely-wrong expectation carried more than the
hits did (stage 4's E2 → §15.5; stage 5's E2 → the flat transient boundary;
F2 → §22.4's two-term mechanism split). **The pattern is now strong enough
to act on rather than just note: every future stage should register an
expectation it expects to lose**, and the trace obligation should attach to
it in advance, as §21.6 did here.

---

## 23. Stage 6 Part B — G4, prompt resume after silence

`scripts/g4_postsilence.py`. The one guarantee in this set that genuinely
needed a run (§21.4), taken via a study-layer `run_sink` reading the live
`MessageLedger` — no panel change, no M20, no `sim/` or `scheduler/`
change.

### 23.0 Three things caught in the instrument before any number was read

**(a) A killed run left a SMOKE artefact sitting at the result path.** The
first real grid was killed mid-flight by a session teardown. It had written
nothing — but an earlier `--smoke` invocation had written
`sweeps/wp9/stage6_g4.json`, with the right filename, a plausible 145 KB,
and 2 seeds at horizon 2,000 covering two of the three duty levels. **A
reader picking up that file would have read a machinery test as the
result.**

This is the **inverse** of the failure mode already in CLAUDE.md — *an
empty or unchanging output file is evidence about the FILE, not about the
process*. Here a **populated, correctly-named, plausibly-sized** file was
evidence about a **different run**, which is strictly harder to catch than
an empty one: nothing about the contents looked wrong. What caught it was
checking the file's mtime against when `--smoke` was invoked.

Fixed structurally rather than by remembering: `--smoke` now writes
`stage6_g4_SMOKE.json`, and **both** variants stamp a `provenance` block
inside the JSON (smoke flag, duty levels, seed count, horizon), so a reader
holding only the file can still tell which run produced it. Re-launched
under `setsid nohup` — the cause was session teardown, not a crash.

**(b) The gap buckets were partly separating FLOWS, not silences.**
Bucketing by preceding gap is threshold-free, which is why it was chosen —
but the workload's flows have different cadences, so a gap bucket at a
given duty is dominated by whichever flow has that cadence. Measured at
duty 0.1: `[1000,inf)` contains **qfi 1 only**, while `[0,1)` is ~933k
qfi-9 best-effort messages plus ~120k video fragments. **A cross-bucket
comparison is therefore a comparison of different flows**, with different
sizes and PDBs, not of different silence lengths. **All scoring below is
per-flow.** The first table produced by this script was cross-bucket and
would have scored F5 on a flow contrast.

**(c) The first message of each flow was bucketed at gap 0.** It has no
preceding gap at all, and calling that "followed a zero-length silence" is
a false claim about the one quantity this instrument measures. It mattered:
for the low-cadence flows (qfi 1 and 82) those first messages were the
**entire** `[0,1)` bucket — n=80, exactly 8 UEs × 10 seeds, a number that
factors into the grid's own dimensions in the way §19.2's rule flags —
so that cell read as an in-burst measurement and was nothing of the kind.
Now excluded, and the grid re-run rather than annotated.

### 23.1 What the flows are, since the scoring depends on it

| qfi | tier | direction | generator | base | at duty 0.1 |
|---|---|---|---|---|---|
| **1** | T1 telemetry — **the liveness instrument, and G4's flow** | **UL** | `periodic_control` | 100 ms / 300 B | 1000 ms / 3000 B |
| 2 | T3 camera | UL | `xr_video`, fragmented at 1500 B | 33 ms / 16 kB | 330 ms / 160 kB |
| **82** | T2 commands | **DL** | `periodic_control` | 50 ms / 100 B | 500 ms / 1000 B |
| 9 | T6 best-effort — the load | UL | `poisson` | — | unchanged |

### 23.2 F5 — post-silence latency exceeds steady state: **CRITERION HIT, MECHANISM MISS**

**F5 as registered:** *"G4's post-silence first-message latency exceeds the
steady-state p98 on at least one arm at `duty_cycle` 0.1 — the SR/BSR
cold-start path is exactly what WP4 rebuilt, and a 90 %-silent flow
re-enters it constantly."*

qfi 1 (T1 telemetry, UL — G4's own flow), p98 ms, mean over 10 seeds:

| duty | gap bucket | PF | Reservation | TwoTier | msgs | size |
|---|---|---|---|---|---|---|
| 1.0 | `[100,1000)` | 21.62 | 20.58 | 33.82 | 2,400 | 300 B |
| 0.5 | `[100,1000)` | 33.68 | 26.63 | 39.71 | 1,920 | 600 B |
| **0.1** | **`[1000,inf)`** | **77.23** | **64.87** | **74.79** | 254 | 3,000 B |

**The criterion is met, and on all three arms rather than the "at least
one" registered** — 77.23 / 64.87 / 74.79 ms against a steady state of
21.62 / 20.58 / 33.82.

**The stated mechanism is not supported.** The post-silence message is
**10× larger by construction** (§23.5), and measured against that baseline
the latency grew **sub-proportionally on every arm**:

| arm | duty 1.0 → 0.1 | ratio | size baseline | excess over size |
|---|---|---|---|---|
| PF | 21.62 → 77.23 ms | ×3.57 | ×10 | **×0.36** |
| Reservation | 20.58 → 64.87 ms | ×3.15 | ×10 | **×0.32** |
| TwoTier | 33.82 → 74.79 ms | ×2.21 | ×10 | **×0.22** |

**So the exceedance is fully accounted for by message size, with room to
spare — there is no residual an SR/BSR cold-start penalty needs to
explain.** The competing outcome named with F5 — *"the `ul_access` SR path
fully absorbs resumption"* — is the closer description of what happened.

**Scored as a HIT on the criterion and a MISS on the mechanism, kept as two
separate verdicts rather than averaged into one.** The project has scored
this shape before and in the same way: §11's `fires == 0` prediction was
recorded as a HIT *"for the reason originally given rather than the
conflation hypothesis that was floated afterwards"*. A prediction that
lands for the wrong reason is not a confirmation of the reasoning that
produced it, and collapsing the two verdicts would lose exactly that.

### 23.3 The qfi 82 contrast — SUGGESTIVE, with four confounds named

qfi 82 (T2 commands) is **DL**, so it has no SR path at all — the gNB is
its own buffer and never waits for a scheduling request. It takes the
**identical 10× size step**, which makes it a control that was in the
workload already rather than one built for the purpose.

| flow | direction | PF | Reservation | TwoTier |
|---|---|---|---|---|
| qfi 1 | UL | ×3.57 | ×3.15 | ×2.21 |
| qfi 82 | DL | ×1.62 | ×2.08 | ×1.49 |
| **UL / DL** | | **×2.20** | **×1.51** | **×1.48** |

**UL pays between 1.5× and 2.2× more than DL for the same size step, and
the figure is not stable across arms** — ×2.20 on PF against ×1.48–1.51 on
the two QoS-aware arms. **That spread is itself a reason to distrust the
contrast as an access-chain measurement:** an SR-chain cost should not
depend this strongly on which scheduler is running, whereas contention for
UL grants very much does.

**Four confounds, and the contrast cannot separate them.** qfi 1 and qfi 82
differ in **direction** (the term of interest), **absolute size** (300 B vs
100 B base), **PDB** (both 100 ms, but qfi 82's is scenario-overridable via
`pdb_ms` while qfi 1's is fixed), and **priority / contention** — the UL
flow competes with the qfi-9 best-effort load for grants while the DL flow
does not contend for that resource at all. Any one of the four could
produce the ratio difference on its own.

**Recorded as an observation with a candidate mechanism, not a finding** —
the same status §15.5 carries, and §23.4 names the experiment that would
change it.

### 23.4 The experiment that would settle the qfi 82 contrast — REGISTERED, NOT RUN

§23.3's UL-vs-DL contrast is **suggestive and not a measurement of the
access chain**, and it is named here as its own experiment for the same
reason §15.5 named its own: an observation with a candidate mechanism that
is never given a discriminating test becomes a story that fits the data.

**What would settle it: a purpose-built two-flow scenario, not a grid.**
One UL flow and one DL flow **identical in message size, cadence, PDB and
priority — differing only in direction — subjected to the same silence.**
Their latency difference after silence is then the UL access chain (SR on
PUCCH → `sr-ProhibitTimer` → grant → BSR, `sim/ul_access.py`) and nothing
else, because every other term is held equal by construction.

**Why the current contrast cannot do this job: qfi 1 and qfi 82 differ in
four ways at once** — direction (the term of interest), **absolute size**
(300 B vs 100 B base), **PDB** (100 ms both, but qfi 82's is
scenario-overridable via `pdb_ms` while qfi 1's is fixed), and **priority /
flow position** (a UL flow contends with the qfi-9 best-effort load for
grants; the DL flow does not contend for the same resource at all). Any of
the four could produce a 2.2× ratio difference.

**Deliberately not run now, and not appended to this stage.** G4's grid and
the n=40 extension were in flight when the observation appeared; bolting a
new scenario onto a stage already running is how a post-hoc result acquires
the appearance of a registered one. It gets its own registration.

### 23.5 SCOPE NOTE for G4's row — the size confound is not incidental to this guarantee

**This belongs in the regime map's G4 row, not only here.** G4 asks whether
a message sent after silence arrives promptly. Under `_burstify` the
post-silence message **is larger by construction** — the generator holds
mean offered rate constant by stretching the period and growing the burst
by the same 1/duty, so a 10× longer silence means a 10× larger message.

**On this workload the guarantee's own question is therefore entangled with
message size**, in a way a real deployment need not be: a real robot that
goes quiet for a second and then sends one 300-byte telemetry frame has a
long silence and a *normal-sized* message. `_burstify`'s constant-mean-rate
design is right for H2 — it exists so the duty axis cannot smuggle in a
load change — and it is the wrong shape for G4, which wants silence varied
at constant message size.

**A reader taking "post-silence p98 = 77 ms" without this is reading a
number about size as a number about silence.** The scope note travels with
the row.

---

## 24. FINDING — G6's TwoTier "failure" is a metric-scope artefact over an under-specified test, and the real impairment is elsewhere

Diagnosis requested before any extension. **No fix, no re-baseline and no
new grid is taken here.** One single-seed diagnostic run was made to
confirm a mechanism read from source; everything else is from records
already on disk.

### 24.0 A disambiguation the answer depends on: `n=40` is a SEED COUNT

The failing cell is **N=8 UEs at offered load ×1.0** — the base point
(§1). `n=40` is the number of paired seeds §22.1a bought. **No cell at 40
UEs has ever been run**, so if the question was "does G6 hold at a fleet of
40", the answer is *unrun*, not *failed*.

### 24.1 G6's exact wording, and what it binds

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md:100`:

> **G6** | Background traffic (logs, firmware) can never impair the fleet. |
> With saturating 5QI-9 load added (either direction), every G1/G3/G5
> statistic **stays within its bound and** shifts by ≤ ▷ +20 % relative.

Three things follow, and the implemented test honoured none of them fully.

1. **The bar is `▷` — a proposed default, not a ratified threshold.**
   Same file, line 91: *"Numbers marked ▷ are **proposed defaults** to be
   ratified with the client."* So "+20 %" is an assumption under test, not
   a specification.
2. **It is a CONJUNCTION.** "stays within its bound **and** shifts by
   ≤ +20 %". `scripts/analyse_stage6.py::g6_verdict` tests **only the
   second half**. The bound half was never evaluated.
3. **It binds "every G1/G3/G5 statistic" — which is TEN panel metrics**,
   derived from `config/metric_panel.yml`'s own `guarantees:` fields:
   M01, M02, M03, M04, M05, M06, M15, M16, M17, M19.
   **The implemented test used three: M01.p98, M03.max_gap_ms,
   M05.fraction. Seven were omitted, M02 among them.**

### 24.2 The mechanism, from source — M03 scores the AGGRESSOR's own starvation

`sim/scorecard.py:220` iterates **every flow in the record**:

```
for fr in record.flows.values():
    for role, ts_list in fr.completion_ts_by_role_s.items():
```

and takes the maximum gap across all of them (`sim/scorecard.py:233-235`).
**There is no restriction to telemetry, and none to the protected fleet** —
the panel's own note says so: *"computed generically over any flow's
completions"* (`config/metric_panel.yml:106-108`).

`bg=True` adds exactly one flow — `sim/parametric.py:282-292`:

```
flows.append(FlowConfig(
    ue_id=n_ues, qfi=_QFI_AGGRESSOR, direction="UL", flow_class="PF",
    pdb_ms=300.0, lcg=6, traffic_kind="poisson",
    traffic_params={"rate_bps": 50_000_000.0}))
```

a 50 Mbps saturating best-effort flood on the last UE
(`_QFI_AGGRESSOR = 8`, `sim/parametric.py:64`).

**Measured: on all four seeds that produce the +136.84 %, M03's reported
worst-gap flow under `bg` is `ue8_qfi8` — the aggressor itself.**

Single-seed diagnostic, seed 1440696407, TwoTier, per-flow max
inter-completion gap:

| | fleet telemetry (qfi 1) | aggressor (qfi 8) | M03 reports |
|---|---|---|---|
| `bg=False` | 108.50 – 118.75 ms | — | `ue4_qfi1` @ 118.75 ms |
| `bg=True` | 117.75 – **352.25** ms | **2277.50 ms** | **`ue8_qfi8` @ 2277.50 ms** |

**Every fleet telemetry flow stays inside G3's own 500 ms bound; the
statistic G6 failed on belongs to the background traffic.**

**And the causal direction is inverted.** TwoTier is QoS-aware, so it
correctly deprioritises a non-GBR 5QI-8 flood against GBR video and
delay-critical telemetry. Starving that flood is **what G6 asks for.** The
metric then reads the starvation back as a liveness failure — so **the
better an arm contains the aggressor, the worse its G6 score.** PF spreads
capacity, the aggressor gets steadier service, and PF's M03 worst-gap flow
stays a fleet telemetry flow on 40/40 seeds — which is why PF "passes".

### 24.3 The interval, and what it does and does not cover

`+136.84 %`, **95 % percentile-bootstrap CI [+35.23, +267.01]**, n = **40
paired seeds** (`regime_sweep.bootstrap_ci`, 2000 resamples), **paired
within seed** — same seed drives base and excursion, verified equal seed
sets before scoring.

**The point estimate is the mean of 40 per-seed RATIOS on a MAX statistic,
and it is not a robust summary of them:**

| | TwoTier | PF |
|---|---|---|
| seeds worse / better | **18 / 21** (1 unchanged) | 18 / 22 |
| **median** relative delta | **−0.22 %** | −0.30 % |
| **mean** relative delta | **+136.84 %** | +0.44 % |

**The median is negative — more seeds improve than worsen.** The mean is
carried by four seeds (+2158, +1918, +1720, +1511 ms).

**What the interval covers:** sampling variability of that mean across
these 40 seeds, at this one cell (N=8, load ×1.0), on this scenario.
**What it does not cover:** any other fleet size or load; the choice of
estimator (mean-of-ratios on a maximum); the metric's flow scope (§24.2);
the seven omitted statistics (§24.1); and the ▷-provisional bar itself.

### 24.4 The real impairment is large, universal, and on a metric the test omitted

**M02 (`pdb_violation_rate`, `guarantees: [G1, G5, G12]` — squarely inside
G6's "every G1/G5 statistic") rises on 40 of 40 seeds on every arm:**

| arm | mean Δ M02 | median Δ | seeds increased |
|---|---|---|---|
| PF | **+0.2446** | +0.2452 | **40/40** |
| Reservation | **+0.2404** | +0.2406 | **40/40** |
| **TwoTier** | **+0.2178** | +0.2131 | **40/40** |

The aggressor raises the byte-weighted PDB-violation rate by ~**24
percentage points**. That is a real, unambiguous fleet impairment and a
genuine G6 failure — **on all three arms**, not one.

**And TwoTier is the LEAST impaired.** So the reported result was not
merely imprecise: **it was inverted.**

> **RETRACTED by §28.1a.** The paragraph above calls M02's rise "a real,
> unambiguous fleet impairment and a genuine G6 failure". **It is not.** Put
> through the same aggressor/filler decomposition this very section applied
> to M03, M02's rise is **entirely the aggressor's own bytes** — the
> protected-fleet delta is **+0.0000 / −0.0104 / −0.0270** with every
> interval containing zero. *(This sentence originally read −0.0019 /
> −0.0022 / +0.0010, which is the aggressor-excluded row and not the
> protected fleet — see the correction box in §28.1.)* The error was attributing an aggregate to the fleet
> **without decomposing it**, immediately after decomposing M03 and finding
> exactly that mistake. Read §28.1 for the settled result: **G6 passes on
> the protected fleet on M02, on every arm; M20 is INCONCLUSIVE on
> TwoTier** (+29.35 % [+4.81, +56.18], an interval excluding zero). The arm the test singled out as
failing is the best-performing arm on the statistic that actually measures
what G6 is about. Corroborated by the diagnostic seed, where fleet
telemetry loses messages under `bg` (ue6_qfi1: 50 → 32 delivered) — real
impairment that M03's max-gap statistic cannot see and M02 does.

### 24.5 Is it monotone in fleet size? NOT ANSWERABLE FROM DISK

The `bg` excursion was run **only at the base point**: all 30 stage-1
`bg=True` rows carry `n_ues = None`. There is no `bg` cell at any other
fleet size, so where the guarantee starts to fail as N grows **cannot be
answered without new runs**, and is reported as unrun rather than
estimated.

### 24.6 This DOES change what Part C measures

Part C's depth on `duty_cycle` is directly exposed, and the interaction is
already visible on disk (stage 1, median M03 `max_gap_ms`, breaches of
G3's 500 ms bound):

| cell | PF | TwoTier |
|---|---|---|
| base point | 132.25 ms — 0/10 breach | 120.13 ms — 1/10 |
| `duty_cycle` 0.5 | 233.12 ms — 0/10 | 503.25 ms — **5/10** |
| `duty_cycle` 0.1 | **2077.50 ms — 10/10** | **2033.25 ms — 10/10** |

**At `duty_cycle` 0.1 the telemetry flow's own configured period is
1000 ms** (`_burstify(100.0, 300.0, 0.1)`, `sim/parametric.py:122-137`), so
a ~2000 ms inter-completion gap is **the cadence, not a liveness failure**.
M03 breaches its bound in 10/10 seeds on **both** arms for a reason that
has nothing to do with scheduling. `snr_spread_db` shows no such coupling —
it does not change any flow's cadence.

> **CORRECTED: the exclusion applies at `duty_cycle` 0.1, NOT at "≤ 0.5",
> and the difference discards a real result.** This paragraph read *"any
> Part C M03 reading at `duty_cycle` ≤ 0.5 is measuring the duty cycle"*.
> At duty 0.5 the telemetry period is `_burstify(100.0, 300.0, 0.5)` =
> **200 ms — well BELOW the 500 ms bound** — so `sim/scorecard.py`'s
> caveat, whose predicate is `median_gap_ms > T_live/4`, **does not fire**
> there. **TwoTier's 503.25 ms with 5/10 seeds breaching at duty 0.5 is a
> real liveness breach against PF's 0/10**, and the over-generalisation
> threw it away.
>
> **The direction is what makes this worth a box.** Every other cadence
> note in this document guards against *crediting* a cadence artefact as a
> breach. This one did the opposite — it **discarded a genuine arm
> difference** by widening a correct exclusion one level past its own
> arithmetic. A caveat applied too broadly destroys findings exactly as
> efficiently as one applied too narrowly manufactures them, and it is much
> harder to notice, because the result simply never gets reported.

> **AND THE CORRECTION ABOVE IS ITSELF WRONG — corrected again 2026-09-03,
> this time against the data rather than the scenario file.** The box asserts
> *"the caveat does NOT fire"* at duty 0.5. **It fires on 4 of 44 duty-0.5
> breaches**, measured directly over the committed
> `sweeps/wp9/part_c_rows.csv`:
>
> | arm | max gap | median | configured period |
> |---|---|---|---|
> | TwoTier | 963.25 | 596.63 | 200 ms |
> | Reservation | 2815.00 | 602.25 | 200 ms |
> | Reservation | 2041.25 | 551.25 | 200 ms |
> | Reservation | 2063.75 | 525.00 | 200 ms |
>
> **The error is one step, and it is the reusable part: the box inferred the
> predicate's STATE from the CONFIGURATION instead of reading the predicate's
> INPUT.** The predicate is `median_gap_ms > T_live/4`, and `median_gap_ms`
> is MEASURED. A flow configured at 200 ms whose network degrades it to a
> 600 ms observed median trips it. So the exclusion is not a property of
> `duty_cycle` at all — it is a property of each row, and it must be read per
> row.
>
> **This is triage finding #22 arriving from the other direction**, and it is
> why #22 blocks G3: the caveat silences real breaches on the metric G3 binds
> to. **TwoTier's 503.25 ms / 5-of-10 result quoted above survives** — those
> rows are not among the four — but the general claim that duty 0.5 is
> caveat-free does not.
>
> Registered as a failure class in `prediction-journal.md`: *an
> over-correction is its own class, and it is the hardest to see, because it
> reads as settled.*
>
> Note the caveat's predicate is a strict `>`, and at duty 0.1 the DL
> command flow's period is exactly **500.0 ms**, so rows won by 5QI 82 sit
> on the threshold and fire or not on float jitter. The caveat is not
> exhaustive and should not be quoted as though it were.

This is the same shape as §23.5's G4 scope note: `_burstify` holds mean
rate constant by stretching the period, which is right for H2 and wrong for
any metric keyed to inter-arrival time.

### 24.7 Verdict, and what would falsify it

**Verdict: (c) a measurement artefact of the metric definition, compounded
by an under-specified test — NOT (a) a scheduler defect and NOT (b) a
guarantee stated at the wrong scope.** The failing statistic belongs to the
background traffic; the arm blamed is the one containing it best; and the
statistic that shows the real impairment was omitted from the test.

**Two things are nonetheless real and must not be lost in the correction:**
G6 *is* failing — on M02, on all three arms, 40/40 seeds — and TwoTier's
max-gap distribution is genuinely heavy-tailed even at `bg=False` (one seed
at 660 ms, mean 183.85 vs median 119.13), which is its own open question.

**What would falsify this diagnosis:**

1. **A fleet-restricted M03 that still fails.** Recompute the worst-gap
   contest over protected-fleet flows only (excluding qfi 8 and qfi 9). If
   TwoTier's delta still exceeds +20 % with an interval above the bar, the
   artefact is not the explanation and (a) returns.
2. **Per-flow evidence that fleet telemetry, not the aggressor, drives the
   four extreme seeds.** §24.2 checked one seed; the other three are
   assumed to share it from their identical `M03.flow`, not verified
   per-flow.
3. **The bound half evaluated.** If fleet-only gaps breach 500 ms under
   `bg` while staying inside it without, G6 fails its first conjunct on a
   fleet statistic and the verdict changes regardless of the relative bar.

### 24.8 What follows — proposed, not taken

Nothing below is done in this commit.

1. **Correct the G6 test before extending it**: evaluate the conjunction's
   bound half, restrict M03's contest to protected-fleet flows or add a
   fleet-restricted companion, and cover the seven omitted G1/G3/G5
   statistics. Each is a mechanism change with its own guard test.
2. **A guard test verified to fail against current code** must accompany
   any such fix, with the failing output in the commit message.
3. **Part C's M03 readings need the duty-cycle coupling handled** before
   depth is bought, or its M03 column will be uninterpretable.
4. **§22.1b's G6 row and the regime map's G6 row are now known to be
   wrong** and must be corrected — but the correction is part of the fix
   commit, not asserted ahead of it.

---

## 25. Step 1 — §24.7's falsifier run. Neither branch fires cleanly; the test is under-powered at the `n_seeds` on disk

`scripts/g6_fleet_restricted_m03.py`. Read-only: recomputes M03's own
contest (`sim/scorecard.py:220-235`) over four flow subsets from records
stage 1 already wrote. **No metric changed, no new grid.**

### 25.1 A data constraint that decides what `n_seeds` this can be answered at

`scripts/g6_seed_extension.py:62-64` calls `sweep()` with **no
`record_sink`**, so the n_seeds=40 run persisted only the tidy CSV, which
carries M03's *winning* flow and value and never the per-flow
`completion_ts_by_role_s` a restricted recomputation needs. Stage 1's
`records.jsonl` does carry them, for **n_seeds=10** (3 arms × 10 seeds in
both the `bg=True` cell and the base cell, 30 paired (arm, seed) pairs).

**So this falsifier is answerable from disk at n_seeds=10, and at
n_seeds=40 only by re-running those same two cells with a sink.**

### 25.2 The result — cell n_ues=8, load ×1.0, paired within seed, n_seeds=10

Relative delta of M03's max gap, `bg=True` vs base. Mean is the
mean-of-ratios the existing test uses; median and IQR are shown beside it
because Step 4 exists.

| flow subset | arm | MEAN [95 % CI] | verdict | MEDIAN | IQR | seeds worse |
|---|---|---|---|---|---|---|
| **ALL flows** (as implemented) | PF | +3.73 [−6.80, +15.57] | PASS | −1.53 | [−10.95, +17.15] | 5/10 |
| | Reservation | +8.99 [−8.37, +29.04] | INCONCLUSIVE | +0.82 | [−2.02, +17.82] | 6/10 |
| | **TwoTier** | **+157.04 [−13.83, +467.12]** | INCONCLUSIVE | **−1.20** | [−5.80, +55.94] | 5/10 |
| **aggressor excluded** (no qfi 8) | PF | +3.73 [−6.80, +15.57] | PASS | −1.53 | | 5/10 |
| | Reservation | +8.99 [−8.37, +29.04] | INCONCLUSIVE | +0.82 | | 6/10 |
| | **TwoTier** | **+60.37 [−19.41, +190.99]** | INCONCLUSIVE | **−2.44** | [−16.54, +41.38] | 4/10 |
| **no best-effort** (no qfi 8, 9) | **TwoTier** | **+34.08 [−16.90, +105.67]** | INCONCLUSIVE | **−2.44** | [−8.43, +41.38] | 4/10 |
| **TELEMETRY only** (qfi 1) | **TwoTier** | **+34.08 [−16.90, +105.67]** | INCONCLUSIVE | **−2.44** | [−8.43, +41.38] | 4/10 |

**PF and Reservation are bit-identical across all four subsets.** Their
winning flow was never the aggressor or the best-effort filler — always
fleet telemetry — which is the §24.2 mechanism confirmed from the opposite
direction.

### 25.3 Verdict: NEITHER branch fires cleanly

§24.7's rule was *excess still above +20 % ⇒ (a); inside the bar ⇒ (c)
stands*. At n_seeds=10:

- the **point estimate** is +34.08 %, **above** the bar;
- the **interval** is [−16.90, +105.67], which **contains the bar and
  contains zero** — INCONCLUSIVE;
- the **median** is **−2.44 %**, inside the bar, with **4 of 10 seeds
  worse**.

**Reading the point estimate alone would return (a); reading the interval
returns neither.** §24.3 committed this project to reading the interval, so
the honest answer is **the falsifier is under-powered at n_seeds=10 and
does not decide between (a) and (c).**

### 25.4 What it DOES decide — the decomposition, which is estimator-independent

| subset removed | TwoTier mean excess | share of the original removed |
|---|---|---|
| — (as implemented) | +157.04 % | — |
| aggressor (qfi 8) | +60.37 % | **62 %** |
| + best-effort filler (qfi 9) | +34.08 % | **+17 %** (79 % cumulative) |
| telemetry only | +34.08 % | unchanged |

**About 78 % of the excess belongs to flows that are not fleet telemetry**,
and ~22 % remains on telemetry itself. **That is precisely the "mechanism
INCOMPLETE rather than wrong" outcome P2 registered in advance**: §24
correctly identified the dominant contributor and missed a smaller, real,
telemetry-side degradation.

### 25.5 The standing branch FIRED, and it changes what any fix must do

P2 registered the branch *"the instrument is measuring something other than
what the question is about"*, with a named signature: *the winning flow
changes identity between the paired base and excursion runs.*

**Measured: the winner flow changes identity on 9 of 10 seeds — for every
arm, and in every subset including telemetry-only.**

So even restricted to telemetry, M03's max is a **maximum over n_ues=8
UEs**, and its relative change is dominated by *which UE happened to spike
hardest*, not by whether the fleet degraded. **Restricting the flow set
does not turn an extreme-value statistic into a fleet-health statistic.**
A Step 2 that only restricts the flow set would fix the scope error and
leave the estimator error untouched.

### 25.6 What this changes about the remaining steps — proposed, not taken

1. **Step 1 is not finished.** Deciding (a) vs (c) needs the same two cells
   re-run with a `record_sink` at n_seeds=40 — the same cells, not a new
   grid. At n_seeds=40 the interval narrows ≈2×, which is the difference
   between INCONCLUSIVE and an answer.
2. **Step 2's guard test still stands unchanged** — the aggressor really
   does own 62 % of the excess, and a fleet-restricted statistic really
   does need to ignore it.
3. **Step 4 is promoted from a reporting default to part of the fix.**
   §25.5 shows the estimator is not a presentation choice here: median
   −2.44 % and mean +34.08 % on the same 10 pairs disagree about whether
   the guarantee holds.

---

## 26. How fast is this simulator, really — and the comparison that actually justifies it

Derived from measurements already on disk (§6.3a's serial timings, §13's
probe, stages 4 and 5's own logs). **Nothing here was run for it.** The
headline the deck needs is in §26.4, and it is not a speed claim.

### 26.1 Per-run ratio, single core — and it is a NEGATIVE result

Sim-seconds delivered per wall-second. Horizon is **20,000 slots = 5.0 s of
sim time** at this RAN (`dsuuu_40mhz`, numerology 2, 0.25 ms slots), and a
cell is **3 arms × 10 seeds = 30 runs**.

`driver.run()` only:

| configuration | flows | PF | Reservation | TwoTier |
|---|---|---|---|---|
| n_ues=2 | 8 | **4.55×** | 3.73× | 1.47× |
| n_ues=8 | 32 | 1.38× | 0.87× | 0.46× |
| n_ues=32 | 128 | 0.30× | 0.22× | **0.18×** |

**Endpoints named: 4.55× at the cheapest configuration (n_ues=2, PF) down
to 0.18× at the most expensive (n_ues=32, TwoTier) — a 25× span that
CROSSES UNITY.** Full per-record cost (cell ÷ 30, so driver + scoring + the
12 variations) is worse: **1.852× → 0.495× → 0.137×**.

**So at every working fleet size this simulator is SLOWER than the radio it
models.** That is the useful thing for a future reader to know and it is
why this table stays in the document even though it does not go on a slide.
The ratio the deck quotes comes from **parallelism**, not from the model
being fast.

### 26.2 Reference configuration, so the headline has a defined meaning

**n_ues=8, `factory` mix, 32 flows, 20,000 slots = 5.0 s sim** — §1's base
point. Measured cell 303 s ÷ 30 runs = **10.10 wall-s per run**:

| | ratio |
|---|---|
| single core, full per-record cost | **0.495×** |
| single core, `driver.run()` only, 3-arm mean | 0.74× |
| 10 workers @ stage 2's measured **6.75×** parallel efficiency (68 %) | **3.34×** |
| 10 workers @ linear 10× — **not used** | 4.95× |

### 26.3 But the MEASURED end-to-end number is lower, and it is the one to quote

| stage | cells | runs | sim time | wall (10 workers) | ratio |
|---|---|---|---|---|---|
| stage 4 | 48 | 1,440 | 7,200 s | 40.6 min | **2.96×** |
| stage 5 | 48 | 1,440 | 7,200 s | 43.2 min | **2.78×** |

**≈2.9×, whole pipeline, measured over two real stages — not derived.**
§26.2's 3.34× over-states it, because a real stage includes n_ues=32 cells
far more expensive than the base point. **Quote the measured one.**

### 26.4 What the ratio EXCLUDES — and why a driver-only figure will not reproduce

Scoring is **~24 % of per-record time** on top of `driver.run()`
(§6.3a's own third cause), and record persistence is on top of that again.
**§26.1's driver-only column is not reproducible by anyone running a
sweep.** §26.3's figures are, because they are end-to-end wall time
including scoring, the 12 scoring variations, and record writing.

### 26.5 The comparison that justifies the tool — and it is NOT speed

WP9 to date: **407 cells × 30 runs = 12,210 runs = 17.0 h of simulated air
time, in ≈5.9 h of wall time** at the measured 2.86× (stages 4+5 pooled).

| testbed equivalent, same 407 configurations | wall time | vs sim |
|---|---|---|
| pure air time, zero overhead, perfectly serial | 17.0 h | **2.9×** |
| + 5 min reconfiguration per cell | 50.9 h | 8.6× |
| + 15 min reconfiguration per cell | 118.7 h | 20.0× |
| + 30 min reconfiguration per cell | 220.5 h | 37.2× |

**THE RECONFIGURATION MINUTES ARE AN ASSUMPTION, NOT A MEASUREMENT, and
they drive most of the claim's range (8.6×–37.2×).** Nobody has measured
them. **Ask whoever runs the testbed before this reaches a slide.** Until
then the defensible statement is the **2.9× pure-air-time floor**, which
needs no assumption at all, plus the two capabilities below, which need
none either.

**And the honest framing for the deck is not speed — it is that a testbed
cannot run this study at all. Not slowly: at all.**

1. **Paired seeds.** Every comparison in this WP is within-seed: the same
   channel realisation is replayed across arms. A testbed cannot replay a
   channel realisation, so it must raise n per cell to recover the same
   statistical power — which means the table above **understates** the gap.
   §4 of the regime map records an unpaired comparison producing a
   confident answer **opposite** to the paired one, so this is not a
   refinement; it is the difference between a right and a wrong result.
2. **Fleet size.** Stages swept `n_ues` to 32. Reaching n_ues=32 physically
   needs 32 robots.

**Lead with reachability, not with time.** A speed claim invites the
obvious and correct rebuttal — *a testbed gives you real RF* — and the time
saving is real but secondary. "This study is not physically runnable"
has no such rebuttal, and it is true.

---

## 27. Step 1 COMPLETED at n_seeds=40 — the telemetry residual is real, and still not resolved against the bar

`scripts/g6_fleet_restricted_m03.py --records sweeps/wp9/stage6_g6_n40_records.jsonl`.
The two cells re-run with `PersistingRecordSink`, so the per-flow
completion timestamps exist this time. **240/240 records persisted; the
control passed bit-for-bit (worst absolute difference 0.000e+00 over 30
shared arm-seed pairs × 3 metrics).**

Framed as §25.6 required: **this measures the telemetry residual**, not
(a)-vs-(c). The verdict falls out of it.

### 27.1 The decomposition at n_seeds=40 — and it is stable

TwoTier, cell n_ues=8 at offered load ×1.0, paired within seed:

| flow subset | mean [95 % CI] | verdict | median | seeds worse |
|---|---|---|---|---|
| ALL flows (as implemented) | **+136.84 % [+32.75, +272.45]** | **FAIL** | −0.22 % | 18/40 |
| aggressor excluded (no qfi 8) | **+43.15 % [+6.13, +87.99]** | INCONCLUSIVE | −0.44 % | 17/40 |
| no best-effort (no qfi 8, 9) | **+29.35 % [+4.81, +56.18]** | INCONCLUSIVE | −0.44 % | 17/40 |
| **telemetry only** (qfi 1) | **+29.35 % [+4.81, +56.18]** | INCONCLUSIVE | −0.44 % | 17/40 |

PF (+0.44 %) and Reservation (+1.84 %) **PASS** and are identical across
all four subsets — their winning flow was never the aggressor or the
filler.

**The decomposition barely moved from n_seeds=10, which is the point:**

| removed | n_seeds=10 | n_seeds=40 |
|---|---|---|
| aggressor (qfi 8) | 62 % of the excess | **68 %** |
| + best-effort filler (qfi 9) | +17 % (79 % cum.) | **+10 % (78 % cum.)** |
| **telemetry residual** | **22 %** | **21 %** |

**~78 % of the excess belongs to flows that are not fleet telemetry, and
~21 % is a real telemetry-side residual.** Quadrupling n_seeds changed that
split by one point.

### 27.2 The verdict, stated at the precision the data supports

**The interval narrowed as predicted and moved off zero: [−16.90, +105.67]
at n_seeds=10 → [+4.81, +56.18] at n_seeds=40.** So:

- the residual **excludes zero** — there IS a real telemetry-side
  degradation under the aggressor, which n_seeds=10 could not establish;
- the residual **still contains the +20 % bar** — whether it BREACHES the
  guarantee is unresolved, and quadrupling the seeds again would be needed
  to settle it.

**So the honest verdict is neither pure (a) nor pure (c): the metric-scope
artefact is the dominant term (78 %) AND a smaller real scheduler-side
effect exists underneath it, previously masked.** §24's verdict of (c)
stands as the explanation of the *reported number*; it was **incomplete**
as an account of the *underlying behaviour*.

### 27.3 The standing branch fired again, harder

P2's registered signature — *the winning flow changes identity between the
paired base and excursion runs* — holds on **35 of 40 seeds** (37/40 for
Reservation), **in every subset including telemetry-only**.

**Even restricted to one 5QI, M03's max is a maximum over n_ues=8 UEs, so
its relative change tracks WHICH UE spiked hardest rather than whether the
fleet degraded.** Confirmed at n_seeds=40 what n_seeds=10 suggested: **a
scope-only fix leaves the estimator error untouched**, which is why Step 2
lands scope and estimator as one binding change.

### 27.4 P2 scored — HIT, on every clause

| clause registered | outcome |
|---|---|
| excess drops substantially but stays **above +20 %** under mean-of-ratios | **HIT** — +136.84 % → +29.35 %, above the bar |
| **median** stays inside the bar | **HIT** — −0.44 % |
| the branch: mechanism **INCOMPLETE** rather than wrong | **HIT** — 78 % explained, 21 % real residual |
| standing branch's signature (winner-flow identity churn) | **HIT** — 35/40 |

**P2 is a clean hit where P1 was a miss, and the difference is instructive:
P1 predicted a MECHANISM from the aggregate; P2 predicted an OUTCOME SHAPE
and named in advance what each possible shape would mean.** The second is
the form that survives contact with data, and it is the form to register in
future.

---

## 28. Step 3 — G6's conjunction over all ten statistics, and a CORRECTION to §24.4's headline

`scripts/g6_conjunction_table.py`. n_seeds=40 paired, cell n_ues=8 at
offered load ×1.0, evaluated on the **protected fleet** (M20's restriction,
excluding 5QIs 8 and 9).

### 28.1 THE RESULT: G6 PASSES on the protected fleet on M02, on every arm; M20 is INCONCLUSIVE on TwoTier

> **The heading read "on both statistics" until 2026-09-03.** That is
> the claim defect-log #3 corrected — M20 on TwoTier is **+29.35 %
> [+4.81, +56.18]**, an interval EXCLUDING zero and STRADDLING the
> +20 % bar, i.e. INCONCLUSIVE. The body below carried the correction
> from `1cc4dbc`; the heading above it did not, so a reader scanning
> headings got the retracted claim.

**Background traffic does not impair the fleet.** Neither statistic that
appeared to fail G6 does so once it is measured on the bearers G6 is about:

| | M03/M20 (worst liveness gap) | M02 (PDB violation rate) |
|---|---|---|
| PF | PASS | PASS — Δ **+0.0000** |
| Reservation | PASS | PASS — Δ **−0.0104** [−0.0284, +0.0049] |
| TwoTier | INCONCLUSIVE, median −0.44 % | PASS — Δ **−0.0270** [−0.0724, +0.0191] |

**Every protected-fleet M02 interval contains zero, on all three arms, at
n_seeds=40 paired.** The fleet's PDB-violation rate does not move when a
50 Mbps saturating flood is added beside it.

> **CORRECTED. This table previously quoted −0.0019 / −0.0022 / +0.0010,
> which is the `no qfi 8` row of §28.1a's decomposition — the AGGRESSOR
> excluded, but the per-UE best-effort filler still in.** The protected
> fleet is defined in code as `Scorecard.NON_PROTECTED_5QI = frozenset({8,
> 9})`, so it drops **5QI 9 as well**, and the matching row is `no
> best-effort (no qfi 8, 9)`: **+0.0000 / −0.0104 / −0.0270**.
>
> **The verdict is unchanged** — every interval still contains zero and two
> of the three deltas are now more negative, so G6 passes more comfortably
> than the wrong numbers said. **But the error is the same one this whole
> section exists to correct, committed inside the correction:** §28.1a
> decomposed "all flows" → "aggressor excluded" and *stopped one population
> short of the definition it was invoking*. **An under-decomposition is
> still a decompose-rule failure**, and it is harder to see than the
> original because the population moved in the right direction — just not
> far enough.
>
> **§28.3 of this same document already had it right** — *"on the protected
> fleet PF's M02 is exactly 0.0 in both conditions on every seed"*, i.e.
> Δ = +0.0000 — so the document disagreed with itself for as long as
> neither passage was read beside the other. Caught while building the
> client deck, not by review.

**This is a stronger and more useful result than the failure was.** It says
the schedulers do the thing G6 exists to check — a non-GBR flood is
absorbed without touching the protected bearers — and it says the apparent
failure came from **the aggressor being measured as though it were the
fleet, by two different mechanisms in two different metrics**: M03's
max-over-all-flows, and M02's byte-weighting-over-all-flows. One
guarantee, two metrics, two distinct scope defects, same root cause.

The supporting decomposition — M02's rise is **entirely the aggressor's own
bytes**:

| flow subset | PF | Reservation | TwoTier |
|---|---|---|---|
| **ALL flows** (as implemented) | **+0.2313** [+0.2264, +0.2362] | **+0.2270** [+0.2224, +0.2320] | **+0.2055** [+0.1951, +0.2164] |
| aggressor excluded (no qfi 8) — **NOT the protected fleet** | −0.0019 [−0.0075, +0.0041] | −0.0022 [−0.0075, +0.0036] | +0.0010 [−0.0109, +0.0133] |
| **PROTECTED FLEET** — no best-effort (no qfi 8, 9), matching `NON_PROTECTED_5QI` | **+0.0000** | **−0.0104** [−0.0284, +0.0049] | **−0.0270** [−0.0724, +0.0191] |
| telemetry only (qfi 1) | +0.0000 | −0.0104 [−0.0285, +0.0054] | −0.0150 [−0.0534, +0.0216] |

*(absolute deltas — M02 is a fraction, so a relative delta off a near-zero
base is meaningless; §28.3.)*

The +0.23 was the flood's own traffic being late or dropped — which is what
**should** happen to a best-effort flood under a QoS-aware scheduler.

**M02's rise dissolves MORE completely than M03's did.** M03 left a 21 %
telemetry residual whose interval excludes zero (§27.2); M02 leaves
**nothing**.

### 28.1a CORRECTION to §24.4, stated here because this is where it is settled

**§24.4 called M02's ~24-point rise "the real fleet impairment" and said G6
was genuinely failing on all three arms. That was wrong.**

**The claim was mine**, and the direction it went wrong is the point: §24
had *just* decomposed M03's excess and found most of it belonged to the
aggressor — and then attributed M02's rise to the fleet **without running
the same decomposition on it**. The tool was already built and in hand; it
simply was not pointed at the second metric.

**The check that caught it is the one that has now caught four corrections
in this item: decompose before attributing.** §24.2 (M03's worst flow is
the aggressor), §25.4 and §27.1 (the 68/10/21 split), and now §28.1. Each
time the failure mode was the same — reading an aggregate as a statement
about the population it is *named* for rather than the one it is *computed
over*.

**And the instruction to lead with M02 compounded it**, by framing the
alternative as *burial* — "otherwise the genuine finding gets buried under
the corrected one" — which presupposed M02 was genuine. That presupposition
came from §24.4, i.e. from me. **The right response to "don't bury the real
finding" was to check whether it was real, not to promote it**; the framing
made promotion feel like the careful option and it was not. Recorded
because this is the second time in this thread a premise of mine returned
as an instruction and had to be checked rather than executed
(`92d9a60`, and the cost-model replacement in §13).

### 28.2 Why M03 needed a binding change and M02 did not

The question §28.1 forces, and the answer separates two defects that
looked like one:

| | M03 | M02 |
|---|---|---|
| **scope defect** (aggregate includes non-fleet flows) | **yes** — max over every flow | **yes** — bytes summed over every flow |
| **estimator defect** (summary misrepresents its own distribution) | **yes** — mean +136.84 % vs median −0.22 %, 21/40 seeds improve | **no** — mean +0.2313 vs median +0.2318, **100 % of seeds move the same way** |
| **winner-churn** (statistic tracks *which* flow spiked) | **yes** — winning flow changes identity on 35/40 seeds | **not applicable** — a byte-weighted aggregate has no "winning flow" |

**Both metrics have the scope defect; only M03 has the estimator defect.**
M02's mean is a perfectly good summary of its distribution — it just
summarises the wrong flow set. That is precisely why Step 2's binding
change carried **two** halves for M03 and why M02 needs only the flow
restriction: **the estimator fix is metric-specific, the scope fix is
guarantee-wide.**

### 28.3 A structural problem with G6's bar that this exposes

**G6's "+20 % relative" is undefined for a rate that can be zero.** On the
protected fleet PF's M02 is exactly 0.0 in both conditions on every seed, so
the relative form is `0/0`; TwoTier's relative mean reads **+4271 %** off a
near-zero base while its median is **−0.21 %**. A relative bar is the wrong
shape for M02 and the absolute delta is the only readable form.

Recorded rather than fixed: **the bar is `▷`-provisional** (test plan line
91), so this is input to ratifying it, not a defect to patch unilaterally.

### 28.4 The full conjunction — ten statistics × two clauses × three arms

Statistics **derived from the panel's `guarantees:` fields**, not
hand-listed: M01, M02, M03, M04, M05, M06, M15, M16, M17, M19.

| metric | arm | clause 1: within bound | clause 2: shift ≤ +20 % |
|---|---|---|---|
| **M01** | PF | PASS 0/40 over 100 ms | INCONCLUSIVE (med +4.36 %, mean +12.09 %) |
| | Reservation | PASS 0/40 | PASS (med −0.46 %) |
| | TwoTier | **FAIL 8/40 over 100 ms** | INCONCLUSIVE (med −1.02 %, mean +45.97 %) |
| **M02** | all | no stated bound | see §28.1 — **PASS on absolute deltas** |
| **M03** | PF / Reservation | PASS 0/40 over 500 ms | PASS |
| | TwoTier | **FAIL 2/40 over 500 ms** | INCONCLUSIVE (med −0.44 %, mean +29.35 %) |
| **M04** | all | **NOT EVALUABLE** — `pending` | NOT EVALUABLE |
| **M05** | PF | **FAIL 3/40 under 0.99** | PASS |
| | Reservation | **FAIL 30/40** | PASS |
| | TwoTier | **FAIL 35/40** | INCONCLUSIVE |
| **M06** | PF / Reservation | PASS 0/40 over 67 ms | PASS |
| | TwoTier | **FAIL 12/40 over 67 ms** | INCONCLUSIVE |
| **M15, M17** | all | **NOT EVALUABLE** — no bound stated, and the metric emits a dict this table cannot reduce to one scalar without inventing a rule | NOT EVALUABLE |
| **M16** | all | **NOT EVALUABLE** — study-layer, needs a named flow pair | NOT EVALUABLE |
| **M19** | all | **NOT EVALUABLE** — `pending`, no join events in any WP9 scenario | NOT EVALUABLE |

**Stated plainly, per the instruction not to estimate: 4 of 10 statistics
are NOT EVALUABLE (M04, M15/M17, M16, M19) and are reported as unrun, not
inferred.** Only 5 have a stated numeric bound at all; M02 has none.

**Clause 1 is where the real failures are, and it was never checked before
this.** M05 fails on all three arms (3/40, 30/40, 35/40 seeds under the
99 % completeness bar) and M01/M03/M06 fail on TwoTier — **none of which
the original three-statistic, second-clause-only test could see.**

**These clause-1 failures are NOT G6 failures on their own.** G6 is a
*delta* guarantee: it asks whether background traffic pushes a statistic
out of bound. A statistic already out of bound **without** the aggressor is
a G1/G3/G5 problem, not a G6 one. Whether these are pre-existing is the
next question and **is not answered here** — the base-cell bound check is
computed but not yet compared against it.

### 28.5 A defect this table found in its own first run

The first version tested `value > bound` for **every** metric, including
the higher-better **M05** — so it counted the 37 seeds that **met** the
≥ 99 % completeness bar as failures. Fixed by reading `direction` from
`config/metric_panel.yml` rather than hand-writing the comparison, the same
way `analyse_stage2.py::_load_directions` already does, and for the reason
that file gives: *a hand-copied sign inverts a winner and nothing
downstream catches it.*

---

## 29. P3 — the clause-1 breaches are PRE-EXISTING, and one of them is a serious G5 finding

Answered from `sweeps/wp9/stage6_g6_n40_records.jsonl` (both cells), **no
new run**. Protected fleet, n_ues=8, offered load ×1.0, n_seeds=40 paired.

### 29.1 The standing branch, read first — and it was right

P3 registered, before looking: *"30/40 under" may be one
chronically-incomplete video flow rather than thirty failures, since M05's
bound only applies to `xr_video`.*

**Measured — M05 breach counts are over SEEDS, and the breaching flows are
a handful:**

| arm | seeds under 0.99 (base) | **distinct flows** | concentration |
|---|---|---|---|
| PF | 4/40 | 4 | scattered |
| Reservation | 33/40 | **2** | `ue8_qfi2` ×24, `ue7_qfi2` ×9 |
| TwoTier | 35/40 | 4 | **`ue6_qfi2` ×30**, then ×2, ×2 |

**"33/40 breaching" is two flows, not thirty-three failures.** M01/M03/M06
behave the same way (3–5 distinct flows behind 6–12 seed breaches). The
count answers *how many seeds contained a breach*, never *how many flows
breached* — and every one of those flows is a `qfi 2` video flow except
M03's, which is telemetry.

### 29.2 P3's question — pre-existing on every statistic

| metric | arm | base | bg | Δ | verdict |
|---|---|---|---|---|---|
| M01 | TwoTier | 6 | 8 | +2 | pre-existing |
| M03 | TwoTier | 1 | 2 | +1 | pre-existing |
| M05 | PF / Res / TwoTier | 4 / 33 / 35 | 3 / 30 / 35 | −1 / −3 / 0 | **pre-existing** |
| M06 | TwoTier | 7 | 12 | **+5** | pre-existing, **widened** |

*(PF and Reservation breach nothing on M01, M03 or M06 in either cell.)*

**Nothing is aggressor-created — no statistic goes from 0 breaches at base
to non-zero under `bg`. So G6 passes its FIRST conjunct too**, on every
arm.

**The SECOND conjunct is where the qualification lives, and this sentence
previously dropped it.** It read *"§28.1's headline stands unqualified:
G6 passes both clauses, on the protected fleet, on every arm."* Corrected:
**clause 1 passes on every arm; clause 2 passes on M02 on every arm and is
INCONCLUSIVE on M20 for TwoTier** (+29.35 % [+4.81, +56.18], interval
excluding zero, straddling the +20 % bar — §27.2, §28.1).

*(`prediction-journal.md`'s P2 entry carries the same "stands unqualified"
phrasing and is **deliberately not edited** — it is a pre-registration
written before the data, and its value is that it is unedited. The live
claim is this one.)*

**M06's +5 is the messiest outcome P3 named in advance**, and it lands
exactly where predicted: non-zero in both cells but materially higher under
`bg`. **G6's wording supplies no rule for how much widening counts** — it
says "stays within its bound", not "does not breach it more often". A
statistic that breaches on 7 seeds without the aggressor and 12 with it is
neither clearly passing nor clearly failing under the text as written.
**That is a finding about the guarantee's specification, not about the
scheduler**, and it belongs with §0.6's other two.

### 29.3 THE G5 FINDING — and it is not a G6 one

**M05's breaches are pre-existing, which means they are a G5 failure at the
base cell with no aggressor present.** G5 is *"Operators and the AI always
see fresh, complete video"*, bar *"≥ 99 % of PDU sets complete within
PDB"* (`IA_P5G_Factory_Guarantee_Test_Plan.md:99`).

**It is severe, and it is not a thin-sample artefact** — checked before
quoting, per the rule §29.1's own prediction came from:

| arm | min | median | max | seeds < 0.99 |
|---|---|---|---|---|
| PF | 0.9868 | 0.9934 | 1.0000 | 4/40 |
| **Reservation** | **0.0000** | **0.0000** | 1.0000 | 33/40 |
| **TwoTier** | **0.0000** | **0.0000** | 1.0000 | 35/40 |

**On more than half of all seeds, both QoS-aware arms have a video flow
whose PDU-set completeness is ZERO.** The zero flows carry
**frame_count 147–148** against sibling video flows at 152 — so the flow
produced ~148 frames and **completed none of them within its 150 ms PDB**.
Not a flow with two frames and bad luck.

**PF has no zero cells at all.** Its worst seed is 0.9868.

**This is §0.1's documented concentrate-vs-spread split, arriving for the
first time on a GUARANTEE BAR rather than on a comparative metric.** PF
spreads capacity and every video flow clears 98.7 %; the QoS-aware arms
concentrate and one video flow per run gets nothing. §0.1's rule has always
said neither arm is simply better — but on G5's own pass criterion, at the
base cell, **PF passes and both QoS-aware arms fail.**

**Filed as G5, not G6.** It surfaced inside the G6 work only because Step 3
evaluated a conjunct nobody had evaluated before; no aggressor is involved
and the failure is present at the base point. It belongs in G5's row.

### 29.4 P3 scored — one clean hit, one miss, and the branch that mattered

| clause registered | outcome |
|---|---|
| M05's breaches **pre-existing on all three arms** | **HIT** — Δ −1 / −3 / 0 |
| TwoTier's M01/M03/M06 **partially aggressor-driven, at materially lower base counts** | **MISS for M01/M03** (6→8, 1→2 — within noise at n_seeds=40), **HIT for M06** (7→12) |
| the messiest outcome needs a widening rule G6 does not supply | **HIT** — M06 is exactly that cell |
| **standing branch**: "30/40" may be one chronic flow | **HIT, decisively** — 2 distinct flows behind 33 breaches |

**The standing branch was the most valuable clause again**, and this time
it was cheap: predicted before the data existed, confirmed on arrival, and
it changed how the headline number is read. Contrast the same insight's
three earlier appearances (§24.2, §25.4, §28.1), each of which cost a
published conclusion first.


---

## 30. Part C — the depth §21.5 bought, and a count-in-prose correction

`scripts/wp9_part_c.py`. §21.5's pre-registered rule bought depth for
`duty_cycle` and `snr_spread_db` (both had a paired CI excluding zero) and
not for `bg` (§22.7).

**§21.7's budget said "~10 cells". The grid §21.5 actually specifies is
24** — each axis × 2 levels × (4 `n_ues` + 2 off-base `load_mult`) — and
the runner prints its own count rather than restating one. **Fifth instance
of the count-in-prose rule**, and the first where the prose and the spec
were in the *same document*: §21.5 described the cross correctly and §21.7
budgeted a number nobody derived from it. Serial cost is therefore ~3 h,
not the ~15 min at 10 workers §21.7 implied — the runner is serial and was
not parallelised, which is the honest cost of the grid as specified.

**M03's cadence caveat is attached automatically** (Step 4,
`sim/scorecard.py`): at **`duty_cycle` 0.1** the telemetry source's own
period (1000 ms) exceeds the 500 ms T_live/4 bound, so `max_gap_ms` reports
cadence rather than a liveness failure. *(This read "≤ 0.5"; at duty 0.5
the period is 200 ms and the caveat does not fire — see the correction box
in §24.6. The wider wording discarded a real TwoTier breach.)* It is derived from each flow's own median
gap and travels **in the record**, so Part C's M03 column cannot be read
against that bound by mistake.

### 30.1 Results — 24 cells, 720 runs, 10 workers, ~28 min

M07 contracts met / M08 worst-flow GFBR fraction, mean over 10 paired
seeds, at `load_mult` 1.0. **§0.1's rule applies throughout: both numbers
are quoted together, every time either is quoted.**

| axis | n_ues | PF | Reservation | TwoTier |
|---|---|---|---|---|
| `duty_cycle` 0.1 | 4 | 3.8 / 0.972 | 3.8 / 0.968 | 3.7 / 0.965 |
| | 8 | 1.0 / **0.847** | **3.1** / 0.380 | 1.4 / 0.627 |
| | 16 | 0.0 / **0.445** | 0.0 / 0.000 | 0.0 / 0.271 |
| | 32 | 0.0 / **0.216** | 0.0 / 0.000 | 0.0 / 0.000 |
| `duty_cycle` 0.5 | 4 | 3.9 / 0.961 | 3.9 / 0.961 | 3.9 / 0.961 |
| | 8 | **7.6** / **0.952** | 6.8 / 0.190 | 5.2 / 0.525 |
| | 16 | **12.8** / **0.922** | 10.5 / 0.000 | 4.5 / 0.000 |
| | 32 | 0.0 / **0.475** | 2.6 / 0.000 | **5.6** / 0.000 |
| `snr_spread_db` 6 | 4 | 4.0 / 0.965 | 4.0 / 0.964 | 4.0 / 0.965 |
| | 8 | **8.0** / **0.962** | 7.3 / 0.288 | 6.6 / 0.919 |
| | 16 | 9.6 / **0.795** | **10.5** / 0.000 | 9.2 / 0.000 |
| | 32 | 0.0 / **0.382** | **14.3** / 0.000 | 7.2 / 0.000 |
| `snr_spread_db` 12 | 4 | 4.0 / 0.965 | 4.0 / 0.965 | 4.0 / 0.965 |
| | 8 | 7.9 / **0.961** | 7.1 / 0.095 | 7.0 / 0.941 |
| | 16 | 9.0 / **0.596** | **10.4** / 0.000 | 7.8 / 0.000 |
| | 32 | 0.0 / **0.289** | **15.0** / 0.000 | 7.4 / 0.000 |

**Finding 1 — §0.1's split reproduces on BOTH new axes, at every fleet size
above 4.** At n_ues=32 on `snr_spread_db` 12: **Reservation meets 15.0
contracts and PF meets 0.0, while PF holds a 0.289 max-min floor and both
QoS-aware arms sit at exactly 0.000.** That is §0.1's pattern verbatim, on
axes stage 2 never ran. **The split is therefore not an artefact of the two
axes the stage-1 cap happened to promote** — which is the strongest
available answer to §0.4's standing complaint that the cap, not the score,
did the narrowing.

**Finding 2 — the axes do NOTHING at n_ues=4.** All three arms are
identical to three significant figures on both axes at every level
(3.7–4.0 / 0.961–0.972). **The effects Part A measured at the n_ues=8 base
point are fleet-size-dependent, not properties of the axes themselves**, and
a reader quoting Part A's single-cell result should carry that.

**Finding 3 — `duty_cycle` 0.5 is worse than 0.1 for contracts and better
for the floor, non-monotonically.** At n_ues=16, duty 0.5 gives PF
12.8 / 0.922 while duty 0.1 gives 0.0 / 0.445 — the burstier setting
destroys contracts outright. **Duty cycle is not a monotone axis**, so a
two-level reading of it (which is all Part A had) can invert.

**What this does NOT establish.** Every cell is `load_mult` 1.0; the load
line was run but is not analysed here. M03 in these cells carries its
**cadence caveat** automatically at `duty_cycle` ≤ 0.5 (Step 4) and is not
quoted above for that reason.

---

## 31. G9 — the join/re-join campaign (plan, registered before any code)

### 31.1 What G9 asks, from the test plan's own text

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md:103`:

> **G9** | A robot joins (or re-joins after an outage) quickly, even on a
> busy cell. | Warm app re-handshake p95 ≤ ▷ 1 s; full attach-to-streaming
> ≤ ▷ 15 s; post-RLF time-to-SLO ≤ ▷ 10 s; **neighbours unaffected
> throughout**.

**Four distinct measurements with three different instruments, and this
simulator cannot produce all four.** Taken one at a time rather than
assumed:

| # | clause | instrument | can this sim produce it? |
|---|---|---|---|
| 1 | warm app re-handshake **p95 ≤ 1 s** (GT-6.1) | M18, `path="warm"` | **YES** — the app-handshake message pair exists (`JoinConfig.handshake_ul_qfi`/`handshake_dl_qfi`, WP-Join commit 6) |
| 2 | full **attach-to-streaming ≤ 15 s** (GT-6.2) | M18, `path="cold"` | **PARTIALLY** — the sim models RACH+RRC, PDU-session and handshake as *sampled* delays from `JoinConfig`'s floors/ceilings, which are **calibration-log timers, not a measured attach trace**. It produces a number; that number is a restatement of its own configured distribution, not an independent measurement. **Reported as such or not at all.** |
| 3 | post-RLF **time-to-SLO ≤ 10 s** (GT-6.3) | M19, `path="reestablish"`, measured from RF-restore | **YES in mechanism** — `sim/rlf.py` detection + `sim/join.py` recovery + `ScriptedFadeWindow` — but see §31.4 on M19's own blindness. |
| 4 | **neighbours unaffected throughout** | a delta on the *non-recovering* UEs | **YES**, and it is the clause most at risk of the §24 error — see §31.6. |

**Clause 2 is the one to be honest about.** `JoinConfig`'s
`rach_rrc_setup_floor_ms=20` / `ceiling=400`, `cell_search_ceiling_ms=3000`
and the reestablishment floor are **t300/t301/t311 ceilings from the
calibration log plus one RACH trace**, with the module's own comment
recording that the reestablishment floor is *"a BORROW from the one RACH
trace, not a reestablishment-specific measurement"*. A p95 computed from
sampling those bounds tells you what you configured. **Clause 2 is
`SIM-informative` at best and its plan row must say so.**

### 31.2 What already exists — established by reading, not from §6.3's budget note

**Built and live:** `sim/join.py` (the FSM: `JoinConfig`, `JoinState`,
`JoinPhase`, `JoinRngStreams`, `JoinAwareBufferView`), `sim/rlf.py`
(n310-armed t310 dwell, n311-gated cancel), the driver wiring (`rlf.step()`
per UE per slot; `JoinAwareBufferView` composed outermost),
`SchedulerContextReset` on TwoTier, `ScriptedFadeWindow`, `JoinEventRecord`,
and M18/M19 in the panel. `sim/tests/test_join*.py` and
`test_wpjoin_rlf_recovery.py` cover the transitions.

**NOT built: a scenario.** `grep` finds **no `JoinConfig` anywhere** outside
`sim/join.py` and `sim/config.py` — no scenario, no script, no sweep.
That is the whole of §21.2a's finding, confirmed directly.

**So G9 is scenario + runner + analyser work, not mechanism work** — which
makes it lighter than "needs implementation" implied, and the §6.3 budget
note (~72 min for 50 cycles) is a runtime estimate, not a build estimate.

### 31.3 The M18/M19 check — RUN, not assumed

A throwaway probe (2 UEs, one with a scripted `app_restart`, 8,000 slots):

```
join_events recorded: 1     path=warm  trigger_slot=1000  attached_slot=None
M18: status=ok      by_path.warm = {n_events: 1, n_never_completed: 1, p50_ms: None, ...}
M19: status=proxy   by_path.warm = {n_events: 1, n_never_recovered: 0, p50_ms: 0.0, ...}
```

**This settles §21.2a's gap concretely: M18 flips `pending` → `ok` and M19
`pending` → `proxy` the moment a single join event exists.** Nothing else in
the panel can do that.

**And it exposes two degeneracies a naive scenario produces**, both of which
the real campaign must avoid:

1. **`attached_slot=None`, `n_never_completed=1`** — the event never
   completed, so every latency is `None`. M18's own panel note predicts
   exactly this: the handshake needs `handshake_ul_qfi`/`handshake_dl_qfi`
   **set to QFIs the UE actually has flows for**. My probe set neither.
2. **M19 reports `p50_ms = 0.0` with `n_never_recovered: 0`** — "recovered
   instantly", because the UE's flows were never outside PDB to begin with.
   **A recovery time of zero is not a pass, it is an absent event.**

**Both are scenario-design requirements, and both are pre-registered here so
the first run cannot be mistaken for a result.**

### 31.4 M19's registered blindness must travel with every G9 number

`config/metric_panel.yml`'s M19 row already carries the caveat WP-Join
commit 8 found: `sim/buffer.py::expire()` evicts the queue head before it
can age past `pdb_ms`, **so a flow that never delivers anything can read as
"green"**. M19's SLO-green test is head-of-line age, not delivery.

**Consequence for G9, stated in advance:** a UE whose flows are being
dropped wholesale during recovery can produce a *short* time-to-SLO. **Any
M19 number in this campaign is reported beside that UE's M02 (PDB-violation
rate) for the same window**, exactly as §29 had to do for M05. A G9 pass on
M19 alone is not a pass.

### 31.5 Scope, and corpus exposure

**Three scenarios, one runner, one analyser. No `sim/` or `scheduler/`
behaviour change.** Every mechanism G9 needs is already wired and already
runs on every scenario — a scenario that sets `UEConfig.join` merely
*exercises* paths that are otherwise inert.

**Prediction registered: `regression_corpus.py --check` CLEAN on all 20
records.** The corpus scenarios configure no `join`, so `join_states` is
empty and both wrappers are no-ops. **If it moves, the mechanism is not as
opt-in as WP-Join claimed, and that is a finding about WP-Join, not about
G9.**

### 31.6 The neighbours clause — decompose BEFORE attributing

**"Neighbours unaffected throughout" is a delta guarantee of exactly G6's
shape**, and the G6 item cost four corrections to the same error. So the
population is fixed here, in advance, before any number exists:

- **The statistic is computed over: every UE EXCEPT the one joining or
  recovering** — and, within those, over its **protected** bearers only
  (`Scorecard.NON_PROTECTED_5QI` excluded), because a background flow's own
  service is not what "neighbours unaffected" is about.
- **The claim is about: the same set.** Named so the two cannot drift.
- **The comparison is paired within seed**, joining-UE-present vs a control
  with the same seed and no join event — not a before/after within one run,
  because the recovering UE's traffic is absent from the "before" window by
  construction.
- **The estimator is `robust_delta_summary`** (median + IQR + `frac_worse`
  + n_seeds), never a bare mean — Step 4's default, and M18/M19 are
  max-type.

**Registered check, to be run before any neighbours number is quoted:** for
each statistic, print the flow set that entered it and assert the
recovering UE's flows are absent. **A neighbours statistic that includes the
recovering UE is measuring the event, not the containment.**

### 31.7 Pre-registered expectations — shapes, with each shape's meaning

Written in the form the journal now requires: **what the data will look
like, and what each look would mean.** No mechanism is predicted.

| # | expectation | what each outcome would mean |
|---|---|---|
| **J1** | With `handshake_*_qfi` correctly wired, **`n_never_completed` drops to ≈0** on the warm path and M18 reports real p50/p95. | Still 100 % never-completed ⇒ the handshake pair is not being delivered at all, and the scenario, not the FSM, is wrong. |
| **J2** | Warm-path M18 p95 is **bounded by `app_restart_delay` + one handshake round trip**, i.e. it will look like a *narrow* distribution near its configured floor, not a heavy tail. | A heavy tail ⇒ the handshake is queueing behind load, which is the one genuinely informative thing GT-6.1 can tell us and would be the finding. |
| **J3** | **Cold-path M18 restates its own configured distribution** — p95 near the sampled ceiling sum, insensitive to offered load. | Load-sensitivity ⇒ the sampled delays are *not* dominating and the number is more than a restatement, which would upgrade clause 2 from `SIM-informative`. |
| **J4** | **M19's reestablish path produces a non-degenerate number** (not 0.0) once a scripted fade actually breaks SLO. | Still 0.0 ⇒ §31.4's blindness is active and M19 is unusable for G9 without the M02 companion. |
| **J5** *(most-likely-wrong)* | **Neighbours are NOT unaffected: at least one protected neighbour statistic shifts with an interval excluding zero** during a cold attach, because a joining UE takes PRBs and PDCCH from a loaded cell. | Unaffected ⇒ the containment is real and G9's fourth clause passes cleanly, which given §0.1's concentrate-vs-spread pattern would be genuinely surprising. |

**J5 carries the standing trace obligation.** It is this stage's registered
most-likely-wrong, and that slot has produced the more interesting finding
four times in this WP. **If J5 misses — if neighbours really are unaffected
— it gets a worktree-instrumented direct-cause trace before write-up**,
distinguishing "the scheduler contains the join" from "the join is too
small to see at this load", which are different claims and only the first
is G9 passing.

### 31.8 Commit sequence

1. This section. Docs only.
2. The three scenarios (GT-6.1 warm, GT-6.2 cold, GT-6.3 RLF) + their
   tests, including a test that `handshake_*_qfi` matches a real flow —
   the defect §31.3 found by probe.
3. The runner, persisting records (`PersistingRecordSink`), and the
   neighbours-population assertion from §31.6.
4. The campaign run; **J1–J5 scored, hits and misses both**.
5. Regime-map G9 row + the guarantee inventory updated from results.

Full suite + `--check` after each. **§31.5's clean-corpus prediction is
scored at commit 2**, the first point at which it could move.

### 31.9 Commit 2 — landed, with two scenario defects caught by running them

**§31.5's corpus prediction: HIT.** `--check` clean on all 20 records; 846
passing (20 new). Scenario construction only — no `sim/` or `scheduler/`
behaviour change, as predicted.

**All three scenarios produce non-degenerate events** (PF, 3 neighbours):

| scenario | events | M18 |
|---|---|---|
| GT-6.1 warm | 7 warm, **0 never completed** | p50 **1.5 ms**, p95 **6.5 ms** |
| GT-6.2 cold | 4 cold, **0 never completed** | p50 **74 ms**, p95 **164 ms** |
| GT-6.3 RLF | 1 reestablish | p95 **1055.75 ms**; phases cell_search 997.75 / reestablish 25.25 / handshake 32.75; **rf_restore_to_attached 58.0 ms** |

**So §31.3's first degeneracy is closed** — `n_never_completed` is 0
everywhere, against 100 % in the probe.

**DEFECT 1, caught by the probe before commit 2: the handshake QFIs.**
`JoinConfig` cannot validate them (it never sees the flow list) and a wrong
or absent pair does not raise — it silently yields all-`None` latencies.
`validate_handshake_wiring()` is the guard, every builder calls it, and
three tests pin the failure modes. Narrowed while testing:
`JoinConfig.__post_init__` **already** rejects a *half*-set pair, so the
reachable defect is **both unset**, which it allows by design as the
pre-commit-6 default. That is exactly what the probe hit.

**DEFECT 2, caught by RUNNING GT-6.3: the fade was half of t310, and the
scenario produced ZERO RLF events.** `sim/rlf.py`'s `RlfDetectorConfig` —
which the driver constructs, **not** `JoinConfig`'s identically-named field
— carries **t310 = 2000 ms**, i.e. **8,000 slots** at numerology 2. The
first fade was 4,000 slots, so the dwell re-armed and RLF was never
declared. **Zero events reads as "recovery was instant", not as "the
scenario never fired."** Depth arms t310; **duration expires it**, and both
are needed. Fade is now 12,000 slots (1.5× t310) with a test asserting
`fade_len > T310_SLOTS_MU2`, and the constant is derived in the module
rather than restated.

**A divergence from the test plan, recorded rather than silently taken:**
GT-6.3 specifies a **10 s** obstruction; this uses **3 s**. 10 s is 40,000
slots and would need a ~60,000-slot horizon. The detector only requires
t310 to expire — the 10 s figure is the hardware's obstruction duration,
not a detection threshold.

**J4's precondition is already visible and it is NOT yet met.** M19 reports
`p50_ms = 0.0` on every path, with `n_never_recovered` 3/7 (warm) and 2/4
(cold). That is §31.4's registered blindness: the joiner's flows are either
never out of SLO, or never recovering. **The campaign scenario needs the
recovering UE's flows to actually breach PDB for M19 to mean anything**, and
J4 is registered against exactly this.


---

## 32. G9 commit 3 — J4 solved STRUCTURALLY, because M19 cannot report red

J4 taken first, as the campaign's blocker. **The answer is not a scenario
that breaches PDB harder — no such scenario exists.**

### 32.1 What "actually breach PDB" requires, and why nothing can

M19's green test is `_first_sustained_green`: every flow's
`ts_hol_delay_s` within its own `pdb_ms` for `slo_green_dwell_s`.
`sim/buffer.py::expire()` pops any chunk older than the PDB **every slot**
(`while chunks and (now_s - chunks[0][0]) > pdb_s`), so **head-of-line age
is capped at `pdb_s` by construction.**

Measured on G9's own scenarios, joiner UE:

| scenario | flow | pdb | max HoL | slots over PDB | bytes dropped |
|---|---|---|---|---|---|
| cold | qfi 1 | 100 ms | **100.00 ms** | **0 / 20,000** | 900 |
| cold | qfi 2 | 150 ms | 149.88 ms | **0 / 20,000** | 16,511 |
| rlf | qfi 2 | 150 ms | **150.00 ms** | **0 / 30,000** | **1,396,203** |

**A UE losing 1.4 MB of video reads GREEN on every slot of the run.**
`hol > pdb_ms` is never true, so M19's recovery time is 0.0 ms by
arithmetic, not by the UE recovering.

**So M19's registered caveat understates it.** The caveat says a
never-delivering flow *can* read green; the measurement says it **always**
does — M19 has no red state at all. **That is not tunable**, and a scenario
adjusted until M19 moved would be fitting the fixture to the metric.

### 32.2 The fix: a companion metric, not an edited one

**M19 is left byte-for-byte unchanged.** Editing a pre-registered metric is
what `config/metric_panel.yml`'s own guard forbids, and every historical
M19 reading must keep meaning what it meant. **M21
(`slo_recovery_time_by_delivery`) is an ADDITION** — the same disposition
Step 2 used for M03/M20, and the fix M19's own caveat names ("a true fix
needs the PDB-violation rate itself (M02-style), not head-of-line age
alone").

Green = a window in which the UE's flows drop or deliver-late ≤ 1 % of
their **arriving bytes**. Measured, same runs:

| path | M19 | **M21** |
|---|---|---|
| warm | 0.0 ms | **0.0 ms** — correct; a warm app restart never interrupts the radio |
| cold | 0.0 ms | **p50 1449 ms / p95 2949 ms** |
| reestablish | 0.0 ms | **13.5 ms** |

**J4 is met: M21 produces a non-degenerate number where M19 structurally
cannot**, and warm staying at 0.0 is the control that shows M21 is not
manufacturing delay.

### 32.3 A defect in M21's own first version, caught by running it

The first implementation compared bytes **dropped in slot i** against bytes
that **arrived in slot i**. But a chunk is dropped `pdb_ms` *after* it
arrived, so those are different bytes — the ratio was near-meaningless and
**returned 0.25 ms on the UE that had just lost 1.4 MB**. Summing both over
the same window removes the offset and matches M02's byte-weighted form.
Pinned by a test with arrivals and drops deliberately offset, which a
per-slot ratio scores as recovered.


### 32.4 Did §29's G5 finding rest on M19? CHECKED — no

Asked because if M19 had been quoted there it would have been reporting
green on exactly the flows M05 showed completing nothing.

**It was not.** M19 does not appear anywhere in §29, and could not have:
it has read `pending` on every row of every WP9 stage (§21.2a), so it never
produced a value to quote. **§29's G5 finding rests on M05 alone and is
unaffected.**

**But the near-miss is worth naming, because it is the same fault line.**
M05 caught the zero-completeness flows precisely because it measures
**completion**; M19 could not have, because it measures **head-of-line
age**. The metrics that can see a flow failing are the delivery-based ones
(M02, M05, now M21); the age-based one is blind to it by construction.
**When choosing which metric answers a question about whether traffic got
through, prefer a delivery-based statistic — an age-based one can be
capped by the very mechanism that drops the traffic.**


---

## 33. G9 commit 4 — the campaign runner, and a neighbours statistic that could not fail

Two assertions run before any metric is read, and the runner refuses to
report if either fails (`scripts/g9_campaign.py`).

### 33.1 The two registered assertions, both firing

**Event-count assertion** (CLAUDE.md's sixth empty-selection instance):
per case, assert non-zero events **of the expected path** — `warm` for
GT-6.1, `cold` for GT-6.2, `reestablish` for GT-6.3 — not merely "some
events". A scenario producing none reads identically to one where
everything went well, which is exactly how the t310 defect hid.

**Neighbours-population assertion** (§31.6): the runner **prints** the flow
set that enters the statistic and asserts the joiner's flows are absent.
Measured: 9 protected flows from `ue2`/`ue3`/`ue4`, none from `ue1`.

### 33.2 THE FINDING — the neighbours clause was VACUOUS as first built

The first campaign returned **ΔM02 = 0.000000 on every arm, every case,
every seed, with `worse 0%`.** An exact zero everywhere is the signature
this project has recorded twice — a statistic that cannot move, wearing a
result.

**Decomposed before quoting, per the standing check:** the neighbours'
absolute M02 was **0.0 in both conditions**, at **22 % UL utilisation**,
with every protected flow at zero drops and zero late bytes. **ΔM02 = 0 − 0
is arithmetically correct and detects nothing** — J5 could never have been
falsified.

**Cause: the scenarios omitted the load GT-6 specifies.** GT-6.1 says
*"while Asset A runs full profile **+ bg saturation**"*; GT-6.2 *"against a
**loaded cell**"*. The builders had no `bg`. Added as a 50 Mbps 5QI-8
aggressor — which `Scorecard.NON_PROTECTED_5QI` already excludes from the
neighbours statistic, so it loads the cell without entering the population.
**UL utilisation 0.222 → 0.876.**

### 33.3 And even loaded, M02 on the neighbours is FLOORED

At 0.876 UL utilisation the neighbours' protected flows still show **m02 =
0.0** and **p98 = 15.5 ms against a 100 ms PDB — roughly 6× headroom.**
The QoS-aware arms are doing exactly what they should: a best-effort flood
is deprioritised and protected bearers are untouched.

**But a delta of a floored statistic still cannot move.** So the campaign
reports **both**: ΔM02, which is the guarantee's own currency, and **Δp98,
which is the instrument with dynamic range**. A "neighbours unaffected"
pass read off ΔM02 alone would be a statement about the floor, not about
containment — the same error shape as §28.1's M02 and §24.2's M03, caught
here **before** any number was quoted rather than after.

**Consequence for J5:** it is now falsifiable. If neighbours are genuinely
disturbed by a join, Δp98 can show it; if ΔM02 and Δp98 are both flat, that
is a real null rather than a floored one.

---

## 34. G9 campaign — J1–J5 scored

10 paired seeds, 3 arms, 3 cases, 7 neighbours + bg. Both registered
assertions passed on every run: non-zero events of the expected path, and
a neighbours population of **21 protected flows from ue2–ue8, none from
the joiner**.

### 34.1 Scoreboard

| # | expectation | verdict |
|---|---|---|
| **J1** | handshake wired ⇒ `n_never_completed` ≈ 0, real M18 p50/p95 | **HIT** — warm M18 p95 = 16.6 (PF) / 21.0 (Res) / 79.6 ms (TT) |
| **J2** | warm p95 a *narrow* distribution near its configured floor | **MISS on TwoTier, HIT on the others** — 16.6 / 21.0 vs **79.6 ms**, ~4× |
| **J3** | cold M18 restates its configured distribution, load-insensitive | **HIT** — PF 145.25 vs Res 147.75 ms, near-identical across arms |
| **J4** | M19 reestablish non-degenerate once a fade breaks SLO | **HIT on the registered form** — still **0.0 on every arm and case**, so §31.4's blindness is confirmed active and M21 supplies the number (PF 130.1 / Res 142.1 ms) |
| **J5** *(most-likely-wrong)* | neighbours **disturbed**: ≥1 protected statistic shifts with an interval excluding zero | **MISS** — two cells exclude zero and both move the **wrong way** |

### 34.2 J5's miss, and the trace it obligated

Two cells have Δp98 intervals excluding zero, **both negative**:
GT-6.2 cold / TwoTier **−8.995 ms [−14.234, −3.085]** and GT-6.3 / PF
**−1.268 ms [−2.074, −0.504]**. **Neighbours measurably IMPROVE when the
join schedule is present.** ΔM02 stays floored at zero everywhere, exactly
as §33.3 predicted, so Δp98 is the only instrument that saw anything —
which is the dynamic-range rule paying for itself.

**The obvious explanation is that the joiner is absent part of the run and
therefore competes less. The trace refutes it.** Over the campaign's own
10 seeds, TwoTier GT-6.2:

- the joiner delivers a **median 9.9 %** of its control bytes — it really is
  almost entirely absent;
- neighbours' Δp98 median is **−9.289 ms**;
- **correlation between joiner-absence and neighbour improvement:
  r = −0.028.**

**Essentially zero.** Absence is near-constant across seeds (ratio 0.095–
0.105) while Δp98 swings from **−23.9 to +9.1 ms**, so the variance is not
explained by how much the joiner got out of the way. **My explanation was
wrong, and so was J5's direction.**

**What the trace was obligated to distinguish** — "the scheduler contains
the join" vs "the join is too small to see at this load" — **is answered by
neither.** A third possibility is what the data shows: the effect is real
and sizeable (±10–24 ms swings) but **not attributable to the joiner's
resource footprint at all**. Its cause is unidentified. **Recorded as
unexplained**, per the standing rule that an unexplained result is a
legitimate finding and an invented mechanism is not.

### 34.3 A control-design limitation this exposes, stated plainly

The paired control removes the **join schedule**, which also removes the
joiner's **outages**. So the comparison is *"joiner sometimes absent"* vs
*"joiner always present"* — it cannot separate the cost of the **join
procedure** from the effect of the **UE being gone**. That the correlation
is ~0 shows absence is not driving the p98 result, but the confound is
structural: **for this workload no control can hold the joiner's offered
load constant while varying whether it joins, because being off IS the
outage.**

**Consequence: G9's fourth clause is answerable only in the weak form** —
"no neighbour statistic degrades with an interval excluding zero" — and
that form **passes on all nine arm-cases**. The strong form, isolating the
join procedure's own cost, needs a control this scenario shape cannot
provide.

### 34.4 An anomaly, not scored, recorded for its own commit

**TwoTier registers far fewer join events than the other arms** and many do
not complete: warm **3.8 events/run vs 10.0**, cold **1.0 vs 5.0** with
M18 p95 `None` (nothing completed), and GT-6.3 M21 `None`. Its warm M18 p95
is also ~4× the others (79.6 ms), which is J2's own "handshake queueing
behind load" branch.

**A plausible link is that a slower handshake overlaps the next scripted
restart, so events are dropped rather than queued — but that is a
hypothesis, not a finding, and the event-count assertion passed because it
checks non-zero, not the expected count.** Worth its own investigation;
**strengthening that assertion to check the expected count is the cheap
guard**, and it would have flagged this on the first run.

> **The hypothesis in the paragraph above was taken up and is REFUTED —
> §34.5a.** The overlap never happens. And "cold 1.0 vs 5.0" counts events
> *recorded*; the count of cold attaches *completed* is **0 of 50**.

### 34.5 TwoTier's event shortfall — a mechanism proposed here, and REFUTED in §34.5a

Checked rather than left beside J5's unexplained result. Same scenario,
same seed, GT-6.1, per-event duration in slots from trigger to attached:

| arm | events recorded | durations (first six) |
|---|---|---|
| PF | **10 / 10** | 36, 46, 26, 6, 6, 6 |
| **TwoTier** | **7 / 10** | **337, 851, 441, 411, 282, 241** |

**TwoTier's app handshake takes 6–24× longer than PF's**, against a scripted
restart period of **1,600 slots**. When a handshake is still in progress as
the next scripted restart fires, the FSM has no in-progress restart to
restart and the event is **dropped**. So the shortfall is neither purely a
scheduler property nor purely a scenario one — **it is the interaction**:
a slow arm against a fixed period silently loses events.

**Two consequences, and the second is the serious one.**

1. **It confirms J2's named branch with a mechanism.** J2 predicted a narrow
   distribution near the configured floor and said a heavy tail would mean
   *"the handshake is queueing behind load, which is the one genuinely
   informative thing GT-6.1 can tell us"*. It is queueing, and these are the
   durations.
2. **The arms in §34.1 were not comparable.** PF's M18 is computed over 10
   events per run and TwoTier's over 3.8 — and the survivors are
   **self-selected**: precisely the restarts whose predecessor finished in
   time, i.e. the *fastest* ones. **TwoTier's 79.6 ms warm p95 is therefore
   biased optimistic**, and the true gap to PF's 16.6 ms is wider than
   reported, not narrower. The strengthened assertion now refuses to report
   this rather than averaging over it.

**The fix is a scenario change, not a metric one** — the restart period must
exceed the slowest arm's handshake — and it is deliberately **not** made
here: re-running the campaign with a longer period is its own commit with
its own before/after, and §34.1's numbers stand as what the current
scenario produced, now with the bias direction stated.

### 34.5a THE MECHANISM ABOVE IS REFUTED — the handshake never completes at all

§34.5's overlap story was checked by re-running the campaign's exact
configuration for all three arms across its own ten `paired_seeds(10)`
seeds, counting both **events recorded** and **attaches completed**
(`attached_ts_s is not None`, the same test M18's `n_never_completed` uses).

| case | scheduled | PF | Reservation | TwoTier |
|---|---|---|---|---|
| **cold** (GT-6.2, 5/run × 10 seeds = 50/arm) | 50 | 50 events / **50 completed** | 50 / **50** | **10 events / 0 completed** |
| **warm** (GT-6.1, 10/run × 10 seeds = 100/arm) | 100 | 100 / **100** | 100 / **100** | 38 / **29** |

**TwoTier completed ZERO of its 50 scheduled cold attaches, on every one of
the ten seeds.** Exactly one cold event is recorded per seed — always the
*first*, at trigger slot 2800 — and the remaining four cycles produce no
event at all. The warm arm reproduces the committed campaign's 3.8
events/run bit-for-bit, which is how this re-run is known to be the same
configuration.

**Why the overlap mechanism cannot be what happened.**

- **Cold: nothing ever completed**, so no event was displaced by a slow
  predecessor. There is no survivor population to be self-selected *from*.
- **Warm: no completed handshake ever collided with its successor.** Every
  completed attach landed **21–1,086 slots** after its trigger against a
  **1,600-slot** period. In all ten seeds the truncation is a **terminal
  stall** — the last recorded event never completes and every later
  scheduled restart is discarded, and the run simply ends there.
- **§34.5's own table already showed this and it was not read that way.**
  Its longest quoted duration is **851 slots against a 1,600-slot
  period** — comfortably inside. The section's evidence contradicted its
  mechanism on the page.

**What actually happens** (traced, seed 1826701614, TwoTier, scheduler spy
over `allocate()`): the joiner receives **122 UL grants, all at slots
1–1997, and zero at any slot ≥ 2000** — none in the 4,000-slot PDB window
after the 64-byte handshake request is injected at ~slot 2824. PF gets 823
UL grants to the same UE after that instant. The request expires unserved
(`ue1_qfi70`: 64 bytes dropped to PDB). **The masking/BSR path is ruled
out**: `APP_HANDSHAKE` is inside `_RADIO_CONNECTED_PHASES` and the flow
shows `bytes_reported > 0` on 1,296 slots — TwoTier saw a reported,
unmasked, backlogged flow and never granted it.

**Two `sim/join.py` properties then make the stall permanent and silent**,
and they are defects in their own right:

1. `JoinPhase.APP_HANDSHAKE` has **no ceiling and no retransmission** — it
   waits only on `handshake_complete`, and nothing re-injects a dropped
   request.
2. Scripted events are **consumed by index whenever `candidate.slot ==
   slot_index`, regardless of phase**, so the four later power_off/power_on
   pairs are advanced past and **discarded rather than deferred**.

The joiner is radio-gated out of the cell for **17,176 of 20,000 slots
(86 %)**.

**The instruction changes, and this is the operational point.** Not
*"lengthen the scripted restart period"* — no period fixes a handshake that
never completes. It is **(a) find why TwoTier stops issuing UL grants to
the joiner after re-attach**, and **(b) fix the two silent-stall defects
above.** For (a) the prime suspect is TwoTier's post-`reset_ue(scope=
"full")` / Tier-1 re-solve state for a UE radio-gated across the re-solve —
**a lead, not a finding**, and it needs its own trace before anything is
written down.

**Downstream consequences, because they change how §34.1 reads.**

- TwoTier's cold numbers are **not a smaller sample — they are a
  measurement of an absent UE.** M18 p95 is `None`, and M19/M21 read
  **0.0 ms**, i.e. *instant recovery*, for a robot that never came back.
- **§34.2's "unexplained" neighbour Δp98 acquires a candidate**: −8.995 ms
  [−14.234, −3.085] is computed over a run in which the joiner's 4 Mbps
  video left the cell for 86 % of the horizon. That is a **lead, not a
  resolution** — §34.2's own correlation test against joiner absence
  returned r = −0.028 and is not overturned by this.
- **The strengthened assertion is still not strong enough.** It checks
  event **count**; an arm can record its full scheduled count and complete
  none. It should assert `n_never_completed == 0` alongside — M18 already
  computes it.

**The transferable lesson is one level up from the one §34.5 drew.** That
section concluded "a slow arm against a fixed period loses events" and
proposed a scenario fix. The truth is that **an arm can register events and
complete none of them**, and every count-based guard — including the one
this campaign added in response — passes on that. *Firing* and *finishing*
are different questions, and a campaign that asserts only the first will
report instant recovery for a UE that never returned.

---

## 35. G12 — ordered degradation under overload (plan, registered before any code)

§22.5 closed F4 as **UNSCOREABLE** and named the fix as *"a workload with
≥ 2 GBR classes — scenario work, not analysis"*. That is right, and this
section is that scenario work. It is planned before any code, and the
§33.3 pre-flight below was **run** rather than assumed — which is how a
confound large enough to invalidate the whole statistic was found before
any expectation was registered.

### 35.1 What G12 asks — and its four clauses use FOUR DIFFERENT currencies

`docs/IA_P5G_Factory_Guarantee_Test_Plan.md:106` and GT-7.3 (line 318):

> First-violation order under a load ramp is exactly: **5QI 9 → 5QI 4
> (lidar) → 5QI 2 (camera) → *never* 5QI 1** (telemetry/commands) while any
> lower class still has throughput. […] any inversion (e.g. **telemetry
> gap** grows while bg still **moves bytes**) is a FAIL regardless of
> absolute numbers.

Read one clause at a time, in G9's manner, because a single verdict would
again average four different epistemic situations — and here the four
clauses are not even measured in the same units:

| # | clause | the guarantee's own word | currency | instrument |
|---|---|---|---|---|
| 1 | 5QI 9 first | **"exhausted"** | throughput → 0 | study-layer; 5QI 9 is non-GBR (GFBR 0), so it has **no contract to breach** |
| 2 | then 5QI 4 | **"degrades"** | GBR contract | **M13**, unchanged |
| 3 | then 5QI 2 | **"degrades"** | GBR contract | **M13**, unchanged |
| 4 | never 5QI 1 | **"intact"**, inversion = *"telemetry **gap** grows"* | liveness gap / PDB | **M20** (`protected_fleet_liveness_gap`) + M02, **not** a GBR contract |

**This is the load-bearing observation of the whole item.** The middle pair
is exactly the pair that has a GBR contract, and exactly the pair M13
orders. **Clauses 1 and 4 are not M13's job by the guarantee's own
wording** — "exhausted" and "gap" are not contract language, and GT-7.3's
own worked example of a FAIL is phrased in gaps and bytes, not in GFBR.

### 35.2 M13 is usable UNCHANGED — and the reason is structural, not a concession

§22.5 rejected widening M13 to the Delay-class flows as redefining a
pre-registered metric until it separates something. **That rejection stands
and this plan does not reopen it.** Confirmed against the code rather than
from the section text: `sim/scorecard.py:1083`'s `first_violation_order`
reads `rec.flows_by(flow_class="GBR")` and `meets_gbr_contract(fraction)`
only, and returns `{order_5qi, first_fail_at_index}`. Nothing it needs is
missing; what was missing was a second GBR class in the input.

**And §35.1 shows the restriction is not a limitation.** M13 covers clauses
2 and 3 completely. Clauses 1 and 4 were never contract statistics in the
guarantee's own text, so supplying them from M20/M02/throughput is
*reading the guarantee correctly*, not routing around a metric.

**A rejected alternative, recorded because it is the tempting one.**
Convert `sim/fleet.py`'s 5QI 1 telemetry flow from `flow_class="Delay"` to
`"GBR"` so M13 sees all four classes. Rejected: it is the same error shape
as widening M13 one level down — changing the *input's* class until the
instrument reads it, rather than changing the instrument. It also fails on
its own terms, measured in §35.4(c).

### 35.3 The inventory, taken first — and it corrects §22.5's scan

Per §21.2's discipline: measure what is on disk before designing a grid.

**§22.5's measurement was over stages 1 and 4 only, and it is accurate for
those.** Re-measured here across all three fleet stages:

| stage | records | GBR 5QI classes present |
|---|---|---|
| stage 1 | 1,770 | `[2]` |
| stage 4 | 1,440 | `[2]` (90 records carry no GBR flow at all) |
| **stage 5** | **1,440** | **`[2, 4]` on 840 records, across 28 cells** |

**So a two-GBR-class workload already exists on disk and F4 did not scan
it.** The regime map's G12 row says G12 "needs a workload with ≥ 2 GBR
classes"; that is true as far as it goes and **too weak** — the classes are
there, in stage 5's lidar excursion, and they are still unusable, for a
different and more specific reason:

**Stage 5's 5QI 4 has NO DYNAMIC RANGE, by construction.** Across all 1,110
lidar flow-records its `gfbr_fraction` is `min 0.0329, median 0.4000,
max 0.4000`, and **0 of 1,110 meet the 0.95 contract**. The cap is
arithmetic, not scheduling: `LidarActivation` is active `duration_s=2.0` of
a `5.0 s` horizon, `throughput_bps` averages over the **whole** run, so the
fraction cannot exceed `2.0 / 5.0 = 0.4000` — which is exactly the observed
maximum. **5QI 4 fails at every load, including ramp index 0, on every
arm.** It would enter every ordering first, always, as a property of the
duty cycle rather than of the scheduler.

**This is the §33.3 shape one level over: not a floored delta, a floored
ORDER.** And stage 5 could not have been used regardless — its axes are
`composition / lidar_ues / n_ues` with **no load-ramp axis at all**, so
`report_g12` would raise on it, correctly.

**What `sim/fleet.py` already carries, per profile** (read from the module,
not assumed):

| G12 class | present? | as what | usable for G12 as-is? |
|---|---|---|---|
| **5QI 9** | yes — DRONE 1 Hz heartbeat (512 bps), UGV logs (500 kbps poisson), SENSOR DL config (2 kbps) | `PF`, GFBR 0 | **no** — nothing saturating; the guarantee's bg is *"0 GFBR / 100 Mbps MFBR / saturating"* |
| **5QI 4** | yes — UGV lidar | `GBR`, GFBR 12 Mbps, **duty-cycled off by default** | **yes, via existing parameters** — see §35.5 |
| **5QI 2** | yes — DRONE/UGV/CAMERA `xr_video` | `GBR`, GFBR 4–6 Mbps | **yes, unchanged** |
| **5QI 1** | yes — DRONE MAVLink telemetry | `Delay`, GFBR 0 | **yes, unchanged** — clause 4 is a gap statistic (§35.1) |

**So exactly one flow has to be added: a saturating 5QI 9.** Neither
`sim/parametric.py`'s `bg` aggressor nor `sim/scenarios/g9.py`'s
`QFI_AGGRESSOR` can be reused — both are **5QI 8**, and G12 names 5QI 9
specifically. Both 8 and 9 are in `Scorecard.NON_PROTECTED_5QI`, so the
substitution is invisible to every protected-fleet statistic and would have
gone unnoticed.

### 35.4 The §33.3 pre-flight — RUN, not assumed

The journal's third form rule requires checking the instrument has dynamic
range **in the control** before registering anything. Applied to an *order*
rather than a delta, the question becomes: **at the bottom of the ramp does
every class MEET its contract, and at the top do several fail?** A class
pinned at "fails" (stage 5's lidar) or pinned at "meets" cannot enter an
ordering.

Throwaway probe: `mixed`, N=8, one seed, horizon 20,000, `cqi_delay_slots=8`,
a saturating 50 Mbps 5QI 9 bg, and a committed-load multiplier scaling both
GBR classes' offered rate **and** their GFBR together — the sim analogue of
GT-7.3's *"ramp aggregate offered load … to 145 % of the measured ceiling"*.

**(a) The control is CLEAN on all three arms.** At ×1.0 every GBR class
meets on PF, Reservation and TwoTier (5QI 2 `5/5`, 5QI 4 `2/2`), at
UL utilisation 0.897–0.925 and 5QI 9 carrying 31.3–36.3 Mbps. Nothing is
pre-broken, so the ordering starts empty and has somewhere to go.

**(b) The ramp moves the statistic, and 5QI 9 degrades FIRST.** PF, one
seed: bg throughput falls **35.8 → 22.8 → 13.9 → 11.8 Mbps** across
×1.0/×1.5/×2.0/×3.0 while both GBR classes are still meeting at ×1.5 — so
clause 1's "best-effort gives way first" is observable *before* any
contract breaks, which is the whole ordering claim.

**(c) The test plan's OWN provisioning makes clause 4 unscoreable, and the
document already half-caught it.** §2.1's table gives telemetry (5QI 1)
`GFBR 0.5 Mbps` against `offered ≈ 24 kbps`. Converting 5QI 1 to GBR at that
GFBR scores **0 of 2 flows meeting, `gfbr_fraction = 0.045`, at ramp index
0** — 5QI 1 would lead every ordering and G12 would read as a maximal FAIL
on an untouched telemetry stream. `meets_gbr_contract` is
`delivered / GFBR`, so a flow provisioned ~21× above what it offers (against
the test plan's own 24 kbps) can never meet it. **§2.1 raises exactly this arithmetic in its own prose** — *"a
heartbeat with a 5 Mbps GFBR is never meaningfully 'within GFBR'"* — and
then fixes 5 Mbps to 0.5 Mbps, which is still ~21× the offered rate. The
flag was right and the correction was insufficient. This is the measured
half of §35.2's rejected alternative.

### 35.5 THE FINDING — flow DECLARATION ORDER sets the first-violation order

**Found by two probe builds disagreeing, not by design**, and recorded that
way. Probe 1 appended its 5QI 4 flows to the end of `ScenarioConfig.flows`;
probe 2 obtained them from `build_fleet`, which emits them first within each
UE. **The two disagree about whether 5QI 4 ever violates at all** — which is
clause 2, the centre of the guarantee.

Isolated by varying one thing at a time from probe 2's build, everything
else byte-identical (`mixed`, N=8, seed 12345):

| variant | PF ×2.0 | PF ×3.0 | TwoTier ×3.0 |
|---|---|---|---|
| `build_fleet` order | 5QI4 **2/2** met (min 1.000) | 5QI4 **2/2** (min 1.000) | 5QI4 **2/2** (min 0.966) |
| **lidar declared last** | 5QI4 **0/2** (min 0.771) | 5QI4 **0/2** (min **0.005**) | 5QI4 **0/2** (min 0.142) |
| 5QI 1 as GBR | no material change | no material change | no material change |
| drop `active_*_s` params | **identical** | **identical** | **identical** |

**Declaration order is the entire cause; the other two candidates change
nothing.** And it is a broad sensitivity, not a knife-edge — five random
permutations of the same flow list at PF ×2.0 give 5QI 4 `1/2 min 0.822`,
`1/2 min 0.832`, `1/2 min 0.941`, `1/2 min 0.765`, `2/2 min 1.000` against
`build_fleet`'s own `2/2 min 1.000`; at
TwoTier ×2.0 two permutations drive a 5QI 2 flow to **min 0.021** and
**min 0.000** — a bearer delivering nothing — where `build_fleet`'s own
order gives `5/5 met, min 0.953`.

**Why this matters more than any other item here: the first-violation order
between 5QI 4 and 5QI 2 — the exact pair M13 orders and the exact pair G12
is about — INVERTS on the order flows happen to appear in a list.** That is
a scenario-authoring detail with no physical referent. An order read off one
declaration order is not a scheduler property until this is controlled.

**And the direction is the sharp part, not just the magnitude.** Under
`build_fleet`'s own order — the canonical one, the one every WP9 fleet stage
ran — **5QI 4 never breaches at all through ×3.0 on any of the three arms**
(min 0.966–1.000) while **5QI 2 collapses** (PF min 0.121). Under the
permuted order the result conforms to the guarantee instead: 5QI 4 breaches
first. So the canonical order does not merely give a *different* order, it
gives **G12's own inversion** — and `scheduler/flow.py`'s standardised
`FIVE_QI_PRIORITY` puts 5QI 2 at **40** and 5QI 4 at **50**, i.e. 5QI 2 is
the *higher*-priority class, which is what the guarantee's `4 → 2` sequence
encodes. **Whether any arm actually consumes that priority value is part of
what the trace must establish**, and is deliberately not asserted here.

**A consequence that lands directly on E2.** Stage 5's lidar was pinned at
*"fails"* (§35.3). Under the canonical order this workload's lidar looks
pinned at *"meets"* — **the same §33.3 defect mirrored**, and equally fatal
to an ordering. So the ramp's top level is not a free choice: **the grid is
not launched until a probe cell shows 5QI 4 breaching under the CANONICAL
order**, and if no feasible load does so, that is itself the result and is
reported as one rather than fixed by adopting whichever permutation
cooperates. Choosing the permutation that produces the expected answer would
be the multiplicity-guard violation §22.5 refused, moved from the metric to
the scenario.

**The mechanism is NOT identified and is not guessed at.** Three candidates
exist in this repo's own recorded behaviour and the trace must distinguish
them, not assume: `sim/baselines/pf.py`'s declaration-order tie-break
(README §8); per-UE flow iteration order in the LCP fill; and
`sim/harq.py::HarqProcessPool._pools`' shared insertion-ordered iteration,
which CLAUDE.md already records as able to move outcomes for an *unrelated*
UE. Recorded as **unexplained** pending that trace, per §34.2's precedent —
an invented mechanism is not a finding.

### 35.6 Decisions

**D1 — the ramp is a committed-load multiplier, not `video_tier` and not
`n_ues`.** `video_tier` scales only `xr_video`, i.e. only 5QI 2, which
biases the very ordering under test toward 5QI 2 failing first. `n_ues`
changes class populations lumpily through `_allocate`'s largest-remainder
step. The multiplier scales **both** GBR classes' offered rate and GFBR
together, at fixed fleet — GT-7.3's *"both assets nominal; ramp aggregate
offered load"*.

**D2 — no `sim/fleet.py` change is needed, and this was verified rather
than hoped.** `build_fleet(n, comp, lidar=LidarActivation(n_ues=2,
start_s=0.0, duration_s=horizon_s, rate_bps=3e6*m, synchronised=True),
video_tier=m)` already produces a **continuous** 5QI 4 at the test plan's
3 Mbps with GFBR tracking it, plus 5QI 2 scaled identically. Only the
saturating 5QI 9 is appended by the scenario module. `LIDAR_MAX_CONCURRENT`
is respected, not bypassed.

**D3 — a continuous lidar is a different device claim from stage 5's, and
does not contradict `sim/fleet.py`'s comment.** That module argues a
duty-cycled lidar must not be modelled as *"a permanently-downscaled
continuous feed"* — an argument about **stage 5's transient excursion**,
whose point was to stress a transient. GT-7.3's T4 is *"lidar / **second
feed**"*, provisioned at *"3 Mbps mean, 10 Hz sweeps"*: a stream, not an
event. Both models are in the test plan; they belong to different tests.
Stated as a decision so a later reader does not read it as an oversight.

**D4 — declaration order becomes a REGISTERED CONTROL, not a silent
choice.** Canonical order is `build_fleet`'s own, because it is the order
every other WP9 fleet stage ran. The campaign additionally runs *k* seeded
permutations at one cell. **If the M13 order flips under permutation, G12's
result is not a scheduler property and the write-up says so** — that is the
control's whole purpose, and it is registered before any number exists.

**D5 — `record_timeseries` stays `True`.** M13 needs only
`throughput_bps`/`gfbr_bps`, but clause 4's M20/M02 companions and §1's
standing guard both want it, and turning it off to save disk is exactly the
kind of quiet divergence from every other stage that makes a cross-stage
comparison unreadable later.

### 35.7 Degenerate cases, pre-registered as ASSERTIONS rather than discoveries

Given this WP's record, each is asserted by the runner before any number is
reported — a failure raises, it does not score.

1. **One-element order.** `len(order_5qi) < 2` at the top of the ramp is
   **not an ordering** and is F4's own result recurring. Assert ≥ 2 GBR
   classes are present *and* that the number that ever violate is ≥ 2.
2. **A class that violates at ramp index 0.** `first_fail_at_index[qi] == 0`
   means the class was already broken in the control (stage 5's lidar,
   §35.4(c)'s telemetry) — the order is measuring provisioning, not load.
   Assert the ramp's bottom cell has an **empty** `first_fail_at`.
3. **A class that never violates.** Silently absent from `order_5qi`, which
   reads identically to "protected". Print the per-class terminal
   `gfbr_fraction` at the top of the ramp beside the order, always, so
   "never failed" and "never present" cannot be confused.
4. **An empty selection.** `report_g12` already raises when the ramp axis
   matches no record (§21.3's coercion rules); the G12 runner reuses it
   rather than re-deriving it, and asserts `len(cell) == n_arms × n_seeds`.
5. **A tie.** `first_violation_order` sorts by `first_fail_at` index, and
   Python's sort is stable — two classes first failing at the **same** ramp
   index therefore emit in dict-insertion order, which is silently the
   flow-iteration order §35.5 has just shown to be an artefact. **Ties are
   detected and reported as ties**, never as an order.

### 35.8 The expected-count assertion, in its strengthened form, applied to violations

c2a9f13 strengthened G9's guard from *"did the mechanism fire at all"* to
*"did it fire as often as the schedule specifies"*, because the gap between
those is where a **partially** degenerate run hides. The analogue here is
not events but **violations**, and it has the same two levels:

- **Weak (rejected as sufficient):** ≥ 1 class violated somewhere.
- **Registered:** per (arm, cell), assert the **number of ramp points** is
  the grid's own `len(RAMP)` — derived, never restated — and assert the
  **number of GBR flow-records per class per ramp point** equals what
  `build_fleet` produced for that composition and N, computed from the
  built scenario at run time.

**And the self-selection warning transfers directly.** If one arm's ramp
contributes fewer flow-records than another's, the survivors are not a
smaller sample of the same population — G9's exact lesson — and the arms are
not comparable. That check runs before the order is computed.

### 35.9 Pre-registered expectations

**Registered in the journal's required form: what the data will LOOK like,
and what each look would MEAN. No mechanism is predicted.**

**A disclosure that has to come first, because it affects how these should
be read.** §33.3's dynamic-range check is *not* information-neutral for an
order statistic the way it is for a delta. Asking *"does M02 move in the
control"* tells you nothing about the treatment effect; asking *"do these
classes violate across the ramp"* **is a one-seed draw of the answer**. The
pre-flight therefore leaked part of G12's result, and E1–E3 below are
**pilot-informed, not blind**. They are still falsifiable — at 10 seeds ×
3 arms × the full ramp, against a one-seed, one-composition pilot — but a
later reader must not score them as blind predictions. **This tension
between two of the project's own rules is itself new and is recorded rather
than resolved silently.**

| # | expectation | what each outcome would mean |
|---|---|---|
| **E1** | **The bottom of the ramp is clean on all three arms at every composition** — `first_fail_at` empty, so the order starts from nothing. | Any class violating at index 0 means the workload is mis-provisioned rather than overloaded, and the ramp measures provisioning (§35.7 case 2). **This is the control and it is read FIRST**; a failure is a stop condition, not a result. |
| **E2** | **`order_5qi` is a TWO-element list on every arm** — both 5QI 4 and 5QI 2 violate somewhere in the ramp, under the CANONICAL declaration order. | One element ⇒ F4's result recurring one level down: the second class is pinned, and the item returns to being about the workload, not the schedulers. **The pilot argues against E2 at ×3.0** (5QI 4 unbroken on all three arms), so either the ramp must reach further or E2 loses — and §35.5's stop condition, not a change of permutation, is what settles which. |
| **E3** | **Clause 4 holds: 5QI 1 shows no liveness-gap or PDB degradation at any ramp point where 5QI 9 still moves bytes.** The pilot's 5QI 9 stays above zero at every ramp point on every arm (PF floors at 11.8 Mbps; Reservation reaches 0.019 and TwoTier 0.755 Mbps at ×3.0), so the conjunction's left side is true throughout — which makes clause 4 maximally exposed rather than vacuous. **Those arms differ by three orders of magnitude, so the left side is evaluated per arm, never pooled.** | A 5QI 1 degradation while bg still moves bytes is GT-7.3's own worked example of a FAIL and would be the strongest negative result this item can produce. |
| **E4** | **Clause 1 is NOT literally satisfied: a GBR class will breach its contract while 5QI 9 is still moving multiple Mbps** — "exhausted" as a strict precondition will not hold, though 5QI 9 degrades first and furthest. In the pilot 5QI 2 breaches at PF ×2.0 with bg still carrying 13.9 Mbps. | Strict exhaustion before any GBR breach would mean the schedulers enforce a harder class boundary than any of them claims to, and would make GT-7.3's ordering literally rather than approximately true. |
| **E5** *(most-likely-wrong)* | **The M13 order is the SAME across arms**, and varies across compositions more than across arms — F4's original wording, re-registered because it was never actually tested. | An **arm-dependent** order is the genuine scheduler-differentiating result and the strongest positive thing G12 can produce. The pilot already hints against E5 (Reservation put a 5QI 1 flow at 0.700 at ×3.0 where TwoTier held ≥ 0.980), which is precisely why it takes the most-likely-wrong slot. |

**E5 carries the standing trace obligation, and §35.5 has already fixed
what the trace must rule out first.** If the order differs across arms, the
first question is **not** which scheduler is safer — it is whether the
difference survives D4's permutation control. A per-arm order difference
that disappears under a re-ordered flow list is the declaration-order
artefact wearing a scheduler result, and this WP has published that shape of
error before. Only a difference that **persists across permutations** gets a
mechanism trace, and that trace is worktree-instrumented and direct-cause,
per CLAUDE.md's cross-direction invariants.

### 35.10 Budget

**Timed, not scaled** — §6.3a's rule. Measured in the pre-flight at
`mixed`/N=8/horizon 20,000, **without** scoring or `record_timeseries`:
PF ≈ 2.4 s, Reservation ≈ 3.3 s, TwoTier ≈ 9.0 s per run, ≈ 14.7 s per
(3 arms × 1 ramp point × 1 seed).

**That figure is a floor and is deliberately not the budget.** §6.3a's own
measured 303 s per 3-arm × 10-seed N=8 cell includes `record_timeseries=True`
and the full scorecard pass, which D5 keeps. **One probe cell is timed
end-to-end with its real post-processing before the full grid launches** —
the rule that table exists to enforce, and the one §21.7 also bound itself
to.

### 35.11 Commit sequence

1. **This section.** Docs only.
2. **`sim/scenarios/g12.py`** — the GT-7.3 ramp workload built on
   `sim/fleet.py`'s profiles per D2 (no `fleet.py` change), plus the
   saturating 5QI 9, plus its tests: that the ramp scales both GBR classes'
   GFBR together, that 5QI 4 is continuous over the horizon, that the bg is
   5QI 9 and not 8, and that `LIDAR_MAX_CONCURRENT` still binds.
   **§35.7's assertions land here, with the runner refusing to report.**
   **The ramp's top level is fixed by §35.5's stop-condition probe in this
   commit** — under the canonical order, not a permuted one — and the
   measured level is recorded, never chosen to produce an outcome.
3. **The campaign runner + analyser**, reusing `report_g12`'s coercion and
   empty-selection guards rather than re-deriving them; §35.8's
   expected-count assertion; D4's permutation control.
4. **The run. E1–E5 scored, hits and misses both.**
5. **`docs/wp9-regime-map.md`'s G12 row rewritten from results** — and its
   current *"needs a workload with ≥ 2 GBR classes"* corrected on both
   sides: the classes already exist on disk in stage 5 (§35.3), and what
   they lack is **dynamic range**, which is a stricter and more useful
   requirement to hand a reader than a class count.
6. **End-of-item judgment-calls review.**

Full suite + `--check` after each. **`--check` is predicted CLEAN
throughout**: every commit is a new scenario module, a script and docs, and
no corpus scenario builds a fleet. If it moves, `sim/fleet.py` is less
inert than D2 claims, and that is a finding about D2.

### 35.12 Commit 2 — the stop-condition probe RAN, and where 5QI 4 breaches is the finding

`scripts/g12_ramp_probe.py`, `mixed`/N=8/seed 12345/horizon 20,000, **canonical
declaration order, no permutation**, one seed — this fixes a grid parameter,
it scores nothing.

**§35.5's stop condition does NOT fire.** 5QI 4 breaches its contract on every
arm: **PF ×4.0, Reservation ×6.0, TwoTier ×4.0**. So `RAMP` can be set and
`order_5qi` can have two elements.

**But where it breaches is outside the guarantee's own ramp, and that is the
result this probe actually produced.** GT-7.3 specifies *"+10 % steps of the
measured ceiling … to 145 %"*. Measured ceiling (UL delivered when the cell is
already saturated, at the ramp's bottom): **63.4 Mbps**, against **28.0 Mbps**
committed at ×1.0.

| mult | committed | % of ceiling | 5QI 2 (worst flow) | 5QI 4 (worst flow) | 5QI 9 |
|---|---|---|---|---|---|
| ×1.0 | 28.0 | 44 % | 5/5 met, 0.953 | 2/2 met, 1.000 | 35.8 Mbps |
| ×2.0 | 56.0 | 88 % | 3/5, 0.780 | 2/2, 1.000 | 13.9 |
| ×3.0 | 84.0 | 132 % | 0/5, 0.121 | **2/2, 1.000** | 11.8 |
| **×3.3** | **92.4** | **146 %** | — | — | *GT-7.3's own top* |
| ×4.0 | 112.0 | 177 % | 0/5, 0.000 | **0/2, 0.869** | 11.8 |
| ×6.0 | 168.0 | 265 % | 0/5, 0.000 | 0/2, 0.580 | 11.8 |

(PF shown; Reservation and TwoTier are in the probe's own output. Reservation
holds 5QI 4 at `2/2, 0.997` as far as ×4.0 and breaks at ×6.0.)

**Within GT-7.3's own ramp only 5QI 2 breaches, on all three arms — so the
order there is a ONE-ELEMENT list.** That is F4's result recurring, but for a
newly *measured* reason rather than a workload-census one, and it is a
materially different statement: F4 said the data had nothing to order; this
says the guarantee's own load range does not overload the class the guarantee
says fails first.

**And the two-element order, once the ramp is extended, is `[2, 4]` — 5QI 2
before 5QI 4, which is G12's own inversion**, on every arm, under the
canonical order. §35.5 has already shown the permuted order gives the
conforming answer instead. **So the declaration-order confound is not a side
issue for this guarantee; it decides the verdict**, and D4's control stops
being a hygiene measure and becomes the load-bearing experiment.

**On the legitimacy of extending the ramp.** Extending until a class breaches
is the procedure §35.5 registered in advance — *"if no feasible load does so,
that is itself the result"* — so the extension is not a result being bought.
What would have been illegitimate is picking the **declaration order** that
produces a breach, and that is not done: every number above is canonical
order. The ramp therefore spans the guarantee's range **and** extends past it,
`GUARANTEE_RAMP_TOP_MULT = 3.3` marks the boundary in code, and the analyser
reports the two regions separately rather than averaging across them.
**Reporting the beyond-145 % ordering as if it were the guarantee's own would
be the error that constant exists to prevent.**

**What commit 2 landed:** `sim/scenarios/g12.py` (no `sim/fleet.py` change —
D2 verified, `build_fleet`'s existing parameters carry the whole ramp),
`scripts/g12_ramp_probe.py`, and 26 tests. §35.7's five degeneracy guards are
executable (`assert_cell_is_scoreable`, `assert_ramp_bottom_clean`,
`assert_order_non_degenerate`), and `permute_flows` makes D4 a first-class
control rather than an ad-hoc reshuffle.

**A cell-exclusion fact worth having in advance:** `sensor_dense` allocates
3 % UGVs, so at N=4 and N=8 it carries **no 5QI 4 flow at all** and cannot
produce an ordering. `assert_cell_is_scoreable` refuses it by name rather than
scoring it to a one-element "order" — the same 28-of-48 pattern stage 5's own
census shows.

### 35.13 How G12's row must READ — registered before the campaign runs

The campaign produces two orderings from one grid, and they are **not two
views of one result**. One is a statement about the test specification; the
other is not yet a statement about anything. Fixing the reporting structure
now, before the numbers exist, is what stops the more dramatic of the two
from becoming the headline by default.

#### Region 1 — inside GT-7.3's own ramp. THE PRIMARY FINDING, stated first.

**Within the guarantee's own load range — "+10 % steps of the measured
ceiling … to 145 %" — only one GBR class breaches, so G12's specified
degradation order cannot be observed at the load G12 specifies.** The
ordering is a one-element list on every arm.

**This is a specification finding, and it is the more useful of the two**,
because it says the test as written cannot produce the evidence it asks for.
A reader who acts on it changes GT-7.3 or accepts that G12 is not testable
as specified; no scheduler work follows from it at all.

**It is NOT F4's result, and the two must never be merged.** They share a
symptom and nothing else:

| | **F4 (§22.5)** | **§35.12, this campaign** |
|---|---|---|
| symptom | one-element `order_5qi` | one-element `order_5qi` |
| **cause** | the workload carried **one** GBR class — literally nothing to order | the workload carries **two**, both present at every ramp point, and the **guarantee's own load range does not overload the class it names as failing first** |
| what it is a claim about | the **data on disk** | the **test specification** |
| **fix** | build a workload with ≥ 2 GBR classes — **done, commit 2** | raise GT-7.3's ramp top, or accept G12 is not testable as written |
| **who acts on it** | whoever builds the next sweep | whoever owns the test plan and signs the Guarantee Sheet |

**The "different fix / different owner" row is the reason for the
distinction.** Writing this up as "G12 is still unscoreable" would hand a
reader F4's fix — build a better workload — which has already been done and
would not help.

#### Region 2 — beyond 145 %. Its own header, and never without the control.

Extending past the guarantee's ramp does produce a two-element order:
**`[2, 4]` under the canonical declaration order — 5QI 2 before 5QI 4, which
is G12's own inversion — on every arm.**

**This must not be reported without the permutation result beside it, in the
same table.** §35.5 measured the same workload under a permuted flow list
giving the *conforming* order instead. **On its own the inversion reads as a
scheduler finding and it is not established as one.** The registered wording
is that the Region-2 verdict is **not established as a scheduler property and
is consistent with a declaration-order artefact** — a NON-establishment, not a
positive causal claim (this site still carried the hardened form *"is
currently a property of declaration order"* until 2026-09-03, the same
overclaim `38248f9` corrected elsewhere) — and the regime map's G12 row
carries that qualifier inline — the same
discipline as M19's standing caveat and §34.5's bias note, both of which
exist because a number without its qualifier travels further than the
qualifier does.

#### What would make the inversion a REAL finding — named now, not after

E5's most-likely-wrong slot is only honest if the bar for promoting the
inversion is fixed before the data arrives. **Exactly two things would do
it, and neither is "the effect was large".**

1. **An arm difference that SURVIVES permutation.** Not "the arms differ
   under the canonical order" — that is what a position artefact looks
   like. The criterion is that the arms' order distributions differ **in
   the same direction under every permutation tested**, canonical included.
   A difference present under canonical and absent under any permutation is
   the artefact, reported as such.
2. **A mechanism traced to something OTHER than list position.** And this
   clause has a sharp edge worth stating in advance: **all three candidate
   mechanisms §35.5 named are position-dependent** — `pf.py`'s
   declaration-order tie-break, per-UE LCP iteration order, and
   `HarqProcessPool._pools`' insertion-ordered iteration. **Tracing the
   effect to any of them CONFIRMS the artefact; it does not refute it.**
   Promotion needs a position-*independent* mechanism — priority actually
   being consumed, GBR deficit accounting, something that would produce the
   same ordering from any flow list.

**If neither fires, the registered conclusion is already written:** the
Region-2 ordering is *not established as a scheduler property and is
consistent with a declaration-order artefact*, and G12's row says exactly
that rather than reporting an inversion. **That sentence is committed to
here so it cannot be softened later**, when a striking result is in hand and
the temptation runs the other way.

**And a limit on the control itself, so it is not over-read.** Four
permutations at one cell can say *whether* the order is stable under
reordering. They **cannot** characterise a distribution over permutations,
and no claim of that shape may be made from them — the two-level-axis rule
in the journal, applied to a factor whose levels are permutations.

### 35.14 Commit 3 — the campaign runner, and two things the smoke run found

**Built:** `scripts/g12_campaign.py` — the ramp runner, the three
pre-report assertions, D4's permutation control, and a report structured as
§35.13 requires (Region 1 first, Region 2 only beside the control). Cell
selection is **derived**: `scoreable_cells()` builds each candidate and asks
`assert_cell_is_scoreable`, printing exclusions with their reason —
`sensor_dense` N=8 is excluded automatically, `GBR classes [4] absent
(census {2: 1})`, because 3 % UGVs rounds to none.

**§6.3a's timed cell, measured with the real post-processing** (`--time-cell`,
`record_timeseries=True`, full scorecard): **128 s for 3 arms × 1 seed × 8
ramp points = 5.4 s/run.** Main grid 21 min/cell × 3 scoreable cells = 64 min;
D4 control 480 runs = 43 min; **107 min serial** for commit 4.

**Two things the smoke run found, both by a guard firing.**

**1. A permutation can break the CONTROL, not just the ordering.** On
TwoTier, two of four permutations put 5QI 2 in breach **at ramp index 0** —
at ×1.0, nominal load, before any overload at all — and
`assert_ramp_bottom_clean` refused them. This is stronger than §35.5's
result, which was about which class breaches *under load*; here reordering
the flow list alone breaks a bearer in the condition the whole ramp is
measured against.

**It is one seed and is reported as one** — commit 4 quantifies it over the
real seed set. But it sharpens §35.13's promotion bar rather than blurring
it: a permutation that cannot even produce a clean control cannot contribute
an ordering, so **the count of unscoreable permutations is itself part of
the control's answer** and is printed beside the orders.

**And it required a design decision, made explicitly rather than by
`try`/`except`.** In the main grid a dirty ramp bottom is E1's stop
condition — the workload is mis-provisioned and nothing computed from it is
interpretable. In the permutation arm the identical failure is *the
measurement*. So there are two named entry points, `order_for` (raising) and
`order_for_permutation` (recording), for the same reason `allow_one_element`
is a named parameter and not a caught exception: **a swallowed assertion and
an honoured one must not look alike to a later reader.**

**2. An EMPTY order, not just a one-element one.** On one smoke seed nothing
breached anywhere in range, on two arms — `order_5qi == []`. That is the
same in-range finding *more so*, and it is why `allow_one_element` permits
fewer-than-two rather than exactly-one. It also makes the reporting choice
load-bearing: the order distribution prints `[2]×1  []×1` rather than a
single pooled order, so "one class breached" and "nothing breached" stay
distinguishable. Pooling them would have been the empty-selection signature
one more time.

**A pre-result the campaign must not be allowed to inherit uncritically.**
Smoke already shows PF's permuted orders splitting **`[2,4]` on three
permutations and `[4,2]` on the fourth** — the order flipping under
reordering alone, at one seed. §35.13's bar is unchanged by it: that is what
an artefact looks like, and promotion still requires an arm difference
surviving *every* permutation or a position-independent mechanism.

## 36. G12 campaign — E1–E5 scored, and clause 4 fails inside the guarantee's own ramp

`scripts/g12_campaign.py` → `sweeps/wp9/g12_campaign.json`; scored by
`scripts/g12_score.py` → `sweeps/wp9/g12_score.log`. Reproduce with
`uv run python scripts/g12_score.py sweeps/wp9/g12_campaign.json`.

### 36.0 E1's control fired on real data, and it cost two of three cells

§35.9 registered E1 as a stop condition, and **it stopped the first launch**
at `ugv_heavy/PF/seed579362555` — 5QI 2 breaching at ramp index 0, ×1.0,
nominal load, **canonical declaration order, no permutation**. The response
was a cell-level control pass, not a relaxed guard:

| cell | contaminated at ×1.0 | pattern |
|---|---|---|
| `mixed_n8` | **0/30** | clean |
| `ugv_heavy_n8` | **3/30** | all three arms, the *same* seed, 5QI 2 ≈ 0.947 |
| `drone_heavy_n8` | **9/30** | **TwoTier-dominated**, 5QI 2 down to **0.7505** |

**5QI 4 is at 1.000 in every contaminated group** — it is always the camera
that is marginal at nominal load, never the lidar.

**The unit of exclusion is the CELL, and that choice is the load-bearing
one.** Dropping only the failing seeds would leave the survivors
**self-selected** — G9's partially-degenerate-run trap, where the surviving
events were the fastest ones and the arms stopped being comparable. So a
contaminated cell goes whole. **E1: MISS**, 12/90 groups, and the ordering
analysis rests on **one** cell rather than three. That is a real loss of
scope and is stated as one.

### 36.1 The permutation control, read FIRST (§35.13)

| arm | unscoreable permuted runs | orders across permutations |
|---|---|---|
| PF | 0/20 | `[2,4]`×15, `[4,2]`×5 — **2 distinct** |
| Reservation | 0/20 | `[2,4]`×12, `[4,2]`×8 — **2 distinct** |
| TwoTier | **7/20** | `[2,4]`×13 |

**PF's split is clean and total: permutations 101/102/103 give `[2,4]` on all
5 seeds each, permutation 104 gives `[4,2]` on all 5.** The order is a
deterministic function of the flow list's order, not a noisy one — which is
worse for the ordering's status as a result, not better.

**And 7 of TwoTier's 20 permuted runs cannot produce a clean ramp bottom at
all**, at ×1.0. Reordering the flow list alone breaks a bearer in the control
condition.

### 36.2 Region 1 — inside GT-7.3's own ramp. THE PRIMARY FINDING, and it is worse than "unobservable"

**The ordering cannot be observed**: 3 of 30 groups produce a ≥2-element
order at or below 145 % of ceiling (all three from TwoTier; PF and
Reservation give `[2]` on all 10 seeds each). So G12's specified degradation
order is not visible at the load G12 specifies — the specification finding
§35.13 registered, and **not** F4's: F4's cause was one GBR class on disk,
fixed by building a workload (done); this one is fixed by changing GT-7.3's
ramp or accepting G12 is not testable as written. Different cause, different
fix, **different owner**.

**But the campaign found something the ordering was never going to show, and
it is the headline: clause 4 — "never 5QI 1 while any lower class still has
throughput" — FAILS, on every arm, inside the guarantee's own ramp.**

| arm | worst telemetry M02 | seeds degraded | earliest degradation |
|---|---|---|---|
| PF | 1.000 | 10/10 | ×2.3 (**102 % of ceiling**) |
| Reservation | 1.000 | 10/10 | ×2.3 (**102 %**) |
| **TwoTier** | **1.000** | **10/10** | **×1.0 — NOMINAL LOAD** |

`telemetry_m02 = 1.0` means **every resolved telemetry byte was
PDB-violated**, while 5QI 9 was still carrying **11.6 Mbps**. That is
GT-7.3's own worked example of a FAIL — *"telemetry gap grows while bg still
moves bytes"* — realised exactly.

**TwoTier's is the striking number: 9 of 10 seeds show telemetry degradation
at ×1.0**, M02 0.009–0.068, rising to **0.92–0.98 by ×1.6**. PF and
Reservation stay clean until ×2.3.

**Two qualifications this must carry, both stated rather than discovered
later.** First, **whether the arm difference survives permutation is
UNTESTED**: D4's control was built for the *ordering* and measures M13's
output, not telemetry M02, so nothing here rules out declaration-order
sensitivity in this statistic too. Second, **E1's control pass could not have
caught it** — that check reads M13's GBR classes, and 5QI 1 is `Delay`, so
"the ramp bottom is clean" meant *clean for the ordering*, never *clean for
clause 4*. Both are gaps in this campaign's own instrumentation, named here.

**And this finding does not belong to G12.** A telemetry flow PDB-violated at
nominal load is a **G1/G3** result (drive-command p98 within PDB; no
false-failsafe); G12's clause 4 is only where it surfaced. Filed accordingly,
per §29's precedent of promoting the G5 failure out of the G6 item rather
than leaving it buried.

### 36.3 Region 2 — beyond 145 %, with the control beside it

`[2, 4]` on all 30 groups, all three arms, under the canonical order — 5QI 2
before 5QI 4, **G12's own inversion**. §36.1 is the control: PF's own
permutation 104 produces `[4, 2]` on all 5 of its seeds.

**A STRUCTURAL COMPETING EXPLANATION THE CAMPAIGN DID NOT DISCLOSE: the two
GBR classes do not start the ramp on equal terms.** Recomputed from the
scenario builder, not from a document:

| class | offered | GFBR | ratio | headroom above the 0.95 line at ramp bottom |
|---|---|---|---|---|
| 5QI 2 camera (4 of 5 flows) | 16,000 B / 33.0 ms = **3.879 Mbps** | 4.000 Mbps | **0.9697** | measured **0.9571–0.9724**, i.e. ~**0.007** |
| 5QI 4 lidar (both flows) | `int(3e6·m/8·0.1)` per 100 ms = **3.000·m Mbps** | 3.000·m | **1.0000** | measured **0.9978–1.0000**, i.e. ~**0.048–0.050** |

**The camera class is provisioned below its own guarantee**, so its
`gfbr_fraction` has an arithmetic ceiling of ~0.970 *in expectation* and it
begins the ramp roughly **7× closer to the contract line than the lidar
class does**. "Camera degrades first" is therefore **biased by the
workload's own provisioning, independently of any scheduler and
independently of flow-list order.**

**This is additive to the declaration-order artefact, not a replacement for
it** — permutation 104 flips the order with the provisioning byte-identical,
so position matters too. But it means the canonical `[2, 4]` order has a
structural explanation that owes nothing to scheduling, and any future
attempt to promote the ordering to a scheduler property must defeat *both*.

**Note the shape: this is §35.4's own trap (c) — "a GFBR provisioned above
what the flow offers can never be met" — recurring on a different class.**
`sim/scenarios/g12.py`'s docstring states that rule and applies it only to
5QI 1, where the mismatch is ~21×; the 3 % camera shortfall is the same
defect small enough to survive the check that was built for it. The same
pair appears independently in `sim/parametric.py`'s `factory` mix, so it
reaches the WP9 sweep's G10 and G6 cells too.

*(The deck that surfaced this rounded 3.879 → 3.89 before dividing and
reported a 0.973 ceiling; the exact value is 0.9697 → **0.970**. Fixing the
workload — e.g. 16,000 → 16,500 B — would be a fidelity change moving the
regression corpus and every G10/G12 number, so it needs its own commit
under the one-change-per-commit rule. Nothing here changes a number.)*

**The registered qualifier applies verbatim and is not softened here:** the
Region-2 ordering is **not established as a scheduler property and is
consistent with a declaration-order artefact.** It is not reported as an
inversion finding.

> **CORRECTED. This sentence previously read "*this ordering IS a property
> of declaration order*" — which is not what §35.13 registered**, and the
> difference is not cosmetic: the registered form is a **non-establishment**
> ("not established as X, consistent with Y"), and the replacement asserts
> a positive causal claim the permutation control does not license. The
> control shows the order *changes* with list position; it does not show
> position is *the* cause, and §36.4's own clause-2 edge says a traced
> mechanism would confirm the artefact rather than promote anything.
>
> **What makes this worth recording is the direction.** §35.13 committed
> the sentence in advance *"so it cannot be softened later, when a striking
> result is in hand"*. **The drift was not a softening — it was a
> hardening**, and the guard was written against only one direction. A
> pre-registered sentence needs to be protected against being made
> *stronger* as much as weaker; an over-claim is the more natural error
> when the result is striking, which is exactly the situation the guard
> anticipated. Found while building the client deck.

### 36.4 The promotion bar, applied as written — including its edge

- **Clause 1 — an arm difference surviving every permutation.** Does not
  fire: the arms **do not differ** under the canonical order (all three give
  `[2,4]`), so there is no difference to survive anything. **E5: HIT.**
- **Clause 2 — a mechanism traced to something position-independent.** Not
  run, and the edge stands: all three candidates §35.5 named are
  position-dependent, so tracing to any of them would **confirm** the
  artefact. "We found the mechanism" is not promotion.

**Neither fires, so the conclusion registered in §35.13 applies word for
word:** the Region-2 ordering is **not established as a scheduler property
and is consistent with a declaration-order artefact.** G12's row says that,
not an inversion.

### 36.5 Scoreboard

| # | expectation | verdict |
|---|---|---|
| **E1** | ramp bottom clean on all arms at every composition | **MISS** — 12/90 groups breach at ×1.0; two of three cells excluded whole |
| **E2** | two-element order on every arm | **HIT** — 30/30, but only beyond the guarantee's own range |
| **E3** *(clause 4)* | 5QI 1 intact wherever 5QI 9 still moves bytes | **MISS**, and the largest result here — M02 reaches 1.000 on every arm, TwoTier from ×1.0 |
| **E4** | "5QI 9 exhausted" not literally satisfied | **HIT** — median 3.836 Mbps still flowing at the first GBR breach |
| **E5** *(most-likely-wrong)* | order the same across arms | **HIT** — `[2,4]` on all three, canonical order |

**E5 was the registered most-likely-wrong and it HIT** — the first time in
this WP that slot has not carried the most interesting finding. It did not
need to: **the pattern held in substance rather than in form**, because the
result that mattered came from the expectation that missed. E3 is the largest
finding in the item, and it arrived through clause 4, which M13 never touches.

### 36.6 A defect in this scorer, found by decomposing its own output

`g12_score.py`'s first E3 implementation scored clause 4 on the **liveness
gap alone** and returned **UNSCOREABLE**. That was a defect, not a null:
`telemetry_max_gap_ms` is `None` on **116** ramp points because the flow
stops completing messages entirely, and a flow with no completions has no gap
between completions to measure. **The gap is blind exactly where the failure
is total** — the same shape as M19's registered caveat, and §33.3's
dynamic-range rule one level over. E3 as registered said *"no liveness-gap
**or PDB** degradation"*; the implementation had simply dropped half the
criterion. Scoring on M02 restores fidelity to the registration rather than
loosening it — and it moved E3 from UNSCOREABLE to **MISS**, i.e. against the
expectation, which is the honest direction for a post-hoc correction to run.

**Its second version then pooled across arms and reported "first degradation
at ×1.0"** — true of TwoTier only. **That is the standing decompose check
failing inside the tool built to apply it**, caught by asking which rows
entered the minimum before quoting it. Both fixes are in the committed
scorer.

### 36.7 End-of-item judgment-calls review

CLAUDE.md's standing step, run over the four G12 commits (`07da6fd`,
`6a37815`, `4abc657`, `b29c02d`). Four things found; two fixed here, two
recorded.

**1. FIXED — E2 pooled across cells, the same shape as §36.6's E3 defect.**
`score_expectations` keyed its per-arm two-element counts on `arm` alone, so
two scoreable cells would have merged into one figure reported as per-arm.
**Harmless in this run because the control pass left exactly one cell, and
silently wrong the moment it leaves two.** Found by deliberately looking for
E3's defect *shape* elsewhere in the same file rather than treating E3 as a
one-off — now keyed on `(cell, arm)`. Region 1's headline count now also
prints per cell beside the pooled figure, for the same reason: the pooled
number is only meaningful while one cell survives, and a reader should see
that rather than infer it.

**2. RECORDED, not fixed — `MEASURED_CEILING_BPS` is a measured constant
with no guard.** `sim/scenarios/g12.py` carries `63_400_000.0` from the
probe, and the whole ×-to-%-of-ceiling mapping rests on it.
`REFERENCE_COMMITTED_BPS` *is* guarded — a test recomputes it from the
builder — but the ceiling cannot be, because it is an outcome of running the
simulator, not a property of the scenario. **So a RAN-config change (`min_rb`,
bandwidth, TDD pattern) would silently invalidate "×3.3 = 146 % of ceiling"
and nothing would fail.** Not fixed because the honest fix is to re-run the
probe whenever the RAN changes, which is a procedure rather than a test.
Flagged so the next reader treats the percentage column as dated to this RAN.

**3. RECORDED — the campaign calls a private Scorecard method.**
`scripts/g12_campaign.py` calls `sc_card._m02_pdb_violation_rate(tele)` on a
5QI-restricted sub-record. **Deliberate:** it reuses M02's exact registered
definition rather than reimplementing the numerator/denominator, and M02's
denominator subtlety (resolved bytes, not arrived) is precisely the kind of
thing a reimplementation gets wrong — WP3 shipped a real M02 denominator bug
once (`c7baba9`). The cost is that a `scorecard.py` refactor can break a
study script silently. **The alternative — a public "score M02 over this flow
subset" entry point — is a panel-layer change and is not made inside G12's
own item**, on the one-fidelity-change-per-commit rule. Noted as the cheapest
future cleanup.

**4. RECORDED — clause 1 is scored more weakly than clauses 2–4.** E4 asks
only whether 5QI 9 still moves bytes at the first GBR breach, and answers
yes (median 3.836 Mbps). **It does not test the guarantee's actual ordering
claim about 5QI 9** — that best-effort is exhausted *before* anything else
degrades — because 5QI 9 has no contract and therefore no breach event to
order against the GBR classes. The bg trajectory is recorded per ramp point
in the campaign JSON, so the question is answerable from stored data without
a re-run; it simply was not registered as an expectation. **Left as a named
gap rather than answered post hoc**, since scoring an unregistered claim
after seeing the data is what the pre-registration discipline exists to
prevent.

**And one thing checked and found clean.** The `allow_one_element` /
`order_for_permutation` pair was re-read specifically for whether either had
become a general escape hatch. Neither has: `allow_one_element` is passed
`True` only for the in-range region and for a ramp with no out-of-range
points (derived, not hardcoded), and `order_for_permutation` is called only
from the D4 control. `assert_ramp_bottom_clean` is never bypassed anywhere —
the permutation arm records its failures, and the main grid still stops on
them.

---

## 37. G11 IS NOT RUNNABLE AS SPECIFIED — a feasibility finding, not a soak result

Measured on the overnight machine before any G11 code was written. **This
is a finding about the guarantee, not about the campaign that would have
scored it**: G11 could not have been run at 3 seeds, at 10 seeds, or at 1,
on the laptop or on the machine bought to replace it. The soak was never
budget-limited in the way §6.3 recorded.

### 37.1 The measurement

Base cell (`sweep_scenario` N=8, 32 flows, `cqi_delay_slots=8`),
`driver.run` only, horizons 20 k → 2.56 M, three arms. Peak RSS is **affine
in horizon with R² ≥ 0.99991** on every (arm, `record_timeseries`) series —
`85 MiB + 6.78 GiB per Mslot` with the timeseries on, `+3.36 GiB per Mslot`
with it off. GT-7.1's ≥30 min is **7,200,000 slots** at numerology 2.

| arm | peak RSS at 7.2 M, `record_timeseries=True` | with it **off** |
|---|---|---|
| PF | **47.7 GiB** | 23.7 GiB |
| Reservation | **47.7 GiB** | 23.5 GiB |
| TwoTier | **49.5 GiB** | 24.5 GiB |

**Both machines have 30 GB of RAM** (`§6.3b` for the laptop; re-measured on
the desktop), of which ~24 GiB is usable beside a desktop session.

**And the extrapolation was checked against a real run rather than
trusted.** One guarded 7,200,000-slot run, `record_timeseries=False`, PF —
*the cheapest arm* — under a 22 GiB watchdog:

```
14:06:00 pid=868929 rss=22317MB avail=2441MB
14:06:00 KILL pid=868929 rss=22317MB exceeded 22000MB
```

**It reached 21.8 GiB, was still climbing, and was stopped with 2.4 GB of
system memory left.** The fit said PF would pass 22 GiB before finishing;
it did.

### 37.2 Why `record_timeseries=True` is not optional

`scripts/wp9_sweep.py:101` sets it by default with the reason attached —
*"M04/M09/M19 are `pending` without it"*. **GT-7.1's KPI is that every 60 s
window passes G1/G3/G5/G8, and G8 is M09.** So the 48 GiB column is the one
G11 actually needs; the 24 GiB column is what you get by forfeiting a
quarter of the guarantee.

### 37.3 It is NOT the per-slot arrays — that is only half

The obvious reading is that per-slot timeseries are the problem
(`sim/metrics.py:91-121` appends one sample per slot per flow with no
stride). At 1.28 M they are **4,382 of 8,757 MiB — almost exactly half.**

The other half survives `record_timeseries=False` and grows linearly with
horizon. `tracemalloc` on a ts=0 run attributes it by line:

| MiB (h=80,000) | objects | site |
|---|---|---|
| 93.8 | 1,378,969 | `sim/traffic.py:178` — `Message(...)`, every message generated |
| 50.6 | 843,192 | `sim/buffer.py:161` — `MessageCompletion(...)` on drain |
| 32.1 | 535,722 | `sim/buffer.py:249` — `MessageCompletion(...)` on expiry |
| 19.3 | 689,228 | `sim/messages.py:77` — the message-**id** integers |

**It is per-message bookkeeping**, allocated in `traffic.py`/`buffer.py` and
retained by `MessageLedger._completions` and `BufferModel._completed`. Two
things that a coarser look gets wrong:

- **A filename-level read blames `sim/messages.py`**, which holds 19.3 of
  222 MiB — and even that row is the id counter, not the completions list.
  **The object size identified the line, not the line number**: 19.3 MB over
  689 k objects is 28 bytes, which is a CPython int.
- **It is not a saturation artefact.** 4× the horizon gives **4.04×** the
  objects, and **halving `load_mult` moves it 2.6 %** — the count is driven
  by the periodic flows' cadence, which `load_mult` does not scale. A
  gentler soak workload does not avoid it.

**And there is no flag.** `sim/driver.py:113-115` constructs the
`MessageLedger` unconditionally; `TrafficModel`'s `ledger=None` path
(`sim/traffic.py:80`) exists and is unreachable through `run()`.

### 37.4 What the deviation actually solved

§6.3 cut the soak from 10 seeds to 3 because *"3 arms × 10 seeds ≈ 21 h,
which does not fit alongside stage 2"*, and §5.1 of the handover recorded
it as reversible on a machine that runs unattended overnight.

**The time arithmetic was right.** Measured mean is 45.8 min/run against
§6.3's ≈43 — close, even though §6.3a found the cell table beside it 5–7×
low. **The memory budget was never taken at all**, and it is the binding
one: ~1.6× the whole machine, on a resource that **did not improve with the
new hardware** — both hosts have 30 GB.

So the deviation **solved a constraint that was not the blocker**, and its
reversibility was recorded against a machine property (cores) that is not
the one that binds. **Cutting seeds cannot fix an out-of-memory condition
in a single run**: 3 seeds and 10 seeds OOM identically, on run one.

### 37.5 The rule this leaves behind

§6.3a's rule was *time the thing you are actually going to run — same
horizon, same flags, same post-processing — or state explicitly that the
number is a lower bound.* It was written after a 5–7× timing miss and it is
about **time**.

**Extend it to every resource the run consumes, and to memory first**,
because the failure modes differ in kind:

- **A wrong time budget degrades.** You discover it late, the run takes
  longer than planned, and the result still arrives.
- **A wrong memory budget does not degrade — it terminates.** The run dies
  partway with nothing scored, which is how stage 1 lost 25 GB and how G11
  would have died ~20 minutes into its first 30-minute run.

**A budget that reports only time is a partial budget**, and the partiality
is invisible because time is what the cost model happens to measure. The
cheap guard is the one that caught this: **run one instance at the real
horizon under a watchdog with a kill threshold before committing to a
grid** — hours, against a work package.

### 37.6 What it does NOT say

- **Not "the simulator leaks."** The retention is a ledger doing its job;
  every completion is retained because run-aggregate metrics consume the
  whole run. It is a *scaling* mismatch with a 360×-longer horizon, not a
  defect.
- **Not "G11 is unanswerable."** It needs two mechanisms first — evicting
  each 60 s window's completions as it closes, and folding the per-slot
  arrays to per-second accumulators (which preserves M09 and M08w
  *exactly*). Both are things G11's own windowed scoring wants anyway. With
  them, per-run retention drops to ~1 GiB and the campaign fits 16-wide in
  **≈2.15 h**.
- **Not a fleet-size-general claim.** Every number here is the 32-flow
  parametric base cell. GT-7.1's literal two-asset workload is ~7–12 flows,
  where §13's cost model puts it 2.9–5.2× cheaper — it may well fit
  unmodified. **At the fleet size WP9 has been running, G11 does not fit;
  at GT-7.1's literal reading it is untested.** Which reading G11 answers
  is a scoping decision, and it must be made before the scenario is built.

Full plan: `docs/wp9-g11-plan.md`. Probe harness and raw measurements:
`sweeps/wp9/g11_probes/`, `sweeps/wp9/g11_*.jsonl`.
