# Scheduler enhancements — `feat/harq-bler-retx`

Numerology μ=1 throughout: 30 kHz SCS, 0.5 ms slots, 14 symbols/slot.

---

## 1. BLER stochastic model

Replace the flat 10% BLER constant with a sigmoid waterfall driven by the
mismatch between instantaneous and EWMA SNR.

- **Mismatch:** `Δ = snr_inst − snr_ewma`. MCS is selected from EWMA SNR;
  the actual channel at transmission time is instantaneous — the gap is the
  primary source of BLER variance in practice.
- **Curve:** `BLER(Δ) = sigmoid(−1.5·Δ + logit(0.10))`. Returns 10% at Δ=0,
  rises toward 1 on fades (Δ < 0), falls toward 0 on peaks (Δ > 0).
  Slope 1.5 dB⁻¹ matches the 2–3 dB waterfall width of real MCS curves.
- **Combining gain:** retx 1 → Δ+3 dB (chase combining); retx 2 → Δ+4.5 dB
  (diminishing returns). In practice first retransmission succeeds ~99% of
  the time at the nominal operating point.
- **Files:** `link.py` (new `bler_from_delta` function replacing constant),
  `two_tier._emit_grant` (compute and pass Δ per UE).

---

## 2. HARQ retransmission bookkeeping

Track failed TBs explicitly and schedule retransmissions as the
highest-priority PRB reservation 8 slots (4 ms) after each failure.

- **State:** `_harq_pending: dict[slot → list[HARQEntry]]`.
  `HARQEntry` holds `ue_id`, `direction`, `prbs`, `flow_fills [(key,bytes)]`,
  `retx_count`, `bits_in_tb`.
- **RTT:** 8 slots (4 ms at μ=1). `MAX_HARQ_RETX = 3`; on final discard
  bytes remain in RLC buffer and re-enter the scheduler as new data.
- **Slot order:** (1) retransmissions — (2) SPS — (3) dynamic new TX.
  Retransmissions consume no CCE (non-adaptive HARQ, no new DCI).
- **Virtual queue:** `Q_i` is drained only on confirmed ACK, not on initial
  TX. On MAX_RETX discard, drain by the discarded bits to prevent phantom
  debt accumulation.
- **Throughput impact:** aggregate throughput changes < 1% because
  retransmissions are eventually delivered. The primary observable effects
  are latency (10% of TBs incur +4 ms; ~1% incur +8 ms) and per-slot PRB
  pool variance when multiple failures cluster in the same past slot.

---

## 3. PRB budget correction

Account for retransmission overhead in the per-slot PRB pool and in the
Tier-1 LP capacity constraint.

- **Per slot:** `new_data_prbs = 106 − Σ retx_prbs_due[current_slot]`.
  Passed as `prb_budget` to both SPS and dynamic scheduler each slot.
- **Tier-1:** set `capacity_safety_factor = 0.90` so the LP's DL/UL capacity
  constants reflect the ~95.4 PRBs sustainably available for new data at
  10% BLER, rather than the full 106.
- **GBR impact:** transient GBR floor violations can occur in slots with a
  retransmission burst (several UEs failing in the same past slot). The
  dual-ascent penalty mechanism will naturally compensate over the next
  Tier-1 period.

---

## 4. Retransmission-aware Tier-2 metric

The current metric `ΣQ_f × SE_ue` overstates the value of scheduling a
high-BLER UE: it sees only the PRB cost of the current slot, not the
retransmission PRBs mortgaged in slot t+8. A UE in a deep fade costs up to
55% more total PRBs per TB than a reliable UE with the same nominal SE.

- **Effective SE:** replace bare `SE` with the expected bits delivered per
  total PRB consumed across the full HARQ chain:

  ```
  effective_SE(Δ) = SE × Σ_k  p_reach(k) · (1 − BLER_k)
                            ─────────────────────────────
                              Σ_k  p_reach(k)

  p_reach(k) = Π_{j<k} BLER_j   (probability of reaching attempt k)
  ```

  At nominal BLER=10%: `effective_SE ≈ SE × 0.908`.
  At deep-fade BLER=50%: `effective_SE ≈ SE × 0.644` — 30% penalty for
  mortgaging future PRBs.

- **New metric:** `ue_metric = ΣQ_f × effective_SE(Δ_ue)`.
  All other Tier-2 logic (ranking, greedy PRB assignment, MAC LCP fill)
  is unchanged.

- **Self-correcting:** once a fade lifts and Δ recovers, effective_SE
  recovers and the UE rises in ranking. Virtual queue debt accumulated
  during the fade ensures the UE is not permanently starved.

- **Implementation:** add `retx_aware_metric: bool = False` flag to
  `TwoTier.__init__`. When enabled, compute `effective_SE` per UE each
  slot using the current Δ and the BLER chain from Feature 1. Disabled
  by default for backward compatibility.

- **Evaluation:** compare `retx_aware_metric=True` vs `False` on the same
  scenario with Feature 2 active. Key metrics: retransmission-slot PRB
  utilisation, p99 HoL delay, GBR satisfaction ratio under channel variation.
  Feature 1 (BLER stochastic model) is a hard prerequisite — with flat
  10% BLER the two modes produce identical results.

---

## 5. Greedy PRB allocation — investigate then fix

- **Hypothesis:** virtual queue guarantees long-run fairness for throughput
  and GBR; greedy is only harmful for Delay-class flows with tight PDB that
  can be starved across multiple consecutive slots by a high-scoring GBR flow.
- **Measure first:** p99/p99.9 HoL delay and PDB violation rate under mixed
  load with retransmissions active (Features 1–2 prerequisite).
- **Fix options (in order of preference):**
  - Tune `delay_w` / `delay_exp` so urgency dominates near deadline.
  - Per-UE PRB cap: `floor(budget / n_active_ues)`.
  - Emergency pool: reserve `N_emergency` PRBs exclusively for flows
    with `HoL > 0.5 × PDB`.
- **Decision:** implement the simplest option that closes the measured gap.

---

## 6. Indoor channel model — deferred

- **Model:** 3GPP TR 38.901 InF variants (InF-SL, InF-DL, InF-SH, InF-DH).
- **Adds:** position-based path loss, spatially correlated shadow fading,
  CDL small-scale taps → per-subcarrier SNR → MIESM-based BLER.
- **Gap vs current:** AR(1) + sigmoid BLER (Feature 1) already captures
  temporal SNR correlation. What 3GPP adds is frequency selectivity (per-
  subcarrier SNR) and spatial structure (shadow fading correlated across UE
  positions). These matter for absolute accuracy but not for comparative
  scheduler evaluation where all schedulers see the same channel.
- **Priority:** low. Implement only when spatially grounded scenarios
  (UE position maps, shadow-fading outage rates) are needed.
- **Integration:** implements `ChannelView` protocol; zero scheduler changes.
