"""Scenario registry.

Each scenario is a self-contained YAML file in this package directory
(``scenario_config_<id>.yml``); the functions here load one into a
``ScenarioConfig``. See README.md for the file structure.

To add a scenario: drop a new ``scenario_config_<id>.yml`` file here and
add a one-line loader function below.
"""

from pathlib import Path

from ..config import ScenarioConfig
from ..config_loader import load_scenario_file

_DIR = Path(__file__).resolve().parent


def _load(scenario_id: str) -> ScenarioConfig:
    return load_scenario_file(_DIR / f"scenario_config_{scenario_id}.yml")


def smoke_scenario() -> ScenarioConfig:
    """Mixed workload, no overload. All schedulers should serve everyone."""
    return _load("smoke")


def overload_scenario() -> ScenarioConfig:
    """Severe DL overload — exposes QoS-enforcement differences."""
    return _load("overload")


def vision_scenario() -> ScenarioConfig:
    """Three 30 fps cameras + best-effort; I-frame bursts stress tail latency."""
    return _load("vision")


def sensor_dense_scenario() -> ScenarioConfig:
    """30 dense periodic UL sensors — the PDCCH/CCE-limited regime."""
    return _load("sensor_dense")


def latency_bound_scenario() -> ScenarioConfig:
    """Medium-rate deadline streams vs bulk on a congested DL."""
    return _load("latency_bound")


def factory_robots_scenario() -> ScenarioConfig:
    """10 factory robots on a private 5G cell — the main study scenario."""
    return _load("factory_robots")
