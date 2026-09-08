"""FlowConfig -- the scheduler's per-flow QoS / traffic descriptor.

One FlowConfig is the scheduler's view of a single uni-directional flow
(a DRB / logical channel): its QoS class and contract, its scheduling
priority, and enough of a traffic descriptor for Tier-1 to estimate the
offered load. In an OAI deployment this is populated from the 5QI / QoS
profile of each bearer.
"""

from dataclasses import dataclass, field
from typing import Iterable, Literal

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
# PRIMARY SOURCE, 2026-09-04: transcribed byte-for-byte from the DEPLOYED
# gNB's own table -- oai-branches/mac_rrc_dl_handler.c:43-48, `qos_fiveqi[26]`
# / `qos_priority[26]` / `qos_pdb_ms[26]`, itself cited to 3GPP TS 23.501
# Table 5.7.4-1.
#
# THIS SUPERSEDES the previous provenance (ShareTechnote cross-checked
# against Devopedia, with spec re-verification flagged open) rather than
# adding to it, and it is BETTER than the spec PDF for this project's
# purpose: it is the table the gNB we deploy against actually reads. A
# divergence between this file and that one means results do not transfer to
# hardware, and nothing before this could have detected it.
#
# VERIFICATION RESULT. Every PDB the repo already had MATCHES the deployed
# table exactly -- so the secondary transcription was correct and this is
# confirmation, not correction. Three PRIORITIES were absent (5QI 79, 80,
# 86); `priority_for_5qi` silently returned DEFAULT_PRIORITY_LEVEL=100 for
# them, i.e. the lowest priority in the system, and 5QI 86 is a 5 ms
# delay-critical class. Latent, not active: no scenario uses those three.
# Added below.
#
# ALL 26 IMPORTED, and the decision is recorded rather than assumed. Cost of
# importing is zero -- these are lookup tables consulted on demand, not
# mechanisms with unreachable code paths, so an unused ENTRY misleads nobody
# (unlike the never-passed UlAccessModel knobs, which are a different shape).
# The benefit is that `priority_for_5qi` can no longer silently return 100
# for a standardised class. `pdb_for_5qi` already RAISES on an unlisted 5QI,
# which is the loud half; this makes the priority half loud too by removing
# the gaps that made the fallback reachable.
FIVE_QI_PRIORITY: dict[int, int] = {
    # GBR
    1: 20,    # conversational voice
    2: 40,    # conversational video (live)
    3: 30,    # real-time gaming / V2X
    4: 50,    # non-conversational buffered video
    65: 7,    # mission-critical push-to-talk voice
    66: 20,   # non-mission-critical push-to-talk voice
    67: 15,   # mission-critical video
    71: 56,   # live uplink streaming
    72: 56,   # live uplink streaming
    73: 56,   # live uplink streaming
    74: 56,   # live uplink streaming
    76: 56,   # live uplink streaming
    # non-GBR
    5: 10,    # IMS signalling
    6: 60,    # buffered video (TCP)
    7: 70,    # voice / live video
    8: 80,    # buffered video (TCP)
    9: 90,    # default bearer
    69: 5,    # mission-critical delay-sensitive signalling
    70: 55,   # mission-critical data
    # delay-critical GBR
    79: 65,   # V2X messages          -- ADDED 2026-09-04 (was absent -> 100)
    80: 68,   # low-latency eMBB      -- ADDED 2026-09-04 (was absent -> 100)
    82: 19,   # discrete automation
    83: 22,   # discrete automation
    84: 24,   # intelligent transport
    85: 21,   # electricity distribution
    86: 18,   # V2X messages          -- ADDED 2026-09-04 (was absent -> 100)
}
# `qos_per_exp[26]` (packet error rate, stored as the exponent of 10^-n) is
# in the deployed table at mac_rrc_dl_handler.c:48 and is DELIBERATELY NOT
# CARRIED HERE. This repo has no packet-error-rate model: nothing would read
# it, so importing it would create exactly the shape CLAUDE.md's twelve-
# instance table records -- a value present, plausible and consulted by
# nothing, indistinguishable from one that is used. If a PER model is ever
# built, import it in THAT commit, where a caller exists to make it
# observable.
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
# FIVE_QI_PRIORITY on all 13 values the two share.
#
# ── PROVENANCE UPGRADED 2026-09-04 -- THE OPEN RE-VERIFICATION IS CLOSED ──
# The secondary sources above are SUPERSEDED, not supplemented. The deployed
# gNB's own table is now in-repo at oai-branches/mac_rrc_dl_handler.c:43-48
# (`qos_fiveqi[26]` / `qos_pdb_ms[26]`), cited there to TS 23.501
# Table 5.7.4-1, and every PDB below was checked against it.
#
# RESULT: EVERY VALUE MATCHES. The secondary transcription was correct, so
# this is CONFIRMATION rather than correction -- worth stating plainly,
# because a wrong PDB here would have silently mis-scored every guarantee
# bound to it (M01's bound, M02's violation rate, M05/M06's frame budgets)
# with no check anywhere able to notice.
#
# And this is BETTER than the spec PDF for this project's purpose, which is
# why it closes the item rather than deferring it again: it is the table the
# gNB we deploy against actually reads. A divergence between this file and
# that one would mean results do not transfer to hardware, and until this
# file was in the repo nothing could have detected such a divergence.
#
# The companion FIVE_QI_PRIORITY check was NOT clean -- three entries were
# absent (5QI 79, 80, 86), silently falling back to DEFAULT_PRIORITY_LEVEL.
# See that table's own note.
#
# PDB is a property of the QoS CLASS, so it is derived here rather than
# authored per flow. GFBR is NOT: it is a per-bearer negotiated value and
# stays scenario-authored (see FlowConfig.gfbr_bps). LCG is neither: it is
# the DEPLOYED rule LCG = DRB ID (assign_deployed_lcgs below). Those three
# different provenances are why every device profile states each field's source.
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
# table above in __post_init__. (lcg is the one field __post_init__ does
# NOT resolve: its value depends on the UE's OTHER flows -- see
# assign_deployed_lcgs.)
DERIVE_PDB_FROM_5QI = -1.0

# Same convention for priority: -1 means "resolve from the 5QI table in
# __post_init__". A real 5QI priority is always >= 1, so -1 is unambiguous.
DERIVE_PRIORITY_FROM_5QI = -1


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
# The deployed LCG rule, ported from the RRC rather than invented here. All
# three facts are from the full checkout (Oai_Ran_QoS_Supported_MultiDRB,
# branch twotier), none from the vendored subset:
#
#   nr_radio_config.c:3781-3785      long lcg_id = drbId; if (lcg_id > 7) lcg_id = 7;
#   rrc_gNB_radio_bearers.c:498-505  every MAX_QOS_FLOWS_PER_DRB_* == 1 (one flow per DRB)
#   rrc_gNB_radio_bearers.c:248-263  drb_id = lowest free integer from 1
#
# So LCG is a per-UE BEARER ORDINAL -- the k-th QoS flow a UE sets up is
# DRB k and sits on LCG min(k, 7) -- and it is NOT a function of 5QI. LCG 0
# is never a DRB: it is the SRB group (get_SRB_RLC_BearerConfig(...,
# logicalChannelGroup=0)), which is what both comparators' `has_srb`
# predicate keys on (gNB_scheduler_ulsch.c:2167-2176). The FIVE_QI_LCG
# table this replaced put 5QI 1/3 DATA on LCG 0, so wiring that predicate
# would have read telemetry as control (M-5,
# docs/mac-fidelity-audit-2026-09-07.md; docs/builds-2026-09-08.md §1).
LCG_SRB = 0
LCG_MAX_DRB = 7
# A FlowConfig whose lcg is still this after construction has not been
# through assign_deployed_lcgs. Consumers that index a per-LCG array refuse
# it, because Python would accept [-1] silently -- as [7].
LCG_UNASSIGNED = -1


def lcg_for_drb(drb_id: int) -> int:
    """nr_radio_config.c:3781-3785 verbatim: LCG = DRB ID, capped at 7. The
    ONE place the rule is written; assign_deployed_lcgs and sim/fleet.py's
    provenance table both call it rather than restating min(k, 7)."""
    if drb_id < 1:
        raise ValueError(f"DRB IDs start at 1 (rrc_gNB_radio_bearers.c:251); got {drb_id}")
    return min(drb_id, LCG_MAX_DRB)


def assign_deployed_lcgs(flows: Iterable["FlowConfig"]) -> None:
    """Assign LCG = DRB ID to every flow still at LCG_UNASSIGNED, in place.

    DRB IDs are per-UE setup ordinals from 1; the simulator's proxy for
    setup order is the flow list's order within the UE (a stated
    assumption, docs/builds-2026-09-08.md §1.3 -- nothing in the repo can
    verify it). A DL and a UL flow with the same (ue_id, qfi) are one
    deployed QoS flow and share a DRB. An explicit lcg is kept but still
    consumes an ordinal, because the deployed RRC creates a DRB for every
    flow regardless of how the simulator labels it.

    Idempotent: a second call over already-assigned flows changes nothing,
    which is what lets ScenarioConfig.__post_init__ run again under
    dataclasses.replace (G12's permute_flows) without re-deriving -- so a
    permutation control stays a declaration-order control and does not
    silently become an LCG-assignment control.
    """
    next_drb: dict[int, int] = {}
    drb_of: dict[tuple[int, int], int] = {}
    for f in flows:
        if getattr(f, "is_srb", False):
            continue          # an SRB is not a DRB: no ordinal, LCG 0 already
        key = (f.ue_id, f.qfi)
        if key not in drb_of:
            next_drb[f.ue_id] = next_drb.get(f.ue_id, 0) + 1
            drb_of[key] = next_drb[f.ue_id]
        if f.lcg == LCG_UNASSIGNED:
            f.lcg = lcg_for_drb(drb_of[key])


def ul_lcg_bytes(flows, ue_id: int, buffers) -> dict[int, int]:
    """The gNB's per-LCG UL estimate for one UE, keyed by LCG.

    ONE reader for a value three call sites need (reservation's
    ``has_srb``/``_ul_lcg0_estimate``, two-tier's ``srb_floor``/``cp_floor``)
    -- extracted before the second copy existed rather than after the third.
    ``BsrModel.broadcast`` writes each flow's state with the aggregate for
    THAT flow's LCG, so the first flow found on an LCG carries the whole LCG
    (the same first-flow-found-wins rule both schedulers' QoS loops use); a
    second flow on the same LCG would restate it, not add to it.

    ``buffers`` is duck-typed (any ``BufferView``) so this module keeps its
    no-simulator-imports rule.
    """
    out: dict[int, int] = {}
    for f in flows:
        if f.ue_id != ue_id or f.direction != "UL" or f.lcg in out:
            continue
        out[f.lcg] = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
    return out


def require_assigned_lcgs(flows: Iterable["FlowConfig"], consumer: str) -> None:
    """Raise if any flow is still LCG_UNASSIGNED. Every consumer that
    indexes a per-LCG array calls this, so a flow list that bypassed
    ScenarioConfig fails loudly instead of indexing [-1]."""
    for f in flows:
        if f.lcg == LCG_UNASSIGNED:
            raise ValueError(
                f"{consumer}: flow (ue={f.ue_id}, qfi={f.qfi}, {f.direction}) has "
                f"no LCG -- flows must pass through ScenarioConfig (or "
                f"assign_deployed_lcgs) before reaching a consumer"
            )


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
    # Read by scheduler/tier1.py::_weight_from_priority (the Delay-class
    # threshold), two_tier.py's UL urgency weight, and sim/ue_lcp.py's
    # uplink LCP sort.
    #
    # DERIVE_PRIORITY_FROM_5QI (-1) means "use priority_for_5qi(qfi)" --
    # __post_init__ resolves it, exactly as
    # pdb_ms == DERIVE_PDB_FROM_5QI already does, so an explicit priority
    # always wins and every other FlowConfig gets its standardised value
    # regardless of how it was constructed.
    #
    # WHY THIS IS THE DEFAULT AND 100 IS NOT (2026-09-03). The old default
    # was the literal 100, i.e. DEFAULT_PRIORITY_LEVEL -- the fallback for a
    # 5QI the standard does not list. sim/config_loader.py resolved from the
    # table, so the three published-study scenarios got a real spread, but
    # sim/parametric.py and sim/fleet.py construct FlowConfig directly and
    # passed nothing: EVERY flow in EVERY WP9, G9, G11 and G12 scenario tied
    # at 100. Tier-1's Delay class (p <= 20) was therefore never selected,
    # two_tier's urgency priority weight clamped to its floor for every flow,
    # and ue_lcp.py's stable sort on a constant key made the uplink split
    # declaration-ordered. regression_corpus.py could not see it: its cases
    # all come from scripts/scheduler_study.py, which never calls those two
    # builders. Deriving here rather than at each call site is what stops the
    # next builder from reintroducing it.
    priority_level: int = DERIVE_PRIORITY_FROM_5QI
    # This flow's logical channel group, 0-7 (TS 38.321: BSR aggregates to
    # 8 LCGs). LCG_UNASSIGNED until ScenarioConfig resolves it by the
    # deployed rule LCG = DRB ID (assign_deployed_lcgs). NOT resolved in
    # __post_init__: the ordinal depends on the UE's other flows, which a
    # single FlowConfig cannot see. An explicit lcg always wins -- and is a
    # divergence from the deployment, since the RRC never lets a flow choose.
    lcg: int = LCG_UNASSIGNED
    # Network-slice id. Tier-1 can give each slice a guaranteed share of PRB
    # capacity; default 0 puts every flow in one slice (no slicing).
    slice_id: int = 0
    # Build 1.2: SRB1/SRB2 (sim/srb.py). Not a DRB -- no ordinal, LCG 0 by
    # construction, excluded from every QoS tier, from Tier-1 and from every
    # scorecard population. Validated in __post_init__.
    is_srb: bool = False
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
        if self.priority_level == DERIVE_PRIORITY_FROM_5QI:
            # priority_for_5qi falls back to DEFAULT_PRIORITY_LEVEL for an
            # unlisted 5QI, so deriving never raises -- unlike pdb_for_5qi,
            # which does, because inventing a *budget* is a scenario-
            # authoring error while a neutral priority is a real default.
            self.priority_level = priority_for_5qi(self.qfi)
        if self.lcg != LCG_UNASSIGNED and not (0 <= self.lcg < LCG_COUNT):
            raise ValueError(f"lcg={self.lcg} outside 0..{LCG_COUNT - 1} (qfi={self.qfi})")
        if self.is_srb and (self.lcg != LCG_SRB or self.qfi >= 0):
            raise ValueError("an SRB flow sits on LCG_SRB with a negative qfi (sim/srb.py)")

    def effective_pbr_bps(self) -> float:
        """Configured prioritised bit rate, defaulting a GBR flow to its GFBR."""
        if self.pbr_bps > 0.0:
            return float(self.pbr_bps)
        if self.flow_class == "GBR" and self.gfbr_bps > 0.0:
            return float(self.gfbr_bps)
        return 0.0
