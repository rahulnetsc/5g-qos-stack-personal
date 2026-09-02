"""The drift detector must be able to SEE drift. That is the whole guard.

WP9 G11 commit 7. A detector that cannot return non-flat on a drifting
input cannot report the leak it exists to find -- CLAUDE.md's
could-have-failed rule, applied to an instrument before it is trusted.

The ramp/flat PAIR is the check: either test alone passes for the wrong
reason (a detector that always says "drift" passes the ramp; one that
always says "flat" passes the flat series).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from g11_drift import drift_verdict, theil_sen_slope, trend


def test_a_ramp_is_detected_with_an_interval_excluding_zero():
    r = trend([10 + 2 * k for k in range(30)])
    assert r["value"] > 0
    assert r["excludes_zero"], f"a clean ramp was not detected: {r}"
    assert r["lo"] > 0


def test_a_flat_series_with_noise_is_NOT_detected():
    noise = [5.0, 5.2, 4.8, 5.1, 4.9, 5.0, 5.3, 4.7, 5.1, 4.95] * 3
    r = trend(noise)
    assert not r["excludes_zero"], f"noise reported as drift: {r}"


def test_a_downward_ramp_is_detected_too():
    r = trend([100 - 3 * k for k in range(30)])
    assert r["value"] < 0 and r["excludes_zero"] and r["hi"] < 0


def test_a_constant_series_is_NOT_scored_as_stable():
    """No dynamic range: 'no drift' would describe the counter, not the run."""
    r = trend([0.0] * 30)
    assert r["value"] is None
    assert "NO DYNAMIC RANGE" in r["reason"]


def test_too_few_windows_is_declared_not_guessed():
    r = trend([1.0, 2.0])
    assert r["value"] is None and "needs >=3" in r["reason"]


def test_theil_sen_ignores_a_single_spike():
    clean = [1.0 * k for k in range(20)]
    spiked = list(clean)
    spiked[7] = 500.0
    assert abs(theil_sen_slope(range(20), spiked)
               - theil_sen_slope(range(20), clean)) < 0.05


def test_the_verdict_is_per_internal_and_carries_its_coverage():
    v = drift_verdict({
        "crumb_rate": [1 + 0.5 * k for k in range(20)],   # drifting
        "floor_fire_rate": [0.0] * 20,                    # exists, no range
        "skip_reasons": None,                             # does not exist
    })
    assert v["verdict"] == "DRIFT"
    assert v["drifting"] == ["crumb_rate"]
    assert v["n_scored"] == 1 and v["n_named_by_GT_7_1"] == 3
    assert v["coverage"] == "1 of 3 internals GT-7.1 names"
    assert v["per_internal"]["skip_reasons"]["scored"] is False
    assert "hardware log field" in v["per_internal"]["skip_reasons"]["reason"]
    assert v["per_internal"]["floor_fire_rate"]["scored"] is False


def test_all_flat_reports_NO_DRIFT_rather_than_silence():
    v = drift_verdict({"crumb_rate": [5.0, 5.1, 4.9, 5.0, 5.2, 4.8] * 4})
    assert v["verdict"] == "NO DRIFT" and v["n_drifting"] == 0
