# WP9 plan — the characterisation sweep (Phase 3)

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
*Expectation:* **Yes at N ≥ 8** on M07/M08, and — equally load-bearing —
**No at N=2 on any primary metric.**
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

### 6.3 The run-count arithmetic, stated before committing to axes

Measured on this machine, `record_timeseries=True`, at 20,000 slots (cost is
linear in slots and near-linear in N, both measured, not assumed):

| N | TwoTier | Reservation | PF | 3 arms × 10 seeds |
|---|---|---|---|---|
| 8–10 | ~3.6 s | ~1.3 s | ~1.25 s | **~62 s / cell** |
| 32 | ~7.5 s | ~3.8 s | ~3.5 s | **~150 s / cell** |

- **Stage 1: 50 cells ≈ 1.3 h single-core** — inside the ≤ 4 h ceiling with
  room for a full re-run after a fix.
- **Stage 2: ≤ 3 axes, ~256 cells ≈ 7 h** — inside the ≤ 24 h ceiling, leaving
  budget for both sub-campaigns below.
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
