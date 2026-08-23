from sim.cycle_clock import phase_offset_slots


def test_phase_offset_slots_truncates_like_other_period_conversions():
    assert phase_offset_slots(5.0, slot_duration_s=0.0005) == 10
    assert phase_offset_slots(0.0, slot_duration_s=0.0005) == 0


def test_phase_offset_slots_truncates_towards_zero_on_partial_slots():
    # 4.9ms / 0.5ms = 9.8 slots -> truncates to 9, same convention as every
    # other period_ms-to-slots conversion in sim/traffic.py.
    assert phase_offset_slots(4.9, slot_duration_s=0.0005) == 9
