# Scheduler enhancements — `feat/harq-bler-retx`

Numerology μ=1 throughout: 30 kHz SCS, 0.5 ms slots, 14 symbols/slot.

---

## 1. BLER stochastic model

Replace the flat 10% BLER with a sigmoid waterfall keyed on SNR mismatch.

- **Mismatch:** `Δ = snr_inst − snr_ewma`. MCS is chosen from EWMA; actual
  channel is instantaneous — the gap drives BLER.
- **Curve:** `BLER(Δ) = sigmoid(−1.5·Δ + logit(0.10))`. Returns 10% at Δ=0,
  rises toward 1 on fades, falls toward 0 on peaks.
- **Combining gain:** retx 1 → Δ+3 dB; retx 2 → Δ+4.5 dB (diminishing).
- **Files:** `link.py` (new BLER function), `two_tier._emit_grant` (pass Δ).

---

## 2. HARQ retransmission bookkeeping

Track failed TBs and schedule their retransmissions as highest-priority
reservations 8 slots (4 ms) later.

- **State:** `_harq_pending: dict[slot → list[HARQEntry]]`.
  `HARQEntry` holds `ue_id`, `direction`, `prbs`, `flow_fills`, `retx_count`,
  `bits_in_tb`.
- **RTT:** 8 slots. `MAX_HARQ_RETX = 3`; on discard, bytes stay in RLC buffer.
- **Slot order:** retransmissions → SPS → dynamic (retx consumes no CCE).
- **Virtual queue:** drain `Q_i` only on ACK, not on initial TX. On discard,
  drain by discarded bits to clear phantom debt.

---

## 3. PRB budget correction

- **Per slot:** `new_data_prbs = 106 − Σ retx_prbs_due`.
  Passed as `prb_budget` to SPS and dynamic scheduler.
- **Tier-1:** set `capacity_safety_factor = 0.90` to align LP capacity with
  the ~95.4 PRBs sustainably available for new data at 10% BLER.
- **Note:** aggregate throughput changes < 1%; the observable impact is
  latency variance and transient GBR violations during retx bursts.

---

## 4. Greedy PRB allocation — investigate then fix

- **Hypothesis:** virtual queue guarantees long-run fairness; greedy only
  harms Delay-class flows with tight PDB that can be starved across slots.
- **Measure first:** p99/p99.9 HoL delay and PDB violation rate under mixed
  load, with retransmissions modeled (Feature 2 prerequisite).
- **Fix options (in order of preference):**
  - Tune `delay_w` / `delay_exp` so urgency dominates near deadline.
  - Per-UE PRB cap: `floor(budget / n_active_ues)`.
  - Emergency pool: reserve `N_emergency` PRBs for flows with
    `HoL > 0.5 × PDB`.
- **Decision:** pick the simplest option that closes the measured gap.

---

## 5. Indoor channel model — deferred

- **Model:** 3GPP TR 38.901 InF (InF-SL, InF-DL, InF-SH, InF-DH).
- **Adds:** position-based path loss, spatially correlated shadow fading,
  CDL small-scale taps → per-subcarrier SNR → MIESM BLER.
- **Priority:** low. AR(1) + sigmoid BLER (Feature 1) is sufficient for
  comparative evaluation. InF needed only for absolute accuracy claims.
- **Integration:** implements `ChannelView` protocol; no scheduler changes.
