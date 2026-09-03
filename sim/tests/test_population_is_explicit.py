"""A worst-flow statistic has no meaning without the flows it ranges over.

THE DEFECT. Every worst-flow metric in sim/scorecard.py ranged over EVERY
flow in the record, silently. `Scorecard.NON_PROTECTED_5QI = {8, 9}` names
the per-UE best-effort filler and the GT-4.1/4.2 saturating aggressor -- flows
a QoS-aware scheduler is SUPPOSED to starve -- and they were entering the
contest for statistics the guarantees bind to the protected fleet.

MEASURED, not argued. On sweeps/wp9/stage2/stage2_rows.csv (7,560 rows) the
5QI-9 filler wins M01's contest in 85.4 % of runs and the 5QI-1 telemetry
bearer G1 is actually about wins it in 6. On a fresh N=8 run
(scripts/phase2_core.py) the verdict itself inverts, in OPPOSITE directions:

    G1  M01 p98   all-flow 300.00/300.25/300.00 ms  -> FAIL every arm, and
                  the three arms agree to 0.25 ms because the number is
                  pinned at 5QI 9's own 300 ms PDB
                  protected      28.00/22.00/96.75  -> PASS every arm, 4.4x
                  separation
    G8  M09 Jain  all-flow 0.9446/0.9419/0.8783    -> TwoTier FAILS >= 0.9
                  protected 0.9995/0.9998/0.9584   -> TwoTier PASSES

    G3  M03 gap   IDENTICAL under both populations
    G5  M05 frac  IDENTICAL under both populations

THE ASYMMETRY IS THE POINT. If restriction moved everything, it would be a
preference about framing. It moves G1 and G8 -- where the filler was winning
the contest -- and leaves G3 and G5 untouched, because their winners were
already protected bearers. That is what makes it a defect.

WHY REQUIRED RATHER THAN DEFAULTED TO PROTECTED. An unrestricted worst-flow
number is the correct instrument for "is the cell saturated at all". Both
populations are legitimate; what is not legitimate is not saying which. A
default of all-flow is what let this survive nine work packages, and a
default of protected would move the silence rather than remove it.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sim.run_record import RunRecord  # noqa: E402
from sim.scorecard import Population, Scorecard  # noqa: E402


def _flow(ue_id, qfi, *, p99, gaps_s, frames=None, arr=None, dlv=None,
          flow_class="Delay", pdb_ms=100.0):
    ts, t = [], 0.0
    for g in [0.0] + list(gaps_s):
        t += g
        ts.append(t)
    fc = frames or {"total": 0, "complete_ages_ms": [], "complete": 0,
                    "incomplete": 0}
    return {
        "ue_id": ue_id, "qfi": qfi, "direction": "UL", "flow_class": flow_class,
        "priority_level": 20, "pdb_ms": pdb_ms, "gfbr_bps": 0.0,
        "bytes_arrived": 100, "bytes_delivered": 100, "bytes_dropped_pdb": 0,
        "bytes_delivered_late_pdb": 0, "bytes_harq_lost": 0,
        "delivery_ratio": 1.0, "throughput_bps": 1.0, "offered_bps": 1.0,
        "delay_p50_ms": p99 / 2, "delay_p95_ms": p99, "delay_p98_ms": p99,
        "delay_p99_ms": p99, "delay_p50_ms_proxy": p99 / 2,
        "delay_p95_ms_proxy": p99, "delay_p98_ms_proxy": p99,
        "delay_p99_ms_proxy": p99, "survival_time_ms": 0.0,
        "message_count": len(ts), "completion_ts_by_role_s": {"data": ts},
        "frame_completions": fc,
        "ts_arrived_bytes": arr or [10] * 6,
        "ts_delivered_bytes": dlv or [10] * 6,
    }


def _record():
    """The discriminating shape, built deliberately.

    ue9_qfi9  -- NON-PROTECTED filler: worst latency AND worst delivery, so
                 it wins M01 and drags M09. Restriction must remove it.
    ue1_qfi1  -- protected telemetry: worst liveness gap, so it wins M03
                 under BOTH populations. Restriction must not move M03.
    ue2_qfi2  -- protected video: worst frame completeness, so it wins M05
                 under BOTH populations. Restriction must not move M05.
    """
    frames_bad = {"total": 10, "complete_ages_ms": [10.0] * 7 + [999.0] * 3,
                  "complete": 10, "incomplete": 0}
    return RunRecord.from_dict({
        "schema_version": 1, "scenario_name": "toy", "scheduler_name": "PF",
        "seed": 1, "arm": {}, "meta": {},
        "flows": {
            "ue9_qfi9": _flow(9, 9, p99=300.0, gaps_s=[0.05, 0.05],
                              flow_class="PF", pdb_ms=300.0,
                              arr=[10] * 6, dlv=[1, 1, 1, 1, 1, 1]),
            "ue1_qfi1": _flow(1, 1, p99=20.0, gaps_s=[0.40, 0.05]),
            "ue2_qfi2": _flow(2, 2, p99=15.0, gaps_s=[0.05, 0.05],
                              frames=frames_bad, flow_class="GBR"),
        },
        "system": {"horizon_s": 6.0, "dl_prb_utilization": 0.0,
                   "ul_prb_utilization": 0.0, "cce_utilization": 0.0},
        "timeseries_time_s": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
    })


def test_score_refuses_to_compute_without_an_explicit_population():
    """A missing population is a LOUD ERROR, not a quiet default.

    This is the whole fix. The value of a worst-flow statistic depends on
    which flows it ranges over, so a caller that does not say has not asked
    a well-formed question.
    """
    with pytest.raises(TypeError):
        Scorecard().score(_record())          # no population -> refuse


def test_population_travels_with_every_population_sensitive_value():
    """Reported inline, the way M03/M14 already report t_live_s and
    survival_time_ms -- never a bare number."""
    out = Scorecard().score(_record(), population=Population.all_flows())
    for mid in ("M01", "M03", "M05", "M08", "M09", "M15"):
        r = out.get(mid)
        assert r is not None, mid
        assert r.population == "all_flows", (mid, r.population)


def test_restriction_inverts_g1_and_g8_and_leaves_g3_and_g5_alone():
    """THE ASYMMETRY. Verified against Phase 2's measured run before being
    written here; a future change that silently re-broadens the population
    breaks this rather than moving a number quietly."""
    card = Scorecard()
    every = card.score(_record(), population=Population.all_flows())
    prot = card.score(_record(), population=Population.protected_fleet())

    # G1 MOVES: the filler wins the all-flow contest and is gone from the
    # protected one.
    assert every["M01"].value["flow"] == "ue9_qfi9"
    assert prot["M01"].value["flow"] != "ue9_qfi9"
    assert prot["M01"].value["p99"] < every["M01"].value["p99"]

    # G8 MOVES: the filler's starved delivery drags the all-flow index.
    assert prot["M09"].value["worst"] > every["M09"].value["worst"]

    # G3 DOES NOT MOVE: its winner was already a protected bearer.
    assert every["M03"].value["flow"] == prot["M03"].value["flow"] == "ue1_qfi1"
    assert every["M03"].value["max_gap_ms"] == prot["M03"].value["max_gap_ms"]

    # G5 DOES NOT MOVE: same reason.
    assert every["M05"].value["flow"] == prot["M05"].value["flow"] == "ue2_qfi2"
    assert every["M05"].value["fraction"] == prot["M05"].value["fraction"]


def test_protected_fleet_population_excludes_exactly_the_registered_5qis():
    """Derived from Scorecard.NON_PROTECTED_5QI, never restated -- CLAUDE.md's
    count rule, whose fourth and fifth instances were both in test code."""
    p = Population.protected_fleet()
    assert p.excluded_5qi == Scorecard.NON_PROTECTED_5QI
    assert Population.all_flows().excluded_5qi == frozenset()


def test_every_panel_metric_records_which_population_its_guarantee_binds():
    """A new metric must DECLARE its population, not inherit one.

    Derived from the panel rather than restated -- the fifth instance of
    CLAUDE.md's restated-count rule was a test asserting `len(...) == 21`,
    which fired on the one operation the append-only panel permits. This
    asserts a PROPERTY of every row instead of a count of rows, so it stays
    correct as the panel grows.
    """
    from sim.scorecard import load_panel
    panel = load_panel()
    missing = [m["id"] for m in panel["metrics"] if not m.get("population")]
    assert not missing, (
        f"metric(s) {missing} declare no `population`. Every metric whose "
        f"value depends on which flows are in the record must record which "
        f"population its guarantee binds -- a blank is indistinguishable "
        f"from the unstated default this field exists to abolish.")
    allowed = {"protected_fleet", "all_flows", "named_flow_pair"}
    bad = {m["id"]: m["population"] for m in panel["metrics"]
           if m["population"] not in allowed}
    assert not bad, f"unrecognised population(s): {bad}; allowed {sorted(allowed)}"


def test_population_sensitive_set_matches_what_score_actually_stamps():
    """The set that drives the restriction is the set that drives the stamp.

    They are one constant (Scorecard.POPULATION_SENSITIVE) precisely so a
    result cannot report a population it was not computed over -- the failure
    mode M20 had, where it delegated to M03 and then built a fresh result
    that silently dropped what M03 had derived.
    """
    out = Scorecard().score(_record(), population=Population.protected_fleet())
    stamped = {mid for mid, r in out.items() if r.population is not None}
    expected = Scorecard.POPULATION_SENSITIVE & set(out)
    assert stamped == expected, (
        f"stamped-but-not-declared: {sorted(stamped - expected)}; "
        f"declared-but-not-stamped: {sorted(expected - stamped)}")
    # And the system-level metrics must NOT claim one.
    for mid in ("M10", "M11", "M12"):
        assert out[mid].population is None, mid
