"""Scenario registry — the three-file layout in this package directory.

A simulation run is the product of three independently editable files:

  - ran_config_<id>.yml      the radio (carrier + TDD).
  - simulation_config.yml    the run window (horizon, seed). Shared.
  - scenario_config_<n>.yml  the workload (UEs/flows) + a `default_ran:`.

`scenario(n)` assembles run n on its default radio; pass `ran_id` to run
the same workload on a different radio (DSUUU vs DDDSU, narrow vs wide).
The named helpers below are thin wrappers over the numbered scenarios.

To add a scenario: drop a scenario_config_<next>.yml file in this
directory (it names its own default_ran); `scenario(<next>)` loads it.
See README.md for the file structure.
"""

from pathlib import Path

from ..config import ScenarioConfig
from ..config_loader import load_scenario

_DIR = Path(__file__).resolve().parent


def scenario(scenario_id: int, ran_id: str | None = None) -> ScenarioConfig:
    """Load scenario_config_<scenario_id>.yml, on its default RAN unless
    `ran_id` names a different ran_config_<id>.yml."""
    return load_scenario(_DIR, scenario_id, ran_id)


def smoke_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 1 — mixed workload, no overload; a sanity baseline."""
    return scenario(1, ran_id)


def overload_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 2 — PF/GBR/Delay flows under severe overload."""
    return scenario(2, ran_id)


def vision_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 3 — three cameras + best-effort; I-frame bursts."""
    return scenario(3, ran_id)


def sensor_dense_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 4 — 30 dense periodic UL sensors; PDCCH-limited."""
    return scenario(4, ran_id)


def latency_bound_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 5 — medium-rate deadline streams vs bulk on a congested DL."""
    return scenario(5, ran_id)


def factory_robots_scenario(ran_id: str | None = None) -> ScenarioConfig:
    """Scenario 6 — 10 factory robots; the main study scenario."""
    return scenario(6, ran_id)
