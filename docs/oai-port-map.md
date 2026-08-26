# OAI port map

A spot-checking reference for every behavior ported from the vendored OAI
source (`oai-branches/`) into this simulator so far. One row per mechanism,
ordered **load-bearing first** — WP3's BSR realism is wired into every
scenario's live UL path; WP1's power headroom is dormant (unit-tested only,
not imported by `driver.py` or any scheduler — README §4).

C line ranges are in `oai-branches/two-tier/`, not the external OAI
checkout. Where a mechanism has no OAI counterpart at all (a deliberate
simulator-only addition), the C-source column says so explicitly rather
than citing a nearby-but-unrelated line range.

## WP3 — BSR realism (`sim/bsr.py`, live in every scenario via `sim/driver.py`)

| # | Mechanism | C source | Python | Test(s) | Divergence |
|---|---|---|---|---|---|
| 1 | **Cold-start / re-arm probe — RETIRED by WP4.** Was: when a flow's gated report would be 0 but real data is queued and a BSR is `pending`, report the true backlog directly instead of 0. WP4 replaced this stopgap with the real SR mechanism — see row 9 below (`sim/ul_access.py`). | **None** — no OAI mechanism ported; this row now documents what was removed, not live code. | Was `sim/bsr.py`'s `broadcast()` probe branch (pre-WP4); now `broadcast()` calls `ul_access.sr_report_floor()` instead (`sim/bsr.py:305-341`). | `sim/tests/test_bsr.py::test_broadcast_alone_cannot_report_without_a_grant_or_sr` (confirms the probe's bypass is gone: without SR engaged, `bytes_reported` stays 0, not the true backlog) | **Retired, not simplified away without a replacement** — the deadlock this stood in for is real and is now closed by row 9's real SR mechanism, verified in `sim/tests/test_ul_access.py`. See that row's Divergence cell for what changed in the process (WP4 did not fully restore the probe's own delivery numbers — see README §8). |
| 2 | **`sched_ul_bytes`/`B` collapse-to-crumb gate.** `B = max(0, estimated_ul_buffer − sched_ul_bytes)`; `sched_ul_bytes += tb_size` on every grant, reset to 0 only when a BSR is actually assembled. | `gNB_scheduler_ulsch.c:2151`, `:2460` (`B` computed in `pf_ul`), `:2730` (`sched_ul_bytes += tb_size` in `post_process_ulsch`), `:630`, `:651` (reset to 0, short/long BSR cases) | `sim/bsr.py:236-238` (credit, in `on_ul_grant`), `:268` (reset), `:295` (`broadcast`'s `B` computation) | `sim/tests/test_bsr.py:188-204` (`test_sched_ul_bytes_resets_to_zero_only_when_pending`), `:283-306` (`test_crumb_collapse_not_defeated_by_the_probe`), `:377-403` (`test_crumb_fraction_emerges_from_fast_grants_slow_bsr`) | Faithful port of the *formula*. Measured crumb *frequency* (0.09% of UL grants on `factory_robots_scenario`@1.0×/TwoTier) falls far short of the hardware's ~48-52% — flagged, not chased (README §8, CLAUDE.md known issues). |
| 3 | **Event-triggering: regular / periodic / retx.** A BSR is assembled only when `pending`, set by (a) an arrival on a previously-empty LCG or of higher priority than every other buffered LCG, (b) the periodic (5 ms) timer, or (c) the retx (80 ms) timer. The retx timer restarts on *every* grant, not just BSR-carrying ones. | **Trigger logic and timer values are not in the vendored gNB C at all** — periodicBSR/retxBSR are UE-side MAC timers (`nr_ue_scheduler.c`/UE MAC, not vendored here); the gNB C only ever *receives* whatever BSR arrives. The 5 ms / 80 ms values and the "retx restarts on every grant, so a crumb trickle suppresses recovery" behavior are stated as hardware-measured facts in the charter (README §4 WP3, `p5g-sim-plan.md` §9), not read off a C line. | `sim/bsr.py:172-204` (`on_arrivals`), `:206-212` (`tick_timers`), `:238` (retx restart, inside `on_ul_grant`) | `sim/tests/test_bsr.py:312-324` (`test_regular_trigger_fires_on_previously_empty_lcg`), `:327-334` (`test_no_regular_trigger_without_an_arrival`), `:337-349` (`test_periodic_timer_fires_pending_after_deadline`), `:352-374` (`test_retx_timer_restarts_on_every_grant_suppressing_recovery`) | **No C source to check line-for-line against** — this row is a hardware-measurement port, not a code port. See judgment-call list below for a sub-nuance in the "higher priority" condition that isn't covered by any test. |
| 4 | **Short vs. Long BSR format selection + short-BSR aliasing.** Exactly one active LCG → Short BSR (that LCG's estimate set, every other LCG's slot zeroed). ≥2 active LCGs → Long BSR (all active LCGs' slots set from the same reset-then-repopulate memset). | `gNB_scheduler_ulsch.c:626-645` (Short/Short-Truncated BSR case), `:647-679` (Long/Long-Truncated BSR case) — both `memset` the per-LCG array to 0 before repopulating | `sim/bsr.py:244-266` (inside `on_ul_grant`, the `active_lcgs`/format-selection branch) | `sim/tests/test_bsr.py:126-144` (`test_short_bsr_used_and_other_lcgs_zeroed_when_one_lcg_active`), `:147-162` (`test_long_bsr_used_when_multiple_lcgs_active`), `:165-185` (`test_per_lcg_estimate_frozen_between_grants_not_drained`) | Format selection here is always computed from **true current** per-LCG state, never from a truncation-forced choice (grant too small for a Long BSR CE) — that hazard isn't modeled. See judgment-call list. |
| 5 | **Quantisation: UE-side ceiling-encode + gNB-side +1 overestimation bump.** `quantise_short`/`quantise_long` = encode (smallest table index ≥ true bytes) then decode (+1 index, "to account for headers", index 0 exempt). | Tables: `nr_mac_common.c:43-48` (short, 32 entries), `:57-74` (long, 256 entries). Encoder: `nr_ue_scheduler.c:1506-1542` (`nr_locate_BsrIndexByBufferSize`). Decoder bump: `gNB_scheduler_ulsch.c:239-245` (`overestim_bsr_index`); wrapper functions `:247-258` / `:260-291` (`estimate_ul_buffer_{short,long}_bsr`) | Tables: `sim/bsr.py:53-58`, `:62-79`. Encoder: `:82-90` (`_locate_bsr_index`). Decoder bump: `:93-101` (`_overestim_index`). Composition: `:104-122` (`quantise_short`/`quantise_long`) | `sim/tests/test_bsr.py:37-44`, `:47-51` (table byte-for-byte vs. vendored source, re-checked every test run), `:54-59`, `:62-69`, `:72-74`, `:77-82`, `:85-89`, `:92-99` | None known — tables verified byte-for-byte against the vendored C by an automated test, not just at authoring time. |
| 6 | **Scalar `estimated_ul_buffer` SDU-receipt decrement (finding b).** The scalar decrements by `delivered_bytes` on *every* grant, independent of whether that grant also carries a BSR; the per-LCG array is untouched by this, so the two legitimately desync between BSRs. | `gNB_scheduler_ulsch.c:544-547` (DTCH/DCCH sub-PDU case in `nr_process_mac_pdu`, decrements the scalar only) | `sim/bsr.py:239` (inside `on_ul_grant`, unconditional, before the `pending` check) | `sim/tests/test_bsr.py:207-222` (`test_scalar_decrements_on_every_grant_independent_of_pending`) | Faithful to finding (b) (README §7) with one omission: OAI's `sched_ul_bytes` is *also* decremented at SDU-receipt time (`gNB_scheduler_ulsch.c:1096-1098`), which this port does not mirror — see judgment-call list (the k2/HARQ-pipelining argument for why). |

## WP1 — Tx power headroom (`sim/power.py`, dormant — not imported by `driver.py` or any scheduler)

| # | Mechanism | C source | Python | Test(s) | Divergence |
|---|---|---|---|---|---|
| 7 | **`ph_factor` — 38.213 §7.1.1 PH factor.** `delta_tf` (0 unless `delta_mcs` configured and single-layer) plus `bw_factor` (`10·log10(rb<<mu)`, optional via `include_bw`), rounded half-away-from-zero. | `gNB_scheduler_ulsch.c:208-232` (`compute_ph_factor`). `include_bw` call sites: `:592-599` (true), `:1805-1812`/`:1822-1829`/`:1842-1849` (true, inside `nr_ue_max_mcs_min_rb`), `:2534-2541` (false, PHR telemetry), `:2888-2895` (false, PHR telemetry) | `sim/power.py:22-29` (`_round_half_away_from_zero`), `:32-74` (`ph_factor`) | `sim/tests/test_power.py:18-24`, `:27-34`, `:37-48`, `:51-71`, `:74-85`, `:88-101`, `:104-117` | `roundf()` (half-away-from-zero) explicitly mirrored instead of Python's `round()` (half-to-even) — documented divergence-avoidance, not a divergence. `rb<=0`/`tbs_bits<=0` raise `ValueError` instead of mirroring C's `log10(0.0)`→`-inf`→`int` cast (undefined behavior in C, not deterministic hardware behavior — deliberate raise, already in README §7/CLAUDE.md). |
| 8 | **`shrink_to_power_budget` — two SEQUENTIAL loops, RB first then MCS.** Shrinks RB down to `min_rb` before ever touching MCS; not a joint optimum. | `gNB_scheduler_ulsch.c:1780-1858` (`nr_ue_max_mcs_min_rb`); `AssertFatal`s at `:1789`, `:1790` | `sim/power.py:77-140` | `sim/tests/test_power.py:140-173`, `:176-192`, `:195-207`, `:210-219` | Caller supplies `tbs_bits_fn(rb, mcs)` in place of the C's `nr_compute_tbs()` call (needs a full Qm/code-rate MCS table this sim doesn't have) — every existing test drives it with a synthetic, non-3GPP efficiency table (`_SE_BY_MCS` in `test_power.py`), so only the *loop order* is verified, never a real MCS/TBS number end to end (dormant — no caller exists yet). See judgment-call list. |

## WP4 — Uplink access chain (`sim/ul_access.py`, live in every scenario via `sim/driver.py`)

Ground truth for this WP was **not in `oai-branches/`** when WP4 started —
`gNB_scheduler.c` calls `nr_sr_reporting`/`nr_schedule_pucch` but neither
was defined anywhere in what WP1/WP3 vendored, and the SR-transmission-
attempt counting (`nr_ue_get_SR`) lived in a file (`nr_ue_procedures.c`)
that had never been pulled in. Found and vendored from the live checkout
(`~/projects/Oai_Ran_QoS_Supported_MultiDRB`, `twotier` branch) as part of
this WP; see `oai-branches/README.md` for commit provenance. C line ranges
below are in the newly-vendored `oai-branches/two-tier/gNB_scheduler_uci.c`
and `nr_ue_procedures.c`, plus the already-vendored `nr_ue_scheduler.c`
(WP3) and `gNB_scheduler_ulsch.c` (WP3) where this WP also depends on them.

| # | Mechanism | C source | Python | Test(s) | Divergence |
|---|---|---|---|---|---|
| 9 | **SR trigger.** New data arriving when a UE has no other way to signal it (no standing grant, no SR already pending, not mid-RACH-recovery) arms a pending SR. | `nr_update_sr` (`oai-branches/two-tier/nr_ue_scheduler.c:1207-1277`, already vendored for WP3) | `sim/ul_access.py:118-143` (`UlAccessModel.on_arrivals`) | `sim/tests/test_ul_access.py::test_arrival_on_empty_ue_arms_pending`, `::test_no_trigger_when_buffer_was_already_nonempty` | **Simplified to UE granularity, not per-logical-channel**, and the ground truth's two additional gates (`logicalChannelSR-DelayTimer`, `configuredGrantConfig`+`logicalChannelSR-Mask`) are not ported — no per-LCID SR-DelayTimer or CG-mask config exists in this sim to key them off. Judgment call, recorded below. |
| 10 | **Recurring PUCCH SR occasion + transmission-attempt counter + prohibit-timer gate.** On each `(slot - offset) % period == 0` occasion, if pending and not prohibit-blocked, transmit: increment `counter`, arm the prohibit timer, set the gNB's SR flag. Retransmits (not one-shot) at every subsequent occasion until granted or exhausted. | `trigger_periodic_scheduling_request` (`oai-branches/two-tier/nr_ue_procedures.c:2569-2611`) + `nr_ue_get_SR` (`:2613-2661`, the counter/prohibit-timer logic) | `sim/ul_access.py:145-191` (`UlAccessModel.tick`) | `sim/tests/test_ul_access.py::test_tick_fires_sr_on_the_next_occasion_and_sets_gnb_flag`, `::test_prohibit_timer_suppresses_a_retransmission`, `::test_prohibit_timer_is_a_no_op_at_the_real_deployed_value`, `::test_on_ul_grant_clears_sr_state` | **SR periodicity has no ground truth anywhere** (not the calibration banner, not either OAI repo's config for this deployment) — a first-class swept parameter (`sr_period_slots`), not a silent default (README §8). `sr_ProhibitTimer` at its real deployed value (0 ms, `calibration-logs/twotier_startup_gnb.log`) is a genuine no-op per `nr_timer_start`/`nr_timer_is_active` (OAI `common/utils/nr/nr_common.c:1414-1436` — a plain flag with no minimum-active-duration floor); the suppression test above uses an explicit illustrative 5 ms value instead, since the real value cannot demonstrate the mechanism at all. |
| 11 | **gNB decodes a received SR; clears its flag on any grant.** A positive PUCCH SR sets `sched_ctrl->SR`; the flag is cleared the moment the UE receives any UL grant, regardless of grant size. | Set: `handle_nr_uci_pucch_0_1` (`gNB_scheduler_uci.c:959`, `sched_ctrl->SR \|= true`). Clear: `gNB_scheduler_ulsch.c:2694` (`sched_ctrl->SR = false`, already vendored for WP3). | Set (collapsed with the UE-side transmission, no PHY loss model for PUCCH in this sim): `sim/ul_access.py:187` (inside `tick`). Clear: `sim/ul_access.py:193-202` (`on_ul_grant`) | `sim/tests/test_ul_access.py::test_on_ul_grant_clears_sr_state` | UE transmission and gNB reception are one atomic, lossless step (this sim has no PUCCH PHY model) — real hardware can lose an SR transmission, which is exactly why real UEs retransmit rather than assuming receipt; ported the retransmit *behavior* (row 10) without needing a loss model to motivate it operationally. |
| 12 | **sr-TransMax exhaustion → RACH fallback (timing only).** On exhausting `sr-TransMax` attempts, cancel the pending SR and enter a fixed recovery delay; no preamble-collision modeling (README §6 draws this line). | `nr_ue_get_SR`'s final branch (`nr_ue_procedures.c:2655-2660`, calls `schedule_RA_after_SR_failure`, `nr_ue_scheduler.c:1190-1206`, already vendored) | `sim/ul_access.py:182-190` (exhaustion branch, inside `tick`) | `sim/tests/test_ul_access.py::test_sr_trans_max_exhaustion_falls_back_to_rach` | **The recovery delay's value (t300, 400 ms) is a judgment call**, not a literal port — real RACH's own timing (preamble→RAR→Msg3→contention resolution) is out of scope entirely (README §6); t300 (the RRC-setup response timer, already cited in README §6/§7 from the same calibration banner) was chosen as the nearest real, cited timer of the right order of magnitude ("the mechanism behind multi-hundred-millisecond blackouts", `p5g-sim-plan.md` §9), not because t300 itself governs SR-exhaustion recovery in the spec. |
| 13 | **SR-triggered grant's report floor — a small, honest report, not a lie.** Once served (gNB flag set), `broadcast()` reports a small fixed constant instead of WP3's probe's bypass to the true backlog. | **None** — no OAI counterpart for the exact byte value; grounded instead in this branch's own established "crumb" definition (README/CLAUDE.md known issues: grants ≤150 bytes, ~72-107 byte hardware range) rather than a literal `min_rb`/PRB-capacity C computation this sim doesn't model at the byte level. | `sim/ul_access.py::DEFAULT_SR_REPORT_FLOOR_BYTES = 150`, `sim/ul_access.py:204-213` (`sr_report_floor`) | `sim/tests/test_ul_access.py::test_cold_start_rearms_after_a_flow_drains_and_refills`, `::test_sr_retires_the_cold_start_deadlock_without_it`, `::test_sr_preserves_delivery_on_the_branch_s_main_scenario` | **Tuned once, empirically, from 1 byte to 150 during this WP** — recorded here because it's exactly the kind of number a future session could "simplify" back down without realizing why. At 1 byte, every scheduler's own `tbs_bytes = min(ue_backlog, ...)` sizing cap wasted almost an entire grant's real PRB capacity delivering nothing (`sensor_dense_scenario`+PF mean delivery 50.6%); at 150 bytes (matching the branch's own crumb ceiling) most small messages complete in the triggering grant itself (mean delivery 82.1%). Still short of WP3 probe's 99.1% — see row 1's Divergence cell and README §8. |

---

## Worked numeric trace: BSR path, one UE, two LCGs, 4000 bytes

Every number below is the actual output of `sim.bsr.BsrModel`/`sim.buffer.BufferModel`
run against this scenario (not hand-derived and then transcribed) — check the
table lookups against `oai-branches/two-tier/nr_mac_common.c:57-74`
(`NR_LONG_BSR_TABLE`) by hand; everything downstream of the first BSR follows
mechanically from the formulas in rows 1-6 above.

**Setup.** UE 1, two UL flows, `slot_duration_s = 0.0005` (μ=1 → periodicBSR
= 10 slots, retxBSR = 160 slots):

| Flow | qfi | LCG | priority_level | true backlog at t=0 |
|---|---|---|---|---|
| A | 2 | 0 | 40 (higher priority) | 2500 bytes |
| B | 9 | 1 | 90 (lower priority) | 1500 bytes |

Total: **4000 bytes across 2 LCGs.**

### Slot 0 — arrival, regular trigger, first grant

Both LCGs go from empty to non-empty in the same slot → `on_arrivals` fires
the regular trigger (condition (ii)) for **both**: `pending = True`.

A grant of `tb_size = 1000` arrives. The UE's own LCP (not modeled by
`BsrModel` — TS 38.321 §5.4.3.1 is UE-side) splits it 700/300 by priority,
illustratively:

- Flow A: `2500 − 700 = 1800` bytes remaining
- Flow B: `1500 − 300 = 1200` bytes remaining

`on_ul_grant(tb_size=1000, delivered_bytes=1000)` runs. Two LCGs are active
→ **Long BSR**. Per-LCG encode/decode (`oai-branches/two-tier/
nr_mac_common.c:57-74`, `NR_LONG_BSR_TABLE`):

| LCG | true bytes | encode: smallest idx with `table[idx] ≥ true` | encode value | decode: `+1` idx (headroom bump) | decode value = `quantise_long()` |
|---|---|---|---|---|---|
| 0 (A) | 1800 | idx 83 | `table[83] = 1850` | idx 84 | `table[84] = 1970` |
| 1 (B) | 1200 | idx 77 | `table[77] = 1269` | idx 78 | `table[78] = 1351` |

Resulting state:

```
estimated_ul_buffer_per_lcg = [1970, 1351, 0, 0, 0, 0, 0, 0]
estimated_ul_buffer (scalar) = 1970 + 1351 = 3321
sched_ul_bytes = 0            (reset -- a BSR was just assembled)
pending = False
periodic_deadline_slot = 10   (0 + 10)
```

`broadcast()`: `B = max(0, 3321 − 0) = 3321`.

| Flow | `estimated_ul_buffer_per_lcg` | `gated = min(per_lcg, B)` | `bytes_reported` |
|---|---|---|---|
| A | 1970 | min(1970, 3321) = 1970 | **1970** |
| B | 1351 | min(1351, 3321) = 1351 | **1351** |

### Slot 5 — second grant, no new BSR, the crumb-collapse gate fires

No new arrival, no timer due yet → `pending` is still `False`. A grant of
`tb_size = 2000` arrives and fully drains flow A's remaining true backlog
(1800 of the 2000 granted bytes; 200 bytes go unused — flow B is untouched,
still sitting at 1200 true bytes).

`on_ul_grant(tb_size=2000, delivered_bytes=1800)` runs. **Not pending**, so
only the always-on effects apply:

```
sched_ul_bytes += 2000        -> sched_ul_bytes = 2000
estimated_ul_buffer -= 1800   -> estimated_ul_buffer = 3321 - 1800 = 1521   (finding b)
estimated_ul_buffer_per_lcg UNCHANGED: [1970, 1351, 0, 0, 0, 0, 0, 0]        (finding a, frozen)
```

`broadcast()`: `B = max(0, 1521 − 2000) = 0` — **collapsed**.

| Flow | `estimated_ul_buffer_per_lcg` (frozen) | `gated = min(per_lcg, B)` | `bytes_reported` |
|---|---|---|---|
| A | 1970 | min(1970, 0) = 0 | **0** |
| B | 1351 | min(1351, 0) = 0 | **0** |

Note what just happened: flow B's `bytes_reported` collapsed to 0 even
though **nothing has ever touched flow B's true 1200-byte backlog** — it's
purely a side effect of flow A's grant pushing the UE-wide `sched_ul_bytes`
past the UE-wide `estimated_ul_buffer`. This is the mechanism WP3 exists to
demonstrate (README §4 WP3, `p5g-sim-plan.md` §9): a UE-wide gate, not a
per-flow one, gated by a stale aggregate estimate.

### Slots 6-9 — still collapsed, no recovery path fires

No grant, no arrival, neither timer due (`periodic_deadline_slot=10`,
`retx_deadline_slot=160`). `pending` stays `False`; `bytes_reported` stays
at `0` for both flows every slot.

### Slot 10 — periodic timer fires; before WP4, flow B recovered here

`tick_timers(10)`: `10 >= periodic_deadline_slot (10)` → `pending = True`
(BSR's own pending, independent of SR — see the WP4 trace below for SR's
own state machine).

Before WP4, `broadcast()`'s cold-start/re-arm probe fired here (`gated ≤ 0
and bytes_queued > 0 and pending`), reporting flow B's raw true backlog
(1200) directly. That probe is retired (row 1, above). Now, `broadcast()`
asks `ul_access.sr_report_floor(1)` instead: if this UE's own SR state
machine has already fired and is awaiting a grant, it reports the fixed
150-byte floor; otherwise 0. Which one actually happens depends on when
flow B's SR was triggered relative to this slot — worked in full in the
WP4 trace below, which continues from a fresh cold start (flow B's true
backlog going from empty to 1200 bytes) rather than this exact slot-10
moment, since SR's own timing (occasion period, prohibit timer) needs its
own worked example independent of BSR's periodic-timer coincidence here.

---

## Phase 2 — reservation (`scheduler/reservation.py`, new)

Unlike every WP above, no prior Python existed for this scheduler at all
before Phase 2 (`docs/phase2-plan.md`). Rows are added commit by commit as
each mechanism lands, continuing the running row numbering from WP4's
table above. C line ranges are in `oai-branches/reservation/`, not
`two-tier/` — the two branches' `gNB_scheduler_{dlsch,ulsch}.c` have
different contents (`oai-branches/README.md`).

| # | Mechanism | C source | Python | Test(s) | Divergence |
|---|---|---|---|---|---|
| 14 | Per-UE throughput EWMA (`ul_thr_ue`/`dl_thr_ue`), α=0.01, units bytes, updated only for UEs eligible (backlogged) this slot — not a blanket every-UE-every-slot pass. | `gNB_scheduler_ulsch.c:2083-2087`, `gNB_scheduler_dlsch.c:750-752` | `reservation.py::_UeState`, the decay/increment steps inside `_allocate_direction` | `sim/tests/test_reservation.py::test_lower_accumulated_throughput_is_favored_when_prbs_are_scarce`, `::test_pf_coefficient_formula_matches_hand_computation` | `current_bytes`'s accumulation site (grant-time vs. confirmed-delivery-time) isn't visible in the vendored files; ported as `tbs_bytes*(1-bler)` at grant time — the same structural constraint (no post-grant delivery-confirmation callback in `Scheduler`) every existing scheduler resolves the same way. Decay scope (this-slot-eligible UEs only) deliberately does **not** match `sim/baselines/pf.py`'s `_r_avg`, which decays every UE every slot regardless of eligibility (`pf.py:33-35`) — this scheduler's own C ground truth governs here, not the sibling baseline's convention, even though the two look like the same idea. |
| 15 | PF coefficient: hypothetical grant at a **hardcoded** `rbSize=1`, `10`-symbol duration, ÷ thr (floored at 1.0). | `gNB_scheduler_ulsch.c:2205-2213,2301-2302`, `gNB_scheduler_dlsch.c:814-824` (`nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, layers)`) | `reservation.py::_allocate_direction`'s candidate-building step (`_PF_COEF_HYPOTHETICAL_SYMBOLS = 10`) | `sim/tests/test_reservation.py::test_pf_coefficient_formula_matches_hand_computation` | The `10` is a fixed literal, confirmed to mean 10 *symbols* (matching `nr_compute_tbs`'s 4th parameter at every other call site in this codebase, e.g. `sim/power.py`'s `nrOfSymbols`), not 10 slots — the C's own inline comment ("hypothetical number of slots") is itself imprecise, checked directly rather than trusted. Separately: ground truth's `selected_mcs` feeding this TBS is itself `get_mcs_from_bler`'s (OLLA) output, even at this coefficient — this commit substitutes an instantaneous static-staircase lookup (`bits_per_prb`) pending OLLA activation (commit 8/9, `docs/phase2-plan.md` D2). Deliberate and temporary, flagged from commit 1 rather than discovered later. |
| 16 | UL grant emission: a single opaque `ue_grant=True` Allocation; the scheduler never computes a per-flow split. | N/A — simulator architecture, not an OAI-specific mechanism | `reservation.py::_emit_grant`'s UL branch | `sim/tests/test_reservation.py::test_ul_emits_a_single_opaque_ue_grant_allocation`, `::test_scheduler_package_never_imports_sim` | None — conforms exactly to the pattern every existing scheduler (PF/RoundRobin/Gradient, and `two_tier.py`'s own fallback path) already uses. `sim/ue_lcp.py` (driver-owned, `sim/driver.py:613`) performs the real per-flow split entirely outside any scheduler's code — confirming `docs/phase2-plan.md`'s D1 needed zero new code, just conformance to this existing convention. |
| 17 | DL LCP fill — **placeholder** (priority ascending, then backlog descending). | — (placeholder; the real structure is `gNB_scheduler_dlsch.c:1394-1463`, a genuine two-pass SRB/DRB loop, ported in commit 6) | `reservation.py::_dl_fill` | `sim/tests/test_reservation.py::test_dl_emits_one_allocation_per_filled_flow_with_real_qfi` | **Known, deliberate placeholder — not yet a finished mechanism.** Superseded by commit 6's real two-pass structure. Do not treat this row as portable evidence of fidelity; it exists only so commit 1 can emit a well-formed DL grant at all. |
| 18 | UL comparator: 3-of-5 tiers (SRB[no-op] → GBR[coarse] → PDB/coef). Ground truth is genuinely 5 tiers (SRB → liveness → GBR → `sched_inactive`-last → PDB/coef). | `gNB_scheduler_ulsch.c:2010-2039` (comparator), `:2318-2341` (tier population) | `reservation.py::_ul_rank_key` | `sim/tests/test_reservation.py::test_gbr_tier_beats_the_coefficient_tiebreak_ul`, `::test_pdb_beats_the_coefficient_tiebreak_within_the_same_gbr_bucket_ul`, `::test_ul_and_dl_rank_keys_stay_independently_sourced_not_deduped` | **Two tiers are current no-ops, for two different reasons — `README.md` §8's two new `[OPEN: PHASE2]` entries.** `has_srb` (T1): hardcoded `False`, no SRB/RRC-signaling traffic model exists in this simulator at all (permanent limitation, not a future-commit item). `liveness`/`sched_inactive` (T2/T4): need a `do_sched`-equivalent (SR-or-inactivity trigger for a zero-backlog UE) the `Scheduler` protocol doesn't expose; `sim/ul_access.py`'s SR-report-floor is not a usable proxy (fires only when `bytes_queued > 0`, `sim/bsr.py:381-392`). **Hedged, not verified**: exhaustive case analysis of `liveness = sched_inactive && !ul_has_srb` (`:2339`) suggests T4 may never produce a decisive comparator result even in the real C (whenever `sched_inactive=True`, either T1 or T2 already resolves the comparison first) — recorded as my own reading, not instrumented ground truth, and doesn't change what's ported (T4 is implemented exactly as the C runs it regardless). |
| 19 | DL comparator: 3-of-4 tiers (SRB[no-op] → GBR[coarse] → PDB/coef). Ground truth is genuinely 4 tiers (SRB → liveness(TA) → GBR → PDB/coef) — **DL has no `sched_inactive` field or tier at all**, confirmed absent by reading `UEsched_t` directly, not expressed differently. | `gNB_scheduler_dlsch.c:692-715` (comparator), `:830-843` (tier population) | `reservation.py::_dl_rank_key` | `sim/tests/test_reservation.py::test_gbr_tier_beats_the_coefficient_tiebreak_dl`, `::test_pdb_beats_the_coefficient_tiebreak_within_the_same_gbr_bucket_dl`, `::test_coefficient_remains_the_final_tiebreak_when_gbr_and_pdb_are_equal_dl`, `::test_ul_and_dl_rank_keys_stay_independently_sourced_not_deduped` | Same two no-op categories as UL's row above (`has_srb`: no traffic model; `liveness`: here TA-pending, not SR/inactivity — `gNB_scheduler_dlsch.c:840`, and this simulator has no TA modeling at all). **`_dl_rank_key` is a separately-written, separately-cited method from `_ul_rank_key`, even though their output tuples currently coincide in shape** — a data-availability coincidence (both directions happen to have exactly one real, implementable tier today), not a decision to share a comparator; guarded by its own anti-dedup test. |
| 20 | `has_gbr` — coarse placeholder ("any GBR-class flow has reported backlog"), shared row for both directions since it's the identical simplification on each side. | `gNB_scheduler_ulsch.c:2336` (`ul_has_unfulfilled_gbr`, set inside the per-LCG deficit loop), `gNB_scheduler_dlsch.c:838` (`dl_has_unfulfilled_gbr`, set inside the per-LC deficit loop) | `reservation.py::_allocate_direction`'s `has_gbr` computation | `sim/tests/test_reservation.py::test_gbr_tier_beats_the_coefficient_tiebreak_ul`, `::test_gbr_tier_beats_the_coefficient_tiebreak_dl` | **Known, deliberate placeholder.** Real ground truth is genuine unfulfilled-*deficit* tracking (a GBR flow can have backlog but no unfulfilled deficit, or vice versa depending on recent grant history), not merely "has a GBR flow with any backlog." Commit 3/5 supplies the real per-LCG/per-LC deficit computation without moving this tier's position in either comparator. |
