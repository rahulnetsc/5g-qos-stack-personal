"""BSR realism (WP3): per-LCG, quantised, rides on a UL grant.

Ground truth: `oai-branches/two-tier/gNB_scheduler_ulsch.c` (the gNB-side
BSR reception path and `sched_ul_bytes` accounting), `nr_mac_common.c` (the
38.321 quantisation tables), and `nr_ue_scheduler.c` (the UE-side BSR-index
encoder) -- see `oai-branches/README.md` for exact commit provenance of
each. This module owns everything the old fixed-delay/loss
`sim/buffer.py::snapshot_bsr()` used to fake: quantisation, per-LCG
aggregation, short-BSR aliasing, and the `sched_ul_bytes`/
`estimated_ul_buffer` gate that collapses a UE's grants to a `min_rb`
crumb between BSRs. `sim/buffer.py` stays the true-backlog store only --
this module is the only writer of a UL flow's `bytes_reported` /
`estimated_ul_buffer_per_lcg`.

Commit-1 scope: quantisation + per-LCG structure only. A BSR is assembled
on every slot a UE receives a UL grant (as if always pending).
Event-triggering (regular/periodic/retx timers, real pending-gating, the
"~48-52% of grants collapse to a crumb" hardware fraction) lands in a
follow-up commit -- see README §4 WP3 for why the split.

Cold-start / re-arm stopgap: a flow whose last-known per-LCG BSR estimate
is exactly 0 has nothing to report and no way to get a grant to report on
-- every scheduler's eligibility gate reads bytes_reported, and only a
grant can update it. This isn't just a one-time startup case: it recurs
every time a flow's real backlog goes from empty back to non-empty, which
is most UL traffic in this repo (bursty/periodic sources). Real 5G breaks
it with a Scheduling Request on PUCCH -- a grant-free control-channel
signal (WP4, not modeled here) -- plus, for GBR flows specifically, a
separate BSR-independent floor (`ul_has_unfulfilled_gbr` in the ground
truth) neither modeled here. Until then, `broadcast()` reports a flow's
true backlog directly whenever its per-LCG estimate is 0 and real data is
waiting (see the probe branch below); this does NOT touch the crumb-
collapse case (a nonzero per-LCG estimate capped to 0 by `B` -- that stays
gated, which is the mechanism WP3 exists to demonstrate), only the "gNB
has zero evidence at all" case.
"""

import bisect
from dataclasses import dataclass, field

from scheduler.flow import FlowConfig

LCG_COUNT = 8

# oai-branches/two-tier/nr_mac_common.c:43-48 (twotier branch, commit
# 98618a7dc8c2c9bdf7fc3d2c789f57658cbd46d1) -- 38.321 Table 6.1.3.1-1,
# transcribed verbatim.
NR_SHORT_BSR_TABLE: tuple[int, ...] = (
    0, 10, 14, 20, 28, 38, 53, 74,
    102, 142, 198, 276, 384, 535, 745, 1038,
    1446, 2014, 2806, 3909, 5446, 7587, 10570, 14726,
    20516, 28581, 39818, 55474, 77284, 107669, 150000, 300000,
)

# oai-branches/two-tier/nr_mac_common.c:57-74 (same commit) -- 38.321
# Table 6.1.3.1-2, transcribed verbatim.
NR_LONG_BSR_TABLE: tuple[int, ...] = (
    0, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22, 23, 25, 26,
    28, 30, 32, 34, 36, 38, 40, 43, 46, 49, 52, 55, 59, 62, 66, 71,
    75, 80, 85, 91, 97, 103, 110, 117, 124, 132, 141, 150, 160, 170, 181, 193,
    205, 218, 233, 248, 264, 281, 299, 318, 339, 361, 384, 409, 436, 464, 494, 526,
    560, 597, 635, 677, 720, 767, 817, 870, 926, 987, 1051, 1119, 1191, 1269, 1351, 1439,
    1532, 1631, 1737, 1850, 1970, 2098, 2234, 2379, 2533, 2698, 2873, 3059, 3258, 3469, 3694, 3934,
    4189, 4461, 4751, 5059, 5387, 5737, 6109, 6506, 6928, 7378, 7857, 8367, 8910, 9488, 10104, 10760,
    11458, 12202, 12994, 13838, 14736, 15692, 16711, 17795, 18951, 20181, 21491, 22885, 24371, 25953, 27638, 29431,
    31342, 33376, 35543, 37850, 40307, 42923, 45709, 48676, 51836, 55200, 58784, 62599, 66663, 70990, 75598, 80505,
    85730, 91295, 97221, 103532, 110252, 117409, 125030, 133146, 141789, 150992, 160793, 171231, 182345, 194182, 206786, 220209,
    234503, 249725, 265935, 283197, 301579, 321155, 342002, 364202, 387842, 413018, 439827, 468377, 498780, 531156, 565634, 602350,
    641449, 683087, 727427, 774645, 824928, 878475, 935498, 996222, 1060888, 1129752, 1203085, 1281179, 1364342, 1452903, 1547213, 1647644,
    1754595, 1868488, 1989774, 2118933, 2256475, 2402946, 2558924, 2725027, 2901912, 3090279, 3290873, 3504487, 3731968, 3974215, 4232186, 4506902,
    4799451, 5110989, 5442750, 5796046, 6172275, 6572925, 6999582, 7453933, 7937777, 8453028, 9001725, 9586039, 10208280, 10870913, 11576557, 12328006,
    13128233, 13980403, 14887889, 15854280, 16883401, 17979324, 19146385, 20389201, 21712690, 23122088, 24622972, 26221280, 27923336, 29735875, 31666069, 33721553,
    35910462, 38241455, 40723756, 43367187, 46182206, 49179951, 52372284, 55771835, 59392055, 63247269, 67352729, 71724679, 76380419, 81338368, 162676736, 4294967295,
)


def _locate_bsr_index(table: tuple[int, ...], true_bytes: int) -> int:
    """UE-side BSR index encoder -- mirrors `nr_locate_BsrIndexByBufferSize`
    (`oai-branches/two-tier/nr_ue_scheduler.c:1506-1540`). Smallest index i
    such that ``table[i] >= true_bytes`` (0 bytes -> index 0 falls out of
    this naturally); clamped to the last index if `true_bytes` exceeds
    every table entry.
    """
    idx = bisect.bisect_left(table, true_bytes)
    return min(idx, len(table) - 1)


def _overestim_index(idx: int, table_size: int) -> int:
    """gNB-side decode headroom bump -- mirrors `overestim_bsr_index`
    (`oai-branches/two-tier/gNB_scheduler_ulsch.c:239-245`). One more index
    of overestimation "to account for headers", except index 0 ("no data")
    is left alone; clamped to the table's last index.
    """
    if idx <= 0:
        return idx
    return min(idx + 1, table_size - 1)


def quantise_short(true_bytes: int) -> int:
    """gNB's estimated byte value for a Short/Short-Truncated BSR --
    matches `estimate_ul_buffer_short_bsr`
    (`gNB_scheduler_ulsch.c:247-258`): encode then decode, a double
    overestimate relative to `true_bytes` (except at 0).
    """
    idx = _locate_bsr_index(NR_SHORT_BSR_TABLE, true_bytes)
    idx = _overestim_index(idx, len(NR_SHORT_BSR_TABLE))
    return NR_SHORT_BSR_TABLE[idx]


def quantise_long(true_bytes: int) -> int:
    """gNB's estimated byte value for one active LCG's entry in a Long/
    Long-Truncated BSR -- matches `estimate_ul_buffer_long_bsr`
    (`gNB_scheduler_ulsch.c:260-291`), applied per active LCG.
    """
    idx = _locate_bsr_index(NR_LONG_BSR_TABLE, true_bytes)
    idx = _overestim_index(idx, len(NR_LONG_BSR_TABLE))
    return NR_LONG_BSR_TABLE[idx]


@dataclass
class _UeBsrState:
    estimated_ul_buffer: int = 0
    estimated_ul_buffer_per_lcg: list[int] = field(default_factory=lambda: [0] * LCG_COUNT)
    sched_ul_bytes: int = 0


class BsrModel:
    """Per-UE BSR state: quantised per-LCG estimates plus the
    `sched_ul_bytes`/`estimated_ul_buffer` gate that collapses a UE's
    grants toward a `min_rb` crumb between BSRs. See module docstring for
    commit-1 scope.
    """

    def __init__(self, flows: list[FlowConfig]) -> None:
        self._ue_flows: dict[int, list[FlowConfig]] = {}
        for f in flows:
            if f.direction != "UL":
                continue
            self._ue_flows.setdefault(f.ue_id, []).append(f)
        self._state: dict[int, _UeBsrState] = {
            ue_id: _UeBsrState() for ue_id in self._ue_flows
        }

    def on_ul_grant(self, ue_id: int, tb_size: int, delivered_bytes: int, buffers) -> None:
        """Call once per UE per slot, for the UE's `ue_grant=True`
        allocation, after `buffers.drain()` has applied it. Assembles and
        quantises a BSR from the true post-drain per-LCG backlog and
        resets `sched_ul_bytes`, matching `gNB_scheduler_ulsch.c:626-679`
        (both BSR formats reset `sched_ul_bytes = 0` unconditionally).

        Commit-1 scope reports on every grant (no event-triggering yet),
        so a fresh BSR always overwrites `estimated_ul_buffer` below --
        `delivered_bytes` (the SDU-receipt scalar decrement,
        `gNB_scheduler_ulsch.c:544-547`, finding (b) in README §7) has no
        observable effect yet. It becomes load-bearing once a follow-up
        commit makes the reset conditional on a pending BSR rather than
        automatic on every grant.
        """
        st = self._state[ue_id]
        st.sched_ul_bytes += tb_size

        per_lcg_true: dict[int, int] = {}
        for f in self._ue_flows[ue_id]:
            per_lcg_true[f.lcg] = per_lcg_true.get(f.lcg, 0) + buffers.state(f.ue_id, f.qfi).bytes_queued
        active_lcgs = [lcg for lcg, backlog in per_lcg_true.items() if backlog > 0]

        st.estimated_ul_buffer_per_lcg = [0] * LCG_COUNT
        if not active_lcgs:
            st.estimated_ul_buffer = 0
            st.sched_ul_bytes = 0
            return

        if len(active_lcgs) == 1:
            # Short BSR: reports one LCG's size; the aliasing is the memset
            # above -- every other LCG's slot is already zeroed and stays
            # that way until a future BSR repopulates it.
            lcg = active_lcgs[0]
            estim = quantise_short(per_lcg_true[lcg])
            st.estimated_ul_buffer_per_lcg[lcg] = estim
            st.estimated_ul_buffer = estim
        else:
            total = 0
            for lcg in active_lcgs:
                estim = quantise_long(per_lcg_true[lcg])
                st.estimated_ul_buffer_per_lcg[lcg] = estim
                total += estim
            st.estimated_ul_buffer = total
        st.sched_ul_bytes = 0

    def broadcast(self, buffers) -> None:
        """Every slot, every UE: recompute
        ``B = max(0, estimated_ul_buffer - sched_ul_bytes)`` and write
        `bytes_reported` / `estimated_ul_buffer_per_lcg` for every UL flow.
        Capping the frozen per-LCG estimate by the UE-wide `B` gate is what
        lets `scheduler/two_tier.py`'s existing per-flow reads of
        `bytes_reported` collapse toward zero with no scheduler-side
        change -- see README §4/§7.

        Cold-start / re-arm probe (see module docstring): if a flow's
        per-LCG estimate is 0 but it actually has data queued, the gNB has
        no evidence of it at all (as opposed to evidence that's merely
        collapsed under `B`) -- report the true backlog directly so the
        flow can get a grant at all, standing in for the Scheduling
        Request WP4 will model properly.
        """
        for ue_id, flows in self._ue_flows.items():
            st = self._state[ue_id]
            b = max(0, st.estimated_ul_buffer - st.sched_ul_bytes)
            for f in flows:
                state = buffers.state(f.ue_id, f.qfi)
                per_lcg = st.estimated_ul_buffer_per_lcg[f.lcg]
                if per_lcg <= 0 and state.bytes_queued > 0:
                    state.estimated_ul_buffer_per_lcg = state.bytes_queued
                    state.bytes_reported = state.bytes_queued
                else:
                    state.estimated_ul_buffer_per_lcg = per_lcg
                    state.bytes_reported = min(per_lcg, b)
