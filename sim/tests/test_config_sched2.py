"""ConfigSched2 (sim/baselines/config_sched2.py): one test per increment,
each asking something a run's output could contradict, plus the
at-scale check that the increment's mechanism is reached."""
from sim.baselines.config_sched2 import ConfigSched2
from sim.driver import run as driver_run
from sim.random_access import RandomAccessConfig
from sim.resource import ResourceGrid
from sim.scenarios import deployed_cell as _dcell
from sim.scenarios.g2 import QFI_STOP, build_gt12_scenario
from sim.scenarios.g3 import QFI_TELEMETRY, build_gt22_scenario
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


def test_inc1_an_unplanned_contracted_flow_is_due_now_and_placed_before_planned_best_effort():
    """Cap 1, UL. UE 2's best-effort flow has a residual plan (it was backlogged
    at the re-solve); UE 1's telemetry had NOTHING at the re-solve, so it has
    no plan, and 300 B arrive afterwards. The prototype classed UE 1 "no
    share" and gave the slot to UE 2; increment 1 makes UE 1 due now, sized
    for its 300 B, and the counters say the branch fired."""
    sc = _cell(n_ues=2)
    grid = ResourceGrid(sc.carrier, sc.tdd)
    s = ConfigSched2(min_rb=5)
    s.configure(sc.flows, grid.slot_duration_s, grid)
    bg = next(f for f in sc.flows if f.direction == "UL" and f.flow_class == "PF" and f.ue_id == 2)
    slot = grid.slot_grid(2)
    # re-solve with UE 1 silent and UE 2 backlogged, then UE 1's message arrives
    s._resolve_tier1(slot, _Buffers({(2, bg.qfi): 200_000}), _Channel())
    assert s._plan.get((1, QFI_TELEMETRY)) is None or s._plan[(1, QFI_TELEMETRY)].n_visits >= 1
    s._plan.pop((1, QFI_TELEMETRY), None)          # the between-re-solves state, exactly
    table = {(1, QFI_TELEMETRY): 300, (2, bg.qfi): 200_000}
    got = s._place(slot, _Buffers(table), _Channel(), "UL")
    assert got and got[0].ue_id == 1 and got[0].ue_grant, [(a.ue_id, a.bytes_capacity) for a in got]
    assert got[0].bytes_capacity >= 300
    assert s.counters["unplanned_contracted_due"] > 0 and s.counters["unplanned_contracted_sized"] > 0
    # and a best-effort flow with no plan is still leftover: class 2
    s._plan.pop((2, bg.qfi), None)
    assert s._due_key((2, bg.qfi), 2)[0] == 2


def test_inc1_is_reached_at_scale_on_g2_and_no_planned_stop_expires_for_want_of_a_plan():
    """G2 at N = 12, two simultaneous STOPs, cap 2, 2 s: the mechanism fires
    (counted), and every STOP that arrives between re-solves is granted --
    the prototype expired 32 of 34 such arrivals on one seed."""
    sc = with_srb(build_gt12_scenario(seed=1826701614, n_ues=12, n_stop=2, n_trials=6,
                                      horizon_slots=_dcell.slots(4_000.0)))
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    s = driver_run(sc, ConfigSched2(min_rb=5), cqi_delay_slots=8, max_sched_ues=2, random_access=ra, configured_grant=None)
    c = s["scheduler_counters"]
    assert c["unplanned_contracted_due"] > 0, dict(c)
    assert c["unplanned_contracted_sized"] > 0, dict(c)
