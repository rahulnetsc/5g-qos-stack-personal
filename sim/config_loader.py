"""Load ScenarioConfig from the YAML pair in configs/.

system_config.yml carries the radio / gNodeB side (bandwidth, numerology, TDD).
sim_config.yml carries the workload (UEs, flows, run horizon).

Fields the simulator doesn't yet model are accepted and silently ignored:
  - system: gnodeb.count > 1, mimo.mu_mimo_active, mimo.max_*_layers,
            pdcch.cce_budget_per_slot (the sim derives PDCCH per slot-type
            in sim/resource.py), duplex (only TDD supported)
  - flow:   max_data_rate_bps (MFBR — no cap enforcement yet)
"""

from copy import deepcopy
from pathlib import Path

import yaml

from .config import (
    CarrierConfig,
    FlowConfig,
    ScenarioConfig,
    TDDConfig,
    UEConfig,
)


def _load_yaml(path: str | Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_system(path: str | Path) -> tuple[CarrierConfig, TDDConfig]:
    """Parse system_config.yml into (CarrierConfig, TDDConfig)."""
    cfg = _load_yaml(path)

    c = cfg["carrier"]
    carrier = CarrierConfig(
        bandwidth_hz=int(c["bandwidth_mhz"] * 1_000_000),
        numerology=int(c["numerology"]),
        overhead_factor=float(c.get("overhead_factor", 0.85)),
    )

    t = cfg["tdd"]
    s = t["s_slot_split"]
    tdd = TDDConfig(
        pattern=str(t["pattern"]),
        s_slot_split=(
            int(s["dl_symbols"]),
            int(s["gap_symbols"]),
            int(s["ul_symbols"]),
        ),
    )
    return carrier, tdd


def _merge_flow(defaults: dict, override: dict) -> dict:
    """Shallow-merge a flow override on top of defaults. The `traffic` key is
    treated atomically — if the override specifies any traffic field, the
    override's traffic dict replaces the default's entirely.
    """
    merged = deepcopy(defaults)
    for k, v in override.items():
        if k == "traffic":
            merged["traffic"] = deepcopy(v)
        else:
            merged[k] = v
    return merged


def _flow_from_dict(ue_id: int, flow_dict: dict) -> FlowConfig:
    traffic = flow_dict.get("traffic", {})
    traffic_kind = traffic.get("kind", "poisson")
    traffic_params = {k: v for k, v in traffic.items() if k != "kind"}
    return FlowConfig(
        ue_id=ue_id,
        qfi=int(flow_dict["qfi"]),
        direction=flow_dict.get("direction", "DL"),
        flow_class=flow_dict.get("flow_class", "PF"),
        pdb_ms=float(flow_dict.get("max_delay_budget_ms", 100.0)),
        gfbr_bps=float(flow_dict.get("min_data_rate_bps", 0.0)),
        traffic_kind=traffic_kind,
        traffic_params=traffic_params,
    )


def load_scenario(
    system_path: str | Path,
    sim_path: str | Path,
    name: str = "yaml",
) -> ScenarioConfig:
    """Build a ScenarioConfig from the system + sim YAML pair."""
    carrier, tdd = load_system(system_path)
    sim = _load_yaml(sim_path)

    run = sim.get("simulation", {})
    defaults = sim.get("defaults", {})
    ue_defaults = defaults.get("ue", {})
    flow_defaults = defaults.get("flow", {})

    ues: list[UEConfig] = []
    flows: list[FlowConfig] = []
    for ue_block in sim["ues"]:
        ue_id = int(ue_block["ue_id"])
        ues.append(
            UEConfig(
                ue_id=ue_id,
                mean_snr_db=float(
                    ue_block.get("mean_snr_db", ue_defaults.get("mean_snr_db", 20.0))
                ),
                coherence_slots=int(
                    ue_block.get(
                        "coherence_slots", ue_defaults.get("coherence_slots", 100)
                    )
                ),
            )
        )
        for flow_block in ue_block.get("flows", []):
            merged = _merge_flow(flow_defaults, flow_block)
            flows.append(_flow_from_dict(ue_id, merged))

    return ScenarioConfig(
        name=name,
        horizon_slots=int(run.get("horizon_slots", 4000)),
        carrier=carrier,
        tdd=tdd,
        ues=ues,
        flows=flows,
        seed=int(run.get("seed", 42)),
    )
