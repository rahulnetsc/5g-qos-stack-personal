"""FlowConfig -- the scheduler's per-flow QoS / traffic descriptor.

One FlowConfig is the scheduler's view of a single uni-directional flow
(a DRB / logical channel): its QoS class and contract, its scheduling
priority, and enough of a traffic descriptor for Tier-1 to estimate the
offered load. In an OAI deployment this is populated from the 5QI / QoS
profile of each bearer.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class FlowConfig:
    ue_id: int
    qfi: int
    direction: Literal["DL", "UL"]
    flow_class: Literal["PF", "GBR", "Delay"] = "PF"
    pdb_ms: float = 100.0
    gfbr_bps: float = 0.0
    # Scheduling priority, 3GPP 5QI convention: lower value = higher priority.
    # Used to tier SPS reservations and the MAC logical-channel multiplexer.
    # Default is a single neutral level; set per-flow once the workload is
    # mapped to standardised 5QIs.
    priority_level: int = 100
    # Network-slice id. Tier-1 can give each slice a guaranteed share of PRB
    # capacity; default 0 puts every flow in one slice (no slicing).
    slice_id: int = 0
    # --- UE-side logical-channel prioritisation (uplink only) -------------
    # In the uplink the gNB grants a transport block and the *UE* decides how
    # to fill it (TS 38.321 sec 5.4.3.1), using the prioritised bit rate and
    # bucket size duration the network configured over RRC. The gNB knows
    # these values -- it set them -- but not the UE's live token-bucket state.
    #
    # pbr_bps = 0 with a GBR contract means "use the GFBR", which is what an
    # operator would configure. A non-GBR flow with pbr_bps = 0 is served
    # only from the second LCP round, i.e. out of whatever the prioritised
    # round leaves behind.
    pbr_bps: float = 0.0
    bsd_ms: float = 100.0

    traffic_kind: str = "poisson"
    traffic_params: dict = field(default_factory=dict)

    def effective_pbr_bps(self) -> float:
        """Configured prioritised bit rate, defaulting a GBR flow to its GFBR."""
        if self.pbr_bps > 0.0:
            return float(self.pbr_bps)
        if self.flow_class == "GBR" and self.gfbr_bps > 0.0:
            return float(self.gfbr_bps)
        return 0.0
