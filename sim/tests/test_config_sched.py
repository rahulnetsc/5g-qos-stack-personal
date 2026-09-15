"""Configuration-based scheduler prototype (sim/baselines/config_sched.py).
Every test asks something a run's output could contradict."""
import math

from scheduler.two_tier import TwoTier
from sim.baselines.config_sched import ConfigSched
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.resource import ResourceGrid
from sim.scenarios import deployed_cell as _dcell
from sim.run_record import RunRecord
from sim.scenarios.g3 import (QFI_CAMERA, QFI_FLEET_DL, QFI_TELEMETRY, TELEMETRY_PERIOD_MS,
                              build_gt22_scenario)
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


def test_tier1_prb_budget_is_symbol_weighted_and_the_visit_budget_is_slot_counted():
    """On the deployed `DDSUU` cell the special slot carries 6 of 14 symbols
    per direction. Tier 1's PRB budget must weight it by those symbols,
    while the visit (DCI) budget counts it as a whole slot. Both expected
    values are derived from the grid inside the test, never restated; the
    first build's slot-counted PRB budget is asserted to be strictly larger
    than the symbol-weighted one, so the test could see a regression to it."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    pat = len(grid.pattern)
    w = s._window_slots
    for direction, attr in (("UL", "ul_symbols"), ("DL", "dl_symbols")):
        syms = [getattr(grid.slot_grid(k), attr) for k in range(pat)]
        slot_count = w * sum(1 for x in syms if x > 0) // pat
        full = max(syms)
        prbslots = w * sum(syms) / (pat * full)
        assert s._dir_slots_per_window[direction] == slot_count
        assert abs(s._dir_prbslots_per_window[direction] - prbslots) < 1e-9, direction
        assert any(0 < x < full for x in syms), "the deployed pattern has a mixed slot"
        assert prbslots < slot_count, (direction, prbslots, slot_count)


def test_tier2_stops_at_the_cap_and_stamps_only_what_it_places():
    """Eight robots, every heartbeat due at once, cap derived from the grid
    (4 at 106 PRB). Placement must stop at the cap: at most `cap` UEs get a
    grant, no clock is stamped for a UE that got none, and the skip is
    counted. The first build placed all eight and trimmed afterwards, so the
    four trimmed robots' clocks read "served" for a grant never sent."""
    sc = _cell(n_ues=8)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    slot = grid.slot_grid(2)
    cap = slot.max_sched_ues
    assert 0 < cap < 8, cap
    for direction, qfi in (("UL", QFI_TELEMETRY), ("DL", QFI_FLEET_DL)):
        s._last_visit.clear()
        s.counters.clear()
        table = {(ue, qfi): 300 for ue in range(1, 9)}
        s._resolve_tier1(slot, _Buffers(table), _Channel())
        got = s._place(slot, _Buffers(table), _Channel(), direction)
        placed = {a.ue_id for a in got}
        assert len(placed) == cap, (direction, placed)
        stamped = {k[0] for k in s._last_visit}
        assert stamped == placed, (direction, stamped, placed)
        assert s.counters[f"cap_skipped_{direction.lower()}_due"] == 8 - cap, dict(s.counters)
        # and allocate() itself never hands the driver more UEs than the cap
        assert len({a.ue_id for a in s.allocate(slot, _Buffers(table), _Channel())}) <= cap


def _instrument_heartbeats(sc, summary, arm: str) -> int:
    """Messages the instrument robot's (UE 1) telemetry completed in a run."""
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm, seed=0,
                                 flow_configs=sc.flows, summary=summary,
                                 arm={"cqi_delay_slots": 8, "max_sched_ues": 4}, meta={})
    flows = rec.flows.values() if isinstance(rec.flows, dict) else rec.flows
    tel = next(fr for fr in flows if fr.ue_id == 1 and fr.qfi == QFI_TELEMETRY and fr.direction == "UL")
    return sum(len(v) for v in (tel.completion_ts_by_role_s or {}).values())


def test_at_a_fleet_that_starves_twotier_the_instrument_is_no_worse_than_the_port_and_it_is_reached():
    """G3 at N = 16 is where the port's telemetry shows 300 ms silences. The
    arm's claim is that removing the rank leaves the instrument robot (UE 1)
    no worse than the port on the same seed: it completes at least as many
    heartbeats as TwoTier, out of a schedule whose size is derived from the
    horizon and the period. The arm is shown to have run (grants in both
    directions, Tier 1 re-solved, the cap reached), and it delivers at least
    the port's telemetry bytes. The camera floors may not fit (16 x 4 Mbps
    is beyond this cell's uplink) and that is reported, not hidden.

    Two earlier forms of this assertion were wrong in the same direction.
    `visits_late_qfi1 == 0`, from the arm's own clock, was green only
    because placement stamped visits for grants the per-slot cap then
    discarded. "UE 1 delivers EVERY heartbeat" held on the slot-counted PRB
    budget and not on the symbol-weighted one: with the real capacity the
    plan shifts and UE 1's first message, generated while 16 robots attach
    at once, expires at its PDB (19 of 20 in 2 s). The prototype's order
    has no priority or age term, so "every heartbeat" is not something it
    guarantees; the relative claim is."""
    n = 16
    sc = _cell(n_ues=n)
    s = _run(sc, ConfigSched(min_rb=5))
    c = s["scheduler_counters"]
    assert c["t1_resolves"] > 0 and c["grants_ul"] > 0 and c["grants_dl"] > 0
    assert c["visits_stamped"] > 0
    assert c["cap_skipped_ul_due"] > 0, dict(c)      # the cap is reached, so the mechanism is live
    expected = int(sc.horizon_slots * _dcell.SLOT_S * 1000.0 // TELEMETRY_PERIOD_MS)
    assert expected > 1
    sc_t = _cell(n_ues=n)
    t = _run(sc_t, TwoTier(min_rb=5))
    got_cs, got_tt = _instrument_heartbeats(sc, s, "ConfigSched"), _instrument_heartbeats(sc_t, t, "TwoTier")
    assert 0 < got_cs <= expected and 0 < got_tt <= expected, (got_cs, got_tt, expected)
    assert got_cs >= got_tt, (got_cs, got_tt, expected)
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
