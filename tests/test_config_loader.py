"""End-to-end check that the YAML config pair builds a runnable scenario."""

from pathlib import Path

from sim.config_loader import load_scenario, load_system
from sim.driver import run
from sim.scenarios import yaml_scenario
from sim.schedulers.round_robin import RoundRobin


_CONFIGS = Path(__file__).resolve().parent.parent / "configs"


def test_load_system_translates_units_and_tdd():
    carrier, tdd = load_system(_CONFIGS / "system_config.yml")
    # 40 MHz -> 40_000_000 Hz, mu=2
    assert carrier.bandwidth_hz == 40_000_000
    assert carrier.numerology == 2
    # TDD pattern + S-slot symbol split (sum to 14)
    assert tdd.pattern == "DSUUU"
    assert tdd.s_slot_split == (3, 2, 9)
    assert sum(tdd.s_slot_split) == 14


def test_load_scenario_flattens_ues_and_flows():
    scen = load_scenario(
        _CONFIGS / "system_config.yml",
        _CONFIGS / "sim_config.yml",
    )
    # 10 robot UEs; mix of 2/3/4 flows each (24 total in the current scenario).
    assert len(scen.ues) == 10
    assert len(scen.flows) == 24
    # Defaults propagate (every UE got a coherence_slots, every flow got a PDB)
    assert all(ue.coherence_slots > 0 for ue in scen.ues)
    assert all(f.pdb_ms > 0 for f in scen.flows)
    # GBR / Delay overrides survived the merge
    gbr_flows = [f for f in scen.flows if f.flow_class == "GBR"]
    delay_flows = [f for f in scen.flows if f.flow_class == "Delay"]
    assert gbr_flows and all(f.gfbr_bps > 0 for f in gbr_flows)
    assert delay_flows and all(f.pdb_ms <= 30 for f in delay_flows)
    # UL/DL split: this scenario is uplink-heavy (more UL flows than DL).
    ul_flows = [f for f in scen.flows if f.direction == "UL"]
    dl_flows = [f for f in scen.flows if f.direction == "DL"]
    assert len(ul_flows) > len(dl_flows)


def test_yaml_scenario_runs_end_to_end():
    """The YAML-driven scenario must actually execute through the driver."""
    scen = yaml_scenario()
    summary = run(scen, RoundRobin())
    assert summary["horizon_s"] > 0
    assert len(summary["flows"]) == 24
    # At least one flow should have delivered bytes (sanity, not correctness)
    assert any(f["throughput_bps"] > 0 for f in summary["flows"].values())
