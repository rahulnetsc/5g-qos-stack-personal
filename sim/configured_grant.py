"""Configured grants, Type 2 -- a MAC feature that runs AHEAD of every
scheduler. Build 2 of the pre-scheduler occupancy (`sim/pre_sched.py`).

WHAT IT IS FOR. Every uplink failure this evaluation traced -- the
cold-start lock-out (no BSR without a grant), a crumb resetting the deadline
clock of a heartbeat it did not carry, BSR desync, the 300 ms visit tail,
the per-slot DCI cap -- is a DYNAMIC-grant pathology on SMALL, PERIODIC,
DELAY-CRITICAL flows. A configured grant removes all five for such a flow
structurally: no SR, no BSR to wait for, no DCI, no ranking to lose. The
test plan's own section 12 names CG on the 5QI-1 bearer as the feature
that "structurally removes the entire GT-2 failure class".

THIS IS A LABELLED DIVERGENCE FROM THE DEPLOYED C, ON EVERY ARM. The
deployed gNB has no CG (the vendored `gNB_scheduler_ulsch.c` only parses
the CG-confirmation MAC CE). "Product + CG" is the comparison decided on
2026-09-14 (README section 8): every arm, the faithful ports included, is
measured with CG through one driver flag, and any arm with CG on is
labelled `+CG` in its name and in every table. The scheduler files stay the
port -- CG reaches them only as occupancy and as the UE's own transmission,
never as a scheduler mechanism (CLAUDE.md's SPS/CG invariant still holds
for `scheduler/`).

WHAT THE STANDARD FIXES (transcribed, cited) AND WHAT IS VENDOR.

  * TS 38.321 V16.22.0 / V18.10.0 sec 5.8.2: Type 2's grant is provided by PDCCH
    (activation / deactivation DCI, CS-RNTI) and stored as a configured
    uplink grant; RRC configures `periodicity`, `nrofHARQ-Processes` and
    `configuredGrantTimer`; the Nth occasion recurs every `periodicity`.
  * TS 38.331 V16.22.0 / V18.10.0 `ConfiguredGrantConfig.periodicity`: the allowed
    set per subcarrier spacing is transcribed below in
    `CG_PERIODICITY_N_BY_SCS_KHZ` -- never recalled, never derived.
  * TS 38.214 V16.17.0 / V18.10.0 sec 6.1.2.3: for Type 2 the time/frequency
    allocation and MCS come from the activation DCI; the occasion is a
    PUSCH like any other (same MCS/TBS determination).
  * TS 38.321 sec 5.4.3.1.3: a configured uplink grant whose MAC PDU would
    carry zero MAC SDUs (only a periodic/padding BSR) generates no PDU --
    the UE SKIPS the occasion. The PRBs are still reserved: the gNB
    scheduled the dynamic grants around them before it could know.
  * TS 38.321 sec 5.4.4 NOTE 2: "UL-SCH resources are considered available
    if the MAC entity has an active configured grant", and an SR is
    triggered for a Regular BSR only if no UL-SCH resource is available OR
    the available resources "do not meet the LCP mapping restrictions
    configured for the logical channel that triggered the BSR". So an
    active CG SUPPRESSES SR for every logical channel the CG may carry.
  * TS 38.321 sec 5.4.3.1.2: which logical channels a CG may carry is the
    LCP mapping restriction `allowedCG-List` (Type 2; `configuredGrantType1
    Allowed` is Type 1 only).
  * TS 38.321 sec 5.4.1: the HARQ process for an occasion is
    `floor(CURRENT_slot x 10 / (slotsPerFrame x periodicity)) mod
    nrofHARQ-Processes` -- i.e. consecutive occasions rotate through the
    configured processes.

  Vendor (this module's policy, every value CHOSEN and named as such):
  which flows get a CG, the period, the size, when to activate, resize and
  release. Nothing here reads UE-side state the gNB cannot see: eligibility
  comes from the QoS profile (5QI class, GFBR, PDB -- all signalled at
  bearer setup), activation from the first buffer-status report for the
  flow's LCG, sizing from the reported CQI.

THE UE-SIDE RESTRICTION IS A SWITCH, BECAUSE THE OAI UE DOES NOT IMPLEMENT
IT. The vendored `nr_ue_scheduler.c` (upstream 63f3fb5) applies no LCP
mapping restriction -- its own comment reads "LCP mapping restrictions --
TODO not implemented" -- so an OAI UE given a CG multiplexes EVERY logical
channel into it by priority, and per sec 5.4.4 the CG then suppresses SR
for every channel too. `CgConfig.lcp_restriction`:
    True  -- COTS / patched UE: only `allowedCG-List` channels ride the CG;
             other channels still trigger SR and use dynamic grants.
    False -- OAI UE today: the CG carries whatever the LCP puts in it and
             no channel on that UE triggers SR while the CG is active.
Both are measured; the port-back design needs the UE half
(`docs/plan-cg-and-config-scheduler-2026-09-14.md` sec 1.2).

POLICY (the vendor part), stated so a reader can see what was chosen:
  * ELIGIBLE: an uplink flow (not SRB) with a delay budget, in one of two
    forms the gNB can read off the bearer's QoS profile. A GBR flow
    qualifies when its contract implies one message per PDB no larger
    than `max_message_bytes` (`gfbr_bps x pdb_ms / 8000`) -- G3/G5's
    telemetry (300 B per 100 ms), not the 4 Mbps camera (75 kB per 150
    ms). A DELAY-class flow (5QI 1 in the parametric mix: PDB 100 ms, no
    GFBR) has no rate to size from, so its message size is taken from the
    gNB's OWN first buffer-status estimate for the flow's LCG at
    activation, and it activates only if that estimate is at most
    `max_message_bytes` -- a first report larger than that says "not a
    small periodic flow" and the decision waits for a later one.
    Best-effort (`PF`) flows never qualify.
  * PERIOD: the largest allowed periodicity (in slots) not above
    `pdb_slots x period_pdb_fraction`, preferring one that is a multiple
    of the TDD pattern length so every occasion lands on the same slot
    kind. `period_pdb_fraction = 0.5` is CHOSEN: the worst wait for a
    message is then half its PDB. At mu = 2 with PDB 100 ms that is 160
    slots (40 ms); the message period is 100 ms, so ~60 % of occasions
    are skipped empty, at ~2 PRB each.
  * SIZE: `(message_bytes + header_bytes) x (1 + size_margin)` bytes,
    converted to PRBs at the MCS the reported SNR selects on the occasion
    slot's symbol count; the TB is what those PRBs carry.
  * ACTIVATE: on the first slot the gNB's own estimate for the flow's
    LCG is positive (`bytes_reported > 0`) -- the activation DCI costs
    CCE and one M-6 cap slot on that slot; the first occasion is `k2`
    slots later on the first UL-capable slot.
  * RESIZE: if the reported-SNR MCS moves by `resize_mcs_delta` or more
    since the last (re)activation, or the gNB's estimate for the LCG at an
    occasion exceeds the TB (two messages queued where one was sized --
    a flow whose period is shorter than its PDB), re-activate with the
    larger size (a DCI, same cost), never above `max_message_bytes`.
    Measured before this rule: a 150 B report sized a 231 B TB for a flow
    arriving at 3 B/ms, and the queue drifted to a 60 ms median wait.
  * RELEASE: after `release_after_unused` consecutive occasions during
    whose whole period the gNB saw NO report for the flow's LCG (a
    deactivation DCI); re-activation follows the same rule as first
    activation. An occasion the UE skips because the dynamic path already
    emptied the queue does NOT count -- measured at N = 8, that policy
    churned 12 activations and 5 releases in 2 s while the flow was alive
    the whole time; "unused" and "quiet" are different questions.
    `configuredGrantTimer` is not modelled separately -- a failed
    occasion's TB retransmits through the ordinary dynamic HARQ path
    (CS-RNTI DCI, k2 later, TDD-aligned), which is what the timer exists
    to allow.
  * IN FLIGHT (Build 2c, 2026-09-15): a RESTRICTED occasion transmits
    unless bytes of ITS channel are already in an unresolved UL TB -- a
    pending CG TB of this configuration, or a dynamic TB whose stored LCP
    split holds some (`HarqProcessPool.ul_flow_in_flight`); an
    unrestricted occasion keeps the whole-UE rule, since its TB may carry
    any channel. Skipped occasions are `skipped_harq_pending`. Before 2c
    the whole UE was masked while ANY UL TB was pending, which cost 3 %
    of single-CG occasions and would have cost a second CG on the same
    robot most of its occasions.
  * ONE PUSCH PER SLOT (TS 38.214 sec 6.1): an occasion on a slot in
    which the UE already transmits a retry or another CG is skipped
    (`skipped_same_slot`), and a UE that transmits a CG PUSCH is hidden
    from the dynamic scheduler for that slot.

TRAFFIC DESCRIPTOR (Build 2d, 2026-09-15, arm label `+CGt`). The PERIOD
rule above is what a gNB that knows only the QoS profile can do, and it is
wasteful: for a 300 B / 100 ms heartbeat it picks 40 ms, so 2.5 occasions
per message, 75 % of them empty and 79 % of the reserved PRBs unused
(measured 2026-09-15, G5 N = 6), with a wait of up to one period for each
message. The standard's answer is to TELL the gNB the pattern: TSCAI from
the core at QoS-flow setup (burst arrival time, periodicity -- TS 38.300
sec 16.8.1, a Rel-16 NGAP input), or Rel-18 UE traffic info (`ul-TrafficInfo`,
TS 38.331 -- NOT available from a Rel-16 UE, so only the core route counts). With
`traffic_descriptor` on, a flow that declares a single periodic pattern
(`sim/traffic.py` periodic_control / condition_monitor: period, phase under
a sync_group, jitter clip) gets
  * PERIOD = the declared period in slots -- any integer up to the
    `periodicityExt` bound (TS 38.331, transcribed above), 400 slots for
    100 ms at mu = 2, not the nearest enumerated value;
  * PHASE = the declared arrival + jitter bound + `descriptor_margin_slots`,
    on an uplink slot, so one occasion follows each message;
  * ACTIVATION at setup, without waiting for a first report, since the
    descriptor arrives with the flow -- `setup_activations_per_slot` per
    slot, because each activation is a DCI on the cap.
Measured (G3 GT-2.2, 2026-09-15): occasions 400 -> 160, reserved PRBs
wasted 2 346 -> 266; used occasions 76 % (G5: 88 %), not 100 %, because on
a loaded robot the dynamic scheduler grants the UE before the occasion and
the UE's LCP multiplexes the channel into any grant -- as a real UE does
unless `allowedPHY-PriorityIndex` fences the channel off dynamic grants.
The occasion is the message's floor, not its only path.
Everything else (sizing, restriction, resize, release, multi-CG rules) is
unchanged, and a flow without a declared pattern keeps the PDB rule. This
is CONDITIONAL on the deployment -- free5GC's SMF and the OAI gNB carry no
TSCAI today, and the OAI UE reports no traffic info -- which is why it is
its own label rather than the `+CG` default: `+CG` is what an OAI + free5GC
system could do now, `+CGt` what a core that sends TSCAI would allow.

REL-16 BASELINE (2026-09-15). The OAI gNB and the COTS UE are Rel-16, so
every UE-side rule this module relies on was re-read in TS 38.321 V16.22.0,
38.331 V16.22.0 and 38.214 V16.17.0 by clause diff against the V18 editions
cited above (`docs/rel16-baseline-2026-09-15.md` sec 2): Type 2 activation
and release, `periodicityExt`, `allowedCG-List`, `harq-ProcID-Offset2` and
one process block per configuration (sec 5.4.1 NOTE 5), the SR-suppression
conditions of sec 5.4.5 and the phase-per-configuration recurrence of sec
5.8.2 are all Rel-16. What is NOT: multi-PUSCH CG (`nrofSlotsInCG-Period`),
UTO-UCI, `intraCG-Prioritization`, the refined BSR table, the Delay Status
Report. Rel-16 bounds that cap this module's knobs: `nrof_harq_processes`
<= 16 per UE in total, `repK` <= 8, `configuredGrantTimer` <= 64 periods,
12 configurations per BWP.

MORE THAN ONE CG ON A UE (Build 2b, 2026-09-15). One configuration per
eligible flow was always the model; what the probe of 2026-09-15 showed is
that two of them on one robot ALWAYS coincided -- both activated on the
same first BSR, so both took the same phase, and a period that divides
the other's (80 and 160 slots) then shares every occasion. Two rules from
the standard fix that, and both are the gNB's to choose:
  * PHASE: each configuration's phase is set by the gNB (Type 1
    `timeDomainOffset`; Type 2 the slot of the activated PUSCH, TS 38.321
    sec 5.8.2), so an activation is placed on the first uplink slot no
    other active configuration of the UE ever uses (`_free_phase`, an
    exact gcd test). Counted as `phase_deferred` / `phase_deferred_slots`;
    a collision accepted for want of a free phase is `phase_collisions`.
  * HARQ: each configuration owns a block of `nrof_harq_processes` UL
    process IDs (`nrofHARQ-Processes` + `harq-ProcID-Offset2`, TS 38.321
    sec 5.4.1, NOTE 5 no sharing), reserved in `HarqProcessPool` so a
    dynamic TB never takes them and a CG TB never takes a dynamic one;
    `dynamic_harq_min` IDs always stay dynamic and a configuration the
    budget cannot afford is refused (`refused_harq_budget`).
Neither rule reaches a run with at most one CG per UE: the phase test has
no `others`, and the pid choice is unobservable (verified byte-identical
on the 2026-09-15 reference runs).

WHAT THE DRIVER DOES WITH AN OCCASION (`sim/driver.py`, "CG" block):
the occasion's PRBs enter `Occupancy` whether or not the UE transmits; the
UE transmits iff a channel the CG may carry has data (the skip rule), and
only if none of its channel's bytes are in flight (IN FLIGHT above) and a
process of its own block is free (`cg_busy` otherwise); the UE's own LCP fills the TB from the allowed channels
(or all channels when the restriction is off); a BSR rides it if one is
pending (`BsrModel.on_ul_grant`); the outcome is drawn exactly as for a
dynamic TB; a failure retransmits through the existing retry loop.

Must not import the driver or any scheduler. Imports `scheduler.link` for
the MCS/PRB arithmetic (the same functions the port uses) and
`sim/pre_sched.py`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from scheduler.link import bits_per_prb_for_mcs, cce_aggregation_level, mcs_index_for_snr

from .cycle_clock import phase_offset_slots
from .pre_sched import Occupancy

__all__ = ["CgConfig", "CgOccasion", "CgSlotResult", "ConfiguredGrantModel",
           "CG_PERIODICITY_N_BY_SCS_KHZ", "CG_PERIODICITY_EXT_MAX_BY_SCS_KHZ",
           "cg_periodicities_slots"]

#: TS 38.331 V16.22.0 (identical in V18.10.0), `ConfiguredGrantConfig` field
#: description, "periodicity": "The following periodicities are supported depending on
#: the configured subcarrier spacing [symbols]" -- the `n` of `n*14`
#: symbols (one slot is 14 symbols with normal CP), transcribed from the
#: spec text. The 2- and 7-symbol entries are sub-slot and are not
#: expressible on this slot-granular grid, so they are omitted here.
CG_PERIODICITY_N_BY_SCS_KHZ: dict[int, tuple[int, ...]] = {
    15: (1, 2, 4, 5, 8, 10, 16, 20, 32, 40, 64, 80, 128, 160, 320, 640),
    30: (1, 2, 4, 5, 8, 10, 16, 20, 32, 40, 64, 80, 128, 160, 256, 320, 640, 1280),
    60: (1, 2, 4, 5, 8, 10, 16, 20, 32, 40, 64, 80, 128, 160, 256, 320, 512, 640, 1280, 2560),
    120: (1, 2, 4, 5, 8, 10, 16, 20, 32, 40, 64, 80, 128, 160, 256, 320, 512, 640, 1024, 1280, 2560, 5120),
}


#: TS 38.331 V16.22.0 (identical bounds in V18.10.0 up to 120 kHz),
#: `ConfiguredGrantConfig` field description,
#: "periodicityExt": "used to calculate the periodicity for UL transmission
#: without UL grant for type 1 and type 2 ... 15 kHz: periodicityExt*14,
#: where periodicityExt has a value between 1 and 640. 30 kHz: ... 1 and
#: 1280. 60 kHz with normal CP: ... 1 and 2560. 120 kHz: ... 1 and 5120."
#: So with the extension ANY integer number of slots up to this bound is a
#: lawful period -- the enumerated set above is only the pre-Rel-16 one.
CG_PERIODICITY_EXT_MAX_BY_SCS_KHZ: dict[int, int] = {15: 640, 30: 1280, 60: 2560, 120: 5120}


def cg_periodicities_slots(numerology: int) -> tuple[int, ...]:
    """Allowed CG periodicities in SLOTS at this numerology (n*14 symbols
    = n slots with normal CP)."""
    scs_khz = 15 * (2 ** numerology)
    try:
        return CG_PERIODICITY_N_BY_SCS_KHZ[scs_khz]
    except KeyError:
        raise ValueError(f"no transcribed CG periodicity set for {scs_khz} kHz "
                         f"(numerology {numerology})") from None


@dataclass
class CgConfig:
    """Driver-level knobs. Every default is a CHOSEN policy value (module
    docstring), not a deployed one -- the deployed system has no CG."""
    lcp_restriction: bool = True
    max_message_bytes: int = 1500
    period_pdb_fraction: float = 0.5
    header_bytes: int = 8
    size_margin: float = 0.25
    nrof_harq_processes: int = 2
    #: UL HARQ process IDs a UE keeps for dynamic grants whatever its CG
    #: count; a configuration that cannot be given its block is refused.
    dynamic_harq_min: int = 4
    release_after_unused: int = 8
    resize_mcs_delta: int = 2
    k2_slots: int = 2
    #: Build 2d: take period and phase from the flow's DECLARED traffic
    #: pattern -- what TSCAI (TS 38.300 sec 16.8.1, Rel-16) or Rel-18 UE traffic
    #: info would tell the gNB -- instead of the PDB rule. Conditional on
    #: the deployment (free5GC / OAI carry neither today): arm label `+CGt`.
    traffic_descriptor: bool = False
    #: Slots after the declared arrival (plus its jitter bound) before the
    #: occasion, so the data is in the UE's buffer when it fires.
    descriptor_margin_slots: int = 4
    #: Setup-time activations per slot (each is a DCI on the cap).
    setup_activations_per_slot: int = 2

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CgConfig":
        unknown = set(d) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown CgConfig keys {sorted(unknown)}")
        return cls(**d)

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass(frozen=True)
class CgOccasion:
    """One configured-grant occasion the driver must resolve this slot."""
    ue_id: int
    qfi: int                       # the flow whose contract sized the CG
    prbs: int
    tbs_bytes: int
    mcs: int
    snr_used_db: float
    #: The logical channels (qfis) the UE may put in this TB. None = every
    #: channel of the UE (the restriction switch is off).
    allowed_qfis: Optional[tuple[int, ...]]
    #: This configuration's reserved UL HARQ process IDs (Build 2b).
    harq_pids: tuple[int, ...] = ()


@dataclass
class CgSlotResult:
    occupancy: Occupancy
    occasions: list[CgOccasion] = field(default_factory=list)
    activated: list[tuple[int, int]] = field(default_factory=list)
    resized: list[tuple[int, int]] = field(default_factory=list)
    released: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class _CgState:
    ue_id: int
    qfi: int
    pdb_slots: int
    #: None until the first report sizes it (Delay-class flows).
    message_bytes: Optional[int]
    period_slots: int
    active: bool = False
    next_occasion: int = -1
    prbs: int = 0
    tbs_bytes: int = 0
    mcs: int = -1
    snr_used_db: float = math.nan
    unused_run: int = 0
    seen_report: bool = False      # any bytes_reported > 0 since the last occasion
    pending_release: bool = False
    # counters, per config
    occasions: int = 0
    used: int = 0
    skipped_empty: int = 0
    skipped_harq_pending: int = 0
    skipped_cg_busy: int = 0
    skipped_same_slot: int = 0      # the UE already transmits a PUSCH this slot
    invalid_slot: int = 0
    prb_reserved: int = 0
    prb_wasted: int = 0
    bytes_carried: int = 0
    activations: int = 0
    resizes: int = 0
    releases: int = 0
    # Build 2b: the configuration's UL HARQ process block, and the phase
    # packing counters (an activation moved off a slot another CG of the
    # same UE already uses; the slots it moved by; collisions accepted
    # because no free phase existed within one period).
    harq_pids: tuple[int, ...] = ()
    phase_deferred: int = 0
    phase_deferred_slots: int = 0
    phase_collisions: int = 0
    # Build 2d: the declared pattern (None = no descriptor, PDB rule).
    desc_period: Optional[int] = None
    desc_phase: int = 0
    desc_jitter_slots: int = 0
    ever_activated: bool = False


class ConfiguredGrantModel:
    """One CG per eligible uplink flow; see the module docstring for the
    policy and the spec clauses each rule comes from."""

    def __init__(self, flows, grid, cfg: Optional[CgConfig] = None, *,
                 ul_harq_capacity: int = 16) -> None:
        self.cfg = cfg or CgConfig()
        self._grid = grid
        self._pattern_len = len(grid.pattern)
        self._numerology = int(round(math.log2(0.001 / grid.slot_duration_s)))
        self._allowed = cg_periodicities_slots(self._numerology)
        try:
            self._max_period_ext = CG_PERIODICITY_EXT_MAX_BY_SCS_KHZ[15 * (2 ** self._numerology)]
        except KeyError:
            raise ValueError(f"no transcribed periodicityExt bound for numerology "
                             f"{self._numerology}") from None
        self._states: dict[tuple[int, int], _CgState] = {}
        for f in flows:
            if f.direction != "UL" or getattr(f, "is_srb", False):
                continue
            if f.pdb_ms <= 0:
                continue
            if f.flow_class == "GBR" and f.gfbr_bps > 0:
                message: Optional[int] = int(math.ceil(f.gfbr_bps * f.pdb_ms / 8000.0))
                if message > self.cfg.max_message_bytes:
                    continue
            elif f.flow_class == "Delay":
                message = None            # sized from the first report
            else:
                continue                  # best-effort: never
            pdb_slots = int(f.pdb_ms / (grid.slot_duration_s * 1000.0))
            desc = self._descriptor(f) if self.cfg.traffic_descriptor else None
            self._states[(f.ue_id, f.qfi)] = _CgState(
                ue_id=f.ue_id, qfi=f.qfi, pdb_slots=pdb_slots,
                message_bytes=message,
                period_slots=(desc[0] if desc else self._choose_period(pdb_slots)),
                desc_period=(desc[0] if desc else None),
                desc_phase=(desc[1] if desc else 0),
                desc_jitter_slots=(desc[2] if desc else 0))
        self._by_ue: dict[int, list[_CgState]] = {}
        for st in self._states.values():
            self._by_ue.setdefault(st.ue_id, []).append(st)
        # Build 2b: one block of `nrof_harq_processes` UL HARQ process IDs
        # per configuration, taken from the top of the UE's pool so the
        # low IDs stay dynamic (TS 38.321 sec 5.4.1: `nrofHARQ-Processes`
        # + `harq-ProcID-Offset2` per configuration, NOTE 5 no sharing).
        # A configuration the budget cannot afford is refused, not
        # squeezed: `dynamic_harq_min` IDs always remain for dynamic TBs.
        self.refused_harq_budget = 0
        block = max(1, int(self.cfg.nrof_harq_processes))
        for ue, sts in list(self._by_ue.items()):
            top, kept = int(ul_harq_capacity), []
            for st in sts:
                if top - block < int(self.cfg.dynamic_harq_min):
                    self.refused_harq_budget += 1
                    del self._states[(st.ue_id, st.qfi)]
                    continue
                st.harq_pids = tuple(range(top - block, top))
                top -= block
                kept.append(st)
            if kept:
                self._by_ue[ue] = kept
            else:
                del self._by_ue[ue]

    def harq_reservations(self) -> list[tuple[int, tuple[int, ...]]]:
        """(ue_id, pids) per configuration, for `HarqProcessPool.reserve_ul`."""
        return [(st.ue_id, st.harq_pids) for st in self._states.values()]

    def _free_phase(self, st: _CgState, first: int) -> int:
        """First uplink slot >= `first` on which none of this UE's other
        ACTIVE configurations ever has an occasion. Two periodic sequences
        with periods P and Q and phases a and b share a slot somewhere iff
        (a - b) % gcd(P, Q) == 0, so the test is exact, not a lookahead.
        The standard leaves each configuration's phase to the gNB (Type 1
        `timeDomainOffset`; Type 2 the activated PUSCH, TS 38.321 sec
        5.8.2), and a UE transmits one PUSCH per slot -- measured before
        this rule, two CGs on a robot coincided on every occasion because
        both activated on the same first report. Bounded by one period;
        if no free phase exists the collision is accepted and counted."""
        others = [o for o in self._by_ue.get(st.ue_id, ()) if o is not st and o.active]
        if not others:
            return first
        cand = first
        while cand < first + st.period_slots:
            if self._grid.slot_grid(cand).ul_symbols > 0 and not any(
                    (cand - o.next_occasion) % math.gcd(st.period_slots, o.period_slots) == 0
                    for o in others):
                if cand != first:
                    st.phase_deferred += 1
                    st.phase_deferred_slots += cand - first
                return cand
            cand += 1
        st.phase_collisions += 1
        return first

    # ------------------------------------------------------------ policy

    def _choose_period(self, pdb_slots: int) -> int:
        """Largest allowed periodicity <= pdb_slots x fraction, preferring a
        multiple of the TDD pattern length (every occasion then lands on
        the same slot kind); the smallest allowed value if none fits."""
        cap = max(1, int(pdb_slots * self.cfg.period_pdb_fraction))
        fits = [p for p in self._allowed if p <= cap]
        aligned = [p for p in fits if p % self._pattern_len == 0]
        if aligned:
            return max(aligned)
        if fits:
            return max(fits)
        return self._allowed[0]

    def _descriptor(self, f) -> Optional[tuple[int, int, int]]:
        """(period_slots, phase_slot, jitter_slots) from the flow's declared
        periodic pattern -- the same slot arithmetic as
        `sim/traffic.py::_gen_periodic_control` (truncating period; a phase
        only under a sync_group; the jitter bound is the clip), so the
        occasion is placed where the generator will put the data. None
        when the flow declares no single period, or a period beyond what
        `periodicityExt` can express at this numerology."""
        if getattr(f, "traffic_kind", None) not in ("periodic_control", "condition_monitor"):
            return None
        p = getattr(f, "traffic_params", None) or {}
        if "streams" in p or "period_ms" not in p:
            return None
        slot_s = self._grid.slot_duration_s
        period = max(1, int(float(p["period_ms"]) / 1000.0 / slot_s))
        if period > self._max_period_ext:
            return None
        phase = (phase_offset_slots(float(getattr(f, "phase_offset_ms", 0.0)), slot_s)
                 if getattr(f, "sync_group", None) is not None else 0)
        sigma = float(p.get("jitter_sigma_ms", 0.0))
        clip = p.get("jitter_clip_ms")
        clip_ms = float(clip) if clip is not None else 2.0 * sigma
        jitter = int(math.ceil(clip_ms / 1000.0 / slot_s)) if clip_ms > 0 else 0
        return period, phase % period, jitter

    def _descriptor_first_occasion(self, st: _CgState, slot_index: int) -> int:
        """The first slot >= now + k2 that is `margin + jitter` after a
        declared arrival, on an uplink slot. With a pattern-multiple period
        every later occasion keeps the same alignment."""
        target = st.desc_phase + st.desc_jitter_slots + int(self.cfg.descriptor_margin_slots)
        earliest = slot_index + int(self.cfg.k2_slots)
        if target < earliest:
            target += ((earliest - target + st.period_slots - 1) // st.period_slots) * st.period_slots
        return self._next_ul_slot(target)

    def _next_ul_slot(self, slot: int) -> int:
        """First slot >= `slot` whose kind carries uplink symbols. Same rule
        as `sim/driver.py::align_due_slot` for UL, kept local because this
        module must not import the driver."""
        for k in range(slot, slot + self._pattern_len + 1):
            if self._grid.slot_grid(k).ul_symbols > 0:
                return k
        raise ValueError(f"TDD pattern {self._grid.pattern!r} carries no uplink slot")

    def _size(self, st: _CgState, snr_db: float, ul_symbols: int) -> tuple[int, int, int]:
        """(prbs, tbs_bytes, mcs) for this flow at this reported SNR."""
        mcs = mcs_index_for_snr(snr_db)
        bits_per_rb, _ = bits_per_prb_for_mcs(mcs, symbols=ul_symbols)
        target = int(math.ceil((st.message_bytes + self.cfg.header_bytes)
                               * (1.0 + self.cfg.size_margin)))
        prbs = max(1, int(math.ceil(target * 8 / max(1, bits_per_rb))))
        tbs = (prbs * bits_per_rb) // 8
        return prbs, tbs, mcs

    # ------------------------------------------------------------ queries

    def eligible_flows(self) -> list[tuple[int, int]]:
        return sorted(self._states)

    def covers(self, ue_id: int, qfi: int) -> bool:
        """TS 38.321 sec 5.4.4: does an ACTIVE configured grant on this UE
        count as available UL-SCH for this logical channel? With the LCP
        restriction on, only the CG's own channel; off, every channel."""
        sts = self._by_ue.get(ue_id)
        if not sts:
            return False
        if not self.cfg.lcp_restriction:
            return any(s.active for s in sts)
        return any(s.active and s.qfi == qfi for s in sts)

    def allowed_qfis(self, ue_id: int, qfi: int) -> Optional[tuple[int, ...]]:
        return (qfi,) if self.cfg.lcp_restriction else None

    # ------------------------------------------------------------ per slot

    def step(self, slot_index: int, slot_grid, buffers, channel) -> CgSlotResult:
        """Activation / resize / release decisions and this slot's
        occasions. Occupancy carries every occasion's PRBs (reserved
        whether or not the UE transmits) and each DCI's CCE and cap slot."""
        occ = Occupancy()
        res = CgSlotResult(occupancy=occ)
        ul_symbols = int(slot_grid.ul_symbols)
        for key, st in self._states.items():
            ue, qfi = key
            if st.pending_release:
                # Deactivation DCI (TS 38.321 sec 5.8.2): a DCI, so CCE and a
                # cap slot, and the configured grant is cleared.
                snr = channel.get_reported_snr_db(ue)
                occ.cce += cce_aggregation_level(snr)
                occ.ue_counts["UL"] = occ.ue_counts.get("UL", 0) + 1
                st.active = False
                st.pending_release = False
                st.unused_run = 0
                st.releases += 1
                res.released.append(key)
                continue
            if not st.active:
                # Activate on the gNB's own evidence that this LCG has data --
                # or, with a descriptor and a contract-sized message, once at
                # setup, as a gNB holding TSCAI would (a few per slot: each
                # activation is a DCI on the cap). A re-activation after a
                # release waits for a report either way.
                reported = buffers.state(ue, qfi).bytes_reported
                at_setup = (st.desc_period is not None and st.message_bytes is not None
                            and not st.ever_activated
                            and occ.ue_counts.get("UL", 0) < int(self.cfg.setup_activations_per_slot))
                if reported <= 0 and not at_setup:
                    continue
                if st.message_bytes is None:
                    # Delay class: the first report sizes the CG, and a report
                    # too large for a small periodic flow defers the decision.
                    if reported > self.cfg.max_message_bytes:
                        continue
                    st.message_bytes = int(reported)
                snr = channel.get_reported_snr_db(ue)
                # The first occasion is k2 slots on, on a UL-capable slot; its
                # symbol count sizes the TB (all occasions share the kind
                # when the period is pattern-aligned).
                if st.desc_period is not None:
                    first = self._descriptor_first_occasion(st, slot_index)
                else:
                    first = self._next_ul_slot(slot_index + self.cfg.k2_slots)
                first = self._free_phase(st, first)
                sym = int(self._grid.slot_grid(first).ul_symbols)
                st.prbs, st.tbs_bytes, st.mcs = self._size(st, snr, sym)
                st.snr_used_db = snr
                st.next_occasion = first
                st.active = True
                st.ever_activated = True
                st.activations += 1
                occ.cce += cce_aggregation_level(snr)
                occ.ue_counts["UL"] = occ.ue_counts.get("UL", 0) + 1
                res.activated.append(key)
                continue
            if buffers.state(ue, qfi).bytes_reported > 0:
                st.seen_report = True
            if slot_index != st.next_occasion:
                continue
            st.next_occasion = slot_index + st.period_slots
            if ul_symbols <= 0:
                # TS 38.214 sec 6.1: an occasion on a slot the pattern gives
                # to downlink is not valid; nothing is transmitted or
                # reserved. Only reachable when the period is not a
                # multiple of the pattern length.
                st.invalid_slot += 1
                continue
            snr = channel.get_reported_snr_db(ue)
            mcs_now = mcs_index_for_snr(snr)
            reported = int(buffers.state(ue, qfi).bytes_reported)
            grow = (reported > st.tbs_bytes
                    and st.message_bytes is not None
                    and st.message_bytes < self.cfg.max_message_bytes)
            if grow:
                st.message_bytes = min(self.cfg.max_message_bytes, reported)
            if grow or abs(mcs_now - st.mcs) >= self.cfg.resize_mcs_delta:
                # Re-activation with a new allocation: a DCI on this slot.
                st.prbs, st.tbs_bytes, st.mcs = self._size(st, snr, ul_symbols)
                st.snr_used_db = snr
                st.resizes += 1
                occ.cce += cce_aggregation_level(snr)
                occ.ue_counts["UL"] = occ.ue_counts.get("UL", 0) + 1
                res.resized.append(key)
            st.occasions += 1
            st.prb_reserved += st.prbs
            occ.prbs_ul += st.prbs
            res.occasions.append(CgOccasion(
                ue_id=ue, qfi=qfi, prbs=st.prbs, tbs_bytes=st.tbs_bytes,
                mcs=st.mcs, snr_used_db=st.snr_used_db,
                allowed_qfis=self.allowed_qfis(ue, qfi), harq_pids=st.harq_pids))
        return res

    def note_occasion(self, ue_id: int, qfi: int, outcome: str,
                      bytes_carried: int = 0) -> None:
        """The driver reports what happened on an occasion: "used",
        "empty", "harq_pending", "same_slot" or "cg_busy". An unused occasion counts
        toward release only if the gNB saw no report for the LCG during the
        period that led to it."""
        st = self._states[(ue_id, qfi)]
        seen = st.seen_report
        st.seen_report = False
        if outcome == "used":
            st.used += 1
            st.bytes_carried += bytes_carried
            st.unused_run = 0
            return
        st.prb_wasted += st.prbs
        # Quiet, not merely unused: only a period in which the gNB saw no
        # report for this LCG counts toward release (docstring, RELEASE).
        st.unused_run = 0 if seen else st.unused_run + 1
        if outcome == "empty":
            st.skipped_empty += 1
        elif outcome == "harq_pending":
            st.skipped_harq_pending += 1
        elif outcome == "same_slot":
            st.skipped_same_slot += 1
        elif outcome == "cg_busy":
            st.skipped_cg_busy += 1
        else:
            raise ValueError(f"unknown CG occasion outcome {outcome!r}")
        if st.unused_run >= self.cfg.release_after_unused:
            st.pending_release = True

    # ------------------------------------------------------------ report

    def summary(self) -> dict[str, Any]:
        """Per-run counters, so a run where CG never fired is
        distinguishable from one where it was off (CLAUDE.md's
        unreachable-mechanism rule)."""
        keys = ("occasions", "used", "skipped_empty", "skipped_harq_pending",
                "skipped_same_slot", "skipped_cg_busy", "invalid_slot", "prb_reserved", "prb_wasted",
                "bytes_carried", "activations", "resizes", "releases",
                "phase_deferred", "phase_deferred_slots", "phase_collisions")
        total = {k: sum(getattr(s, k) for s in self._states.values()) for k in keys}
        per_flow = {
            f"ue{s.ue_id}_qfi{s.qfi}": {
                "period_slots": s.period_slots, "message_bytes": s.message_bytes,
                "prbs": s.prbs, "tbs_bytes": s.tbs_bytes, "mcs": s.mcs,
                "active_at_end": s.active, "harq_pids": list(s.harq_pids),
                "descriptor_period": s.desc_period, "descriptor_phase": s.desc_phase,
                **{k: getattr(s, k) for k in keys}}
            for s in self._states.values()}
        return {"config": self.cfg.to_dict(), "eligible_flows": len(self._states),
                "totals": total, "per_flow": per_flow,
                "refused_harq_budget": self.refused_harq_budget}
