# G9 as a stress experiment — registration and result

**Opened 2026-09-08.** G9 is rebuilt as an experiment with an axis, not a
table row. This document is the registration (written before the runs) and
the report (§6 onward).

**The published G9 rows are WITHDRAWN.** `docs/STATE.md`'s G9 line and the
four rows in `docs/GUARANTEE-TABLE-2026-09-07.md` were produced with
`--rejoin-seed` on and undeclared, on artefacts predating M-9 and M-6.
Nothing in this document inherits from them.

---

## 1. Step 0 — pre-run corrections, each landed before any number was read

### 1.0 The control-plane floors: `sched_inactive` was hardcoded off

**Build 1.2 concluded that the two-tier arm has no SRB ranking tier. That
was wrong, and the error was a wrong file.** `has_srb` was grepped for in
`oai-branches/two-tier/gNB_scheduler_ulsch.c` — which is not this arm's UL
scheduler. The arm's own scheduler, `ia_p5g_scheduler.c:2778-2783`, promotes
any UE with LCG-0 bytes to the top (control-plane) class under a different
field name:

```c
int srb_pending_bytes = sched_ctrl->estimated_ul_buffer_per_lcg[0];
const bool srb_floor = (srb_pending_bytes > 0);
if (reconfig_floor || srb_floor)
    sched_inactive = true;   /* control-plane takes precedence */
else
    sched_inactive = ((B == 0 && do_sched) || cp_floor)
                     && !sched_ctrl->ul_has_unfulfilled_gbr;
```

**Who else reads this state — four sites, all wired in the same commit**,
because wiring one and leaving three is this project's most expensive
recurring defect:

| # | site | C | was |
|---|---|---|---|
| 1 | the UL sort tier | `ia_p5g_ul_cmp:2118-2120` | ported, permanent no-op |
| 2 | FIX-2's `gbr_below` exclusion | `:3025` | ported, no-op |
| 3 | **the `max_q` scan for the urgency normaliser** | `:2901` | **wrong once live** — a control-plane candidate would have set the normaliser for every data UE |
| 4 | **grant sizing** | `:3102`, `:3118`, `:3264` | **wrong once live** — control plane takes exactly `min_rb`, skips the FIX-2 cap and skips demand sizing |

**What becomes live that was inert — and it is not only SRBs.** `cp_floor`
= `B > 0 && data_lcg_bytes == 0` is precisely the BSR-desync fault this
project already documented (defects-log #24/#25): the SR report floor puts
bytes on `bytes_reported` while the per-LCG array still reads zero. The C
rescues that UE into the control-plane class. **This port did not.** So the
floor fires on workloads with no SRB traffic at all — 6 / 24 / 92 times at
N = 4 / 8 / 16 on the parametric mix.

**What this duplicates — nothing, now.** Reading the per-LCG UL array was
about to exist twice (`reservation.py::_ul_lcg0_estimate`, and two-tier's
new floor). Extracted to one function, `scheduler/flow.py::ul_lcg_bytes`,
before the second copy existed; reservation now delegates to it.

**One divergence, stated.** The C's `B` is
`max(0, estimated_ul_buffer - sched_ul_bytes)`, a UE-level scalar. The port
uses `sum(bytes_reported)`, which is what every other scheduler-side
backlog read in this repo uses (`reservation.py:906`). They differ only when
the UE-level estimate is positive while no flow reports anything, where the
C would fire `cp_floor` and this port does not — conservative, and stated
rather than hidden. `reconfig_floor` stays absent (no `await_reconfig` state
is modelled) and the `B == 0 && do_sched` disjunct is unreachable (M-9's
rescue reports through `sr_report_floor`, so a rescued UE always has B > 0).

**DELIBERATE RE-BASELINE — registered before the diff was read.**
`regression_corpus.py --check` moves **1905 values, every one of them
TwoTier**; PF, Reservation and RoundRobin are byte-identical, which is the
correct blast radius for a change confined to `two_tier.py`. The largest
effect is on `sensor_dense`, the scenario whose UEs are the ones starving:

| | before | after |
|---|---|---|
| `sensor_dense` UL PRB utilisation | 0.6325 | **0.8216** (+18.9 points) |
| `sensor_dense` CCE utilisation | 0.2748 | 0.2633 |
| `cp_floor` firings there | — | 184, of which 67 became grants |

This is the rescue landing: UEs that were starved by the desync now get one
`min_rb` grant, which carries the BSR that restores their normal
classification. **It is a port, not an improvement** — CLAUDE.md's rule is
to reproduce the C, and the C has this floor.

**Manipulation check (required before any number is read):** the counters
`srb_floor_fired` / `cp_floor_fired` / `sched_inactive_fired` /
`control_plane_grants` are emitted as `summary["scheduler_counters"]`, and
`sim/tests/test_control_plane_floor.py` pins all four read sites plus the
firing counts. Measured on GT-6.2 with SRBs: TwoTier `sched_inactive` 34,
`srb_floor` 23, control-plane grants 33; Reservation `has_srb` decisive 24.

### 1.1 `committed_mult` for the parametric cell (`sim/workload.py`)

`load_mult` scales the best-effort filler only, and the parametric cell is
already ~1.5x oversubscribed at x1.0, so it cannot reach the committed
plane. `scale_committed_load(scenario, mult)` scales **every GBR/Delay
flow's offered bytes and its contract (`gfbr_bps`/`mfbr_bps`/`pbr_bps`)
together** — demand and promise move as one, the confound `g12.py`'s own
`committed_mult` already avoided. The committed set is **derived from
`flow_class`**, never a list of QFIs; the per-kind load parameter is a map
that **refuses an unknown traffic kind** rather than passing it through
unscaled, with a test that derives the kind list from `sim/traffic.py`'s own
dispatch. Wired into `sweep_scenario(committed_mult=)` and all three G9
builders; the scenario name carries the value so a ledger cannot merge two
points.

### 1.2 `survival_time_ms`, and what could not be obtained

**TS 22.104's per-use-case survival-time table could not be obtained on this
machine** — ETSI returns 403, no copy exists in `~/Documents/.../3gpp/`, and
no readable transcription was found. Reconstructing that table from memory
is exactly what CLAUDE.md's spec-table rule forbids, so it is **requested,
not invented**, the same way the SRB capture was.

What *is* available locally is **TS 122 261 V17.11.0**, and it supplies both
the definition and the threshold rule verbatim (`pdftotext`, §3.1):

> *"survival time: the time that an application consuming a communication
> service may continue without an anticipated message."*

> *"the communication service is unavailable if a message is not correctly
> received within a specified time, which is the sum of maximum allowed
> end-to-end latency and survival time."*

For periodic deterministic traffic the anticipated messages arrive one
transfer interval apart, so **the time an application may continue without
`n` of them is `n × transfer_interval`** — derived from the flow's own
configured period, per flow, not assigned per 5QI from memory.
`with_survival_times(scenario, intervals)` sets it; `intervals` is the
CHOSEN part and is **swept**. Aperiodic kinds have no anticipated message
and stay at 0.

It is opt-in at the scenario level rather than resolved in
`FlowConfig.__post_init__`, because the regression corpus stores
`FlowRecord.survival_time_ms` and defaulting it non-zero would move 462
baseline values as a side effect of a scoring change.

### 1.3 Step 0(a) — G10's boundary, re-measured on current code

Re-run with `scripts/g5_consolidation.py` at **cap 4**, **RA + SRB on** (the
configuration this experiment runs in, so the axis range and the experiment
carry the same configuration), 9 fleet sizes × 3 arms × 10 seeds = 270 runs,
horizon 20 000. **Wall clock: 250 s at 12 workers, 0.93 s/run.**

**A scoring error caught before it became a result.** `M07_met` is a COUNT,
not a boolean, and truthiness-testing it made every arm pass to N=16. The
criterion is `M07_met == M07_total`, and it is verified by re-scoring the
**old** artefact with the same code: it reproduces the published table
exactly (PF 6 / Reservation 6 / TwoTier 5 -- **SUPERSEDED 2026-09-09: PF 12 /
Reservation 6 / TwoTier 7**, see this file's head note), so the comparison below is
like-for-like rather than two different questions.

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF — old | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** |
| PF — new | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** |
| Reservation — old | 10/10 | 10/10 | 10/10 | 10/10 | 3/10 | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| Reservation — new | 10/10 | 10/10 | 10/10 | 10/10 | 4/10 | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| TwoTier — old | 10/10 | 10/10 | 10/10 | 9/10 | 6/10 | 2/10 | 0/10 | 0/10 | 0/10 | **5** |
| TwoTier — new | 10/10 | 10/10 | 10/10 | 9/10 | **9/10** | 3/10 | 0/10 | 0/10 | 0/10 | **5** |

**The boundary is unchanged: PF 6 / Reservation 6 / TwoTier 5.**
**SUPERSEDED 2026-09-09 -- PF 12 / Reservation 6 / TwoTier 7.** The figure
above was measured before the GBR offered-shortfall fix; the camera's own
contract, not the cell's capacity, was binding it
(`docs/gbr-offered-shortfall-2026-09-08.md`, re-measured
`sweeps/g1-stress/g10_remeasure_cap4.json`). **The conclusion of this
section -- that RA and SRB do not move the boundary -- is unaffected**, since
both arms of that comparison carried the same shortfall. RA's PRACH
reservation (12 PRB in one slot per 20 ms) and SRB traffic (zero, with no
join events) do not move it, and the control-plane floor does not move it
either — it improves TwoTier *past* the boundary (N=7: 6/10 → 9/10) without
shifting where the first failure is. **So the published 6/6/5 stands**, and
this experiment's occupancy axis is set to span it:

| level | total UEs | `committed_mult` |
|---|---|---|
| 1 | 3 | 0.50 |
| 2 | 4 | 0.75 |
| 3 | 5 | 1.00 |
| 4 | 6 | 1.25 |
| 5 | 7 | 1.50 |
| 6 | 8 | 2.00 |

Levels 3-4 straddle every arm's boundary; 5-6 are past it, where the
baseline sanity gate is expected to start reporting CELL ALREADY BROKEN.

---

## 2. The experiment — parameters, complete

**Question, in the operator's terms:** *if the cell is already busy, will a
newly connecting robot start working correctly and immediately?*

**Runner:** `scripts/g9_stress.py`. **Artefact:**
`sweeps/g9-stress/g9_stress.json` (+ `.runs.jsonl`, one fsynced line per
completed run, so a kill loses nothing).

### 2.1 Axis, scenarios, arms

| | |
|---|---|
| **axis** | cell occupancy — **UE count and committed load move together**, one knob, because an operator does not experience them separately |
| **levels** | (3 UEs, ×0.50), (4, ×0.75), (5, ×1.00), (6, ×1.25), (7, ×1.50), (8, ×2.00) — total UEs incl. the joiner |
| **range set by** | G10's re-measured boundary, PF 6 / Reservation 6 / TwoTier 5 (§1.3). Levels 3-4 straddle it; 5-6 are past it. **SUPERSEDED 2026-09-09: the boundary is PF 12 / Reservation 6 / TwoTier 7**, so this occupancy axis straddles Reservation's and TwoTier's boundaries and sits well inside PF's -- the levels are unchanged, their position relative to PF's boundary is |
| **scenarios** | `warm` (GT-6.1 app restart), `cold` (GT-6.2 power cycle), `rlf` (GT-6.3 deep fade) — scored separately |
| **arms** | PF, Reservation, TwoTier |
| **seeds** | 10, paired (`regime_sweep.paired_seeds`) |
| **each run** | also builds its **paired control** — same seed, same fleet, no join schedule — so the neighbours delta is within-seed |
| **join rate** | **deferred, deliberately.** One joiner per run: this experiment is contention against incumbents, not between joiners |

### 2.2 Cell, flags, every state declared

| | |
|---|---|
| carrier | 40 MHz, numerology 2, TDD `DSUUU`, slot 0.25 ms |
| horizon | 20 000 slots (5.0 s) warm/cold; 30 000 (7.5 s) rlf |
| **M-6 cap** | **`max_sched_ues = 4`** — the deployment's value. The carrier caveat stands: this is 55 PRB against the deployment's 106 |
| **RA** | **ON**, deployed config (`RandomAccessConfig.deployed()`) |
| **SRB** | **ON** (`with_srb`, `srb: True`) — attach and re-establishment dialogues live |
| **`--rejoin-seed`** | **BOTH columns run and both reported**, each labelled |
| `cqi_delay_slots` | 8 |
| `attach_seed_slots` | **off** (the sim-only slot-0 lever; distinct from `--rejoin-seed`) |
| `committed_mult` | the axis (see above) |
| `survival_time` | **1 transfer interval** (`--intervals 1.0`), CHOSEN, swept |

### 2.3 Thresholds — where each one comes from

| clause | threshold | source |
|---|---|---|
| **warm re-handshake** | every committed flow available again, i.e. a delivery within **PDB + survival_time** | **TS 122 261 V17.11.0 §3.1**, transcribed |
| **post-RLF time-to-SLO** | same | same |
| **cold attach-to-streaming** | **≤ 15 s** | the test plan (L103), kept as the plan states it |
| **neighbours** | \|Δp98\| ≤ ε, **ε ∈ {0.5, 1, 2, 5} ms** | **CHOSEN — no spec basis. The test plan says "neighbours unaffected" and never states an ε**, so it is swept and reported at every value rather than fixed |

**PDB and survival time per 5QI, as actually built** (`intervals = 1.0`;
survival time is `n × transfer_interval`, derived from each flow's own
configured period per TS 122 261 §3.1's definition):

| 5QI | dir | class | traffic | PDB (ms) | survival (ms) | **budget (ms)** | GFBR | period (ms) |
|---|---|---|---|---|---|---|---|---|
| 1 | UL | Delay | periodic_control | 100 | 100 | **200** | — | 100 |
| 2 | UL | GBR | xr_video | 150 | 33 | **183** | 4 Mbps | 33 |
| 82 | DL | Delay | periodic_control | 100 | 50 | **150** | — | 50 |
| 8 | UL | PF | poisson (aggressor) | 300 | 0 | — | — | — |
| 70 / 71 | UL / DL | Delay | handshake pair | 1000 | 0 | — | — | fire-once |
| −11…−14 | UL / DL | — | SRB1/SRB2 | — | — | — | — | — |

**Scored population:** committed flows only — `flow_class ∈ {GBR, Delay}`,
**derived**, never a QFI list. Best-effort (5QI 8/9) carries no promise;
SRBs and the handshake pair are signalling, not services, and the handshake
pair is what sub-experiment A measures the *completion* of. **The fire-once
handshake period (1e9 ms) would have derived a 1e9 ms survival time**, a
number that reads as authoritative and makes a flow unconditionally
available — `with_survival_times` now bounds survival time by the
scenario's own horizon, and the campaign restarted clean rather than ship an
artefact whose rows spanned two code versions.

### 2.4 Scoring

**Baseline sanity gate, first.** Over the window ending at the first join
trigger (skipping one availability budget of warm-up), what fraction of the
time was any incumbent committed flow *unavailable* by the spec rule? Three
outcomes, all reported:

- **CELL ALREADY BROKEN** — the incumbents were failing before the joiner
  arrived, on more than half the seeds. A result an operator needs, not a
  skipped cell.
- **JOIN FAILURE** — the cell was fine, and the join clause failed.
- **PASS** — both.

**Yield rule, applied uniformly rather than per clause:** **9 of 10 seeds
pass AND no failing seed is catastrophic.** One seed slightly over a bound
is tail variance; one seed that never completes is a mechanism, and a single
one fails the point.

**Manipulation checks, asserted BEFORE any number above is read** — RA
completions by kind against the scenario's own scheduled count, SRB dialogue
steps non-zero on every path that has signalling, nothing still running at
the horizon, and the `sched_inactive` / `srb_floor` / `cp_floor` /
`has_srb_decisive` firing counts carried onto every row.

---

## 3. Manipulation checks — all four mechanisms fired, with counts

Read **before** any number below. Summed over all 540 unseeded runs
(the seeded column is comparable and in the artefact):

| mechanism | firings | reading |
|---|---|---|
| RA procedures | 670 dialogues started, **669 completed**, 140 preamble failures | fires and finishes; the 140 failures are all at the RLF fade floor, where Msg3 at MCS 0 cannot decode |
| SRB dialogue steps | **13 136** | signalling really flows |
| `sched_inactive` (TwoTier) | **7 147** | the tier that was hardcoded off is now decisive traffic |
| `srb_floor` | **3 734** | SRB backlog promoting a UE |
| `cp_floor` | **7 008** | the BSR-desync rescue |
| `has_srb_decisive` (Reservation) | **4 736** | its top tier separating adjacent candidates |
| still running at the horizon | RA 0, SRB **1** | one stalled dialogue in 670, recorded as catastrophic, not hidden |

**None of these read zero.** Had `sched_inactive` still read zero with SRB
traffic present, everything below would be uninterpretable — which is why
the check runs first.

## 4. Results

**How to read "B: time to a stable cell".** The horizon minus the first
trigger is **4.5 s** (warm/cold) and **4.5 s** (rlf). A value at that
ceiling means **the cell never settled before the run ended** — it is a
saturated counter, not a measurement, and is written as *never* below.

### 4.1 Warm re-handshake (GT-6.1) — unseeded

| occupancy | PF | Reservation | TwoTier |
|---|---|---|---|
| 3 UEs ×0.50 | PASS · 0.000 s | PASS · 0.000 s | PASS · 0.000 s |
| 4 UEs ×0.75 | PASS · 0.000 s | PASS · 0.000 s | PASS · 0.000 s |
| 5 UEs ×1.00 | PASS · 0.000 s | PASS · 0.000 s | PASS · 0.000 s · *cell never settles* |
| 6 UEs ×1.25 | PASS · 0.000 s | PASS · 0.000 s | PASS · 0.000 s · 3 broken seeds · *never settles* |
| 7 UEs ×1.50 | PASS · 0.000 s | PASS · 0.000 s | **CELL ALREADY BROKEN** · 10/10 seeds |
| 8 UEs ×2.00 | **CELL ALREADY BROKEN** · 7/10 | PASS · 0.000 s | **CELL ALREADY BROKEN** · 10/10 |

**A warm re-join is free on every arm, at every occupancy.** First service
is 0.000 s — the app restart never drops the radio, so the robot is served
in the first slot it has data. **The warm clause is not where the risk is**,
and no failure at 7-8 UEs is a join failure: the cell was already broken.

### 4.2 Cold attach-to-streaming (GT-6.2) — unseeded

| occupancy | PF | Reservation | TwoTier |
|---|---|---|---|
| 3 UEs ×0.50 | PASS · 0.100 s | PASS · 0.100 s | PASS · 0.102 s |
| 4 UEs ×0.75 | PASS · 0.100 s | **JOIN FAILURE** · 1 catastrophic seed | PASS · 0.106 s |
| 5 UEs ×1.00 | PASS · 0.100 s | PASS · 0.113 s | PASS · 0.119 s · *never settles* |
| 6 UEs ×1.25 | PASS · 0.100 s | PASS · 0.116 s | **JOIN FAILURE** · **5/10 seeds never complete** · 3.23 s |
| 7 UEs ×1.50 | PASS · 0.104 s | PASS · 0.126 s | **CELL ALREADY BROKEN** · 10/10 · 8 catastrophic |
| 8 UEs ×2.00 | **CELL ALREADY BROKEN** · 8/10 | PASS · 0.152 s | **CELL ALREADY BROKEN** · 10/10 |

**Attach-to-streaming is ~100 ms and essentially flat across the whole
axis** on PF and Reservation — against the test plan's 15 s bound, a **~150×
margin that occupancy does not erode**. Reservation drifts 0.100 → 0.152 s
from the lightest to the heaviest point; PF does not move at all.

**TwoTier is the arm that fails, and it fails *before* the cell is full.**
At 6 UEs — its own G10 boundary is 5 — **half the seeds never complete the
attach**, and first service jumps 0.119 → 3.23 s.

### 4.3 Post-RLF time-to-SLO (GT-6.3) — unseeded

| occupancy | PF | Reservation | TwoTier |
|---|---|---|---|
| 3 UEs ×0.50 | PASS · 1.031 s | PASS · 1.136 s | PASS · 1.031 s |
| 4 UEs ×0.75 | PASS · 1.031 s | PASS · 1.136 s | PASS · 1.048 s |
| 5 UEs ×1.00 | PASS · 1.031 s | PASS · 1.140 s | **CELL ALREADY BROKEN** · 7/10 · 5 catastrophic |
| 6 UEs ×1.25 | PASS · 1.031 s | PASS · 1.143 s | **CELL ALREADY BROKEN** · 10/10 · **10 catastrophic, no attach completes** |
| 7 UEs ×1.50 | PASS · 1.031 s | PASS · 1.148 s | **CELL ALREADY BROKEN** · 10/10 · 9 catastrophic |
| 8 UEs ×2.00 | **CELL ALREADY BROKEN** · 10/10 | **JOIN FAILURE** · 4 catastrophic | **CELL ALREADY BROKEN** · 10/10 |

**Recovery is ~1.03 s (PF) / ~1.14 s (Reservation) and flat**, against the
plan's 10 s bound — a **~9× margin**, and occupancy does not erode it up to
7 UEs. **TwoTier is broken from 5 UEs**, and at 6 and 8 UEs **not one seed
completes the recovery**.

### 4.4 The neighbours clause — the plan's missing ε is doing the work

Pooled over all 540 unseeded runs, the fraction whose worst incumbent p98
moved by no more than ε:

| ε | seed-runs within |
|---|---|
| **0.5 ms** | 184 / 540 (34 %) |
| **1.0 ms** | 217 / 540 (40 %) |
| **2.0 ms** | 266 / 540 (49 %) |
| **5.0 ms** | 408 / 540 (76 %) |

**"Neighbours unaffected" is not a testable clause as written.** At 1 ms it
fails on 60 % of runs; at 5 ms it passes on 76 %. **The verdict is chosen by
the ε, and the test plan does not state one** — so no neighbours result
should be quoted without its ε beside it. Signs are mixed rather than
uniformly bad: TwoTier's deltas are positive (up to +7.8 ms at 5 UEs, CI
excluding zero), while at 8 UEs ×2.0 every arm goes strongly *negative*
(PF −12.9 ms) because the cell is saturated and the paired control is
degraded too.

## 5. The `--rejoin-seed` lever — and whether RA retired it

**Both columns were run in full. Outcomes are identical on 53 of 54
(scenario × occupancy × arm) cells.** The single difference:

| cell | unseeded | seeded |
|---|---|---|
| cold, 6 UEs ×1.25, TwoTier | **JOIN FAILURE** (5/10 never complete) | **PASS** (0 never complete) |

Residual differences in catastrophic-seed counts, all TwoTier:
cold n=6 **5→0**, n=7 **8→3**; rlf n=5 **5→3**. PF and Reservation are
unchanged everywhere.

**The finding, and it is the one asked for.** Before Build 1, TwoTier could
not be scored on G9 without the seed at all — the runner's guard refused a
degenerate arm (1 of 5 cold events registering). **With RA and SRB live,
the unseeded column runs and scores on every cell.** The real RACH grant
plus the SRB dialogue supply what the sim-only BSR seed was standing in for.

**So: nearly redundant, not yet deletable.** It still rescues TwoTier at
exactly its boundary. The honest disposition is to keep the lever, **declare
it on every row that uses it** (which the withdrawn G9 rows did not), and
default it **off** — the unseeded column is the one that describes the
deployment, and it is now scoreable.

## 6. What an operator should take from this

1. **A robot rejoining after an app restart is served immediately, on every
   arm, at every occupancy tested.** Warm re-join is not a risk.
2. **A robot cold-attaching to a busy cell is streaming in ~100 ms** on PF
   and Reservation — 150× inside the 15 s bound, and flat across a 4× range
   of committed load.
3. **After a radio outage a robot is back inside ~1.1 s**, ~9× inside the
   10 s bound.
4. **On TwoTier, none of that holds once the cell reaches 5-6 robots.** At
   6 UEs half the cold attaches never complete; after an RLF at 6 or 8 UEs,
   **none** do. Its G10 admissible boundary is 5, and the join clauses fail
   at or just past it — the two agree.
5. **PF's cell breaks at 8 UEs ×2.0 while its joins keep working.** The
   distinction the gate exists to draw: the joiner is fine, the incumbents
   are not. An operator seeing "joins are fine" there would be looking at
   the wrong thing.
6. **Reservation is the most robust arm in this experiment** — PASS to
   8 UEs ×2.0 on warm and cold, failing only post-RLF at the top point.
7. **Do not quote a neighbours verdict without its ε.**

## 7. Run times

| campaign | runs | wall | per run |
|---|---|---|---|
| G10 re-measurement (Step 0a) | 270 | **250 s** | 0.93 s |
| G9 stress, leg 1 (aborted at 430) | 430 | ~300 s | 0.70 s |
| G9 stress, leg 2 (resumed) | 650 | **513 s** | 0.79 s |
| **G9 stress total** | **1 080 rows = 2 160 driver runs** | **~813 s** | **0.75 s/row** |
| **all campaigns** | | **~1 063 s (17.7 min)** | |

12 workers, `OMP_NUM_THREADS=1`. Mean CPU per row (joiner + paired control)
**12.72 s**. The resumed leg re-ran only the 650 unbanked rows: the ledger
banks one fsynced line per completed run, and only the *guard* changed
between legs, not any run's behaviour.

## 8. Caveats, stated on the result rather than buried

- **`survival_time` is 1 transfer interval, CHOSEN.** TS 22.104's table
  could not be obtained (§1.2); the derivation rule is TS 122 261's, the
  count of intervals is ours and is swept.
- **The neighbours ε is chosen and unspecified by the plan** (§4.4).
- **This carrier is 55 PRB against the deployment's 106**, so cap 4 is the
  deployment's value on half its bandwidth. Neither cap is the deployment's
  system.
- **`stable cell` saturates at 4.5 s** = horizon − trigger; at that value
  the cell never settled within the run, and no larger number exists to
  measure.
- **TwoTier's `sched_inactive` went live in this same pass** (§1.0). Its
  numbers here are the first measured with the control-plane floors ported;
  they are not comparable to any TwoTier G9 figure published before
  2026-09-08.
