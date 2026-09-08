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
exactly (PF 6 / Reservation 6 / TwoTier 5), so the comparison below is
like-for-like rather than two different questions.

| arm | 2 | 4 | 5 | 6 | 7 | 8 | 10 | 12 | 16 | boundary |
|---|---|---|---|---|---|---|---|---|---|---|
| PF — old | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** |
| PF — new | 10/10 | 10/10 | 10/10 | 10/10 | 9/10 | 10/10 | 10/10 | 9/10 | 0/10 | **6** |
| Reservation — old | 10/10 | 10/10 | 10/10 | 10/10 | 3/10 | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| Reservation — new | 10/10 | 10/10 | 10/10 | 10/10 | 4/10 | 1/10 | 0/10 | 0/10 | 0/10 | **6** |
| TwoTier — old | 10/10 | 10/10 | 10/10 | 9/10 | 6/10 | 2/10 | 0/10 | 0/10 | 0/10 | **5** |
| TwoTier — new | 10/10 | 10/10 | 10/10 | 9/10 | **9/10** | 3/10 | 0/10 | 0/10 | 0/10 | **5** |

**The boundary is unchanged: PF 6 / Reservation 6 / TwoTier 5.** RA's PRACH
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
