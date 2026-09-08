"""4-step contention-based random access, ported from the deployed gNB and
UE MAC (Build 1, docs/builds-2026-09-08.md §2).

What is a PORT and what is CHOSEN is marked field by field on
`RandomAccessConfig`. The procedure's shape is OAI's:

  UE: `nr_ra_procedures.c` -- `config_preamble_index` (uniform over the CB
      preambles), `nr_ra_backoff_setting` (uniform in [0, BI) slots),
      `nr_rar_not_successful` / `nr_ra_contention_resolution_failed`
      (`preamble_tx_counter++`; failure at `preambleTransMax + 1`).
  gNB: `gNB_scheduler_RA.c` -- `nr_initiate_ra_proc` (one RA process per
      detected preamble: two UEs on one preamble share it -- a collision),
      `nr_generate_Msg2` (only inside `ra_ResponseWindow`, only at a Type-1
      CSS monitoring occasion, only if a Msg3 slot is feasible),
      `get_feasible_msg3_tda` (Msg3 at `Msg2 + k2 + delta_mu` on the first
      UL slot), `nr_get_Msg3alloc` (`max(8, min_grant_prb)` RBs, TBS >= 7),
      `start_ra_contention_resolution_timer` (`((idx+1)*8) << mu + 2*K2`
      slots from Msg2), `nr_schedule_RA` (timer expiry releases the process),
      `schedule_nr_prach` + `fill_vrb` (the RO's RBs are reserved in
      `vrb_map_UL` on EVERY occasion whether or not anyone transmits).

No PHY: preamble detection is deterministic absent a same-preamble
collision, and `powerRampingStep` is therefore inert. Stated, not hidden.

Timeline the port reproduces at mu=1 / DDDDDDDSUU (calibration log):
preamble 369.19 -> Msg2 370.10 -> Msg3 370.19 -> Msg4 ACK 371.17, 19 ms.

Must not import the driver or any scheduler. Consumes `sim/pre_sched.py`
and `scheduler/link.py` only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Optional

import numpy as np

from scheduler.link import (
    bits_per_prb, bits_per_prb_for_mcs, cce_aggregation_level, snr_threshold_for_mcs,
)
from .harq import draw_harq_outcome
from .pre_sched import Occupancy

# --- transcribed tables ------------------------------------------------------

@dataclass(frozen=True)
class PrachConfigRow:
    """One row of TS 38.211 Table 6.3.3.2-3 (FR1, unpaired), transcribed
    from `nr_mac_common.c:913+` (`table_6_3_3_2_3_prachConfig_Index`)
    column for column: format, x, y, subframe bitmap, start symbol, PRACH
    slots per subframe, time-domain occasions per slot, duration."""
    format: int
    x: int
    y: int
    sfn_bitmap: int
    start_symbol: int
    n_ra_slot: int
    n_t_slot: int
    duration: int


#: Only the deployed index is transcribed. `prach_row()` refuses any other,
#: so a scenario cannot silently run on a row nobody transcribed.
PRACH_TABLE_FR1_UNPAIRED: dict[int, PrachConfigRow] = {
    98: PrachConfigRow(format=0xA2, x=2, y=1, sfn_bitmap=512, start_symbol=0,
                       n_ra_slot=1, n_t_slot=3, duration=4),
}

#: `nr_mac_common.c:610-616`, `N_RA_RB[delta_f_RA_PRACH][delta_f_PUSCH]`
#: (TS 38.211 Table 6.3.3.2-1): rows 0..3 are 15/30/60/120 kHz PRACH SCS,
#: rows 4..5 the long formats; columns are the PUSCH SCS. -1 = invalid.
N_RA_RB: tuple[tuple[int, ...], ...] = (
    (12, 6, 3, -1, -1, -1),
    (24, 12, 6, -1, -1, -1),
    (-1, -1, 12, 6, -1, -1),
    (-1, -1, 24, 12, 3, 2),
    (6, 3, 2, -1, -1, -1),
    (24, 12, 6, -1, -1, -1),
)

#: TS 38.321 Table 7.2-1, transcribed from `nr_ue_procedures.c:64-79`
#: (`table_7_2_1`): backoff parameter value in ms by BI index.
BACKOFF_TABLE_7_2_1_MS: tuple[int, ...] = (
    5, 10, 20, 30, 40, 60, 80, 120, 160, 240, 320, 480, 960, 1920,
)

#: TS 38.214 Table 6.1.2.1.1-5, delta for the Msg3 slot: `abs_slot = slot +
#: k2 + mu_delta` (`get_feasible_msg3_tda`, `gNB_scheduler_RA.c:1019`).
#: Checked against the log: Msg2 370.10, k2 6, Msg3 370.19 => delta 3 at mu=1.
MSG3_DELTA_BY_MU: tuple[int, ...] = (2, 3, 4, 6)


def prach_row(index: int) -> PrachConfigRow:
    try:
        return PRACH_TABLE_FR1_UNPAIRED[index]
    except KeyError:
        raise ValueError(
            f"prach_ConfigurationIndex {index} is not transcribed; add its row "
            f"from nr_mac_common.c:913+ rather than reconstructing it"
        ) from None


def n_ra_rb(prach_scs_mu: int, pusch_mu: int) -> int:
    n = N_RA_RB[prach_scs_mu][pusch_mu]
    if n < 0:
        raise ValueError(f"no PRACH RB count for PRACH SCS index {prach_scs_mu} "
                         f"with PUSCH mu {pusch_mu} (TS 38.211 Table 6.3.3.2-1)")
    return n


def response_window_slots(mu: int) -> int:
    """`gnb_config.c:582`: `min(sl80, sl10 + mu)` on the enum, i.e. 10 slots
    doubled per numerology step, capped at 80 -- 20 slots (10 ms) at mu=1.
    Derived from the carrier, never a literal."""
    return min(80, 10 << mu)


def contention_resolution_timer_slots(mu: int, k2: int, idx: int = 7) -> int:
    """`start_ra_contention_resolution_timer`, `gNB_scheduler_RA.c:771-785`:
    `(((idx + 1) * 8) << scs) + 2 * K2`; idx 7 = sf64."""
    return (((idx + 1) * 8) << mu) + 2 * k2


# --- configuration ---------------------------------------------------------

@dataclass(frozen=True)
class RandomAccessConfig:
    """Every field names its provenance. PORT = the deployed value from the
    sibling conf whose log-printed values all match (`docs/builds-2026-09-08.md`
    §2.1); MEASURED = read off the calibration log; CHOSEN = ours, to be
    replaced by the capture the testbed was asked for."""
    prach_config_index: int = 98        # PORT
    msg1_fdm: int = 1                   # PORT (msg1_FDM = one)
    prach_scs_mu: int = 1               # PORT (msg1_SubcarrierSpacing = 30 kHz)
    cb_preambles: int = 64              # PORT (ssb_perRACH..CB_PreamblesPerSSB = one_n64)
    preamble_trans_max: int = 10        # PORT (preambleTransMax = n10)
    backoff_index: int = 0              # PORT (gNB sends BI = 0, `:583`)
    contention_resolution_idx: int = 7  # PORT (ra_ContentionResolutionTimer = sf64)
    min_grant_prb: int = 5              # PORT (NPRB 5 in the log; Msg3 = max(8, 5) RBs)
    msg3_k2_slots: int = 6              # PORT (min_rxtxtime 6; log "TDA index 0 ... k2 6")
    msg3_tbs_bytes: int = 7             # PORT (`nr_get_Msg3alloc`: TBS >= 7)
    msg4_bytes_setup: int = 157         # MEASURED (log: "Generate Msg4 ... payload 157 bytes")
    msg4_bytes_reestablish: int = 20    # CHOSEN (no RRCReestablishment in any log)
    msg2_css_period_ms: float = 5.0     # CHOSEN: Type-1 CSS occasions every 5 ms
    msg2_min_delay_slots: int = 2       # CHOSEN: preamble processing; with the period, reproduces 369.19 -> 370.10
    msg4_ready_delay_ms: float = 5.0    # CHOSEN: Msg3 decode + RRC building RRCSetup. Bounded below by the log: Msg3 370.19, ACK 371.17 => Msg4 no earlier than 371.9
    msg2_cce: int = 4                   # CHOSEN: RA-RNTI DCI in the common search space at AL 4
    msg4_k1_max: int = 8                # PORT (dl-DataToUL-ACK values 1..8; log Msg4 -> ACK 371.17)
    srb: bool = False                   # Build 1.2 switch

    @classmethod
    def deployed(cls) -> "RandomAccessConfig":
        return cls()

    def to_dict(self) -> dict:
        return asdict(self)


# --- the occasion rule -------------------------------------------------------

def ro_prbs_in_slot(cfg: RandomAccessConfig, slot_index: int, mu: int,
                    tdd_pattern: str) -> int:
    """PRBs the PRACH occasion reserves in this slot, 0 if none.

    Port of `get_nr_prach_sched_from_info` (TDD/FR1 branch,
    `nr_mac_common.c`) plus `schedule_nr_prach`'s `is_ul_slot` gate:

    - the frame must satisfy `frame % x == y`;
    - the subframe must be set in the row's bitmap;
    - for `config_index >= 67` with one PRACH slot per subframe at 30 kHz
      PRACH SCS, only the ODD 30-kHz slot of the subframe carries the
      occasion (`"no prach in even slots @ 30kHz for 1 prach per subframe"`);
    - the slot must be an uplink slot, or nothing is scheduled.

    The table is written in PRACH-SCS slots. A PUSCH slot at a higher
    numerology maps to the PRACH slot that contains it, so at mu=2 both
    60-kHz slots inside 30-kHz slot 19 carry the reservation -- the
    occasion spans 12 of the 14 30-kHz symbols, so reserving both whole
    60-kHz slots over-reserves by 2 symbols; stated. A PUSCH numerology
    below the PRACH SCS is not a built case and raises.
    """
    row = prach_row(cfg.prach_config_index)
    if mu < cfg.prach_scs_mu:
        raise NotImplementedError("PUSCH numerology below the PRACH SCS is not modelled")
    slots_per_frame = 10 << mu
    frame, slot = divmod(slot_index, slots_per_frame)
    if frame % row.x != row.y:
        return 0
    prach_slot = slot >> (mu - cfg.prach_scs_mu)
    subframe = prach_slot >> cfg.prach_scs_mu
    if not (row.sfn_bitmap >> subframe) & 1:
        return 0
    if cfg.prach_config_index >= 67 and cfg.prach_scs_mu == 1 and row.n_ra_slot <= 1:
        if prach_slot % 2 == 0:
            return 0
    if tdd_pattern[slot_index % len(tdd_pattern)] != "U":
        return 0
    return n_ra_rb(cfg.prach_scs_mu, mu) * cfg.msg1_fdm


# --- per-procedure state -------------------------------------------------------

_WAIT_RO, _BACKOFF, _WAIT_RAR, _WAIT_MSG3, _WAIT_MSG4, _DONE = (
    "wait_ro", "backoff", "wait_rar", "wait_msg3", "wait_msg4", "done")


@dataclass
class _UeProc:
    ue_id: int
    kind: str                      # "cold" | "reestablish" | "crnti"
    requested_slot: int
    state: str = _WAIT_RO
    earliest_slot: int = 0
    preamble_tx_counter: int = 0   # OAI: 1 after the first transmission
    preamble: int = -1
    first_preamble_slot: Optional[int] = None
    rar_deadline: Optional[int] = None
    gnb: Optional["_GnbProc"] = None


@dataclass
class _GnbProc:
    """One RA process per DETECTED preamble (`nr_initiate_ra_proc` keys on
    `preamble_index`); every UE that sent that preamble in that occasion
    shares it -- which is exactly what a collision is."""
    preamble: int
    ro_slot: int
    ues: list[_UeProc]
    state: str = "msg2"
    msg2_slot: Optional[int] = None
    msg3_slot: Optional[int] = None
    msg3_round: int = 0
    msg3_is_retx: bool = False
    msg4_slot: Optional[int] = None
    msg4_feedback_slot: Optional[int] = None
    msg4_round: int = 0
    cr_deadline: Optional[int] = None


@dataclass
class RaSlotResult:
    occupancy: Occupancy
    completed: dict[int, str] = field(default_factory=dict)   # ue_id -> kind
    failed: dict[int, str] = field(default_factory=dict)
    latency_slots: dict[int, int] = field(default_factory=dict)  # preamble -> resolved


class RandomAccessModel:
    """UE-side and gNB-side RA, stepped once per slot by the driver BEFORE
    `scheduler.allocate()`; returns the slot's pre-scheduler `Occupancy`.

    Two RNG streams of its own, per the standing rule: preamble choice and
    backoff (`seed ^ 0x52414348`, "RACH"); Msg3/Msg4 HARQ outcomes
    (`seed ^ 0x4D534733`, "MSG3"). Neither is the data plane's stream.
    """

    def __init__(self, cfg: RandomAccessConfig, *, numerology: int,
                 tdd_pattern: str, slot_duration_s: float, seed: int,
                 k1_slots: int, harq_round_max: int, harq_combining_mode: str) -> None:
        self.cfg = cfg
        self.mu = numerology
        self.pattern = tdd_pattern
        self.slot_s = slot_duration_s
        self.k1 = k1_slots
        self.harq_round_max = harq_round_max
        self.harq_mode = harq_combining_mode
        self.window = response_window_slots(numerology)
        self.cr_slots = contention_resolution_timer_slots(
            numerology, cfg.msg3_k2_slots, cfg.contention_resolution_idx)
        self.delta = MSG3_DELTA_BY_MU[numerology]
        self.css_period = max(1, round((cfg.msg2_css_period_ms / 1000.0) / slot_duration_s))
        bi_ms = BACKOFF_TABLE_7_2_1_MS[cfg.backoff_index]
        self.backoff_limit_slots = max(1, round((bi_ms / 1000.0) / slot_duration_s))
        self.msg3_prbs = max(8, cfg.min_grant_prb)
        self.msg4_ready_slots = max(1, round((cfg.msg4_ready_delay_ms / 1000.0) / slot_duration_s))
        self._rng = np.random.default_rng(seed ^ 0x52414348)
        self._harq_rng = np.random.default_rng(seed ^ 0x4D534733)
        self._procs: dict[int, _UeProc] = {}
        self._gnb: list[_GnbProc] = []
        # Counters -- every one asserted against the scenario's schedule by
        # the campaigns, never against "non-zero".
        self.counters: dict[str, int] = {
            "ra_requested": 0, "ra_preambles_tx": 0, "ra_collisions": 0,
            "ra_rar_misses": 0, "ra_msg3_failures": 0, "ra_msg4_failures": 0,
            "ra_cr_timeouts": 0, "ra_completed": 0, "ra_failed": 0,
            "ra_cancelled": 0, "ra_ro_slots": 0,
        }
        self.latencies_slots: list[int] = []        # first preamble -> resolved
        self.total_slots: list[int] = []            # request -> resolved
        # Per KIND, because the same UE can run a cold RA and then, once
        # connected, a C-RNTI one from sr-TransMax -- and a campaign that
        # counts "RA completions" against "scheduled attaches" must not fold
        # the second into the first (found on the first smoke: TwoTier, 10
        # completions for 5 attaches).
        self.by_kind: dict[str, dict[str, int]] = {
            k: {"requested": 0, "completed": 0, "failed": 0}
            for k in ("cold", "reestablish", "crnti")}

    # -- requests ------------------------------------------------------------

    def request(self, ue_id: int, kind: str, slot_index: int) -> None:
        """Start (or restart) a procedure for a UE. A restart cancels the
        running one -- T300/T301 expiry in the RRC re-initiates access."""
        if kind not in ("cold", "reestablish", "crnti"):
            raise ValueError(f"unknown RA kind {kind!r}")
        if ue_id in self._procs:
            self.cancel(ue_id)
        self._procs[ue_id] = _UeProc(ue_id=ue_id, kind=kind, requested_slot=slot_index,
                                     earliest_slot=slot_index + 1)
        self.counters["ra_requested"] += 1
        self.by_kind[kind]["requested"] += 1

    def cancel(self, ue_id: int) -> None:
        p = self._procs.pop(ue_id, None)
        if p is None:
            return
        self.counters["ra_cancelled"] += 1
        if p.gnb is not None:
            p.gnb.ues = [u for u in p.gnb.ues if u is not p]
            if not p.gnb.ues:
                self._gnb = [g for g in self._gnb if g is not p.gnb]

    def active(self, ue_id: int) -> bool:
        return ue_id in self._procs

    # -- helpers ----------------------------------------------------------------

    def _kind(self, slot: int) -> str:
        return self.pattern[slot % len(self.pattern)]

    def _next_ul_slot(self, start: int) -> int:
        s = start
        while self._kind(s) != "U":
            s += 1
        return s

    def _next_dl_slot(self, start: int) -> int:
        s = start
        while self._kind(s) == "U":
            s += 1
        return s

    def _has_ul_symbols(self, slot: int) -> bool:
        return self._kind(slot) != "D"

    def _msg4_schedule(self, start: int) -> tuple[int, int]:
        """First slot with DL symbols >= start for which a slot with UL
        symbols exists within k1 in [k1_slots, msg4_k1_max]; feedback at the
        earliest such slot. Reproduces the log's Msg4 -> ACK 371.17 on the
        deployed pattern and is immediate on the sim's DSUUU."""
        s = start
        while True:
            if self._kind(s) != "U":
                for k1 in range(self.k1, self.cfg.msg4_k1_max + 1):
                    if self._has_ul_symbols(s + k1):
                        return s, s + k1
            s += 1

    def _backoff(self, p: _UeProc, slot: int) -> None:
        # `nr_ra_backoff_setting`: uniform in [0, RA_backoff_limit) slots.
        p.state = _BACKOFF
        p.earliest_slot = slot + int(self._rng.integers(0, self.backoff_limit_slots))
        p.gnb = None

    def _preamble_failed(self, p: _UeProc, slot: int, res: RaSlotResult) -> None:
        """`nr_rar_not_successful` / `nr_ra_contention_resolution_failed`:
        the counter has already been incremented at transmission; failure is
        declared when it would exceed preambleTransMax."""
        if p.preamble_tx_counter >= self.cfg.preamble_trans_max:
            p.state = _DONE
            self._procs.pop(p.ue_id, None)
            self.counters["ra_failed"] += 1
            self.by_kind[p.kind]["failed"] += 1
            res.failed[p.ue_id] = p.kind
        else:
            self._backoff(p, slot)

    def _complete(self, p: _UeProc, slot: int, res: RaSlotResult) -> None:
        p.state = _DONE
        self._procs.pop(p.ue_id, None)
        self.counters["ra_completed"] += 1
        self.by_kind[p.kind]["completed"] += 1
        res.completed[p.ue_id] = p.kind
        lat = slot - (p.first_preamble_slot if p.first_preamble_slot is not None else slot)
        res.latency_slots[p.ue_id] = lat
        self.latencies_slots.append(lat)
        self.total_slots.append(slot - p.requested_slot)

    # -- the step ----------------------------------------------------------------

    def step(self, slot_index: int, slot_grid, channel) -> RaSlotResult:
        occ = Occupancy()
        res = RaSlotResult(occupancy=occ)
        # (1) PRACH occasion: reserved on EVERY occasion (`schedule_nr_prach`),
        # transmitted on by whichever UEs are waiting for one.
        ro_prbs = ro_prbs_in_slot(self.cfg, slot_index, self.mu, self.pattern)
        if ro_prbs:
            self.counters["ra_ro_slots"] += 1
            occ.prbs_ul += ro_prbs
            by_preamble: dict[int, list[_UeProc]] = {}
            for p in list(self._procs.values()):
                if p.state == _BACKOFF and slot_index >= p.earliest_slot:
                    p.state = _WAIT_RO
                if p.state == _WAIT_RO and slot_index >= p.earliest_slot:
                    p.preamble = int(self._rng.integers(0, self.cfg.cb_preambles))
                    p.preamble_tx_counter += 1
                    if p.first_preamble_slot is None:
                        p.first_preamble_slot = slot_index
                    p.state = _WAIT_RAR
                    p.rar_deadline = slot_index + self.window
                    self.counters["ra_preambles_tx"] += 1
                    by_preamble.setdefault(p.preamble, []).append(p)
            for preamble, ues in by_preamble.items():
                g = _GnbProc(preamble=preamble, ro_slot=slot_index, ues=ues)
                for p in ues:
                    p.gnb = g
                self._gnb.append(g)
                if len(ues) > 1:
                    self.counters["ra_collisions"] += 1
        else:
            for p in self._procs.values():
                if p.state == _BACKOFF and slot_index >= p.earliest_slot:
                    p.state = _WAIT_RO

        # (2) gNB-side processes.
        for g in list(self._gnb):
            if not g.ues:
                self._gnb.remove(g)
                continue
            # Contention-resolution timer runs from Msg2 to the Msg4 ACK.
            if g.cr_deadline is not None and slot_index >= g.cr_deadline:
                self.counters["ra_cr_timeouts"] += 1
                for p in list(g.ues):
                    self._preamble_failed(p, slot_index, res)
                self._gnb.remove(g)
                continue
            if g.state == "msg2":
                in_window = slot_index <= g.ro_slot + self.window
                if not in_window:
                    # RAR never sent: every UE's window expires.
                    self.counters["ra_rar_misses"] += len(g.ues)
                    for p in list(g.ues):
                        self._preamble_failed(p, slot_index, res)
                    self._gnb.remove(g)
                    continue
                if (slot_index % self.css_period == 0
                        and slot_index >= g.ro_slot + self.cfg.msg2_min_delay_slots
                        and slot_grid.dl_symbols > 0):
                    msg3 = self._next_ul_slot(slot_index + self.cfg.msg3_k2_slots + self.delta)
                    g.msg2_slot = slot_index
                    g.msg3_slot = msg3
                    g.state = "msg3"
                    g.cr_deadline = slot_index + self.cr_slots
                    # RAR PDU: BI subheader + per RAPID (subheader 1 + RAR 7)
                    # at MCS 0 for the RA-RNTI broadcast.
                    rar_bytes = 1 + 8 * len(g.ues)
                    bpp, _ = bits_per_prb_for_mcs(0, slot_grid.dl_symbols)
                    occ.prbs_dl += max(1, math.ceil(rar_bytes * 8 / max(1, bpp)))
                    occ.cce += self.cfg.msg2_cce
                    for p in g.ues:
                        p.state = _WAIT_MSG3
            elif g.state == "msg3" and slot_index == g.msg3_slot:
                occ.prbs_ul += self.msg3_prbs
                if g.msg3_is_retx:
                    occ.cce += cce_aggregation_level(
                        min(channel.get_reported_snr_db(p.ue_id) for p in g.ues))
                if len(g.ues) > 1:
                    ok = False   # two UEs on one PUSCH grant: neither decodes
                else:
                    ue = g.ues[0].ue_id
                    ok = draw_harq_outcome(
                        self._harq_rng, channel.get_snr_db(ue), snr_threshold_for_mcs(0),
                        g.msg3_round, self.harq_mode, slot_grid.ul_symbols)
                if ok:
                    p = g.ues[0]
                    if p.kind == "crnti":
                        # Msg3 carries the C-RNTI MAC CE; contention is resolved
                        # by the gNB addressing that C-RNTI -- no Msg4.
                        self._complete(p, slot_index, res)
                        self._gnb.remove(g)
                    else:
                        g.state = "msg4"
                        g.msg4_slot, g.msg4_feedback_slot = self._msg4_schedule(
                            self._next_dl_slot(slot_index + self.msg4_ready_slots))
                        p.state = _WAIT_MSG4
                else:
                    self.counters["ra_msg3_failures"] += 1
                    g.msg3_round += 1
                    # gNB_scheduler_ulsch.c:802-809: released once
                    # msg3_round reaches harq_round_max - 1, else round++ and retx.
                    if g.msg3_round < self.harq_round_max:
                        g.msg3_slot = self._next_ul_slot(
                            slot_index + self.cfg.msg3_k2_slots + self.delta)
                        g.msg3_is_retx = True
                    else:
                        g.state = "dead"   # released at the CR timer, as the C does
            elif g.state == "msg4" and slot_index == g.msg4_slot:
                p = g.ues[0]
                nbytes = (self.cfg.msg4_bytes_setup if p.kind == "cold"
                          else self.cfg.msg4_bytes_reestablish)
                snr = channel.get_reported_snr_db(p.ue_id)
                bpp, _ = bits_per_prb(snr, slot_grid.dl_symbols)
                occ.prbs_dl += max(1, math.ceil(nbytes * 8 / max(1, bpp)))
                occ.cce += cce_aggregation_level(snr)
                g.state = "msg4_ack"
            elif g.state == "msg4_ack" and slot_index == g.msg4_feedback_slot:
                p = g.ues[0]
                ok = draw_harq_outcome(
                    self._harq_rng, channel.get_snr_db(p.ue_id),
                    channel.get_reported_snr_db(p.ue_id), g.msg4_round, self.harq_mode,
                    slot_grid.dl_symbols if slot_grid.dl_symbols > 0 else 14)
                if ok:
                    self._complete(p, slot_index, res)
                    self._gnb.remove(g)
                else:
                    self.counters["ra_msg4_failures"] += 1
                    g.msg4_round += 1
                    if g.msg4_round < self.harq_round_max:
                        g.state = "msg4"
                        g.msg4_slot, g.msg4_feedback_slot = self._msg4_schedule(
                            self._next_dl_slot(slot_index + 1))
                    else:
                        g.state = "dead"

        # (3) UEs whose RAR window expired without a Msg2 (their process was
        # never created -- cannot happen here, since every preamble is
        # detected -- kept as the C's own second failure path for symmetry).
        for p in list(self._procs.values()):
            if p.state == _WAIT_RAR and p.rar_deadline is not None and slot_index > p.rar_deadline:
                self.counters["ra_rar_misses"] += 1
                self._preamble_failed(p, slot_index, res)
        return res

    # -- reporting -------------------------------------------------------------

    def summary(self) -> dict:
        lat_ms = sorted(l * self.slot_s * 1000.0 for l in self.latencies_slots)
        tot_ms = sorted(l * self.slot_s * 1000.0 for l in self.total_slots)

        def pct(xs, p):
            if not xs:
                return None
            return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]
        return {
            **self.counters,
            "by_kind": {k: dict(v) for k, v in self.by_kind.items()},
            "ra_active_at_end": len(self._procs),
            "ra_latency_ms": {"n": len(lat_ms), "p50": pct(lat_ms, .5), "p95": pct(lat_ms, .95),
                              "max": lat_ms[-1] if lat_ms else None},
            "ra_total_ms": {"n": len(tot_ms), "p50": pct(tot_ms, .5), "p95": pct(tot_ms, .95),
                            "max": tot_ms[-1] if tot_ms else None},
            "config": self.cfg.to_dict(),
            "derived": {"response_window_slots": self.window, "cr_timer_slots": self.cr_slots,
                        "msg3_delta": self.delta, "css_period_slots": self.css_period,
                        "backoff_limit_slots": self.backoff_limit_slots,
                        "msg3_prbs": self.msg3_prbs, "msg4_ready_slots": self.msg4_ready_slots},
        }
