# WP7 plan — factory traffic generators and the discrete message model

**Provenance.** The original 10-commit breakdown was agreed in a conversation
that this session does not have access to; it was never written to disk and
is now lost. This document reconstructs it from what commits 1-2 actually
did (`git show ef121b3 c904e92`), `config/metric_panel.yml`'s `requires:`
fields, `docs/p5g-sim-plan.md` §9's WP7 spec, and README.md §4/§6/§7. Treat
the commit boundaries and count below as this reconstruction's judgment
call, not a recovered fact — the five target metrics and their `requires:`
values are the part actually pinned down by files on disk; the grouping into
commits 3-9 is a proposal to review, not a memory. (Originally sketched as
commits 3-10; commit 10 was dropped — see the RTSP/TCP decision below.)

This file is the artifact that should survive the *next* session restart.
Update it as commits land; don't let it drift back out of sync with reality.

## Landed

- **Commit 1/10** (`ef121b3`) — `sim/messages.py` (`Message`,
  `MessageCompletion`, `MessageLedger`). `BufferModel.enqueue()` gained an
  optional `message=` kwarg; `drain()`/`expire()` track completion as a side
  effect. `TrafficModel` gained an optional `ledger=` that tags each
  generated arrival. `driver.py` wires a `MessageLedger` through and collects
  completions but does not yet feed them anywhere. Every existing call site
  omits the new params and is bit-for-bit unaffected. `Message` already
  carries `frame_id: int | None` and `role: str = "data"` fields that
  commit 1 doesn't use — placed ahead of need for the XR (§ M05/M06/M17) and
  MAVLink (§ M03) work below.
- **Commit 2/10** (`c904e92`) — consumes commit 1's ledger.
  `message_latency_percentiles_ms()` computes true per-message completion
  latency; `driver.py` merges it into the summary dict alongside the
  existing head-of-line proxy (both kept, nothing overwritten);
  `RunRecord.FlowRecord` gained `delay_p50/95/98/99_ms` + `message_count`
  (`None` on pre-WP7 records); `scorecard.py`'s M01/M15 report `status="ok"`
  from the true fields via `_has_true_latency()` (every flow in the record
  has a non-`None` `message_count`), falling back to the old proxy
  otherwise. Also fixed in the same commit: a flow with `message_count==0`
  (chronic stall, never fully delivered a message) is now excluded from
  M01/M15's "worst flow" contest instead of winning it by reporting a false
  0ms. `config/metric_panel.yml`: M01, M15 flipped `proxy` → `ok`.
- **Decisions commit** — records decisions #1-3 below (all reviewed and
  resolved), drops the RTSP/TCP coupling from this plan entirely (was
  commit 10; see Decision #2), confirms base generators fold into commit 3,
  and assigns the aggressor/fault-injection knobs to commit 9. Also lands
  `FlowConfig.survival_time_ms: float = 0.0` (`scheduler/flow.py`) as a
  dormant field ahead of its commit-8 consumer — same "plumbing before
  need" pattern commit 1 used for `Message.frame_id`/`role` — and a new
  README §8 `[OPEN]` entry recording the RTSP/TCP gap.
- **Commit 3** — `sim/traffic.py`: `periodic_control`/`condition_monitor`
  (deterministic period + shared `_clipped_gaussian_jitter_ms` jitter,
  optional `traffic_params["streams"]` for MAVLink-style multi-role tagging
  of `Message.role`, falling back to single-rate `role="data"` when absent)
  and `aperiodic_event`/`machine_vision` (Poisson-triggered single burst,
  reusing the existing `poisson` kind's per-slot-probability trigger
  style). `TrafficModel._gen()`'s return type grew from `(ts, bytes)` to
  `(ts, bytes, role)` — every existing kind's return statement now states
  `role="data"` explicitly, mechanically, matching `Message.role`'s
  existing default exactly. New `sim/tests/test_traffic.py` (12 tests).
  Predicted **zero regression drift** before writing any code (no existing
  scenario references any of the four new kind strings — checked directly
  against `scripts/scheduler_study.py`/`demand_study.py`/
  `diagnose_finding3.py`/`test_smoke.py`, not assumed) — confirmed exactly:
  `--check` clean, no re-baseline. `config/metric_panel.yml` untouched —
  M03 stays `pending`; only the generator half of its `requires:` landed
  here, the scorecard function is commit 4.
- **Commit 4** — M03's scorecard function. `sim/driver.py` groups each
  flow's `MessageLedger` completions by `role` (fully-delivered only) and
  stores sorted completion timestamps in a new `RunRecord.FlowRecord.
  completion_ts_by_role_s` field (`scorecard.py` can't own the raw ledger,
  and can't bake in a `T_live` threshold at driver-time, so it needs the raw
  timestamps, not a precomputed count). `Scorecard._m03_liveness_gap_
  distribution()` computes consecutive-completion gaps per role, picks the
  worst (largest max-gap) role per flow and across flows, and reports
  `t_live_s` alongside every value it returns — never a bare number, same
  condition as M14's `survival_time_ms`. A role with <2 completions is
  excluded from the "worst" contest (not scored as gap=0) for the same
  reason M01 excludes zero-message flows. `config/metric_panel.yml`: M03
  flipped `pending` → `ok` — checked against every other metric's
  `requires:`, nothing else flips (M04 stays `proxy` by prior decision;
  M05/M06/M14/M17 still need the XR frame model). 5 new tests in
  `sim/tests/test_scorecard.py`.

  **Drift prediction, made before writing code, confirmed exactly:**
  `regression_corpus.py` never calls `Scorecard.score()` — it snapshots
  `RunRecord.to_dict()` directly, so M03's *scoring logic* can't move
  `--check` regardless of correctness (that path is `test_scorecard.py`'s
  job). What can move it is the new `FlowRecord` field. Predicted 510
  mismatches (24×16 + 30×3 + 12×3 flows across the 22 records), all and
  only `completion_ts_by_role_s`, zero movement elsewhere — confirmed
  exactly: 510 mismatches, all that one key. Re-baselined, matching commit
  2's precedent for a purely-additive change.

  **New finding, not chased further here:** the baseline file grew 512KB →
  5.7MB (11x) from this one field — raw per-message timestamp lists are not
  free, unlike the scalar percentiles commit 2 added. Commits 5-8 (frame
  ledgers, XR completions) will add more data of the same shape. Not
  blocking, but worth watching — if the corpus grows unwieldy, precomputing
  gaps instead of raw timestamps would help at the cost of baking a fixed
  `T_live` in at capture time. (Addressed below, before commit 5.)
- **Regression-corpus compaction** (not a numbered commit) — see its own
  section below. Landed between commits 4 and 5.
- **Commit 5** — `sim/traffic.py`'s `xr_video` generator: frame size
  `_clipped_gaussian_around_mean` (σ≈10.5% of mean, clipped [50%,150%],
  `docs/p5g-sim-plan.md` §9); arrival jitter reuses commit 3's
  `_clipped_gaussian_jitter_ms` (σ≈2ms, clipped ±4ms — one jitter
  mechanism, not two, same reasoning as `periodic_control`'s); PDU-set
  decomposition per Decision #1 (`ceil(frame_bytes/fragment_bytes)` sibling
  messages sharing one `frame_id`, `fragment_bytes` required with **no
  default** so no scenario can silently inherit an unexamined constant).
  `_gen()`'s return shape changed a second time — `(ts, bytes, role)` →
  a `_Arrival` `NamedTuple` with keyword-defaulted `role`/`frame_id` — so a
  third per-arrival attribute won't require touching every existing kind's
  return statement again; bundled into this commit since it's mechanical
  and provably inert (unlike the corpus compaction, no information
  tradeoff to isolate). 8 new tests in `sim/tests/test_traffic.py` (20
  total in that file).

  **Drift prediction, made before writing any code, confirmed exactly:** no
  scenario or test anywhere references `xr_video` (checked directly, not
  assumed) — predicted a clean `--check`, falsifiable. Actual: clean, full
  suite 185 passed (177 + 8 new).

  **Panel check:** `config/metric_panel.yml` untouched — confirmed by its
  absence from the diff. M05/M06/M17 all need commit 6/7's `FrameLedger` and
  scorecard functions; the generator alone satisfies none of their
  `requires:`.

**Verified independently before writing this plan** (2026-08-23): full
suite green (160 passed, `sim/tests -q`), `scripts/regression_corpus.py
--check` clean, both commits now pushed to `origin/feat/high-fidelity-sim`.
The summary above matches `git show --stat` and the actual diffs, not just
the commit messages.

## The five pending metrics WP7 owns

Per `config/metric_panel.yml`, these are every metric with `status: pending`
whose `requires:` names WP7 — matching commit 1's own "five pending
metrics" framing. (M04 is `status: proxy`, not `pending`; WP7 gives it an
incidental exactness upgrade but doesn't flip its status the way it does for
these five, so it's out of scope for this list — see the note at the end.)

### M03 — `liveness_gap_distribution`
`requires: WP7 (discrete periodic message model), WP4 (uplink access
chain)`. **WP4 already landed** (this branch's UL floor / SR-path work), so
WP7 is the only remaining blocker — the second name in `requires:` is not
an open dependency, it's a already-satisfied precondition worth confirming
rather than assuming blocks anything.

Missing: a multi-rate, multi-role generator. README §6: "MAVLink multiplexes
a 1 Hz HEARTBEAT with 4-10 Hz other streams onto one port; WP7's
`periodic_control` generator (one rate per flow) can't express this." This
is exactly what `Message.role` was added in commit 1 to carry
(`"heartbeat"` vs `"telemetry"`), unused until now. Also needs a scorecard
function: group `MessageLedger.completions_for(ue_id, qfi)` by `role`,
compute receiver inter-arrival gaps, compare against `{T_live/4, T_live/2,
T_live}` (`T_live` = `defaults.t_live_s`, already flagged `[OPEN]` in
README §8 — M03 inherits that uncertainty, doesn't need to resolve it).

- Commit 3: multi-role `periodic_control` variant (one port, several
  role-tagged sub-streams at independent rates).
- Commit 4: M03 scorecard function + panel flip to `ok`.

### M05 — `pdu_set_completeness`, M06 — `frame_age_at_mec`, M17 — `frame_freeze_and_effective_fps`
All three: `requires: WP7 (XR frame / PDU-set model)`, nothing else named —
WP7 alone suffices for all three once it lands.

Missing: the `xr_video` generator itself (plan doc §9: frame size truncated
Gaussian σ≈10.5% of mean clipped to [50%,150%]; arrival jitter truncated
Gaussian σ≈2ms clipped to ±4ms; non-integer-ms periods — 16.67/11.11/8.33 —
that alias against the 100ms Tier-1 period, README §7); the frame→PDU-set
decomposition into sibling `Message`s sharing one `frame_id` (decided —
size-derived MTU-style fragmentation, Decision #1 below); and a
`FrameLedger` construct. Note: `sim/messages.py`'s own
docstring already says completeness is "computed by grouping completions by
`frame_id` after the fact (`FrameLedger` below)" — **no `FrameLedger` class
exists in the file**. That's a stale forward-reference commit 1 left for
this work, not a bug to fix now, but flagging it so it isn't mistaken for
one later.

- Commit 5: `xr_video` generator, implementing Decision #1's size-derived
  fragmentation. The fragment size must be a config parameter (not a
  hardcoded 1500), so WP9 can sweep it — M05 is a G5 metric, and fragment
  size plausibly moves completeness. The generator's docstring must state
  plainly that this is an MTU-style stand-in for RTP packetization with no
  ground truth behind it, the same honesty `sim/power.py`'s
  `shrink_to_power_budget`/`snr_to_prb_floor` hold themselves to.
- Commit 6: `FrameLedger` + M05 (completeness) + M06 (frame age) + panel
  flips.
- Commit 7: M17 (freeze events, gaps > 2 frame intervals; effective fps vs
  source fps) — reuses commit 6's `FrameLedger`, no new decomposition
  question. Panel flip.

### M14 — `communication_service_availability`
`requires: WP7 (discrete message model, same as M03/M04)` — WP7 alone.

Missing: the metric itself (TS 22.104: fraction of transfer intervals where
the message arrived within `max_latency + survival_time`).
`FlowConfig.survival_time_ms` (decided — Decision #3 below) already exists
as a dormant default-0 field as of the decisions commit above; this is not
the same concept as `t_live_s` or `defaults.survival_miss_n`, both of which
are different concepts already flagged `[OPEN]` elsewhere.

- Commit 8: M14 scorecard function + panel flip. Per Decision #3's
  condition, M14 must report the `survival_time_ms` value it used alongside
  the availability figure itself — never a bare number.

## Supporting work named in the WP7 spec, not tied to a single metric

- **Base generators** — `periodic_control`, `aperiodic_event`,
  `machine_vision`, `condition_monitor` (plan doc §9's table). None of the
  five metrics above strictly requires all four, but M03's multi-role
  variant (commit 3) extends `periodic_control`, so landing the plain
  single-rate versions first is the natural substrate. **Commit 3 should
  probably land these alongside the MAVLink variant**, not as a separate
  commit — splitting "add periodic_control" from "add its multi-role
  variant" one commit apart buys little isolation since neither is consumed
  by a scorecard change until commit 4.
- **`cycle_clock.py` / `FlowConfig.sync_group`, `phase_offset`,
  `phase_jitter_ms`** — the production-line correlated-burst / "thundering
  herd" mechanism. Plan doc §9 calls this "plausibly the most discriminating
  factory feature," load-bearing for H2 (two-tier's cross-idle credit
  accumulation) and H5. Doesn't flip a panel metric by itself — it's a
  scenario-realism feature that a later characterisation run (WP9) would
  exercise. **Commit 9.**
- **RTSP/TCP UL/DL coupling** (README §6, needed for G10's mixed-fleet
  column and T9) — **decided: build none of it** (Decision #2 below).
  Dropped from this plan entirely; recorded instead as a new `[OPEN]` entry
  in README §8 pointing back to Decision #2's three-option analysis. No
  commit.
- **Aggressor/fault-injection rate multipliers** (README §6, GT-4.3/T6a-e:
  2x/3x/5x/10x on a named flow, mid-run) — "should be first-class scenario
  parameters, not one-off scripts." **Assigned to commit 9**, alongside
  `cycle_clock`/`sync_group` — both touch scenario-config machinery, and
  nothing else forces when the knobs would otherwise land, which is exactly
  why they'd get dropped without an explicit assignment.

**On M04:** already `status: proxy` (the per-slot-timeseries
consecutive-miss approximation), not `pending`. Its `requires:` line notes
WP7 would give it "an exact per-message miss" — once commit 1's ledger
carries `late`/`complete` per completion, an exact version is close to free
(consecutive `late=True` runs per flow, ordered by `generation_ts_s`). Worth
adding as a bonus once the ledger is fully wired (after commit 8, say), but
it isn't one of the five status flips this plan is organized around, and
nothing above depends on it.

## Decisions — no ground truth to check against, made explicitly

Two of these were named directly; a third turned up while tracing M14. All
three share the same shape as the WP-Join RACH-depth question in README §6:
nothing on disk can settle them, so picking one silently would just become a
README §8 `[OPEN]` discovered after the fact — the same pattern as
`FIVE_QI_LCG` and `sr_period_slots`. Surfaced before implementation instead;
all three are now decided, with the options kept below so a future revisit
starts from this analysis rather than redoing it.

### 1. XR frame → PDU-set decomposition — decided: (c)
`sim/messages.py` already models a frame as several sibling `Message`s
sharing one `frame_id`, each its own buffer chunk — but not how many
siblings, or on what basis.

- **(a) One message per frame.** Simplest; but a PDU set of size 1 can never
  be "partially" delivered, which erases the exact property the metric
  panel wants (M05's whole point is partial-frame failure). Not viable if
  M05 is to mean anything.
- **(b) A fixed small N (e.g. 3-4) of equal-size siblings per frame.**
  Cheap, and makes partial loss possible. N itself is arbitrary — real
  slice/RTP-packet counts vary with codec, resolution and motion, none of
  which this branch models.
- **(c) N derived from frame size against a fixed chunk size** (e.g. one
  message per ~1500-byte MTU-sized fragment, mimicking IP fragmentation).
  Ties the count to a real physical constant instead of picking N by hand —
  not a faithful model of actual RTP packetization, but at least the
  *generating rule* is grounded rather than arbitrary.

**What would distinguish them:** nothing currently in the repo.
`oai-branches/` is MAC-layer scheduler source only — there is no RTP/PDCP
fragmentation ground truth anywhere in this branch's vendored material.

**Decided: (c).** (a) is rejected outright — a PDU set of size 1 can never
partially fail, which makes M05 vacuous by construction. (c) over (b)
because tying the fragment count to a real physical constant beats picking
N by hand. Two conditions bind on commit 5: the fragment size must be a
config parameter, not a hardcoded 1500 — M05 is a G5 metric, and if
fragment size moves completeness it needs to be sweepable in WP9 — and the
generator's docstring must state plainly that this is an MTU-style stand-in
for RTP packetization with no ground truth behind it, the same honesty
`sim/power.py`'s `shrink_to_power_budget`/`snr_to_prb_floor` hold
themselves to.

(Side effect, resolves itself once the above is fixed: as long as all
siblings of one frame are enqueued within the same `generate()` call, they
naturally share one `now_s` — no separate decision needed for what
"frame_generation_ts" means for M06.)

### 2. RTSP/TCP UL/DL coupling abstraction — decided: build none
README §6 already flags this as needing sign-off, not just an
implementation detail. Three shapes considered:

- **(a) Cross-wire the existing `adaptive` AIMD source** — feed its
  `served_ratio` from the *paired* video flow's DL delivery instead of its
  own UL delivery. Reuses existing code, but `adaptive`'s own constants
  (`decrease_factor=0.7`, etc.) already have no calibration behind them;
  this stacks a second groundless coupling on top of a groundless base.
- **(b) A minimal windowed-RTT abstraction** (congestion window in messages,
  halved on a missed RTSP keepalive deadline derived from the video flow's
  PDB). Closer to real TCP mechanics, more new code, and adds its own
  uncalibrated parameters (initial cwnd, RTT estimate).
- **(c) Skip a general mechanism**; hard-code a fixed multiplier coupling
  the two flows' *offered* rates, scoped to whatever GT-4.3/T9 specifically
  needs rather than a reusable TCP model.

**What would distinguish them:** nothing on disk — `oai-branches/` has no
TCP or RTSP source at all.

**Decided: build none of the three.** All three add uncalibrated constants;
(a) stacks a groundless coupling on top of `adaptive`'s already-uncalibrated
`decrease_factor=0.7`, compounding rather than avoiding the problem. The
only consumers — G10's mixed-fleet column and T9 — are both Phase 3, not
now. Building any of the three ahead of that would carry invented
parameters through WP5/WP6/WP-Join and contaminate their regression diffs
to serve a consumer that doesn't exist yet. Recorded instead as a
deliberate, documented gap in README §8, pointing back to this analysis.

### 3. M14's `survival_time_ms` — decided: default 0.0, `[OPEN]`
TS 22.104's communication service availability needs a per-flow "survival
time" — the *additional* grace period beyond max latency before an
interval counts as failed. No config field for this exists. It is
**not** the same thing as either existing `[OPEN]` item: `t_live_s`
(README §8, MEC liveness timeout, feeds M03/G9) or
`defaults.survival_miss_n` (a *count* of consecutive misses, feeds M04's
proxy) — both are already-flagged different concepts that happen to sound
adjacent.

- Reuse `pdb_ms` as a stand-in: wrong per spec, since survival time is
  explicitly *beyond* the deadline, not the deadline itself.
- Add `FlowConfig.survival_time_ms` defaulting to 0: silently collapses CSA
  to "delivered within max latency," discarding the distinction the metric
  exists to capture.
- Add the field with a nonzero default picked from nothing in particular.

**What would distinguish them:** nothing on disk names a factory-relevant
survival time value (TS 22.104's worked examples are for other use cases
entirely).

**Decided:** `FlowConfig.survival_time_ms: float = 0.0`, flagged `[OPEN]`.
Default-0 — collapsing CSA to "delivered within max latency" — is
acceptable only on one binding condition: it must not be silent. Commit 8's
M14 implementation must report the `survival_time_ms` value it used
alongside the availability figure itself, so the number is never quotable
without its assumption attached — the `Sweep_Orig_vs_TwoTier.xlsx` lesson
(README §7/§8: a number quoted without the caveat that travels with it
gets misused later).

### 4. (minor) `cycle_clock`'s `phase_jitter_ms` default
Lower stakes than the three above — scenario-authoring rather than a
simulator mechanism — but `phase_jitter_ms` has no natural default either.
Fine to pick something for commit 9 and record it as `[OPEN]` rather than
block on it.

## Regression-corpus storage: compacted before it compounded further

Not one of the numbered commits — a fix to `scripts/regression_corpus.py`'s
own storage format, landed between commits 4 and 5 because the problem it
fixes gets strictly worse if deferred (commits 5-8 add more of the same
shape of data) and because bundling a storage-format change into commit 5's
own fidelity work would make commit 5's drift prediction uninterpretable —
the same reason CLAUDE.md insists on one fidelity change per commit,
extended here to one *corpus* change per commit.

**Problem, with numbers, not a feeling:** commit 4's `completion_ts_by_role_s`
took the baseline from 512KB to 5.7MB (11x) by storing raw per-message
timestamps. Checked whether this was actually a live risk before touching
anything: M14 needs no new array (reuses this same field plus one new
scalar, `survival_time_ms`); M05/M06/M17 only populate non-empty data for
flows using `xr_video`, which none of the 22 baseline records do (studies
1-3's scenarios aren't part of WP7's scope to change) — so the *immediate*
scaling risk from commits 5-8 is smaller than it first looked, but the
underlying problem (any universally-populated array field re-triggers this)
doesn't go away, and would recur exactly this way whenever a future WP (most
likely WP9) adds an XR-using scenario to the corpus.

**Verified before implementing, not assumed: summary stats would have
missed nothing.** Diffed the JSON key-sets across every historical
baseline-affecting commit (`git show <c>:regression/baseline_studies_1_3.json`).
WP4's 1706 mismatches (`02a0fe9`) and WP3's own re-baselines involved **zero
new/removed keys** — pure value drift on already-existing scalars
(`delay_p50_ms_proxy`, `dl_prb_utilization`, etc.). No array was ever
involved in any drift class seen so far; array-vs-summary-stat storage is
orthogonal to all of it. The only real residual risk is a hypothetical
future change that reshuffles values inside an array without moving
count/min/max/any of 6 percentiles — possible in principle, never the
actual failure mode here, and covered independently by `sim/tests/
test_traffic.py`/`test_scorecard.py`'s exact hand-computed assertions (this
corpus's own docstring already calls it a coarse "what moved and by how
much" instrument, not a correctness oracle).

**Implementation:** `scripts/regression_corpus.py::_compact_for_regression()`
replaces `completion_ts_by_role_s`'s raw per-role timestamp lists with
`_array_stats()` (count/min/max/p10/p25/p50/p75/p90/p99) of the **gap
array** (consecutive differences), not the raw timestamps — a more direct
fingerprint of what M03 actually reports (a gap distribution), since
timestamp percentiles mostly just re-encode traffic volume/pacing already
tracked by `message_count`/`throughput_bps` elsewhere in the same record.
This is a change to the corpus's own storage/comparison representation
only — `sim/run_record.py::RunRecord`/`sim/scorecard.py` are untouched, and
still get the full raw data for live scoring (an adjustable `T_live` can't
be baked in ahead of time). Extend `_compact_for_regression`, not
`RunRecord` itself, if commits 5-8 (or a future WP9 scenario) ever add
another large array here.

**Predicted, then confirmed exactly:** the format change itself (list ->
stats dict) surfaces as a mismatch on every *non-empty* role entry — 458 of
them (510 flows, 52 with zero completions matching trivially as `{}` on
both sides) — not 510. Actual: 458. Re-baselined; resulting file:
665,781 bytes (8.6x smaller than the 5,701,824-byte raw-array baseline,
back below commit 3's trajectory).

## Next step

Commits 3-5 are landed (see "Landed" above); M03 is `ok`; the regression
corpus is stored compactly; `xr_video` exists but no scenario uses it yet.
Next action is commit 6: `FrameLedger` + M05 (`pdu_set_completeness`) + M06
(`frame_age_at_mec`), grouping `xr_video`'s frame-tagged completions by
`frame_id`, and the panel flip for both.
