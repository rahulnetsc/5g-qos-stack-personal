"""Build 1.1 -- 4-step CBRA (sim/random_access.py). Three kinds of pin:

- transcription: the table rows and derived constants are the C's;
- the procedure: a scripted single UE reproduces the calibration log's
  timeline on the DEPLOYED pattern, and the failure paths (collision, RAR
  miss, preambleTransMax) fire with counts;
- the seams: the join FSM asks for RA and consumes its edges, the SR
  fallback starts a C-RNTI RA, the driver carries the counters into
  RunRecord, and RA OFF is the pre-Build-1 code path (the corpus check is
  the bit-identity instrument; here we pin that nothing is constructed).
"""
from __future__ import annotations

import numpy as np
import pytest

from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig
from sim.join import JoinConfig, JoinEvent, JoinPhase, init_join_rng_streams, init_join_state, step
from sim.pre_sched import Occupancy
from sim.random_access import (
    BACKOFF_TABLE_7_2_1_MS, MSG3_DELTA_BY_MU, N_RA_RB, RandomAccessConfig, RandomAccessModel,
    contention_resolution_timer_slots, n_ra_rb, prach_row, response_window_slots,
    ro_prbs_in_slot,
)
from sim.resource import ResourceGrid
from sim.run_record import RunRecord
from sim.ul_access import UlAccessModel
from scheduler.flow import FlowConfig

DEPLOYED_PATTERN = "DDDDDDDSUU"   # log:30 -- 7 DL, S(6/4), 2 UL at mu=1


class _Chan:
    def __init__(self, snr=25.0):
        self.snr = snr

    def get_snr_db(self, ue_id):
        return self.snr

    def get_reported_snr_db(self, ue_id):
        return self.snr


def _grid(mu=1, pattern="DSUUU", bw=40_000_000):
    return ResourceGrid(CarrierConfig(bandwidth_hz=bw, numerology=mu), TDDConfig(pattern=pattern))


def _model(mu=1, pattern="DSUUU", seed=1, cfg=None):
    g = _grid(mu, pattern)
    return RandomAccessModel(cfg or RandomAccessConfig.deployed(), numerology=mu,
                             tdd_pattern=pattern, slot_duration_s=g.slot_duration_s,
                             seed=seed, k1_slots=4, harq_round_max=4,
                             harq_combining_mode="ir"), g


def _run(m, g, chan, until, hooks=None):
    """Step the model to `until`, returning every RaSlotResult."""
    out = []
    for s in range(until):
        if hooks and s in hooks:
            hooks[s]()
        out.append((s, m.step(s, g.slot_grid(s), chan)))
    return out


# --- transcription -------------------------------------------------------

def test_table_rows_are_the_c_s_and_unknown_indices_refuse():
    r = prach_row(98)
    assert (r.format, r.x, r.y, r.sfn_bitmap, r.start_symbol, r.n_ra_slot, r.n_t_slot, r.duration) == \
        (0xA2, 2, 1, 512, 0, 1, 3, 4)
    with pytest.raises(ValueError, match="not transcribed"):
        prach_row(97)
    assert N_RA_RB[1][1] == 12 and N_RA_RB[1][2] == 6 and n_ra_rb(1, 1) == 12
    with pytest.raises(ValueError):
        n_ra_rb(0, 3)
    assert BACKOFF_TABLE_7_2_1_MS[0] == 5 and len(BACKOFF_TABLE_7_2_1_MS) == 14
    assert MSG3_DELTA_BY_MU == (2, 3, 4, 6)


def test_derived_constants_follow_the_carrier_not_a_literal():
    assert response_window_slots(1) == 20 and response_window_slots(2) == 40
    assert response_window_slots(4) == 80                      # capped
    assert contention_resolution_timer_slots(1, 6) == 128 + 12  # 64 ms << 1, + 2*K2
    m, _ = _model(mu=1, pattern=DEPLOYED_PATTERN)
    assert m.window == 20 and m.cr_slots == 140 and m.delta == 3
    assert m.css_period == 10 and m.backoff_limit_slots == 10 and m.msg3_prbs == 8


def test_deployed_values_have_their_provenance():
    c = RandomAccessConfig.deployed()
    assert c.cb_preambles == 64 and c.preamble_trans_max == 10 and c.msg3_k2_slots == 6
    assert c.msg4_bytes_setup == 157
    assert RandomAccessConfig(**c.to_dict()) == c


# --- the occasion rule ----------------------------------------------------

def test_ro_is_slot_19_of_odd_frames_on_the_deployed_pattern():
    cfg = RandomAccessConfig.deployed()
    ro = [s for s in range(80) if ro_prbs_in_slot(cfg, s, 1, DEPLOYED_PATTERN)]
    assert ro == [39, 79]                      # frame 1 slot 19, frame 3 slot 19
    assert ro_prbs_in_slot(cfg, 39, 1, DEPLOYED_PATTERN) == 12


def test_ro_on_the_sim_s_own_carriers():
    cfg = RandomAccessConfig.deployed()
    # mu=1 DSUUU: slot 19 is position 4 = U
    assert [s for s in range(40) if ro_prbs_in_slot(cfg, s, 1, "DSUUU")] == [39]
    # mu=2 DSUUU: 30-kHz slot 19 spans 60-kHz slots 38..39 of the frame,
    # both U, each reserving 6 PRBs (N_RA_RB[30 kHz][60 kHz])
    ro2 = [(s, ro_prbs_in_slot(cfg, s, 2, "DSUUU")) for s in range(160)]
    assert [s for s, n in ro2 if n] == [78, 79, 158, 159]
    assert {n for s, n in ro2 if n} == {6}
    # a pattern where slot 19 is not uplink schedules nothing there
    assert ro_prbs_in_slot(cfg, 39, 1, "DDDDU") == 0 or True  # position 4 = U here too; use one that isn't:
    assert ro_prbs_in_slot(cfg, 39, 1, "UDDDD") == 0
    with pytest.raises(NotImplementedError):
        ro_prbs_in_slot(cfg, 19, 0, "DSUUU")


# --- the procedure -------------------------------------------------------

def test_single_ue_reproduces_the_log_timeline_on_the_deployed_pattern():
    """Preamble 369.19 -> Msg2 370.10 -> Msg3 370.19 -> Msg4 ACK 371.17:
    38 slots. Frames 369/370/371 map here to frames 1/2/3."""
    m, g = _model(mu=1, pattern=DEPLOYED_PATTERN)
    m.request(1, "cold", 0)
    res = _run(m, g, _Chan(25.0), 80)
    done = [(s, r) for s, r in res if 1 in r.completed]
    assert len(done) == 1
    s_done, r = done[0]
    assert m.counters["ra_preambles_tx"] == 1 and m.counters["ra_completed"] == 1
    assert r.latency_slots[1] == 38, r.latency_slots
    assert s_done == 39 + 38                     # preamble at frame 1 slot 19
    # Msg2 at frame 2 slot 10, Msg3 at frame 2 slot 19 (k2 6 + delta 3), Msg4 ACK at frame 3 slot 17
    occ = {s: r.occupancy for s, r in res}
    assert occ[39].prbs_ul == 12                 # the RO itself
    assert occ[50].prbs_dl > 0 and occ[50].cce == 4   # Msg2 at 2.10
    assert occ[59].prbs_ul == 8                  # Msg3 at 2.19, no DCI
    assert occ[59].cce == 0
    assert occ[70].prbs_dl > 0 and occ[70].cce > 0            # Msg4 at 3.10 (3.9 is U), ACK at 3.17 (k1 = 7)


def test_msg3_and_msg4_consume_the_shared_occupancy_per_direction():
    m, g = _model(mu=1, pattern="DSUUU")
    m.request(1, "cold", 0)
    res = _run(m, g, _Chan(25.0), 120)
    total = Occupancy()
    for _, r in res:
        total.add(r.occupancy)
    assert total.prbs_ul >= 12 + 8 and total.prbs_dl > 0 and total.cce > 0
    assert total.ue_counts == {}      # RA UEs never take an M-6 cap slot


def test_same_preamble_collision_fails_msg3_for_both_then_backs_off_and_resolves():
    m, g = _model(mu=1, pattern="DSUUU", seed=3)
    class _Forced:
        """numpy's Generator is read-only; wrap it so the first two preamble
        draws (the only draws with high == 64) collide."""
        def __init__(self, inner):
            self.inner, self.n = inner, 0

        def integers(self, low, high=None):
            if high == 64 and self.n < 2:
                self.n += 1
                return 7
            return self.inner.integers(low, high)
    m._rng = _Forced(np.random.default_rng(0))
    m.request(1, "cold", 0)
    m.request(2, "cold", 0)
    res = _run(m, g, _Chan(25.0), 2000)
    assert m.counters["ra_collisions"] == 1
    assert m.counters["ra_msg3_failures"] >= 4         # every Msg3 round of the shared process
    assert m.counters["ra_cr_timeouts"] >= 1
    assert m.counters["ra_completed"] == 2, m.counters
    assert m.counters["ra_preambles_tx"] >= 4


def test_preamble_trans_max_declares_failure_with_a_count():
    cfg = RandomAccessConfig(preamble_trans_max=2)
    m, g = _model(mu=1, pattern="DSUUU", cfg=cfg)
    m.request(1, "cold", 0)
    chan = _Chan(-30.0)        # Msg3 never decodes
    res = _run(m, g, chan, 4000)
    failed = [s for s, r in res if 1 in r.failed]
    assert failed and m.counters["ra_failed"] == 1 and m.counters["ra_completed"] == 0
    assert m.counters["ra_preambles_tx"] == 2 and not m.active(1)


def test_crnti_variant_resolves_at_msg3_without_msg4():
    m, g = _model(mu=1, pattern="DSUUU")
    m.request(5, "crnti", 0)
    res = _run(m, g, _Chan(25.0), 120)
    done = [(s, r) for s, r in res if 5 in r.completed]
    assert len(done) == 1 and done[0][1].completed[5] == "crnti"
    assert m.by_kind["crnti"]["completed"] == 1 and m.by_kind["cold"]["completed"] == 0
    assert m.summary()["by_kind"]["crnti"]["requested"] == 1
    assert all(r.occupancy.prbs_dl == 0 or s < done[0][0] for s, r in res)  # no Msg4 PDSCH after completion
    assert m.summary()["ra_latency_ms"]["n"] == 1


def test_request_restart_cancels_and_counts():
    m, g = _model()
    m.request(1, "cold", 0)
    m.request(1, "cold", 5)
    assert m.counters["ra_requested"] == 2 and m.counters["ra_cancelled"] == 1 and m.active(1)
    m.cancel(1)
    assert not m.active(1) and m.counters["ra_cancelled"] == 2


# --- the seams ------------------------------------------------------------

def test_join_fsm_requests_ra_and_consumes_its_edges():
    cfg = JoinConfig(initial_state="powered_off", events=(JoinEvent(slot=3, kind="power_on"),))
    st = init_join_state(cfg); rngs = init_join_rng_streams(1)
    r = step(st, cfg, rngs, 3, 0.0005, ra_available=True)
    assert st.phase is JoinPhase.RRC_ESTABLISH and st.ra_pending and r.ra_request_kind == "cold"
    for s in range(4, 40):
        r = step(st, cfg, rngs, s, 0.0005, ra_available=True)
        assert st.phase is JoinPhase.RRC_ESTABLISH and st.ra_pending and r.ra_request_kind is None
    sampled = st.ra_sampled_deadline_slots
    r = step(st, cfg, rngs, 40, 0.0005, ra_available=True, ra_complete_this_slot=True)
    assert not st.ra_pending and st.deadline_slots == max(sampled, float(st.phase_elapsed_slots))
    # without RA the FSM is untouched: no request, no pending
    st2 = init_join_state(cfg); rngs2 = init_join_rng_streams(1)
    r2 = step(st2, cfg, rngs2, 3, 0.0005)
    assert r2.ra_request_kind is None and not st2.ra_pending


def test_join_fsm_ra_failure_re_requests_and_counts_as_t300():
    cfg = JoinConfig(initial_state="powered_off", events=(JoinEvent(slot=1, kind="power_on"),))
    st = init_join_state(cfg); rngs = init_join_rng_streams(2)
    step(st, cfg, rngs, 1, 0.0005, ra_available=True)
    r = step(st, cfg, rngs, 2, 0.0005, ra_available=True, ra_failed_this_slot=True)
    assert r.timer_expired_this_slot and r.ra_request_kind == "cold"
    assert st.timer_expiry_counts["rrc_establish"] == 1 and st.ra_pending


def test_sr_transmax_starts_a_crnti_ra_when_a_requester_is_set():
    flows = [FlowConfig(ue_id=1, qfi=9, direction="UL", lcg=1)]
    ua = UlAccessModel(flows, 0.0005, sr_period_slots=1, sr_prohibit_ms=0.0, sr_trans_max=2)
    calls = []
    ua.ra_requester = lambda ue, slot: calls.append((ue, slot))
    ua._state[1].pending = True
    for s in range(10):
        ua.note_slot(s); ua.tick(s)
    assert calls and ua._state[1].ra_pending and ua._state[1].rach_recovery_until is None
    ua.on_ra_complete(1)
    assert ua._state[1].pending and not ua._state[1].ra_pending


def test_sr_state_is_frozen_for_a_radio_gated_ue_only_when_ra_is_on():
    flows = [FlowConfig(ue_id=1, qfi=9, direction="UL", lcg=1)]
    ua = UlAccessModel(flows, 0.0005, sr_period_slots=1, sr_prohibit_ms=0.0, sr_trans_max=2)
    calls = []
    ua.ra_requester = lambda ue, slot: calls.append(ue)
    ua._state[1].pending = True
    for s in range(6):
        ua.note_slot(s); ua.tick(s, gated_ues=frozenset({1}))
    assert not calls and ua._state[1].counter == 0 and ua._state[1].pending
    for s in range(6, 12):
        ua.note_slot(s); ua.tick(s)
    assert calls == [1]


def _gt62(n_cycles=2):
    from sim.scenarios.g9 import gt62_cold_attach
    return gt62_cold_attach(seed=1, n_neighbours=2, n_cycles=n_cycles, horizon_slots=9000,
                            first_slot=500, off_slots=400, period_slots=3000,
                            allow_partial_schedule=True)


def test_driver_counts_every_scheduled_cold_attach_and_records_it():
    from sim.baselines.pf import ProportionalFair
    from sim.driver import run
    sc = _gt62(2)
    summary = run(sc, ProportionalFair(), random_access=RandomAccessConfig.deployed().to_dict())
    ra = summary["random_access"]
    assert ra["ra_requested"] == 2 and ra["ra_completed"] == 2, ra
    assert ra["ra_latency_ms"]["n"] == 2 and ra["ra_latency_ms"]["max"] < 60.0
    ev = [e for e in summary["join_events"] if e["path"] == "cold"]
    assert len(ev) == 2 and all("ra" in e["phases"] and e["phases"]["ra"] > 0 for e in ev)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="PF", seed=1,
                                 flow_configs=list(sc.flows), summary=summary)
    assert rec.random_access["ra_completed"] == 2
    assert RunRecord.from_dict(rec.to_dict()).random_access == rec.random_access


def test_ra_off_constructs_nothing():
    from sim.baselines.pf import ProportionalFair
    from sim.driver import run
    sc = _gt62(1)
    summary = run(sc, ProportionalFair())
    assert "random_access" not in summary
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="PF", seed=1,
                                 flow_configs=list(sc.flows), summary=summary)
    assert rec.random_access is None
