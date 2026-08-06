# QoS-Optimized Two-Tier Scheduler for Private 5G

**Status:** Implemented and validated in simulation; the scheduler is
extracted into a standalone `scheduler/` library for OAI integration.
Remaining `[OPEN]` markers are deployment choices, not algorithm gaps.
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

Implemented in [scheduler/tier1.py](../scheduler/tier1.py) (`solve_tier1` accepts a
per-flow penalty dict) and [scheduler/two_tier.py](../scheduler/two_tier.py)
(`_update_gbr_penalties`, knobs `gbr_penalty_init / _lr / _max`).

**When to use it.** The 2026-05-17 scheduler study (see [NOTES.md](../NOTES.md))
found dual ascent is the wrong *shape* under deep overload: equalising
normalised shortfall parks every flow just below its floor, since a GBR
contract is a step function. It raises worst-case *min* delivery but
*lowers* the count of flows that actually meet GFBR (0/10, vs 3/10 for the
fixed penalty, at 1x deep overload). Recommended default is
`gbr_penalty_lr = 0`;
genuine infeasibility calls for admission control, not penalty escalation.
The adaptive penalty's role is narrow — fairness-of-shortfall reporting,
not contract satisfaction.

### Spectral-efficiency tilt of the penalty (knob `k`)

A second, *static* lever on the penalty: scale each flow's `p_i` by its
spectral efficiency, `p_i ← p_i · (SE_i / SE_max)^k`.

The lever exists because the LP allocates RBs, not bps. The marginal
objective gain of one RB spent closing flow `i`'s GBR gap is `p_i · SE_i`
(an RB buys `SE_i` bps of slack reduction). So:

- `k = 0` — off. Per-RB priority `∝ SE_i`; the objective already favours
  high-SE flows.
- `k > 0` — *efficiency-first*. Per-RB priority `∝ SE_i^(1+k)`; poor-SE
  flows' shortfall drags the objective down less.
- `k < 0` — *RB-level parity*. `k = -1` makes per-RB priority `∝ const`:
  every GBR gap is equally urgent per RB, regardless of channel.

Empirically (10-robot scenario, `gbr_penalty_lr = 0`): `k > 0` is a near
no-op — the objective is already efficiency-tilted, so the cell-edge GBR
flows are sacrificed at `k = 0` and `k > 0` cannot sacrifice them further.
`k < 0` does rescue the cell-edge flows (ue4 8→65 %, ue7 4→64 % at
`k = -1`) but **only relocates** starvation: it re-sorts victims by SE
rank, crushing the next tier (ue8/9/10) and lowering both mean GBR
delivery and total throughput. A static tilt cannot lift the worst-case
floor — only the adaptive penalty above does that, because it targets the
flow that is *actually* missing rather than re-ranking by channel. The two
mechanisms interfere: `k < 0` stacked on `lr > 0` overshoots the adaptive
correction and lowers the floor again. Recommended default: `k = 0`; treat
`k > 0` as an explicit "efficiency over cell-edge" policy choice.

Knob: `gbr_penalty_se_exponent` on `TwoTier`; `se_penalty_exponent` on
`solve_tier1`.

### Max-min GBR stage (two-stage solve) — the Finding 1 fix

Both knobs above reweight the penalty vector `p`, and **neither can work**.
At the default `p = 1e3` the penalty term outweighs the log utility by ~1e7
(measured: 2.4e10 vs 709 on `factory_robots`), so the program is effectively
the LP `min Σ(GFBR_i − r_i)` s.t. `Σ r_i/SE_i ≤ C` — a fractional knapsack
whose optimum is greedy in spectral efficiency, and whose solution therefore
sits at a **vertex**: flows are served in full or abandoned, with at most one
partially-served flow per SE tier. Reweighting `p` chooses a different
vertex; it never removes the abandonment. `k < 0` permutes the victim set,
dual ascent promotes one flow and demotes another. Only changing the
*feasible region* — a constraint, not a weight — changes the outcome.

So Tier-1 optionally runs a **max-min satisfaction stage first**:

```
stage A:   maximize  t
           s.t.  r_i ≥ t · contract_i        ∀ i: c(i) = GBR
                 capacity, demand caps, soft slice floors
                 0 ≤ t ≤ 1

stage B:   the objective above, plus the hard floor
                 r_i ≥ scale · t* · contract_i
```

- `t*` is the largest fraction of its contracted floor that *every* GBR flow
  can hold at once. `t* = 1` means the GBR set is jointly feasible and the
  floor is non-binding — the stage is self-disabling exactly where the
  single-stage solve is already right.
- `contract_i = min(GFBR_i, demand_i)`. The demand cap is load-bearing: an
  under-offered GBR flow would otherwise pin `t*` at its own unreachable
  ratio and drag the whole set down with it.
- The soft GFBR constraint is **kept** in stage B, so the utility term still
  has an incentive to close the gap from the floor up to full GFBR wherever
  that is cheap. Stage B is feasible by construction.
- `scale ∈ [0,1]` trades the guarantee against throughput; `0` recovers the
  single-stage solve exactly. On `factory_robots` at 1.0× load the curve is
  smooth and monotone (min GBR delivery 0 → 40% as scale goes 0 → 1, for
  −10% total throughput), with the knee near `0.75`.

Both stages are posed in **normalised units** — rates as a fraction of the
largest contract, capacity usage as a fraction of each direction's budget.
This is not cosmetic: posed in raw bps, maximising a unit-scale `t` against
1e7-scale rates made the solver return `optimal` on a `t*` that was
*non-monotone in capacity*, which is impossible for a max-min level. See
NOTES.md 2026-08-06.

Knobs: `gbr_maxmin`, `gbr_maxmin_scale` on `TwoTier`; `gbr_floor_bps` on
`solve_tier1`, built by `gbr_maxmin_floors` from `solve_maxmin_gbr_level`.
Default **off**, so the published study numbers reproduce unchanged.

**What it does not do.** It cannot raise the count of flows *meeting* GFBR:
a contract is a step function, and a uniform 59% satisfies nobody. Max-min
and contract-count are genuinely opposed objectives — the latter is a
knapsack over contracts, i.e. an admission-control decision, out of scope
here. Tier-1 does hand that gate a clean signal for free: `t* < 1` is the
infeasibility detector and `t*` measures how far off the GBR set is.

### Network slicing (soft RB-share floors)

Each flow carries a `slice_id`. An operator gives each network slice a
guaranteed fraction of per-direction PRB-symbol capacity via
`slice_shares = {slice_id: {"DL": frac, "UL": frac}}`. Tier-1 enforces it
as a soft floor — the same shape as the GBR floor:

```
Σ_{i ∈ slice s, dir d} r_i/SE_i  +  slice_slack_{s,d}  ≥  min(share_s·C_d, slice_demand_{s,d})
```

- The floor is capped at the slice's own offered demand, so an idle slice
  holds no capacity.
- The per-direction capacity constraint keeps it **work-conserving**: a
  busy slice freely borrows an idle slice's unused share. Modelling the
  share as a guaranteed *minimum* (not a hard cap) is what makes that
  borrowing free.
- The slack is penalised (`slice_slack_penalty`), so the LP stays feasible
  when slice floors and GBR floors cannot all be met.

Tier-2 needs no slice logic — it tracks the now slice-aware Tier-1 targets.

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

**Slice partitions:** soft per-slice RB-share floors — see "Network slicing" above.

**HARQ feedback feasibility (TDD):** for each UL transmission slot, there must be a downstream D-slot or S-slot DL portion within k1_max for the ACK/NACK. In DSUUU this is tight — the single D-slot per cycle has to carry HARQ feedback for 3+ U-slots.

### Infeasibility handling
What does Tier-1 do when GBR demand exceeds capacity? **Decided** (2026-08-06):
soft GBR floors for runtime feasibility, plus the optional max-min stage
above when the sacrifice must be shared rather than concentrated.

- Option A (hard constraints) is unusable alone — the program goes
  infeasible the moment GBR demand exceeds capacity, which is exactly when
  an answer is still needed.
- Option B (soft penalty) does *not* "fail gracefully by under-serving the
  lowest-priority GBR": with a uniform penalty it under-serves the
  **lowest-spectral-efficiency** flow, to zero, regardless of priority. That
  is the fractional-knapsack result above, and it is why the max-min stage
  exists.
- Runtime answer: B, with `gbr_maxmin` when a shared floor is wanted.
- `t* < 1` from stage A is the admission-control trigger — it detects
  infeasibility *and* quantifies it before any flow is starved to reveal it.
  The admission gate itself is out of scope for the scheduler.

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
ahead.

**Scheduling is per UE**, mirroring the 5G MAC: one grant — one DCI, one
transport block — per UE per slot. Each UE is ranked by the summed
drift-plus-penalty deficit of its backlogged flows, weighted by its
spectral efficiency:

```
ue_metric = ( Σ_{f ∈ UE}  Q_f + delay_urgency_f ) · spectral_efficiency_UE
```

A granted UE gets PRBs sized to a transport block; a **MAC logical-channel
multiplexer** then fills the TB across the UE's flows — in `priority_level`
order, and within a priority tier by drift-plus-penalty deficit. The rule
is opportunistic (good channel → high `spectral_efficiency`) AND
rate-tracking (a flow behind its target → high Q); long-run delivered rate
converges to the `r_target` Tier-1 set.

### Implementation details that matter

1. **Clamp Q to a windowed ceiling.** After growing Q by the target
   inflow, clamp it to the bits the flow legitimately should have
   delivered over the last Tier-1 window but did not:
   `ceiling = max(0, min(target·W, arrived_W) − delivered_W)` over a
   trailing `tier1_period` window. A flow cannot be owed more than its
   target, nor more than what actually arrived. A *windowed* arrival count
   — not the instantaneous backlog — is essential: a bursty flow's buffer
   momentarily empties between frames, and clamping Q to that near-zero
   backlog would destroy its rate-tracking debt and let continuous flows
   starve bursty GBR ones.

2. **Delay urgency scaled by max-system-Q, not per-flow target rate.**
   Small periodic flows (low `target_bps` → tiny `Q`) cannot compete with
   bulk flows on absolute Q. The fix:
   ```
   delay_bonus = delay_w · (HoL/PDB)^k · max(Q across all flows)
   ```
   This makes deadline-pressed delay flows preempt anything when their HoL
   approaches PDB. The bonus is folded into each flow's `Q_f` before the
   per-UE sum.

3. **One DCI per UE.** A UE's whole transport block — all its flows — costs
   a single DCI, not one per flow. The MAC multiplexer fills the TB; the
   PRB count and CCE cost ride on the grant, not the logical channels.

4. **Transport-block right-sizing.** A granted UE gets only as many PRBs
   as its total backlog needs. Greedy fill across UEs in metric order.

### Per-slot flow
1. Grow each virtual queue by its target inflow; clamp to the windowed
   ceiling.
2. For each direction (DL, then UL):
   - **SPS** — serve each UE's configured grant; the MAC multiplexer fills
     the SPS transport block across the UE's flows.
   - **Dynamic** — rank UEs by `ue_metric`; on the remaining PRBs grant
     each UE a transport block (one DCI) and MAC-multiplex it across the
     UE's flows.
3. Drain each served flow's virtual queue by its expected delivered bits
   (post-BLER).

### Where Tier-1 and Tier-2 meet
- Tier-1 produces: per-flow target rates `r_target_i`, and (inside the
  scheduler) the SPS reservations and slice-aware allocation derived from
  those targets.
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

**Caveat — this is a single favourable scenario.** A 3-flow cell with no
SNR diversity and no mixed-flow UEs flatters the two-tier system. The
authoritative comparison is the contract-oriented scheduler study
(`scripts/scheduler_study.py`, results in [NOTES.md](../NOTES.md)): the
two-tier advantage is real but regime-dependent — it shows at moderate
overload and in the PDCCH-limited and latency-bound regimes, and largely
vanishes at deep overload or light load. Cite the study, not this table.

---

## 6. Tier-1 ↔ Tier-2 Interface

```
struct Tier1Output {
  // SPS / Configured Grants  [implemented]
  ConfiguredGrant sps[MAX_UE_QFI];          // periodicity, RB range, MCS, lifetime

  // The single load-bearing field for the dynamic pool
  float target_rate_bps[UE_ID][QFI];        // per-flow rate target

  // Slice partitioning  [implemented as soft RB-share floors]
  RBRange slice_partition[SLICE_ID];

  // Admission decisions  [planned]
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

### Sizing and the reservation policy (as implemented)
- Each SPS reservation is sized to the flow's **contracted floor** — the
  GFBR for a GBR flow, the deterministic rate for a periodic Delay flow —
  not the peak (I-frame). Bursts spill to the dynamic pool.
- Reservations are allocated per direction in **priority tiers** (lower
  `priority_level` first). Within a tier, if the floors over-subscribe the
  PRB budget, every reservation is scaled back **proportionally** — no flow
  is dropped just for being last in the flow list (NOTES.md Finding 2 was
  exactly that bug: a greedy first-come reservation starved the last UEs).
- **Viability floor:** if a tier's reservations would scale below ~75% of
  their desired size, SPS is undersized and tends to lose to the adaptive
  dynamic scheduler, so the tier runs dynamically instead — *unless*
  dropping it would overrun the PDCCH/CCE budget, in which case SPS's
  zero-DCI property keeps it. SPS is capped at ~85% of the carrier so a
  dynamic pool always remains.
- SPS is net-positive when PDCCH is the bottleneck or bursts need latency
  headroom; it is net-negative on a data-channel-overloaded link (fixed
  allocation displaces the better adaptive scheduler). See the scheduler
  study in NOTES.md.
- `[OPEN]` Periodicity quantization: 5G NR allows specific values (1, 2, 4,
  5, 8, 10, 16, 20, 32, 40, ... slots). Closest to 16.67 ms at μ=3
  (0.125 ms/slot) is 128 slots = 16 ms or 136 slots = 17 ms. Over-provision
  at 16 ms (never under-serves) or use staggered configs.

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
- Cell-edge starvation (Finding 1) is caused by the **slack penalty, not the log utility**. At `p ≳ 1` the penalty outweighs the utility by ~1e7, making Tier-1 a total-shortfall minimiser — a fractional knapsack solved greedily by spectral efficiency, whose optimum is a vertex (serve in full or abandon). No linear reweighting of `p` removes that; the log utility on its own is in fact *protective* of low-SE flows. Fix is a **max-min GBR stage** producing hard floors (`gbr_maxmin`), not a penalty tweak.
- Tier-1 programs are posed in **normalised units**. Mixing O(1) and O(1e7) magnitudes made CVXPY report `optimal` on a max-min level that was non-monotone in capacity — a silent wrong answer, not a solver error.
- Tier-2 metric form: **drift-plus-penalty (Lyapunov virtual queues)**, not multiplicative urgency. Multiplier saturates and cannot enforce unequal targets.
- Delay urgency: scaled by **max-system-Q**, not per-flow target. Allows small periodic flows to preempt bulk flows when near PDB.
- Tier-2 grants **per UE, not per flow**: one DCI per UE, one transport block, filled by a MAC logical-channel multiplexer across the UE's flows (`priority_level`, then drift-plus-penalty deficit). Mirrors the 5G MAC.
- Virtual-queue clamp: a **windowed ceiling** (`min(target·W, arrived_W) − delivered_W` over a trailing Tier-1 window), not a clamp to instantaneous backlog — the latter zeroes a bursty flow's debt between frames.
- Network slicing: **soft per-(slice, direction) RB-share floor** in the Tier-1 LP, capped at the slice's demand and work-conserving (a busy slice borrows an idle one's share).
- SPS implementation: **per-UE configured grant, each flow's reservation sized to its contracted floor (GFBR / deterministic rate)**, allocated in `priority_level` tiers with proportional scale-back and a viability floor (drop a tier to dynamic when SPS would be undersized, unless PDCCH-bound). Right-sized to the buffer each slot, released on empty. SPS flows still spill I-frame bursts into the dynamic pool; their dynamic urgency is the real backlog, not Q.
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
