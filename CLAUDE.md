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
  M01/M03/M05/M06/M14/M15/M17). The scoring layer. `scorecard.py` must not
  import `sim/driver.py` or `sim/config.py`; it consumes `RunRecord` only,
  so it can score records from any producer.
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
- `config/metric_panel.yml` — the pre-registered metric panel. See rules below.
- `scheduler/` — `two_tier.py`, `tier1.py`, `link.py`, `flow.py`.
  `flow.py::FlowConfig.lcg` self-resolves from 5QI via `__post_init__` — see
  invariants below.
- `sim/baselines/` — PF, RoundRobin, Gradient. The Phase 1 comparison arms.
- `oai-branches/{two-tier,reservation}/` — read-only verified OAI C source.
  Ground truth for Phase 2. Same filenames in both dirs with *different*
  contents; never merge or dedupe them. `two-tier/nr_mac_common.c` and
  `nr_ue_scheduler.c` (WP3) are vendored from a *different* upstream
  directory (`NR_MAC_COMMON`/`NR_MAC_UE`, not `NR_MAC_gNB`) than the rest —
  see `oai-branches/README.md` for per-file commit provenance.
- `regression/baseline_studies_1_3.json` — 22-record numeric snapshot.
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

**Do not add SPS / Configured Grant to the schedulers.** `main`'s
`scheduler/two_tier.py` has it (`_SPSReservation`, `_allocate_sps`); the real
hardware scheduler defers SPS to a Phase 2 that was never built. The Python
model must match the deployed scheduler, not exceed it.

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
identical. Not a bug, and not a Tier-1 boundary leak — don't "fix" it by
splitting into per-direction rates — but expect PF-arm DL drift whenever a
UL-only change lands, and check `pf.py` before assuming a DL mismatch
means something crossed a scheduler boundary it shouldn't have.

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
just being a suboptimal scheduling choice. `scheduler/two_tier.py`'s SPS
path defeats this non-destructively by pooling backlog across a UE's
SPS-eligible flows before masking is applied (README §8,
`harq_masked_flow_double_grant_count`) — that's a flagged, deliberately
unfixed limitation of SPS specifically (Phase-2-doomed per this doc's own
SPS rule above), not evidence that masking itself can be relaxed
elsewhere.

**Every new independent random draw needs its own seed stream — do not
share an RNG across two different draws.** Precedent: `cqi_seed =
scenario.seed ^ 0xC9C9C9C9`. WP5 found a real bug from *not* following
this: `harq_rng` was one shared stream for both DL and UL outcome draws;
the moment UL started consuming draws too, it perturbed DL's own draw
interleaving order, moving pure-DL flows in `--check` with zero DL-
mechanism change. Fixed with independent `harq_rng_dl`/`harq_rng_ul`
(`scenario.seed ^ 0x48415251` / `... ^ 0xFFFFFFFF`). When adding any new
stochastic mechanism, give it its own XOR'd seed rather than reusing an
existing RNG object, even one that looks unrelated to what you're adding.

**BSR quantisation tables come from vendored OAI source, not the 3GPP
spec text or memory.** `sim/bsr.py`'s `NR_SHORT_BSR_TABLE`/
`NR_LONG_BSR_TABLE` are transcribed from `oai-branches/two-tier/
nr_mac_common.c` (see that file's own citation for the exact commit) and
checked byte-for-byte against it by `sim/tests/test_bsr.py` on every test
run. If a future change touches these tables, re-verify against that
vendored file, not by re-deriving from the spec — 38.321 tabulates rather
than publishing a generating formula, so "reconstructing" a table by
formula is exactly the same silent-wrongness risk as recalling it from
memory.

## Rules for the WP0 machinery

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

## Style

- Comments explain *why*, especially why something deviates from the obvious.
  A comment saying what the line does is noise.
- Docstrings on new modules state what the module is for and what it must not
  depend on.
- No new runtime dependencies. Current set: numpy, cvxpy, matplotlib, pyyaml,
  scipy (+ solvers). Stdlib `csv`/`json` over pandas.
- Type hints on new public functions.
