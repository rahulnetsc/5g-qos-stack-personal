"""sim/workload.py -- committed-load scaling and spec-derived survival time.

The coverage test is the point: LOAD_PARAMS is an enumeration over a set
`sim/traffic.py` defines, so it can silently reach less than it claims. It
is derived from that file's own dispatch here, not restated.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from scheduler.flow import FlowConfig
from sim.parametric import sweep_scenario
from sim.workload import (COMMITTED_CLASSES, INTERVAL_PARAMS, LOAD_PARAMS,
                          scale_committed_load, survival_time_ms_for,
                          with_survival_times)

REPO = pathlib.Path(__file__).resolve().parents[2]

from sim.tests.test_flow_key_collision_sweep import _cases  # noqa: E402
_CASES = _cases()


def _kinds_traffic_dispatches_on() -> set[str]:
    """Every literal `kind` compared in sim/traffic.py's `_gen`, from its AST
    -- never a grep and never a list written here."""
    tree = ast.parse((REPO / "sim" / "traffic.py").read_text())
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_gen")
    kinds: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        left = node.left
        if not (isinstance(left, ast.Name) and left.id == "kind"):
            continue
        for comp in node.comparators:
            if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                kinds.add(comp.value)
            elif isinstance(comp, (ast.Tuple, ast.List)):
                kinds.update(e.value for e in comp.elts
                             if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return kinds


def test_load_params_covers_every_traffic_kind_the_model_dispatches_on():
    kinds = _kinds_traffic_dispatches_on()
    assert kinds, "the AST scan found no kinds -- the scan is broken, not the map"
    missing = kinds - set(LOAD_PARAMS)
    assert not missing, (
        f"traffic kinds {sorted(missing)} have no LOAD_PARAMS entry: "
        f"scale_committed_load would pass them through UNSCALED while "
        f"reporting the scenario scaled")
    assert set(INTERVAL_PARAMS) <= set(LOAD_PARAMS)


def test_an_unknown_kind_fails_loudly_rather_than_passing_through():
    f = FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="Delay",
                   traffic_kind="nonesuch", traffic_params={"bytes_per_period": 10})
    from sim.config import ScenarioConfig
    sc = ScenarioConfig(name="t", horizon_slots=10, flows=[f])
    with pytest.raises(ValueError, match="LOAD_PARAMS"):
        scale_committed_load(sc, 2.0)


def test_committed_scaling_moves_demand_and_contract_together_and_spares_best_effort():
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=2000)
    x2 = scale_committed_load(sc, 2.0)
    assert sc.name != x2.name and x2.name.endswith("_cm2")
    for a, b in zip(sc.flows, x2.flows):
        if a.flow_class in COMMITTED_CLASSES:
            if a.gfbr_bps:
                assert b.gfbr_bps == pytest.approx(2 * a.gfbr_bps)
            if a.mfbr_bps:
                assert b.mfbr_bps == pytest.approx(2 * a.mfbr_bps)
            for key in LOAD_PARAMS[a.traffic_kind]:
                if key in (a.traffic_params or {}):
                    assert b.traffic_params[key] == pytest.approx(
                        2 * a.traffic_params[key])
        else:
            assert b is a, "best-effort is load_mult's axis, not committed_mult's"


def test_identity_at_one_is_the_same_object():
    sc = sweep_scenario(seed=1, n_ues=4, horizon_slots=2000)
    assert scale_committed_load(sc, 1.0) is sc
    with pytest.raises(ValueError):
        scale_committed_load(sc, 0.0)


def test_survival_time_is_the_flow_s_own_transfer_interval():
    """TS 122 261 §3.1: the time an application may continue WITHOUT AN
    ANTICIPATED MESSAGE. One interval per message, from the flow's period."""
    periodic = FlowConfig(ue_id=1, qfi=1, direction="UL", flow_class="Delay",
                          traffic_kind="periodic_control",
                          traffic_params={"period_ms": 100.0, "bytes_per_period": 300})
    assert survival_time_ms_for(periodic, 1.0) == 100.0
    assert survival_time_ms_for(periodic, 2.5) == 250.0
    assert survival_time_ms_for(periodic, 0.0) == 0.0
    aperiodic = FlowConfig(ue_id=1, qfi=9, direction="UL", flow_class="PF",
                           traffic_kind="poisson", traffic_params={"rate_bps": 1e6})
    assert survival_time_ms_for(aperiodic, 1.0) == 0.0, "no anticipated message"
    with pytest.raises(ValueError):
        survival_time_ms_for(periodic, -1.0)


def test_with_survival_times_populates_every_periodic_flow():
    sc = with_survival_times(sweep_scenario(seed=1, n_ues=4, horizon_slots=2000), 1.0)
    periodic = [f for f in sc.flows if f.traffic_kind in INTERVAL_PARAMS]
    assert periodic and all(f.survival_time_ms > 0 for f in periodic)
    assert all(f.survival_time_ms == f.traffic_params["period_ms"] for f in periodic)
    assert all(f.survival_time_ms == 0.0 for f in sc.flows
               if f.traffic_kind not in INTERVAL_PARAMS)


def _offered_bps(f):
    """Offered load of a periodic flow, from its own traffic params."""
    p = f.traffic_params or {}
    k = f.traffic_kind
    if k in ("xr_video", "video_frame"):
        return p["avg_bytes"] * 8 / (p.get("period_ms", 16.67) / 1000.0)
    if k in ("deterministic", "periodic_control", "condition_monitor"):
        return p["bytes_per_period"] * 8 / (p["period_ms"] / 1000.0)
    if k == "poisson":
        return p["rate_bps"]
    return None


def test_min_bytes_per_period_for_gfbr_never_rounds_short():
    from sim.workload import min_bytes_per_period_for_gfbr as f
    for gfbr, period in ((4e6, 33.0), (6e6, 33.33), (6.5e6, 33.33), (20e6, 16.67),
                         (3e6, 20.0), (8e6, 33.33), (14e6, 33.33)):
        b = f(gfbr, period)
        assert b * 8 / (period / 1000.0) >= gfbr, (gfbr, period, b)
    with pytest.raises(ValueError):
        f(0.0, 33.0)
    with pytest.raises(ValueError):
        f(4e6, 0.0)


@pytest.mark.parametrize("label,sc", _CASES, ids=[c[0] for c in _CASES])
def test_no_gbr_flow_offers_below_its_own_contract(label, sc):
    """THE INVARIANT, over every builder the flow-key sweep proves it covers.

    A GBR flow offering less than its own GFBR can never meet its contract at
    any load on any scheduler, so every metric that reads contract attainment
    (M07, M13 -- and therefore G10 and G12) measures the traffic generator
    instead. Six flow definitions across five builders had this shape before
    2026-09-08; this test is what stops a seventh appearing silently.
    """
    for f in sc.flows:
        if f.flow_class != "GBR" or not f.gfbr_bps:
            continue
        offered = _offered_bps(f)
        if offered is None:
            continue
        assert offered >= f.gfbr_bps * 0.99999, (
            f"{label}: ue{f.ue_id} 5QI {f.qfi} ({f.traffic_kind}) offers "
            f"{offered/1e6:.4f} Mbps against a {f.gfbr_bps/1e6:.4f} Mbps GFBR "
            f"-- an arithmetic ceiling of {offered/f.gfbr_bps:.4f} on "
            f"gfbr_fraction that no scheduler can lift")
