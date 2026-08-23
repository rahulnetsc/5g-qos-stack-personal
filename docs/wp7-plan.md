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

## Next step

All three decisions are made and recorded above; commit 10 (RTSP/TCP
coupling) is dropped from this plan, base generators are confirmed folding
into commit 3, and the aggressor/fault-injection knobs are assigned to
commit 9. Nothing here is still pending review. Next action is commit 3
itself: the base traffic generators plus the MAVLink multi-role
`periodic_control` variant (§ M03 above).
