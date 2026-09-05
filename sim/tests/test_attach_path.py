"""Model C's attach seed, and the conditions fixed before any number was read.

`docs/attach-path-map.md` §3. Two of these matter more than the rest:

  * OFF BY DEFAULT AND BIT-IDENTICAL WHEN OFF. The experiment compares
    against every artefact this project has already published, so a
    mechanism that perturbs a run with the path disabled would invalidate
    the baseline it is being compared to.
  * THE SEED MUST NOT SILENTLY NO-OP. A seed written against an empty
    buffer writes an all-zero array, clears nothing, and looks EXACTLY like
    the treatment having failed -- outcome A3 in the map, the strongest
    result available, reached by a bug. So `seed_attach_bsr` returns
    whether it wrote anything, the driver only marks a UE seeded when it
    did, and the test below asserts the array is non-zero for the attaching
    UE at the slot it seeds.
"""

from __future__ import annotations

import json

import pytest

from scheduler.reservation import Reservation
from scheduler.two_tier import TwoTier
from sim.baselines.pf import ProportionalFair
from sim.bsr import LCG_COUNT
from sim.driver import run
from sim.parametric import sweep_scenario
from sim.run_record import RunRecord

ARMS = {
    "PF": lambda: ProportionalFair(ewma_window_slots=200),
    "Reservation": lambda: Reservation(min_rb=5),
    "TwoTier": lambda: TwoTier(min_rb=5),
}


def _sc(h=4000, n=4):
    return sweep_scenario(seed=1, n_ues=n, horizon_slots=h, load_mult=1.0)


def _rec(summary, sc, arm):
    return RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                  seed=1, flow_configs=sc.flows,
                                  summary=summary, arm={}, meta={})


# --- OFF BY DEFAULT, AND BIT-IDENTICAL WHEN OFF ---------------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_off_by_default_is_bit_identical(arm):
    """`attach_seed_slots=None` must be the pre-Model-C run exactly."""
    sc = _sc()
    a = run(sc, ARMS[arm](), cqi_delay_slots=8, record_timeseries=True)
    b = run(_sc(), ARMS[arm](), cqi_delay_slots=8, record_timeseries=True,
            attach_seed_slots=None)
    # Compared as RunRecords, NOT as the raw summary: `summary` carries live
    # objects (`_ue_lcp`, `_message_ledger`) whose repr() embeds a memory
    # address, so `json.dumps(summary, default=str)` differs between two
    # IDENTICAL runs. Found building this test (defects-log #26) -- the same
    # `default=` serialization-fallback trap CLAUDE.md already records for
    # RunLedger.bank(), one layer over.
    ra = json.dumps(_rec(a, sc, arm).to_dict(), sort_keys=True, default=str)
    rb = json.dumps(_rec(b, sc, arm).to_dict(), sort_keys=True, default=str)
    assert ra == rb


def test_the_seed_counters_are_ABSENT_when_the_path_is_off():
    """An absent key means "not configured"; a present 0 means "configured
    and never fired". Conflating those two is how five mechanisms in this
    project became unobservable."""
    s = run(_sc(), ProportionalFair(), cqi_delay_slots=8)
    assert "attach_seeds_fired" not in s
    s2 = run(_sc(), ProportionalFair(), cqi_delay_slots=8,
             attach_seed_slots={1: 0})
    assert s2["attach_seeds_fired"] >= 0
    assert s2["attach_seeds_expected"] == 1


# --- IT MUST ACTUALLY FIRE, AND WRITE SOMETHING ---------------------------

@pytest.mark.parametrize("arm", sorted(ARMS))
def test_the_seed_fires_for_EVERY_scheduled_ue_not_merely_some(arm):
    """Assert the EXPECTED COUNT, derived from the scenario, not non-zero.
    `docs/wp9-plan.md` §34.5: "did it fire at all" is a weaker question than
    "did it fire as often as the schedule specifies", and the gap between
    them is where a partially-degenerate run hides."""
    sc = _sc()
    ul_ues = sorted({f.ue_id for f in sc.flows if f.direction == "UL"})
    s = run(sc, ARMS[arm](), cqi_delay_slots=8, record_timeseries=True,
            attach_seed_slots={u: 0 for u in ul_ues})
    assert s["attach_seeds_expected"] == len(ul_ues)
    assert s["attach_seeds_fired"] == len(ul_ues), \
        f"{arm}: {s['attach_seeds_fired']} of {len(ul_ues)} UEs seeded"
    assert s["attach_seeded_ues"] == ul_ues


def test_the_seeded_array_is_NON_ZERO_at_the_slot_it_is_written():
    """THE NO-OP GUARD. A seed against an empty backlog writes an all-zero
    array -- which clears nothing and is indistinguishable from outcome A3
    (the strongest available result) reached by a bug."""
    from sim.bsr import BsrModel
    from sim.buffer import BufferModel

    sc = _sc()
    flows = [f for f in sc.flows if f.direction == "UL"]
    buffers = BufferModel()
    for x in flows:
        buffers.register(x.ue_id, x.qfi, is_ul=True, lcg=x.lcg)
    bsr = BsrModel(sc.flows, slot_duration_s=0.00025)

    # Empty backlog: the seed must REFUSE rather than write zeros.
    assert bsr.seed_attach_bsr(flows[0].ue_id, buffers) is False

    # With backlog it must write, and the array must be non-zero.
    f = flows[0]
    buffers.enqueue(f.ue_id, f.qfi, 20_000, 0.0)
    assert bsr.seed_attach_bsr(f.ue_id, buffers) is True
    st = bsr._state[f.ue_id]
    assert sum(st.estimated_ul_buffer_per_lcg) > 0
    assert st.estimated_ul_buffer > 0
    assert st.estimated_ul_buffer_per_lcg[f.lcg] > 0
    assert len(st.estimated_ul_buffer_per_lcg) == LCG_COUNT
    # The C zeroes sched_ul_bytes on every BSR; without it broadcast()'s own
    # B gate would cap the fresh array straight back toward zero.
    assert st.sched_ul_bytes == 0


def test_the_seed_quantises_like_a_real_bsr_and_is_not_privileged():
    """A seed more informative than a real BSR would clear the starvation
    for a reason hardware does not have -- the one way this experiment could
    answer its own question wrongly."""
    from sim.bsr import BsrModel, quantise_long
    from sim.buffer import BufferModel

    sc = _sc()
    f = [x for x in sc.flows if x.direction == "UL"][0]
    buffers = BufferModel()
    # Every UL flow of this UE, because seed_attach_bsr aggregates per LCG
    # across all of them -- registering only the one under test would make
    # the seed raise rather than quantise.
    for x in sc.flows:
        if x.direction == "UL":
            buffers.register(x.ue_id, x.qfi, is_ul=True, lcg=x.lcg)
    buffers.enqueue(f.ue_id, f.qfi, 12_345, 0.0)
    bsr = BsrModel(sc.flows, slot_duration_s=0.00025)
    assert bsr.seed_attach_bsr(f.ue_id, buffers) is True
    got = bsr._state[f.ue_id].estimated_ul_buffer_per_lcg[f.lcg]
    assert got == quantise_long(12_345), "the seed bypassed quantisation"


# --- STAGGERED ARRIVAL USES THE EXISTING GATE, NOT A NEW MECHANISM --------

def test_staggered_arrival_is_the_existing_activation_window():
    """`active_from_s` already gates traffic generation (WP9 G11 commit 4),
    so a UE that has not attached simply has no backlog, is not a candidate
    and needs no masking mechanism at all."""
    import dataclasses
    sc = _sc(h=4000, n=4)
    flows = []
    for f in sc.flows:
        if f.direction == "UL" and f.ue_id == 4:
            p = dict(f.traffic_params)
            p["active_from_s"] = 0.5
            f = dataclasses.replace(f, traffic_params=p)
        flows.append(f)
    sc2 = dataclasses.replace(sc, flows=flows)
    s = run(sc2, ProportionalFair(), cqi_delay_slots=8,
            record_timeseries=True)
    late = [k for k in s["flows"] if k.startswith("ue4_")]
    assert late, "no ue4 flows in the summary"
    # 4000 slots * 0.25 ms = 1.0 s, so a 0.5 s gate must roughly halve it.
    a = s["flows"]["ue4_qfi2"]["bytes_arrived"]
    b = s["flows"]["ue3_qfi2"]["bytes_arrived"]
    assert 0 < a < b, f"gate did not delay ue4 (a={a}, b={b})"
