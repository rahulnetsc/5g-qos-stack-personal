"""ConfigSched2 (sim/baselines/config_sched2.py): one test per increment,
each asking something a run's output could contradict, plus the
at-scale check that the increment's mechanism is reached."""
from sim.baselines.config_sched2 import ConfigSched2, allocate_tracks
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.resource import ResourceGrid
from sim.scenarios import deployed_cell as _dcell
from sim.scenarios.g2 import build_gt12_scenario
from sim.scenarios.g3 import QFI_CAMERA, QFI_TELEMETRY, build_gt22_scenario
from sim.srb import with_srb


def _cell(n_ues=6, horizon=None, seed=1097657231):
    horizon = _dcell.slots(2_000.0) if horizon is None else horizon
    return with_srb(build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon))


class _St:
    def __init__(self, reported):
        self.bytes_queued = reported
        self.bytes_reported = reported
        self.lcg = 1
        self.estimated_ul_buffer_per_lcg = reported


class _Buffers:
    def __init__(self, table):
        self._t = table

    def state(self, ue, qfi):
        return _St(self._t.get((ue, qfi), 0))


class _Channel:
    def get_reported_snr_db(self, ue):
        return 20.0

    def get_snr_db(self, ue):
        return 20.0


def _ul_slot(grid):
    return next(grid.slot_grid(t) for t in range(20) if grid.slot_grid(t).ul_symbols > 0)


# ---------------------------------------------------------------- increment 1

def test_inc1_an_unplanned_contracted_flow_is_served_before_a_mapped_best_effort_backlog():
    """Cap 1, UL. UE 2's best-effort flow holds a plan and a track; UE 1's
    telemetry had NOTHING at the re-solve, so it has neither, and 300 B
    arrive afterwards. The prototype classed UE 1 "no share" and gave the
    slot to UE 2; here UE 1 is served first, sized for its 300 B, and the
    counter says the branch fired."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched2(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    bg = next(f for f in sc.flows if f.direction == "UL" and f.flow_class == "PF" and f.ue_id == 2)
    slot = _ul_slot(grid)
    s._resolve_tier1(slot, _Buffers({(2, bg.qfi): 200_000}), _Channel())
    key = (1, QFI_TELEMETRY)
    s._plan.pop(key, None)                   # the between-re-solves state, exactly:
    s._tracks["UL"].pop(key, None)           # no plan and no track
    s._period["UL"].pop(key, None)
    table = {key: 300, (2, bg.qfi): 200_000}
    got = s._place(slot, _Buffers(table), _Channel(), "UL")
    assert got and got[0].ue_id == 1 and got[0].ue_grant, [(a.ue_id, a.bytes_capacity) for a in got]
    assert got[0].bytes_capacity >= 300
    assert s.counters["unplanned_contracted_due"] > 0


# ---------------------------------------------------------------- increment 5

def test_inc5_tracks_are_disjoint_and_the_deployed_g3_fleet_fits_the_cap():
    """24 heartbeats at T = 32 and 24 cameras at T = 8 on a cap of 4: density
    3.75 <= 4, every flow placed, and no slot on any track holds two flows
    over a full period. Then a re-solve with the same periods keeps every
    flow's (track, residue) when asked to prefer the old map."""
    periods = {("tel", i): 32 for i in range(24)}
    periods.update({("cam", i): 8 for i in range(24)})
    density = sum(1.0 / T for T in periods.values())
    assert density <= 4
    assign = allocate_tracks(periods, 4)
    assert len(assign) == len(periods)
    seen = {}
    for key, (tr, r) in assign.items():
        for t in range(r, 640, periods[key]):
            assert (tr, t) not in seen, (key, seen[(tr, t)])
            seen[(tr, t)] = key
    again = allocate_tracks(periods, 4, prefer=assign)
    assert again == assign


def test_inc5_a_mapped_flow_is_served_in_its_slot_and_an_owed_flow_first_in_the_next():
    """After a re-solve every planned UL flow holds a track over the
    direction's own slots. At the telemetry's mapped index it is placed
    whatever else is backlogged; a flow owed a missed visit is served first
    at the next placement and is no longer owed."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched2(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    bg = next(f for f in sc.flows if f.direction == "UL" and f.flow_class == "PF" and f.ue_id == 2)
    key = (1, QFI_TELEMETRY)
    table = {key: 300, (2, bg.qfi): 200_000, (2, QFI_TELEMETRY): 300, (1, QFI_CAMERA): 5_000, (2, QFI_CAMERA): 5_000}
    slot = _ul_slot(grid)
    s._resolve_tier1(slot, _Buffers(table), _Channel())
    assert key in s._tracks["UL"], s._tracks["UL"]
    tr, r = s._tracks["UL"][key]
    T = s._period["UL"][key]
    assert T >= 2 and (T & (T - 1)) == 0
    assert sum(1.0 / t for t in s._period["UL"].values()) <= slot.max_sched_ues
    s._dir_index["UL"] = r                   # the telemetry's mapped direction-slot
    got = s._place(slot, _Buffers(table), _Channel(), "UL")
    assert any(a.ue_id == 1 for a in got), [(a.ue_id, a.bytes_capacity) for a in got]
    assert s.counters["mapped_visits_served"] >= 1
    # owed: served first at a non-mapped index, then no longer owed
    s._dir_index["UL"] = r + 1
    s._owed[key] = r
    got = s._place(slot, _Buffers(table), _Channel(), "UL")
    assert got and got[0].ue_id == 1, [(a.ue_id, a.bytes_capacity) for a in got]
    assert key not in s._owed


def test_inc5_is_reached_at_scale_on_g2_and_the_table_is_live():
    """G2 at N = 12, two simultaneous STOPs, cap 2, 4 s: tracks are mapped,
    mapped visits are served, the unplanned-contracted branch fires, and
    every planned flow got a track (density fitted)."""
    sc = with_srb(build_gt12_scenario(seed=1826701614, n_ues=12, n_stop=2, n_trials=6,
                                      horizon_slots=_dcell.slots(4_000.0)))
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    s = driver_run(sc, ConfigSched2(min_rb=5), cqi_delay_slots=8, max_sched_ues=2, random_access=ra, configured_grant=None)
    c = s["scheduler_counters"]
    assert c["tracks_mapped"] > 0 and c["mapped_visits_served"] > 0, dict(c)
    assert c["unplanned_contracted_due"] > 0, dict(c)
    assert c.get("track_unplaced", 0) == 0, dict(c)
