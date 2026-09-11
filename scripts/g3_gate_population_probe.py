"""Which of the four candidate reserve gates can FIRE in the 8-14 band at all?

Written BEFORE the gates, because a gate that cannot fire where the boundary
sits cannot move the boundary -- which is exactly what E1 taught, one run too
late (`docs/proto-e1-result-2026-09-10.md` §2). Three populations, one per
gate, measured on the campaign's own configuration (gt22, cap 4, telemetry GBR,
40 000 slots, seed 35492826):

  G-count / G-depth  need = the number of qualifying followers per UL slot.
      Both gates key off it: E1 fires at `prb_count <= min_rb * need`, and
      `floor(prb_count / min_rb) - 1` is the same threshold. If `need` never
      reaches 11 below N = 12, NEITHER can act where the boundary is.

  G-backlog  of the qualifying followers, how many have NOTHING reported.
      Those are the ones holding band for nothing. If the count is zero the
      gate is a structural no-op.

  G-deadline  the candidate's OWN `urgency01`, which is `1 - remaining_pdb /
      pdb_ms` priority-weighted over its backlogged GBR LCGs
      (`ia_p5g_scheduler.c:2576-2647`). This is the right observable and
      `_Candidate.pdb_ms` is NOT: line 1356 of the port says pdb_ms "stays
      unread" on UL, so it holds its 9999 default there -- a first version of
      this probe read it and classified every candidate "unknown". Measured as
      a distribution so G-deadline's threshold is derived from where the data
      sits, not picked.

Read-only: every override calls `super()` first and returns its result
unchanged, so the tallied run is the faithful arm's own trajectory.
"""
import sys
from pathlib import Path
from collections import Counter

# Resolved from THIS file, never an absolute path: an absolute path makes
# the script unrunnable on any other checkout, and this repo is meant to
# be clonable and continued elsewhere.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from scheduler.two_tier import TwoTier
from sim.scenarios.g3 import build_gt22_scenario
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.srb import with_srb

HORIZON = 40_000
SEED = 35492826
MIN_RB = 5


class Probe(TwoTier):
    """The port, plus read-only tallies of the three gate populations."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.need_hist = Counter()          # need -> UL slots
        self.qual_total = 0
        self.qual_empty = 0                 # qualifying, nothing reported
        self.urg_hist = Counter()           # 20ths of urgency01 -> candidates
        self.urg_cands = 0
        self.last_ul = {}
        self._probe_buffers = None

    def allocate(self, slot, buffers, channel):
        self._probe_buffers = buffers
        out = super().allocate(slot, buffers, channel)
        for a in out:
            if a.direction == "UL":
                self.last_ul[a.ue_id] = slot.slot_index
        return out

    def _finalize_ul_coef(self, candidates):
        super()._finalize_ul_coef(candidates)
        buffers = self._probe_buffers
        qual = [c for c in candidates
                if not c.sched_inactive and c.has_gbr and c.gbr_bytes_slot > 0]
        self.need_hist[len(qual)] += 1
        for c in qual:
            self.qual_total += 1
            reported = sum(buffers.state(f.ue_id, f.qfi).bytes_reported
                           for f in c.flows)
            if reported <= 0:
                self.qual_empty += 1
        for c in candidates:
            if c.sched_inactive:
                continue
            self.urg_cands += 1
            self.urg_hist[min(20, int(c.urgency01 * 20))] += 1


def one(n_ues):
    sc = build_gt22_scenario(seed=SEED, n_ues=n_ues, horizon_slots=HORIZON,
                             telemetry_gbr=True)
    sched = Probe(min_rb=MIN_RB)
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    driver_run(with_srb(sc), sched, cqi_delay_slots=8, max_sched_ues=4,
               random_access=ra)
    return sched


def main():
    print(f"gt22, cap 4, telemetry GBR, {HORIZON} slots, seed {SEED}, "
          f"min_rb {MIN_RB}\n")
    for n in (int(x) for x in (sys.argv[1:] or "4 6 8 10 12 14 16 24".split())):
        s = one(n)
        slots = sum(s.need_hist.values())
        # DERIVED, not restated: the count at which the reserve exhausts a
        # 55-PRB band, and the depth bound the sweep registers.
        prb = s._grid.prb_count
        thresh = prb // MIN_RB              # need >= this exhausts the band
        depth_cap = prb // MIN_RB - 1
        ge = sum(v for k, v in s.need_hist.items() if k >= thresh)
        gd = sum(v for k, v in s.need_hist.items() if k > depth_cap)
        top = sorted(s.need_hist.items())
        empty_pct = 100.0 * s.qual_empty / s.qual_total if s.qual_total else 0.0
        ratios = s.urg_hist
        tot_r = sum(ratios.values())
        over = sum(v for k, v in ratios.items() if k >= 20)     # urgency01 >= 1.0
        half = sum(v for k, v in ratios.items() if k >= 10)     # >= 0.50
        print(f"N={n:2d} prb={prb} ul_slots={slots:6d} need_max={max(s.need_hist)} "
              f"need>= {thresh}: {ge:6d} ({100.0*ge/slots:5.1f}%)  "
              f"need>{depth_cap}: {gd:6d} ({100.0*gd/slots:5.1f}%)")
        print(f"        need hist {top}")
        print(f"        G-backlog: qualifying={s.qual_total:7d} "
              f"EMPTY={s.qual_empty:7d} ({empty_pct:4.1f}%)")
        print(f"        G-deadline: cands={tot_r:7d} urgency01>=1.0 {over:7d} "
              f"({100.0*over/tot_r if tot_r else 0:5.2f}%)  "
              f">=0.5 {half:7d} ({100.0*half/tot_r if tot_r else 0:5.2f}%)")
        print(f"        urgency01 hist (20ths) "
              f"{[(k/20, v) for k, v in sorted(ratios.items())]}")
        print()


if __name__ == "__main__":
    main()
