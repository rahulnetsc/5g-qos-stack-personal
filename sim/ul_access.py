"""Uplink access chain (WP4): SR -> grant -> BSR -> grant.

Ground truth: `oai-branches/two-tier/gNB_scheduler_uci.c` (`nr_sr_reporting`,
L1274-1360 -- schedules the recurring PUCCH SR occasion per UE; and
`handle_nr_uci_pucch_0_1`'s `sched_ctrl->SR |= true` at L959 -- the gNB
decoding a received positive SR) and `oai-branches/two-tier/
nr_ue_procedures.c` (`trigger_periodic_scheduling_request`, L2569-2611, and
`nr_ue_get_SR`, L2613-2661 -- the UE-side sr-TransMax counter, prohibit-timer
gate, and RA-fallback trigger). The SR *trigger* half (deciding a UE has
something to signal) is `nr_update_sr` /`schedule_RA_after_SR_failure`,
already vendored in `oai-branches/two-tier/nr_ue_scheduler.c:1190-1277` for
WP3. `sched_ctrl->SR = false` on grant is `gNB_scheduler_ulsch.c:2694`.

Timer constants (`calibration-logs/twotier_startup_gnb.log`, a real gNB
startup banner): `sr_ProhibitTimer 0`, `sr_TransMax 64`, `t300 400` (ms).
`sr_ProhibitTimer=0` is a real deployed value, not a placeholder -- per
`common/utils/nr/nr_common.c`'s `nr_timer_start`/`nr_timer_is_active`
(plain active-flag-plus-counter, no minimum-active-duration floor), a 0 ms
prohibit timer never actually blocks a retransmission. It's implemented
here generally (so it isn't dead code and can be swept), but at the real
deployed default it is a no-op -- see `docs/oai-port-map.md`'s worked trace
for a suppression example using an explicit non-zero illustrative value.

SR periodicity (`sr_period_slots`) has no ground truth anywhere -- not in
the calibration banner, not in either vendored or live OAI repo's config
for this deployment. It's a first-class parameter here, swept explicitly
by `scripts/scheduler_study.py`'s offered-load study rather than defaulted
silently, because it's a direct multiplier on the low-load latency WP4's
calibration target depends on (README §8).

Granularity: one SR state machine per UE, not per LCG/flow -- real
deployments commonly configure a single dynamic SR resource per UE, the
calibration target is UE-level round-trip time, and this repo's scenarios
have no per-flow SR-ID/RRC config to key a finer granularity off (a
judgment call, recorded in the WP4 commit).

RACH fallback: on sr-TransMax exhaustion, model only the timing
consequence (README §6 draws the line at full contention resolution) --
the UE is marked UL-ineligible for a fixed recovery delay drawn from the
RRC timer constants already in the calibration banner (`t300`, the
RRC-setup response timer), not a preamble-collision simulation.

Interaction with `sim/bsr.py`: this module does not touch
`BsrModel`/`BufferState` directly. It exposes `sr_report_floor(ue_id)`,
which `BsrModel.broadcast()` calls in place of WP3's cold-start/re-arm
probe (see that module's docstring) -- a small honest constant instead of
the probe's bypass-to-true-backlog, reported through the same
`bytes_reported` channel every scheduler already reads. This is what keeps
all four scheduler arms (PF, RoundRobin, Gradient, TwoTier) working
uniformly with zero scheduler-file changes: none of them need to learn a
new eligibility signal, because the signal arrives through the field they
already read.
"""

from dataclasses import dataclass

from scheduler.flow import FlowConfig

# Calibration banner value (calibration-logs/twotier_startup_gnb.log):
# sr_TransMax 64.
DEFAULT_SR_TRANS_MAX = 64
# Calibration banner value: sr_ProhibitTimer 0 -- a real deployed no-op,
# not a placeholder. See module docstring.
DEFAULT_SR_PROHIBIT_MS = 0.0
# Calibration banner value: t300 400 (ms) -- the RRC-setup response timer,
# used here as the fixed RACH-recovery delay (README §6: timing
# consequence only, not contention resolution).
DEFAULT_RACH_RECOVERY_MS = 400.0
# Small, honest, fixed report once an SR has been served by the gNB's
# flag -- sized to represent a real gNB's static minimum grant (README §7's
# `min_rb`/`nrmac->min_grant_prb` invariant: a fixed config floor, not
# computed from demonstrated need), not the true backlog (the difference
# from WP3's probe, which reported the true backlog -- a lie the gNB
# couldn't actually know). Matches this branch's own established "crumb"
# definition (README/CLAUDE.md known issues: grants <=150 bytes, averaging
# ~79 measured on hardware) rather than an arbitrary tiny value.
#
# This number matters more than it looks: every scheduler's own grant
# sizing caps *delivered* bytes at `min(bytes_reported, prb_capacity)`
# (e.g. `scheduler/two_tier.py`'s `tbs_bytes = min(ue_backlog, ...)`), so a
# too-small floor (a single byte was tried first) wastes almost the whole
# 1-PRB grant's real capacity delivering nothing, forcing a second full
# round trip for data a real min-grant-sized allocation would have carried
# directly. 150 bytes lets many small periodic messages complete in the
# SR-triggered grant itself, matching what a real static min-grant floor
# would actually do.
DEFAULT_SR_REPORT_FLOOR_BYTES = 150


@dataclass
class _UeSrState:
    pending: bool = False
    counter: int = 0
    prohibit_active: bool = False
    prohibit_deadline_slot: int = 0
    gnb_sr_flag: bool = False
    # Slot index at/after which RACH recovery completes; None when not in
    # recovery.
    rach_recovery_until: int | None = None


class UlAccessModel:
    """Per-UE SR state machine: no grant -> SR occasion on PUCCH ->
    sr-ProhibitTimer -> SR-to-grant latency -> BSR on that grant -> data
    grant. See module docstring for ground truth and design notes.
    """

    def __init__(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        sr_period_slots: int = 10,
        sr_offset_slots: int = 0,
        sr_prohibit_ms: float = DEFAULT_SR_PROHIBIT_MS,
        sr_trans_max: int = DEFAULT_SR_TRANS_MAX,
        rach_recovery_ms: float = DEFAULT_RACH_RECOVERY_MS,
        sr_report_floor_bytes: int = DEFAULT_SR_REPORT_FLOOR_BYTES,
    ) -> None:
        self._ue_flows: dict[int, list[FlowConfig]] = {}
        for f in flows:
            if f.direction != "UL":
                continue
            self._ue_flows.setdefault(f.ue_id, []).append(f)
        self._sr_period_slots = max(1, sr_period_slots)
        self._sr_offset_slots = sr_offset_slots % self._sr_period_slots
        self._prohibit_slots = max(0, round((sr_prohibit_ms / 1000.0) / slot_duration_s))
        self._trans_max = sr_trans_max
        self._rach_recovery_slots = max(1, round((rach_recovery_ms / 1000.0) / slot_duration_s))
        self._report_floor = sr_report_floor_bytes
        self._state: dict[int, _UeSrState] = {ue_id: _UeSrState() for ue_id in self._ue_flows}

    def reset_ue(self, ue_id: int) -> None:
        """WP-Join commit 7 (docs/wp-join-plan.md sec1.9): fresh per-UE SR
        state on radio reconnection. Unlike BsrModel's timers, every
        ``_UeSrState`` field defaults to its own "nothing pending, no
        timer running" value, so no slot-relative seeding is needed here
        -- ``prohibit_deadline_slot=0`` is inert whenever
        ``prohibit_active`` is False, which the fresh default already is.
        No-op for a UE with no UL flows at all."""
        if ue_id not in self._state:
            return
        self._state[ue_id] = _UeSrState()

    def on_arrivals(self, per_flow_arrived: dict[tuple[int, int], int], buffers) -> None:
        """SR trigger: new data arriving when this UE has no other way to
        signal it -- no standing grant (SR flag not already set), no SR
        already pending, and not mid-RACH-recovery. Mirrors `nr_update_sr`
        (`nr_ue_scheduler.c:1207-1277`) at UE granularity rather than
        per-logical-channel: this sim has no per-LCID SR-DelayTimer or
        configured-grant gate to port, so those two additional conditions
        in the ground truth are simplified away (a judgment call -- see
        `docs/oai-port-map.md`).

        Second trigger (WP9): a pending regular BSR with no UL-SCH resource
        available -- TS 38.321 sec5.4.4, and the condition retxBSR-Timer
        expiry itself sets. **This is a third divergence from
        `nr_update_sr`, and unlike the two simplifications above it was not
        conservative**: without it, a UL flow whose backlog never returns to
        zero can never raise another SR, and the empty->non-empty test below
        is the only other trigger. Combined with the `sched_ul_bytes` gate
        (`bytes_reported = max(0, estimated_ul_buffer - sched_ul_bytes)`)
        that is a permanent stall -- `sched_ul_bytes` resets only inside
        `BsrModel.on_ul_grant`, which needs a grant, which needs
        `bytes_reported > 0`, while `BsrModel.pending` re-arms every 5ms
        with nothing able to consume it. Traced per-slot and measured
        corpus-wide in `docs/wp9-plan.md` sec8b/sec8c.

        `backlog > 0 and nothing reportable across every flow of this UE` is
        the proxy for the spec's condition, and is faithful given this
        simulator's structure: every scheduler's UL eligibility gate reads
        `bytes_reported`, so all-zero means no grant can be issued, and live
        backlog means a regular BSR is pending or due. `BsrModel.pending` is
        deliberately NOT consulted -- `UlAccessModel` holds no reference to
        `BsrModel`, and wiring one would couple two modules kept independent
        on purpose. A judgment call, recorded rather than hidden.

        Note the second trigger is evaluated EVERY slot, not only on slots
        carrying an arrival: the spec conditions the SR on the pending BSR
        and the absent grant, not on new data, and a flow that stalls and
        then goes quiet must still recover.

        Call once per slot, after arrivals are enqueued but before `tick()`
        -- same ordering constraint as `BsrModel.on_arrivals`.
        """
        for ue_id, flows in self._ue_flows.items():
            st = self._state[ue_id]
            if st.pending or st.gnb_sr_flag or st.rach_recovery_until is not None:
                continue
            states = [buffers.state(f.ue_id, f.qfi) for f in flows]
            arrived = sum(per_flow_arrived.get((f.ue_id, f.qfi), 0) for f in flows)
            total_now = sum(s.bytes_queued for s in states)
            if arrived > 0 and total_now - arrived <= 0:
                st.pending = True
            elif total_now > 0 and all(s.bytes_reported <= 0 for s in states):
                st.pending = True

    def tick(self, slot_index: int) -> None:
        """Per-UE, per-slot: recurring PUCCH SR occasion
        (`trigger_periodic_scheduling_request`) and the sr-TransMax
        counter / prohibit-timer gate / RA-fallback trigger
        (`nr_ue_get_SR`). Call once per slot, before `BsrModel.broadcast()`
        -- `sr_report_floor()` needs this slot's decision already made.

        RACH recovery: while `rach_recovery_until` is set, the UE is
        UL-ineligible entirely (no occasion check, no report). On
        completion, real backlog is still there (nothing drained it during
        recovery), so recovery completing re-arms `pending` directly --
        equivalent to a fresh SR trigger.

        Retransmission, not one-shot: a real UE has no confirmation its SR
        was received, so it keeps re-signaling at every subsequent occasion
        (subject to the prohibit timer) for as long as it remains
        ungranted -- `gnb_sr_flag` already being set does NOT stop a
        retry. Without this, a UE the scheduler never gets around to
        granting would wait at `counter=1` forever, and sr-TransMax
        exhaustion (the RACH-fallback boundary this WP exists to model)
        would be unreachable in an actual run, only demonstrable by
        hand-forcing state in a test.
        """
        for ue_id, st in self._state.items():
            if st.rach_recovery_until is not None:
                if slot_index >= st.rach_recovery_until:
                    st.rach_recovery_until = None
                    st.pending = True
                continue
            if not st.pending:
                continue
            if st.prohibit_active:
                if slot_index < st.prohibit_deadline_slot:
                    continue
                st.prohibit_active = False
            if (slot_index - self._sr_offset_slots) % self._sr_period_slots != 0:
                continue
            if st.counter >= self._trans_max:
                # sr-TransMax exhausted: cancel the pending SR and fall
                # back to RACH (`nr_ue_get_SR`'s final branch,
                # `nr_ue_procedures.c:2655-2660`).
                st.pending = False
                st.counter = 0
                st.gnb_sr_flag = False
                st.rach_recovery_until = slot_index + self._rach_recovery_slots
                continue
            st.counter += 1
            st.prohibit_active = True
            st.prohibit_deadline_slot = slot_index + self._prohibit_slots
            st.gnb_sr_flag = True

    def on_ul_grant(self, ue_id: int) -> None:
        """Mirrors `sched_ctrl->SR = false` (`gNB_scheduler_ulsch.c:2694`)
        plus the UE-side pending/counter/timer reset on receiving any
        grant -- the request has been served. Call once per UE per slot,
        for the UE's `ue_grant=True` allocation (same call site as
        `BsrModel.on_ul_grant`)."""
        st = self._state.get(ue_id)
        if st is None:
            return
        st.gnb_sr_flag = False
        st.pending = False
        st.counter = 0
        st.prohibit_active = False

    def sr_report_floor(self, ue_id: int) -> int:
        """What `BsrModel.broadcast()` should report in place of WP3's
        probe: the small honest floor once the gNB's SR flag is set
        (served, waiting for the UE to use the grant), 0 otherwise --
        still waiting on an occasion, prohibit-blocked, or in RACH
        recovery."""
        st = self._state.get(ue_id)
        if st is None or not st.gnb_sr_flag:
            return 0
        return self._report_floor
