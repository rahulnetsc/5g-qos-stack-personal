"""G5's scenarios and its new windowed-GFBR metric.

The tests that matter here are the ones that could FAIL: that M23 is a
genuinely different statistic from M08, that the load flows never enter a
scored population, and that GT-3.2's ramp does not reach the fragmentation
knob CLAUDE.md flags.
"""
from __future__ import annotations

import pytest

from sim.run_record import FlowRecord, RunRecord
from sim.scorecard import Population, Scorecard
from sim.scenarios.g5 import (
    BG_UL_BPS, CAMERA_FPS, CAMERA_GFBR_BPS, CAMERA_PERIOD_MS, FRAGMENT_BYTES,
    GFBR_WINDOW_S, LOAD_STEPS, QFI_BG_UL, QFI_CAMERA, QFI_LIDAR,
    QFI_TELEMETRY, build_gt31_scenario, build_gt32_scenario,
    build_gt33_scenario, camera_flow_key, frame_age_bound_ms,
    telemetry_flow_keys)


# --- the clause's own constants are DERIVED ------------------------------

def test_frame_age_bound_is_two_frame_periods_not_the_sheets_rounded_67():
    """The sheet says 67 ms; two periods at 30 fps is 66.67. If the camera's
    frame rate ever changes this must move with it."""
    assert frame_age_bound_ms(30.0) == pytest.approx(66.6667, abs=1e-3)
    assert frame_age_bound_ms(60.0) == pytest.approx(33.3333, abs=1e-3)
    assert frame_age_bound_ms(CAMERA_FPS) == pytest.approx(
        2.0 * CAMERA_PERIOD_MS, abs=1e-9)


def test_the_scenario_window_and_the_panel_default_agree():
    """Two copies of 2.0 exist -- the scenario constant and the panel
    default. Drift between them would silently score a different clause."""
    assert Scorecard().defaults["gfbr_window_s"] == GFBR_WINDOW_S


def test_load_steps_are_derived_and_span_the_sub_tests_own_range():
    assert LOAD_STEPS[0] == 1.0 and LOAD_STEPS[-1] == 1.5
    assert len(LOAD_STEPS) == 6
    assert all(round(b - a, 10) == 0.1 for a, b in zip(LOAD_STEPS, LOAD_STEPS[1:]))


# --- the population ------------------------------------------------------

def test_the_instrument_is_ONE_named_camera_not_worst_of_N():
    """If every robot were the instrument, the fleet axis would move the
    statistic as well as the load -- the defect that produced G3's
    withdrawn row."""
    for n in (4, 8, 24):
        sc = build_gt31_scenario(seed=1, n_ues=n, horizon_slots=4_000)
        assert camera_flow_key(sc) == f"ue1_qfi{QFI_CAMERA}"


def test_part4s_population_is_EVERY_robots_telemetry_derived_from_the_flows():
    """GT-3.1 says "A and B telemetry unharmed", so the collateral check
    ranges over both assets -- and the set is derived from the scenario, so a
    builder change cannot silently shrink it."""
    for n in (4, 8, 16):
        sc = build_gt31_scenario(seed=1, n_ues=n, horizon_slots=4_000)
        keys = telemetry_flow_keys(sc)
        assert len(keys) == n, (n, keys)
        assert keys == sorted(keys)


def test_the_load_flows_are_present_and_are_NOT_in_the_protected_population():
    """The lidar and the 5QI-9 saturator must exist (or there is no
    contention) and must never enter a scored aggregate."""
    sc = build_gt31_scenario(seed=1, n_ues=6, horizon_slots=4_000)
    qfis = {f.qfi for f in sc.flows}
    assert QFI_LIDAR in qfis, "no lidar: GT-3.1 has no contention"
    assert QFI_BG_UL in qfis, "no background: GT-3.1 has no saturation"
    excluded = Population.protected_fleet().excluded_5qi
    assert QFI_BG_UL in excluded
    assert QFI_CAMERA not in excluded and QFI_TELEMETRY not in excluded


def test_the_saturator_rides_ASSET_B_ALONE_not_the_whole_fleet():
    """Spreading it over every neighbour would make the fleet axis vary the
    offered background load as well as the contention, confounding the two."""
    for n in (4, 8, 24):
        sc = build_gt31_scenario(seed=1, n_ues=n, horizon_slots=4_000)
        bg = [f.ue_id for f in sc.flows if f.qfi == QFI_BG_UL]
        assert bg == [2], (n, bg)


# --- GT-3.2's ramp -------------------------------------------------------

def test_gt32_scales_avg_bytes_BEFORE_fragmentation_not_the_fragments():
    """CLAUDE.md's known issue: `aggressor_multiplier` scales an xr_video
    flow's fragments AFTER _gen_xr_video has fragmented the frame, so a
    scaled fragment can exceed fragment_bytes. The ramp must not use it."""
    lo = build_gt32_scenario(seed=1, load_mult=1.0, n_ues=6, horizon_slots=4_000)
    hi = build_gt32_scenario(seed=1, load_mult=1.5, n_ues=6, horizon_slots=4_000)
    a = [f for f in lo.flows if f.qfi == QFI_CAMERA and f.ue_id == 1][0]
    b = [f for f in hi.flows if f.qfi == QFI_CAMERA and f.ue_id == 1][0]
    assert b.traffic_params["avg_bytes"] == pytest.approx(
        1.5 * a.traffic_params["avg_bytes"])
    # the fragment cap is UNTOUCHED by the ramp
    assert a.traffic_params["fragment_bytes"] == FRAGMENT_BYTES
    assert b.traffic_params["fragment_bytes"] == FRAGMENT_BYTES
    # 1.0 is the field's own default -- "untouched", not "zero". The first
    # version of this assertion tested `not aggressor_multiplier` and failed
    # on the default, which is the wrong sentinel for a MULTIPLIER.
    for f in list(lo.flows) + list(hi.flows):
        assert f.aggressor_multiplier == 1.0, (
            f"GT-3.2 reached aggressor_multiplier on ue{f.ue_id}_qfi{f.qfi}, "
            f"the knob that breaks _gen_xr_video's MTU cap")


def test_gt32_has_NO_background_flow_because_the_sub_test_says_so():
    """The ceiling is a property of the committed portfolio; a saturating
    non-GBR flow would make it a property of the aggressor instead."""
    sc = build_gt32_scenario(seed=1, load_mult=1.0, n_ues=6, horizon_slots=4_000)
    assert not [f for f in sc.flows if f.qfi == QFI_BG_UL]


def test_gt32_scales_the_committed_fleet_too_not_only_the_instrument():
    """"all committed flows ... stepped" -- stepping only the instrument
    would measure its own headroom rather than the cell's."""
    lo = build_gt32_scenario(seed=1, load_mult=1.0, n_ues=6, horizon_slots=4_000)
    hi = build_gt32_scenario(seed=1, load_mult=1.5, n_ues=6, horizon_slots=4_000)
    f_lo = [f for f in lo.flows if f.qfi == QFI_LIDAR][0]
    f_hi = [f for f in hi.flows if f.qfi == QFI_LIDAR][0]
    assert (f_hi.traffic_params["bytes_per_period"]
            > f_lo.traffic_params["bytes_per_period"])


# --- GT-3.3 --------------------------------------------------------------

def test_gt33_degrades_a_NEIGHBOUR_and_refuses_to_degrade_the_instrument():
    sc = build_gt33_scenario(seed=1, edge_snr_db=-6.0, n_ues=6,
                             horizon_slots=4_000)
    snrs = {u.ue_id: u.mean_snr_db for u in sc.ues}
    assert snrs[1] == 20.0, "Asset A must stay nominal -- it is the control"
    assert snrs[2] == -6.0
    assert all(v == 20.0 for k, v in snrs.items() if k != 2)
    with pytest.raises(ValueError, match="instrument"):
        build_gt33_scenario(seed=1, edge_snr_db=-6.0, n_ues=6,
                            horizon_slots=4_000, edge_ue=1)


# --- M23, the new metric -------------------------------------------------

def _record_with(delivered_per_slot, gfbr_bps, n_slots, step_s=0.001):
    fr = FlowRecord(
        ue_id=1, qfi=QFI_CAMERA, direction="UL", flow_class="GBR",
        gfbr_bps=gfbr_bps, pdb_ms=150.0, priority_level=40,
        bytes_arrived=0, bytes_delivered=0, bytes_dropped_pdb=0,
        bytes_delivered_late_pdb=0, throughput_bps=0.0, offered_bps=0.0,
        delivery_ratio=1.0, delay_p50_ms_proxy=0.0,
        delay_p95_ms_proxy=0.0, delay_p99_ms_proxy=0.0,
    )
    fr.ts_delivered_bytes = list(delivered_per_slot)
    rec = _empty_record({fr.key: fr})
    rec.timeseries_time_s = [i * step_s for i in range(n_slots)]
    return rec


def _empty_record(flows):
    return RunRecord(schema_version=1, scenario_name="t", scheduler_name="t",
                     seed=1, arm={}, flows=flows, system={})


def test_M23_does_NOT_punish_a_run_that_delivered_EVERY_OFFERED_BYTE():
    """The defect the first version of M23 had, pinned so it cannot return.

    A variable-frame-size source sized to its contract on average offers a few
    percent either side of it per window. Uncapped, `delivered / (GFBR *
    window)` scores a shortfall in a window where the network held back
    NOTHING -- measuring the traffic generator, which is this project's own
    offered-shortfall defect one level down.
    """
    step = 0.001
    per_window = int(GFBR_WINDOW_S / step)
    gfbr = 8_000_000.0
    at_gfbr = int(gfbr / 8.0 * step)
    # Window 0 offers 3 % BELOW contract; window 1 offers 3 % above. Both are
    # delivered in full, so the network held nothing back in either.
    series = ([int(at_gfbr * 0.97)] * per_window
              + [int(at_gfbr * 1.03)] * per_window)
    rec = _record_with(series, gfbr, len(series), step)
    fr = rec.flows["ue1_qfi2"]
    fr.ts_arrived_bytes = list(series)          # delivered == offered
    fr.throughput_bps = sum(series) * 8.0 / (len(series) * step)

    v = Scorecard().score(rec, population=Population.protected_fleet(),
                          only=["M23"])["M23"].value
    assert v["fraction"] == pytest.approx(1.0, rel=1e-9), (
        f"a run that delivered every offered byte scored {v['fraction']} -- "
        f"the denominator is not capped at what was offered")
    # ... and the under-offering is still VISIBLE rather than forgiven.
    assert v["worst_offered_fraction"] == pytest.approx(0.97, rel=1e-3)


def test_M23_FAILS_where_M08_PASSES_which_is_the_reason_it_exists():
    """The registered claim in `docs/g5-step0-2026-09-10.md` sec 1.1: a
    run-level minimum cannot see a bad window. Constructed so M08's own
    run-level fraction is comfortably above 1.0 while one 2 s window is
    starved -- if this ever stops holding, M23 is redundant."""
    step = 0.001
    per_window = int(GFBR_WINDOW_S / step)          # 2000 slots
    # Sized so one slot at GFBR is a WHOLE number of bytes. A first version
    # used 8 kbps, where GFBR is 1 B/slot and a 0.1x window truncates to
    # ZERO bytes per slot -- the fixture then failed its own precondition
    # rather than the thing under test.
    gfbr = 8_000_000.0                              # 1e6 B/s = 1000 B/slot
    at_gfbr = int(gfbr / 8.0 * step)                # 1000 B per slot
    assert at_gfbr * per_window == gfbr * GFBR_WINDOW_S / 8.0
    # window 0 starved to a tenth, windows 1 and 2 carry the shortfall back.
    series = ([int(at_gfbr * 0.1)] * per_window
              + [int(at_gfbr * 1.5)] * per_window * 2)
    rec = _record_with(series, gfbr, len(series), step)
    fr = rec.flows["ue1_qfi2"]
    # The SOURCE offers at contract throughout; only DELIVERY is starved in
    # window 0. Without this the capped denominator would forgive it.
    fr.ts_arrived_bytes = [at_gfbr] * len(series)
    fr.throughput_bps = sum(series) * 8.0 / (len(series) * step)

    res = Scorecard().score(rec, population=Population.protected_fleet(),
                            only=["M08", "M23"])
    m08 = res["M08"].value["fraction"]
    m23 = res["M23"].value["fraction"]
    assert m08 > 1.0, f"the fixture must make M08 PASS, got {m08}"
    assert m23 < 0.2, f"the starved window must show in M23, got {m23}"


def test_M23_discards_the_trailing_PARTIAL_window():
    """A short window's denominator is smaller, so scoring it would report a
    shortfall that is an artefact of where the run ended."""
    step = 0.001
    per_window = int(GFBR_WINDOW_S / step)
    gfbr = 8_000_000.0
    full = [1000] * per_window             # exactly GFBR at 8 Mbps
    rec = _record_with(full + [1000] * (per_window // 2), gfbr,
                       per_window + per_window // 2, step)
    rec.flows["ue1_qfi2"].ts_arrived_bytes = list(
        rec.flows["ue1_qfi2"].ts_delivered_bytes)
    v = Scorecard().score(rec, population=Population.protected_fleet(),
                          only=["M23"])["M23"].value
    assert v["n_windows"] == 1
    assert v["n_windows_discarded_partial"] == 1
    assert v["fraction"] == pytest.approx(1.0, rel=1e-6)


def test_M23_is_PENDING_not_zero_without_timeseries():
    """An omitted or zeroed row is indistinguishable from a real shortfall."""
    rec = _empty_record({})
    r = Scorecard().score(rec, population=Population.protected_fleet(),
                          only=["M23"])["M23"]
    assert r.status == "pending" and r.value is None
    assert "record_timeseries" in (r.note or "")
