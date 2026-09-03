"""M22 -- G8's second conjunct, which had no instrument (Phase-1 fix pass).

THE GAP THIS CLOSES. G8's KPI is a conjunction: "per-1 s Jain >= 0.9 per
role across assets; AND zero starvation epochs >= 1 s". Only M08 and M09
were bound to G8 and neither can express the second half -- M09 scores
`delivered / arrived` with a hardcoded 1.0 when `arrived == 0`, so a flow
delivering nothing reads as PERFECTLY FAIR precisely when it is starved.

THE GUARD THAT BINDS, and it is the pairing rather than either half: the
metric must return NON-ZERO on a starved flow and ZERO on a served one. A
test that only showed the first would pass for a metric that counts
everything; one that only showed the second would pass for a metric that
counts nothing. Both are checked here against the SAME fixture shape.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Population, Scorecard  # noqa: E402


def _flow(ue_id, qfi, arrived, delivered):
    return {
        "ue_id": ue_id, "qfi": qfi, "direction": "UL", "flow_class": "Delay",
        "priority_level": 20, "pdb_ms": 100.0, "gfbr_bps": 0.0,
        "bytes_arrived": sum(arrived), "bytes_delivered": sum(delivered),
        "bytes_dropped_pdb": 0, "bytes_delivered_late_pdb": 0,
        "bytes_harq_lost": 0, "delivery_ratio": 1.0, "throughput_bps": 1.0,
        "offered_bps": 1.0, "delay_p50_ms": 1.0, "delay_p95_ms": 1.0,
        "delay_p98_ms": 1.0, "delay_p99_ms": 1.0, "delay_p50_ms_proxy": 1.0,
        "delay_p95_ms_proxy": 1.0, "delay_p98_ms_proxy": 1.0,
        "delay_p99_ms_proxy": 1.0, "survival_time_ms": 0.0,
        "message_count": 0, "completion_ts_by_role_s": {},
        "ts_arrived_bytes": arrived, "ts_delivered_bytes": delivered,
    }


def _record(flows, n):
    return RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "PF",
        "seed": 1, "arm": {}, "meta": {}, "flows": flows,
        "system": {"horizon_s": float(n), "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
        "timeseries_time_s": [float(i) for i in range(n)],
    })


def _m22(flows, n=10):
    return Scorecard().score(_record(flows, n),
                             population=Population.all_flows())["M22"]


def test_served_flow_scores_zero_epochs():
    """Delivering every second: the metric must be able to say ZERO."""
    r = _m22({"ue1_qfi1": _flow(1, 1, [10] * 10, [10] * 10)})
    assert r.value["epochs"] == 0, r.value
    assert r.value["flows_scored"] == 1


def test_starved_flow_scores_the_epoch():
    """Same shape, arrivals throughout, four consecutive silent seconds."""
    dlv = [10, 10, 0, 0, 0, 0, 10, 10, 10, 10]
    r = _m22({"ue1_qfi1": _flow(1, 1, [10] * 10, dlv)})
    assert r.value["epochs"] == 1, r.value
    assert r.value["longest_epoch_s"] == 4.0, r.value
    assert r.value["worst_flow"] == "ue1_qfi1"


def test_silence_outside_the_flow_s_own_active_interval_is_not_starvation():
    """A flow that has not started, or has finished, is not being starved.

    This is the discriminator that stops M22 from charging every
    activation-gated or duty-cycled source for its own schedule -- the same
    class of error as M03 reporting a source's cadence as a liveness gap.
    """
    arr = [0, 0, 10, 10, 10, 0, 0, 0, 0, 0]
    dlv = [0, 0, 10, 10, 10, 0, 0, 0, 0, 0]
    r = _m22({"ue1_qfi1": _flow(1, 1, arr, dlv)})
    assert r.value["epochs"] == 0, r.value


def test_a_flow_that_never_offered_anything_is_not_scored():
    r = _m22({"ue1_qfi1": _flow(1, 1, [0] * 10, [0] * 10)})
    assert r.value is None
    assert "no flow had any arrival" in r.note


def test_pending_without_timeseries():
    """The panel's never-omit rule: a row with value=None AND a reason."""
    rec = RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "PF",
        "seed": 1, "arm": {}, "meta": {},
        "flows": {"ue1_qfi1": _flow(1, 1, [], [])},
        "system": {"horizon_s": 1.0, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
    })
    r = Scorecard().score(rec, population=Population.all_flows())["M22"]
    assert r.value is None and r.status == "pending" and r.note


def test_m22_is_bound_to_g8_in_the_panel():
    """Derived from the panel, not restated -- CLAUDE.md's count rule, whose
    fourth recorded instance was in test code and failed toward PASSING."""
    from sim.scorecard import load_panel
    m22 = next(m for m in load_panel()["metrics"] if m["id"] == "M22")
    assert "G8" in m22["guarantees"]
    g8 = {m["id"] for m in load_panel()["metrics"]
          if "G8" in (m.get("guarantees") or [])}
    assert {"M08", "M09", "M22"} <= g8, g8
