"""Pre-scheduler occupancy -- the ONE object every mechanism that consumes
grid resources ahead of `scheduler.allocate()` adds to.

On the deployed gNB, PRACH, RA (Msg2/Msg3/Msg4) and HARQ retransmissions are
all scheduled BEFORE the data schedulers run and write the same
`vrb_map_UL`/`vrb_map` the data schedulers then allocate from
(`gNB_scheduler.c:225-252`: `schedule_nr_prach` -> `nr_schedule_RA` ->
`nr_schedule_ulsch` -> `nr_schedule_ue_spec`). This module is that map's
simulator equivalent, kept deliberately dumb: contributors ADD, the driver
builds ONE `ReducedSlotView` from the sum, and no contributor ever touches
the view. It exists so that RA (Build 1) and Configured Grants (Build 2) do
not each grow their own subtraction path and diverge -- the RunLedger
lesson, applied before the copy is made rather than after.

Must not import the driver, any scheduler, or `sim/harq.py` (which imports
this).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Occupancy:
    """Resources already committed in one slot, before new-data scheduling.

    `prbs` is ONE combined DL+UL count, matching the pre-existing
    `ReducedSlotView` semantics (the grid carries a single `prb_count` per
    slot and only splits DL/UL by symbol availability); `cce` is PDCCH
    budget; `ues` is, per direction, the number of DISTINCT UEs that hold a
    DCI this slot and therefore consume one of the M-6 cap slots. HARQ retx
    UEs count; RA UEs do NOT -- the deployed cap loops over
    `connected_ue_list` and RA UEs live in `access_ue_list`
    (`gNB_scheduler_RA.c:2150+`), so their DCIs cost CCE but not a cap slot.
    """
    prbs_dl: int = 0
    prbs_ul: int = 0
    cce: int = 0
    #: distinct UEs holding a DCI this slot, per direction. Contributors are
    #: disjoint by construction (a UE in RA has no data retx), so counts add.
    ue_counts: dict[str, int] = field(default_factory=dict)

    @property
    def prbs(self) -> int:
        return self.prbs_dl + self.prbs_ul

    def add(self, other: "Occupancy") -> None:
        self.prbs_dl += other.prbs_dl
        self.prbs_ul += other.prbs_ul
        self.cce += other.cce
        for d, n in other.ue_counts.items():
            self.ue_counts[d] = self.ue_counts.get(d, 0) + n

    def ue_count_max(self) -> int:
        return max(self.ue_counts.values(), default=0)
