import sys
from pathlib import Path
ROOT = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/"scripts"))
from sim.driver import run
from sim.scenarios.g9 import gt62_cold_attach
from sim.baselines.pf import ProportionalFair
from scheduler import load_two_tier
_TT = str(ROOT/"scheduler"/"scheduler_config.yaml")

class Spy:
    def __init__(self, inner, name):
        self.inner = inner; self.name = name
        self.reported_slots = 0; self.queued_slots = 0
        self.ul_grants_joiner = 0; self.first_reported = None; self.first_grant = None
        self.slots_seen_ul = 0; self.win = []
    def allocate(self, slot, buffers, channel):
        st = buffers.state(1, 70)
        if getattr(st, "bytes_reported", 0) > 0:
            self.reported_slots += 1
            if self.first_reported is None: self.first_reported = slot.slot_index
        if getattr(st, "bytes_queued", 0) > 0:
            self.queued_slots += 1
        allocs = self.inner.allocate(slot, buffers, channel)
        for a in allocs:
            if a.ue_id == 1 and a.direction == "UL":
                self.ul_grants_joiner += 1
                if self.first_grant is None: self.first_grant = slot.slot_index
                self.win.append(slot.slot_index)
        return allocs
    def __getattr__(self, k): return getattr(self.inner, k)

for name, fac in (("TwoTier", lambda: load_two_tier(_TT, min_rb=5)),
                  ("PF", lambda: ProportionalFair(ewma_window_slots=200))):
    sc = gt62_cold_attach(seed=1826701614, n_neighbours=7)
    spy = Spy(fac(), name)
    run(sc, spy, cqi_delay_slots=8, record_timeseries=True)
    print(f"{name}: slots with ue1/qfi70 bytes_reported>0 = {spy.reported_slots} "
          f"(first at {spy.first_reported}); bytes_queued>0 = {spy.queued_slots}; "
          f"UL grants to ue1 = {spy.ul_grants_joiner} (first at {spy.first_grant})")
    w = spy.win
    print(f"   ue1 UL grant slots: first={w[0] if w else None} last={w[-1] if w else None} "
          f"n_before_2000={sum(1 for x in w if x < 2000)} n_2000_2824={sum(1 for x in w if 2000 <= x < 2824)} "
          f"n_after_2824={sum(1 for x in w if x >= 2824)}")
