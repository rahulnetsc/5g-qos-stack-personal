"""M21 -- SLO recovery judged by DELIVERY, not head-of-line age.

THE DEFECT THIS EXISTS FOR, measured rather than argued: `expire()` pops
any chunk older than the PDB every slot, so head-of-line age is capped at
`pdb_ms` BY CONSTRUCTION. M19's `hol <= pdb_ms` green test is therefore
always true -- on G9's own scenarios, 0 of 20,000 and 0 of 30,000 slots
exceed PDB on any flow while the recovering UE drops 1,396,203 bytes.
**M19 cannot report red.** M21 is the companion; M19 is left untouched.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.run_record import JoinEventRecord, RunRecord  # noqa: E402
from sim.scorecard import Scorecard  # noqa: E402

SLOTS = 40
DT = 0.25 / 1000.0 * 4      # 1 ms per sample, 40 ms of run


def _flow(qfi, arrived, dropped):
    return {
        "ue_id": 1, "qfi": qfi, "direction": "UL", "flow_class": "Delay",
        "priority_level": 100, "pdb_ms": 100.0, "gfbr_bps": 0.0,
        "bytes_arrived": sum(arrived), "bytes_delivered": 0,
        "bytes_dropped_pdb": sum(dropped), "bytes_delivered_late_pdb": 0,
        "bytes_harq_lost": 0, "delivery_ratio": 1.0, "throughput_bps": 1.0,
        "offered_bps": 1.0, "delay_p50_ms": 1.0, "delay_p95_ms": 1.0,
        "delay_p98_ms": 1.0, "delay_p99_ms": 1.0, "delay_p50_ms_proxy": 1.0,
        "delay_p95_ms_proxy": 1.0, "delay_p98_ms_proxy": 1.0,
        "delay_p99_ms_proxy": 1.0, "survival_time_ms": 0.0, "message_count": 1,
        "ts_arrived_bytes": arrived, "ts_dropped_bytes": dropped,
        # HoL stays inside PDB throughout -- exactly what expire() enforces,
        # and exactly why M19 sees nothing here.
        "ts_hol_delay_s": [0.001] * len(arrived),
    }


def _record(arrived, dropped, trigger_ts_s=0.0):
    n = len(arrived)
    return RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "t", "scheduler_name": "PF",
        "seed": 1, "arm": {}, "meta": {},
        "timeseries_time_s": [i * 0.001 for i in range(n)],
        "timeseries_slot_index": list(range(n)),
        "system": {"horizon_s": n * 0.001, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
        "flows": {"ue1_qfi1": _flow(1, arrived, dropped)},
        "join_events": [JoinEventRecord(
            ue_id=1, path="reestablish", trigger_slot=0,
            trigger_ts_s=trigger_ts_s, rf_restore_slot=0,
            rf_restore_ts_s=trigger_ts_s).__dict__],
    })


def test_m19_reads_green_through_a_total_outage_and_m21_does_not():
    """THE WHOLE POINT. Everything dropped for the first 20 ms, clean after.
    HoL never exceeds PDB (expire() guarantees that), so M19 says recovery
    took 0 ms. M21 sees the drops."""
    arrived = [100] * SLOTS
    dropped = [100] * 20 + [0] * 20
    rec = _record(arrived, dropped)
    sc = Scorecard()
    # Matched windows, so the comparison isolates the GREEN TEST rather than
    # the dwell length: M19's panel default is 1 s and this record is 40 ms.
    m19 = sc._m19_slo_recovery_time(rec, 0.01).value["by_path"]["reestablish"]
    m21 = sc.slo_recovery_time_by_delivery(rec, window_s=0.01).value["by_path"]["reestablish"]
    assert m19["p50_ms"] == 0.0, "M19 cannot see a 100% drop rate"
    assert m21["p50_ms"] is not None and m21["p50_ms"] > 0.0, \
        "M21 must report a non-zero recovery time"


def test_m21_reports_zero_when_delivery_was_never_interrupted():
    """A warm app restart does not interrupt the radio, so 0 ms is the
    CORRECT answer there -- M21 must not manufacture a delay."""
    rec = _record([100] * SLOTS, [0] * SLOTS)
    m21 = Scorecard().slo_recovery_time_by_delivery(rec, window_s=0.01)
    assert m21.value["by_path"]["reestablish"]["p50_ms"] == 0.0


def test_m21_counts_an_event_that_never_recovers():
    rec = _record([100] * SLOTS, [100] * SLOTS)
    m21 = Scorecard().slo_recovery_time_by_delivery(rec, window_s=0.01)
    d = m21.value["by_path"]["reestablish"]
    assert d["n_never_recovered"] == 1
    assert d["p50_ms"] is None


def test_the_ratio_is_windowed_not_per_slot():
    """The first version compared bytes dropped in slot i against bytes
    ARRIVED in slot i -- but a chunk is dropped pdb_ms AFTER it arrived, so
    those are different bytes. It returned 0.25 ms on a UE that had just
    lost 1.4 MB. Here arrivals and drops are deliberately offset: a
    per-slot ratio sees alternating clean slots and calls it recovered."""
    arrived = ([100, 0] * 10) + [100] * 20      # bursty arrivals, first 20ms
    dropped = ([0, 100] * 10) + [0] * 20        # drops land in the GAPS
    rec = _record(arrived, dropped)
    m21 = Scorecard().slo_recovery_time_by_delivery(rec, window_s=0.01)
    assert m21.value["by_path"]["reestablish"]["p50_ms"] > 0.0, \
        "a windowed ratio must see the offset drops a per-slot ratio misses"


def test_m21_is_pending_without_join_events():
    rec = _record([100] * SLOTS, [0] * SLOTS)
    rec.join_events = []
    assert Scorecard().slo_recovery_time_by_delivery(rec).status == "pending"
