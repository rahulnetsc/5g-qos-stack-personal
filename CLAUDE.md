# 5g-qos-stack — working notes for Claude

Read `README.md` first; it is the branch charter and is authoritative wherever
it conflicts with `docs/p5g-sim-plan.md`. This file is only the things that
get re-explained every session.

## Commands

```bash
uv sync                                          # set up env (first time)
uv run pytest sim/tests -q                       # full suite (~45s, must stay green)
uv run pytest sim/tests/test_scorecard.py -q     # one file
uv run python scripts/regression_corpus.py --check   # numeric drift vs snapshot
uv run python scripts/regression_corpus.py --capture # re-baseline (see rules below)
uv run python scripts/scheduler_study.py         # the published studies 1-3
uv run python scripts/parallel_audit.py --check  # no runner ships serial
uv run python scripts/verify_parallel.py         # serial == parallel, per runner
```

Everything runs under `uv run`. There is no `pip install -e .` step and no
bare `python` invocation that works.

## Project layout

- `sim/` — simulator: `driver.py` (slot loop), `channel.py`, `buffer.py`,
  `traffic.py`, `resource.py`, `ue_lcp.py`, `metrics.py`.
- `sim/power.py` — WP1. Tx power headroom (`ph_factor`, `shrink_to_power_budget`).
  Dormant: not imported by `driver.py` or any scheduler. PHR is inert on
  hardware (README §4).
- `sim/bsr.py` — WP3. UL BSR realism: per-LCG quantisation (TS 38.321
  Tables 6.1.3.1-1/-2), short-BSR aliasing, event-triggering (regular/
  periodic/retx), and the `sched_ul_bytes` crumb-collapse gate.
  `sim/buffer.py` is purely the true-backlog store now — it does not model
  BSR delay/loss/quantisation at all; `BsrModel` is the only writer of a
  UL flow's `bytes_reported`/`estimated_ul_buffer_per_lcg`.
- `sim/run_record.py`, `sim/scorecard.py` — WP0 (+ WP3 for M02, WP7 for
  M01/M03/M05/M06/M14/M15/M17, WP-Join for M18/M19). The scoring layer.
  `scorecard.py` must not import `sim/driver.py` or `sim/config.py`; it
  consumes `RunRecord` only, so it can score records from any producer.
- `sim/messages.py` — WP7. `Message`/`MessageCompletion`/`MessageLedger`
  (per-message identity and completion bookkeeping) and
  `FrameCompletion`/`FrameLedger` (grouping sibling PDU-set fragments by
  `frame_id`). Pure simulator-side scoring construct — no OAI ground truth,
  no real network element learns per-message identity (`sim/bsr.py`,
  `sim/ul_access.py` stay untouched).
- `sim/cycle_clock.py` — WP7. Stateless phase-offset math for
  `FlowConfig.sync_group`'s correlated-burst mechanism — every member
  anchors to slot 0 independently, so no shared mutable clock state is
  actually needed. Only `sim/traffic.py`'s `periodic_control`/
  `condition_monitor` kind reads it; every other kind ignores `sync_group`
  silently.
- `sim/pathloss.py`, `sim/blockage.py` — WP6. TR 38.901 InF path loss/LOS
  probability (the real five sub-scenarios are SL/DL/SH/DH/HH — not the
  four this repo's own docs used to cite, README §8) and two-state Markov
  blockage. Both opt-in via `UEConfig.position`/`inf_scenario`/`blockage`
  (default `None` preserves pre-WP6 behaviour exactly); wired into
  `sim/channel.py`, not `driver.py`.
- `sim/rlf.py` — WP6. Sync-loss (RLF) *detection* only (`n310`-armed
  `t310` dwell, `n311`-gated cancel). The module's own code is still pure
  (no simulator/scheduler imports) and detection-only, but it is **no
  longer dormant**: WP-Join commit 2 wires `step()` into `driver.py`'s
  slot loop unconditionally, per UE per slot. Recovery timing (`t311`/
  `t300`/`t301`/`t319`) is implemented in `sim/join.py`, not this file —
  see invariants below for the exact interface WP-Join consumes.
- `sim/join.py` — WP-Join. Per-UE join/re-join/RLF-recovery FSM
  (`JoinConfig`/`JoinState`/`JoinRngStreams`) plus `JoinAwareBufferView`,
  composed outermost over `HarqAwareBufferView` in `driver.py`, gating a
  UE out of scheduling with zero scheduler-interface change. Consumes
  `sim/rlf.py`'s `RlfStepResult.rlf_declared_this_slot` edge event; does
  not extend `rlf.py`'s state machine itself — see invariants below.
- `config/metric_panel.yml` — the pre-registered metric panel. **Its size is
  DERIVED, never quoted**: `len(load_panel()["metrics"])`. Any "N metrics"
  in `docs/` is as-of-writing and has been wrong at least three times (19 →
  21 → 22). Every metric now also records a `population:` binding — see the
  population rules below. See rules
  below, including WP-Join's M18/M19 (the panel's first additions since
  WP0 pre-registration).
- `scheduler/` — `two_tier.py`, `tier1.py`, `link.py`, `flow.py`,
  `interfaces.py`. `flow.py::FlowConfig.lcg` self-resolves from 5QI via
  `__post_init__` — see invariants below. `interfaces.py`'s
  `SchedulerContextReset` Protocol (WP-Join commit 7) is implemented only
  by `two_tier.py` (`reset_ue(ue_id, scope, buffers)`) — the one
  scheduler-file change in this WP, and the only one since WP0.
- `sim/baselines/` — PF, RoundRobin, Gradient. The Phase 1 comparison arms.
- `oai-branches/{two-tier,reservation}/` — read-only verified OAI C source.
  Ground truth for Phase 2. Same filenames in both dirs with *different*
  contents; never merge or dedupe them. `two-tier/nr_mac_common.c` and
  `nr_ue_scheduler.c` (WP3) are vendored from a *different* upstream
  directory (`NR_MAC_COMMON`/`NR_MAC_UE`, not `NR_MAC_gNB`) than the rest —
  see `oai-branches/README.md` for per-file commit provenance.
- `regression/baseline_studies_1_3.json` — 20-record numeric snapshot.
  **Derive it, do not quote it:** `len(json.load(...)["records"])` and
  `len(regression_corpus._cases())` both give 20. (The file has ONE top-level
  key, `records`; an earlier note here said "20 keys", which is the same
  restated-count slip one level down.) Described as "22-record" until WP9's
  fix commit — stale, most
  likely from a pre-Phase-2 capture whose `TwoTier-nomaxmin`/
  `TwoTier-adaptive` arms were deleted at Phase 2 two-tier commit 1.)
- `docs/` — planning docs. `p5g-sim-plan.md` §9 has the per-WP technical spec.

## Non-obvious invariants

These are the ones where the "helpful" fix is the wrong one.

**Reproduce measured behavior, not documented intent.** Where the OAI C
source's comment disagrees with its code, the *code* is what shipped and
what produced the hardware numbers. Known case: reservation's post-grant
deficit drain comments "distribute tb_size drain proportionally across
active LCGs" and then credits the full `tb_size` to every active LCG
independently. Port the full-credit behavior. Do not make it proportional.
If you find another comment/code mismatch, flag it and ask — do not
reconcile it silently in either direction.
**This rule governs this repo's own stale defaults too, not only values
ported from OAI source.** Confirmed by a third instance, found scoping
Phase 2: `scheduler/two_tier.py`'s `tier1_period_slots` default (`2000`)
was written to match `ia_p5g_scheduler.h`'s doc-commented "1.0 s default"
for Tier-1's LP re-solve cadence — but that comment is itself stale (see
the Tier-1-period invariant above); the deployed macro is 0.1 s
(`IA_P5G_TIER1_PERIOD_S`, `ia_p5g_scheduler.c:74-76`). At this repo's
default `numerology=1` (`sim/config.py`, `slot_duration_s=0.5ms`),
`2000 * 0.5ms = 1.0s` — the Python default silently encodes the header's
wrong value, not the confirmed-real one. Phase 2's rewrite defaults to
200 slots (or better, derives the slot count from `tier1_period_s=0.1`
÷ `grid.slot_duration_s` so it survives a numerology change) — this is
not a special case of the OAI-comment rule, it's the same rule applied to
a default this codebase itself chose.

**TIER-1'S LP HAS MULTIPLE OPTIMA AND ITS SCA LOOP DOES NOT CONVERGE —
so `scheduler/tier1.py`'s output depends on the SOLVER PATH, not only on
the model.** Measured 2026-09-04 over one real run's 2,437 Tier-1 LPs
(`sweeps/phase2/lp-degeneracy-2026-09-04/`): solving each one twice, via
`scipy.optimize.linprog(method="highs")` and via a directly-built HiGHS
model with scipy's own options, returns a **different `x` on 1,781 of them
(73 %)** — median max abs difference **3.3e6** — while the **relative
objective gap never exceeds 9.5e-11** and **both points are feasible in all
2,437**. That is degeneracy: same optimal face, different vertex, chosen by
how the solver got there. `presolve` on/choose/off does not change it.

**Two consequences, and the second is the one that will surprise someone.**

1. **A pure-speedup swap of the LP call cannot be bit-identical**, so the
   41×-per-call direct-HiGHS optimisation the profile identified is
   **unavailable at this project's own bar** and was reverted rather than
   landed — both the warm (reuse model, change `c`) and cold (rebuild per
   call) variants move `regression_corpus.py --check`, e.g. TwoTier
   `ue9_qfi9` `throughput_bps` 5,521,232 → 5,340,428. Unblocking it means
   giving the LP its own vertex-selection rule (lexicographic tie-break, or
   a tiny secondary objective), which is a **behaviour change to the
   scheduler**, would move the corpus deliberately, and needs its own
   decision against ground truth.
2. **The regression corpus is pinning a solver path as tightly as it is
   pinning the scheduler.** A scipy upgrade is a scheduler change here.
   Treat a `--check` diff after a dependency bump as this first, before
   looking for a fidelity regression.

**And the loop runs to its cap: 41 of 50 Tier-1 solves hit
`_SCA_MAXITERS = 150` without reaching `_SCA_TOL = 1e-6`** (median 150
iterations, mean 133.1, 6,656 LP solves in one 20,000-slot run). So on 82 %
of solves the targets are not a converged fixed point — they are where the
damped sequence stood at iteration 150, across 150 degenerate LPs. **The cap
is faithful to ground truth** (`IA_P5G_TIER1_SCA_MAXITERS`), so this is not
a porting error; what is **unknown** is whether the deployed C converges
where this does not, since GLPK's vertex selection is not HiGHS's. Do not
"fix" the convergence by raising the cap — that would depart from ground
truth to chase a property nobody has established the real system has.

**Do not add SPS / Configured Grant to the schedulers.** `main`'s
`scheduler/two_tier.py` had it (`_SPSReservation`, `_allocate_sps`); the real
hardware scheduler defers SPS to a Phase 2 that was never built. The Python
model must match the deployed scheduler, not exceed it. **This branch's
`scheduler/two_tier.py` no longer contains any of it** — Phase 2 two-tier
commit 1 deleted the lot, so the rule now reads as "do not re-add", and the
only occurrences of those names are in the docstring recording the
deletion.

**The gNB cannot see a UE's intra-TB per-flow split.** Only aggregate
per-LCG BSR. `main` has `_shadow_lcp_split` / `_occupancy_split` /
`_mac_lcp_fill` doing this anyway; it is a known modeling error, not a
pattern to extend. When adding any mechanism, ask which network element
would actually learn this and how.

**Tier-1 period is 0.1 s, not the 1.0 s in `ia_p5g_scheduler.h`'s doc
comment.** The `.c` file hoists the macro; the gNB startup banner confirms
100 ms is what ran.

**`min_rb` is a static gNB config constant (`nrmac->min_grant_prb`), not
derived from SNR or payload.** Don't compute it from channel quality —
that's a different, sim-only quantity (`scheduler/link.py::snr_to_prb_floor`,
WP1). See README §7 for the full distinction; Phase 2's reservation
follower budget needs the real one.

**When porting an OAI C function, check every call site before collapsing
or defaulting a parameter.** WP1 almost shipped `compute_ph_factor`'s
`include_bw` as always-`true` after checking 3 of its 6 call sites; the
other 3 (`phr_txpower_calc`) pass `false`. Also mirror `AssertFatal`
preconditions as raises rather than dropping them (silently wrong beats
loudly wrong), and mirror `roundf()` (half-away-from-zero) explicitly
instead of Python's `round()` (half-to-even) — they disagree at exact
`.5`. `sim/power.py` is the worked example for all three.

**PARALLEL BY DEFAULT — a runner that calls the driver in a loop uses
`regime_sweep.run_cells`, and its serial path is the REFERENCE, not a
fallback.** Parallelism landed once, at `scripts/wp9_sweep.py` (`0ec8ddb`),
with a correct determinism argument and a bit-identity check — and every
runner written afterwards was serial, including the five that produced every
Phase 2 result. They imported that module's `BASE` / `_arms` /
`_driver_kwargs`, so they **inherited its configuration and not its pool**,
which is why nobody noticed: an import from the fixed module reads like
inheriting the fix. `g12_campaign.py` then timed out at 2,400 s having
completed one cell, on one of sixteen cores. Recorded as the second clean
instance of `prediction-journal.md`'s fix-at-the-category rule.

Four things travel with the pool, each from a measured failure, and
`run_cells` carries all four so a new runner cannot lose them:

- **It is a CORRECTNESS change, not a speedup.** Every comparison here is
  within-seed, so the acceptance criterion is **byte-identical output to the
  serial path on the same seeds, verified per script** —
  `scripts/verify_parallel.py`, not inherited from `0ec8ddb`'s one check of
  one runner. Exclusions from that diff are named per runner and have to earn
  themselves: provenance must be present *and* differ, and a timing exclusion
  must be a clock by name, so a result cannot be reclassified as "timing" to
  make a difference disappear.
- **`OMP_NUM_THREADS=1` and friends, set in the PARENT before the pool.** W
  workers each running a multi-threaded BLAS oversubscribe the machine. It
  cannot be done in a Pool `initializer=`: under `spawn` a worker imports
  numpy while unpickling the task, which is *before* the initializer runs.
- **The parent retains nothing live.** `run_cells` is a generator handing one
  result at a time; a worker reduces, strips or projects before returning.
  This is the 25 GB retention stall (`wp9_sweep.m13_projection`), which was
  fixed in the parent and then reintroduced one layer down in the worker.
- **Longest-first, `chunksize=1`.** `pool.map`'s default chunking hands one
  worker a contiguous block of a cost-ordered list; on `g10_rerun.py` that
  gave one worker every N=32 TwoTier cell and another every N=2 PF one — 1.7×
  imbalance. `run_cells(cost=...)` orders submission and carries the task's
  original index through, so output order stays independent of it.

**`scripts/parallel_audit.py` is what makes this hold without anyone
remembering to check.** It derives the runner/parallel split from each file's
AST — never from a grep written into prose — and `--check` exits non-zero on
a serial runner not named in its `ALLOW_SERIAL` list with a reason. Serial on
purpose is fine; serial silently is the finding.

**One fidelity change per commit.** Land it, run the full suite, run
`regression_corpus.py --check`, and record which numbers moved and why.
Bundling two changes makes the deltas uninterpretable, which is the whole
point of the corpus.

**A UL flow's `bytes_reported` deadlocks without something to break the
cold-start silence — WP4 landed the real fix; don't revert to a probe.**
Every scheduler's UL eligibility gate reads `bytes_reported > 0`, but only
a grant updates it (`sim/bsr.py::BsrModel.on_ul_grant`), and a grant
requires the gate to already be open. This recurs every time a flow's real
backlog goes from empty back to non-empty, which is most UL traffic in
this repo. WP3's stopgap (a probe that bypassed straight to true backlog)
is retired; `sim/ul_access.py::UlAccessModel` now models the real
mechanism — SR on PUCCH → `sr-ProhibitTimer` → grant → BSR — and
`BsrModel.broadcast()` asks it for `sr_report_floor()` instead of probing.
Don't reintroduce the old probe or bypass `UlAccessModel`'s wait as a
"simplification" — doing so silently breaks UL throughput the same way
removing the old probe did, and desyncs the crumb-fraction/latency numbers
this document tracks (README §8).

**`sim/baselines/pf.py`'s `_r_avg` is one EWMA per UE, shared across that
UE's UL and DL flows — a UL-only change can still move DL numbers on the
PF arm.** `allocate()` schedules DL then UL each slot, updating the same
`_r_avg[ue_id]` either way, so a UE's DL competitive ranking in a later
slot depends on its UL grant history too. Confirmed via WP4: sweeping only
`sr_period_slots` (UL-only) shifted PF's per-UE DL PRB counts while
TwoTier's and RoundRobin's `dl_prb_utilization` stayed bit-for-bit
identical **for that specific sweep**. Not a bug, and not a Tier-1
boundary leak — don't "fix" it by splitting into per-direction rates —
but expect PF-arm DL drift whenever a UL-only change lands, and check
`pf.py` before assuming a DL mismatch means something crossed a
scheduler boundary it shouldn't have. **Not evidence that TwoTier (or
any scheduler) is immune to cross-direction effects in general** — see
the very next invariant below for a different, simulator-level mechanism
(`HarqProcessPool.due_this_slot()`'s shared iteration order) that moved
TwoTier's own UL numbers from a DL-only change.

**`sim/harq.py::HarqProcessPool.due_this_slot()` iterates one shared
dict across every (UE, direction) pool, in insertion order — a DL-only
scheduling change can still shift UL HARQ outcomes for a different UE.**
`_pools` lazily creates a `(ue_id, direction)` entry the first time that
UE gets a grant in that direction; `due_this_slot()` returns every due
process across every pool in that dict's iteration order, and
`sim/driver.py`'s retransmission loop draws HARQ outcomes in exactly
that order — `harq_rng_dl`/`harq_rng_ul` stay correctly separated
per-direction (WP5's own fix), but *within* one direction, if a DL-only
change reorders which UE gets its first grant earliest, the relative
insertion order of `(ue_id, "UL")` keys among the `(other_ue, "DL")`
keys they're interleaved with can shift too — reordering which UL UE's
retry draws from `harq_rng_ul` first, giving different UEs different
random values without any change to UL's own scheduling logic. Found
scoping two-tier's Phase 2 commit 3 (`docs/phase2-plan.md`): a DL-only
sort-tier change (`has_gbr`/`pdb_ms`, no UL code touched) moved
`ul_prb_utilization` and per-UE UL delivered-bytes on 2 of 6 regression
records, confirmed via direct trace (identical SNR, identical
`_ul_rank_key` formula, but a real ~94-byte drain-amount divergence at
the first affected UL grant, growing over the run) — not a bug, and not
limited to two-tier: any scheduler is exposed the moment its own DL and
UL grant timing for different UEs can vary independently. Don't "fix" by
sorting `due_this_slot()`'s output (would silently change which UE's
retry resolves first, a different behavior change, not a neutral one);
expect small UL drift whenever a DL-only change lands (or vice versa)
and confirm via a worktree-instrumented direct-cause trace before
assuming a cross-direction mismatch means a scheduler boundary was
crossed.

**`sim/bsr.py`'s per-LCG array is frozen between BSRs — do not drain it on
a grant, and do not resync it with the scalar `estimated_ul_buffer`.**
Faithful to the OAI ground truth (README §7): a grant only drains a
separate `ul_lcg_deficit_bytes`-style counter in the real C, never
`estimated_ul_buffer_per_lcg` itself; the scalar *is* decremented on real
data receipt but the per-LCG array is not, so the two legitimately desync
between BSRs. Both are deliberate, not oversights.
**Since WP5: "real data receipt" means *confirmed* receipt, not grant
time — they stopped being the same event once UL HARQ retry existed.**
`on_ul_grant(..., delivered_bytes=...)` still decrements unconditionally
whatever it's given (kept byte-for-byte backward compatible for pre-WP5
callers), but the HARQ-aware call site in `driver.py` now passes
`delivered_bytes=0` at grant time and calls the separate
`on_ul_confirmed_receipt(ue_id, delivered_bytes)` only once a HARQ attempt
is actually known to have succeeded. WP5's own end-of-WP review found and
fixed a real bug here: the first UL-retry implementation called the old
unconditional decrement at grant time regardless of outcome, crediting
"received" for bytes that could still fail, retry, or be lost to
max-retx exhaustion. If you add another UL delivery path, wire it to
`on_ul_confirmed_receipt` on success, never to `on_ul_grant`'s
`delivered_bytes` directly.

**HARQ delivery is a binary per-TB draw, not a fractional discount — do
not reintroduce `bytes_capacity * (1 - bler)`.** Pre-WP5, every DL/UL
grant applied a deterministic fractional loss straight to delivered
bytes; real HARQ has no concept of "70% of a transport block," only
success/failure per attempt (`sim/harq.py::draw_harq_outcome`). WP5 found
this fractional model was the dominant driver of the pre-4a/post-4a
latency-metric drift — every latency number before commit 4a was shaped
more by this unphysical smoothing artifact than by anything a real
network does. A future "smooth out the noisy binary outcome" change would
be reintroducing exactly the artifact WP5 removed, not an improvement.

**`sim/harq.py::HarqAwareBufferView` fully masks (`bytes_queued=0`/
`bytes_reported=0`) a flow with a HARQ process pending — this is a FIFO
correctness requirement, not a modeling preference, and must not be
loosened to a partial/proportional mask.** `sim/buffer.py`'s `drain()`/
`expire()` consume by byte count, not by chunk identity — they don't know
which bytes are "the ones already granted and in flight." A second grant
issued to a masked flow while its first TB is still pending would drain
whatever bytes are oldest by FIFO order, which may not be the pending
ones, silently corrupting delivery/completion bookkeeping rather than
just being a suboptimal scheduling choice.

**CORRECTED 2026-09-03: the SPS bypass this paragraph used to describe NO
LONGER EXISTS in this branch.** It read that `scheduler/two_tier.py`'s SPS
path "defeats this non-destructively by pooling backlog across a UE's
SPS-eligible flows", presented as a live flagged limitation. **Phase 2
two-tier commit 1 deleted `_SPSReservation`, `_allocate_sps`,
`_is_sps_eligible` and everything that fed them** — `grep` now finds those
names only inside the docstring recording their removal. **There is no
masking bypass in the shipped scheduler**, and the accompanying
`harq_masked_flow_double_grant_count = 877` was measured before the
deletion, so it does not describe this code either.

**The masking rule above is unchanged and is why this correction matters:**
with the SPS path gone there is no longer any sanctioned exception to it,
so a future author cannot cite SPS as precedent for relaxing the mask.
Note also that `harq_masked_flow_double_grant_count` never reaches
`RunRecord` and no test asserts it, so the "standing regression check"
README §8 claims for it **cannot currently fail** — see the
could-have-failed rule below.

**`harq_exhausted_count` and `bytes_harq_lost` are two different counters
measuring two different failure modes — do not conflate them.**
`harq_exhausted_count` (`sim/driver.py`) counts HARQ *pool* exhaustion:
`HarqProcessPool.allocate()` returned `None` because every process slot
for that (UE, direction) was already busy (`dl_capacity=8`/
`ul_capacity=16`, WP5 Decision 2) — a scheduling-eligibility problem.
`bytes_harq_lost` (`buffers.discard_harq_loss`, surfaced per-flow via
`Metrics.summary()`) counts *retry-cap* exhaustion: a TB that used all
`harq_round_max` attempts and still failed — a link-quality problem. A
scenario can have zero of one and many of the other. WP6 commit 4's own
demo hit exactly this confusion first-hand: checked `harq_exhausted_count`
after adding blockage, saw 0 in every arm, briefly read that as a
refutation of the whole mechanism — the real signal was always in
`bytes_harq_lost` (`docs/wp6-plan.md` commit 4). A third disposition
exists beyond "delivered" and "retry-exhausted": `HarqProcessPool.
flush_ue()` (WP-Join) frees every busy HARQ process for a UE on a
radio-gated transition, bypassing `drain()`/`discard_harq_loss()`
entirely — the bytes stay in `BufferModel` and are re-granted later, so
this isn't a third loss category, just a third exit from "pending" that
neither counter above observes.

**A TB's `Allocation.snr_used_db` (the MCS-pick-time SNR) freezes at its
ORIGINAL grant and is reused unchanged across every retry — this makes
`cqi_delay_slots` load-bearing for any interaction between a
time-varying channel and HARQ retry, not just a CQI-realism nicety.**
`sim/harq.py::HarqProcess.snr_used_db` is set once in `allocate()`; every
later `draw_harq_outcome` call for that process (`sim/driver.py`'s retry
loop) reuses it rather than re-picking against a fresh reported SNR. So a
fresh grant issued *while a channel condition is already in effect* (e.g.
mid-blockage) gets its threshold matched to the CURRENT degraded SNR and
sees no elevated BLER — only a TB whose threshold was committed *before*
a condition changed and evaluated *after* is at risk. At
`cqi_delay_slots=0` this only happens by rare coincidence (a TB caught
specifically mid-retry at the exact transition instant); at a realistic
`cqi_delay_slots=8` (`scripts/scheduler_study.py::CQI_DELAY_SLOTS`, the
value every real study in this branch runs with, not the driver's bare
`0` default), every fresh grant issued in the ~8 slots after a transition
inherits a stale threshold, turning a rare coincidence into a near-
certainty. Confirmed empirically, not just reasoned: WP6's blockage×HARQ
interaction showed unreliable, overlapping results at `cqi_delay_slots=0`
(0-6193 bytes lost across 7 seeds, overlapping the no-blockage baseline)
and a clean, non-overlapping separation at `cqi_delay_slots=8` (5200-
21514 vs 0-800, `docs/wp6-plan.md` commit 4). Before concluding a
time-varying-channel interaction with HARQ is weak or absent, check
`cqi_delay_slots` first.

**`sim/rlf.py`'s `RlfDetectorState`/`RlfStepResult` is `sim/join.py`'s
contract — consume it, don't extend the state machine inside `sim/
rlf.py` itself.** It exposes exactly three things: `sync_state` (the
level — `IN_SYNC`/`T310_RUNNING`/`RLF_DECLARED`), `RlfStepResult.
rlf_declared_this_slot` (an edge-triggered event, true for the one slot
RLF is declared — react to this, don't poll the level and re-derive the
edge), and `rlf_declared_at_slot` (timestamp). `step()` never un-declares
RLF once reached; re-arming after a real reattach is `sim/join.py`'s job,
confirmed landed: `driver.py` constructs a fresh `RlfDetectorState()` per
UE exactly at `jres.radio_connected_this_slot`. `t311`/`t300`/`t301`/
`t319` (the recovery-side timers, also real values in `calibration-logs/
twotier_startup_gnb.log:17`) are implemented in `sim/join.py`, not
`sim/rlf.py` — deliberately out of the detector's scope
(`docs/wp6-plan.md` Decision 4).

**Radio-layer gating composes by wrapping `BufferView`, never by
changing scheduler code — the pattern to follow for any future
"hide this UE/flow from scheduling" mechanism.** `JoinAwareBufferView`
(`sim/join.py`) is composed outermost over `HarqAwareBufferView`
(`sim/harq.py`) in `driver.py`, masking a radio- or app-gated UE's
backlog to zero with no changes to `scheduler/two_tier.py`,
`sim/baselines/*.py`, or the `BufferView` protocol's call sites. This
works specifically because backlog is externally observable state a
scheduler reads *through* an interface — see the next invariant for the
one kind of state this pattern cannot reach.

**A scheduler's own private per-UE instance state (`TwoTier`'s
`_virtual_q`, `_demand_bps`, `_snr_avg`, etc.) has no external lever —
masking `BufferView` cannot reset it, and that's why
`SchedulerContextReset` exists.** WP-Join commit 7 needed to clear a
UE's fairness/urgency bookkeeping across a re-join, and the
`BufferView`-wrapping pattern above genuinely cannot reach it (it's
never read through the interface scheduler.allocate() receives). The
fix — `scheduler/interfaces.py::SchedulerContextReset`,
`two_tier.py::reset_ue(ue_id, scope, buffers)` — is the one scheduler
file change in this branch since WP0's "zero scheduler changes" rule,
and it is not a precedent for further scheduler edits; it was the
narrowest change that could reach genuinely private state. Reset scope
is path-dependent: `"mac"` (RRC reestablishment) keeps the fairness
ledger, `"full"` (cold attach or an IDLE fallback) clears everything.
Note `JoinState.active_path` never flips from `"reestablish"` even when
a cycle falls back through `JoinPhase.IDLE` — a separate
`join_used_idle_fallback` flag tracks that, so scope selection doesn't
silently read the wrong path.

**TwoTier loses real HARQ bytes under a collapsing channel; PF does
not — a genuine scheduler-differentiating behavior, not a bug in
either.** Under WP-Join's scripted SNR fade (`sim/channel.py`), TwoTier's
urgency-driven ranking keeps attempting grants to a UE whose channel is
actively degrading, producing real `bytes_harq_lost` (~37,500–38,242
bytes across the GT-6.3 demo's arms); PF's achievable-rate-sensitive
ranking backs off sooner and shows 0 bytes lost in every arm. Reproduces
even in the pre-existing `harq_masked_flow_double_grant_count` baseline
(877, unrelated to join/RLF) — this is a standing property of the two
rankings, not something WP-Join introduced.

**Every new independent random draw needs its own seed stream — do not
share an RNG across two different draws.** Precedent: `cqi_seed =
scenario.seed ^ 0xC9C9C9C9`. WP5 found a real bug from *not* following
this: `harq_rng` was one shared stream for both DL and UL outcome draws;
the moment UL started consuming draws too, it perturbed DL's own draw
interleaving order, moving pure-DL flows in `--check` with zero DL-
mechanism change. Fixed with independent `harq_rng_dl`/`harq_rng_ul`
(`scenario.seed ^ 0x48415251` / `... ^ 0xFFFFFFFF`). WP6 added three more
on the same principle (`los_seed`/`shadow_fading_seed`/`blockage_seed`,
`scenario.seed ^ 0x105105` / `^ 0x5FADE5` / `^ 0x424C4F4B`) — no violation
found that time, a clean instance of following the rule rather than a
second bug. WP-Join added three more on the same principle
(`join_cold_seed`/`join_reest_seed`/`join_warm_seed`, `sim/join.py`) — a
third clean instance. When adding any new stochastic mechanism, give it
its own XOR'd seed rather than reusing an existing RNG object, even one
that looks unrelated to what you're adding.

**A guard test written at the moment of a fix pins the thing you were
looking at, not the pipeline around it — live instrumentation is what
catches the recurrence one layer out.** WP9 commit 1b fixed a 25 GB
retention leak in the sweep runner's parent and landed memory tests with
it. Commit 1c then reintroduced the identical leak inside the parallel
worker it added, and **1b's tests stayed green throughout** — they pinned
`m13_projection()` and the parent's retention, and the parent genuinely
was clean; the bug was one layer below, in the code that actually runs the
sweep. What caught it was the run monitor's memory trend plus a `ps`
check, at 20 of 59 cells, not the test suite. The lesson is narrower than
"write guard tests at the moment of the fix" (still true, but it is not
what worked here): **a test proves the helper you just fixed stays fixed;
it does not prove the pipeline that calls it is clean, so long runs need
live resource instrumentation with a kill threshold, not just a green
suite.** Note also that `pkill -f <script>` does not reach
`multiprocessing` **spawn** workers — their argv is the spawn bootstrap —
so stopping a pool leaves orphans holding memory that `pgrep -f` cannot
see; kill the children by PID.

**AND THE CONSEQUENCE IS BROADER THAN "pkill FAILS TO KILL THEM": THEY
CANNOT BE FOUND BY NAME AT ALL.** The same fact about argv means a
*liveness* or *cleanup* check that greps for the script name **reports
clean while the workers are alive** — it is not that the kill misses, it is
that nothing looks. Worse, the search can return a *non-worker* PID (the
shell running the check, whose own command line contains the pattern), so it
simultaneously misses every worker and reports a match. Both halves were
reproduced deliberately on 2026-09-04 while building the check below.

**Measured three times on this machine.** Two orphans from a killed
2-worker attempt held **13.5 GB** and starved the live run to 5.9 GB free
while `g11_campaign`'s own aggregate guard reported the pool healthy
throughout (2026-09-03 audit). An orphan pair — a resource tracker and one
spawn worker — was found alive after **28.6 hours**, idle, from a parent
long gone (2026-09-04). And a first version of the orphan *test* leaked
**15** of them in one pytest run.

**At ~200 MB per worker a forgotten pool is enough on its own to trip the
aggregate ceiling that killed G11 at 21.8 GiB — and it is charged to the
NEW run's footprint**, because that is the only run anyone is watching. A
stale pool therefore looks exactly like a regression in the run just
launched.

**So the check is PRE-LAUNCH and lives in the shared layer.**
`regime_sweep.check_for_orphans()` refuses to start a pool while any
orphaned spawn worker or resource tracker is alive, naming the PIDs and the
`kill` line. `run_cells` calls it, and so does every hand-rolled pool
(`wp9_sweep`, `g11_campaign`, `wp9_part_c`, `g10_rerun`,
`blackout_frequency`). **An orphan is detected by its PARENT'S IDENTITY, not
by `ppid == 1`** — measured, they reparent to `systemd --user`, so a pid-1
test finds none of them. `allow_orphans=True` downgrades it to a warning,
for the case the guard cannot judge: the orphans may belong to another
user's job.

**One trap when writing anything that spawns a pool to test this:** do not
`capture_output` a parent that orphans children. The children inherit the
pipe's write end, so the read blocks until they die — the observation
channel hangs on the thing being observed, which is the same family as the
buffered-stdout case above.

**A test that CONSTRUCTS the precondition it is testing cannot discover
that the precondition never occurs.** The other side of the guard-test
rule above. WP9 §19: the truncated-BSR formats were wired to the wrong
BSR trigger, and all 36 unit tests passed — every one of them handed
`on_ul_grant` a `tb_size`/`filled_bytes` pair chosen to land in the
padding window under test. They correctly verified "given a 2-byte
padding, the report is short-truncated"; none could ask whether a 2-byte
padding ever co-occurs with the trigger the model actually uses. It
didn't, and in a loaded scenario no BSR was assembled at all. **What
caught it was an at-scale run producing an arithmetically impossible
number**, and the recognition is reusable: `144000` was exactly
`6 UEs × 3 LCGs × 8000 slots`. **Ask of any surprising count: does this
factor into the run's own dimensions?** A value equal to an exact product
of the grid's shape is almost never a measurement — it is a saturated
counter or an empty selection wearing one. Note the contrast with this
WP's two earlier instances (the gate's `None`-base selecting 1,710 rows,
the CSV coercion scoring `0.000`): both were wrong but PLAUSIBLE and
survived longer for it. So the lesson is not "impossible numbers get
caught" — it is that a fixture-built precondition needs a separate
at-scale check that the precondition fires at all.

**A SIXTH instance, and its shape is different enough to separate: the
MECHANISM returned nothing and the metric reported SUCCESS.** The previous
five were a *selection* returning nothing — the gate's `None`-base picking
1,710 rows, the CSV coercion scoring `0.000`, the stage-6 analyser's wrong
ramp axis printing "distinct orderings: 0", and so on. WP9's G9 commit 2 is
not that. `sim/scenarios/g9.py`'s GT-6.3 scripted a fade **half the length
of t310**, so `sim/rlf.py` never declared RLF, **zero join events occurred,
and M18/M19 reported instant recovery.** Every number was *correct for the
events that happened* — there simply were none.

**No metric caveat could have caught this**, which is what makes it worth
separating: a caveat qualifies a computed value, and here the value was
right. The catch has to happen one level up, at "did the thing I am
measuring actually occur?".

**A MEASUREMENT CARRIES ITS CONFIGURATION. QUOTING IT OUTSIDE THAT
CONFIGURATION IS A CATEGORY ERROR, NOT AN ESTIMATE.** Not "an approximation
that might be off" — a statement about a different system, which is why the
errors are large and one-directional rather than noisy.

**Three instances, and the third cost a 3× and a 4× error in one week:**

| the measurement | the configuration it was taken in | where it was quoted | error |
|---|---|---|---|
| §13's cost model `4.48 × flows^1.09` | **fleet-builder** compositions | the parametric `factory` mix | 1.23–1.87× low |
| §6.3a's timing table | horizon **4,000**, `record_timeseries` **off** | horizon 20,000 with it **on** | 5–7× low |
| **G11's 2.83 GiB/run** | **N=8**, `record_timeseries=False`, **no** fold, **no** scripted flows | N=4 **with** fold and scripted flows | **~3× low** |
| **G11's "hol samples are 49 % of the residual"** | the same configuration | the real scenario, where it measures **12 %** | **~4× off, and it named the wrong lever** |

**The last two are one week apart and both were mine.** The second is the
more instructive: 49 % made `array("d")` look like the memory lever worth
spending a commit on, and it is worth ~12 % — so the number did not merely
mis-size a budget, **it pointed at the wrong fix.**

**Why "category error" and not "stale number".** A stale number gets closer
as you refine it. This one does not: `record_timeseries=False` and
`record_timeseries="second"` are not near-neighbours on a scale, they are
different runs. There is no error bar that makes the quote defensible,
which is why the mitigation is not "add uncertainty" but **re-measure in
the configuration you are about to use**, or state the configuration
alongside the number so the reader can see the mismatch you could not.

**Mechanically, and it is one line at the point of use:** when quoting a
measured number, name the configuration it came from **in the same
sentence**. If that configuration differs from the one being budgeted, the
number is a lower or upper bound at best, and §16.1.4's "lower bound"
framing is what has repeatedly saved this project from acting on one — the
safety came from the framing, not from the model being right.

**A TEST PROVES A MECHANISM BEHAVES. NOTHING HERE PROVES IT IS REACHED —
and for twelve mechanisms the answer was that it is not.** This is the
run-it-at-scale rule one layer up. That rule asks *did the precondition
occur*; this asks the prior question, *was the code called at all*.

**It is a structural property of how work has been verified in this
project, not a list of oversights.** The 2026-09-03 audit found **twelve**
instances, and the recurring shape is identical: a mechanism is built,
unit-tested against its own inputs, green in the suite, and either has no
non-test caller or emits nothing that would show it ran.

| the mechanism | how it is unreachable / unobservable |
|---|---|
| WP6 blockage (`sim/blockage.py`, `UEConfig.blockage`) | no scenario, sweep or YAML key sets it; `is_blocked()` has no non-test caller |
| `sync_group` / `phase_offset_ms`, `aggressor_multiplier` | set only in `sim/tests/test_traffic.py` |
| `JoinConfig.app_restart_*`, `pdu_session_*` | never set: both phases last **0 slots in every G9 result** |
| `RlfDetectorConfig` | hardcoded in the driver; unreachable from `run()` |
| four `UlAccessModel` knobs incl. `sr_report_floor_bytes` | not passed by the driver |
| `FlowConfig.survival_time_ms` | never non-zero, so **M14 has never measured what it defines** |
| `slice_id` | never set, and no scheduler reads it |
| five driver counters (HARQ exhaustion, RLF, double-grant) | emitted into `summary`, dropped by `from_summary` |
| `harq_masked_flow_double_grant_count` | claimed as the standing Phase-2 guard; reaches no record, no corpus, no test |
| TwoTier's UL floor (Tier 1.5, ~200 lines) | OAI's counters not ported; activation unknowable |
| `analyse_stage5.py`'s `TransientExclusionError` | the guard against a bad aggregate has no caller outside its test |
| G11 commit 7's drift detector | commit 8 never wired its counters in |

**The two failure modes are different and both are here.** *Unreachable*:
no caller, so the code never runs and the tests describe a hypothetical.
*Unobservable*: the code runs and emits nothing, so a result cannot be
distinguished from the mechanism never firing — which is exactly the sixth
empty-selection instance, arrived at from the other direction.

**Why nobody noticed for twelve of them.** Every one has a green test, and a
green test is the signal this project trusts. Coverage answers *is this code
correct when called*; nothing in the suite answers *is it called*. The
G11 drift detector is the cleanest case: it was built, tested, merged, and
its absence was discovered only when someone wrote the scorer that needed
its output — i.e. by an unrelated task, not by any check.

**Mechanically, at the moment a mechanism lands, ask two questions and
write the answers down:**

1. **Who calls this outside a test?** If the answer is "nothing yet", say so
   in the docstring with the commit that will, or accept it is dormant and
   label it so — `sim/power.py` and `sim/olla.py` do this correctly and are
   not part of the problem.
2. **What in a run's output would differ if it never fired?** If the answer
   is "nothing", the mechanism is unfalsifiable in situ. Emit a counter, and
   make sure the counter survives into whatever the campaign persists — five
   of the twelve above emit one that `RunRecord.from_summary` then drops.

**The cheap check for an existing mechanism is one grep**, and it is worth
running before quoting any mechanism as active: `grep -rn <name> --include=*.py . | grep -v tests/`.
If every hit is a test or a comment, the mechanism is not part of any
result this project has published.

**BEFORE CITING A CHECK AS PASSING, ESTABLISH IT COULD HAVE FAILED.** The
same shape as the journal's dynamic-range rule (`prediction-journal.md`,
third form rule) but applied to a **verification step** rather than to an
expectation — and worse than J5's case in one specific way: **J5 was an
unfalsifiable prediction that was never scored against anything; this was
an unfalsifiable check ALREADY CITED AS EVIDENCE THAT A COMMIT WAS SAFE.**

The instance. `docs/wp9-g11-plan.md` §10 registered, for the M09 hoist,
*"`--check` must not move"*. It did not move — and **it could not**:
`regression/baseline_studies_1_3.json` stores `RunRecord`s (`flows`,
`system`, `timeseries_*`, `join_events`) and **no scorecard output at
all**, so a change to `Scorecard._m09_per_second_jain` is structurally
invisible to it. The green `--check` was **zero evidence** and was written
into the plan as the commit's verification.

**Why this is its own class and not just "pick a better check".** A failing
check is information; a passing one is information *only if failure was
reachable*. The three fault shapes are distinct and the third is the one
that hides:

| | what happens | how it is caught |
|---|---|---|
| the check fails | you learn something | trivially |
| the check passes and could have failed | you learn something | trivially |
| **the check passes and could NOT have failed** | **you learn nothing, and believe you learned something** | **only by asking what would make it fail** |

**The mechanical form, and it costs one sentence per check:** name the input
the check reads and the artefact the change touches, and confirm they
intersect. `--check` reads `RunRecord`s; the hoist touched
`sim/scorecard.py`; they do not intersect; therefore the check is blind.
That is the whole test, and it is the same question §33.3 asks of an
instrument and §35.4 asks of a control.

**This is a recurring shape in this project, now with three instances at
three levels** — an *expectation* that could not be contradicted (J5), a
*control* that read a different population than the claim (G12's clean
ramp bottom, which checks M13's GBR classes while clause 4 is about a
Delay-class flow), and now a *regression check* structurally insensitive to
the layer being changed. **Treat "the check passed" as a claim requiring
the same decomposition as any other aggregate: what did it look at, what
did the change touch, are they the same set?**

**AND A CHECK CAN FAIL IN PRINCIPLE YET NOT AT THE LEVEL THE FAILURE
HAPPENS — establish the SCOPE a check operates at, not only that it can
fail.** The entry above asks whether a check *can* fail. This asks a second
question that the first does not reach: **can it fail at the level where
the thing goes wrong?** A guard aimed one level away from its failure mode
is as silent as one that cannot fail at all, and it is harder to spot,
because it demonstrably works — on the wrong quantity.

**Three instances in one week, at three different layers**, which is why
this is its own entry rather than an example of the one above:

| layer | the check | why it could not fire |
|---|---|---|
| **expectation** | J5's ΔM02 on neighbours | the statistic was floored at 0 in both conditions — no *value* could contradict it |
| **verification** | commit 1's `--check` on the M09 hoist | the corpus stores `RunRecord`s, the change was in `sim/scorecard.py` — wrong *layer* |
| **runtime guard** | the 22 GiB per-process memory watchdog | at 2.83 GiB/run no single worker approaches it, while the machine exhausts at ~8 concurrent runs — wrong *aggregation level* |

**The generalised form covers all three: before relying on any check,
establish that the level it operates at is the level the failure occurs
at.** Value, layer, scope — a check has to intersect the failure in all
three or it is decoration.

**The watchdog case is the sharpest because the guard was demonstrably
working.** It had already killed a real run at 21.8 GiB, so there was
direct evidence it fired — evidence that says nothing whatever about the
*parallel* failure mode it was about to be pointed at. **"This guard has
fired before" is not evidence it can fire against the next thing**, and a
guard reused across a change of scale needs its scope re-derived, not its
history cited.

**Mechanically:** name the failure you are guarding against, name the level
it manifests at (a value, a layer, an aggregate), and confirm the guard
observes *that* level. For memory: per-process guards catch per-process
leaks; machine exhaustion across N workers needs an aggregate threshold, or
a per-worker one derived as `budget ÷ workers`.

**CONFIRMED BY MEASUREMENT ONE COMMIT AFTER THE ARGUMENT WAS MADE.** G11's
runner replaced the per-process watchdog with an aggregate one on exactly
this reasoning, and the first real-horizon run tripped it:

```
00:57:45 workers=4 total_rss=20219MB avail=4001MB
00:57:45 KILL pid=1517277 (9249MB) -- pool total 20219MB exceeded budget 20000MB
```

**Largest worker 9,249 MB against a 22 GiB per-process threshold, with
4.0 GB of machine memory left.** The old guard could not have fired; the
new one turned an OOM into a measurement. **The argument was made from
arithmetic before any run — 2.83 GiB × 16 workers against 24 GiB — and the
run confirmed it**, which is the cheap direction: a scope argument costs a
sentence, and discovering it from a dead 5-hour job costs the job.

**So the standing rule — run it at scale and ask whether the precondition
occurs at all — applies to MECHANISMS FIRING, not only to rows selecting.**

**And "at all" is too weak — assert the EXPECTED COUNT.** The G9 campaign
implemented this rule as a non-zero check and it passed on every run, while
TwoTier recorded **3.8 of 10 scripted warm restarts and 1.0 of 5 cold
cycles**. *"Did the mechanism fire at all"* is a weaker question than *"did
it fire as often as the scenario specifies"*, **and the gap between them is
exactly where a PARTIALLY degenerate run hides.**

**A partially-degenerate run is not a smaller sample of the same thing.**
The events that survive are **self-selected**, so an arm with fewer events
is measuring a different population, and comparing it to a full arm
compares two things. Derive the expected count from the schedule (never
restate it) and assert equality.

**AND THE COUNT IS STILL NOT ENOUGH — assert COMPLETIONS too.** Two
corrections from re-running that campaign (`docs/wp9-plan.md` §34.5a),
kept because the second is a stronger version of this whole invariant.

*First, the mechanism this entry used to name is refuted.* It read *"the
ones whose predecessor finished before the next was scheduled"*. That
overlap never happens: every completed warm handshake landed 21–1,086
slots after its trigger against a **1,600-slot** period, and §34.5's own
table already showed a maximum of 851 — its evidence contradicted its
mechanism on the page. What actually occurs is a **terminal stall**: the
handshake never completes, and every later scripted event is
consumed-and-discarded rather than deferred.

*Second, and this is the transferable part:* **3.8 of 10 and 1.0 of 5
count events RECORDED. The count of cold attaches COMPLETED is 0 of 50** —
on every seed, against 50 of 50 on both other arms. **An arm can register
its full scheduled count and complete none of them**, and a count-only
assertion passes on that while the recovery metrics report **0.0 ms —
instant recovery — for a UE that never came back.** *Firing* and
*finishing* are different questions. Assert the expected count **and** that
nothing failed to complete (M18 already computes `n_never_completed`).

**The shape to carry: a guard added in response to a degenerate run can
itself be degenerate.** This campaign's count assertion was written to
close exactly this hole and closed only half of it — the same
one-level-short failure as the under-decomposition in `docs/wp9-plan.md`
§28.1.

**The concrete diagnosis, kept verbatim because a later reader will hit
this exact trap: depth arms t310, duration expires it.** Two identically
named `rlf_snr_floor_db` fields exist on *different objects* —
`JoinConfig` and `RlfDetectorConfig` — and **`sim/driver.py` constructs
`RlfDetectorConfig()`, so that is the one that matters**; setting
`JoinConfig`'s does nothing for detection. A fade deep enough to cross the
floor only *arms* the n310/t310 dwell. **t310 is 2,000 ms — 8,000 slots at
numerology 2 — and the fade has to outlast it**, or the dwell re-arms and
nothing is ever declared.

**An empty or unchanging output file is evidence about the FILE, not about
the process — check process state directly before concluding anything
about liveness.** Twice in WP9 a *reading* of instrumentation produced a
false conclusion while the run itself was fine or already finished: a
`pgrep -f` match on a leftover shell made a dead sweep look alive for a
full monitor tick, and a block-buffered `python -c` stdout made a probe
that had completed normally look stalled at 615 s (it was killed for it).
Both are the same class — **the observation channel lied, not the run** —
and both have the same mitigation: `ps` the actual PID and look at CPU
time and RSS, rather than trusting a proxy. Related and already recorded
above: `pgrep -f`/`pkill -f` on a command-line pattern misses
`multiprocessing` **spawn** workers (their argv is the bootstrap), matches
any `watch`/monitor whose own command line contains the pattern, and will
match the *shell running the check itself* — which killed a relaunch
mid-session when a cleanup loop matched its own command line.

**A THIRD instance, and it generalises the family past liveness: a NAMED
ALIAS IS A CLAIM ABOUT TOPOLOGY, and claims about topology get verified
against `ip addr`, not against the config that makes them.** Moving to the
desktop, `~/.ssh/config` carried `Host lab → HostName 172.25.70.124, User
smartpc`, and it read exactly like the route to the other machine. It is
not. **172.25.70.124 is the desktop's own `wlp7s0` address** (`ip -4 addr`),
and **`smartpc` is not a user on the desktop** (`id smartpc` → no such
user). `ssh lab` is a loopback to a nonexistent account; it fails for
everyone, always, and the failure it returns —
`Permission denied (publickey,password)` — **looks exactly like a missing
credential**, which is the wrong diagnosis and the expensive one. It cost
two investigations before `hostname -I` settled it, and would have cost a
third.

**Why this belongs beside the other two rather than in a networking note.**
The `pgrep` and buffered-stdout cases are an observation channel asserting
a *process state* that was not real; this is an observation channel
asserting a *route* that never existed. Same shape, same mitigation — go to
the primary source (`ps` for state, `ip addr` for topology) instead of the
proxy that is easier to read.

**And the corollary that actually matters here: check DIRECTION before
concluding you lack access.** The desktop has no private key at all, while
its `authorized_keys` holds two keys commented `laptop` — so the trust is
**one-way, laptop → desktop**, and no amount of retrying from the desktop
can pull anything. The transfer had to be *pushed* from the other side.
**"I cannot authenticate" and "the trust runs the other way" produce the
same error message and have completely different fixes**, and only the
second one is actionable.

**A value crossing a serialization boundary must be coerced back to its
declared type at that boundary, and any aggregate over a selection must
assert the selection is non-empty and the expected size.** WP9's stage-1
verdict was recomputed from a CSV; boolean axis levels came back as the
string `'True'` and never matched the bool `True`, so the `shared_lcg` and
`bg` cells silently selected **zero** rows. **What made this one catchable
is that it produced an impossible number rather than a plausible one** — a
score of exactly `0.000` is the signature of an empty selection, not of a
real result. The two earlier versions of the same class of bug in this WP
(the gate's `None`-base contamination selecting 1,710 rows; the "22-record"
corpus) both produced plausible numbers and survived longer as a result.
Do not rely on implausibility: coerce at the boundary against the declared
levels, and assert cell sizes (`len(cell) == n_arms * n_seeds`) before
scoring anything.

**Any count that describes a structure must be computed from that
structure at the point of use, never restated in prose.** Three instances
in this project, each of which cost real confusion: the regression corpus
was described as "22-record" in `README.md` §9 and this file while
`_cases()` built 20 (WP9's fix commit); `docs/wp9-plan.md` §6.3's per-cell
timing table was carried as prose and was wrong by 5-7x (§6.3a); and the
stage-1 grid was described as 56 cells while `EXCURSIONS` summed to 59.
The third was caught **only because the runner printed its own count and
disagreed with the document** — nothing else would have surfaced it. A
count in prose is a claim about code that drifts silently the moment the
code changes, and unlike a wrong citation it does not point anywhere that
would reveal the error. Derive it (`len(_cases())`, `sum(len(v) for v in
EXCURSIONS.values())`), or print it from the thing that produces it.
**A fourth instance, and its LOCATION is the new part: it was in TEST
code.** `sim/tests/test_scorecard.py`'s caveat test hard-listed the
caveat-carrying metric ids (`("M01","M02","M14","M15","M19")`) instead of
deriving them from the panel; WP9 Step 2 added a caveat to M20 and the
literal list was wrong. The generalised rule is unchanged, but **the blast
radius differs by where the restated count lives.** The first three
instances were a document, a plan and an analysis script — all of which
fail *loudly and visibly*, by disagreeing with something. **A test that
restates a count fails in the direction of PASSING**: had the new metric
carried no caveat, the stale list would have kept passing while silently
checking less than it claimed to. That is worse precisely because a test is
the thing meant to catch this class of drift. Derive the set inside the
test (`{m["id"] for m in load_panel()["metrics"] if m.get("caveats")}`).
**A fifth instance, and it is in the BUDGETING path rather than the
measurement path — which is why it belongs beside the empty-selection
family rather than inside it.** WP9's G12 campaign runner has a
`--time-cell` mode that times one cell and extrapolates to the grid. The
flag also truncates the cell list to one entry so only that cell runs, and
the extrapolation was computed from `len(kept)` *after* the truncation, so
it reported **"22 min for the grid"** when the real grid was three
scoreable cells and 64 min. A list silently reduced to one element and then
summed over: structurally the same as the empty selection, the one-element
"order", and the 1,710-row `None`-base.

**What is new is the failure mode, and it is worth separating because the
mitigation differs.** Every earlier instance corrupts a RESULT — a wrong
claim gets published and has to be retracted. **A wrong budget publishes
nothing.** It fails by making someone launch a run they abandon, or decline
work that was actually affordable, or size a grid against a cost that was
never real. There is no artefact to check it against afterwards, and no
`--check` that moves. So the guard cannot be "verify the number later"; it
has to be **derive the extrapolation from the population BEFORE any mode
flag narrows it**, and say which population it is extrapolating over. The
fix was one line — capture `n_real_cells` before the truncation — and it is
only findable by reading the code, never by reading the output, because
"22 min" is exactly as plausible as "64 min".

**DECOMPOSE BEFORE ATTRIBUTING: for any aggregate about a protected set,
ask what rows actually entered the sum before quoting it.** Not an instinct
— a check with a definite question, because it caught **four** errors in a
single WP9 item and the shape was identical every time: *reading an
aggregate as a statement about the population it is NAMED for rather than
the one it is COMPUTED OVER.*

1. **M03's worst liveness gap** is a max over *every* flow
   (`sim/scorecard.py:220`), so a saturating background aggressor's own
   starvation won the contest and was scored as fleet damage — inverting
   the causal direction, since a QoS-aware scheduler starves such a flood
   *by design* (`docs/wp9-plan.md` §24.2).
2. **The same statistic's per-seed deltas** were summarised by a
   mean-of-ratios that read +136.84 % while the median read −0.22 % and
   21/40 seeds improved (§25.4, §27.1).
3. **M02's PDB-violation rate** byte-weights over *every* flow, so its
   ~24-point rise was the aggressor's own bytes; the protected-fleet delta
   is ≈0 on all three arms (§28.1). **This one was asserted immediately
   after catching (1)** — the tool was built and in hand and simply was not
   pointed at the second metric.
4. **M05's "30/40 seeds under bound"** is a worst-*flow* scalar, so the
   count is over seeds, not over flows: Reservation's 33 breaches came from
   **2 distinct flows** and TwoTier's 35 from 4, one accounting for 30
   (§29). Thirty failures and one chronically-broken flow look identical in
   that number.

**The check, stated so it is mechanical:** before quoting any aggregate —
max, mean, rate, count of breaches — name (a) the rows it sums over, (b)
the rows the *claim* is about, and (c) whether they are the same set. If
they differ, the aggregate does not support the claim no matter how large
the effect or how tight the interval. **Asking it in advance is cheap;
instance (4) was predicted before the data arrived and cost nothing, while
instances (1)–(3) each cost a wrong published conclusion.**

**Spec/hardware-derived numeric tables get transcribed from the actual
source text, never reconstructed from memory or re-derived by formula —
this applies to any such table, not just BSR's.** `sim/bsr.py`'s
`NR_SHORT_BSR_TABLE`/`NR_LONG_BSR_TABLE` are transcribed from
`oai-branches/two-tier/nr_mac_common.c` (see that file's own citation for
the exact commit) and checked byte-for-byte against it by `sim/tests/
test_bsr.py` on every test run — 38.321 tabulates rather than publishing
a generating formula, so "reconstructing" a table by formula is exactly
the same silent-wrongness risk as recalling it from memory. **Confirmed
as a general rule, not a BSR-specific one, by WP6**: this repo's own docs
had mis-cited TR 38.901's InF sub-scenario naming (SL/DL/SH/HH, omitting
InF-DH) from a session's recollection; the fix was fetching the actual
ATIS transposition of the spec and transcribing `sim/pathloss.py`'s path-
loss/LOS-probability tables from `pdftotext`-extracted spec text, cited
by table and page, not from memory. If a future change touches any
spec-derived table (BSR, path loss, or otherwise), re-verify against the
real source, not by re-deriving it.

**The vendored `oai-branches/` subset is a convenience copy, not the
evidence base.** When a constant looks sourceless from the vendored
`.c` files alone, check the full OAI checkout
(`~/Documents/artpark_projects/Oai_Ran_QoS_Supported_MultiDRB`) and
`calibration-logs/`'s own referenced config files before treating it
as unsourced or inventing a value. Found scoping Phase 2 reservation
commit 4: `nrmac->min_grant_prb` (UL's follower-budget floor) looked
sourceless from the four vendored `.c` files — no assignment site
anywhere in them. The full checkout's `MACRLC_nr_paramdef.h` config-
parser default, the exact deployed `.conf` `calibration-logs/
twotier_startup_gnb.log`'s own `CMDLINE` cites, and 486/486 empirical
`NPRB 5` lines in that log together confirmed the value as a deliberate
deployment/operator choice for the calibration campaign (made so no UE
is starved of a grant and BSRs keep being reported) — not a config
default that happened to go unoverridden, and not an invented number.

**A forward-looking note left in this port's own docs (a port-map row,
a module docstring) is a hypothesis for the commit that takes it up to
verify, not an instruction it should execute unchecked.** Two such notes
have been checked so far, when their own commit arrived, and both were
wrong — two different failure modes, not the same one twice. `_dl_stamp`
(Phase 2 two-tier commit 3a) was a wrong *citation*: it pointed at
something readable, and pointed at the wrong lines. Port-map row 46
(Phase 2 two-tier commit 4b) was a wrong *plan*: commit 3 wrote "reused
directly here, not re-derived" as forward guidance for a consumption it
had not yet verified — `guaranteed_bytes + be_bytes` — and commit 4b
found the two quantities genuinely differ from what `B_eff` actually
needed (`ul_total_target_bytes`, a third accumulator, excludes the
GBR-LCG overflow term `be_bytes` includes). A citation points at code
that already exists to be checked; a plan asserts something about code
not yet written, and code not yet written can still turn out to want
something different once it's actually read against ground truth. Both
are wrong in the same direction — optimistic — but for different
reasons, so don't treat "the note has always been right before" as
evidence for either kind. When a future commit picks up a note like
this, re-derive or re-read against ground truth directly; do not port
the note's own claim on the strength of it having been written down.
**A third kind, added by WP9: a wrong *argument* about code that already
existed and could have been read at the time.** WP9 commit 0b concluded
that `bytes_reported` could not stall at 0 over live backlog, on the
grounds that three re-arming paths bound the state — the third being
"assembly on any grant once `pending` is set", which assumed
`sim/ul_access.py` always eventually supplies that grant. It did not:
the SR was gated on an empty→non-empty transition, so a never-emptying
flow stalled permanently (`docs/wp9-plan.md` §8b/§8c, port-map row 79).
0b's *headline* answer survived — the per-LCG array really is not the
route — but its reasoning was checkable against code that already
existed, and was not checked. So this invariant is not only about notes
describing code not yet written: **an argument about existing code is
also a hypothesis until someone runs it.** The cheap discriminator that
would have caught it is the one that eventually did — a per-slot trace,
not more reading.
**A fourth kind, added by WP9 §20: a wrong *diagnosis* — an inference
about BEHAVIOUR that was never run, not even in counterfactual.** The
first three kinds are all about code that existed and could have been
read; a wrong diagnosis cannot be caught by reading anything, because the
thing it is wrong about is what a mechanism would DO. §19.5 concluded that
truncated BSR could not fire for want of TB-size quantisation and named it
as what would close G2 — and README §7, `docs/wp9-regime-map.md`'s G2 row
and a commit message all carried that forward. It is wrong: replaying
every UL grant of a real run through OAI's own `nr_find_nb_rb`/
`nr_compute_tbs` (`scripts/tbs_counterfactual.py`) leaves the padding
distribution **completely unchanged** at the load the claim was measured
at — 13,214 of 13,214 grants at padding 0 before and after — and *reduces*
lawful Truncated BSRs at light load, 5 → 4. **This is the first of the
four caught BEFORE any code was written**, and what caught it is the same
rule written after correction one of the previous item: *run it at scale
and ask whether the precondition occurs at all.* Applying that rule to a
forward NOTE rather than to a landed mechanism is the transferable part,
and it is far and away the cheapest place to apply it — a counterfactual
probe is hours; discovering it after a mechanism ships is a work package.
**The positive result is reusable and is recorded so the next person does
not re-run the probe** (`docs/wp9-plan.md` §20.1): the blocker for the
BSR/SR desync is the **magnitude of the gNB's BSR error at grant time**
(median 12,194–13,387 bytes on grants with ≥2 LCGs backlogged) against a
truncation window **2–5 bytes** wide — TB granularity is nowhere near the
operative scale. And the shape any future attempt must defeat is an
**anti-correlation**: load a UE until several LCGs are backlogged and its
grants become PRB-limited, and a PRB-limited grant is filled exactly
(padding 0 at any TB size); unload it until the grant has spare room and
all but one LCG drains, at which point 38.321 §5.4.5 mandates a *Short*
BSR rather than a truncated one.

## Rules for the WP0 machinery

**M18/M19 (WP-Join) are the panel's first additions since WP0
pre-registration** — the rules below still apply to them unchanged; the
panel isn't a fixed WP0 artifact, it's append-only under the same rules.

**`config/metric_panel.yml` is pre-registered.** Adding a metric is fine.
Removing one, or changing a definition to something that happens to separate
two schedulers better, defeats the multiplicity guard. Every metric keeps a
`status` of `ok` / `proxy` / `pending` and a `requires` naming the WP that
promotes it — a WP that claimed to unlock a metric but left its status
unchanged is a finding, not a detail.

**A `pending` metric emits a row with `value=None` and a reason.** Never
omit it. An omitted row is indistinguishable from a forgotten one.

**Do not `--capture` a new regression baseline to make a diff go away.**
Re-baseline only when a change is *intended* to move the numbers, and say so
in the commit message. `--check` failing is information.

**Check `requires:` in the file, not from memory, before assuming which WP
gates a metric.** M04's `requires` has always named WP7 (discrete message
model) + `record_timeseries=True`, never WP3 — a plausible-sounding
assumption that WP3 gates it (it's BSR-adjacent) is wrong. As of WP3
landing: M01 stays `proxy` (still needs WP7), M02 flipped to `ok` (WP3's
third commit), M04 unchanged. WP7 then flipped M01/M03/M05/M06/M14/M15/M17
to `ok` — but **deliberately left M04 as `proxy`**, even though WP7's
message ledger gives it everything an exact per-message-miss count would
need. Not an oversight: fixing M04 exactly is "close to free" but was kept
out of every WP7 commit on purpose, since bundling a refinement of an
already-shipped metric into an unrelated commit's diff defeats the
attribution the one-fidelity-change-per-commit rule exists for
(`docs/wp7-plan.md`, "On M04"). Still open, own commit, whenever taken up.

**If a WP predicts which regression metrics will move and how, check the
prediction against the actual `--check` output and record the misses, not
just the hits.** WP4 predicted M11/M12 up and GBR p50 flat; the actual
output showed M11 100% opposite, M12 mostly opposite, and p50 moved in
*more* cases than the higher percentiles it was supposed to stay flat
against (README §8). A prediction exercise that only gets cited when it's
right isn't a prediction exercise.

## End-of-WP checklist

Before calling a WP done: run the full suite + `--check`; if predictions
were made, score them (see above). Then do a judgment-calls review of the
WP's own diff — reread it looking for undocumented decisions or silent
bugs, the same pass that caught WP3's real M02 denominator bug (`c7baba9`)
and an unrecorded open decision (`86c54b9`). Treat this as a standing step
for every WP, not an opportunistic one.

## Known issues (flagged deliberately, do not fix as a drive-by)

- `sim/metrics.py::record_hol_delay` drops zero-delay samples, biasing every
  latency percentile pessimistic at low load. Left as-is so the regression
  baseline matches the published numbers. Fixing it is its own commit with
  its own regression diff.
- `average_agg_level` is hardcoded to 4 in the OAI DL scheduler
  (`// TODO find a better estimation`). Decide deliberately whether the sim
  models it fixed or SNR-dependent.
- Crumb fraction (grants ≤150 bytes) on `factory_robots_scenario` @ 1.0×
  with TwoTier moved from WP3's 0.09% to WP4's **4.4503%** (151/3393 UL
  grants) after landing the real SR path — still ~11x short of hardware's
  48-52%, and the crumbs' own size profile got *less* accurate in the
  process (79 bytes, inside hardware's 72-107 range → 146 bytes, outside
  it, now dominated by the SR path's fixed report floor rather than an
  organic collapse). Not chased further; see README §8 for the full
  writeup. **The `sched_ul_bytes`/k2-HARQ omission is now largely ruled
  out as the gap's explanation, not still an open candidate**: WP5 commit
  4b landed the real k2/HARQ pipelining this item asked for, and crumb
  fraction moved to **4.9558%** (157/3168) — **+0.51 percentage points of
  the ~45-point gap to hardware's 48-52%.** (First measured at 5.1233%
  under a bug WP5's own end-of-WP review found and fixed — `sim/bsr.py::
  on_ul_grant` was decrementing `estimated_ul_buffer` at grant/attempt
  time instead of confirmed-receipt time, `docs/wp5-plan.md` — corrected
  here to the post-fix figure, not the first one measured.) A second,
  separate candidate this item's own text didn't previously distinguish:
  real hardware ALSO decrements `sched_ul_bytes` itself at confirmed-
  receipt time (a second decrement, on top of the `+= tb_size` grant-time
  credit) once a real k2 gap exists — deliberately not built (`sim/
  bsr.py::on_ul_grant`'s docstring), since it's a new mechanism, not a bug
  fix, and needs its own commit. Revisit with WP9's wider sweep for what
  the remaining gap is.
- H5 (`p5g-sim-plan.md` line 338, two-tier degrades as flows-per-LCG
  grows) is not demonstrable on any current scenario — WP3's default 5QI→
  LCG mapping deliberately separates QoS classes into different LCGs, so
  no scenario's multi-UL-flow UEs share one. Needs a small follow-up
  scenario (README §8) before H5 can be tested in Phase 3.
- `FlowConfig.aggressor_multiplier` scales an `xr_video` flow's fragments
  *after* `sim/traffic.py::_gen_xr_video` has already fragmented the frame
  to fit `fragment_bytes` — a scaled fragment can end up larger than the
  configured `fragment_bytes`, silently breaking that generator's own
  "grounded in a real physical constant" MTU-cap claim. Found in WP7's
  end-of-WP review; untested (no scenario combines the two). Not fixed —
  a real fix means scaling `avg_bytes` before fragmentation, which breaks
  the multiplier's "uniform regardless of kind" design and needs its own
  decision. Workaround until then: scale `traffic_params["avg_bytes"]`
  directly for an `xr_video` aggressor instead of using
  `aggressor_multiplier`.
- M19's `hol_delay <= pdb_ms` pass check is blind to a flow being
  catastrophically PDB-violated via continuous drops: `sim/buffer.py::
  expire()` keeps evicting the queue head before it can age past
  `pdb_ms`, so a flow that never delivers anything can still read as
  "green." Recorded as a `caveats:` entry on M19's panel row rather than
  fixed (WP-Join commit 8) — a distinct mechanism change, not a
  metric-definition tweak.
- `sim/traffic.py`'s `adaptive` source kind is distorted by WP-Join
  commit 6's `suppressed_ues` gate: the AIMD backoff logic it uses isn't
  aware a UE can be source-gated mid-cycle, so a suppressed then
  un-suppressed `adaptive` flow's rate state may not reflect what real
  AIMD would do across that gap. Flagged in `docs/wp-join-plan.md` §6
  item 5; no scenario currently combines the two, so untested.

## Style

- Comments explain *why*, especially why something deviates from the obvious.
  A comment saying what the line does is noise.
- Docstrings on new modules state what the module is for and what it must not
  depend on.
- No new runtime dependencies. Current set: numpy, cvxpy, matplotlib, pyyaml,
  scipy (+ solvers). Stdlib `csv`/`json` over pandas.
- Type hints on new public functions.
