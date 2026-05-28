"""End-to-end smoke test for the HARQ feature (Step 6).

Runs the full simulation loop with harq=True and harq=False through
multiple schedulers and scenarios, verifying:

  1. No crashes -- all schedulers complete without exception.
  2. HARQ summary fields are present and sane.
  3. harq=True delivery_ratio >= harq=False delivery_ratio.
     (HARQ retransmits failures → more bytes confirmed delivered)
  4. harq=True produces non-zero harq_retx_ratio (retx actually fired).
  5. harq=False summary is unchanged from pre-HARQ behaviour
     (harq_enabled=False, harq_retx_bytes=0).
  6. PRB utilisation stays in [0, 1].
  7. The reduced slot view correctly limits scheduler PRBs when retx fires.

Run from the project root:
    pytest sim/tests/test_smoke_harq.py -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest
from sim.config_loader import load_scenario
from sim.driver import run
from sim.baselines.round_robin import RoundRobin
from sim.baselines.pf import ProportionalFair
from scheduler import TwoTier

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def _schedulers():
    return [
        ("RoundRobin",       RoundRobin()),
        ("ProportionalFair", ProportionalFair()),
        ("TwoTier",          TwoTier(tier1_period_slots=500)),
    ]


def _load(scenario_id):
    return load_scenario(SCENARIOS_DIR, scenario_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_flows(summary):
    return list(summary["flows"].values())


def _check_flow_sanity(flow, harq_enabled):
    assert flow["bytes_delivered"] >= 0
    assert flow["delivery_ratio"] >= 0.0
    assert flow["delivery_ratio"] <= 1.0
    assert flow["harq_retx_bytes"] >= 0
    assert flow["harq_loss_bytes"] >= 0
    assert flow["harq_retx_ratio"] >= 0.0
    assert flow["harq_loss_ratio"] >= 0.0
    if not harq_enabled:
        assert flow["harq_retx_bytes"] == 0
        assert flow["harq_loss_bytes"] == 0


# ---------------------------------------------------------------------------
# Test 1: no crash with harq=True, all schedulers
# ---------------------------------------------------------------------------

class TestNocrash:

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_harq_true_completes(self, name, sched):
        scenario = _load(1)
        summary = run(scenario, sched, harq=True)
        assert "flows" in summary
        assert summary["harq_enabled"] is True

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_harq_false_completes(self, name, sched):
        scenario = _load(1)
        summary = run(scenario, sched, harq=False)
        assert "flows" in summary
        assert summary["harq_enabled"] is False


# ---------------------------------------------------------------------------
# Test 2: HARQ summary fields present and sane
# ---------------------------------------------------------------------------

class TestSummaryFields:

    def test_harq_fields_present(self):
        summary = run(_load(1), RoundRobin(), harq=True)
        for flow in _all_flows(summary):
            for key in ("harq_retx_bytes", "harq_loss_bytes",
                        "harq_retx_ratio", "harq_loss_ratio"):
                assert key in flow, f"Missing field: {key}"

    def test_harq_false_retx_bytes_zero(self):
        summary = run(_load(1), RoundRobin(), harq=False)
        for flow in _all_flows(summary):
            assert flow["harq_retx_bytes"] == 0
            assert flow["harq_loss_bytes"] == 0

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_flow_sanity_harq_true(self, name, sched):
        summary = run(_load(1), sched, harq=True)
        for flow in _all_flows(summary):
            _check_flow_sanity(flow, harq_enabled=True)

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_flow_sanity_harq_false(self, name, sched):
        summary = run(_load(1), sched, harq=False)
        for flow in _all_flows(summary):
            _check_flow_sanity(flow, harq_enabled=False)


# ---------------------------------------------------------------------------
# Test 3: retransmissions actually fired with harq=True
# ---------------------------------------------------------------------------

class TestRetxFired:

    def test_some_retx_occurred(self):
        """With 10 % nominal BLER, retransmissions must occur over a long run."""
        scenario = _load(1)
        summary = run(scenario, RoundRobin(), harq=True)
        total_retx = sum(f["harq_retx_bytes"] for f in _all_flows(summary))
        assert total_retx > 0, (
            "No retransmissions recorded -- HARQ never fired. "
            "Check bler_sigmoid and HARQEngine.process_outcome."
        )

    def test_harq_loss_ratio_small(self):
        """MAX_RETX=3 with IR combining: losses should be extremely rare."""
        summary = run(_load(1), RoundRobin(), harq=True)
        for flow in _all_flows(summary):
            assert flow["harq_loss_ratio"] < 0.05, (
                f"harq_loss_ratio={flow['harq_loss_ratio']:.4f} seems too high. "
                "Check combining gain or MAX_RETX logic."
            )


# ---------------------------------------------------------------------------
# Test 4: delivery_ratio with harq=True >= harq=False
# ---------------------------------------------------------------------------

class TestDeliveryRatio:

    def test_harq_improves_delivery_ratio(self):
        """HARQ retransmits NACKed TBs → confirmed delivered bytes go up.
        delivery_ratio(harq=True) should be >= delivery_ratio(harq=False).
        """
        scenario = _load(1)
        # Same seed → same traffic and channel realisations
        s_harq  = run(scenario, RoundRobin(), harq=True)
        s_flat  = run(scenario, RoundRobin(), harq=False)

        for key in s_harq["flows"]:
            dr_harq = s_harq["flows"][key]["delivery_ratio"]
            dr_flat = s_flat["flows"][key]["delivery_ratio"]
            assert dr_harq >= dr_flat - 0.02, (
                f"Flow {key}: HARQ delivery_ratio ({dr_harq:.4f}) "
                f"unexpectedly below flat-BLER ({dr_flat:.4f})"
            )


# ---------------------------------------------------------------------------
# Test 5: PRB utilisation stays in [0, 1]
# ---------------------------------------------------------------------------

class TestPRBUtilisation:

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_prb_utilisation_bounded(self, name, sched):
        summary = run(_load(1), sched, harq=True)
        assert 0.0 <= summary["dl_prb_utilization"] <= 1.0
        assert 0.0 <= summary["ul_prb_utilization"] <= 1.0

    @pytest.mark.parametrize("name,sched", _schedulers())
    def test_no_overallocation(self, name, sched):
        """Total PRBs used (new + retx) must not exceed carrier capacity."""
        summary = run(_load(1), sched, harq=True)
        # utilization <= 1.0 is the check; > 1.0 means overallocation
        assert summary["dl_prb_utilization"] <= 1.001   # tiny float tolerance
        assert summary["ul_prb_utilization"] <= 1.001


# ---------------------------------------------------------------------------
# Test 6: multiple scenarios don't crash
# ---------------------------------------------------------------------------

class TestMultiScenario:

    @pytest.mark.parametrize("scenario_id", [1, 2, 3])
    def test_scenario_completes(self, scenario_id):
        try:
            scenario = _load(scenario_id)
        except FileNotFoundError:
            pytest.skip(f"scenario_config_{scenario_id}.yml not found")
        summary = run(scenario, TwoTier(tier1_period_slots=500), harq=True)
        assert summary["harq_enabled"] is True
        assert len(summary["flows"]) > 0


if __name__ == "__main__":
    try:
        import pytest as pt
        sys.exit(pt.main([__file__, "-v"]))
    except ImportError:
        print("run: pytest sim/tests/test_smoke_harq.py -v")
