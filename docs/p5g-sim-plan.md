# factory-sim-v2 — fidelity, a reservation baseline, and a regime map

**Status:** Plan. No code written. `[OPEN]` marks decisions deliberately
deferred to the experiment rather than settled in advance.
**Branch:** `factory-sim-v2`

**The question this branch answers:** for an indoor private-5G automated
factory floor, in which operating regimes does the two-tier scheduler beat the
reservation-based scheduler, in which does it lose, and by how much — expressed
in the guarantees a factory operator actually buys.

---

## 0. Read this first

If you are picking this up cold, read in this order:

1. **§1** — what the system must guarantee. The functional objective.
2. **§2** — the three-layer structure. Where this branch sits and what the
   other two documents do.
3. **§3** — why the existing hardware comparison proved nothing. This is the
   motivation and it is not the obvious one.
4. **§4** — the deployment being modelled. Concrete flows, rates, 5QIs.
5. **§7–§8** — the metric panel and the hypotheses. What gets measured.
6. **§9** — the work packages, in order.

**Companion documents.** All three describe the same system at different
altitudes and must stay consistent:

| Document | Layer | Answers |
|---|---|---|
| `IA_P5G_Factory_Guarantee_Test_Plan.md` | hardware, client-facing | *What am I promised if I put my fleet on this?* |
| `IA_P5G_Scheduler_Benchmark_Suite.md` | hardware, engineer-facing | *Which mechanism works where, and why does it break?* |
| **this document** | simulation | *Where should each scheduler be deployed, and can we find out without burning testbed time?* |

Also relevant: `02_System_Architecture.docx` (MEC system, asset types),
`simulator-design.md` (what the simulator models today),
`adoption-decision.md` (the opposed-metrics problem this plan inherits),
`oai-phase1-review.md` (the OAI port this branch must track), `NOTES.md`.

---

## 1. Functional objectives

The system under test is a private-5G network carrying a fleet of ground robots
(UGVs) and drones (UAVs) to a MEC edge server. Only the **asset ↔ MEC boundary**
crosses the air interface; the MEC ↔ operator-UI leg is wired and out of scope.

**A factory operator does not buy latency percentiles. They buy twelve
guarantees.** These are the functional objectives, and every simulation result
must eventually be expressible as evidence for or against one of them.

| ID | Guarantee, as the client states it |
|---|---|
| **G1** | Every drive command reaches the robot in time to feel responsive |
| **G2** | A STOP always lands, on every ground robot, fast — even at worst-case load |
| **G3** | The network never makes a healthy robot look dead |
| **G4** | After a robot goes quiet, its next message still arrives promptly |
| **G5** | Operators and the AI always see fresh, complete video |
| **G6** | Background traffic can never impair the fleet |
| **G7** | One misbehaving robot cannot take down the others |
| **G8** | Robots of equal entitlement get equal service — continuously, not on average |
| **G9** | A robot joins, or re-joins after an outage, quickly even on a busy cell |
| **G10** | The cell hosts a stated fleet size with all of the above intact |
| **G11** | The guarantees hold for a whole shift, and reproduce run to run |
| **G12** | Under genuine overload, degradation follows the safety order |

Full normative KPI definitions live in the guarantee test plan §3 and §5. The
subset this branch can address is §7.

**Two architecture facts drive everything below.**

**Liveness is inferred from traffic.** There is no separate keep-alive channel.
The MEC declares a session lost when telemetry stops, and a lost session makes
ground robots stop and drones fall to autopilot failsafe. **The scheduler is
therefore inside the liveness loop**, and the known BSR-desync / candidacy-loss
failure mode of the uplink path is not a performance nuisance — it is a
false-failsafe generator. G3 exists to bound it.

**Video inference is latest-frame-only.** A late frame is discarded, not
queued. So the correct video KPIs are PDU-set completeness within deadline and
frame *age* at the MEC — sustained Mbps proves nothing.

---

## 2. The three layers, and what simulation is for

```
   G1..G12  guarantees          <- IA_P5G_Factory_Guarantee_Test_Plan (hardware)
      |  detects THAT a guarantee fails
      v
   F0..F8   mechanisms          <- IA_P5G_Scheduler_Benchmark_Suite (hardware)
      |  localises WHY it fails
      v
   this branch: regime map      <- factory-sim-v2 (simulation)
         predicts WHERE each scheduler holds which guarantee
```

**What simulation buys that hardware cannot.** The discriminating regime is
unknown and must be located by search — many UE counts, load levels, burst
structures, channel conditions and deadline ratios, each with enough seeds to
resolve an effect. That search is affordable in simulation and is not
affordable on OAI. Two guarantees in particular are effectively unreachable on
the testbed:

- **G10 (admissible N)** requires sweeping fleet size. The testbed has two UEs.
- **G12 (degradation order)** requires driving the cell through overload
  repeatedly, which is slow and destructive on hardware.

**What simulation does not buy.** Certifiable numbers. Every latency bound that
reaches the client's Guarantee Sheet comes from real RF. The simulator's output
is a **map telling the hardware campaign where to look**, and a set of
falsifiable predictions the campaign then confirms or refutes.

**Feedback direction.** The regime map should shape which GT tests get real-RF
window time and at what load points. If the map says the arms are
indistinguishable below N=6, the hardware campaign should not spend its RF
window comparing them at N=2.

---

## 3. Why this branch exists

The two schedulers have been compared on hardware (OAI, 5QI-1 uplink,
`compile_twotier.py`, N=2 UEs). The working conclusion from those runs — *"two-tier
does not beat reservation"* — **is not supported by the data.** Three
independent reasons.

**3.1 The measurements are underpowered.** At n=5 runs, uplink-QoS p99 is
26.31 ms [17.36–50.49] for the reservation arm against 41.25 ms [24.74–67.48]
for two-tier. Those intervals overlap across most of their range. Downlink is
statistically indistinguishable in every percentile. No effect of the size the
schedulers plausibly produce is resolvable at that sample count.

**3.2 The reservation mechanism was never engaged.** Its central lever is

```
budget = bwpSize − n_followers_need × min_rb
```

At N=2 UEs, `n_followers_need` is 0 or 1, so `budget ≈ bwpSize` and the
scheduler degenerates to plain proportional fair. The admissible-load sweep
(`Sweep_Orig_vs_TwoTier.xlsx`, 45%→145% offered load, 3 runs/point) records PASS
for both arms at every point with 0% loss and worse-of-two p99 far under the
100 ms bound, and concludes the two schedulers are equivalent at N=2. **That is
the expected result when one of them is switched off.**

**3.3 Low-load points measure the wrong thing.** The sweep's p99 is *inverted*
in load: 67.25 ms at 45% offered load falling to 12.98 ms at 125%. A queueing
system does not behave that way. The signature is the uplink grant-acquisition
chain — at low load a UE has no standing grant, so each burst pays a full
SR → grant → BSR → grant round trip. Neither scheduler controls that latency.
Points P1 and P2 therefore carry no information about scheduling policy.

The one point where the arms separate is P6 (145% load): reservation p99
33.09 ms against two-tier 15.90 ms — the only measurement consistent with
divergence under stress, currently attributed to a capture artefact.

**Restatement.** The honest position is not "two-tier loses." It is **"no
experiment has yet been run in a regime where the two schedulers could
differ."** This branch's job is to find that regime, not to explain a loss that
has not been demonstrated.

---

## 4. The deployment being modelled

Taken from the guarantee test plan §1–§2 so that simulated flows correspond to
real ones. **Do not model abstract "flow 1, flow 2" — model these.**

### 4.1 Traffic classes

| # | Stream (dir) | Model | Why its delivery is critical |
|---|---|---|---|
| T1 | **Telemetry / heartbeat (UL)** | low-rate periodic, 10 Hz × ~300 B; shares one bidirectional port with T2 | **Liveness.** A stall here is a false failsafe: robots stop |
| T2 | **Commands (DL)** | `cmd_vel`, gimbal, flight-mode, and the disconnect **STOP**; same port as T1 | **Safety and controllability.** A late STOP is what a safety review asks about first |
| T3 | **Camera video (UL)** | RTP/H264 push or RTSP pull; frame = PDU set | **Perception.** Latest-frame-only: freshness and completeness, not throughput |
| T4 | **Lidar / bulk sensor (UL)** | msgpack sweeps, bursty | Situational awareness; deliberately isolated from T1/T2 |
| T5 | **Handshake (UL/DL)** | UDP :9000 capability exchange; also re-handshake after liveness loss | **Fleet elasticity.** Join and recovery time |
| T6 | **Best-effort (both)** | logs, mission data, firmware | Must never impair T1–T5; must still progress |

**T1 and T2 share a single bidirectional bearer.** Any model of the control
loop that is unidirectional is modelling half of it.

### 4.2 The `factory_fleet` QoS profile

The current provisioning is a flat 5 Mbps GBR on all flows, which breaks the
comparison twice over: a heartbeat with a 5 Mbps GFBR is never meaningfully
"within GFBR" so PDB conformance semantics do not attach; and 2 assets × 3 ×
5 Mbps = 30 Mbps committed likely exceeds the uplink ceiling, so the committed
portfolio is infeasible before anything runs.

**Model this profile instead:**

| Flow | 5QI | PDB / PER | GFBR | MFBR | Offered (nominal) |
|---|---|---|---|---|---|
| sensor / telemetry | **1** | 100 ms / 10⁻² | 0.5 Mbps | 2 Mbps | ~24 kbps UGV, 10–30 kbps UAV |
| camera | **2** | 150 ms / 10⁻³ | 4 Mbps | 8 Mbps | XR model, 30 fps, mean 4 Mbps |
| streaming / lidar | **4** | 300 ms / 10⁻⁶ | 3 Mbps | 6 Mbps | 10 Hz sweeps, bursty, mean 3 Mbps |
| best-effort | **9** | non-GBR | 0 | 100 Mbps | saturating |

Committed sum 7.5 Mbps per asset. The uplink ceiling is **unre-measured** and
historically ~12 Mbps under rfsim against a ~110 Mbps X310 baseline — a
discrepancy that itself needs resolving, and which sets where overload begins.

> **`[OPEN]`** Which capacity constant the simulator uses. It determines every
> load percentage in the grid. Resolve against GT-3.2's ceiling measurement, or
> sweep it as an axis if that measurement is not yet available.

### 4.3 Deliberate GBR over-provisioning is itself a variable

The 5QI-1 flow offers ~24 kbps against a 0.5 Mbps GFBR — a 20× over-provision,
and under the *current* flat profile a 200× one. This matters because the
two-tier GBR deficit accumulator saturates at its window cap when GFBR greatly
exceeds offered load, leaving the control loop with no dynamic range. **Sweep
the GFBR-to-offered ratio**; a scheduler difference that only appears at one
ratio is a finding about provisioning, not about scheduling.

---

## 5. Design principles

**5.1 Score against every authoritative metric; do not pre-select one.**
`adoption-decision.md` §2 established that contract count and max-min floor are
*opposed* objectives — a threshold metric rewards concentrating shortfall, and
two-tier is built to spread it. TS 22.104 adds a third, survival time, which is
neither. Every run is scored against the full panel (§7) and the regime map is
reported per metric. **Where two metrics disagree, that disagreement is the
finding** (H6), not a problem to resolve.

**5.2 Guard against multiplicity.** Scoring ~14 metrics across a large grid
guarantees something wins somewhere by chance. Three mitigations, all in WP0:

- the panel is **pre-registered** in a committed, hashed YAML before the first
  sweep, so it cannot drift toward whatever separates;
- every result reports **effect size with a confidence interval**, never a bare
  winner — §3.1 is the cautionary example;
- a claimed regime boundary must be **contiguous** across adjacent grid cells.
  An isolated winning cell surrounded by losses is noise.

**5.3 Seeds are paired across arms.** For a given cell both arms run on
identical seeds, so the comparison is within-seed. At n=10 this is materially
more powerful than unpaired, and it directly addresses §3.1.

**5.4 Land fidelity changes one at a time.** `NOTES.md` records two occasions
where a single fidelity correction reversed a headline result (the UE-side
uplink LCP fix; the 5QI priority fix). Batched changes make reversals
unattributable. Every work package lands alone, the regression corpus re-runs,
and the delta on **the gap between the two schedulers** is recorded.

**5.5 The reservation baseline lands early, not last.** If all fidelity work
precedes the second scheduler, each change can only be measured against PF and
two-tier — not against the comparison the branch exists to make.

**5.6 Every new abstraction faces the standing question.** From
`scheduler-study.md` §5.1: *which network element learns this, and how?* The
three fidelity errors that cost headline results all failed this test. A model
that hands the scheduler information no gNB possesses produces a scheduler that
cannot be built.

**5.7 Both arms share everything except allocation policy.** Link adaptation,
BSR, HARQ, power model and grant emission are common code (`sim/baselines/_mac.py`).
Any divergence is a confound (§9, WP2).

**5.8 Score the worst asset, never the mean.** The characteristic failure of
priority scheduling is starving one contender while another looks perfect.

---

## 6. Scope

**In scope:** simulator fidelity (channel, traffic, buffer/BSR, uplink access,
HARQ, power), a faithful reservation baseline, the metric panel and sweep
harness, and the resulting regime map.

**Out of scope on this branch**, each deferred to its own branch built on this:

| Deferred | Why not here |
|---|---|
| CU-DU split, F1-U flow control | Changes what the DL scheduler observes; would confound the fidelity deltas this branch measures |
| Multi-RU, shared-cell / DAS | Changes the capacity model |
| MIMO (rank adaptation, MU-MIMO) | MU-MIMO invalidates the LP's separable capacity constraint and the reservation heuristic's min-RB semantics — a scheduler redesign, not a fidelity item |
| ML (demand prediction, policy selection) | Policy selection is trained *on* this branch's regime map, so it cannot precede it |
| Configured Grant / SPS | The expected remedy if the GT-2 class fails; belongs to the feature branch that follows the map |

---

## 7. The metric panel

Pre-registered in `config/metric_panel.yml`, hashed into every output row.
Computed by `sim/scorecard.py`.

**Every metric traces to a guarantee.** A metric that traces to nothing should
not be in the panel; a guarantee with no metric cannot be evidenced here.

| Metric | Definition | Guarantee | Why it is authoritative for someone |
|---|---|---|---|
| p50 / p95 / **p98** / p99 latency, per flow, worst asset | packet delay distribution | G1, G2 | p98 is the 3GPP conformance statistic (TS 23.501 §5.7.3.4): while within GFBR, 98% of packets shall not exceed PDB |
| PDB violation rate | byte-weighted fraction later than budget, plus bytes discarded on expiry | G1, G5, G12 | The 5QI contract as specified |
| **Liveness gap distribution** | max and count of telemetry inter-arrival gaps at the receiver, vs {T_live/4, T_live/2, T_live} | **G3** | The false-failsafe bound. Consecutive-loss tolerance, not average latency |
| Survival-time failures | runs of ≥ N consecutive missed deadlines | G3, G11 | TS 22.104: industrial applications fail on consecutive misses, not averages |
| **PDU-set completeness** | ≥99% of frames complete within set delay budget; partial frames count as failed | **G5** | Latest-frame-only inference: a partial frame is worthless |
| **Frame age at MEC** | recv_ts − frame generation ts, p95 | **G5** | The operationally binding quantity under latest-frame-only |
| GBR contract count | flows delivering ≥95% of GFBR | G10 | The metric on which PF currently beats two-tier |
| Worst-flow GFBR fraction | `min_f (delivered_f / GFBR_f)` | G8, G10 | The max-min floor, where two-tier's advantage should sit |
| **Per-1 s Jain index** | over per-flow delivery ratios, per second | **G8** | Aggregate Jain masks oscillation: 0.743 per-second has been observed while aggregate read 0.9977 |
| Aggregate throughput | total delivered bytes | — | Cost side of every QoS gain |
| PRB utilisation, per direction | used / available | — | Detects reservation holding reserved-but-unused PRBs |
| PDCCH / CCE utilisation | used / budget | G10 | Detects the control-plane bound (H1) |
| **First-violation order** | which 5QI class first breaches under a load ramp | **G12** | The safety-order guarantee |

Bolded rows are **new relative to the original plan**, imported from the
guarantee documents. They are not optional: G3, G5, G8 and G12 cannot be
evidenced without them, and three of the twelve guarantees would otherwise have
no simulation counterpart at all.

**Statistical policy.** Zero-miss claims follow the rule of three: demonstrating
a miss rate ≤ ε at 95% confidence with zero observed misses needs n ≥ 3/ε
samples. State the demonstrated bound, never a tighter one. This applies to
simulated results exactly as it does to measured ones.

`[OPEN]` Survival threshold N. TS 22.104 varies it by application class. Start
at N=3 and **report H6 as a function of N** — see §8.

---

## 8. Hypotheses

Each has a mechanism, a computable prediction, and a guarantee it bears on, so
each can fail cleanly.

| # | Hypothesis | Mechanism | Prediction | Guarantee |
|---|---|---|---|---|
| **H1** | Reservation collapses above a UE count | `budget = bwpSize − n_followers×min_rb` floors at `min_rb` when followers are many; RBs are reserved for followers who may never receive a DCI, since `max_sched_ues = bw/(AL·6)` capped at `MAX_DCI_CORESET` | Degradation above `N_crit ≈ min(bwpSize/min_rb, CCE_budget/AL)`. Compute both for the carrier first — which one binds is itself a result | **G10** |
| **H2** | Two-tier wins as traffic becomes bursty | The windowed ceiling accumulates credit across idle periods; reservation is memoryless | A crossover duty cycle δ\* exists | **G5, G8** |
| **H3** | Two-tier wins as channel quality spreads | Reservation reserves `min_rb` regardless of SE; the LP weights capacity by `1/se` | Two-tier's margin grows with SNR spread | **G5, G8** |
| **H4** | Two-tier's Tier-1 is mismatched to factory deadlines | Tier-1 re-solves every `IA_P5G_TIER1_PERIOD_S = 0.1 s` (200 slots at μ=1); factory motion control has PDB 1–10 ms, so targets are stale relative to the deadline and Tier-2 carries the flow alone | Two-tier's deadline benefit appears only when `PDB ≳ tier1_period` | **G1, G2** |
| **H5** | Two-tier degrades as flows-per-LCG grows | BSR aggregates to 8 LCGs, which is why `ia_p5g_drain_vq_ul` must approximate delivery proportional to buffer occupancy; reservation has no such dependency | Two-tier's UL accuracy falls monotonically in flows-per-LCG | **G3, G5** |
| **H6** | Overload outcome is metric-dependent, not scheduler-dependent | Reservation concentrates shortfall; two-tier spreads it | Contract count and max-min floor pick *different* winners in the same cell | **G8 vs G10** |
| **H7** | The liveness guarantee is decided by the uplink access path, not by allocation policy | Telemetry is small, periodic and idles between messages, so every message pays SR → grant → BSR → grant. §3.3's load-inverted p99 is that chain's signature | Max telemetry gap is roughly arm-independent and dominated by SR periodicity and `sr-ProhibitTimer` | **G3, G4** |

**H4 runs first**, immediately after WP2, on whatever fidelity exists then. If
it holds, the implication is architectural rather than a tuning result.

> **If H4 holds, add a work package rather than a footnote.** The interesting
> follow-on question is *what Tier-1 period would be required* to serve a 1–10 ms
> PDB, and whether that is feasible in the LP thread at all. Make
> `tier1_period` a swept axis. That answer is worth more than the regime map,
> because it decides whether two-tier is architecturally applicable to motion
> control or only to video-class traffic.

**H7 is new**, imported from the guarantee plan's analysis of the liveness
path. It is the most likely explanation for G3 failures and it predicts a
*negative* result — that no allocation policy fixes G3, and Configured Grant is
the actual remedy. A negative here is as valuable as a positive: it redirects
the feature roadmap.

**Report H6 as a function of the survival threshold N.** H6 claims two metrics
pick different winners; survival time is a third axis of disagreement and N
determines how it aligns with the other two. Reporting one N invites a reader
to treat it as the answer.

---

## 9. Work packages

Order: `WP0 → WP1 → WP2a → WP2b → WP3 → WP4 → WP7 → WP5 → WP6 → WP8 → WP9`.
Each lands alone; the regression corpus re-runs and the delta on the
two-tier-versus-reservation gap is recorded before the next begins.

> **Ordering change from the original plan:** WP2 is split (see below) and WP7
> (traffic) is promoted ahead of WP5/WP6. Rationale in each entry.

### WP0 — Harness, metric panel, regression corpus

| File | Change |
|---|---|
| `sim/run_record.py` | New. The scorecard's input contract |
| `sim/metrics.py` | Extend: consecutive-miss runs, per-flow GFBR fractions, per-second Jain, PDU-set completeness |
| `sim/scorecard.py` | New. Computes the full §7 panel |
| `config/metric_panel.yml` | New. The pre-registered panel |
| `scripts/regime_sweep.py` | New. Grid runner, paired seeds, parallel, tidy output; plus aggregation with bootstrap CIs and contiguity |
| `scripts/regression_corpus.py` | New. Snapshots the panel for later WPs to diff against |

**Acceptance:** the corpus reproduces the currently published numbers on `main`
for studies 1–3.

### WP1 — `min_rb` and power headroom

| File | Change |
|---|---|
| `sim/power.py` | New. UE Tx power, pathloss-derived headroom, per-UE per-slot minimum viable PRB count |
| `scheduler/link.py` | `min_prbs_for_grant(snr_db, bytes, symbols)`; MCS↔PRB tradeoff under a power limit (analogue of `nr_ue_max_mcs_min_rb`) |
| `sim/config.py` | `UEConfig` gains Tx power and pathloss |

Reservation is denominated in `min_rb` and the concept does not exist in the
simulator. Without it WP2 has nothing to reserve.

**Acceptance:** `min_rb` rises monotonically as SNR falls; a cell-edge UE needs
materially more PRBs than a near UE for the same payload.

> Note: on hardware the PHR path is **inert** — no PHR MAC CE has ever been
> received (`ph0 = 0` across every capture). The simulator will therefore model
> a mechanism the testbed cannot currently exercise. Flag any WP1-dependent
> result as sim-only until PHR reporting is fixed.

### WP2a — Read and document the reservation branch *(no code)*

**Split out of the original WP2, because it is the highest-risk item in the
plan and was one line.** Nothing in any document to date is based on having
read `rrc-qos-handling-v0.1.1`; every statement about the reservation scheduler
is inference from observed behaviour. The regime map's transferability rests
entirely on the port being faithful.

Deliverable: a written spec of the reservation scheduler's allocation path, and
the filled-in confound table below.

**Confound control.** The two OAI branches differ in three places unrelated to
reservation-versus-two-tier:

| | two-tier branch | reservation branch |
|---|---|---|
| PF coefficient | `(tbs/thr) × (100/prio)` | `tbs/thr`, `thr` floored at 1.0 |
| UL LCG deficit drain | modelled strict-priority LCP | full `tb_size` credited to every active LCG |
| SRB starvation fix | `cp_floor` in `pf_ul` | `has_srb` sort tier |

Pick one variant of each and use it in **both** arms. **Record the choice in
this document when made.** Carrying the differences through would reproduce the
confound in simulation.

### WP2b — Reservation scheduler

| File | Change |
|---|---|
| `scheduler/reservation.py` | New. Ported per the WP2a spec |

Four mechanisms, all required:

1. Follower reservation: `budget = bwpSize − n_followers_need × min_rb`
2. Guaranteed / best-effort byte split
3. Four-tier sort: SRB → liveness → GBR deficit → PDB → PF coefficient
4. Control-only caps and the two-pass DL LCP (SRB pass, then DRB pass)

**Acceptance:** with `n_followers = 0` the scheduler reduces to plain PF —
which retroactively explains the N=2 tie in §3.2.

### WP3 — BSR realism

| File | Change |
|---|---|
| `sim/bsr.py` | New. Replaces the BSR path in `buffer.py` |
| `sim/buffer.py` | Strip the `bytes_reported` pipeline; delegate |
| `scheduler/interfaces.py` | `BufferStateView` gains LCG-level access |
| `scheduler/flow.py` | `FlowConfig` gains `lcg` |

Today's model is per-flow, exact-valued and fixed-delay. Real BSR is per-LCG,
log-quantised and event-triggered:

- LCID → LCG map, 8 groups
- short and long BSR formats
- quantised index tables, TS 38.321 Tables 6.1.3.1-1 / 6.1.3.1-2
- triggers: regular (higher-priority data arrival), periodic timer, padding
  BSR, retxBSR timer
- the report rides on a UL grant

Modelling this per-flow hands two-tier information no gNB has — the same class
of error as the pre-correction `_mac_lcp_fill`.

**Two mechanisms observed on hardware that the model must reproduce:**

- **`sched_ul_bytes` accounting.** `B = estimated_ul_buffer − sched_ul_bytes`,
  with `sched_ul_bytes += tb_size` on grant and **`= 0` on every BSR
  reception**. When the gNB grants faster than the UE reports, `B` collapses to
  zero and the UE drops to a `min_rb` crumb until the next BSR. On hardware this
  accounted for **~48–52% of the probe's grants**, averaging 72–107 bytes each.
- **Short-BSR aliasing.** A short BSR reports one LCG and the gNB zeroes all
  other per-LCG estimates. A short BSR on the SRB group therefore blanks every
  data LCG's backlog.

Hardware timer values: `periodicBSR = 5 ms`, `retxBSR = 80 ms`. Note that
retxBSR restarts on every received grant, so a crumb trickle *suppresses* the
one recovery path.

**Acceptance:** quantisation error is proportionally largest at small buffers;
two-tier's UL drain accuracy degrades measurably as flows-per-LCG rises, making
H5 testable; the crumb fraction under contention is reproduced within a factor
of two of the measured 48–52%.

### WP4 — Uplink access chain

| File | Change |
|---|---|
| `sim/ul_access.py` | New. Per-UE state machine |
| `sim/driver.py` | Hook ahead of `scheduler.allocate` |

States: no grant → SR opportunity on PUCCH (configurable periodicity) →
`sr-ProhibitTimer` → SR-to-grant latency → BSR on that grant → data grant.
Include `sr-TransMax` exhaustion → RACH, which is the mechanism behind the
multi-hundred-millisecond blackouts seen historically.

**This work package has the branch's only real calibration target.** §3.3
records p99 inverted in load on hardware — 67 ms at 45% offered load, 13 ms at
125% — which is this chain's signature. If WP4 reproduces that inversion at
roughly the right magnitude, it is the strongest fidelity evidence available
here, and it validates discarding P1/P2 as uninformative.

**It also decides H7**, and therefore G3 and G4.

### WP7 — Traffic: factory generators and correlated arrivals

**Promoted ahead of WP5/WP6.** The plan's own assessment is that the
production-line thundering herd is "plausibly the most discriminating factory
feature and is entirely absent today." If that is right it should not be
seventh. A correlated burst is exactly where two-tier's cross-idle credit
accumulation (H2) either pays off or does not, and it is cheaper to build than
either HARQ or the channel model.

| File | Change |
|---|---|
| `sim/traffic.py` | New kinds: `periodic_control` (0.5–2 ms cycle, 20–50 B, jitter), `aperiodic_event` (Poisson-triggered burst, tight PDB), `machine_vision` (triggered large burst), `condition_monitor` (many low-rate sensors), `xr_video` (see below) |
| `sim/cycle_clock.py` | New. Shared production-line clock so flows in a `sync_group` arrive in phase |
| `scheduler/flow.py` | `FlowConfig` gains `sync_group`, `phase_offset`, `phase_jitter_ms` |

**The XR video model matters and is currently absent.** Per 3GPP: frames at
fixed rate; frame size truncated Gaussian with σ ≈ 10.5% of mean clipped to
[50%, 150%]; arrival jitter truncated Gaussian σ ≈ 2 ms clipped to ±4 ms; one
frame = one PDU set, useless if any part misses. Two properties bite:
periodicities are **non-integer in ms** (16.67, 11.11, 8.33), which aliases
against a 100 ms Tier-1 period; and **partial delivery is worthless**, which is
why §7 scores PDU-set completeness rather than packet latency.

### WP5 — HARQ

| File | Change |
|---|---|
| `sim/harq.py` | New. N processes per UE per direction, k1/k2 timing, RTT, per-attempt combining gain, max-retx residual loss |
| `sim/driver.py` | Allocation → attempt → ACK/NACK after RTT → retransmission consumes a grant |
| `scheduler/reservation.py`, `scheduler/two_tier.py` | Retransmission handling |

BLER is currently a scalar discount with no retransmission. At a PDB of 1–10 ms
one HARQ RTT is a large fraction of the deadline budget, so **every deadline
result on this branch is unreliable until this lands** — which includes H4.

**Acceptance:** PDB violation rate rises sharply for flows whose PDB is a small
multiple of the HARQ RTT.

### WP6 — Channel: factory blockage

| File | Change |
|---|---|
| `sim/channel.py` | Keep AR(1) as the small-scale term; add TR 38.901 InF path loss (selectable InF-SL/DL/SH/HH), LOS probability from clutter density and height, two-state Markov blockage |
| `sim/mobility.py` | New, optional. AGV route model so blockage correlates across UEs sharing an aisle |
| `sim/config.py` | `UEConfig` gains position, route, clutter parameters |

AGVs at 1–3 m/s produce near-zero Doppler; mild AR(1) fading is the wrong
dynamic for a factory. The real event is a forklift or robot arm crossing the
path — a 15–20 dB drop lasting hundreds of milliseconds. Recovery from
sustained starvation is exactly what reservation's min-RB floor and two-tier's
virtual-queue growth do *by different mechanisms*, so this is where they should
visibly diverge.

**Acceptance:** blockage produces sustained multi-hundred-millisecond
starvation that a scheduler must actively recover from.

### WP8 — Two-tier alignment audit

Reconcile `scheduler/two_tier.py` and `scheduler/tier1.py` against
`ia_p5g_scheduler.{c,h}`:

- **The Tier-1 period discrepancy.** The header documents `tier1_period_s` as
  "default 1.0 s"; the macro sets `IA_P5G_TIER1_PERIOD_S = 0.1f`. Which value
  produced the published hardware results is unrecorded, and H4 makes it
  load-bearing.
- The demand cap, flagged in `NOTES.md` as a deliberate divergence (removed
  here, retained in OAI).
- Windowed ceiling, `IA_P5G_VQ_UL_CATCHUP_N`, the UL service-interval floor and
  its arming condition.
- The `.c` header comment still describes the file as a Checkpoint-1 stub with
  every function a no-op. Badly stale; misleads anyone reading top-down.

Either match the OAI branch that would actually be deployed, or document each
divergence explicitly. An unaudited divergence invalidates transfer back to
hardware.

### WP9 — Characterisation sweep

Run the grid. Axes: N, offered load, burst duty cycle, SNR spread,
PDB / tier1-period ratio, flows-per-LCG, GFBR-to-offered ratio. 10 seeds per
cell, paired across arms.

Output: a regime map with one panel per metric, per-cell effect sizes and
confidence intervals, testing H1–H7.

**Regime selection discipline.** A cell producing 0% loss on both arms carries
no information and is excluded — that is the mistake §3 diagnoses in the
hardware sweep. **The grid must be pushed until loss appears on at least one
arm.**

---

## 10. From regime map to campaign

The map is not the deliverable. What it produces:

1. **A deployment recommendation per traffic class.** "Use reservation below
   N=6; above that, two-tier" — or the negative result that they are
   equivalent everywhere reachable, which is itself publishable and much
   stronger than the current N=2 tie.
2. **Where to spend the real-RF window.** The hardware campaign's certifiable
   numbers come from a scarce resource. The map says which GT tests, at which
   load points, are worth that time.
3. **Falsifiable predictions.** Each hypothesis that survives becomes a
   prediction the hardware campaign confirms or refutes. A refuted prediction
   is a fidelity bug with a known location.
4. **A feature roadmap.** If H7 holds and no policy fixes G3, Configured Grant
   on the 5QI-1 bearer becomes the next feature — it structurally removes the
   entire failure class, since there is no SR, no BSR and no estimate to
   desync.

---

## 11. Calibration

**The weakest point of this branch, and it should be addressed rather than
noted.** No hardware data exists in a discriminating regime, so the simulator
is largely uncalibrated exactly where it matters.

Available targets, in descending strength:

1. **WP4's SR-chain inversion** (§3.3) — a specific, quantitative, already-measured
   signature.
2. **The crumb fraction** — 48–52% of grants at `min_rb` with `B == 0` on
   ~87% of those, measured across two full-telemetry runs.
3. **Backlog quantisation** — the 5QI-1 BSR distribution was byte-identical
   across two independent runs (p50 1038, p90 1446, p99 2806, max 3909),
   because BSR values are quantised table indices. WP3 should reproduce that
   discreteness.
4. **Per-second Jain oscillation** — 0.743 per-second against 0.9977 aggregate.

**Recommendation: commit to one further hardware sweep at N ≥ 5, pushed until
loss appears, before WP9 rather than after.** It is cheap relative to its value
and is the only insurance against spending the branch characterising an
artefact. A regime map with no calibration point in any discriminating regime
is a map of the simulator's assumptions.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| The simulator never reproduces a discriminating regime | A publishable negative result, and stronger than the N=2 tie — but only if the grid demonstrably reached overload. Hence the WP9 exclusion rule |
| **The reservation port is unfaithful** | WP2a exists precisely for this. Until it is done, every comparative claim is provisional |
| Calibration is weak where it matters | §11: WP4's inversion, plus a committed N ≥ 5 hardware sweep before WP9 |
| A fidelity WP reverses an earlier finding | Expected — it has happened twice. The one-at-a-time rule (§5.4) makes it attributable rather than mysterious |
| Multiplicity manufactures a false regime | §5.2: pre-registration, effect sizes, contiguity |
| WP2a's confound choices bias the comparison | Choices recorded in this document and applied to both arms (§5.7) |
| Simulated results are read as certifiable | §2: every client-facing bound comes from real RF. The Guarantee Sheet states environment per row |

---

## 13. Open decisions

- `[OPEN]` Survival-time threshold N (§7). Start at 3; report H6 as a function
  of N.
- `[OPEN]` Which variant of each WP2a confound to standardise on. Decide at
  WP2a and record here.
- `[OPEN]` The uplink capacity constant (§4.2). Resolve against GT-3.2 or sweep
  it.
- `[OPEN]` InF sub-scenario (SL/DL/SH/HH) for the headline configuration.
  Deployment-dependent; sweep in WP6 rather than picking blind.
- `[OPEN]` `T_live`, the MEC liveness timeout. G3's pass line is `T_live/4`
  and is currently assumed 2 s. **Ask the MEC team** — it calibrates every
  liveness result.
- `[RESOLVED — proposed]` Further hardware sweep at N ≥ 5 for calibration:
  **yes, before WP9** (§11).

---

## Appendix A — Glossary for a reader new to this system

| Term | Meaning here |
|---|---|
| **5QI** | 3GPP QoS class identifier. Carries a PDB, an error rate and a resource type |
| **PDB** | Packet Delay Budget. The 5QI's latency contract |
| **GFBR / MFBR** | Guaranteed / Maximum Flow Bit Rate |
| **BSR** | Buffer Status Report. The UE tells the gNB how much uplink data it holds — quantised, per logical-channel-group, event-triggered. The gNB has no other view of the UE's queues |
| **LCG** | Logical Channel Group. Up to 8; BSR reports per group, not per flow, so several flows sharing a group have their backlogs summed |
| **SR** | Scheduling Request. How a UE with no grant asks for one |
| **PRB** | Physical Resource Block. The allocation unit |
| **`min_rb`** | The minimum grant size. Reservation's currency; also the "crumb" the uplink degenerates to when the buffer estimate reads zero |
| **CCE / PDCCH** | Control channel resource carrying grants. Can bind before PRBs at high UE count |
| **Tier 1 / Tier 2** | Two-tier's slow rate-allocation loop (100 ms, an LP) and fast per-slot ordering loop |
| **Follower reservation** | Reservation's central mechanism: withhold `min_rb` for each UE still waiting behind the current one |
| **rfsim** | OAI's RF simulator. ~0.45× realtime; valid for logic and relative claims, not for certifiable latency |
| **Boundary A** | Asset ↔ MEC. The only traffic crossing the air interface |
| **Latest-frame-only** | The MEC's AI discards stale frames rather than queueing them, which makes frame *age* the binding video KPI |
