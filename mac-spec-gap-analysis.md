# MAC Spec Gap Analysis — TS 38.321 vs Simulator

Gaps between the current simulator/scheduler model and 3GPP TS 38.321 (Release 16),
grouped by impact on the validity of scheduler comparisons.

---

## Tier A — Fix before publishing comparisons (distort scheduler-vs-scheduler results)

### 1. HARQ process state machine (§5.3.2, §5.4.2)
- **Current:** BLER applied as a flat delivery discount per slot; no HARQ process tracking.
- **Missing:**
  - Per-UE bitmap of up to 16 HARQ processes; each tracks NDI and retx count.
  - RTT = 8 slots (μ=1): NACKed TB locked until `slot + 8`, then retransmitted.
  - Retransmissions consume PRBs carved from the slot budget **before** dynamic scheduling runs.
  - Soft-combining gain on retx: effective SNR ≈ +3 dB → next MCS step up.
  - MAX_RETX = 3; discard to RLC ARQ after exhaustion.
  - PRB budget for new scheduling = `total_prbs − retx_prbs_due`.
  - Virtual queue `Q_i` drained only on confirmed delivery, not on first transmission.
- **Impact:** Model underestimates congestion (retx PRBs are free in current model); SPS reservation sizing is too small by ≈ `BLER/(1−BLER)`.

### 2. Buffer Status Reporting quantization and Scheduling Request latency (§5.4.4, §5.4.5)
- **Current:** Scheduler reads exact buffer depth directly — omniscient oracle.
- **Missing (UL):**
  - UE sends a Scheduling Request (SR) first when it has data but no grant; SR periodicity is 1–80 slots (configurable per flow).
  - Scheduler receives a coarsely quantized BSR (38-level index table, TS 38.321 Table 6.1.3.1-1) rather than true byte count.
  - BSR types: Short BSR (1 LC group), Long BSR (4 LC groups), Short/Long Truncated BSR (when TBS too small for full report).
  - BSR trigger conditions: data arrival above zero, padding BSR, retx BSR.
- **Impact:** Omniscience flatters TwoTier more than PF on UL — TwoTier's virtual queue tracking depends on accurate arrived/delivered counts; PF needs only a binary "has data" signal. SR latency (up to 40 ms at μ=1) makes sensor_dense and factory_robots UL latency numbers optimistic.

### 3. LCP Prioritized Bit Rate (PBR) token buckets (§5.4.3.1)
- **Current:** MAC multiplexer sorts flows by `(priority_level, −Q̃_i)` and fills greedily — pure strict priority within a UE grant.
- **Missing:**
  - Phase 1: each LC fills from its PBR token bucket (accumulated at `pbr_bps` per slot, capped at `pbr_bps × bsd_s`) in strict priority order.
  - Phase 2: remaining TBS filled in strict priority order with no rate limit (only after all buckets exhausted).
  - `pbr_bps` and `bsd_ms` are per-LC RRC parameters.
- **Impact:** Without PBR buckets a high-priority GBR flow can fully starve lower-priority flows in the same UE (the ue8/9/10 mixed-flow case). TwoTier's drift-plus-penalty deficit is a proxy for the PBR token but is not equivalent, making the OAI comparison point invalid — OAI's LCP uses the real PBR token mechanism.

---

## Tier B — Document as assumptions; add before OAI integration

### 4. Configured Grant Type 1 vs Type 2, CG confirmation (§5.8.2)
- **Current:** SPS always-on, no activation cost, no HARQ process association.
- **Missing:**
  - Type 1: fully RRC-configured, no DCI activation needed.
  - Type 2: RRC-configured but DCI-activated/deactivated; activation DCI consumes a CCE.
  - UE replies with a CG Confirmation MAC CE (§6.1.3.7 / §6.1.3.31) in the first CG transmission slot, consuming UL TBS.
  - Each CG is bound to a specific set of HARQ processes (no overlap with dynamic scheduling processes).
- **Impact:** Type 2 CG activation adds a round-trip latency and one CCE cost before the grant takes effect. Relevant when modelling dynamic robot join/leave events.

### 5. DRX operation (§5.7)
- **Current:** Every UE is schedulable every slot.
- **Missing:**
  - Active time (on-duration timer + inactivity timer) vs sleep time.
  - Short DRX cycle and long DRX cycle, each with configurable period and on-duration.
  - Scheduler cannot issue grants to a sleeping UE; grant is wasted if it lands in sleep.
  - CG transmissions during DRX sleep are silently dropped by the UE.
- **Impact:** For battery-powered factory sensors, DRX cycles misaligned with the TDD pattern shrink effective scheduling opportunities and tighten the usable PDB budget. Interaction with SPS can cause silent grant waste.

### 6. Mini-slot / sub-slot PDSCH/PUSCH (§5.3.1, §5.4.1)
- **Current:** Only full-slot (14-symbol) granularity; a UE either gets a full slot or nothing.
- **Missing:**
  - PDSCH/PUSCH can start on any symbol and last 2–14 symbols (SLIV field in DCI).
  - Multiple mini-slot grants can occupy a single slot for different UEs.
  - Critical for URLLC flows with PDB < 1 ms (2–4 symbol transmission).
- **Impact:** For control-loop flows with 1–5 ms PDB, a full-slot wait represents 10–50% of the budget. Any URLLC extension of the factory_robots scenario requires mini-slot support.

### 7. k2 UL grant-to-transmission delay (§5.4.1)
- **Current:** UL grants are applied instantaneously in the same slot.
- **Missing:**
  - UL grant issued in slot `n` produces PUSCH in slot `n + k2`, where k2 ≥ 1 (minimum 10 symbols UE processing time at μ=1).
  - Scheduler must not issue a UL grant unless a valid UL slot exists within `k2` slots.
  - In DSUUU, this constrains which D-slot symbols can carry UL grants.
- **Impact:** At μ=1, k2 ≥ 1 means every UL grant is at least 0.5 ms stale. A 5 ms PDB control flow loses 10% of its budget to k2 before any queuing. Also tightens DSUUU timing: D-slot grants for U-slots two cycles ahead may be infeasible.

### 8. Timing Advance MAC CE overhead (§5.2)
- **Current:** Perfect UL synchronization assumed.
- **Missing:**
  - gNB issues Timing Advance Commands (TAC) as MAC CEs in DL grants.
  - Each TAC consumes one DL MAC CE (1–2 bytes) in the UE's grant TBS.
  - TA timer expiry forces UE to re-execute RACH before resuming UL.
- **Impact:** For moving robots at 1–5 m/s, TA updates occur every few hundred ms, each eating DL TBS. Currently invisible overhead; non-negligible at high robot density.

---

## Tier C — Out of scope (explicitly excluded)

| MAC section | Feature | Rationale |
|---|---|---|
| §5.1 / §5.1a | 4-step and 2-step Random Access (RACH) | UEs assumed always connected |
| §5.9 | SCell activation/deactivation | Single carrier only |
| §5.10 | PDCP duplication | Reliability feature, not scheduling |
| §5.14 | Measurement gaps | No inter-frequency mobility |
| §5.15 | BWP switching | Single BWP assumed |
| §5.17 | Beam failure detection and recovery | Single-beam model |
| §5.18.2–18.16 | MAC CEs for CSI-RS, TCI, SRS spatial relations | PHY beamforming config, not MAC scheduler |
| §5.21 | LBT (Listen Before Talk) | Licensed spectrum only |
| §5.22–5.23 | Sidelink SL-SCH / SL-BCH | UE-to-UE direct link, not gNB-centric |
| §5.4.6 | Power Headroom Reporting | UEs assumed not power-limited (short-range factory) |

---

## Summary

| Gap | Spec ref | Affects comparison | Effort |
|---|---|---|---|
| HARQ process state machine + retx PRB carve-out | §5.3.2 / §5.4.2 | **Yes** | Medium |
| BSR quantization + SR latency | §5.4.4 / §5.4.5 | **Yes** | Medium |
| LCP PBR token buckets | §5.4.3.1 | **Yes** | Small |
| CG Type 1 vs Type 2, confirmation CE | §5.8.2 | Minor | Small |
| DRX operation | §5.7 | Moderate (sensor scenarios) | Medium |
| Mini-slot PDSCH/PUSCH | §5.3.1 / §5.4.1 | Critical for <5 ms PDB | Large |
| k2 UL grant delay | §5.4.1 | Moderate | Small |
| Timing Advance CE overhead | §5.2 | Small | Small |
