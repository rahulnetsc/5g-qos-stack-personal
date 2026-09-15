"""Configuration-based scheduler prototype (sim/baselines/config_sched.py).
Every test asks something a run's output could contradict."""
import math

from scheduler.two_tier import TwoTier
from sim.baselines.config_sched import ConfigSched
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.resource import ResourceGrid
from sim.scenarios import deployed_cell as _dcell
from sim.scenarios.g3 import QFI_CAMERA, QFI_TELEMETRY, build_gt22_scenario
from sim.srb import with_srb


def _cell(n_ues=6, horizon=None, seed=1097657231):
    horizon = _dcell.slots(2_000.0) if horizon is None else horizon
    return with_srb(build_gt22_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon))


def _run(sc, sched, sink=None):
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    return driver_run(sc, sched, cqi_delay_slots=8, max_sched_ues=4, random_access=ra,
                      configured_grant=None, grant_sink=sink)


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


def test_tier1_floors_follow_the_pdb_and_the_contract():
    """A 300 B / 100 ms telemetry contract with PDB 100 ms owes one visit per
    100 ms window and 300 B of it; the camera's floor is GFBR x W."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    tel = next(f for f in sc.flows if f.qfi == QFI_TELEMETRY and f.ue_id == 1)
    cam = next(f for f in sc.flows if f.qfi == QFI_CAMERA and f.ue_id == 1)
    table = {(f.ue_id, f.qfi): 5_000 for f in sc.flows if f.direction == "UL"}
    slot = grid.slot_grid(2)
    s._resolve_tier1(slot, _Buffers(table), _Channel())
    w = s._window_slots
    assert w == _dcell.slots(100.0)
    p_tel = s._plan[(1, QFI_TELEMETRY)]
    assert p_tel.contracted and p_tel.floor_visits == math.ceil(w / _dcell.slots(tel.pdb_ms))
    assert p_tel.n_visits >= p_tel.floor_visits >= 1
    assert p_tel.bytes_per_visit * p_tel.n_visits >= int(tel.gfbr_bps * 0.1 / 8)
    p_cam = s._plan[(1, QFI_CAMERA)]
    assert p_cam.contracted
    assert p_cam.bytes_per_visit * p_cam.n_visits >= int(cam.gfbr_bps * 0.1 / 8) * 0.99
    assert s.counters["t1_resolves"] == 1


def test_a_due_contracted_flow_is_placed_before_a_best_effort_backlog():
    """Cap 1: UE 2 holds a large best-effort backlog, UE 1 a due telemetry
    visit. The slot goes to UE 1 -- no rank a flood can win."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    bg = next(f for f in sc.flows if f.direction == "UL" and f.flow_class == "PF" and f.ue_id == 2)
    table = {(1, QFI_TELEMETRY): 300, (2, bg.qfi): 200_000}
    slot = grid.slot_grid(2)
    s._resolve_tier1(slot, _Buffers(table), _Channel())
    got = s._place(slot, _Buffers(table), _Channel(), "UL")
    assert got and got[0].ue_id == 1 and got[0].ue_grant
    assert got[0].bytes_capacity >= 300
    # and once served, UE 1 is not due again until its interval elapses
    s._resolve_tier1(slot, _Buffers(table), _Channel())
    again = s._place(grid.slot_grid(3), _Buffers(table), _Channel(), "UL")
    assert again and again[0].ue_id == 2


def test_at_a_fleet_that_starves_twotier_no_visit_is_late_and_it_is_reached():
    """G3 at N = 16 is where the port's telemetry shows 300 ms silences. Here
    every eligible TELEMETRY visit is served on time (the camera floors may
    not fit: 16 x 4 Mbps is beyond this cell's uplink, and that is reported),
    the arm actually ran (grants in both directions, Tier 1 re-solved), and
    the arm delivers at least the port's telemetry bytes."""
    n = 16
    s = _run(_cell(n_ues=n), ConfigSched(min_rb=5))
    c = s["scheduler_counters"]
    assert c["t1_resolves"] > 0 and c["grants_ul"] > 0 and c["grants_dl"] > 0
    assert c["visits_stamped"] > 0
    assert c.get(f"visits_late_qfi{QFI_TELEMETRY}", 0) == 0, {k: v for k, v in c.items() if "late" in k or "unmet" in k}
    t = _run(_cell(n_ues=n), TwoTier(min_rb=5))
    def tel_bytes(summary):
        return sum(v.get("delivered_bytes", 0) for k, v in summary.get("flows", {}).items()
                   if k.endswith(f"qfi{QFI_TELEMETRY}")) if isinstance(summary.get("flows"), dict) else None
    a, b = tel_bytes(s), tel_bytes(t)
    if a is not None and b is not None:
        assert a >= b * 0.95, (a, b)


def test_two_runs_are_identical():
    a = _run(_cell(n_ues=4), ConfigSched(min_rb=5))
    b = _run(_cell(n_ues=4), ConfigSched(min_rb=5))
    assert a["scheduler_counters"] == b["scheduler_counters"]
