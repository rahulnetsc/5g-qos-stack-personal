"""Load a ScenarioConfig from a single self-contained scenario YAML.

Each scenario lives in one file, sim/scenarios/scenario_config_<id>.yml,
carrying the radio (carrier, tdd), the run window (simulation), optional
defaults, and the UE/flow workload. See sim/scenarios/README.md for the
full file structure.

Fields the simulator does not model are accepted and silently ignored
(e.g. a flow's max_data_rate_bps / MFBR — there is no rate-cap enforcement).
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


def _carrier_from(cfg: dict) -> CarrierConfig:
    c = cfg["carrier"]
    return CarrierConfig(
        bandwidth_hz=int(c["bandwidth_mhz"] * 1_000_000),
        numerology=int(c["numerology"]),
        overhead_factor=float(c.get("overhead_factor", 0.85)),
    )


def _tdd_from(cfg: dict) -> TDDConfig:
    t = cfg["tdd"]
    s = t["s_slot_split"]
    return TDDConfig(
        pattern=str(t["pattern"]),
        s_slot_split=(
            int(s["dl_symbols"]),
            int(s["gap_symbols"]),
            int(s["ul_symbols"]),
        ),
    )


def _merge_flow(defaults: dict, override: dict) -> dict:
    """Shallow-merge a flow override on top of defaults. The `traffic` key is
    treated atomically — if the override specifies a traffic block, it
    replaces the default's entirely."""
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


def load_scenario_file(
    path: str | Path, name: str | None = None
) -> ScenarioConfig:
    """Build a ScenarioConfig from one self-contained scenario YAML file.

    `name` overrides the scenario name; otherwise the file's `name:` key is
    used, falling back to the filename stem.
    """
    cfg = _load_yaml(path)

    run = cfg.get("simulation", {})
    defaults = cfg.get("defaults", {})
    ue_defaults = defaults.get("ue", {})
    flow_defaults = defaults.get("flow", {})

    ues: list[UEConfig] = []
    flows: list[FlowConfig] = []
    for ue_block in cfg["ues"]:
        ue_id = int(ue_block["ue_id"])
        ues.append(
            UEConfig(
                ue_id=ue_id,
                mean_snr_db=float(
                    ue_block.get(
                        "mean_snr_db", ue_defaults.get("mean_snr_db", 20.0)
                    )
                ),
                coherence_slots=int(
                    ue_block.get(
                        "coherence_slots",
                        ue_defaults.get("coherence_slots", 100),
                    )
                ),
            )
        )
        for flow_block in ue_block.get("flows", []):
            merged = _merge_flow(flow_defaults, flow_block)
            flows.append(_flow_from_dict(ue_id, merged))

    return ScenarioConfig(
        name=str(name or cfg.get("name", Path(path).stem)),
        horizon_slots=int(run.get("horizon_slots", 4000)),
        carrier=_carrier_from(cfg),
        tdd=_tdd_from(cfg),
        ues=ues,
        flows=flows,
        seed=int(run.get("seed", 42)),
    )
