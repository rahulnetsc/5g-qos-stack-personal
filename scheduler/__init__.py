"""Two-tier 5G QoS scheduler -- a self-contained library.

Tier-1 is an SCA-wrapped LP that re-solves per-flow target rates every
0.1s (`scheduler/tier1.py`); Tier-2 is a per-slot drift-plus-penalty
scheduler that grants PRBs per UE and fills each transport block with a
MAC logical-channel multiplexer.

The package depends only on scipy / numpy -- never on the simulator. A
host (the simulator, or an OAI adapter) supplies the slot / buffer /
channel state, which need only satisfy the structural views in
`interfaces`.
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
    grid_capacity_prbsym_per_sec,
    solve_tier1,
    tier1_capacity_prbslot_per_sec,
)
from .two_tier import TwoTier
from .config_loader import load_two_tier, load_two_tier_config
from .reservation import Reservation

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
    "grid_capacity_prbsym_per_sec",
    "tier1_capacity_prbslot_per_sec",
    "TwoTier",
    "load_two_tier",
    "load_two_tier_config",
    "Reservation",
]
