"""Every scenario_config_*.yml loads into a runnable ScenarioConfig."""

import pytest

from sim import scenarios
from sim.driver import run
from sim.baselines.round_robin import RoundRobin

_ALL_SCENARIOS = [
    scenarios.smoke_scenario,
    scenarios.overload_scenario,
    scenarios.vision_scenario,
    scenarios.sensor_dense_scenario,
    scenarios.latency_bound_scenario,
    scenarios.factory_robots_scenario,
]


@pytest.mark.parametrize("factory", _ALL_SCENARIOS, ids=lambda f: f.__name__)
def test_scenario_loads_and_runs(factory):
    """Each scenario YAML must parse and execute end to end."""
    scen = factory()
    assert scen.ues and scen.flows
    assert scen.horizon_slots > 0
    assert scen.carrier.bandwidth_hz > 0
    assert sum(scen.tdd.s_slot_split) == 14
    summary = run(scen, RoundRobin())
    assert summary["horizon_s"] > 0
    assert any(f["throughput_bps"] > 0 for f in summary["flows"].values())


def test_factory_robots_flattens_ues_and_flows():
    """The factory scenario: 10 robot UEs, 24 flows, defaults propagated,
    units translated (40 MHz -> 40e6 Hz)."""
    scen = scenarios.factory_robots_scenario()
    assert len(scen.ues) == 10
    assert len(scen.flows) == 24
    assert scen.carrier.bandwidth_hz == 40_000_000
    assert scen.carrier.numerology == 2
    # Defaults propagate: every UE got a coherence_slots, every flow a PDB.
    assert all(ue.coherence_slots > 0 for ue in scen.ues)
    assert all(f.pdb_ms > 0 for f in scen.flows)
    # GBR / Delay overrides survived the merge.
    gbr = [f for f in scen.flows if f.flow_class == "GBR"]
    delay = [f for f in scen.flows if f.flow_class == "Delay"]
    assert gbr and all(f.gfbr_bps > 0 for f in gbr)
    assert delay and all(f.pdb_ms <= 30 for f in delay)
    # Uplink-heavy: more UL flows than DL.
    ul = [f for f in scen.flows if f.direction == "UL"]
    dl = [f for f in scen.flows if f.direction == "DL"]
    assert len(ul) > len(dl)


def test_ran_override_runs_workload_on_a_different_radio():
    """Passing ran_id swaps the radio while leaving the workload intact."""
    default = scenarios.latency_bound_scenario()
    override = scenarios.latency_bound_scenario(ran_id="dsuuu_30mhz")
    # Default RAN is DL-heavy DDDSU; the override is balanced DSUUU.
    assert default.tdd.pattern == "DDDSU"
    assert override.tdd.pattern == "DSUUU"
    assert override.carrier.bandwidth_hz == 30_000_000
    # The workload (UEs/flows) is identical regardless of RAN.
    assert len(default.flows) == len(override.flows)
    assert [f.qfi for f in default.flows] == [f.qfi for f in override.flows]


def test_empty_flow_inherits_defaults():
    """`flows: [{}]` must inherit the whole default flow (sensor_dense uses
    this to stay compact)."""
    scen = scenarios.sensor_dense_scenario()
    assert len(scen.ues) == 30
    assert len(scen.flows) == 30
    for f in scen.flows:
        assert f.qfi == 1
        assert f.flow_class == "Delay"
        assert f.direction == "UL"
        assert f.traffic_kind == "deterministic"
        assert f.traffic_params["bytes_per_period"] == 200
