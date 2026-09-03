"""The join handshake's bytes must be ARRIVED as well as DELIVERED.

THE DEFECT (#18). sim/driver.py's ordinary traffic path increments BOTH
`metrics.record_arrival()` and `per_flow_arrived`. The join handshake
incremented only `per_flow_arrived` for its UL request and NEITHER for its
DL response, while both messages were delivered and counted normally. So the
two handshake flows reported far more bytes delivered than ever arrived.

MEASURED BEFORE THE FIX, on gt61_warm_rejoin(seed=1, n_neighbours=3,
horizon_slots=30_000), PF:

    ue1_qfi70   arrived 1   delivered 641   ratio 641.00
    ue1_qfi71   arrived 1   delivered 641   ratio 641.00

against 1.00 or below for every other flow in the same run. sim/metrics.py
computes `delivery_ratio = bytes_delivered / max(1, bytes_arrived)`, so the
ratio is not merely wrong, it is unbounded -- and ANY byte-weighted statistic
over the joiner was unsound, which is the population G9 exists to measure.

WHY A RATIO CEILING RATHER THAN AN EQUALITY. A handshake message can be
generated and not yet delivered when the horizon ends, so delivered <=
arrived is the invariant; delivered == arrived is not. Asserting equality
would make this test fail on horizon choice rather than on the defect.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sim.scenarios.g9 as g9  # noqa: E402
from scheduler import load_two_tier  # noqa: E402
from sim.baselines.pf import ProportionalFair  # noqa: E402
from sim.driver import run as driver_run  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402

HANDSHAKE_QFIS = (g9.QFI_HANDSHAKE_UL, g9.QFI_HANDSHAKE_DL)


def _record():
    sc = g9.gt61_warm_rejoin(seed=1, n_neighbours=3, horizon_slots=30_000)
    summary = driver_run(sc, ProportionalFair(), cqi_delay_slots=8,
                         record_timeseries=False)
    return RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=1,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def test_no_flow_delivers_more_bytes_than_ever_arrived():
    """The general invariant, over EVERY flow -- not just the handshake.

    Stated generally on purpose: the defect was found on the handshake, but
    a test naming only those two 5QIs could not catch the next site that
    delivers without recording an arrival.
    """
    rec = _record()
    offenders = {
        k: (fr.bytes_arrived, fr.bytes_delivered)
        for k, fr in rec.flows.items()
        if fr.bytes_delivered > fr.bytes_arrived
    }
    assert not offenders, (
        f"flow(s) delivered more bytes than arrived: {offenders}. Every "
        f"enqueue path must credit metrics.record_arrival(), not only "
        f"per_flow_arrived -- see sim/driver.py's handshake sites.")


def test_the_handshake_flows_actually_fired():
    """The precondition, asserted rather than assumed.

    A run with no handshake traffic would pass the invariant above
    vacuously -- the empty-selection shape this project has hit six times.
    """
    rec = _record()
    seen = {fr.qfi: fr.bytes_arrived for fr in rec.flows.values()
            if fr.qfi in HANDSHAKE_QFIS}
    assert set(seen) == set(HANDSHAKE_QFIS), (
        f"handshake flows absent from the record: got {sorted(seen)}, "
        f"expected {sorted(HANDSHAKE_QFIS)}")
    for qfi, arrived in seen.items():
        assert arrived > 1, (
            f"5QI {qfi} arrived only {arrived} bytes -- the handshake's own "
            f"messages are not being credited, which is the defect itself")


@pytest.mark.parametrize("arm", ["PF", "TwoTier"])
def test_handshake_ratio_is_sane_on_both_arms(arm):
    """The defect was in the driver, not in any scheduler, so it must be
    gone regardless of which arm ran."""
    sc = g9.gt61_warm_rejoin(seed=1, n_neighbours=3, horizon_slots=30_000)
    sched = ProportionalFair() if arm == "PF" else load_two_tier(
        str(Path(__file__).resolve().parents[2] / "scheduler"
            / "scheduler_config.yaml"), min_rb=5)
    summary = driver_run(sc, sched, cqi_delay_slots=8, record_timeseries=False)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=1, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})
    for fr in rec.flows.values():
        if fr.qfi in HANDSHAKE_QFIS:
            assert fr.delivery_ratio <= 1.0 + 1e-9, (fr.key, fr.delivery_ratio)
