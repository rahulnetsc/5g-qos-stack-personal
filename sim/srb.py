"""SRB1/SRB2 as flows, and the RRC/NAS dialogues that ride them (Build 1.2,
docs/builds-2026-09-08.md §2.8).

The deployed gNB gives every UE SRB1 and SRB2 on LCG 0
(`get_SRB_RLC_BearerConfig(..., logicalChannelGroup=0)`, priority 1 for SRB1,
`nr_radio_config.c:3865`; SRB2 priority 3, TS 38.331 §9.2.1 default), and
both comparators read that backlog: the reservation branch as its TOP tier
in both directions (`gNB_scheduler_ulsch.c:2167-2176`, `_dlsch.c:830-842`),
the two-tier branch as eligibility and bytes only (`update_ul_qos_priority`
matches `lcid = lcg + 3`, which LCG 0 never satisfies; `update_dlsch_buffer`
gates the QoS path on `lcid >= 4`).

What rides the SRBs is a REQUEST-RESPONSE CHAIN, not a rate: each step is
enqueued when the previous one has been delivered. Sizes are MEASURED where
the calibration log prints them and CHOSEN otherwise -- every step says
which -- and every step carries +8 B of L2 headers (PDCP 12-bit SN header
2 B, MAC-I 4 B since integrity is always on for SRBs, RLC AM 12-bit SN
header 2 B). Core-network turnarounds between NAS steps are 0 ms: CHOSEN, a
lower bound, and the first thing the requested capture will correct.

Nothing here reads a scheduler or the driver; the driver calls
`SrbDialogues.step()` once per slot after deliveries are known and feeds
completions to the join FSM. Must not import sim/driver.py.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable, Iterable

from scheduler.flow import LCG_SRB, FlowConfig

#: One qfi PER DIRECTION: sim/buffer.py keys a queue by (ue_id, qfi) with no
#: direction, so a bidirectional pair on one qfi would share a queue --
#: defects log #28/#30, the collision the flow-key sweep exists to catch.
#: And never -1: the driver uses qfi == -1 as its "UE-level uplink grant"
#: sentinel (HarqProcess.qfi, Allocation.ue_grant), and a real flow on that
#: value is indistinguishable from it -- found because the first UL step of
#: every re-establishment dialogue was granted 10,000 times and never
#: delivered.
SRB_QFI = {("SRB1", "UL"): -11, ("SRB1", "DL"): -13, ("SRB2", "UL"): -12, ("SRB2", "DL"): -14}
SRB1_UL_QFI, SRB1_DL_QFI = SRB_QFI[("SRB1", "UL")], SRB_QFI[("SRB1", "DL")]
SRB_PRIORITY = {"SRB1": 1, "SRB2": 3}
#: PDCP (2) + MAC-I (4) + RLC AM (2): TS 38.323 §6.2.2.1, §6.3.4 / TS 38.322 §6.2.2.4.
L2_OVERHEAD_BYTES = 8
#: No PDB exists for signalling; large enough that BufferModel.expire() never
#: evicts an RRC message, and excluded from every PDB-keyed tier by is_srb.
SRB_PDB_MS = 60_000.0
SRB_PBR_INFINITY_BPS = 1e12


@dataclass(frozen=True)
class DialogueStep:
    direction: str          # "UL" | "DL"
    rrc_bytes: int          # RRC PDU size before L2 headers
    name: str
    provenance: str         # "measured" | "chosen"

    @property
    def mac_bytes(self) -> int:
        return self.rrc_bytes + L2_OVERHEAD_BYTES


#: Cold attach after Msg4 (RRCSetup, itself modelled by sim/random_access.py).
#: Order and DL sizes from calibration-logs/twotier_startup_gnb.log:174-205;
#: RRCSetupComplete from the LCID-1 counter line ("RX 41 bytes") right after it.
ATTACH_DIALOGUE: tuple[DialogueStep, ...] = (
    DialogueStep("UL", 41, "RRCSetupComplete(+Registration Request)", "measured"),
    DialogueStep("DL", 42, "DLInformationTransfer", "measured"),
    DialogueStep("UL", 24, "ULInformationTransfer", "measured"),
    DialogueStep("DL", 21, "DLInformationTransfer", "measured"),
    DialogueStep("UL", 60, "ULInformationTransfer", "measured"),
    DialogueStep("DL", 3, "SecurityModeCommand", "measured"),
    DialogueStep("UL", 10, "SecurityModeComplete", "chosen"),
    DialogueStep("DL", 8, "UECapabilityEnquiry", "measured"),
    DialogueStep("UL", 300, "UECapabilityInformation", "chosen"),
    DialogueStep("DL", 53, "DLInformationTransfer(Registration Accept)", "measured"),
    DialogueStep("UL", 13, "ULInformationTransfer(Registration Complete)", "measured"),
    DialogueStep("UL", 35, "ULInformationTransfer(PDU Session Est. Request)", "measured"),
    DialogueStep("DL", 313, "RRCReconfiguration(+PDU Session Accept)", "measured"),
    DialogueStep("UL", 10, "RRCReconfigurationComplete", "chosen"),
)

#: After Msg4 = RRCReestablishment. No log evidence for any of it.
REESTABLISH_DIALOGUE: tuple[DialogueStep, ...] = (
    DialogueStep("UL", 10, "RRCReestablishmentComplete", "chosen"),
    DialogueStep("DL", 313, "RRCReconfiguration", "measured"),
    DialogueStep("UL", 10, "RRCReconfigurationComplete", "chosen"),
)

DIALOGUES = {"cold": ATTACH_DIALOGUE, "reestablish": REESTABLISH_DIALOGUE}


def srb_flows(ue_id: int) -> list[FlowConfig]:
    """SRB1 and SRB2, each as a UL and a DL flow, on LCG 0. `is_srb` keeps
    them out of DRB ordinals, QoS tiers, Tier-1 and every scorecard
    population; `traffic_kind="none"` means only a dialogue can enqueue."""
    out = []
    for (srb, direction), qfi in SRB_QFI.items():
        out.append(FlowConfig(
            ue_id=ue_id, qfi=qfi, direction=direction, flow_class="PF",
            pdb_ms=SRB_PDB_MS, priority_level=SRB_PRIORITY[srb], lcg=LCG_SRB,
            # PORT: SRBs are configured with prioritisedBitRate INFINITY and
            # bucketSizeDuration ms1000 (get_SRB_RLC_BearerConfig(1, 1,
            # bucketSizeDuration_ms1000, ...), nr_radio_config.c:3865; TS
            # 38.331). Without it the UE-side LCP's first round hands the
            # whole TB to a GBR bearer with tokens and an RRC message starves
            # behind it -- measured: 10,085 grants, zero SRB bytes delivered.
            # A large finite rate stands in for infinity (int(inf) overflows).
            pbr_bps=SRB_PBR_INFINITY_BPS, bsd_ms=1000.0,
            is_srb=True, traffic_kind="none", traffic_params={}))
    return out


def with_srb(scenario):
    """The scenario plus SRBs for every UE. Applied at the SCENARIO level so
    every consumer of `scenario.flows` -- traffic, metrics, the schedulers,
    `RunRecord.from_summary` -- sees the same flow list. Idempotent."""
    have = {(f.ue_id, f.qfi) for f in scenario.flows if getattr(f, "is_srb", False)}
    extra = [f for ue in scenario.ues for f in srb_flows(ue.ue_id) if (f.ue_id, f.qfi) not in have]
    if not extra:
        return scenario
    return dataclasses.replace(scenario, flows=list(scenario.flows) + extra)


def srb_flow_keys(flows: Iterable[FlowConfig]) -> frozenset[tuple[int, int]]:
    return frozenset((f.ue_id, f.qfi) for f in flows if getattr(f, "is_srb", False))


@dataclass
class _Active:
    ue_id: int
    kind: str
    steps: tuple[DialogueStep, ...]
    index: int = 0
    target_delivered: int = 0
    current_qfi: int = SRB1_UL_QFI
    started_slot: int = 0


@dataclass
class SrbDialogues:
    """Per-UE request-response chains. `enqueue(ue_id, qfi, mac_bytes, name)`
    is the driver's injection (buffer enqueue + metrics arrival, exactly
    what the G9 app handshake does); `delivered_cum(ue_id, qfi)` reads the
    buffer's cumulative delivered bytes. A step is complete when that
    counter reaches the target recorded at enqueue -- bytes, not "any
    delivery", so a fragmented RRCReconfiguration cannot advance early."""
    enqueue: Callable[[int, int, int, str], None]
    delivered_cum: Callable[[int, int], int]
    _active: dict[int, _Active] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: {
        "srb_dialogues_started": 0, "srb_dialogues_completed": 0,
        "srb_dialogues_cancelled": 0, "srb_steps_sent": 0,
        "srb_bytes_ul": 0, "srb_bytes_dl": 0})
    by_kind: dict[str, dict[str, int]] = field(default_factory=lambda: {
        k: {"started": 0, "completed": 0} for k in DIALOGUES})
    durations_slots: list[int] = field(default_factory=list)

    def start(self, ue_id: int, kind: str, slot_index: int) -> None:
        if kind not in DIALOGUES:
            raise ValueError(f"no dialogue for RA kind {kind!r}")
        if ue_id in self._active:
            self.cancel(ue_id)
        a = _Active(ue_id=ue_id, kind=kind, steps=DIALOGUES[kind], started_slot=slot_index)
        self._active[ue_id] = a
        self.counters["srb_dialogues_started"] += 1
        self.by_kind[kind]["started"] += 1
        self._send(a)

    def cancel(self, ue_id: int) -> None:
        if self._active.pop(ue_id, None) is not None:
            self.counters["srb_dialogues_cancelled"] += 1

    def active(self, ue_id: int) -> bool:
        return ue_id in self._active

    def _send(self, a: _Active) -> None:
        s = a.steps[a.index]
        qfi = SRB1_UL_QFI if s.direction == "UL" else SRB1_DL_QFI
        a.current_qfi = qfi
        a.target_delivered = self.delivered_cum(a.ue_id, qfi) + s.mac_bytes
        self.enqueue(a.ue_id, qfi, s.mac_bytes, s.name)
        self.counters["srb_steps_sent"] += 1
        self.counters["srb_bytes_ul" if s.direction == "UL" else "srb_bytes_dl"] += s.mac_bytes

    def step(self, slot_index: int) -> dict[int, str]:
        """Advance every chain whose current step has been delivered; return
        {ue_id: kind} for the chains that finished this slot."""
        done: dict[int, str] = {}
        for ue_id, a in list(self._active.items()):
            if self.delivered_cum(ue_id, a.current_qfi) < a.target_delivered:
                continue
            a.index += 1
            if a.index >= len(a.steps):
                del self._active[ue_id]
                self.counters["srb_dialogues_completed"] += 1
                self.by_kind[a.kind]["completed"] += 1
                self.durations_slots.append(slot_index - a.started_slot)
                done[ue_id] = a.kind
            else:
                self._send(a)
        return done

    def summary(self, slot_duration_s: float) -> dict:
        d = sorted(x * slot_duration_s * 1000.0 for x in self.durations_slots)
        p = lambda q: (d[min(len(d) - 1, int(round(q * (len(d) - 1))))] if d else None)
        return {**self.counters, "by_kind": {k: dict(v) for k, v in self.by_kind.items()},
                "srb_active_at_end": len(self._active),
                "srb_dialogue_ms": {"n": len(d), "p50": p(.5), "p95": p(.95), "max": d[-1] if d else None},
                "steps": {k: [(s.direction, s.mac_bytes, s.name, s.provenance) for s in v]
                          for k, v in DIALOGUES.items()}}
