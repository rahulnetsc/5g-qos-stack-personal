"""M03's caveat must tell a SLOW source from a DEGRADED one (#22).

THE DEFECT. The caveat fired on `median_gap_ms > T_live/4` and said "do not
score it against that bound". `median_gap_ms` is MEASURED, so the predicate
could not distinguish two opposite situations:

    configured 1000 ms, observed 1000 ms  -> slow BY DESIGN, suppress
    configured  200 ms, observed  600 ms  -> DEGRADED by the network, SCORE

and it suppressed both. Measured in a published dataset
(sweeps/wp9/part_c_rows.csv): 4 of 44 duty-0.5 breaches are the second case,
with real 1-2.8 s max gaps silenced -- observed medians 596/602/551/525 ms
against a 200 ms configured period.

WHY THIS BLOCKED G3. M03/M20 is the metric G3 binds to, so a G3 verdict was
silent precisely on the flows that had failed worst and reported the
remainder as a pass: a selection effect that removes failures from the
numerator, not a caveat.

THE HISTORY IS PART OF THE TEST. The previous correction here
(docs/wp9-defects-log.md #8) was itself an over-correction -- it asserted
"at duty 0.5 the caveat does NOT fire" by reasoning from the CONFIGURED
period while the predicate reads the MEASURED one. This test pins the
distinction that mistake turned on, so a future change cannot quietly
collapse the two cases again.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_m03_protected_fleet import _flow, _record  # noqa: E402
from sim.scorecard import Population, Scorecard  # noqa: E402

SUPPRESS = "CADENCE, NOT LIVENESS"
SCORE = "DEGRADED, NOT CADENCE"


def _m03(gaps, configured_period_ms):
    f = _flow(1, 1, gaps)
    f["configured_period_ms"] = configured_period_ms
    return Scorecard().score(_record({"ue1_qfi1": f}),
                             population=Population.protected_fleet())["M03"]


def test_slow_by_design_is_suppressed():
    """The caveat's intended case, kept working."""
    r = _m03([1.0] * 10 + [2.0] + [1.0] * 10, 1000.0)
    assert any(c.startswith(SUPPRESS) for c in r.caveats)
    assert not any(c.startswith(SCORE) for c in r.caveats)


def test_degraded_by_the_network_is_SCORED_not_suppressed():
    """THE DEFECT. Same max gap as the case above, same observed median above
    the bound -- but the source ASKED for 200 ms, so being served at 600 ms
    is the failure, not the explanation for it."""
    r = _m03([0.1] * 4 + [0.6] * 12 + [2.0] + [0.6] * 4, 200.0)
    assert not any(c.startswith(SUPPRESS) for c in r.caveats), (
        "a network-degraded flow was suppressed as if it were slow by design")
    assert any(c.startswith(SCORE) for c in r.caveats)
    assert r.value["max_gap_ms"] > 500.0     # and it IS a breach


def test_a_healthy_source_gets_neither_caveat():
    """Dynamic range in the other direction: the predicate must be able to
    stay quiet, or 'it fired' would carry no information."""
    r = _m03([0.1] * 10 + [2.0] + [0.1] * 10, 100.0)
    assert not any(c.startswith(SUPPRESS) or c.startswith(SCORE)
                   for c in r.caveats)


def test_an_aperiodic_source_cannot_claim_slow_by_design():
    """No configured period means no basis for the suppression, so the
    conservative branch is taken. Chosen deliberately: the failure mode being
    guarded is a SILENCED breach, so ambiguity resolves toward scoring."""
    r = _m03([0.1] * 4 + [0.6] * 12 + [2.0] + [0.6] * 4, None)
    assert any(c.startswith(SCORE) for c in r.caveats)
    assert not any(c.startswith(SUPPRESS) for c in r.caveats)


def test_the_configured_period_reaches_the_metric_value():
    """The record field must actually arrive -- a scorer reading None for
    every flow would silently take the conservative branch always, which
    looks like the fix working while testing nothing."""
    r = _m03([1.0] * 10 + [2.0] + [1.0] * 10, 1000.0)
    assert r.value["configured_period_ms"] == 1000.0


@pytest.mark.parametrize("period,expect_suppressed", [
    (1000.0, True), (600.0, True), (500.0, False), (200.0, False), (None, False),
])
def test_the_boundary_is_the_bound_itself(period, expect_suppressed):
    """Suppression requires the CONFIGURED period to exceed T_live/4 = 500 ms;
    exactly 500 does not, since the bound is inclusive for the flow."""
    r = _m03([0.6] * 20 + [2.0] + [0.6] * 4, period)
    assert any(c.startswith(SUPPRESS) for c in r.caveats) is expect_suppressed
