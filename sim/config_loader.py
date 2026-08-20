"""Assemble a ScenarioConfig from the three-file layout in sim/scenarios/.

A simulation run is the product of three independently editable concerns:

  - ran_config_<id>.yml      the radio: carrier (bandwidth, numerology,
                             overhead) and TDD pattern / S-slot split.
  - simulation_config.yml    the run window: horizon_slots, seed. Shared.
  - scenario_config_<n>.yml  the workload: UEs and flows, plus a
                             `default_ran:` naming the RAN it expects.

Keeping them separate lets one workload be run against different radios
(DSUUU vs DDDSU, narrow vs wide) without touching the workload file. See
sim/scenarios/README.md for the file structure.

Fields the simulator does not model are accepted and silently ignored
(e.g. a flow's max_data_rate_bps / MFBR — there is no rate-cap enforcement).
"""

from copy import deepcopy
from pathlib import Path

import yaml

from scheduler.flow import lcg_for_5qi, priority_for_5qi

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


def _carrier_from(ran: dict) -> CarrierConfig:
    c = ran["carrier"]
    return CarrierConfig(
        bandwidth_hz=int(c["bandwidth_mhz"] * 1_000_000),
        numerology=int(c["numerology"]),
        overhead_factor=float(c.get("overhead_factor", 0.85)),
    )


def _tdd_from(ran: dict) -> TDDConfig:
    t = ran["tdd"]
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
        # Default the priority from the standardised 5QI table rather than a
        # neutral constant: two flows on one UE sharing a priority makes the
        # MAC multiplexer's order depend on YAML listing order. An explicit
        # priority_level in the scenario still wins.
        priority_level=int(
            flow_dict.get("priority_level", priority_for_5qi(flow_dict["qfi"]))
        ),
        # Default the LCG from the simulator's 5QI->LCG table, same idiom
        # as priority_level above; an explicit `lcg` in the scenario wins.
        # (FlowConfig.__post_init__ also range-checks it either way.)
        lcg=int(flow_dict.get("lcg", lcg_for_5qi(flow_dict["qfi"]))),
        slice_id=int(flow_dict.get("slice_id", 0)),
        # UE-side LCP config (uplink). pbr_bps unset means "use the GFBR"
        # for a GBR flow and "no prioritised rate" otherwise -- see
        # FlowConfig.effective_pbr_bps.
        pbr_bps=float(flow_dict.get("prioritised_bit_rate_bps", 0.0)),
        bsd_ms=float(flow_dict.get("bucket_size_duration_ms", 100.0)),
        traffic_kind=traffic_kind,
        traffic_params=traffic_params,
    )


def load_scenario(
    scenarios_dir: str | Path,
    scenario_id: int | str,
    ran_id: str | None = None,
) -> ScenarioConfig:
    """Assemble a ScenarioConfig from `scenarios_dir`'s three-file layout.

    Reads `scenario_config_<scenario_id>.yml` for the workload, the shared
    `simulation_config.yml` for the run window, and a RAN file for the radio.
    The RAN is the scenario's `default_ran` unless `ran_id` overrides it —
    that override is the knob for running one workload on different radios.
    """
    scenarios_dir = Path(scenarios_dir)
    scen = _load_yaml(scenarios_dir / f"scenario_config_{scenario_id}.yml")
    ran_id = ran_id or scen["default_ran"]
    ran = _load_yaml(scenarios_dir / f"ran_config_{ran_id}.yml")
    sim = _load_yaml(scenarios_dir / "simulation_config.yml")

    run = sim.get("simulation", {})
    defaults = scen.get("defaults", {})
    ue_defaults = defaults.get("ue", {})
    flow_defaults = defaults.get("flow", {})

    ues: list[UEConfig] = []
    flows: list[FlowConfig] = []
    for ue_block in scen["ues"]:
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
        name=str(scen.get("name", f"scenario_{scenario_id}")),
        horizon_slots=int(run.get("horizon_slots", 4000)),
        carrier=_carrier_from(ran),
        tdd=_tdd_from(ran),
        ues=ues,
        flows=flows,
        seed=int(run.get("seed", 42)),
    )
