"""Unit tests for scheduler/link.py -- HARQ additions.

Run from the project root:
    pytest sim/tests/test_link.py -v

Or run this file directly:
    python sim/tests/test_link.py
"""
import pytest
import math
import sys
from pathlib import Path

# Allow running directly from the project root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scheduler.link import bler_sigmoid, combining_gain_db, bits_per_prb


# ---------------------------------------------------------------------------
# bler_sigmoid
# ---------------------------------------------------------------------------

class TestBlerSigmoid:

    def test_nominal_operating_point(self):
        """At delta=0 the BLER must be exactly 0.10 (link adaptation target)."""
        assert abs(bler_sigmoid(0.0) - 0.10) < 1e-9

    def test_good_channel_low_bler(self):
        """3 dB above EWMA → BLER well below 1 %."""
        assert bler_sigmoid(3.0) < 0.01

    def test_very_good_channel_near_zero(self):
        """6 dB above EWMA → BLER essentially zero."""
        assert bler_sigmoid(6.0) < 0.001

    def test_bad_channel_high_bler(self):
        """3 dB below EWMA → BLER should be noticeably above nominal."""
        assert bler_sigmoid(-3.0) > 0.10

    def test_deep_fade_ceiling(self):
        """Deep fade → BLER approaches but does not exceed 0.20."""
        assert bler_sigmoid(-10.0) <= 0.20
        assert bler_sigmoid(-10.0) > 0.19

    def test_monotone_decreasing(self):
        """BLER must decrease as delta_snr increases."""
        deltas = [-6, -3, 0, 3, 6]
        blers  = [bler_sigmoid(d) for d in deltas]
        for a, b in zip(blers, blers[1:]):
            assert a > b, f"BLER not decreasing: {a} -> {b}"

    def test_output_range(self):
        """BLER must stay in [0, 0.20] for all reasonable inputs."""
        for delta in range(-20, 21):
            b = bler_sigmoid(float(delta))
            assert 0.0 <= b <= 0.20, f"BLER={b} out of range at delta={delta}"

    def test_steepness_parameter(self):
        """Higher steepness → steeper cliff → lower BLER at +3 dB."""
        gentle = bler_sigmoid(3.0, steepness=0.5)
        steep  = bler_sigmoid(3.0, steepness=2.5)
        assert steep < gentle


# ---------------------------------------------------------------------------
# combining_gain_db
# ---------------------------------------------------------------------------

class TestCombiningGain:

    def test_first_attempt_zero_gain(self):
        """retx_count=0 (first attempt) must have zero combining gain."""
        assert combining_gain_db(0, mode="ir")    == 0.0
        assert combining_gain_db(0, mode="chase") == 0.0

    def test_chase_linear(self):
        """Chase combining: gain increases by exactly 3 dB per retx."""
        for r in range(1, 4):
            assert combining_gain_db(r, mode="chase") == pytest.approx(3.0 * r)

    def test_ir_first_retx_higher_than_chase(self):
        """IR first retx gain must exceed chase (4.0 > 3.0 dB)."""
        assert combining_gain_db(1, mode="ir") > combining_gain_db(1, mode="chase")

    def test_ir_monotone_increasing(self):
        """IR combining gain must be non-decreasing with retx count."""
        gains = [combining_gain_db(r, mode="ir") for r in range(4)]
        for a, b in zip(gains, gains[1:]):
            assert b >= a

    def test_ir_saturates(self):
        """IR gain beyond MAX_RETX=3 should not grow unboundedly."""
        gain_3 = combining_gain_db(3, mode="ir")
        gain_4 = combining_gain_db(4, mode="ir")   # beyond table
        assert gain_4 == gain_3                     # clamped at max


# ---------------------------------------------------------------------------
# HARQ process simulation: verify BLER drops across attempts
# ---------------------------------------------------------------------------

class TestHARQRetxBler:

    def test_bler_drops_with_retx_at_nominal_snr(self):
        """At nominal SNR (delta=0), each retx attempt must have lower BLER
        than the previous one (IR mode)."""
        delta = 0.0
        blers = [
            bler_sigmoid(delta + combining_gain_db(r, mode="ir"))
            for r in range(4)
        ]
        for i, (a, b) in enumerate(zip(blers, blers[1:])):
            assert b < a, f"BLER did not drop at retx={i+1}: {a} -> {b}"

    def test_second_attempt_ir_below_1pct(self):
        """At nominal SNR, IR first retx (attempt 2) should have BLER < 1 %."""
        delta  = 0.0
        gain   = combining_gain_db(1, mode="ir")   # 4.0 dB
        bler   = bler_sigmoid(delta + gain)
        assert bler < 0.01

    def test_chase_combining_also_reduces_bler(self):
        """Chase combining also reduces BLER, just less than IR."""
        delta      = 0.0
        bler_orig  = bler_sigmoid(delta + combining_gain_db(0, "chase"))
        bler_retx1 = bler_sigmoid(delta + combining_gain_db(1, "chase"))
        assert bler_retx1 < bler_orig

    def test_ir_better_than_chase_at_first_retx(self):
        """IR should yield lower BLER than chase on the first retx."""
        delta       = 0.0
        bler_ir     = bler_sigmoid(delta + combining_gain_db(1, "ir"))
        bler_chase  = bler_sigmoid(delta + combining_gain_db(1, "chase"))
        assert bler_ir < bler_chase


# ---------------------------------------------------------------------------
# bits_per_prb -- sanity check existing function not broken
# ---------------------------------------------------------------------------

class TestBitsPerPrb:

    def test_below_min_snr_untransmittable(self):
        bits, bler = bits_per_prb(-5.0)
        assert bits == 0
        assert bler == 1.0

    def test_nominal_factory_snr(self):
        """Factory UE at 20 dB SNR should get reasonable bits/PRB."""
        bits, bler = bits_per_prb(20.0)
        assert bits > 0
        assert bler == pytest.approx(0.10)

    def test_monotone_bits_with_snr(self):
        """More SNR → more bits per PRB."""
        snrs = [0, 5, 10, 15, 20, 25]
        bits = [bits_per_prb(s)[0] for s in snrs]
        for a, b in zip(bits, bits[1:]):
            assert b >= a


# ---------------------------------------------------------------------------
# Runner (no pytest required for quick checks)
# ---------------------------------------------------------------------------

def _run_manual():
    """Quick smoke check -- prints a table, no assertions."""
    print("=== bler_sigmoid ===")
    for delta in [-6, -3, 0, 3, 6]:
        print(f"  delta={delta:+3d} dB  BLER={bler_sigmoid(delta):.4f}")

    print("\n=== combining_gain_db ===")
    for r in range(4):
        c  = combining_gain_db(r, "chase")
        ir = combining_gain_db(r, "ir")
        print(f"  retx={r}  chase={c:.1f} dB  IR={ir:.1f} dB")

    print("\n=== BLER across retx attempts (delta=0, IR) ===")
    for r in range(4):
        gain = combining_gain_db(r, "ir")
        b    = bler_sigmoid(0.0 + gain)
        print(f"  attempt {r+1}: gain={gain:.1f} dB  BLER={b:.5f}")


if __name__ == "__main__":
    # Run without pytest: python sim/tests/test_link.py
    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        _run_manual()
