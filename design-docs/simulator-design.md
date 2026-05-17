# Lightweight Scheduler Simulator

**Status:** Implemented and running. Most `[OPEN]` items closed during the
build; remaining ones are flagged inline.
**Companion to:** [scheduler-design.md](scheduler-design.md)
**Purpose:** Validate the two-tier scheduler design quantitatively before
investing in an OAI integration.

---

## 1. Goals and Non-Goals

### Goals
- Compare scheduler designs (default PF, Tier-2 only, full two-tier) on identical workloads.
- Run thousands of scenario variations in minutes, not hours.
- Produce defensible quantitative results: per-flow throughput, latency distributions, PDB violation rates, PRB utilization, fairness indices.
- Provide a clean scheduler interface so the same scheduler module can later be lifted into OAI with minimal changes.
- Be readable end-to-end in an afternoon (~500–1000 LOC target).

### Non-Goals
- PHY-layer fidelity. No LDPC, no I/Q samples, no actual modulation.
- Byte-accurate RLC segmentation, header overhead modeling, or precise HARQ buffer state.
- Multi-cell, mobility, handover.
- Conformance with any 3GPP test suite.
- Real-time execution. Simulator runs as fast as the host can.

### What "good enough" means here
The simulator's purpose is to answer **comparative** questions ("does the two-tier scheduler beat baseline PF on this workload, and by how much?"), not **absolute** questions ("what is the actual throughput of a 30 MHz carrier?"). Approximations are fine as long as they apply consistently across scheduler variants being compared.

---

## 2. Fidelity Discipline

Where to be careful, where to approximate.

| Aspect | Modeled how | Why |
|---|---|---|
| Time | Discrete slots | Matches scheduler decision cadence |
| PRB grid | Symbol-RB count, including S-slot | This is what the scheduler actually allocates |
| Channel | Per-UE SNR as stochastic process | Drives MCS selection; affects effective bits |
| MCS → bits | TBS lookup table (3GPP-derived or simplified) | Captures the non-linearity that matters |
| BLER | Per-UE error rate, applied as a discount on delivered bits | Captures retransmission cost without simulating HARQ buffers |
| HARQ retransmits | Lump as added delay (e.g., +4 slots for retransmit) | Avoid full HARQ state machine |
| RLC segmentation | Treat DRB as a fluid byte buffer | Avoid per-packet bookkeeping |
| Header overhead | Constant tax per grant | Captures the "small grant inefficiency" effect |
| PDCCH | Count CCEs against a per-slot budget | The control bottleneck is real and matters |
| HARQ ACK / k1 timing | Counted but not full simulated | Just enforce that DL needs a downstream PUCCH slot within k1_max |
| Multi-antenna / MIMO | Single-stream only | MU-MIMO is future work |

`[OPEN]` Whether to model packet boundaries at all, or strictly fluid bits. Fluid is simpler and probably sufficient for scheduler-level questions; packet-aware is needed if we want to simulate concatenation overhead per SDU. Recommendation: start fluid, add packet-awareness only if a metric demands it.

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  Simulator (driver loop)                                       │
│                                                                │
│   for slot in range(N):                                        │
│      traffic.generate(slot)         → arrivals → buffers       │
│      channel.update(slot)           → per-UE SNR               │
│      grid = resource.slot_grid(slot)                           │
│      decisions = scheduler.allocate(grid, buffers, channel)    │
│      transmissions = apply(decisions, channel)                 │
│      buffers.drain(transmissions)                              │
│      metrics.record(slot, transmissions, buffers)              │
└────────────────────────────────────────────────────────────────┘

Modules:
  - TrafficModel         per-(UE, QFI) arrival generators
  - ChannelModel         per-UE SNR / CQI process
  - BufferModel          per-(UE, DRB) FIFO byte-buffers, HoL timestamps
  - ResourceGrid         TDD pattern, per-slot DL/UL PRB pool, PDCCH budget
  - Scheduler            pluggable interface; baseline + two-tier impls
  - LinkAdaptation       SNR → MCS → bits-per-PRB
  - Metrics              per-flow stats, exportable to CSV / Parquet
```

### Module independence
Each module has a narrow interface. Replacing the channel model (e.g., from AR(1) to a trace-driven model) shouldn't ripple into the scheduler or traffic model.

---

## 4. Time Model

- Simulator advances in **slot ticks**.
- Slot duration: configurable (matches numerology). Default: 0.125 ms (μ=3) per [scheduler-design.md §3](scheduler-design.md).
- Simulation horizon: configurable. Default: 10 s = 80,000 slots at μ=3.
- Sub-slot fidelity (e.g., per-symbol allocation): **not modeled**. A UE either gets a slot's worth of PRBs or doesn't. `[OPEN]` Revisit if mini-slot scheduling effects matter for a specific scenario.

---

## 5. Traffic Model

### Per-flow generators
Each flow is a generator that produces (arrival_time, byte_count) tuples per slot. Mix and match per scenario.

| Generator | Use for | Params |
|---|---|---|
| `Deterministic` | SPS-eligible periodic flows | period, bytes_per_period |
| `VideoFrame` | 4K/60fps with I-frame bursts | period (16.67 ms), avg_bytes, I_frame_multiplier, I_frame_period_in_frames |
| `PeriodicSmall` | Control-loop sensors | period, bytes_per_period, jitter_pct |
| `Poisson` | Best-effort bursty | rate (bytes/sec), max_burst |
| `TraceDriven` | Replay measured or synthetic traces | trace file path |

### Per-flow metadata (set at flow creation, used by scheduler)
- `ue_id`
- `qfi` (label for scheduler)
- `5qi_class` (PF / GBR / Delay) — drives gradient choice in Tier-2
- `pdb_ms` — packet delay budget
- `gfbr_bps` — guaranteed bit rate (if GBR)
- `direction` — UL or DL

### What "arrival" means in the fluid model
Arrivals add bytes to the per-(UE, DRB) buffer with a timestamp. The HoL delay is the timestamp of the oldest unsent byte. No per-packet boundary tracking.

`[OPEN]` Should I-frame bursts be modeled as a single arrival event (atomic) or as a chunked stream? Atomic is simpler and matches how a frame becomes available all at once after encoding.

---

## 6. Channel Model

### Per-UE SNR process
- Default: AR(1) on dB-scale SNR.
  - `SNR(t+1) = α · SNR(t) + (1-α) · mean_SNR_i + noise`
  - `α` chosen to give a target coherence time. For static factory: `α` close to 1 (long coherence).
- Alternative modes (configurable):
  - `Static`: SNR fixed per UE for entire run.
  - `Block`: SNR redrawn every K slots (block fading).
  - `TraceDriven`: replay measured CQI traces.

### SNR → CQI → MCS → bits-per-PRB
- Use a simplified mapping table (5–15 MCS levels) that captures the staircase between SNR ranges and effective spectral efficiency.
- `[OPEN]` Use a real 3GPP TBS table extract, or a fitted curve (e.g., Shannon scaled by 0.75)? Fitted curve is simpler; TBS extract is more defensible.

### BLER
- Per-MCS BLER target: 10% (configurable). The link adaptation aims for this.
- Implementation: when scheduler grants `B` bits to UE *i*, only `B · (1 - BLER_i)` bits are recorded as delivered. The remaining `B · BLER_i` bytes stay in the buffer (modeling the retransmission requirement) and are flagged with a "retransmit available after k slots" timestamp.

### Multi-UE on same PRBs
Not modeled. Each PRB goes to exactly one UE per slot.

---

## 7. Buffer Model

### Per (UE, DRB) state
- `bytes_queued`: total backlog
- `hol_timestamp`: arrival time of oldest queued byte
- `bytes_in_retransmit`: bytes pending retransmit (with available-from timestamp)
- `bytes_dropped_pdb`: cumulative PDB violations

### Operations
- `enqueue(bytes, timestamp)`: add arrivals.
- `drain(bytes)`: remove bytes from head. Returns the (bytes, oldest_timestamp_drained) for latency accounting.
- `expire(now, pdb_ms)`: drop bytes whose age exceeds PDB; bump dropped counter.
- `hol_delay(now)`: `now - hol_timestamp` if queued > 0 else 0.

### DRB ↔ QFI mapping
- For initial scope: one DRB per QFI. Avoids HoL blocking. Matches the recommendation in [scheduler-design.md §10](scheduler-design.md).
- `[OPEN]` Add multi-QFI-per-DRB support if we want to study HoL blocking effects later.

---

## 8. Resource Grid

### Per-slot view
Given the configured TDD pattern (e.g., DSUUU), the simulator tells the scheduler what's available **this slot**:

```python
@dataclass
class SlotGrid:
    slot_index: int
    direction: Literal['DL', 'UL', 'S']
    dl_symbols: int           # usable DL symbols this slot
    ul_symbols: int           # usable UL symbols this slot
    prb_count: int            # number of PRBs across the carrier
    pdcch_cce_budget: int     # CCEs available for dynamic grants this slot
```

### TDD pattern
- Configured as a string + S-slot split (e.g., `"DSUUU"`, S = 3:2:9 DL:Guard:UL).
- The grid module rotates through the pattern.

### PRB count
- Derived from carrier bandwidth and numerology. E.g., 30 MHz at μ=1 → 78 PRBs.

### Reserved overhead
- A configurable fraction (e.g., 15%) of nominal symbol-RB capacity is subtracted for reference signals, PUCCH region, etc. Captured as a flat scaling factor on `prb_count` or `dl_symbols / ul_symbols`.

### PDCCH budget
- Per-slot CCE count, configurable (e.g., 48 CCEs in the D-slot, 0 in U-slots).
- Each dynamic grant consumes CCEs based on aggregation level (function of UE SNR).
- SPS-served flows do **not** consume PDCCH per slot.

---

## 9. Scheduler Interface

### The contract (as implemented)
```python
class Scheduler(Protocol):
    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: ResourceGrid,
    ) -> None: ...

    def allocate(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
    ) -> list[Allocation]: ...

@dataclass
class Allocation:
    ue_id: int
    qfi: int
    direction: str            # 'DL' or 'UL'
    prbs: int
    bytes_capacity: int       # MCS-derived bits → bytes for this allocation
    cce_cost: int = 0         # 0 if SPS, else AL_i
    is_sps: bool = False
```

`grid` is passed to `configure()` so schedulers (specifically TwoTier) can
compute total per-direction PRB-symbol capacity for the LP.

### Reference implementations (all in [sim/schedulers/](../sim/schedulers/))
1. **`RoundRobin`** — sanity check; one flow per direction per slot.
2. **`ProportionalFair`** — standard PF: `r_inst(t) / R_avg(t)` with EWMA
   smoothing. Multi-UE per slot via greedy fill.
3. **`GradientScheduler`** — per-class urgency multipliers on top of PF
   metric (PF / GBR-deficit / Delay-HoL). Hardcoded weights; no Tier-1.
   Useful as a "class-aware-but-no-Tier-1" baseline.
4. **`TwoTier`** — the design under test:
   - `Tier1`: CVXPY LP every N slots ([sim/tier1.py](../sim/tier1.py))
     produces per-flow target rates.
   - `Tier2`: drift-plus-penalty (Lyapunov virtual queues), with
     max-system-Q-scaled delay urgency for deadline-pressed Delay flows.

### Why drift-plus-penalty in Tier-2

The first cut used a multiplicative urgency formula
`(r_inst / R_avg) × (1 + deficit_w · max(0, 1 − R_avg/target))`. This
**saturates**: it equalizes weighted (1/R_avg) across flows, not actual
rates against arbitrary targets. Even with `deficit_w → ∞`, the GBR target
can't be enforced exactly. Drift-plus-penalty (virtual queues that grow
when behind target, shrink when ahead) is the right tool for rate-tracking
and works with no tuning of the deficit constant.

### SPS in the simulator

SPS-eligible flows (deterministic and video_frame) get a per-slot PRB
reservation sized to `target_bps × safety_margin` averaged across
direction-slots in the TDD cycle. Each slot, the SPS reservation is
right-sized to the buffer (so a steady-state P-frame doesn't waste PRBs),
and SPS allocations don't consume PDCCH CCEs. SPS flows *also* participate
in the dynamic pool for I-frame burst spillover; their dynamic urgency is
the actual buffer backlog (bits), not the virtual queue Q (which stays
small because SPS is keeping up on average).

**Two SPS-related bugs to know about:**
1. *Double-allocation:* SPS + dynamic-spillover for the same flow can
   over-drain the buffer if both compute `bytes_capacity` from the same
   un-drained backlog. The scheduler now tracks per-slot per-flow
   commitments and nets them out before the dynamic pass.
2. *Right-sizing:* without it, SPS holds reserved PRBs even when the
   buffer is small (P-frame steady state), wasting capacity that the
   best-effort flow could use.

### Why SPS needs PDCCH modeling to look useful

Without per-slot CCE budget enforcement, SPS made no measurable
difference in any scenario — the dynamic scheduler kept up just fine.
That was the simulator missing the actual reason SPS exists in real 5G:
it bypasses the per-allocation DCI cost on the PDCCH. After adding a
per-slot CCE budget, the sensor-dense scenario shows the expected story
clearly: PF tops out at ~88% delivery (DCI-capped); TwoTier with SPS
hits 100% because each SPS allocation costs zero CCEs.

Lesson: when modeling a control-plane mechanism, you also have to model
the resource it competes for. Otherwise the mechanism looks redundant.

### Variable DCI aggregation level changes the regime

Initially the simulator used a fixed AL=4 (4 CCEs per DCI). After making
AL vary with per-UE SNR — `AL ∈ {1,2,4,8,16}` per the standard 3 dB
robustness staircase — the PDCCH-pressure regime narrowed:

| Sensor SNR | PF AL | PDCCH bound? | PF delivery | TwoTier delivery |
|---|---|---|---|---|
| 22 dB (factory good) | 1 | no | 98% | 100% |
| 12 dB (mid) | 2 | yes | 79% | 100% |
| 8 dB (edge) | 4 | yes | 60% | 100% |
| 6 dB (very edge) | 8 | both PDCCH and PRB | 46% | 58% |

Two takeaways:
1. SPS's value depends heavily on the SNR distribution of the periodic
   flows. A factory full of good-channel UEs may not need SPS for PDCCH
   reasons (though latency benefits remain).
2. The default `sensor_dense_scenario` uses SNR=12 dB (AL=2) so the
   demonstration sits in a clearly PDCCH-bound regime under varying AL.

### Per-slot time-series for plotting

`run(scenario, scheduler, record_timeseries=True)` returns the usual
summary plus a `timeseries` dict containing per-slot per-flow backlog,
HoL delay, delivered/arrived/dropped bytes, and per-slot system PRB and
CCE utilization. Memory footprint is small (a few MB for the canned
scenarios). The companion `scripts/plot_timeseries.py` produces
multi-panel matplotlib plots — single-scheduler mode for per-flow detail,
two-scheduler mode for overlay comparison. Sample plots in
[design-docs/figures/](figures/).

### Tier-1 invocation in the simulator
- Tier-1 runs synchronously between slots in the simulator (no separate thread). Solve time is recorded but doesn't gate the simulation.
- This decouples "is the algorithm correct?" from "is the implementation fast enough?". The latter is an OAI-side concern.

`[OPEN]` Whether to also model the **side-effect** of Tier-1 solve time — e.g., if the LP takes longer than the inter-solve interval, weights become stale. Probably yes, as a configurable knob, since this matters for OAI.

---

## 10. Link Adaptation

Separated module so the channel-to-bits mapping is consistent across all schedulers.

```python
def bits_per_prb(snr_db: float, target_bler: float = 0.1) -> tuple[int, float]:
    """Returns (bits_per_PRB_per_slot, achieved_BLER) for the chosen MCS."""
```

Implementation: lookup table or fitted curve. `[OPEN]` Pick approach.

---

## 11. Metrics and Output

### Per-flow time-series (sampled every K slots)
- Throughput (instantaneous and smoothed).
- HoL delay.
- Buffer occupancy.
- Bytes dropped (PDB violations).

### Per-flow aggregates (end of run)
- Average throughput vs. target.
- p50, p95, p99, p99.9 packet latency.
- PDB violation rate.
- GBR satisfaction ratio (fraction of time GFBR was met).

### Per-UE aggregates
- Total bytes delivered.
- Average MCS / spectral efficiency achieved.
- Effective BLER.

### System aggregates
- DL / UL PRB utilization.
- PDCCH utilization.
- Jain's fairness index across PF flows.
- Sum log throughput (the actual PF objective).

### Output format
- CSV or Parquet for per-flow time series.
- JSON for the run summary.
- `[OPEN]` Add structured logging for debugging individual scheduling decisions? Useful for first-pass debugging, expensive at scale.

---

## 12. Validation Strategy

How we know the simulator is trustworthy enough for comparative claims.

### Sanity checks
- With one UE and infinite buffer: throughput approaches MCS × PRBs × slot rate.
- With K identical UEs and round-robin: each gets 1/K of the airtime.
- With heterogeneous channel + PF: known behavior (PF favors instantaneous peaks but maintains long-run fairness).

### Cross-checks
- Compare **DefaultPF** in our simulator against published PF results on similar workloads. Order-of-magnitude agreement is sufficient.
- Compare **DefaultPF** against OAI's PF in a single carefully-constructed scenario (one UE, one flow, static channel). If our simulator's throughput matches OAI's within ~20%, the macro behavior is captured.

### What we explicitly don't validate
- Absolute latency numbers within a few microseconds — those depend on PHY detail we don't model.
- PHY-layer effects (CSI accuracy, beamforming gains, etc.).

`[OPEN]` Decide a "trust threshold" before running comparative experiments — e.g., the simulator must reproduce two well-known qualitative results (PF vs. RR fairness; SPS vs. dynamic latency for periodic traffic) before its claims about the two-tier scheduler are believable.

---

## 13. Implementation Plan

### Language and dependencies
- **Python 3.11+** for the simulator core.
- `numpy` for channel processes and metrics.
- `cvxpy` (or `scipy.optimize.linprog`) for the Tier-1 LP. `[OPEN]` Pick.
- `pandas` / `pyarrow` for output.
- No web frameworks, no ORMs, no plugin systems. Single-process, single-thread.

### Actual directory structure (as built)
```
sim/
  __init__.py
  driver.py              # main simulation loop
  config.py              # scenario config dataclasses
  traffic.py             # TrafficModel and generators (incl. video_frame
                         # with i_frame_phase for staggering)
  channel.py             # ChannelModel + bits_per_prb (link adaptation)
  buffer.py              # BufferModel
  resource.py            # ResourceGrid + TDD pattern + per-slot CCE budget
  metrics.py             # collectors and exporters (incl. CCE utilization)
  scenarios/             # ran / simulation / scenario YAML configs + loaders
  tier1.py               # Tier-1 CVXPY LP solver
  schedulers/
    __init__.py          # Scheduler protocol + Allocation + DEFAULT_DCI_CCE_COST
    round_robin.py
    pf.py                # ProportionalFair baseline (PDCCH-aware)
    gradient.py          # Class-aware multiplicative urgency (PDCCH-aware)
    two_tier.py          # Tier-1 LP + Tier-2 drift-plus-penalty + SPS
scripts/
  run_smoke.py           # one scheduler, one scenario, dump JSON
  compare_schedulers.py  # all schedulers x all scenarios, side-by-side
  scheduler_study.py     # overload-sweep / PDCCH / latency studies
  transient_check.py     # long-run windowed steady-state check
  plot_timeseries.py     # per-slot multi-panel matplotlib plots
tests/
  test_smoke.py          # buffer, channel, grid, all schedulers, SPS / PDCCH,
                         # penalty knobs, latency-bound deadline protection
  test_config_loader.py  # every scenario_config_<n>.yml loads and runs
```

Scenario files are YAML in [sim/scenarios/](../sim/scenarios/), split three
ways — `ran_config_<id>.yml` (radio), `simulation_config.yml` (run window),
and `scenario_config_<n>.yml` (workload, naming a `default_ran`) — so one
workload can be exercised on different radios. Assembled by
`config_loader.py`. (Earlier these were Python builders, then single
self-contained files; the three-way split came once RAN exploration
mattered.)

### Build status
1. ✅ Skeleton + RoundRobin: driver loop, traffic, channel, buffer, grid, metrics.
2. ✅ ProportionalFair: standard PF baseline.
3. ✅ Gradient: class-aware metric with hardcoded urgency weights (no Tier-1).
4. ✅ Tier-1 LP (CVXPY) + TwoTier scheduler with drift-plus-penalty.
5. ✅ SPS / Configured Grants in TwoTier (right-sized PRB reservation +
      dynamic spillover for I-frame bursts).
6. ✅ PDCCH/CCE per-slot budget enforcement across all schedulers.
7. ✅ Variable DCI aggregation level (1, 2, 4, 8, 16 CCEs based on UE SNR).
8. ✅ Per-slot time-series recording (opt-in) + matplotlib plotting script
      (`scripts/plot_timeseries.py`).
9. ✅ Validation: 23 unit tests covering every scheduler + SPS accounting +
      PDCCH cap + sensor-dense regression + AL monotonicity + ts shape.
10. ⏳ Real 3GPP TBS table (current spectral efficiency is a fitted curve).

---

## 14. Open Questions and Future Work

### Closed (decisions made during the build)
- **Buffer model:** fluid bytes with per-chunk arrival timestamps for HoL.
- **Spectral efficiency:** fitted staircase keyed off SNR, BLER-discounted.
- **LP solver:** CVXPY (flexible, easy to read; slow doesn't matter at 1 Hz).
- **Output format:** JSON summary; per-slot time series not implemented yet.
- **Channel model:** AR(1) with proper stationary innovation scaling
  (`σ × √(1 − α²)`). Without this, high-coherence configs walk off and ruin
  comparisons.
- **Tier-1 cadence:** every N slots; no "stale weight" simulation needed
  — Tier-2's drift-plus-penalty smooths over inter-solve drift.

### Open questions (still open)
- TBS table accuracy: fitted curve is fine for comparative work; would
  want a real 3GPP TBS extract for absolute claims.
- Trace-driven traffic from real factory measurements (none collected yet).
- UL DCI accounting is amortized into U-slot CCE budget; in real 5G the
  DCI was issued in an earlier D-slot. Reasonable approximation but worth
  revisiting if PDCCH-edge scenarios become important.

### Future work
- Trace-driven workloads from real factory measurements (when available).
- MU-MIMO support if the scheduler design extends to it.
- Multi-cell / inter-cell interference (probably out of scope forever).
- Cython / Numba acceleration if scenarios grow beyond ~10 s wall-clock per run.
- Optional GUI / dashboard for live visualization (low priority).

---

## Appendix: Relationship to OAI Integration

The simulator and OAI are complementary, not competing.

| Question | Answered by |
|---|---|
| Does the algorithm beat the baseline on representative workloads? | Simulator |
| What are the failure modes / edge cases of the design? | Simulator |
| How sensitive are results to weight tuning? | Simulator |
| Does the implementation fit in the per-slot budget on real hardware? | OAI |
| Does it interoperate with real UEs? | OAI |
| Are the SPS configurations actually accepted by 3GPP-compliant UEs? | OAI |

The Tier-1 LP formulation and Tier-2 gradient metric should be **identical** between the simulator and the eventual OAI integration. Same Python code can run as the Tier-1 thread in OAI; Tier-2 will need a C/C++ port but its logic should mirror the Python reference.
