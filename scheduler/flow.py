"""FlowConfig -- the scheduler's per-flow QoS / traffic descriptor.

One FlowConfig is the scheduler's view of a single uni-directional flow
(a DRB / logical channel): its QoS class and contract, its scheduling
priority, and enough of a traffic descriptor for Tier-1 to estimate the
offered load. In an OAI deployment this is populated from the 5QI / QoS
profile of each bearer.
"""

from dataclasses import dataclass, field
from typing import Literal

# Standardised 5QI -> scheduling priority level, 3GPP TS 23.501 Table 5.7.4-1.
# Lower value = higher priority. Only the 5QIs these scenarios use are listed;
# an unlisted 5QI falls back to DEFAULT_PRIORITY_LEVEL.
#
# This matters more than it looks -- for UPLINK. sim/ue_lcp.py's UE-side LCP
# genuinely orders a UE's flows by priority_level (`sorted(ue_flows, key=
# lambda f: f.priority_level)`), so if two flows on one UE share a priority
# the sort is decided by whatever order they happen to be listed in -- a
# scenario file reordering would silently change results there. Deriving the
# priority from the 5QI makes that order a property of the QoS profile
# instead, not scenario-declaration accident.
#
# SCOPING CORRECTION, found scoping Phase 2 reservation commit 6: the
# original wording here said "the MAC logical-channel multiplexer" without
# qualification, as if this applied to both directions. It does not.
# scheduler/reservation.py's DL LCP fill (gNB_scheduler_dlsch.c:1394-1463,
# confirmed by reading the loop directly -- no sort/qsort anywhere near
# lc_config in that file) fills DRBs in existing declared order, NOT by
# priority -- `qc->priority` there is a log-only field, never read by the
# fill or the inter-UE comparator. So priority_level's declaration-order-
# reordering fragility this comment warns about is real for UL and does NOT
# exist for reservation's DL: a DL scenario's flow declaration order IS the
# fill order, unguarded, by design. See docs/oai-port-map.md row 31 and
# README.md sec8 for the standing consequence.
FIVE_QI_PRIORITY: dict[int, int] = {
    1: 20,    # GBR, conversational voice
    2: 40,    # GBR, conversational video (live)
    3: 30,    # GBR, real-time gaming / V2X
    4: 50,    # GBR, non-conversational buffered video
    5: 10,    # non-GBR, IMS signalling
    6: 60,    # non-GBR, buffered video (TCP)
    7: 70,    # non-GBR, voice / live video
    8: 80,    # non-GBR, buffered video (TCP)
    9: 90,    # non-GBR, default bearer
    82: 19,   # delay-critical GBR, discrete automation
    83: 22,   # delay-critical GBR, discrete automation
    84: 24,   # delay-critical GBR, intelligent transport
    85: 21,   # delay-critical GBR, electricity distribution
}
DEFAULT_PRIORITY_LEVEL = 100


def priority_for_5qi(qfi: int) -> int:
    """Standardised priority for a 5QI, or the neutral default if unlisted."""
    return FIVE_QI_PRIORITY.get(int(qfi), DEFAULT_PRIORITY_LEVEL)


# Standardised 5QI -> Packet Delay Budget, TS 23.501 Table 5.7.4-1.
#
# PROVENANCE, stated precisely because the standing rule requires it and
# because this table was NOT read from the spec PDF. Transcribed from
# ShareTechnote's rendering of Table 5.7.4-1
# (https://www.sharetechnote.com/html/5G/5G_5QI.html), cross-checked
# against Devopedia (https://devopedia.org/5g-quality-of-service), which
# independently states 5QI 1 = 100 ms, 5QI 3 = 50 ms and 5QI 82 = 10 ms --
# all three agree. The strongest corroboration is internal: that source's
# *priority* column matches this file's own independently-transcribed
# FIVE_QI_PRIORITY on all 13 values the two share. **Re-verify against the
# actual spec text if it becomes available**, as WP6 did for TR 38.901's
# path-loss tables.
#
# PDB is a property of the QoS CLASS, so it is derived here rather than
# authored per flow. GFBR is NOT: it is a per-bearer negotiated value and
# stays scenario-authored (see FlowConfig.gfbr_bps). FIVE_QI_LCG remains an
# invented mapping, as its own comment already says. Those three different
# provenances are why every device profile states each field's source.
FIVE_QI_PDB_MS: dict[int, float] = {
    1: 100.0,    # GBR, conversational voice
    2: 150.0,    # GBR, conversational video (live)
    3: 50.0,     # GBR, real-time gaming / V2X
    4: 300.0,    # GBR, non-conversational buffered video
    5: 100.0,    # non-GBR, IMS signalling
    6: 300.0,    # non-GBR, buffered video (TCP)
    7: 100.0,    # non-GBR, voice / live video / gaming
    8: 300.0,    # non-GBR, buffered video (TCP)
    9: 300.0,    # non-GBR, default bearer
    79: 50.0,    # non-GBR, V2X messages
    80: 10.0,    # non-GBR, low-latency eMBB
    82: 10.0,    # delay-critical GBR, discrete automation (MDBV 255 B)
    83: 10.0,    # delay-critical GBR, discrete automation (MDBV 1354 B)
    84: 30.0,    # delay-critical GBR, intelligent transport
    85: 5.0,     # delay-critical GBR, electricity distribution
    86: 5.0,     # delay-critical GBR, V2X advanced driving
}

# Sentinel: FlowConfig.pdb_ms == DERIVE_PDB_FROM_5QI resolves from the
# table above in __post_init__, exactly as lcg == -1 resolves via
# lcg_for_5qi.
DERIVE_PDB_FROM_5QI = -1.0


def pdb_for_5qi(qfi: int) -> float:
    """Standardised PDB (ms) for a 5QI. Raises for an unlisted 5QI rather
    than inventing a default: a flow asking for a *standardised* budget on a
    class the standard does not define is a scenario-authoring error, and a
    silent fallback would encode the author's opinion as if it were the
    spec's -- the exact failure this table exists to prevent."""
    try:
        return FIVE_QI_PDB_MS[int(qfi)]
    except KeyError:
        raise ValueError(
            f"5QI {qfi} has no standardised PDB in TS 23.501 Table 5.7.4-1; "
            f"set pdb_ms explicitly and record why"
        ) from None


LCG_COUNT = 8

# Default 5QI -> logical channel group mapping for uplink flows (WP3, BSR
# realism). Unlike FIVE_QI_PRIORITY (a 3GPP-standardised table), LCG
# assignment is NOT standardised as a function of 5QI -- a real deployment
# configures each logical channel's LCG via RRC, an operator/gNB policy
# choice. This table is a simulator default only, grouping 5QIs by
# QoS-class family so that same-class bearers plausibly land on one LCG
# and different-class bearers don't; an explicit `lcg` in a scenario's flow
# config always overrides it.
FIVE_QI_LCG: dict[int, int] = {
    1: 0, 3: 0,                   # GBR: voice / real-time gaming-V2X
    2: 1,                         # GBR: conversational video
    4: 2,                         # GBR: non-conversational buffered video
    82: 3, 83: 3, 84: 3, 85: 3,   # delay-critical GBR: discrete automation / ITS
    5: 4, 7: 4,                   # non-GBR: signalling / low-latency voice-video
    6: 5, 8: 5,                   # non-GBR: buffered video (TCP)
    9: 6,                         # non-GBR: default bearer / best effort
}
DEFAULT_LCG = 7


def lcg_for_5qi(qfi: int) -> int:
    """Default LCG for a 5QI, or the neutral fallback if unlisted."""
    return FIVE_QI_LCG.get(int(qfi), DEFAULT_LCG)


@dataclass
class FlowConfig:
    ue_id: int
    qfi: int
    direction: Literal["DL", "UL"]
    flow_class: Literal["PF", "GBR", "Delay"] = "PF"
    # Packet Delay Budget, ms. The 100.0 default is RETAINED DELIBERATELY
    # rather than switched to 5QI-derivation: the regression corpus is
    # frozen (CLAUDE.md), and deriving would move every flow whose 5QI's
    # standardised PDB differs from 100 -- a 5QI-9 flow would jump 100 ->
    # 300 ms and shift every record. New work passes
    # DERIVE_PDB_FROM_5QI to get the standardised value; see pdb_for_5qi.
    pdb_ms: float = 100.0
    gfbr_bps: float = 0.0
    # Maximum flow bit rate (MFBR), 3GPP QoS-profile convention: the
    # reservation scheduler's GBR-deficit target-spread caps at 2x a
    # per-slot burst derived from this (gNB_scheduler_{ul,dl}sch.c's
    # gbr_{ul,dl}_max, Phase 2 commit 3). 0 = "not configured" -- the
    # cap then falls back to its own floor (2x the per-slot obligation
    # derived from gfbr_bps), matching the C's behaviour when a QoS
    # profile has no MFBR set, not an invented default.
    mfbr_bps: float = 0.0
    # Scheduling priority, 3GPP 5QI convention: lower value = higher priority.
    # Used to tier SPS reservations and the MAC logical-channel multiplexer.
    # Default is a single neutral level; set per-flow once the workload is
    # mapped to standardised 5QIs.
    priority_level: int = 100
    # This flow's logical channel group, 0-7 (TS 38.321: BSR aggregates to
    # 8 LCGs). -1 means "use lcg_for_5qi(qfi)" -- __post_init__ resolves it,
    # so any explicit lcg always wins and every other FlowConfig still gets
    # a valid default regardless of how it was constructed.
    lcg: int = -1
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
    # [OPEN] TS 22.104 communication-service-availability grace period beyond
    # pdb_ms (WP7 M14, docs/wp7-plan.md Decision #3) -- distinct from pdb_ms
    # itself and from config/metric_panel.yml's t_live_s/survival_miss_n,
    # which are different concepts despite sounding adjacent. Default 0
    # collapses M14 to "delivered within max latency"; no factory-relevant
    # value exists on disk to pick instead. M14 (WP7 commit 8) reports this
    # value alongside the availability figure on every result, never a bare
    # number, so a 0.0 default is never misread as a full CSA measurement.
    survival_time_ms: float = 0.0

    # WP7 commit 9: shared production-line clock (sim/cycle_clock.py) for
    # correlated bursts -- the "thundering herd" mechanism, docs/p5g-sim-
    # plan.md sec9. None = doesn't participate (every existing flow,
    # unaffected). Flows sharing the same sync_group value all anchor to
    # slot 0 (like every other periodic kind here already does -- a
    # sync_group is about synchrony BETWEEN its members, not the absolute
    # phase of the whole run), then each fires phase_offset_ms after that
    # shared tick, jittered by phase_jitter_ms (reusing sim/traffic.py's
    # _clipped_gaussian_jitter_ms, not a second jitter mechanism).
    # phase_jitter_ms defaults to 0.0 -- no ground truth for a nonzero
    # value, README sec8 [OPEN].
    #
    # SCOPE (found in WP7's end-of-WP review, undocumented until now): only
    # sim/traffic.py's periodic_control/condition_monitor kind actually
    # reads sync_group/phase_offset_ms/phase_jitter_ms
    # (TrafficModel._gen_periodic_control). Setting these on any other kind
    # (xr_video, deterministic, poisson, adaptive, video_frame,
    # aperiodic_event, machine_vision) is a silent no-op -- no error, just
    # unsynchronised as if sync_group were never set. Extending this to
    # xr_video (e.g. a synchronised camera fleet) is plausible future work,
    # not yet built.
    sync_group: int | None = None
    phase_offset_ms: float = 0.0
    phase_jitter_ms: float = 0.0

    # WP7 commit 9: fault-injection rate multiplier (README sec6, GT-4.3/
    # T6a/b/d: 2x/3x/5x/10x on a named flow, mid-run -- checked against
    # docs/IA_P5G_Guarantee_Validation_Suite.md's actual T6 table). Scales
    # every generated arrival's byte count from aggressor_trigger_ms
    # onward, a sustained step, not a bounded burst. Covers a misbehaving/
    # misconfigured asset's SUSTAINED rate increase (T6a/b/d, GT-4.3) --
    # does NOT cover T6c (a "line rate" burst, not a multiple of nominal)
    # or T6e (an RF-outage recovery, a channel-side event, not a traffic-
    # generation one); those need different tooling, not this knob.
    # 1.0 = inert, every existing flow's default.
    #
    # KNOWN GAP with xr_video (found in WP7's end-of-WP review, untested --
    # no scenario combines the two): the multiplier scales EACH fragment's
    # bytes independently, after sim/traffic.py's _gen_xr_video has already
    # fragmented the frame to fit fragment_bytes. A scaled fragment can end
    # up LARGER than the configured fragment_bytes, silently breaking the
    # "grounded in a real physical constant" MTU-cap invariant that
    # generator's own docstring claims. Not fixed here (fixing it properly
    # means scaling avg_bytes before fragmentation, which breaks this
    # field's "uniform post-processing regardless of kind" design and needs
    # its own decision). If building GT-4.3's camera-at-2x-MFBR test on an
    # xr_video flow, scale traffic_params["avg_bytes"] directly instead of
    # using aggressor_multiplier until this is resolved.
    aggressor_multiplier: float = 1.0
    aggressor_trigger_ms: float = 0.0

    traffic_kind: str = "poisson"
    traffic_params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.pdb_ms == DERIVE_PDB_FROM_5QI:
            self.pdb_ms = pdb_for_5qi(self.qfi)
        if self.lcg == -1:
            self.lcg = lcg_for_5qi(self.qfi)
        if not (0 <= self.lcg < LCG_COUNT):
            raise ValueError(f"lcg={self.lcg} outside 0..{LCG_COUNT - 1} (qfi={self.qfi})")

    def effective_pbr_bps(self) -> float:
        """Configured prioritised bit rate, defaulting a GBR flow to its GFBR."""
        if self.pbr_bps > 0.0:
            return float(self.pbr_bps)
        if self.flow_class == "GBR" and self.gfbr_bps > 0.0:
            return float(self.gfbr_bps)
        return 0.0
