# HARQ retransmissions now respect the TDD pattern — one fidelity change, corpus re-baselined

**2026-09-14.** `sim/driver.py::align_due_slot` + four call sites. No
scheduler file touched. Regression corpus deliberately re-captured in the
same commit; this file records what moved and why.

## The gap

New-data grants always respected `TDDConfig.pattern` (`DSUUU`):
`_allocate_direction` runs only when the slot has that direction's symbols,
and the metrics layer credits capacity per direction the same way. Measured:
0 new DL grants on U-slots, 0 new UL grants on D-slots, every arm.

Retransmissions did not. A retry was due at a **fixed offset** — `k1 + k2`
(4 + 2) for DL, `k2` (2) for UL (`docs/wp5-plan.md` Decision 3, which chose
the offsets as "representative points" without reference to slot kind) —
and `HarqProcessPool.due_this_slot()` matched by equality, so the driver
resolved the TB on whatever slot that was: it carved `proc.prbs` and a CCE
out of that slot, counted the UE against that direction's cap, and drew the
decode outcome. The mismatch-aware BLER path does not read the slot's symbol
count, so a DL TB "transmitted" on a U-slot with a valid outcome.

Under `DSUUU` with these offsets: a UL TB granted on slot 3 (U) is due on
slot 5 (D); a DL TB granted on slot 1 (S) is due on slot 7 (U).

**Measured on GT-2.2, N = 8, cap 4, 8 000 slots, seed 1097657231, before
the fix** (`scratchpad` probe, grant-sink over `GrantTrace.retx_count > 0`):

| arm | retx total | DL retx on a U-slot | UL retx on a D-slot |
|---|---|---|---|
| TwoTier | 2 682 | 18 (205 PRB) | **625** (5 658 PRB) |
| PF | 688 | 18 (177 PRB) | **167** (9 088 PRB) |
| ProtoRRageD2 | 1 521 | 28 (346 PRB) | **357** (9 251 PRB) |

About a quarter of UL retries resolved on a downlink slot, and their PRBs
were subtracted from that slot as one combined DL + UL count
(`Occupancy.prbs`) — DL capacity spent on a transmission that could not
have happened, while the next real U-slot got its full band back.

## The change

`align_due_slot(grid, due, direction)`: the first slot `>= due` whose
`slot_grid()` carries that direction's symbols (D or S for DL; U or S for
UL under the default `s_slot_split = (3, 2, 9)`). Bounded by one pattern
period; a pattern with no slot for a direction raises. Applied at all four
`due_slot` assignments (first retry after a failed new grant, DL and UL;
subsequent retries, DL and UL).

**After the fix, same cell:** retries by direction@slot-kind —
TwoTier `DL@D 14, DL@S 26, UL@S 1 291, UL@U 1 276`; PF
`DL@D 17, DL@S 24, UL@S 325, UL@U 313`; RRageD2 `DL@D 14, DL@S 28,
UL@S 743, UL@U 727`. Zero on wrong-kind slots. Note the S-slot now carries
about half of all UL retries — the D-due ones move one slot later onto it.

Tests (`sim/tests/test_harq.py`): the helper's mapping on `DSUUU`, and a
run-level assertion that no retry trace lands on a wrong-kind slot,
guarded by `retx > 0` so it cannot pass vacuously (it failed 625 times on
this cell before the fix).

## What moved in the regression corpus

`regression_corpus.py --check` before re-capture: **6 377 values across
8 of the 20 records** — every record of `study2/pdcch_limited` and
`study3/latency_bound` (all four arms each), and **none** of the other
twelve, which are bit-identical. That is the expected signature: only a run
with failed transport blocks has a retry to move. The largest single move
is `study3/latency_bound/TwoTier` `ue9_qfi9` (the 5QI-9 best-effort flow)
`throughput_bps` 5 646 688 → 4 943 852 and `dl_prb_utilization` 0.931 →
0.906 — DL PRBs no longer spent on UL retries that landed on D-slots.

Re-captured with `--capture` in this commit. This is the deliberate
re-baseline CLAUDE.md requires for a change that is *meant* to move the
numbers; it is the only fidelity change in the commit.

## Two tests the change moved, and what each says

- `test_two_tier_proto.py::test_the_reserve_is_bounded_by_what_the_PER_SLOT_CAP_can_serve`
  pinned `gpb_cap_bound == max_sched_ues − 1` on the *last* UL slot. That
  counter is derived from the REDUCED slot (M-6 counts retx UEs against the
  cap), and with UL retries now on UL slots the last slot usually carries
  one, so it read 2 at cap 4. Behaviour correct, test wrong: a
  `gpb_cap_bound_max` counter now carries the unreduced ceiling and the test
  asserts that.
- `test_wp6_blockage_harq_interaction.py::test_pure_retry_freeze_without_cqi_delay_is_too_unreliable_to_demonstrate`
  asserted "at `cqi_delay_slots=0` some seed loses 0 bytes". Re-measured:
  long-blockage loss at `cqi_delay=0` is 200–4 793 B (was 0–6 193) against
  a no-blockage 0–600; at `cqi_delay=8` 4 600–15 636 against ≤ 800 (was
  ≥ 5 200). No seed reads 0 any more — a retry that waits for a right-kind
  slot straddles a blockage transition more often — but the **finding is
  the overlap**, and the ranges still overlap at 0 and not at 8. The test
  now asserts the overlap; the module docstring carries both measurements.

Full suite after both: 1 546 passed, 10 skipped, 3 failed — the three
pre-existing at HEAD (claims staleness ×2, the four-variations pin).

## Consequences for results measured before it

Every campaign artefact in this repo was produced under the old retry
timing — the faithful G1–G12 rows and this session's Proto results
(`docs/proto-age-c34-2026-09-14.md`) alike. All arms were exposed to the
same rule, so *comparisons* between arms stand as comparisons; absolute
numbers involving HARQ-heavy cells (low SNR, GT-3.3's edge axis, anything at
high load) will move on re-run. The `code_state` stamps will read STALE for
every artefact whose scope reaches `sim/driver.py`, i.e. all of them. Which
campaigns to re-run, and in what order, is a separate decision.
