# Scheduler enhancement backlog

**Branch:** `feat/harq-bler-retx`
**Numerology:** μ = 1 throughout — 30 kHz SCS, 0.5 ms slot duration, 14 OFDM symbols/slot, 2 slots/subframe.

---

## 1. BLER stochastic model

Replace the flat 10% BLER constant with a sigmoid waterfall driven by the
mismatch between the instantaneous SNR and the EWMA SNR used for MCS
selection.

- **SNR mismatch definition:** `Δ = snr_inst(t) − snr_ewma(t)`. The EWMA
  SNR (100-slot window) determines the MCS; the instantaneous SNR is what
  the channel actually delivers in this slot.
- **Waterfall curve:** `BLER(Δ) = sigmoid(−slope · Δ + logit(target_bler))`.
  At Δ = 0 the curve returns `target_bler` (default 0.10). Negative Δ (fade)
  drives BLER toward 1; positive Δ drives it toward 0.
- **Slope parameter:** ~1.5 dB⁻¹, matching real MCS waterfall width of 2–3 dB.
- **Retransmission combining gain:** the first retransmission applies the same
  curve at `Δ + 3 dB` (chase combining energy addition). Second retransmission
  applies `Δ + 4.5 dB` (diminishing returns beyond first combine).
- **Scope:** BLER remains a function of SNR only — no frequency selectivity.
  Full per-subcarrier SINR mapping (MIESM) is deferred with the 3GPP InF
  channel model.
- **Affects:** `link.py` (`bits_per_prb` returns BLER as a function of Δ, not
  a constant), `two_tier.py` (`_emit_grant` passes the mismatch delta to the
  new BLER function).

---

## 2. HARQ retransmission bookkeeping

Track failed transport blocks explicitly and schedule their retransmissions
as a first-priority reservation 8 slots after the original transmission.

- **RTT:** 8 slots = 4 ms at numerology 1 (minimum NR HARQ round-trip).
- **`HARQEntry` dataclass fields:** `ue_id`, `direction`, `prbs` (same count
  as original TX), `flow_fills: list[tuple[key, bytes]]` (which flows and how
  many bytes were in the TB), `retx_count` (0 = first retransmission),
  `bits_in_tb` (for virtual queue drain on confirmed delivery).
- **`_harq_pending: dict[int, list[HARQEntry]]`** keyed by the slot index
  at which the retransmission falls due. Populated when a TB fails; entries
  consumed and deleted each slot.
- **`MAX_HARQ_RETX = 3`:** after three failed retransmissions the TB is
  discarded. The bytes remain in the RLC buffer and are re-submitted as new
  data in subsequent slots.
- **Scheduling order within a slot:**
  1. Retransmissions (`_harq_pending[slot_index]`) — consume PRBs first,
     no CCE cost for non-adaptive HARQ.
  2. SPS configured grants — as today.
  3. Dynamic new transmissions — on the reduced remaining budget.
- **Virtual queue correction:** `Q_i` is *not* drained on initial
  transmission. It is drained only when a delivery is confirmed (ACK on
  original TX or on a retransmission). On TB discard (MAX_RETX exceeded),
  `Q_i` is drained by the discarded bits to avoid phantom debt accumulation.
- **CCE cost:** non-adaptive retransmissions carry no new DCI and therefore
  consume zero CCEs. Adaptive retransmissions (if implemented later) would
  consume the UE's normal aggregation-level CCE cost.

---

## 3. PRB budget correction

Account for the retransmission overhead in the per-slot PRB pool and in the
Tier-1 LP capacity constraint.

- **Per-slot available PRBs for new data:**
  `new_data_prbs = 106 − sum(e.prbs for e in _harq_pending[slot_index])`.
  This value is passed as `prb_budget` to both `_allocate_sps` and
  `_allocate_dynamic`.
- **Steady-state expectation:** at BLER = 10%, the retransmission load
  averages 10.6 PRBs/slot, leaving ~95.4 PRBs for new data.
- **Slot-level variance:** retransmission load is bursty — if multiple UEs
  failed in the same past slot, the current slot absorbs a spike. GBR floors
  can be transiently violated during such spikes.
- **Tier-1 LP correction:** the capacity constants `C_DL` and `C_UL` should
  be scaled by `(1 − bler_target)` to reflect the sustainable new-data budget.
  The existing `capacity_safety_factor` parameter is the natural hook for this;
  set it to `0.90` (or derive dynamically from observed retransmission load
  averaged over the last Tier-1 period).
- **Throughput impact:** total delivered throughput changes by less than 1%
  because retransmissions are eventually delivered. The primary observable
  difference is in latency distributions and PRB pool variance, not aggregate
  throughput.

---

## 4. Greedy PRB allocation — investigation and possible remediation

Characterise whether the current greedy per-UE PRB allocation causes
measurable harm in the target scenarios, and implement a fix if it does.

- **Hypothesis to test:** the virtual queue mechanism guarantees long-run
  throughput fairness and GBR satisfaction regardless of per-slot greediness.
  Greedy is only harmful for Delay-class flows with tight PDB that can be
  starved for multiple consecutive slots by a high-scoring GBR or PF flow.
- **Primary metric:** p99 and p99.9 HoL delay and PDB violation rate for
  Delay-class flows under mixed-load scenarios.
- **Evaluation approach:** run the same scenario with and without a per-UE
  PRB cap; compare PDB violation rates and GBR satisfaction ratios.
- **Option A — urgency parameter tuning:** increase `delay_w` and/or
  `delay_exp` so urgency dominates the scheduling metric when a packet
  exceeds a fraction of its PDB. Soft guarantee; no structural change.
- **Option B — per-UE PRB cap:** limit any single UE to
  `floor(prb_budget / n_active_ues)` PRBs per slot. Prevents monopolisation;
  reduces peak spectral efficiency for bursty near-UEs.
- **Option C — emergency PRB pool:** reserve `N_emergency` PRBs exclusively
  for Delay-class flows whose HoL age exceeds a configurable fraction of PDB
  (e.g. 50%). All other flows compete only for the remainder. Most targeted
  fix; adds a configuration knob.
- **Decision:** deferred until simulation results quantify the PDB violation
  rate under the current greedy policy with retransmissions modeled. Implement
  the simplest option that closes the gap.

---

## 5. Indoor channel model — deferred

Implement the 3GPP TR 38.901 InF (Indoor Factory) channel model as an
optional `ChannelModel` backend.

- **Variants to support:** InF-SL (sparse clutter, low BS), InF-DL (dense
  clutter, low BS), InF-SH, InF-DH.
- **Outputs:** path loss `PL(d)` from floating-intercept formula, log-normal
  shadow fading with spatial decorrelation distance ~10 m, CDL small-scale
  taps for per-subcarrier SNR.
- **Benefit over AR(1):** spatially grounded mean SNR from UE (x, y, z)
  position; shadow fading with correct spatial correlation; frequency-selective
  fading enabling MIESM-based BLER estimation.
- **Prerequisite for MIESM BLER:** per-subcarrier SNR from CDL taps is needed
  to compute effective BLER via mutual-information mapping. Without this, the
  sigmoid BLER model (Feature 1) remains the operative approximation.
- **Priority:** low. The AR(1) + sigmoid BLER model is sufficient for
  comparative scheduler evaluation. The InF model is needed only for
  spatially grounded absolute accuracy claims (e.g. throughput vs UE position
  maps, shadow-fading outage probabilities).
- **Integration point:** implements the `ChannelView` protocol; no scheduler
  code changes required.
