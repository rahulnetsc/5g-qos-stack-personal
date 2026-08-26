# feat/high-fidelity-sim — a realistic 5G QoS simulator, and the two-tier-vs-reservation regime map

**Status:** Phase 1 complete — WP0, WP1, WP3, WP4, WP7, WP5, WP6, and
WP-Join landed (§4); Phase 2 (both schedulers) begins next.
This branch is a rebuild, not a patch — nothing in `scheduler/` or `sim/`
from `main` is assumed correct or reused as-is.
**Branch:** `feat/high-fidelity-sim`, forked from `main`.
**Not merged into this branch, by decision:** `feat/harq-bler-retx`,
`feat/sim-fidelity-phy-layer`, `feat/oai-integration`. All three diverged
from `main` in May–June 2026 and none are ancestors of current `main`. Their
ideas are mined below (§3); their code is not reused directly — see §2.

This document is the entry point. It records the decisions made before
writing any code and reconciles three source documents that don't fully
agree with each other by default. Read in this order:

1. **This README** — objective, scope decisions, the work-package list as it
   actually stands now (not as originally drafted), guarantee traceability.
2. [`docs/p5g-sim-plan.md`](docs/p5g-sim-plan.md) — the original fidelity +
   regime-map plan. Still authoritative for: the channel/traffic/BSR/HARQ
   technical specs (§9's WP1–WP9 file-level detail), the H1–H7 hypotheses,
   the base metric panel (§7), and the calibration targets (§11).
   **Not authoritative for: work-package ordering** — superseded by §4 below.
3. [`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`](docs/IA_P5G_Factory_Guarantee_Test_Plan.md) —
   authoritative G1–G12 definitions and pass criteria (this is what
   `p5g-sim-plan.md` cites for its own G1–G12).
4. [`docs/IA_P5G_Guarantee_Validation_Suite.md`](docs/IA_P5G_Guarantee_Validation_Suite.md) —
   an earlier draft with its own, superseded G1–G10 numbering. Not used for
   thresholds. Mined for test *mechanism* detail the newer plan states more
   tersely (per-leg latency decomposition, the RTSP/TCP back-pressure
   coupling, frame-freeze definitions) — see §6.

---

## 1. Objective

Two deliverables, in this priority order:

1. **Validate the client-facing guarantees (G1–G12) in simulation**, with
   enough fidelity that a pass/fail here is informative — not just a
   simplified analogue — before committing testbed or OAI time to it.
2. **A regime map**: under what traffic, load, and channel conditions does
   two-tier beat reservation, lose, or tie — expressed against G1–G12, not
   raw latency percentiles.

Both objectives are answered by the same simulator and the same runs; they
are not separate pieces of work. A scenario that stresses the scheduler
comparison (§8 of `p5g-sim-plan.md`) should also be scoreable against the
guarantee panel, and vice versa.

---

## 2. Why a rebuild, not a patch

Two structural problems in `main`'s current `scheduler/two_tier.py`, found by
diffing it against the verified OAI source (§7):

- **It has SPS/Configured-Grant** (`_SPSReservation`, `_allocate_sps`). The
  real hardware two-tier scheduler (`ia_p5g_scheduler.h`) explicitly defers
  SPS to "Phase 2" — never built. The Python "two-tier" and the deployed
  two-tier are not the same scheduler in this dimension, and every SPS-
  driven result in `main`'s benchmark output describes a scheduler that
  doesn't exist on the testbed.
- **It models intra-TB per-flow byte splits on uplink**
  (`_shadow_lcp_split`, `_occupancy_split`, `_mac_lcp_fill`). The real gNB
  cannot see this — the UE decides its own intra-TB split via its own LCP,
  and the gNB only ever sees aggregate per-LCG BSR. This is the exact
  failure mode `p5g-sim-plan.md` §5.6 warns about ("which network element
  learns this, and how?"), and it's currently in `main`, not just in a
  historical mistake.

There is also no `reservation.py` on `main` at all. Rather than port one
scheduler, audit it, then build the second one afterward (the original
WP2a → WP2b → WP8 sequence), **both schedulers are written once, at the end
of Phase 1, directly against verified OAI source** (§7) — collapsing
port-then-audit into build-it-right-the-first-time.

**Consequence for `p5g-sim-plan.md` §5.5.** That principle — land the
reservation baseline early, not last, so each fidelity change is measured
against the actual comparison the branch exists to make — assumed we were
*patching* an already-partially-unfaithful two-tier port. That's not what's
happening here. The risk §5.5 guards against (fidelity deltas measured
against the wrong scheduler) doesn't apply when both schedulers are written
fresh against source at the end. The cost: no per-work-package attribution
of how the two-tier-vs-reservation gap moves during Phase 1 (§4).
**Mitigation:** the regression corpus (WP0) still runs after every Phase 1
work package against the existing `sim/baselines/` (PF, RoundRobin,
Gradient) — so simulator bugs are caught as they land, just not
scheduler-comparison deltas.

---

## 3. What was mined from the stale branches vs. left behind

| Branch | What it has | Disposition |
|---|---|---|
| `feat/harq-bler-retx` | Real, tested HARQ/BLER/IR-combining code — `combining_gain_db(retx_count, mode)`: an SNR-domain dB bonus by attempt count (IR: 0/4.0/6.5/8.0 dB for retx 0-3; Chase: 3.0 dB/retx), composed with a sigmoid BLER curve (`scheduler/link.py`); a genuine PRB-budget correction for retransmissions (`_ReducedSlotView.prb_count = total − retx_prbs_due`, `sim/driver.py`); a 16-process-per-UE-per-direction HARQ pool; per-UE-grant baseline refactor; network slicing | The combining-gain *mechanism* and the PRB-budget correction are reused conceptually in WP5 (`docs/wp5-plan.md`). **Correction:** this row previously described the branch as containing a reachability-probability-weighted formula (`effective_SE(Δ) = SE × Σp_reach(k)(1−BLER_k) / Σp_reach(k)`) — verified absent from the branch's actual code (`git grep`/`git show` against `origin/feat/harq-bler-retx`, checked directly while scoping WP5); that formula is not built anywhere either (see `docs/wp5-plan.md` Decision 1). The code itself is not merged — it's 2.5 months behind `main` and touches `scheduler/interfaces.py`, `scheduler/link.py`, `scheduler/two_tier.py`, `sim/driver.py`, `sim/metrics.py` (confirmed `sim/buffer.py`/`sim/baselines/*` are **not** touched by this branch, contrary to what this row previously said). Network slicing is out of scope for this branch. |
| `feat/sim-fidelity-phy-layer` | Docs only, no code. Per-UE BLER sigmoid curve, waypoint mobility + Doppler coherence, CQI reporting delay, OLLA closed-loop link adaptation | CQI delay already landed on `main` independently (`simulator-design.md`, 2026-08-06). OLLA and mobility are **not** in `p5g-sim-plan.md`'s scope and are **not** added here either — no guarantee test in §6 requires UE mobility or OLLA specifically, and adding them now would widen scope past what G1–G12 need. Revisit only if a specific GT/T test fails and mobility/OLLA is the diagnosed cause. |
| `feat/oai-integration` | A checked-in `openairinterface5g/` source tree | Not touched. Parallel workstream per `main`'s README; the 5 files already hand-verified (§7) are sufficient for this branch's needs. |

---

## 4. Phasing

Restructured from `p5g-sim-plan.md`'s original `WP0→WP1→WP2a→WP2b→WP3→WP4→
WP7→WP5→WP6→WP8→WP9` given §2's rebuild decision.

### Phase 1 — realistic simulator (no scheduler logic changes; scored against `sim/baselines/`)

| Order | WP | Scope | Source of truth | Status |
|---|---|---|---|---|
| 1 | WP0 | Harness, pre-registered metric panel, regression corpus | `p5g-sim-plan.md` §9, extended per §5/§6 below | Done |
| 2 | WP1 | `min_rb`, power headroom, SNR→PRB floor | `p5g-sim-plan.md` §9; PHR noted sim-only (inert on hardware) | Done |
| 3 | WP3 | BSR realism: per-LCG, quantised, event-triggered, short-BSR aliasing, `sched_ul_bytes` collapse-to-crumb | `p5g-sim-plan.md` §9; mechanics verified line-for-line against `gNB_scheduler_ulsch.c` (§7) | Done — 3 commits (quantisation/LCG structure, event-triggering/crumb gate, M02 per-chunk tracking); crumb-fraction and H5-scenario gaps open (§8) |
| 4 | WP4 | Uplink access chain: SR → grant → BSR → grant, `sr-ProhibitTimer`, `sr-TransMax`→RACH boundary | `p5g-sim-plan.md` §9; ground truth vendored from the live OAI checkout, not `oai-branches/` (§7); mechanics verified against `gNB_scheduler_uci.c`/`nr_ue_procedures.c` | Done — cold-start probe retired (§8); SR-chain inversion calibration target (§11) **not reproduced** — negative result, reported not tuned (§8); regression-check predictions verified against `--check`'s actual output and mostly falsified (§8) |
| 5 | WP7 | Factory traffic generators, correlated bursts, XR video model | `p5g-sim-plan.md` §9, extended per §6 below (UAV/MAVLink heterogeneous cadence, RTSP/TCP coupling) | Done — 9 commits (message-ledger plumbing; M01/M15 true latency; base factory generators + MAVLink multi-role `periodic_control`; M03; `xr_video` generator; `FrameLedger` + M05/M06; M17; M14; `cycle_clock`/`sync_group` + aggressor knobs); RTSP/TCP UL/DL coupling deliberately unbuilt (§8) |
| 6 | WP5 | HARQ: N processes/UE/direction, k1/k2, RTT, per-attempt combining gain, max-retx residual loss | `p5g-sim-plan.md` §9; combining-gain formula reused from `feat/harq-bler-retx` (§3) | Done — 6 commits (0, 1, 2, 3, 4a, 4b, 6 — gap at 5 is the charter's own numbering); binary-delivery switch dominates pre/post-4a drift (§8); OLLA bug #1 landed dormant, bug #2 blocked on WP1 activation (§8) |
| 7 | WP6 | Channel: TR 38.901 InF path loss + two-state Markov blockage | `p5g-sim-plan.md` §9, extended per §6 below (sync-loss threshold feeding WP-Join) | Done — 4 commits (InF path loss + LOS probability, two-state Markov blockage, sync-loss detection landed dormant per sign-off, blockage×HARQ acceptance-criterion demo); InF sub-scenario naming corrected against spec text (§8); mobility/correlated blockage deliberately deferred (§8) |
| 8 | **WP-Join** *(new)* | Join / re-join / RLF-recovery state machine | §6 below — not in `p5g-sim-plan.md` at all | Done — 8 commits (`docs/wp-join-plan.md`): dormant FSM + delay sampler, `sim/rlf.py` wiring (unconditional, diagnostic-only), a deterministic scripted fade (the GT-6.3a/6.3b boundary confirmed exactly at 10,010 slots/5.005s), the M18/M19 metric schema, the radio-layer gate, the application-layer gate with a real handshake `Message` pair, the per-UE scheduler context reset (the only WP-Join commit, and the only WP since WP0, to touch a scheduler file), and a GT-6.3 acceptance-criterion demo. G9's ratified verdict still blocked on `T_live`/provisional thresholds (§5); GT-6.1/6.2 cycle campaigns deferred to WP9 |

### Phase 2 — both schedulers, written fresh against verified OAI source

| Scheduler | Must reproduce | Must *not* include |
|---|---|---|
| Two-tier | Tier-1 LP (0.1 s period — confirmed, not the header's stated 1.0 s default), windowed-ceiling VQs, UL service-interval floor (fruitless-counter backoff + ADQ crumb-run trigger), two-pass DL LCP | SPS/Configured-Grant (real scheduler defers it); per-flow intra-TB UL split (UE is a black box) |
| Reservation | Follower budget (`bwpSize − n_followers_need×min_rb`, floored at `min_rb`), four-tier sort (SRB→liveness→GBR deficit→PDB/coef), GBR/BE byte split, two-pass DL LCP | — |
| Both | The "full `tb_size` credited to every active LCG" deficit-drain behavior on reservation, reproduced **as measured, bug-for-bug** — the code's comment claims "proportional," the code doesn't do that (§7). Porting the comment's *intent* instead of the code's *behavior* would silently un-fix nothing and mismatch whatever hardware numbers exist. | — |

This absorbs the original WP2a (confound spec), WP2b (reservation build),
and WP8 (alignment audit) into one pass, since both schedulers are being
written against already-verified source rather than ported-then-checked.

### Phase 3 — characterization sweep

WP9 as originally specified: the full grid (N, offered load, burst duty
cycle, SNR spread, PDB/tier1-period ratio, flows-per-LCG, GFBR-to-offered
ratio), 10 seeds/cell paired across arms, scored against the full metric
panel (§5), testing H1–H7. Regime-selection discipline unchanged: a cell
with 0% loss on both arms is excluded.

---

## 5. Guarantee traceability (G1–G12 → what the simulator needs)

Per `IA_P5G_Factory_Guarantee_Test_Plan.md` §3. "Sim-answerable" means the
simulator can produce an informative pass/fail with the fidelity above, not
that the number is certifiable — certifiable numbers still require real RF.

| G | Guarantee | Needs (beyond baseline scheduling) | WP | Sim-answerable? |
|---|---|---|---|---|
| G1 | Drive command p98 ≤ PDB | T1/T2 shared-bearer modeling, DL LCP | WP7, Phase 2 | Yes |
| G2 | STOP always lands fast | Rule-of-three sample sizing (already in panel), DL priority | WP0, Phase 2 | Yes |
| G3 | No false-failsafe | Real BSR/grant chain, liveness gap distribution | WP3, WP4, WP7 | Yes |
| G4 | Prompt resume after silence | SR-path fidelity, floor arming window | WP4 | Yes |
| G5 | Fresh, complete video | XR frame model, PDU-set completeness, frame age | WP7 | Yes |
| G6 | BG traffic never impairs fleet | Non-GBR containment, per-class accounting | WP0 metric panel | Yes |
| G7 | One misbehaving UE contained | MFBR clamp, per-flow accounting | Phase 2 (scheduler logic) | Yes |
| G8 | Equal entitlement, continuously | Per-1s Jain (already flagged as new in `p5g-sim-plan.md` §7) | WP0 | Yes |
| G9 | Fast join / re-join | Join/RLF state machine — landed (`sim/join.py`, `sim/rlf.py`, `docs/wp-join-plan.md`) | WP-Join | **Mechanism/metrics: yes. Ratified verdict: no** — blocked on `T_live` (§8, `[OPEN: HARDWARE]`) and the guarantee test plan's own provisional (▷-marked) thresholds; GT-6.1/6.2's 50-cycle/10-cycle campaigns deferred to WP9 |
| G10 | Admissible fleet size | N-sweep (this is what simulation buys that hardware can't — `p5g-sim-plan.md` §2) | Phase 3 | Yes |
| G11 | Holds for a shift, reproducibly | Long-run soak, communication service availability metric (new, §6) | WP0 metric panel, WP7 | Yes |
| G12 | Ordered degradation under overload | First-violation-order metric (already in panel) | Phase 3 | Yes |

**WP-Join landed the join/re-join/RLF-recovery mechanism this row now
describes** (8 commits: dormant FSM + delay sampler, `sim/rlf.py` wiring,
a scripted deterministic fade, the M18/M19 metric schema, the radio-layer
gate, the application-layer gate with real handshake traffic, the per-UE
scheduler context reset, and a GT-6.3 acceptance-criterion demo —
`docs/wp-join-plan.md`). G9 is no longer unanswerable in principle: a
real scripted-fade run produces real `rejoin_interruption_time` (M18) and
`slo_recovery_time` (M19) numbers for the reestablish path, both
comfortably inside the guarantee test plan's own (provisional) targets in
the demo built for it. What is **not** yet delivered is a *ratified*
verdict — `T_live` and the test plan's own ▷-marked thresholds are both
still open (§8), and GT-6.1/6.2's own repeated-cycle campaigns are WP9's
job, not this WP's.

---

## 6. New fidelity requirements surfaced by the guarantee documents

Not in `p5g-sim-plan.md`'s original scope. Organized by category per the
guarantee-document review.

**Traffic:**
- **UAV telemetry is multi-rate, not scaled-down UGV telemetry.** MAVLink
  multiplexes a 1 Hz HEARTBEAT with 4–10 Hz other streams onto one port.
  WP7's `periodic_control` generator (one rate per flow) can't express
  this — needs a multi-stream-per-port generator variant.
- **RTSP-pulled UAV video couples DL delay into UL throughput** via its TCP
  control channel (`IA_P5G_Guarantee_Validation_Suite.md` T9). No flow in
  `sim/traffic.py` has any UL/DL coupling today. Needs a minimal AIMD/
  windowed abstraction on the RTSP control channel — not full TCP, but
  more than an independent flow. Without this, G10's mixed-fleet (UGV+UAV)
  column and T9 are unanswerable in principle.
- **Aggressor/fault-injection knobs** (GT-4.3, T6a–e: 2×/3×/5×/10× rate
  multipliers on a named flow, mid-run) should be first-class scenario
  parameters, not one-off scripts, since the guarantee campaign runs six
  variants of essentially the same test.

**Channel:**
- **A sync-loss threshold, separate from the BLER discount.** WP6's
  blockage model discounts delivered bits continuously; real RLF is a
  discrete state transition (channel below a sync floor for long enough
  that the UE declares link failure) that feeds into WP-Join. Calibration
  anchor: `calibration-logs/twotier_startup_gnb.log:17`'s startup banner
  gives the actual OAI timer constants — `t300 400, t301 400, t310 2000,
  n310 10, t311 3000, n311 1, t319 400` (ms/counts) — real values from the
  deployed gNB config, not invented ones. (Corrected citation, WP-Join
  commit 8: this was previously misnamed `contention.log`, a phantom path
  from an old layout diagram never actually committed — see
  `calibration-logs/README.md`.)
- **`[RESOLVED]`** WP-Join's attach/RACH/reestablishment timing is a
  **calibrated delay distribution keyed to the timers above**, not a
  contention-based RACH simulation (preamble collision probability etc.) —
  confirmed by sign-off before WP-Join commit 1 landed. Full RACH
  contention is PHY-layer fidelity the simulator's own non-goals correctly
  exclude, and no G9/GT-6/T8 pass criterion needs it — they need realistic
  *timing*, not realistic *contention resolution*. Delays are drawn as
  `floor + Exponential(mean_excess)`, with a draw beyond the cited ceiling
  a real timer-expiry event (`sim/join.py`, `docs/wp-join-plan.md` D2/D3).

**Metrics (extend WP0's panel):**
- **Communication service availability** (TS 22.104): fraction of transfer
  intervals within (max latency + survival time). This is the number that
  actually fills in G11's Guarantee Sheet row; not currently a first-class
  metric.
- **Command jitter as p99 − p50** (not stddev), per `IA_P5G_Guarantee_
  Validation_Suite.md` T2.
- **UL/DL correlation on the shared T1/T2 bearer** — whether both
  directions degrade together (a robot both blind and unresponsive at
  once is a distinct, worse failure than either alone).
- **Frame-level freeze events** (gaps > 2 frame intervals) and
  **effective-fps-vs-source-fps**, distinct from PDU-set completeness —
  needs packets tagged by frame/PDU-set id, which WP7's XR model already
  produces the structure for.

---

## 7. Ground truth from OAI source (what Phase 2 must reproduce)

Verified directly against the uploaded OAI source
(`gNB_scheduler.c`/`_dlsch.c`/`_ulsch.c` for both branches, `ia_p5g_
scheduler.{c,h}`), not inferred from behavior. Full detail in the design
conversation that produced this branch; load-bearing facts recorded here so
they survive it:

- **Tier-1 period is 0.1 s in practice**, despite `ia_p5g_scheduler.h`'s doc
  comment stating a 1.0 s default — the macro is hoisted in the `.c` file
  specifically because of a past build failure, and `contention.log`'s
  startup banner confirms `tier1_period=100ms` is what actually ran. This
  is what makes H4 (Tier-1 mismatched to 1–10 ms motion-control PDBs) the
  first hypothesis to test.
- **The two-tier `.c` file's top-of-file comment describing every function
  as a Checkpoint-1 stub is stale** — the real implementation is fully
  built (SCA/GLPK solver, VQs, LCP budget pass, the UL floor subsystem).
- **An anti-starvation subsystem exists that no prior document mentions**:
  `IA_P5G_UL_FLOOR_*` — a service-interval floor with an exponential-
  backoff "fruitless counter" (caps at 16×) and a separate "ADQ" trigger
  firing on 8+ consecutive `min_rb` crumb grants.
- **Reservation's confound-table entries (`p5g-sim-plan.md` §9 WP2a) are
  now verified against source, not inferred**: PF coefficient `tbs/thr`
  (thr floored at 1.0), the `has_srb`-tier starvation fix, the follower
  budget formula (`budget = bwpSize − n_followers_need×min_rb`, floored at
  `min_rb`), the four-tier sort (SRB→liveness→GBR deficit→PDB/coef), and
  the two-pass DL LCP (SRB pass, then DRB pass, per TS 38.321 §5.4.3.1).
- **The deficit-drain comment/code mismatch**: reservation's post-grant
  drain comment says "distribute tb_size drain proportionally across
  active LCGs"; the code credits the **full** `tb_size` to every active
  LCG independently. Reproduce the code's behavior, not the comment's
  intent (§4, Phase 2 table).
- **A third instance of the same comment/code (or, here, doc/default)
  mismatch — this time in this repo's own Python, found scoping Phase 2.**
  `scheduler/two_tier.py`'s current `tier1_period_slots` default (`2000`)
  matches `ia_p5g_scheduler.h`'s stale "1.0 s default" doc comment for
  Tier-1's re-solve cadence, not the confirmed-real 0.1 s the deployed
  macro (`IA_P5G_TIER1_PERIOD_S`, `ia_p5g_scheduler.c:74-76`) actually
  runs at: at this repo's default `numerology=1` (0.5 ms slots),
  `2000 slots = 1.0 s`. Phase 2's rewrite must default to 200 slots (or
  derive the slot count from `tier1_period_s=0.1` ÷ `grid.slot_duration_s`
  so it's numerology-robust), not carry the stale value forward. CLAUDE.md's
  "reproduce measured behavior, not documented intent" rule now carries
  this as its third cited instance, and the first found in this codebase's
  own code rather than in ported OAI C.
- **A previously-fixed sort bug**, visible in a live comment: sched-
  inactive UEs used to sort to the *front* of the queue ("a bug"), now
  fixed to sort last. Relevant for provenance if any existing hardware
  run predates this fix.
- **`gNB_scheduler.c` is identical across both branches** (shared/common
  dispatcher); only `_dlsch.c`/`_ulsch.c` diverge — this is why the
  reservation branch's files were kept in a separate directory from
  two-tier's (`oai-branches/{two-tier,reservation}/`) rather than one
  flat folder.
- **`min_rb` is a static config constant, not an SNR-derived value.**
  `nr_ue_max_mcs_min_rb`'s `minRb` parameter, and reservation's
  follower-budget formula (`budget = bwpSize − n_followers×min_rb`), both
  trace to `nrmac->min_grant_prb` (`gNB_scheduler_ulsch.c:2055`) — a fixed
  gNB config value with no dependence on channel quality or payload size.
  WP1's `scheduler/link.py::snr_to_prb_floor` computes something related
  but distinct — the fewest PRBs a payload could ever fit into at a given
  SNR — and is explicitly not a stand-in for `min_grant_prb`. Keep the two
  separate when WP2 builds reservation's follower budget.
- **`nr_ue_max_mcs_min_rb`'s `tbs` parameter is dead.** The function opens
  with `int tbs_bits = tbs << 3;`, then immediately overwrites `tbs_bits`
  via `nr_compute_tbs()` before that initial value is ever read
  (`gNB_scheduler_ulsch.c` ~L1792-1798). Same species of comment/code
  oddity as the Tier-1 period and the deficit-drain mismatch above. WP1's
  `sim/power.py::shrink_to_power_budget` correctly omits a `tbs`-equivalent
  parameter — its caller-supplied `tbs_bits_fn(rb, mcs)` already replaces
  what `nr_compute_tbs()` would have computed.
- **`estimated_ul_buffer_per_lcg` is never drained by a grant — only
  reset-then-repopulated on the next BSR (found during WP3).**
  `post_process_ulsch`'s comment (`gNB_scheduler_ulsch.c` ~L2732-2751)
  claims the per-LCG array is consumed "exactly as the UE's strict-priority
  LCP would"; the code that follows (~L2785-2802) only decrements a
  separate `ul_lcg_deficit_bytes[]` field and never writes back to
  `estimated_ul_buffer_per_lcg[]` itself. The array is frozen at its
  last-BSR value between reports. WP3's Python port reproduces this
  faithfully (does not drain it either) — Phase 2's reservation port reads
  this same field and needs to know upfront that it's frozen, not live.
- **The scalar `estimated_ul_buffer` and the per-LCG array can desync
  between BSRs (found during WP3).** On actual SDU receipt
  (`gNB_scheduler_ulsch.c` ~L544-547) the scalar *is* decremented by the
  received bytes, but `estimated_ul_buffer_per_lcg[]` is not touched at
  that site — no comment claims otherwise, so this isn't a mismatch, but
  combined with the previous point it means the per-LCG breakdown can
  drift arbitrarily from the scalar until the next BSR resets both.
  Preserved deliberately in the port, not fixed.
- **At N=2 UEs, the two schedulers do not differentiate on admissible
  load — settled by the original measurement's own author, not just
  argued from absence of evidence.** `oai-branches/Sweep_Orig_vs_TwoTier.
  xlsx` (a 6-point offered-load sweep, 45-145%, 3 runs/point, "worse-of-
  two-UE p99", found untracked in the repo and vendored for WP4) carries
  its own conclusion: "at N=2 UEs over this load range, the two schedulers
  are equivalent on admissible load; neither breaks... if admissible load
  ties, go to N=3, or report the fairness (Jain) metric as the
  differentiator." This independently confirms `p5g-sim-plan.md` §3.2's
  argument that reservation/two-tier's difference was never actually
  exercised at N=2 — from the person who ran the original hardware sweep,
  not just inferred from the numbers after the fact.
- **Neither scheduler is uniformly better across the sweep — there's a
  crossover, and it's the more interesting result than either endpoint.**
  Two-tier reads lower (better) p99 than Original at 45%, 70%, and 145%
  load, but higher (worse) at 90% and 105% (125% is a near-tie: 12.98 vs
  12.99 ms). See §8 for the full curve and the caveats on the 145% point.
  `p5g-sim-plan.md` §11's two-number summary (45%→67.25ms, 125%→12.98ms)
  is an accurate transcription of two of these six points but on its own
  hides this crossover entirely — exactly the kind of detail "reproduce
  the two headline numbers" would miss.

---

## 8. Open decisions

**Triage pass (Phase 1 → Phase 2 boundary):** every `[OPEN]` item below
now carries a category tag so §10's Phase 3 exit criterion ("every
`[OPEN]` item either closed or explicitly carried to the hardware
campaign") is checkable by grep, not aspirational. Four items closed
outright this pass (their substance was already settled by a landed WP
or an already-made decision — flipped to `[RESOLVED]` with a citation of
what actually closed them, not just the tag). Four more items that were
one hypothesis wearing four separate bullets are merged into one
`[OPEN: WP9]` cluster below. Tags in use: `[OPEN: WP9]` (needs a WP9
characterization sweep), `[OPEN: PHASE2]` (resolves when the scheduler is
rewritten fresh from OAI source, not by any sweep), `[OPEN: HARDWARE]`
(needs a real deployment measurement or data this repo doesn't have),
`[OPEN: DECISION]` (needs a call from the project owner, not more data).
**This vocabulary is open-ended** — if a future item doesn't fit one of
these five, add a new tag rather than forcing it into an existing one.

- `[RESOLVED]` WP-Join's RACH/RLF depth: calibrated delay distribution
  (§6), confirmed before WP-Join commit 1 landed, not contention-based
  simulation.
- `[OPEN: HARDWARE]` `T_live` (MEC liveness timeout) — assumed 2 s in the
  guarantee docs; both `p5g-sim-plan.md` and the guarantee test plan flag
  this as unconfirmed. Calibrates every G3/G9 pass line. No calibration
  source anywhere in this repo gives a real value — needs an actual MEC
  liveness measurement, not a sweep.
- `[OPEN: DECISION]` The uplink capacity constant (`p5g-sim-plan.md`
  §4.2) — resolve against GT-3.2's ceiling re-measurement, or sweep it as
  an axis. Your call which path.
- `[OPEN: WP9]` InF sub-scenario (SL/DL/SH/DH/HH — corrected below) for
  the headline configuration — deployment-dependent, sweep in WP9 rather
  than picking blind. (WP6 fixed the sub-scenario *naming* below, not
  this choice — still open.)
- `[RESOLVED]` **This document previously named the InF sub-scenarios
  "SL/DL/SH/HH," omitting InF-DH — verified wrong against TR 38.901 Table
  7.2-4 while scoping WP6 (`docs/wp6-plan.md` §0), not just suspected.**
  The spec defines five InF sub-scenarios: `InF-SL`/`InF-DL`/`InF-SH`
  (sparse/dense clutter × low/high BS height) plus `InF-DH` (dense
  clutter, high BS — the fourth clutter×height member this document
  dropped) and `InF-HH` ("high Tx, high Rx" — both antennas elevated
  above clutter, a structurally different, always-LOS case with no NLOS
  path-loss row of its own in Table 7.4.1-1). The likely source of the
  error: a reader skimming for "the four InF path-loss formulas" sees
  exactly four named rows (SL/DL/SH/DH) and, without checking Table 7.2-4
  first, could mis-transcribe the fourth as "HH" from memory of the
  sub-scenario *list* rather than the *path-loss table*. `sim/pathloss.py`
  (WP6 commit 1) implements the real five; `p5g-sim-plan.md:670`'s own
  "(SL/DL/SH/HH)" is left as-is per this document's own policy of not
  editing that file (§0) — its four-item text is now known-stale in the
  same category as `p5g-sim-plan.md`'s original WP ordering.
- `[OPEN: WP9]` Survival-time threshold N (`p5g-sim-plan.md` §7) — start
  at 3, report H6 as a function of N.
- `[RESOLVED]` **WP3 exposed a UL scheduling deadlock that only WP4 could
  properly close — closed by WP4, commit `fa8232b` ("WIP WP4").** Every
  scheduler's UL eligibility gate (`bytes_reported > 0`) is
  refreshed only by a grant, and a grant requires the gate to already be
  open -- a deadlock for any flow whose real backlog goes from empty back
  to non-empty (most bursty UL traffic here), not just a one-time cold
  start. Real 5G breaks this with a Scheduling Request on PUCCH, a
  control-channel signal needing no existing grant (WP4). Before WP4,
  `sim/bsr.py::BsrModel.broadcast()` reported a flow's true backlog
  directly whenever its per-LCG estimate was exactly 0 -- a stopgap that
  was load-bearing for every scenario's basic UL throughput at the time,
  not a corner case. It did not defeat the crumb-collapse mechanism
  itself (a nonzero estimate capped to 0 by `B` still gated correctly).
  See `design-docs/scheduler-study.md` §5.1 for detail. **Confirmed
  retired, not just superseded**: WP4's real SR path
  (`sim/ul_access.py::UlAccessModel`) replaced this stopgap, and CLAUDE.md
  carries a standing invariant against reintroducing it.
- `[OPEN: HARDWARE]` **The load-inversion calibration target's full source data, and
  what it does and doesn't support.** `p5g-sim-plan.md` §11's 67.25ms/
  12.98ms headline traces to `oai-branches/Sweep_Orig_vs_TwoTier.xlsx` (see
  §7 for the no-differentiation finding) — found sitting untracked in the
  repo while scoping WP4, now vendored there along with a plain-text
  `Sweep_Orig_vs_TwoTier.csv` extraction. Full 6-point curve (Load% → Orig
  / TT p99 med, ms): 45→67.25/63.13, 70→31.88/24.36, 90→15.59/16.7,
  105→14.73/15.26, 125→12.98/12.99, 145→33.09/15.9. Both curves fall
  45%→125%, then Original genuinely upticks at 145% (33.09ms, a real
  measurement). The 145% Two-tier value (15.9ms) is flagged by the sheet's
  own author as a capture-overlap artifact ("real p99 12-16ms" for valid
  runs) — treat it as unusable for characterizing scheduler behavior at
  that point, not as a real "stays flat" measurement. Only medians across
  3 runs/point are available — no raw per-run values or confidence
  intervals. Open question: whether a fuller/raw-runs version of this
  sweep exists elsewhere (being tracked down separately). Practical
  consequence for WP4: the target to reproduce is the *shape* — fall then
  uptick, with a scheduler crossover in the middle (§7) — not a specific
  millisecond value at either endpoint, and not a scheduler-differentiation
  signal, since the source itself says there isn't one at this N.
- `[OPEN: WP9]` H5 (`p5g-sim-plan.md` line 338, "two-tier degrades as
  flows-per-LCG grows") is not demonstrable on any current scenario. WP3's
  default 5QI→LCG mapping (`scheduler/flow.py::FIVE_QI_LCG`) deliberately
  separates QoS classes into different LCGs, matching real deployment
  practice — but it means `scenario_config_6.yml`'s only multi-UL-flow UEs
  (8, 9, 10: GBR video + a different-class best-effort/ack flow each)
  never share an LCG, so short-BSR aliasing and per-LCG aggregation go
  unexercised by every scenario in the repo today. Needs a small follow-up
  scenario (two same-class UL flows forced onto one `lcg` via an explicit
  override) before H5 can be confirmed, refuted, or ruled inconclusive in
  Phase 3.
- `[OPEN: HARDWARE/DECISION]` **`FIVE_QI_LCG` (`scheduler/flow.py`) is an invented mapping with
  nothing to validate it against.** LCG assignment isn't 3GPP-standardised
  as a function of 5QI — a real deployment configures it per-logical-channel
  via RRC, an operator/gNB policy choice — and no OAI source or spec table
  exists for it either. The specific groupings (voice/gaming→LCG0,
  conversational video→LCG1, buffered video→LCG2, ...) are a judgment call
  made during WP3 with no standard, vendored config, or measurement to check
  it against. This isn't just an academic gap: it directly determines which
  flows alias/collapse together under short-BSR reporting, and it's the
  mapping the H5 follow-up scenario above would have to use — so H5's
  result would depend entirely on this unvalidated choice. Resolution needs
  either a real deployment's RRC logical-channel config (if one becomes
  available) or an explicit decision to sweep the mapping itself as a WP9
  axis rather than treating it as fixed ground truth. Recorded nowhere
  before this.
- `[OPEN: WP9]` **The UL-access-chain dominance cluster** — four findings
  below that are one investigation for WP9, not four, per the framing
  each already converges on: "the uplink access chain dominates outcomes
  at low load and for small messages, more than the scheduling policy
  layered on top of it does." Treat Facets 1-4 as one hypothesis to test
  directly in WP9's wider sweep, not as four separately-filed items that
  happen to rhyme.

  **Facet 1 — WP3's crumb fraction falls well short of the charter's
  acceptance bar.** Measured on `factory_robots_scenario` @ 1.0× with
  TwoTier: grants ≤150 bytes ("crumb") are **0.09%** of UL grants, against
  the hardware measurement's ~48-52% — roughly 500x off, not the "within a
  factor of two" the charter (`p5g-sim-plan.md` §9 WP3) asks for. The
  crumbs that do occur average 79 bytes, inside the hardware's measured
  72-107 byte range — the mechanism looks structurally right, only its
  *frequency* is off. Not chased further before landing: plausibly
  scenario-dependent (TwoTier's grant sizing may already avoid granting
  past `bytes_reported` on this workload, unlike the probe's hardware
  traffic) or timer/workload-cadence-dependent (periodicBSR=5ms vs this
  scenario's grant rate), not necessarily a modeling bug. Revisit once
  WP9's characterization sweep runs a wider parameter range — if the
  shortfall persists across scenarios, that's a real finding about this
  port, not just this scenario.
  **Update, WP4:** measured again on the same scenario/scheduler after
  landing the real SR path, under the same `cqi_delay_slots=8` every other
  study/regression case in this branch actually runs with
  (`scripts/scheduler_study.py::CQI_DELAY_SLOTS`) — crumb fraction moved
  to **4.4503%** (151/3393 UL grants), a ~50x increase in the predicted
  direction but still well short of hardware's 48-52%. (At
  `cqi_delay_slots=0`, the driver's bare default and not what this
  branch's studies run, the same measurement gives 4.4653%/152/3404 — the
  two are close enough not to change the finding, but 4.4503%/151/3393 is
  the figure consistent with how every other number in this document was
  produced, so it's the one recorded here.) The crumbs' own size profile
  got *less* accurate in the process: average crumb size is now 146.03
  bytes (vs WP3's 79 bytes, inside hardware's 72-107 byte range) because
  most crumbs are now the SR-triggered grant's fixed 150-byte report floor
  (`sim/ul_access.py::DEFAULT_SR_REPORT_FLOOR_BYTES`) rather than the
  organic `sched_ul_bytes`-outracing-`estimated_ul_buffer` collapse WP3
  identified — a partial, directionally-correct but not closing
  confirmation, not a resolution.
  **Facet 2 — the load-inversion calibration target (§7/§11) does not
  appear in this simulator, at any calibration tried.** `scripts/
  scheduler_study.py::study_ul_access_chain` (WP4) sweeps offered load
  (45-145%, matching the real sweep) against `sr_period_slots` on two
  different scenario constructions (`sensor_dense_scenario`'s 30-UE/15ms-
  PDB setup, and a dedicated N=2-UE/100ms-PDB scenario mirroring the real
  sweep's own methodology more closely). Neither shows the hypothesised
  high-to-low curve. Instead: PF/RoundRobin (non-SPS) show p99
  *increasing* with load — the opposite direction — up to a sharp
  collapse to the PDB ceiling, not a gradual queueing curve; TwoTier
  (SPS-bypassed for these flows) stays flat and small throughout, which
  is the mechanism being absent, not confirmed. `sr_period_slots` changes
  how early the collapse hits, not its shape. Diagnosis: the hypothesis
  needs a regime where a UE's buffer stays busy enough to never return to
  empty between messages (so SR is skipped after the first one) without
  yet missing PDBs outright — in this simulator that middle regime did
  not appear at any tested load/scenario/periodicity combination; the
  transition from fully-served to collapsed is a cliff. Per the WP4
  charter's own instruction, this is reported as a negative finding about
  the mechanism hypothesis rather than tuned until a curve appears —
  whether the cliff itself is realistic (a genuine capacity-ceiling
  effect) or an artefact of these scenarios' traffic/capacity shape is
  open, and is the natural next question for WP9's wider sweep.
- `[OPEN: WP9]` **`study_ul_access_chain`'s TwoTier arm never exercises SPS, so
  its flat curve above isn't evidence of an active anti-inversion
  mechanism.** The study's flows are `flow_class="PF"`
  (`scripts/scheduler_study.py`), which fails `_is_sps_eligible`'s
  `flow_class == "GBR"` gate (`scheduler/two_tier.py:466`) — so
  `_allocate_sps`/`_SPSReservation` (`two_tier.py:21-37`, `915`) never
  fire for these flows at all. "TwoTier (SPS-bypassed for these flows)"
  above (and in the study's own printed finding) describes a
  structurally-unexercised code path, not a confirmed suppressive
  mechanism. Separately: that SPS machinery is itself inherited-from-
  `main` scope CLAUDE.md says the Python two-tier shouldn't carry at all
  — real hardware defers SPS to a Phase 2 that was never built — so the
  TwoTier column of this study carries that fidelity mismatch on top,
  whether or not it happened to fire here. PF/RoundRobin are confirmed
  free of any SPS reference (`grep -rn "SPS" sim/baselines/*.py` — no
  hits), so the negative result's overall conclusion (no load-inversion
  found) is unaffected.
- `[OPEN: DECISION]` **WP4 exposed a pre-existing PF fairness weakness: identical
  scores tie-break by flow iteration order, not randomly or by any
  fairness-relevant tiebreaker.** `sim/baselines/pf.py`'s ranking sorts by
  `bits_per_rb / max(1.0, r_avg)`; many simultaneously-cold UEs with
  similar SNR can score identically, and Python's stable sort always
  resolves ties toward the same UEs (lower `ue_id`, since `_flows`
  iterates in scenario-declaration order). Under WP3's probe this rarely
  mattered (most UEs were eligible with substantial reported backlog most
  of the time, diluting the effect); under WP4's SR-gated eligibility
  (narrower windows, many simultaneously-cold UEs after a synchronised
  burst) it produces persistent starvation for a specific subset of UEs
  on `sensor_dense_scenario` (see `sim/tests/test_ul_access.py`). Not
  fixed — Phase 1 (§4) forbids scheduler logic changes in this WP, and
  the weakness is `pf.py`'s, not `ul_access.py`'s. Flagged for whoever
  next touches `pf.py`, not for WP4 to resolve.
- `[OPEN: WP9]` **The single largest-magnitude movement in WP4's regression
  diff is on non-GBR UL flows (`qfi8`/`qfi9`, PF-class), not the GBR
  flows WP4 targeted.** 135 of the 1706 mismatches, with deltas up to
  **+264ms** and several flows pegged at a ~300ms ceiling. This is the
  same phenomenon as the PF fairness weakness immediately above —
  SR-gated eligibility synchronizes cold-start bursts that PF's
  iteration-order tiebreak then starves — but the magnitude here is
  considerably larger than that item's framing implies on its own;
  re-read the two together, with this number in mind, before WP9
  characterizes either finding further.
- `[OPEN: WP9]` **Delay-class UL flows moved the opposite direction from GBR
  UL flows under the same WP4 change, and this isn't understood yet.**
  In `sensor_dense_scenario`'s PDCCH-limited case, Delay-class UL flows'
  (`qfi1`) p95/p98/p99 latency proxies moved *down* in ~80% of
  mismatches (SR improved their tail latency), while
  `factory_robots_scenario`'s GBR UL flows' same percentiles moved up in
  79-88% of mismatches under the same SR mechanism. Not chased before
  landing — worth understanding why the same UL access-chain change
  helps one flow class and hurts another before WP9 treats either result
  as representative of what SR does in general.
- `[OPEN: DECISION]` **RTSP/TCP UL/DL coupling (§6) is deliberately unbuilt in WP7.**
  Three candidate abstractions were analysed — cross-wiring the existing
  `adaptive` AIMD source's backoff signal from a paired video flow's DL
  delivery, a minimal windowed-RTT model, and a fixed offered-rate
  multiplier scoped to the specific guarantee test — and none was built.
  All three require uncalibrated constants with no ground truth anywhere in
  `oai-branches/` (which has no TCP or RTSP source at all), and the only
  consumers — G10's mixed-fleet (UGV+UAV) column and T9 — are both Phase 3,
  not now. Building any of them ahead of that consumer existing would carry
  invented parameters through WP5/WP6/WP-Join and contaminate their
  regression diffs for nothing. Consequence: **G10's mixed-fleet column and
  T9 are unanswerable until this is built.** See `docs/wp7-plan.md`'s
  Decision #2 for the full three-option writeup — a future revisit should
  start from that analysis, not redo it.
- `[RESOLVED]` **`FlowConfig.phase_jitter_ms` (WP7 commit 9, `976f09d`,
  `sim/cycle_clock.py`'s sync_group mechanism) defaults to 0.0 — no ground
  truth for a nonzero value, and that's the closed decision, not an open
  question.** A `sync_group`'s members are meant to model per-robot
  processing-time variance around a shared production-cycle tick, but
  nothing on disk (no spec, no `oai-branches/` source) gives a real number
  for how much that varies. Defaulting to 0.0 (no jitter, deterministic
  phase) is deliberate and consistent with every other jitter parameter
  this WP added (`periodic_control`'s `jitter_sigma_ms`, `xr_video`'s
  jitter both also default to off) — a scenario author who wants realistic
  variance must set a nonzero value explicitly, rather than inheriting an
  invented constant silently. Reopen only if/when a scenario actually
  needs correlated-burst jitter to be non-degenerate.
- `[RESOLVED]` **WP5's combining-gain composition stacks three uncalibrated
  constructs into one modelled retransmission success probability — closed
  by WP5 commit 2/6, `c669f96` (`bler_for_mcs_with_combining`, per
  `docs/wp5-plan.md` Decision 1b: "compose with today's `bler_for_mcs`;
  `bler_sigmoid` is not reintroduced").** Scoping WP5 (`docs/wp5-plan.md`
  Decision 1), the new per-attempt
  combining gain composes with `scheduler/link.py`'s already-shipped
  `bler_for_mcs` as `bler_for_mcs(threshold, true_snr_db +
  combining_gain_db(retx_count))`. Each of the three pieces is already
  individually flagged as not PHY-defensible on its own — `bler_for_mcs`'s
  "doubles per dB below threshold" slope, the ported `{0, 4.0, 6.5, 8.0}`
  dB IR-combining table (the mined `feat/harq-bler-retx` branch's own
  §11 calls these "approximations derived from... literature," no specific
  curve cited), and `base_bler=0.10` — but the *composition* was never
  flagged anywhere before this entry. A retransmission's modelled success
  probability is now the product of three things, none of which trace to
  a measurement. Recorded here rather than left implicit across three
  separate docstrings, same reasoning as `FIVE_QI_LCG`/`sr_period_slots`.
  Not blocking WP5 (no better numbers exist), but revisit together if any
  one of the three is ever recalibrated — recalibrating one in isolation
  changes the composed probability in a way none of the three docstrings
  alone would reveal.
- `[OPEN: PHASE2]` **WP5 commit 4a's per-flow HARQ masking is defeated,
  non-destructively, by `scheduler/two_tier.py::_allocate_sps`'s
  UE-level backlog pooling — measured at 3,628 occurrences across 13 of
  22 regression-corpus cases, all `TwoTier`, on commit 4a (DL only).
  **Confirmed to extend to UL on commit 4b, exactly as predicted**: total
  rose to 7,092 (including 1,220 hits on `study2/pdcch_limited`, an
  all-UL scenario) once UL grants could also be masked-and-pooled the
  same way. `_allocate_sps` sizes one
  UE's combined SPS grant off the *sum* of backlog across every
  SPS-eligible flow of that UE; masking a single pending flow's
  `bytes_queued` to 0 doesn't zero that sum if the UE has other,
  unmasked flows, so `_allocate_sps`/`_emit_grant` still hands the masked
  flow a nonzero share. `sim/driver.py`'s defensive guard
  (`harq_masked_flow_double_grant_count`) catches this before any
  `buffers.drain()` call and skips the delivery — **this is accounting
  drift, not FIFO corruption**: the pending retry's reserved bytes are
  never double-booked, so docs/wp5-plan.md commit 4a's correctness
  argument holds. What's left is real but contained: the skipped
  delivery's PRBs are wasted, and `TwoTier`'s own `_virtual_q`/
  `committed_this_slot` bookkeeping updates as though it delivered a
  share it didn't. **Deliberately not fixed**: `_allocate_sps` is exactly
  the SPS/Configured-Grant machinery CLAUDE.md already flags as
  shouldn't-exist-at-all (real hardware two-tier defers SPS to a Phase 2
  that was never built, and `scheduler/two_tier.py` gets rewritten fresh
  from OAI source in Phase 2, §4 above) — fixing accounting drift in a
  code path that's getting deleted, at the cost of docs/wp5-plan.md
  Decision 4's "zero scheduler changes" claim, is the wrong trade.
  **`harq_masked_flow_double_grant_count` is being kept as a permanent
  diagnostic, not a one-off debugging counter**: it reads 0 for every
  scheduler without UE-level-pooled SPS (confirmed: 0 on PF/RoundRobin/
  Gradient across the full corpus), so it doubles as a regression check
  for Phase 2 — **whoever rewrites `two_tier.py`/`reservation.py` fresh
  from OAI source must not reintroduce a backlog-pooling grant path that
  makes this counter nonzero again.**
- **Facet 3 (UL-access-chain dominance cluster, above) — WP5 commit 4b:
  HARQ retry can make UL delivery *worse*, not better, for cold-start-
  heavy traffic — a real result, not a defect.** Measured on
  `sensor_dense_scenario` (`ProportionalFair`):

  | `harq_round_max` / `k2_slots` | mean delivery |
  |---|---|
  | `harq_round_max=4` (default) | 0.471 |
  | `harq_round_max=1` (no retry — instant permanent loss) | 0.576 |
  | `k2_slots=1` (default is 2 — shorter retry gap) | 0.667 |

  **Mechanism:** commit 4a's full masking (a FIFO-correctness requirement
  — see that commit's own `[OPEN: PHASE2]` entry above and `docs/
  wp5-plan.md` commit 4a — not a modeling choice) blocks a retrying flow from
  receiving *any* new grant, including a fresh SR-triggered cold-start
  grant, for the whole retry cycle (`k2_slots` × however many retries it
  takes). For traffic dominated by small, one-shot-completion messages —
  exactly what WP4's SR report floor exists to serve — sitting out the
  official retry costs more than failing fast and catching a brand-new
  grant next opportunity, since the channel condition causing the
  failure is often transient. **Confirmed NOT cross-flow masking
  compounding**: zero UEs in `sensor_dense_scenario` have more than one
  UL flow, so this is a single-flow effect, not masking blocking a
  sibling flow while one retries.

  **Not fixed, deliberately, on either axis**: masking stays full-
  strength (weakening it would trade a correctness requirement for a
  metric); `k2_slots`'s default stays 2 (the midpoint of the real 1-4
  slot TDA range at μ=1, Decision 3, `docs/wp5-plan.md`) rather than
  retuned to whatever value happens to pass a test — that is exactly the
  invented-parameter pattern this branch has avoided everywhere else
  (`FIVE_QI_LCG`, `sr_period_slots`). That `k2_slots=1` recovers delivery
  is recorded as the sensitivity **WP9 should sweep**, not a new default.

  **This is Facet 3 of the UL-access-chain dominance cluster above, read
  together with Facets 1 (crumb fraction) and 2 (load-inversion absent),
  not a separate item**: commit 4b's own re-measurement of Facet 1 moved
  it again, 4.4503% → 4.9558% crumb fraction (corrected post-WP5-end-of-
  WP-review; see CLAUDE.md's known issues), mean crumb size 146.03 →
  134.44 bytes, same direction as WP4's own move, still far short of
  hardware. All three (plus Facet 4 below) look like facets of one
  thing: **the uplink access chain dominates outcomes at low load and
  for small messages, more than the scheduling policy layered on top of
  it does.** WP9 should test this hypothesis directly across its full
  sweep, not as four separately-filed items that happen to rhyme.
- `[OPEN: PHASE2]` **WP5 commit 6: OLLA's round-count MCS ratchet
  (`get_mcs_from_bler`) is ported bug-for-bug and unit-tested, but doesn't
  reach grant sizing — it's landed dormant, the same way WP1's `sim/
  power.py` was.** This simulator has no persistent per-UE MCS anywhere
  grant sizing reads (link adaptation here is entirely stateless: a
  function of instantaneous, possibly-CQI-delayed SNR). Real hardware's
  `get_mcs_from_bler` output reaches exactly one call site — it directly
  becomes the grant's MCS before TBS sizing. The only route to feed a
  ratcheted value in without touching scheduler code is wrapping
  `ChannelModel.get_reported_snr_db()` (matching the pattern already used
  for HARQ's `HarqAwareBufferView`/`ReducedSlotView`) — but every current
  scheduler calls that same method for things that have nothing to do
  with MCS selection: PF's ranking, `TwoTier`'s `_r_avg`, Tier-1's
  capacity estimates. Wrapping it would feed OLLA's ratcheted value into
  every one of those unrelated reads too, silently distorting scheduler
  behaviour that no test checks and no metric attributes to OLLA — not a
  fidelity trade-off, a different mechanism wearing OLLA's name. **Not
  built**: activation belongs in Phase 2's fresh scheduler rewrite, where
  MCS selection can live at the one call site it actually needs to.
  `sim/olla.py` is ready for that — pure functions/dataclasses, unit-
  tested against the C's exact -1/+1 asymmetry (`docs/wp5-plan.md`
  commit 6) — Phase 2 needs to design the per-UE manager/wiring, not
  re-derive the ratchet itself.

  **The compounding-vs-coincidence test designed while scoping this
  commit couldn't run with OLLA dormant — recorded here so it isn't lost
  before Phase 2 activates it**: compare per-UE aggregate degradation
  (not per-flow) between UEs with *both* a low-rate/OLLA-ratcheted DL flow
  and a low-rate/SR-access-chain-limited UL flow, against UEs with only
  one condition. Additive degradation (sum of each mechanism's isolated
  effect) is coincidental co-occurrence; supra-additive degradation is a
  genuine interaction worth naming as such, rather than three items
  (this one, WP4's load-inversion result, the crumb-fraction shortfall)
  that only rhyme. Full method in `docs/wp5-plan.md` commit 6.
- `[OPEN: PHASE2]` **Reservation's "liveness" sort tiers — UL's tiers 2
  (`liveness`) and 4 (`sched_inactive`-last), and DL's tier 2
  (`liveness`, TA-pending) — all need a signal the `Scheduler` protocol
  does not expose today, one root cause across both directions.** UL's
  `liveness`/`sched_inactive` need a `do_sched`-equivalent: an
  SR-or-inactivity trigger that schedules a UE despite zero real backlog
  (`nr_UE_is_to_be_scheduled`, `gNB_scheduler_ulsch.c:2161-2165`).
  `sim/ul_access.py`'s SR-report-floor mechanism is not a usable proxy for
  it: verified it is invoked only when `bytes_queued > 0`
  (`sim/bsr.py:381-392`'s own docstring, "while the flow actually has
  data queued") — it exists to fix crumb-collapse-with-real-data, not to
  represent a genuinely-empty UE being kept alive. **DL's `liveness` has
  the identical problem for a different missing signal, found finishing
  the same scoping pass**: `gNB_scheduler_dlsch.c:840` —
  `UE_sched[numUE].liveness = sched_ctrl->ta_apply && !dl_has_srb;` — DL's
  liveness is Timing-Advance-pending, and this simulator has no TA
  modeling anywhere (`sim/`+`scheduler/` grepped for any TA/timing-advance
  concept — nothing). Neither SR/inactivity-keepalive state nor TA state
  reaches the `Scheduler` protocol today, for any scheduler. A UL flow
  with truly zero backlog never becomes a scheduling candidate at all
  today (this gap is currently unobservable — no scenario produces the
  triggering condition on either side). **Not built in reservation commit
  2**: the UL comparator lands 3 tiers (SRB → GBR → PDB/coef) instead of
  the ground-truth 5, and DL lands 3 instead of 4, with the missing tiers
  documented as a placeholder in `docs/oai-port-map.md`, not silently
  dropped. **What would unblock it**: a real `do_sched`/TA-equivalent
  signal sourced from `sim/ul_access.py::UlAccessModel`'s existing
  SR-pending state (UL) or a new TA model (DL, doesn't exist at all),
  threaded through `sim/driver.py` to a new `BufferStateView` field or
  `BufferView`/`ChannelView` method — a cross-cutting `Scheduler`-protocol
  change affecting every scheduler, not a reservation-specific one, and
  therefore its own fidelity change in its own commit if taken up, not
  folded into a sort-tier commit. Revisit if a future scenario ever needs
  a zero-backlog UE to be schedulable, or TA to be modeled, at all.
- `[OPEN: PHASE2]` **Reservation's `has_srb` tier — the TOP tier in
  BOTH comparators — has no data source at all, for a more fundamental
  reason than the liveness gap above: this simulator has no SRB/
  RRC-signaling traffic model whatsoever, found in the same scoping
  pass.** UL's `has_srb` requires LCG0 to hold data that is genuinely
  SRB, explicitly excluding a DRB that happens to map to LCG0
  (`gNB_scheduler_ulsch.c:2167-2177`, the `lcg0_is_drb` check); DL's
  requires `rlc_status[1]`/`[2]` (LCID 1/2, the real SRB1/SRB2 identity)
  to hold data (`gNB_scheduler_dlsch.c:830-831`). `scheduler/flow.py
  ::FlowConfig` has no concept of an SRB flow at all — every `FlowConfig`
  is a QFI-based DRB; `FIVE_QI_LCG`'s LCG0 mapping (QFI 1/3, voice/
  gaming) is ordinary GBR *DRB* traffic sharing LCG0, which is exactly
  the case the C's own `lcg0_is_drb` check excludes from `has_srb` — so
  even a naive "LCG==0" heuristic would be a wrong port, not a merely
  degraded one. **This is a different category of gap than the liveness
  one above**: not a missing wire from already-existing simulator state,
  but a missing traffic model entirely — no scenario, `FlowConfig`, or
  generator anywhere represents RRC signaling. Building it is squarely
  out of Phase 2's scope (both schedulers, not new traffic modeling), so
  this isn't a "revisit when a scenario needs it" item the way the
  liveness gap is; it's a standing, permanent limitation of this
  simulator's traffic model. **Decided**: `has_srb` is implemented as a
  real, structurally-complete comparator tier, hardcoded `False` for
  every candidate — keeping the comparator's shape faithful (ready for a
  hypothetical future SRB-modeling commit to supply the flag) without
  inventing behavior around a concept this simulator doesn't have.
  Recommendation: leave unbuilt — no current guarantee/hypothesis in
  this repo depends on SRB-tier differentiation, and real SRB traffic
  modeling is a materially larger undertaking than this WP's scope.
- `[OPEN: PHASE2]` **Reservation's UL-only "silence detection" deficit
  reset (`gNB_scheduler_ulsch.c:2286-2296`) is not built — found in the
  same source range as commit 3's GBR/BE split, not one of that
  commit's four named elements.** If a UE goes silent (`B==0`) while
  carrying a pending GBR obligation for longer than its best pending
  PDB, every one of its LCGs' deficit resets to 0 — a starvation-guard
  against a permanently-inflated deficit from an app that stopped
  sending. No DL equivalent appears in `gNB_scheduler_dlsch.c` (plausible:
  it's gated on `B`, a UL-only BSR-collapse concept — DL's own deficit
  accumulates unconditionally regardless of buffer state, so it has no
  analogous runaway-deficit risk from silence in the first place; see
  the has_gbr/pdb port-map rows for that asymmetry). **Not built**:
  land the four named elements first (done, commit 3); revisit this as
  its own commit if a scenario's deficit behavior during a long UL
  silence turns out to matter.
- `[OPEN: PHASE2]` **Reservation's grant-sizing target
  (`ul_target`/`dl_target = guaranteed_bytes + be_bytes`,
  `gNB_scheduler_ulsch.c:2496`/`_dlsch.c:1009`) is computed by commit 3
  but not yet consumed — grant sizing stays backlog-based.** Tracked as
  `docs/phase2-plan.md`'s reservation checklist item 4a (alongside
  commit 4's follower budget, which also needs a demand estimate), not
  left as a bare flag here — see that document for the actual
  commit-sequencing decision.
- `[RESOLVED]` **WP6: correlated multi-UE blockage and AGV mobility are
  deliberately not built — closed by the WP6 plan, `docs/wp6-plan.md`
  Decision 7 (scoped in commit `7648475`, before any WP6 code landed,
  unrevisited since WP6's own end-of-WP review `eccdb72`).**
  `p5g-sim-plan.md` §9's WP6 file list names
  `sim/mobility.py` as "New, optional... so blockage correlates across UEs
  sharing an aisle." Decided not to build it (`docs/wp6-plan.md`
  Decision 7): no guarantee in §5's G1-G12 traceability table names
  correlated multi-UE blockage specifically, per-UE independent blockage
  already gives WP6's own acceptance criterion something to test, and this
  is the same treatment §3 already gave UE mobility/OLLA when scoping the
  branch ("revisit only if a specific GT/T test fails and \[mobility\] is
  the diagnosed cause"). Not an oversight — recorded here so the spec's
  file list doesn't silently imply otherwise.
- **Facet 4 (UL-access-chain dominance cluster, above) — WP6 commit 4:
  blockage x HARQ retry interaction confirmed — a single flow's residual
  HARQ loss under long blockage exceeds WP5's entire prior corpus, and
  the mechanism is narrower than first assumed.**
  `Allocation.snr_used_db` freezes a TB's MCS threshold at its original
  grant and reuses it unchanged across every retry (`sim/harq.py::
  HarqProcess.snr_used_db`) — a fresh grant issued *while already blocked*
  gets a threshold matched to the current (degraded) SNR and sees no
  mismatch at all; only a TB whose threshold was committed *before* true
  SNR dropped and evaluated *after* is at risk. At the driver's bare
  `cqi_delay_slots=0` this only happens for the rare TB caught mid-retry
  at the exact transition instant (measured: long-blockage
  `bytes_harq_lost` ranged 0-6193 across 7 seeds, overlapping the
  no-blockage baseline on several). At `cqi_delay_slots=8`
  (`scripts/scheduler_study.py::CQI_DELAY_SLOTS` — the value every real
  study in this branch actually runs with, not the bare default) every
  fresh grant in the ~8 slots after a transition inherits the stale
  threshold, and the effect becomes dramatic and reliable: no-blockage
  and short-blockage (4 slots, below the ~18-slot DL retry cycle) stayed
  in 0-800 bytes on 7 of 7 seeds; long-blockage (600 slots) stayed in
  5200-21514 bytes on the same 7 seeds — non-overlapping. That range
  alone, from one flow in one run, exceeds WP5's own measured total
  (`bytes_harq_lost` nonzero on only 6 of 510 flow-records across the
  entire 22-scenario/3-study corpus, `docs/wp5-plan.md` commit 4b).
  Demonstrated in `sim/tests/test_wp6_blockage_harq_interaction.py`, kept
  deliberately outside the regression corpus (`docs/wp6-plan.md` §4: a
  multi-configuration hypothesis test, not a fixed-baseline scenario).
  **This is Facet 4 of the UL-access-chain dominance cluster above** —
  the fourth facet of the same underlying story, per WP9's wider sweep —
  not chased further here.
- `[RESOLVED]` Branch strategy: fresh rebuild off `main`, stale branches
  not merged (§2, §3).
- `[RESOLVED]` Phase ordering: simulator fidelity fully before either
  scheduler is written (§4), superseding `p5g-sim-plan.md` §5.5's
  original early-reservation sequencing, with the regression-corpus
  mitigation noted in §2.
- `[RESOLVED]` This README, not an edit to `p5g-sim-plan.md`, is the record
  of every place the two documents disagree. `p5g-sim-plan.md` is left
  unmodified as the historical planning document; this README is
  authoritative wherever the two conflict (§0 above states this per
  section).
- `[RESOLVED]` **`fa8232b` ("WIP WP4") bundled three logical changes in one
  commit, and its regression-check predictions were checked against
  `scripts/regression_corpus.py --check`'s actual output (1706 mismatches)
  — left unrewritten (already pushed; not worth a force-push on this
  branch) but recorded here for legibility.** The three units: (1) core
  mechanism — `sim/ul_access.py` (new SR state machine), `sim/bsr.py`,
  `sim/driver.py`, `sim/tests/test_ul_access.py` (new),
  `sim/tests/test_bsr.py`, `sim/tests/test_smoke.py` — replacing WP3's
  cold-start probe; (2) `scripts/scheduler_study.py`'s Study 4
  (`study_ul_access_chain`), the SR-chain load-inversion sweep; (3) the
  `README.md`/`docs/oai-port-map.md` updates described elsewhere in this
  section.

  Prediction scorecard, checked against the actual mismatches rather than
  assumed: **M11** (UL PRB utilization) predicted up; actual 15/15
  mismatches moved *down*, and only at overload_mult ≥1.5× / study2's
  PDCCH-limited case, never at 1.0× — SR's wait-for-PUCCH-occasion delay
  removes utilization headroom under saturation rather than adding it via
  crumb grants. **M12** (CCE/PDCCH utilization) predicted up; actual mostly
  down (12/19 mismatches) — matches `test_smoke.py`'s own rationale for
  lowering its PDCCH-utilization assertion (0.4→0.3): SR reduces
  PDCCH-eligible UEs per slot as load rises; only the lowest-load case
  moved up, and only slightly. **GBR UL p95/p98/p99** predicted worse —
  the one prediction that held (79-88% of mismatches moved as predicted).
  **GBR UL p50** predicted flat; actual moved in *more* cases (110) than
  any higher percentile, with a mean absolute delta (1.86ms) comparable to
  p98/p99's — not flat.

  Also surfaced, unpredicted: **DL PRB utilization** moved for **PF only**
  (4 mismatches, all up) even though WP4 touches no DL code — traced to
  `sim/baselines/pf.py`'s per-UE (not per-direction) `_r_avg` EWMA, shared
  between a UE's UL and DL flows, so WP4's change to UL grant timing
  perturbs that UE's DL competitive ranking in later slots. Verified
  causally: sweeping only `sr_period_slots` (10→1, a UL-only knob) shifts
  PF's per-UE DL PRB counts by a few PRBs each, while TwoTier's and
  RoundRobin's `dl_prb_utilization` stay bit-for-bit identical across the
  same sweep — confirming this is PF's shared-rate design, not a TwoTier
  Tier-1 boundary leak. The other unpredicted, larger-magnitude movements
  (non-GBR UL flows, Delay-class UL flows) are their own `[OPEN: WP9]`
  items above.

---

## 9. Repository layout (this branch)

```
.
├── README.md                     this document — start here
├── docs/
│   ├── p5g-sim-plan.md            original fidelity + regime-map plan (WP technical detail, H1-H7, base metric panel)
│   ├── IA_P5G_Factory_Guarantee_Test_Plan.md    authoritative G1-G12 + GT-0..GT-7 test families
│   └── IA_P5G_Guarantee_Validation_Suite.md     earlier draft; mined for mechanism detail only
├── oai-branches/                 verified OAI source, ground truth for Phase 2 (§7)
│   ├── README.md                 why these are kept separate per-branch
│   ├── two-tier/                 gNB_scheduler{,_dlsch,_ulsch,_uci}.c, nr_ue_procedures.c, ia_p5g_scheduler.{c,h}
│   ├── reservation/               gNB_scheduler{,_dlsch,_ulsch}.c (no ia_p5g equivalent)
│   ├── Sweep_Orig_vs_TwoTier.xlsx N=2 UE admissible-load sweep, 6 points, 3 runs/pt medians (§7, §8)
│   └── Sweep_Orig_vs_TwoTier.csv  plain-text extraction of the above
├── calibration-logs/              real deployment captures (README.md there for provenance)
│   └── twotier_startup_gnb.log    one gNB startup log, two-tier config — RRC/MAC timer constants only, no traffic data
├── scheduler/                    [Phase 2] two_tier.py, reservation.py — rewritten from §7, not ported from main
├── sim/                          [Phase 1] channel.py, buffer.py, traffic.py, driver.py, metrics.py, harq.py (new), join.py (new) — rebuilt per §4
└── scripts/                      [Phase 3] regime_sweep.py, regression_corpus.py, scorecard.py
```

---

## 10. Definition of done

**Phase 1 exit criteria:** every WP0–WP-Join acceptance criterion in
`p5g-sim-plan.md` §9 (extended per §6) met; regression corpus green against
`sim/baselines/`; WP4's SR-chain inversion reproduced within the right
order of magnitude (the branch's only real calibration target, per
`p5g-sim-plan.md` §11).

**Phase 2 exit criteria:** both schedulers pass the acceptance criteria in
§4's table above; `n_followers=0` reservation reduces to plain PF
(retroactively explains the historical N=2 tie); two-tier's UL floor fires
and disarms correctly under the fruitless-counter logic.

**Phase 3 exit criteria:** WP9's grid complete, regime-selection discipline
satisfied (no 0%-loss-on-both-arms cells reported), H1–H7 each resolved
(confirmed, refuted, or inconclusive-with-reason), guarantee traceability
table (§5) fully populated with sim-answerable G1–G12 results, and every
`[OPEN]` item in §8 either closed or explicitly carried to the hardware
campaign. Checkable by grep against §8's tags as of the Phase 1→2 triage:
**19 open entries** remain (7 `[OPEN: WP9]`, including the 4-facet
UL-access-chain dominance cluster counted once; 6 `[OPEN: PHASE2]`; 2
`[OPEN: HARDWARE]`; 3 `[OPEN: DECISION]`; 1 dual `[OPEN: HARDWARE/
DECISION]`) plus whatever new items Phase 2/3 add using the same
open-ended tag vocabulary (§8 preamble). "Closed" means flipped to
`[RESOLVED]` with a citation of what closed it; "carried to the hardware
campaign" means still tagged `[OPEN: HARDWARE]` (or the hardware half of
a dual tag) at this gate — `[OPEN: WP9]`/`[OPEN: PHASE2]`/`[OPEN:
DECISION]` items must resolve some other way (a completed sweep, the
Phase 2 rewrite landing, or an owner decision) before this gate, not
default into "carried to hardware."
