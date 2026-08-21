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
| 1 | **Cold-start / re-arm probe.** When a flow's gated report would be 0 (no per-LCG evidence, or `B` has gated a stale estimate to 0) but real data is queued and a BSR is `pending`, report the true backlog directly instead of 0. | **None** — no OAI mechanism ported. Stands in for the Scheduling Request on PUCCH (a grant-free control-channel signal), which is WP4's job, not WP3's. | `sim/bsr.py:293-305` (`BsrModel.broadcast`, probe branch at 300-302) | `sim/tests/test_bsr.py:239-255` (`test_rides_on_a_grant_no_change_without_one`), `:258-280` (`test_cold_start_probe_rearms_after_a_flow_drains_to_empty`) | **Deliberate, load-bearing.** Verified: removing it drops a 30-UE sensor scenario from ~99% to ~0.2% UL delivery (README §8, CLAUDE.md). Not a hack to simplify away. |
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

### Slot 10 — periodic timer fires, the cold-start/re-arm probe recovers flow B

`tick_timers(10)`: `10 >= periodic_deadline_slot (10)` → `pending = True`.

`broadcast()` re-evaluates both flows against the probe condition
(`gated ≤ 0 and bytes_queued > 0 and pending`):

| Flow | true `bytes_queued` now | `gated` (still 0, B unchanged) | probe condition | `bytes_reported` |
|---|---|---|---|---|
| A | 0 (fully drained at slot 5) | 0 | `bytes_queued > 0` is False → no probe | **0** (correct — nothing left) |
| B | 1200 (never touched) | 0 | **fires** | **1200** (raw true backlog, not yet quantised — no grant has assembled a fresh BSR yet) |

Flow B's stuck backlog becomes visible to the scheduler again at slot 10 —
not because a real BSR arrived, but because `broadcast()`'s probe stood in
for the Scheduling Request a real UE would have sent once the periodic
timer gave it a legitimate reason to. The *next* grant this UE receives
will assemble a real (quantised) BSR and replace this raw `1200` with
whatever `quantise_short(1200)` (a single active LCG now) produces.
