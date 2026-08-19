"""Two-tier 5G QoS scheduler -- a self-contained library.

Tier-1 is a CVXPY LP that sets per-flow target rates over a ~1 s horizon;
Tier-2 is a per-slot drift-plus-penalty scheduler that grants PRBs per UE
and fills each transport block with a MAC logical-channel multiplexer.

The package depends only on cvxpy / numpy -- never on the simulator. A host
(the simulator, or an OAI adapter) supplies the slot / buffer / channel
state, which need only satisfy the structural views in `interfaces`.
"""

from .flow import FlowConfig
from .link import bits_per_prb, bler_for_mcs, cce_aggregation_level, mcs_threshold_for_snr, snr_to_prb_floor
from .interfaces import (
    Allocation,
    BufferView,
    ChannelView,
    GridView,
    Scheduler,
    SlotView,
)
from .tier1 import (
    estimate_demand_bps,
    gbr_contract_bps,
    gbr_maxmin_floors,
    grid_capacity_prbsym_per_sec,
    solve_maxmin_gbr_level,
    solve_tier1,
)
from .two_tier import TwoTier
from .config_loader import load_two_tier, load_two_tier_config

__all__ = [
    "FlowConfig",
    "bits_per_prb",
    "bler_for_mcs",
    "cce_aggregation_level",
    "mcs_threshold_for_snr",
    "snr_to_prb_floor",
    "Allocation",
    "Scheduler",
    "SlotView",
    "GridView",
    "BufferView",
    "ChannelView",
    "solve_tier1",
    "solve_maxmin_gbr_level",
    "gbr_maxmin_floors",
    "gbr_contract_bps",
    "grid_capacity_prbsym_per_sec",
    "estimate_demand_bps",
    "TwoTier",
    "load_two_tier",
    "load_two_tier_config",
]
