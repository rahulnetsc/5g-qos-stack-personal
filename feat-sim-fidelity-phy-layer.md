# Branch: `feat/sim-fidelity-phy-layer`

**Status:** Pre-implementation  
**Parent branch:** `main`  
**Scope:** Simulator fidelity improvements — PHY-layer realism  
**Not in scope:** Scheduler algorithm changes, processing bottleneck cap, admission control

---

## 1. Motivation

The current simulator is deliberately coarse in several places that are acceptable for comparative scheduler studies on a single scenario. However, the next phase of work requires the simulator to surface effects that only appear when the channel model is closer to physical reality:

- **Cell-edge scheduling decisions** are currently distorted because all UEs share the same BLER regardless of how close they are to their MCS threshold. A cell-edge UE and a near-gNB UE both fail 10% of transmissions — an unrealistic equality that masks the real cost of serving poor-channel UEs.
- **Heterogeneous fading environments** cannot be studied because all UEs share the same stationary variance (σ = 1.5 dB). A robot near a metal wall and a robot in open space look identical to the scheduler.
- **Mobility effects** — time-varying mean SNR, velocity-dependent coherence time — are entirely absent. In a factory/warehouse target deployment, AGVs and mobile robots are a primary use case.
- **CQI staleness** is not modeled. The scheduler currently sees perfect, instantaneous SNR. In OAI, CQI reports arrive periodically (every 5–40 ms) and the scheduler always operates on a measurement that is 1–3 slots old. This is a fundamental boundary between the MAC and PHY that the current simulator erases.
- **Link adaptation** has no closed loop. Without outer-loop link adaptation (OLLA), per-UE BLER fluctuates wildly with the channel rather than being controlled toward a target, making throughput figures optimistic under fading.

These gaps matter most when studying the scheduler in scenarios involving mobile UEs, cell-edge UEs, and mixed-fidelity channel conditions — all of which are central to the OAI integration target.

---

## 2. Features Being Implemented

### 2.1 Per-UE SNR Variance

**What:** Replace the global `stationary_std_db = 1.5 dB` shared across all UEs with a per-UE `snr_std_db` field in `UEConfig`.

**Why:** Different UEs in a factory experience very different fading environments. A UE operating line-of-sight near the gNB has σ ≈ 1 dB; a UE behind shelving or near reflective surfaces has σ ≈ 3–5 dB. The shared σ means every scenario is implicitly a uniform-environment scenario, which is not the target deployment.

**What it reflects:** Heterogeneous fading. The scheduler's PRB allocation decisions, virtual queue dynamics, and BLER-discount outcomes now differ meaningfully across UEs with different physical environments, not just different mean SNRs.

**Files touched:** `sim/config.py` (add field), `sim/channel.py` (per-UE σ in AR(1) update).

---

### 2.2 Per-UE BLER Curve

**What:** Replace the flat 10% BLER across all MCS entries with a sigmoid BLER curve parameterized by the UE's SNR distance from the MCS decision threshold.

The shape is an AWGN-approximated complementary error function:

```
BLER(SNR, SNR_thresh) ≈ 0.5 · erfc((SNR − SNR_thresh) / (√2 · σ_bler))
```

with `σ_bler ≈ 1.5 dB` (the steepness of the SNR–BLER waterfall). Each MCS entry in `_MCS_TABLE` already has a threshold; BLER is now computed from the gap between the UE's actual SNR and that threshold rather than returned as a constant.

**Why:** In practice BLER is a steep sigmoid around the operating point. A UE 3 dB above its MCS threshold has BLER ≈ 1–2%; the same UE 2 dB below has BLER ≈ 30–50%. The flat 10% model uniformly understates error for near-threshold UEs and overstates it for comfortable-channel UEs. This matters for:
- Virtual queue drain accuracy (delivered = bytes × (1 − BLER) drives the Tier-2 integrator)
- Cell-edge scheduling: the true cost of serving a near-threshold UE is much higher than 10% suggests
- Any scenario where per-UE σ is nonzero — with the AR(1) channel wandering, the UE regularly crosses MCS thresholds, and the BLER swing around those crossings is large

**Files touched:** `scheduler/link.py` (`bits_per_prb` function, MCS table gains per-entry threshold annotation).

---

### 2.3 UE Mobility (Waypoint Model + Distance-Dependent Path Loss)

**What:** Add a waypoint mobility model to `UEConfig`. A mobile UE moves through a sequence of `(x, y)` waypoints at a configured speed. At each slot:

1. Position is advanced along the current waypoint segment.
2. Distance to the gNB is computed: `d(t) = √((x − x_gnb)² + (y − y_gnb)²)`
3. Mean SNR is updated via log-distance path loss: `SNR_mean_dB(t) = P_tx − PL_0 − 10·n·log10(d/d_0) − N_floor`
4. Coherence time is derived from UE velocity and carrier frequency via Doppler: `T_c ≈ v_c / (v_UE · f_c)`, giving `coherence_slots = T_c / slot_duration_s`
5. The AR(1) `alpha` is updated slot-by-slot from the new coherence time.

Static UEs (`mobility_model = "static"`) are unaffected — the existing AR(1) with fixed mean and alpha is unchanged.

**Why:** Mobile robots (AGVs, forklifts) are the primary GBR traffic source in the target deployment. Their channel varies in two ways the current model misses entirely: (a) mean SNR drifts as they move toward/away from the gNB, (b) their coherence time collapses under speed (a robot at 2 m/s at 3.5 GHz has coherence ≈ 80–150 ms, not seconds). The scheduler's EWMA (`snr_window_slots = 100`) and Tier-1's capacity estimates both depend on how fast the channel evolves — mobility stress-tests this tracking.

**What it reflects:** Time-varying channel means, velocity-dependent coherence, and the realistic trajectory of a factory robot. The interaction between mobility, per-UE BLER, and scheduler responsiveness becomes visible.

**Files touched:** `sim/config.py` (new `UEConfig` fields), `sim/channel.py` (position update, path-loss → mean SNR, Doppler → coherence → alpha update).

---

### 2.4 CQI Reporting Delay

**What:** Add a `cqi_period_slots: int` parameter to `UEConfig` (default 0 = perfect, for backward compatibility). The `ChannelModel` maintains a per-UE last-reported SNR that is only updated every `cqi_period_slots` slots. `get_snr_db(ue_id)` returns the last reported value, not the current instantaneous SNR. The true SNR is used internally for BLER computation in `driver.py` (the channel doesn't know what MCS was picked), while the scheduler sees only the stale CQI.

**Why:** In OAI, CQI reports are periodic (configurable, typically every 5–40 ms = 10–80 slots at μ=1). The scheduler's channel view is always stale by at least one reporting period. This has two consequences: (a) the scheduler may pick a higher MCS than the channel currently supports, causing elevated BLER; (b) a mobile UE's CQI goes stale faster than its channel changes, amplifying mismatches. Without this, the simulator's scheduler operates with an unfair informational advantage over any real gNB.

**What it reflects:** The fundamental MAC/PHY information boundary. CQI staleness is especially important in combination with mobility and the per-UE BLER curve — a stale CQI on a fast-moving UE causes systematic MCS over-selection, which the BLER curve then penalizes realistically.

**Files touched:** `sim/config.py` (new `UEConfig` field), `sim/channel.py` (last-reported SNR cache, `get_snr_db` returns stale value, new `get_true_snr_db` for driver).

---

### 2.5 Outer-Loop Link Adaptation (OLLA)

**What:** Add a per-UE OLLA state to `ChannelModel`. OLLA maintains a per-UE SNR offset `δ_i` (initialized to 0) that is applied to the reported CQI before MCS selection:

```
effective_SNR_i = CQI_reported_i + δ_i
```

After each grant, the offset is updated based on the BLER outcome:
- On a NACK (BLER event): `δ_i ← δ_i − olla_step_up` (back off MCS)
- On an ACK (success): `δ_i ← δ_i + olla_step_down` where `step_down = step_up × BLER_target / (1 − BLER_target)` (this asymmetry drives the steady-state BLER to `BLER_target`)

The driver calls `channel.olla_update(ue_id, had_error)` after each grant delivery.

**Why:** Without OLLA, a UE's effective BLER is determined purely by where the AR(1) process happens to sit relative to MCS thresholds. In reality, OLLA is what stabilizes per-UE BLER near 10% despite channel variability — it is active in every real gNB and in OAI specifically. Without it, the per-UE BLER curve (2.2) produces large BLER swings that look like scheduler-driven effects but are actually link-adaptation effects. OLLA is what separates the two.

**What it reflects:** The real feedback loop between HARQ outcomes and MCS selection. With OLLA active, per-UE BLER converges to ≈10% at steady state regardless of fading, and the scheduler's channel view (via effective SNR) is the correctly link-adapted one rather than raw CQI. This is the closed-loop behavior OAI implements.

**Files touched:** `sim/channel.py` (per-UE `delta_db` state, `get_effective_snr_db`, `olla_update` method), `sim/driver.py` (call `olla_update` after each delivery).

---

## 3. What Will Not Change

To ensure the before/after comparison is meaningful:

- **Scheduler logic** (`scheduler/`) — no changes. The two-tier scheduler, Tier-1 LP, Tier-2 virtual queues, SPS logic, MAC multiplexer — all untouched.
- **Traffic model** (`sim/traffic.py`) — no changes.
- **Buffer model** (`sim/buffer.py`) — no changes.
- **Resource grid** (`sim/resource.py`) — no changes.
- **Scenario configs** — the three benchmark scenarios (`factory_robots`, `sensor_dense`, `latency_bound`) are run identically on both branches. New scenarios exercising mobility and cell-edge behavior are added only on the feature branch.

---

## 4. Expected Directional Effects

These are hypotheses to be validated by the benchmark, not guarantees.

| Feature | Expected direction | Mechanism |
|---|---|---|
| Per-UE σ heterogeneity | Lower mean delivery for high-σ UEs; higher variance in per-UE results | Deeper fades cross MCS thresholds more often |
| Sigmoid BLER curve | Cell-edge UEs see higher BLER than 10%; near-gNB UEs see lower | BLER now depends on SNR–threshold gap |
| Mobility | Time-varying delivery ratio per UE; scheduler EWMA lag visible | Mean SNR drifts; coherence time collapses at speed |
| CQI delay | Elevated BLER under mobility (stale CQI → MCS mismatch) | Scheduler picks MCS based on out-of-date channel estimate |
| OLLA | BLER stabilizes near 10% at steady state despite fading | Closed-loop MCS adjustment absorbs channel variation |
| Combined | More realistic spread of per-UE outcomes; cell-edge starvation (Finding 1) appears at lower overload levels | All effects compound |

A key prediction: **Finding 1 (cell-edge GBR starvation in `factory_robots`) will appear at lower overload multipliers** on the feature branch than on main, because the realistic BLER curve makes cell-edge UEs genuinely more expensive to serve than the flat-10% model implies.

---

## 5. Before/After Comparison Plan

The benchmark script (`scripts/benchmark_phy_fidelity.py`) runs both the main-branch scenario set and the feature-branch additions, producing a structured JSON report. The comparison covers:

### 5.1 Scenarios run on both branches

| Scenario | Purpose |
|---|---|
| `factory_robots` (1.0×, 1.5×, 2.0×, 3.0× overload) | GBR contract satisfaction vs. overload — primary regression |
| `sensor_dense` | PDCCH-bound SPS behavior — should be largely unaffected by PHY changes |
| `latency_bound` | Deadline-critical mixed load — BLER/OLLA effects on HoL tail |

### 5.2 New scenarios (feature branch only)

| Scenario | What it exercises |
|---|---|
| `mobile_robots` | 4 UEs moving at 1–3 m/s; waypoint paths across a 100×60 m warehouse; mixed GBR + PF |
| `cell_edge_mix` | 3 UEs at 22 dB, 3 at 16 dB, 3 at 10 dB, heterogeneous σ; validates BLER curve at cell edge |
| `cqi_staleness_sweep` | Single factory_robots scenario at 2.0× with `cqi_period_slots` swept from 0 to 80; shows BLER inflation vs. staleness |

### 5.3 Metrics compared

**Per-flow:**
- Delivery ratio (bytes delivered / bytes arrived)
- Mean throughput vs. offered load
- HoL p50, p95, p99 (ms)
- Effective BLER per UE (delivered / bytes_capacity across all grants)

**System:**
- DL/UL PRB utilization
- CCE utilization
- GBR contract satisfaction count (flows at ≥ 95% of GFBR)
- Min per-flow GBR delivery ratio (the distributional floor — key for Finding 1)

**New (feature branch only):**
- Per-slot per-UE SNR timeseries (to verify mobility trajectory)
- Per-UE OLLA offset δ over time (to verify convergence)
- Effective BLER per UE per slot (to verify sigmoid shape vs. flat)

### 5.4 Pass/fail regression criteria

The feature branch must satisfy these on the unchanged scenarios:

1. **GBR contract counts do not regress by more than 1 flow** in `factory_robots` at 2.0× (the clean-win regime). The PHY changes should not destroy a result the scheduler earns legitimately.
2. **`sensor_dense` 30/30 delivery** is preserved. SPS logic is scheduler-side and should be unaffected.
3. **`latency_bound` deadline count does not drop below 6/8.** Some degradation is expected (realistic BLER is higher for some UEs) but a collapse would indicate a bug.
4. **OLLA converges:** after a 500-slot warmup, per-UE BLER stays within ±5% of the 10% target in a static-channel scenario.
5. **Mobility trajectory is correct:** for a UE moving from 20 m to 80 m from the gNB at 2 m/s, mean SNR should decrease monotonically consistent with the configured path-loss exponent.

---

## 6. Build Order

```
1. sim/config.py          — add per-UE σ, mobility fields, cqi_period_slots
2. sim/channel.py         — per-UE σ, OLLA state, CQI cache, mobility update
3. scheduler/link.py      — sigmoid BLER curve (replaces flat 0.10)
4. sim/driver.py          — call olla_update after each delivery; use true SNR for BLER
5. scripts/benchmark_phy_fidelity.py  — baseline benchmark (run on main first)
6. Run benchmark on main  → save results/main_baseline.json
7. Implement features 1–5 on feat/sim-fidelity-phy-layer
8. Run benchmark on branch → save results/feat_phy_fidelity.json
9. scripts/compare_results.py — diff and report
```

Steps 5 and 6 are done on `main` before the branch is cut, so the baseline is clean and reproducible without checking out the feature branch.

---

## 7. Files Changed Summary

| File | Change |
|---|---|
| `sim/config.py` | Add `snr_std_db`, mobility fields, `cqi_period_slots` to `UEConfig` |
| `sim/channel.py` | Per-UE σ, CQI cache + staleness, OLLA state + update, mobility position update + path-loss → mean SNR |
| `scheduler/link.py` | `bits_per_prb` uses sigmoid BLER; MCS table entries annotated with threshold |
| `sim/driver.py` | Call `channel.olla_update(ue_id, had_error)` per grant; use `get_true_snr_db` for BLER computation |
| `scripts/benchmark_phy_fidelity.py` | New — standalone benchmark for before/after comparison |
| `scripts/compare_results.py` | New — JSON diff and tabular report |
| `sim/scenarios/` | New scenario configs: `mobile_robots`, `cell_edge_mix`, `cqi_staleness_sweep` |
