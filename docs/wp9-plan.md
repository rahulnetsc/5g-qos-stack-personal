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
