# feat/high-fidelity-sim — a realistic 5G QoS simulator, and the two-tier-vs-reservation regime map

**Status:** Phase 1 in progress — WP0, WP1, and WP3 landed (§4). This branch is a
rebuild, not a patch — nothing in `scheduler/` or `sim/` from `main` is
assumed correct or reused as-is.
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
| 5 | WP7 | Factory traffic generators, correlated bursts, XR video model | `p5g-sim-plan.md` §9, extended per §6 below (UAV/MAVLink heterogeneous cadence, RTSP/TCP coupling) | Pending |
| 6 | WP5 | HARQ: N processes/UE/direction, k1/k2, RTT, per-attempt combining gain, max-retx residual loss | `p5g-sim-plan.md` §9; combining-gain formula reused from `feat/harq-bler-retx` (§3) | Pending |
| 7 | WP6 | Channel: TR 38.901 InF path loss + two-state Markov blockage | `p5g-sim-plan.md` §9, extended per §6 below (sync-loss threshold feeding WP-Join) | Pending |
| 8 | **WP-Join** *(new)* | Join / re-join / RLF-recovery state machine | §6 below — not in `p5g-sim-plan.md` at all | Pending |

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
| G9 | Fast join / re-join | **Join/RLF state machine — does not exist yet** | **WP-Join** | **No, until WP-Join lands** |
| G10 | Admissible fleet size | N-sweep (this is what simulation buys that hardware can't — `p5g-sim-plan.md` §2) | Phase 3 | Yes |
| G11 | Holds for a shift, reproducibly | Long-run soak, communication service availability metric (new, §6) | WP0 metric panel, WP7 | Yes |
| G12 | Ordered degradation under overload | First-violation-order metric (already in panel) | Phase 3 | Yes |

**G9 is the one guarantee this simulator currently cannot address at all**,
not just imprecisely — there is no concept anywhere in `sim/` of a UE
joining, leaving, or losing sync mid-run. This is why WP-Join is a named
work package rather than a line item under WP6 or WP7.

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
  anchor: `contention.log`'s startup banner gives the actual OAI timer
  constants — `t300 400, t301 400, t310 2000, n310 10, t311 3000, n311 1,
  t319 400` (ms/counts) — real values from the deployed gNB config, not
  invented ones.
- **`[OPEN]`** WP-Join's attach/RACH/reestablishment timing should be a
  **calibrated delay distribution keyed to the timers above**, not a
  contention-based RACH simulation (preamble collision probability etc.).
  Full RACH contention is PHY-layer fidelity the simulator's own
  non-goals correctly exclude, and no G9/GT-6/T8 pass criterion needs it —
  they need realistic *timing*, not realistic *contention resolution*.
  This needs your sign-off before WP-Join is built, since it's a scope
  boundary, not an implementation detail.

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

- `[OPEN]` WP-Join's RACH/RLF depth: calibrated delay distribution
  (recommended, §6) vs. contention-based simulation. **Needs confirmation
  before WP-Join is built.**
- `[OPEN]` `T_live` (MEC liveness timeout) — assumed 2 s in the guarantee
  docs; both `p5g-sim-plan.md` and the guarantee test plan flag this as
  unconfirmed. Calibrates every G3/G9 pass line.
- `[OPEN]` The uplink capacity constant (`p5g-sim-plan.md` §4.2) — resolve
  against GT-3.2's ceiling re-measurement, or sweep it as an axis.
- `[OPEN]` InF sub-scenario (SL/DL/SH/HH) for the headline configuration —
  deployment-dependent, sweep in WP6 rather than picking blind.
- `[OPEN]` Survival-time threshold N (`p5g-sim-plan.md` §7) — start at 3,
  report H6 as a function of N.
- `[OPEN]` **WP3 exposed a UL scheduling deadlock that only WP4 can properly
  close.** Every scheduler's UL eligibility gate (`bytes_reported > 0`) is
  refreshed only by a grant, and a grant requires the gate to already be
  open -- a deadlock for any flow whose real backlog goes from empty back
  to non-empty (most bursty UL traffic here), not just a one-time cold
  start. Real 5G breaks this with a Scheduling Request on PUCCH, a
  control-channel signal needing no existing grant (WP4). Until WP4 lands,
  `sim/bsr.py::BsrModel.broadcast()` reports a flow's true backlog directly
  whenever its per-LCG estimate is exactly 0 -- a stopgap that is
  load-bearing for every scenario's basic UL throughput today, not
  a corner case. It does not defeat the crumb-collapse mechanism itself
  (a nonzero estimate capped to 0 by `B` still gates correctly). See
  `design-docs/scheduler-study.md` §5.1 for detail. **WP4 should treat
  properly retiring this stopgap as part of its acceptance criteria, not
  an optional cleanup.**
- `[OPEN]` **The load-inversion calibration target's full source data, and
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
- `[OPEN]` H5 (`p5g-sim-plan.md` line 338, "two-tier degrades as
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
- `[OPEN]` **`FIVE_QI_LCG` (`scheduler/flow.py`) is an invented mapping with
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
- `[OPEN]` **WP3's crumb fraction falls well short of the charter's
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
- `[OPEN]` **The load-inversion calibration target (§7/§11) does not
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
- `[OPEN]` **`study_ul_access_chain`'s TwoTier arm never exercises SPS, so
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
- `[OPEN]` **WP4 exposed a pre-existing PF fairness weakness: identical
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
- `[OPEN]` **The single largest-magnitude movement in WP4's regression
  diff is on non-GBR UL flows (`qfi8`/`qfi9`, PF-class), not the GBR
  flows WP4 targeted.** 135 of the 1706 mismatches, with deltas up to
  **+264ms** and several flows pegged at a ~300ms ceiling. This is the
  same phenomenon as the PF fairness weakness immediately above —
  SR-gated eligibility synchronizes cold-start bursts that PF's
  iteration-order tiebreak then starves — but the magnitude here is
  considerably larger than that item's framing implies on its own;
  re-read the two together, with this number in mind, before WP9
  characterizes either finding further.
- `[OPEN]` **Delay-class UL flows moved the opposite direction from GBR
  UL flows under the same WP4 change, and this isn't understood yet.**
  In `sensor_dense_scenario`'s PDCCH-limited case, Delay-class UL flows'
  (`qfi1`) p95/p98/p99 latency proxies moved *down* in ~80% of
  mismatches (SR improved their tail latency), while
  `factory_robots_scenario`'s GBR UL flows' same percentiles moved up in
  79-88% of mismatches under the same SR mechanism. Not chased before
  landing — worth understanding why the same UL access-chain change
  helps one flow class and hurts another before WP9 treats either result
  as representative of what SR does in general.
- `[OPEN]` **RTSP/TCP UL/DL coupling (§6) is deliberately unbuilt in WP7.**
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
- `[OPEN]` **`FlowConfig.phase_jitter_ms` (WP7 commit 9, `sim/cycle_
  clock.py`'s sync_group mechanism) defaults to 0.0 — no ground truth for a
  nonzero value.** A `sync_group`'s members are meant to model per-robot
  processing-time variance around a shared production-cycle tick, but
  nothing on disk (no spec, no `oai-branches/` source) gives a real number
  for how much that varies. Defaulting to 0.0 (no jitter, deterministic
  phase) is deliberate and consistent with every other jitter parameter
  this WP added (`periodic_control`'s `jitter_sigma_ms`, `xr_video`'s
  jitter both also default to off) — a scenario author who wants realistic
  variance must set a nonzero value explicitly, rather than inheriting an
  invented constant silently. Revisit if/when a scenario actually needs
  correlated-burst jitter to be non-degenerate.
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
  (non-GBR UL flows, Delay-class UL flows) are their own `[OPEN]` items
  above.

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
campaign.
