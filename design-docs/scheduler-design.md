# QoS-Optimized Two-Tier Scheduler for Private 5G

**Status:** Draft skeleton — sections marked `[OPEN]` need decisions before implementation.
**Target stack:** OpenAirInterface (OAI) gNB, private 5G factory/warehouse deployment.

---

## 1. Goals and Non-Goals

### Goals
- A two-tier scheduler that meets per-flow QoS targets (GBR, delay budgets) for a mixed industrial workload (machine-vision cameras, mobile robots, sensors, control loops) while maximizing aggregate utility for best-effort flows.
- Deterministic latency for periodic high-bandwidth flows (4K/60fps cameras) via Configured Grants.
- Symbol-level capacity accounting that includes the S-slot in TDD.
- A clean integration boundary in the OAI MAC scheduler so the Tier-1 strategy can be developed and tested independently of the per-slot PHY-facing code.

### Non-Goals (initial scope)
- Mobility / handover. Single-cell only.
- Public-network interop. Private deployment with operator-controlled QFI/5QI policies.
- MU-MIMO scheduling (called out as future work in §12).
- Dynamic TDD. Static TDD pattern only.
- Massive cell-edge users. Assume reasonable SNR for all UEs (factory deployment).

---

## 2. Workload Model

### Flow taxonomy
| Class | Example | QoS shape | Volume |
|---|---|---|---|
| Vision-UL | 4K@60fps H.264 from robot/fixed cameras | Periodic, ~30–80 Mbps avg, I-frame bursts up to ~5×; PDB 10–30 ms | Few (10s) but heavy |
| Control-loop | Robot motion commands, sensor telemetry | Periodic, small payloads (10s–100s of bytes), tight PDB (1–10 ms) | Many (100s) |
| Best-effort | Firmware updates, log uploads, ops dashboards | Aperiodic, bursty | Variable |
| Signaling | RRC/NAS, PUCCH feedback | System-driven | Constant overhead |

### Traffic assumptions used downstream
- Vision flows: known periodicity, known average rate per camera. Modeled as deterministic for SPS sizing, with a stochastic I-frame burst overlay.
- Control loops: periodic, predictable, can also be served by SPS (low rate but tight delay).
- Best-effort: stochastic; Tier-1 reserves a "dynamic pool" of resources (residual capacity).

`[OPEN]` Concrete numbers to plug in: how many cameras, how many control UEs, expected bitrates per class. Needed to size the carrier and TDD pattern.

---

## 3. Resource Model

### Numerology
- Subcarrier spacing: 30 kHz (μ=1) or 120 kHz (μ=3). `[OPEN]` Pick based on band and required slot duration.
- 1 RB = 12 subcarriers.
- 1 slot = 14 OFDM symbols. At μ=1 → 0.5 ms/slot; at μ=3 → 0.125 ms/slot.

### Carrier
- Bandwidth: `[OPEN]` (e.g., 30 MHz / 100 MHz). Determines RB count.
- At 30 MHz, μ=1: ~78 RBs per slot. At 100 MHz, μ=3: ~66 RBs per slot.

### TDD pattern
- Tentative: **DSUUU** at μ=3 (0.625 ms cycle), UL-heavy for vision workloads.
- S-slot internal split: tentative **3:2:9** (3 DL symbols, 2 guard, 9 UL symbols).
- S-slot **is treated as a usable resource** (not just signaling overhead).

Per 0.625 ms cycle (70 symbols total):
- DL symbols available: 14 (1 D-slot) + 3 (S-slot) = **17** (~24%).
- UL symbols available: 42 (3 U-slots) + 9 (S-slot) = **51** (~73%).
- Guard: 2 symbols (~3%, lost).

### Bandwidth Parts (BWP)
`[OPEN]` Initial design uses a single BWP per UE matching the full carrier. Sensors that need power saving could later be moved to a narrow BWP — out of initial scope.

### Reference signals and control overhead (subtract from data capacity)
- PDCCH (CORESET) occupies the first 1–3 symbols of D-slots. Subtract from DL data symbols.
- CSI-RS, SSB: periodic, account for as fixed overhead in the LP.
- PUCCH region in U-slots: reserve outer RBs.
- SRS in S-slot UL portion: configurable, eats into S-slot UL capacity.

`[OPEN]` Quantify: what fraction of nominal symbol-RB capacity becomes usable PDSCH/PUSCH after accounting for these overheads. Probably 75–85%.

---

## 4. Tier-1 Formulation (Strategic, ~1 s horizon)

### Role
Compute weights and resource allocations that the Tier-2 scheduler enforces over the next horizon. Re-solved on a slow cadence; intermediate "weight refresh" happens more often (see §6).

### Decision variables
For each (UE *i*, QFI *q*) pair active in the next horizon:
- `r_{i,q}` — target bits to deliver in horizon (continuous).
- `sps_{i,q}` — boolean / structured: whether this flow gets a Configured Grant, and its periodicity + size.

### Objective (decided form)
Composite utility, summed across flows. The GBR slack penalty is a
per-flow **vector** `p`, not a scalar:

```
maximize  Σ_i  w_class_i · log(r_i + ε)
        - pᵀ · slack          (p, slack are length-(#flows) vectors)
```

- Per-class utility weights: `w_PF = 1`, `w_GBR = 1`, `w_Delay = 5`.
  Delay's higher weight makes the LP fund it well during overload; GBR
  also has a hard floor via slack.
- GBR enforcement: soft floor `r_i + slack_i ≥ GFBR_i`, with `slack_i ≥ 0`
  and a slack penalty `p_i` per flow. At the baseline value `p_i = 1e3`
  the penalty so dominates the log-utility that the floor is effectively
  hard whenever the flow is *feasible*; slack only appears under genuine
  (partial) infeasibility. Soft form keeps the LP feasible under arbitrary
  overload — slack just carries the cost.
- Delay flows: handled in Tier-2 via HoL urgency on top of Tier-1's rate
  target. The LP itself doesn't model delay; it just gives Delay flows
  extra utility weight so they're well-funded for their (typically modest)
  demand.

CVXPY directly handles the log-sum-with-linear-constraints. Solve time on
the simulator's scenarios is well under 100 ms — fast enough for 1 s
cadence. If solver becomes a bottleneck, switch to ECOS/Mosek explicitly.

### Adaptive per-flow GBR penalty (dual ascent)

A *uniform* penalty has a bias: under partial infeasibility (the cell
cannot meet every GBR floor at once), `min pᵀ·slack` with equal `p`
minimizes total **bps** of shortfall, which is cheapest by sacrificing
*poor-SNR* GBR flows — reducing their slack costs the most capacity per
bit. So the flows in the worst channel are exactly the ones dropped.

Fix: adapt `p` per flow by dual ascent between solves. After solve `k`:

```
p_i(k+1) = min( p_max,  p_i(k) + b · slack_i(k) / GFBR_i )
```

- `slack_i / GFBR_i ∈ [0, 1]` — normalized shortfall, so the learning
  rate `b` is scale-free.
- `b = 0` recovers the fixed uniform penalty exactly.
- This is dual-subgradient ascent on the GBR constraints: a flow that
  keeps missing accrues an escalating penalty until the LP funds it.
  Steady state drives contending GBR flows toward **equal normalized
  shortfall** — proportional fairness among GBR flows under infeasibility,
  instead of "sacrifice the poor-SNR one".
- `p_max` cap: a genuinely infeasible flow's `p_i` would otherwise
  diverge and starve everything (including other GBR flows). Capping
  bounds the damage; a flow pinned at `p_max` and still missing is the
  signal for admission control to reject it.

Implemented in [sim/tier1.py](../sim/tier1.py) (`solve_tier1` accepts a
per-flow penalty dict) and [sim/schedulers/two_tier.py](../sim/schedulers/two_tier.py)
(`_update_gbr_penalties`, knobs `gbr_penalty_init / _lr / _max`).

### Constraints

**Symbol-RB capacity (separately for DL and UL):**
```
Σ_{(i,q) in DL} TBS(rbs_{i,q}, mcs_i) ≥ r_{i,q}^DL
Σ_{(i,q) in UL} TBS(rbs_{i,q}, mcs_i) ≥ r_{i,q}^UL
Σ_{(i,q)} rbs_{i,q}^DL · symbols_DL ≤ Available_DL_symbol_RBs · (1 - overhead)
Σ_{(i,q)} rbs_{i,q}^UL · symbols_UL ≤ Available_UL_symbol_RBs · (1 - overhead)
```

**BLER discount:** effective bits delivered = nominal × (1 - BLER_i). Use per-UE BLER estimate from recent HARQ stats.

**PDCCH / DCI capacity:**
```
Σ_{i in scheduled UEs per slot} AL_i ≤ CCEs per CORESET
```
This caps how many UEs can be dynamically scheduled per slot. SPS UEs don't consume PDCCH per slot.

**Slice partitions:** if multiple S-NSSAIs, hard or soft RB partitioning per slice.

**HARQ feedback feasibility (TDD):** for each UL transmission slot, there must be a downstream D-slot or S-slot DL portion within k1_max for the ACK/NACK. In DSUUU this is tight — the single D-slot per cycle has to carry HARQ feedback for 3+ U-slots.

### Infeasibility handling
`[OPEN]` What does Tier-1 do when GBR demand exceeds capacity?
- Option A: hard constraints + admission control rejects new flows.
- Option B: soft GBR with steep penalty, scheduler "fails gracefully" by under-serving lowest-priority GBR.
- Recommendation: B for runtime, plus a separate admission-control gate that uses A's logic for new-flow decisions.

### Cadence
- Full re-solve: 1 s (configurable). Triggered also on join/leave of a UE or new flow.
- Weight refresh: simulator results so far suggest Tier-2's drift-plus-penalty
  averaging (see §5) handles drift inside the 1 s window without an
  intermediate re-solve. Revisit if scenarios with rapidly changing channel
  quality show steady-state error.

---

## 5. Tier-2 Formulation (Tactical, per slot)

### Role
Per-slot allocation of PRBs to UEs, tracking the rate targets Tier-1 set
across all flows.

### Decision: drift-plus-penalty (Lyapunov virtual queues)

Simulator experiments showed that **multiplicative urgency formulations
saturate** — even with a very large `deficit_w`, a metric of the form
`(r_inst / R_avg) × (1 + deficit_w · max(0, 1 − R_avg/target))` cannot
enforce arbitrarily unequal target rates because in equilibrium it
equalizes weighted (1/R_avg) across flows, not actual rates against
targets. This is a fundamental limitation, not a tuning issue.

Drift-plus-penalty (standard Lyapunov optimization for stochastic networks)
is the correct tool. Each flow has a virtual queue:

```
Q_i(t+1) = max(0, Q_i(t) + r_target_i · slot_duration − delivered_i(t))
```

`Q_i` grows when the flow falls behind its target and shrinks when it gets
ahead. The per-slot scheduling metric is:

```
metric_i = (Q_i + delay_urgency_bonus_i) · spectral_efficiency_i
```

This is opportunistic (good channel → high `spectral_efficiency`) AND
rate-tracking (behind target → high Q). Long-run delivered rate converges
to `r_target_i` set by Tier-1.

### Implementation details that matter

1. **Gate Q growth on buffer non-empty.** Otherwise idle flows accumulate
   phantom debt and starve everyone else when they finally have data.

2. **Cap Q at `q_cap_periods × tier1_period × target × slot_duration`.**
   Prevents runaway Q when actual arrivals are below the configured target
   (e.g., bursty Poisson with low realized rate).

3. **Delay urgency must be scaled by max-system-Q, not by per-flow target
   rate.** Small periodic flows (low `target_bps` → tiny `Q`) cannot
   compete with bulk flows on absolute Q. The fix:
   ```
   delay_bonus = delay_w · (HoL/PDB)^k · max(Q across all flows)
   ```
   This makes deadline-pressed delay flows preempt anything when their HoL
   approaches PDB.

4. **PRB right-sizing.** Each chosen flow gets only as many PRBs as needed
   to drain its buffer, never more. Greedy fill across flows in metric order.

### Per-slot flow
1. SPS-reserved PRBs are pre-allocated — Tier-2 skips them.
2. Update virtual queues: `Q_i += target_i · slot_duration` (gated, capped).
3. For each direction with available symbols:
   - Compute `metric_i = (Q_i + delay_bonus_i) · spectral_efficiency_i`.
   - Sort by metric, descending.
   - Greedy fill: each flow takes only the PRBs it needs.
4. Drain virtual queues by expected delivered bits (post-BLER).

### Where Tier-1 and Tier-2 meet
- Tier-1 produces: SPS allocations (planned, see §7), per-flow target rates
  `r_target_i`, slice quotas (when implemented).
- Tier-2 reads target rates through shared state at each Tier-1 solve.
  Between solves, virtual queues evolve based on the standing targets.

### Sanity benchmarks vs. simpler schedulers (from sim experiments)

For comparison the simulator implements three baselines plus the two-tier
system. Under a 4.8× DL-overload scenario:

| Flow | RR | PF | Gradient (multiplier) | TwoTier (drift+penalty) |
|---|---|---|---|---|
| PF best-effort (20 Mbps offered) | 1.77 | 2.27 | 1.43 | 0.74 |
| GBR (GFBR 4 Mbps) | 1.78 | 2.28 | 3.12 | **3.89 (97%)** |
| Delay (PDB 20 ms, p99 HoL) | 7 ms | 4.5 | 4.5 | 12 (still meets PDB) |

Numbers in Mbps unless marked. The two-tier system trades best-effort
throughput for GBR contract satisfaction, which is exactly the design intent.

---

## 6. Tier-1 ↔ Tier-2 Interface

```
struct Tier1Output {
  // SPS / Configured Grants  [planned, not yet in simulator]
  ConfiguredGrant sps[MAX_UE_QFI];          // periodicity, RB range, MCS, lifetime

  // The single load-bearing field for the dynamic pool
  float target_rate_bps[UE_ID][QFI];        // per-flow rate target

  // Slice partitioning (when implemented)
  RBRange slice_partition[SLICE_ID];

  // Admission decisions (when implemented)
  bool admitted[UE_ID];

  uint64_t valid_until_ns;                  // expires at next Tier-1 solve
};
```

The simulator's interface is simpler today: just `target_rate_bps` per
(UE, QFI). Tier-2's drift-plus-penalty consumes this directly — virtual
queue inflow rate equals target rate. No "weight" field is needed because
the queue dynamics produce the right priority automatically.

- Updated in shared memory by Tier-1 thread.
- Read by Tier-2 (MAC scheduler) every slot. Atomic snapshot to avoid torn reads.
- If Tier-1 misses a deadline (LP solver overruns 1 s), Tier-2 keeps using
  the previous snapshot — fail-safe.

`[OPEN]` Lockless ring buffer vs. RCU-style snapshot vs. simple double-buffer.
Performance impact in the per-slot path matters; needs measurement on
real hardware.

---

## 7. SPS Strategy

### Use SPS for
- Vision-UL flows (60 fps cameras): periodicity ≈ 16.67 ms.
- Periodic control-loop flows: periodicity matches sensor reporting rate.

### Use dynamic scheduling for
- Best-effort flows.
- I-frame "spillover" from camera flows that exceed the SPS allocation in a given period.

### Sizing
- Size SPS for **average frame size**, not peak (I-frame). Spillover handled via dynamic pool.
- `[OPEN]` Periodicity quantization: 5G NR allows specific values (1, 2, 4, 5, 8, 10, 16, 20, 32, 40, ... slots). Closest to 16.67 ms at μ=3 (0.125 ms/slot) is 128 slots = 16 ms, or 136 slots = 17 ms. Decision: over-provision at 16 ms (preferred — never under-serves, slight 4% over-allocation), or use staggered configs.

### Spillover mechanism
When a frame exceeds its SPS grant, RLC buffer fills. Tier-2's gradient metric for that flow spikes (because GBR/delay debt grows), and the dynamic pool serves the overflow in the next available U-slot.

`[OPEN]` Should the gNB explicitly detect I-frame arrivals and pre-grant additional resources? Possible if a small "frame-type" hint can be passed up from the encoder, but this is non-standard.

---

## 8. Control-Plane Modeling

### What Tier-1 must account for
- **PDCCH / DCI capacity:** ~40–80 CCEs per CORESET. Each dynamic grant consumes 1, 2, 4, 8, or 16 CCEs depending on aggregation level (function of UE channel quality).
  - Constraint: Σ AL_i over UEs scheduled in slot ≤ CORESET CCEs.
  - SPS UEs don't consume PDCCH per slot — strong incentive to use SPS aggressively in dense deployments.
- **k1 timing for HARQ ACKs (TDD):** every PDSCH transmission needs a PUCCH slot for ACK within k1_max. In DSUUU, only U-slots carry PUCCH, so DL transmissions in the D-slot of cycle N get their ACK in the U-slots of the same cycle.
  - Implication: k1 values must be feasible given the DSUUU cadence. Tier-1 doesn't directly schedule HARQ but must not over-commit DL transmissions whose ACKs can't fit in the available PUCCH region.
- **k2 timing for UL grants:** UL grant in D-slot of cycle N produces UL transmission in a U-slot of the same or next cycle, depending on UE processing time.
- **SRBs (signaling):** absolute priority, modeled as fixed overhead (~1–2% of capacity) in Tier-1.

### What Tier-2 must enforce
- Don't schedule a UE for PDSCH if no PUCCH slot is available within k1_max for its ACK.
- Don't issue an UL grant if the UE can't process it in time.

---

## 9. Link Adaptation, HARQ, BLER

### MCS selection (link adaptation)
- The scheduler doesn't directly compute "bits per RB" — it picks an **MCS index** based on UE CQI, then looks up TBS (Transport Block Size) from the 3GPP-defined table.
- TBS is non-linear in (PRBs, MCS).
- Outer-loop link adaptation adjusts MCS to hit a target BLER (typically 10% for first transmission).

`[OPEN]` Initial implementation: use OAI's existing link adaptation, expose `effective_bits_per_PRB(UE_i)` to Tier-1 and Tier-2. Refinement (joint MCS + scheduling optimization) is future work.

### HARQ
- Operates at MAC layer. ACK/NACK per HARQ process within ~4 slots of transmission (configurable).
- Soft combining: NACKed transmissions are retransmitted with incremental redundancy; receiver combines for decoding.
- Tier-2 must account for HARQ retransmissions consuming PRBs alongside new transmissions.

### RLC ARQ (RLC-AM mode)
- Operates above HARQ; covers cases where HARQ exhausts retries.
- RLC retransmission re-fills the DRB queue, so buffer-occupancy reads should reflect this naturally.
- Tier-1 should treat the buffer occupancy reported by RLC as authoritative for "outstanding work".

### BLER discount in Tier-1
- Per-UE: track recent first-transmission BLER from HARQ stats.
- Effective capacity for UE *i* = nominal × (1 - BLER_i).
- Refresh BLER estimate at the same cadence as Tier-1 re-solve.

---

## 10. OAI Integration Plan

### Codebase orientation
- gNB MAC scheduler: [openair2/LAYER2/NR_MAC_gNB/](openair2/LAYER2/NR_MAC_gNB/) — main scheduler entry points, slot processing, UE selection, PRB allocation.
- RLC: buffer occupancy reporting via the MAC-RLC primitives in the same area.
- RRC: SPS / Configured Grant configuration messages.
- PHY: not directly modified; use existing FAPI / nFAPI interface.

`[OPEN]` Pin down exact files/functions after a code-reading pass. Likely candidates from the Gemini conversation: `nr_schedule_ue_spec.c`, `nr_simple_dlsch_preprocessor`, `nr_generate_dlsch_pdu`. Verify these exist in the current OAI tree before committing to them.

### Integration architecture
- **Tier-2** lives inside the OAI MAC scheduler thread. Replaces or wraps the default scheduler logic. Must complete in well under one slot (~125 µs at μ=3) — keep math cheap.
- **Tier-1** runs in a separate thread (or process). Reads:
  - RLC buffer occupancies
  - HARQ stats (BLER per UE)
  - Recent CQI reports
  - Current SPS configuration
  Writes:
  - The `Tier1Output` shared-memory snapshot
- **Tier-1 ↔ Tier-2** communication: shared memory + atomic snapshot. No locks in Tier-2 path.

### Phased implementation
1. **Instrumentation** — add per-flow metrics (throughput, HoL delay, BLER) to OAI MAC, log to file/CSV. Verify against baseline scheduler.
2. **Tier-2 replacement** — implement gradient-based selection with hardcoded weights. Compare to baseline PF.
3. **Tier-1 prototype** — offline LP solver, hand-fed buffer state, output weights written to a config file that Tier-2 reads.
4. **Live integration** — Tier-1 runs as a thread, real-time read/write to Tier-2.
5. **SPS support** — add Configured Grant setup driven by Tier-1 admission decisions.

### Build/runtime requirements
- Low-latency Linux kernel (PREEMPT_RT or similar).
- CPU isolation, disabled C-states/P-states for the MAC thread.
- SDR: USRP B210/N310 or compatible.

---

## 11. Test Plan

### Baseline metrics
For each flow class:
- Average throughput vs. target.
- Tail latency (p95, p99, p99.9) vs. PDB.
- Packet loss / discard rate.
- BLER per UE.
- PRB utilization (DL, UL, S-slot DL, S-slot UL).
- PDCCH utilization.

### Test scenarios
1. **Single-camera stress** — one 4K/60fps camera, no other traffic. Verify SPS sizing, I-frame handling.
2. **Multi-camera scaling** — add cameras until UL capacity is saturated. Verify graceful degradation.
3. **Mixed workload** — cameras + control-loop UEs + best-effort UEs simultaneously. Verify GBR / delay targets are met for the priority classes.
4. **Adversarial best-effort** — large bulk transfer competing with priority flows. Verify isolation.
5. **PDCCH bottleneck** — many small-bitrate UEs (sensors). Verify Tier-1 correctly chooses SPS over dynamic to fit the control budget.
6. **Channel degradation** — induce BLER on one UE (attenuator, distance). Verify Tier-1's discount factor reallocates to compensate.

### Comparison points
- vs. OAI default scheduler (PF or round-robin).
- vs. Tier-2 only (no Tier-1 weights, just gradient metric with constant weights).
- Full two-tier system.

---

## 12. Open Questions and Future Work

### Open questions (still need answers)
- TDD pattern (DSUUU? something else?), numerology, carrier bandwidth — exact choice for the deployment.
- SPS periodicity quantization for 16.67 ms camera frames (16 vs 17 slots; or staggered configs).
- PDCCH overhead: actual CORESET sizing for the target deployment.
- Shared-memory mechanism between Tier-1 and Tier-2 on real hardware.
- 5QI table: which standardized 5QIs do we actually use, and what custom 5QIs do we need for industrial flows?

### Closed (decisions made during simulator work)
- Tier-1 solver: **CVXPY** with log objective and slack-penalty GBR.
- Tier-1 cadence: **1 s full re-solve, no intermediate refresh** — drift-plus-penalty handles drift.
- GBR infeasibility: **soft penalty** (slack with `1e3` weight). Keeps LP feasible under any overload; admission control can layer on top later.
- Tier-2 metric form: **drift-plus-penalty (Lyapunov virtual queues)**, not multiplicative urgency. Multiplier saturates and cannot enforce unequal targets.
- Delay urgency: scaled by **max-system-Q**, not per-flow target. Allows small periodic flows to preempt bulk flows when near PDB.
- SPS implementation: **per-slot PRB reservation, sized to (target_bps × safety_margin) averaged across direction-slots**. Right-size the actual SPS allocation to the buffer each slot (don't waste PRBs); release implicitly on empty buffer. SPS-eligible flows still participate in dynamic spillover for I-frame bursts; their dynamic-pool urgency is the buffer backlog (in bits), not the virtual queue Q (which stays small because SPS is keeping up on the average).
- SPS spillover bug to remember: SPS + dynamic-spillover for the same flow can double-drain the buffer if `bytes_capacity` is computed twice against the same backlog. The scheduler must track per-slot per-flow committed bytes and net them out before the dynamic pass.
- **SPS only shows visible benefit when PDCCH is binding.** With unlimited PDCCH, the dynamic scheduler keeps up and SPS adds no value. The simulator now models PDCCH as a per-slot CCE budget; in the sensor-dense scenario (30 small periodic UEs), TwoTier+SPS hits 100% delivery while PF caps out at 88% because dynamic allocations exhaust the CCE budget. Without modeling PDCCH, the simulator would have led to the wrong conclusion that "SPS is unnecessary."

### Future work (out of initial scope)
- MU-MIMO scheduling — could roughly double UL capacity for cameras.
- Dynamic TDD — pattern adapts to instantaneous DL/UL ratio.
- BWP switching for power-constrained sensors.
- Cross-cell coordination (multi-gNB).
- ML-driven channel prediction to inform Tier-1.
- Joint MCS + PRB optimization (currently MCS is link-adaptation-driven independently).

---

## Appendix A: Notation

| Symbol | Meaning |
|---|---|
| `r_{i,q}` | Bits delivered for UE *i*, QFI *q* in horizon |
| `R_{i,q}` | Smoothed average throughput for (i, q) |
| `GFBR` | Guaranteed Flow Bit Rate (5G QoS profile field) |
| `PBR` | Prioritized Bit Rate (LCP per-DRB token rate) |
| `PDB` | Packet Delay Budget |
| `5QI` | 5G QoS Identifier (rule template) |
| `QFI` | QoS Flow Identifier (per-PDU-session label) |
| `DRB` | Data Radio Bearer (RLC queue at the gNB) |
| `MCS` | Modulation and Coding Scheme |
| `TBS` | Transport Block Size |
| `BLER` | Block Error Rate |
| `CCE` | Control Channel Element (PDCCH) |
| `AL` | Aggregation Level (CCEs per DCI) |
| `SPS` | Semi-Persistent Scheduling / Configured Grant |

## Appendix B: References

- Kelly, Maulloo, Tan (1998) — utility-based rate control.
- Stolyar — gradient scheduling and Lyapunov drift-plus-penalty.
- Shakkottai & Stolyar — Exp-rule, Log-rule for delay-aware scheduling.
- 3GPP TS 23.501 — 5G system architecture and QoS framework (5QI, QFI, PDB).
- 3GPP TS 38.300 — NR overall description.
- 3GPP TS 38.214 — NR PHY procedures for data (TBS, MCS).
- 3GPP TS 38.321 — NR MAC (LCP, HARQ, SPS, Configured Grants).
- OpenAirInterface project — [https://gitlab.eurecom.fr/oai/openairinterface5g](https://gitlab.eurecom.fr/oai/openairinterface5g).
