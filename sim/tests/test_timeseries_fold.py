"""Per-second timeseries fold: M09 and M08w bit-identical, the rest pending.

WP9 G11 commit 3. Per-slot recording is ~24 GiB at the 7.2M-slot soak
horizon (docs/wp9-plan.md §37). Everything G11's C1 needs from those arrays
is consumed bucketed to one second, so folding at record time is lossless
for those consumers and a 4,000x reduction.

THE GUARD THAT BINDS, named per CLAUDE.md's could-have-failed rule:
`--check` reads RunRecords and this commit rewrites RunRecord.timeseries_*
-- they DO intersect, but only on the folded path, which no corpus case
takes (the fold is opt-in). So --check is clean and proves nothing here;
these tests are the guard.

  1. EXACTNESS -- M09's value under the fold equals its value per-slot, bit
     for bit. This is the claim that makes the fold safe, and it is the one
     thing a memory measurement cannot establish.
  2. HONEST ABSENCE -- M04/M19/M21 report pending, not a number computed
     from a per-second aggregate misread as a per-slot series.
  3. THE DEFAULT IS UNTOUCHED.
"""

from __future__ import annotations

import pytest

from sim.baselines.pf import ProportionalFair
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard

HORIZON = 20_000          # 5.0 s at numerology 2


def _rec(resolution: str, seed: int = 1, n_ues: int = 4) -> RunRecord:
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=HORIZON)
    summary = run(sc, ProportionalFair(ewma_window_slots=200),
                  cqi_delay_slots=8, record_timeseries=True,
                  timeseries_resolution=resolution)
    return RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name="PF", seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def test_M09_is_bit_identical_under_the_fold():
    """The load-bearing claim: folding is lossless for the metric that
    defines itself in per-second terms."""
    per_slot = Scorecard()._m09_per_second_jain(_rec("slot"))
    folded = Scorecard()._m09_per_second_jain(_rec("second"))
    assert folded.value == per_slot.value, (
        f"M09 moved under the fold: {folded.value} != {per_slot.value}. "
        "The fold sums COUNT series per second and M09 buckets by second, "
        "so these must agree exactly; a difference means the fold is not "
        "aligned to the same second boundaries.")
    assert per_slot.value is not None, "fixture scored no window"


def test_the_fold_actually_shrinks_the_series():
    """Otherwise the test above passes for the wrong reason."""
    slot, sec = _rec("slot"), _rec("second")
    assert len(slot.timeseries_time_s) == HORIZON
    assert len(sec.timeseries_time_s) == pytest.approx(HORIZON * 0.00025, abs=1)
    assert len(sec.timeseries_time_s) < len(slot.timeseries_time_s) / 100


def test_level_series_are_absent_not_summed():
    """backlog and hol delay are LEVELS -- a per-second sum is meaningless
    and a max would be a different statistic under the same field name."""
    sec = _rec("second")
    for fr in sec.flows.values():
        assert fr.ts_backlog_bytes is None
        assert fr.ts_hol_delay_s is None
        assert fr.ts_delivered_bytes is not None


def test_M04_M19_M21_report_pending_not_a_misread_aggregate():
    scores = Scorecard().score(_rec("second"), population=Population.all_flows())
    for mid in ("M04", "M19", "M21"):
        assert scores[mid].status == "pending", (
            f"{mid} is {scores[mid].status!r} with value {scores[mid].value!r} "
            "-- it needs per-slot levels the fold does not carry")
        assert "per-second" in (scores[mid].note or "")


def test_the_slot_default_is_completely_unchanged():
    slot = _rec("slot")
    assert slot.timeseries_resolution == "slot"
    assert "timeseries_resolution" not in slot.to_dict(), (
        "the marker must not be serialised on the default path, or every "
        "record in the frozen corpus changes shape")
    for fr in slot.flows.values():
        assert fr.ts_hol_delay_s is not None
    scores = Scorecard().score(slot, population=Population.all_flows())
    assert scores["M04"].status != "pending" or not slot.has_timeseries()


def test_resolution_survives_a_dict_round_trip_and_an_unknown_value_raises():
    sec = _rec("second")
    assert RunRecord.from_dict(sec.to_dict()).timeseries_resolution == "second"
    sc = sweep_scenario(seed=1, n_ues=2, horizon_slots=200)
    with pytest.raises(ValueError, match="timeseries_resolution"):
        run(sc, ProportionalFair(ewma_window_slots=200),
            record_timeseries=True, timeseries_resolution="minute")
