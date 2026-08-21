"""Scheduler study: which scheduler to build, and under what conditions.

Four studies, each framed as an engineering decision rather than a metric
dump:

  1. Overload sweep -- how the PF-vs-TwoTier gap depends on how overloaded
     the cell is. Establishes the regime where a QoS-aware scheduler earns
     its complexity.
  2. PDCCH-limited (sensor_dense) -- many small periodic flows where the
     control channel, not the data channel, is the bottleneck.
  3. Latency-bound -- tight-PDB control loops sharing a congested downlink
     with bulk traffic. Tests deadline awareness.
  4. Uplink access chain (WP4) -- offered load x SR periodicity grid,
     testing whether this simulator reproduces the branch's one real
     calibration target: hardware's load-inverted UL p99
     (docs/p5g-sim-plan.md sec 3.3, README sec 7/8). No existing study
     sweeps offered load (study 1 sweeps carrier capacity instead), and
     sr_period_slots has no ground truth (README sec 8) -- swept
     explicitly here rather than defaulted silently, per the WP4 plan.

Metrics are contract-oriented: for a GBR flow the contract is its GFBR;
for a Delay flow it is on-time delivery within the PDB. Mean delivery
ratio and total throughput are reported too, but they are PF-friendly
aggregates -- they reward spreading -- so contract counts and p99 latency
are what the recommendations key off.

Usage:
    python scripts/scheduler_study.py
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.config import ScenarioConfig
from sim.driver import run
from sim.scenarios import (
    factory_robots_scenario,
    latency_bound_scenario,
    sensor_dense_scenario,
)
from sim.baselines.pf import ProportionalFair
from sim.baselines.round_robin import RoundRobin
from scheduler import load_two_tier

# TwoTier is configured from the reference YAML in scheduler/, so every
# study run uses the shipped defaults documented alongside the code
# (see scheduler/scheduler_config.yaml). Sensitivity rows override
# individual keys via kwargs to load_two_tier.
SCHEDULER_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

# GBR rate contract is "met" at >= this fraction of GFBR.
GBR_CONTRACT_FRACTION = 0.95
# Delay flow is "on time" at >= this delivery ratio with p99 HoL <= PDB.
DELAY_ONTIME_DELIVERY = 0.99
# UL BSR realism (WP3) is not a delay-slots knob -- sim/bsr.py always
# models the per-LCG, quantised, event-riding-on-a-grant BSR path, driven
# by each flow's FlowConfig.lcg. Configured Grants still bypass it entirely
# (a CG UE needs no BSR), the whole point of SPS in real 5G.

# DL CQI reporting latency in slots. Real 5G reports CQI on a period of
# 5-160 ms; at mu=1 that's 10-320 slots. 8 slots (~4 ms) is a periodic-CQI
# lower bound representative of an aperiodic-CQI-triggered flow. The effect
# in these scenarios is small because the channel coherence is long
# (2000 slots) so the CQI barely goes stale -- see scripts/cqi_study.py for
# the sensitivity to shorter coherence and to sps_snr_margin_db.
CQI_DELAY_SLOTS = 8


def _pf():
    return ProportionalFair(ewma_window_slots=200)


def _tt(**overrides):
    return load_two_tier(SCHEDULER_CONFIG, **overrides)


def _flow_meta(scenario: ScenarioConfig) -> dict:
    """fk -> (flow_class, gfbr_bps, pdb_ms, direction)."""
    meta = {}
    for f in scenario.flows:
        meta[f"ue{f.ue_id}_qfi{f.qfi}"] = (
            f.flow_class, f.gfbr_bps, f.pdb_ms, f.direction
        )
    return meta


def _scale_capacity(scenario: ScenarioConfig, mult: float) -> ScenarioConfig:
    """Return the scenario with its carrier bandwidth scaled by mult."""
    carrier = dataclasses.replace(
        scenario.carrier,
        bandwidth_hz=int(scenario.carrier.bandwidth_hz * mult),
    )
    return dataclasses.replace(scenario, carrier=carrier)


def _scale_ul_load(scenario: ScenarioConfig, mult: float) -> ScenarioConfig:
    """Return the scenario with every UL flow's deterministic traffic
    volume scaled by mult, capacity held fixed -- the load-axis analogue of
    _scale_capacity's capacity-axis scaling, "around the as-configured
    point (1.0x)" the same way. Only `deterministic` traffic_kind flows are
    scaled (bytes_per_period); this study's base scenario uses only that
    kind for its UL flows."""
    new_flows = []
    for f in scenario.flows:
        if f.direction == "UL" and f.traffic_kind == "deterministic":
            params = dict(f.traffic_params)
            params["bytes_per_period"] = params["bytes_per_period"] * mult
            f = dataclasses.replace(f, traffic_params=params)
        new_flows.append(f)
    return dataclasses.replace(scenario, flows=new_flows)


def _profile(scenario: ScenarioConfig, summary: dict) -> dict:
    """Contract-oriented rollup of one run."""
    meta = _flow_meta(scenario)
    flows = summary["flows"]
    total_bps = sum(f["throughput_bps"] for f in flows.values())

    gbr, delay = [], []
    for fk, m in flows.items():
        flow_class, gfbr, pdb_ms, _ = meta[fk]
        if flow_class == "GBR":
            met = m["throughput_bps"] >= GBR_CONTRACT_FRACTION * gfbr
            gbr.append((fk, m, met))
        elif flow_class == "Delay":
            ontime = (
                m["delivery_ratio"] >= DELAY_ONTIME_DELIVERY
                and m["hol_p99_ms"] <= pdb_ms
            )
            delay.append((fk, m, ontime))

    def _agg(rows):
        if not rows:
            return None
        return {
            "n": len(rows),
            "met": sum(1 for *_, ok in rows if ok),
            "mean_delivery": sum(m["delivery_ratio"] for _, m, _ in rows)
            / len(rows),
            "min_delivery": min(m["delivery_ratio"] for _, m, _ in rows),
            "worst_p99": max(m["hol_p99_ms"] for _, m, _ in rows),
        }

    return {
        "total_mbps": total_bps / 1e6,
        "gbr": _agg(gbr),
        "delay": _agg(delay),
        "dl_util": summary["dl_prb_utilization"],
        "ul_util": summary["ul_prb_utilization"],
        "cce_util": summary["cce_utilization"],
    }


def _hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def study_overload_sweep() -> None:
    _hr("STUDY 1 -- Overload sweep (10-robot factory scenario)")
    print(
        "Carrier capacity scaled around the as-configured point (1.0x).\n"
        "GBR contract = delivered throughput >= 95% of GFBR.\n"
    )
    base = factory_robots_scenario()
    # TwoTier ships with the max-min GBR stage on. The two comparison rows
    # pin it off: one isolates what the stage buys, the other keeps the
    # adaptive-penalty negative result (section 8.4) a like-for-like
    # comparison against the same single-stage baseline.
    scheds = [
        ("PF", _pf),
        ("TwoTier", lambda: _tt()),
        ("TwoTier-nomaxmin", lambda: _tt(gbr_maxmin=False)),
        ("  +adaptive", lambda: _tt(gbr_maxmin=False, gbr_penalty_lr=1e5)),
    ]
    print(
        f"{'capacity':>9}  {'scheduler':<18}{'total':>9}"
        f"{'GBR met':>10}{'mean GBR':>10}{'min GBR':>9}{'worst p99':>11}"
    )
    for mult in (1.0, 1.5, 2.0, 3.0):
        sc = _scale_capacity(base, mult)
        for name, factory in scheds:
            p = _profile(sc, run(sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS))
            g = p["gbr"]
            print(
                f"{mult:>8.1f}x  {name:<18}{p['total_mbps']:>7.1f}M"
                f"{g['met']:>7}/{g['n']:<2}{g['mean_delivery']:>9.0%}"
                f"{g['min_delivery']:>8.0%}{g['worst_p99']:>9.0f}ms"
            )
        print()


def study_pdcch_limited() -> None:
    _hr("STUDY 2 -- PDCCH-limited (30 dense sensors)")
    print(
        "Many small periodic UL flows; the per-slot DCI/CCE budget binds\n"
        "before the data channel does. Delay contract = >=99% on-time "
        "within the 15 ms PDB.\n"
    )
    sc = sensor_dense_scenario()
    scheds = [("RoundRobin", RoundRobin), ("PF", _pf), ("TwoTier", _tt)]
    print(
        f"{'scheduler':<14}{'total':>9}{'on-time':>10}"
        f"{'mean deliv':>12}{'min deliv':>11}{'worst p99':>11}"
    )
    for name, factory in scheds:
        p = _profile(sc, run(sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS))
        d = p["delay"]
        print(
            f"{name:<14}{p['total_mbps']:>7.1f}M{d['met']:>7}/{d['n']:<2}"
            f"{d['mean_delivery']:>11.0%}{d['min_delivery']:>10.0%}"
            f"{d['worst_p99']:>9.1f}ms"
        )
    print(f"\n(PDCCH utilization, TwoTier uses SPS to bypass per-slot DCI.)")


def study_latency_bound() -> None:
    _hr("STUDY 3 -- Latency-bound (8 interactive streams + bulk, congested DL)")
    print(
        "Eight 5 Mbps interactive streams with a 12 ms PDB share a saturated\n"
        "downlink with 80 Mbps of bulk best-effort. Delay contract = >=99% of\n"
        "packets delivered on time within the PDB. Bulk DL throughput is shown\n"
        "to make the tradeoff explicit.\n"
    )
    sc = latency_bound_scenario()
    meta = _flow_meta(sc)
    scheds = [("RoundRobin", RoundRobin), ("PF", _pf), ("TwoTier", _tt)]
    print(
        f"{'scheduler':<14}{'ctrl on-time':>14}{'ctrl mean':>11}"
        f"{'ctrl worst p99':>16}{'bulk DL':>10}"
    )
    for name, factory in scheds:
        summary = run(sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS)
        p = _profile(sc, summary)
        d = p["delay"]
        bulk = sum(
            m["throughput_bps"]
            for fk, m in summary["flows"].items()
            if meta[fk][0] == "PF"
        ) / 1e6
        print(
            f"{name:<14}{d['met']:>11}/{d['n']:<2}{d['mean_delivery']:>10.0%}"
            f"{d['worst_p99']:>13.1f}ms{bulk:>8.1f}M"
        )


def _ul_access_study_scenario() -> ScenarioConfig:
    """A dedicated N=2-UE scenario for study 4, deliberately mirroring the
    real hardware sweep's own methodology (oai-branches/
    Sweep_Orig_vs_TwoTier.xlsx: "Two-UE Admissible-Load Sweep", PASS bound
    p99<100ms) rather than reusing sensor_dense_scenario's 30-UE/15ms-PDB
    setup. That setup was tried first and found unsuitable for this study:
    its tight PDB pegs p99 at the PDB ceiling itself once packets start
    getting dropped, saturating almost the entire grid rather than showing
    the smoothly-varying access-chain-latency signal the real sweep
    reveals. Two UEs at a generous 100 ms PDB avoids that saturation
    artifact and is a closer methodological match besides."""
    from sim.config import CarrierConfig, FlowConfig, ScenarioConfig as SC, UEConfig

    # bytes_per_period=1400 (200 x 7) is itself a calibration finding, not
    # an arbitrary choice: at 200 bytes/5ms, UL PRB utilization never
    # exceeds ~13% across the whole 45-145% sweep (checked empirically) --
    # far too lightly loaded for a "load %" axis to mean anything, since
    # the buffer fully drains between every message at every tested point
    # regardless of load, so every message independently pays the same
    # SR round trip and the sweep is flat by construction. 7x is the
    # point where the access chain's own throughput ceiling (not raw PRB
    # capacity, which stays under ~15% utilized even at 145% here) starts
    # to bind -- see study_ul_access_chain's printed finding for what this
    # revealed about the load-inversion hypothesis.
    ues = [UEConfig(ue_id=i, mean_snr_db=20.0, coherence_slots=2000) for i in (1, 2)]
    flows = [
        FlowConfig(
            ue_id=i, qfi=1, direction="UL", flow_class="PF", pdb_ms=100.0,
            traffic_kind="deterministic",
            traffic_params={"period_ms": 5.0, "bytes_per_period": 200 * 7},
        )
        for i in (1, 2)
    ]
    return SC(
        name="ul_access_study", horizon_slots=8000,
        carrier=CarrierConfig(), ues=ues, flows=flows, seed=42,
    )


def study_ul_access_chain() -> None:
    _hr("STUDY 4 -- Uplink access chain (SR -> grant -> BSR -> grant)")
    print(
        "Offered-load x SR-periodicity grid on a dedicated N=2-UE scenario\n"
        "(mirrors the real sweep's own methodology, see\n"
        "_ul_access_study_scenario's docstring for why sensor_dense_\n"
        "scenario didn't work for this). Load points match the real\n"
        "hardware sweep (oai-branches/Sweep_Orig_vs_TwoTier.xlsx, README\n"
        "sec 7/8) -- 100% is this scenario's as-configured traffic, scaled\n"
        "the same way study 1 scales capacity around its as-configured\n"
        "point. Reported: worst-of-two-UE UL HoL p99 (ms), the proxy for\n"
        "M01/flow_latency_percentiles (config/metric_panel.yml).\n"
        "sr_period_slots has no ground truth (README sec 8) -- swept\n"
        "explicitly, not defaulted.\n"
        "Real sweep's own p99 (Orig / Two-tier, ms), for comparison:\n"
    )
    real_sweep = {
        45: (67.25, 63.13), 70: (31.88, 24.36), 90: (15.59, 16.7),
        105: (14.73, 15.26), 125: (12.98, 12.99), 145: (33.09, 15.9),
    }
    for pct, (orig, tt) in real_sweep.items():
        print(f"  {pct:>3}% load: Orig {orig:>6.2f}ms  TT {tt:>6.2f}ms")

    base = _ul_access_study_scenario()
    load_points = (45, 70, 90, 105, 125, 145)
    periods = (1, 10, 20, 40)
    scheds = [("RoundRobin", RoundRobin), ("PF", _pf), ("TwoTier", _tt)]

    for name, factory in scheds:
        print(f"\n{name} -- worst UL HoL p99 (ms), rows=load%, cols=sr_period_slots")
        header = "  load%  " + "".join(f"{p:>9}" for p in periods)
        print(header)
        for pct in load_points:
            sc = _scale_ul_load(base, pct / 100.0)
            meta = _flow_meta(sc)
            row = [f"{pct:>5}%  "]
            for period in periods:
                summary = run(
                    sc, factory(), cqi_delay_slots=CQI_DELAY_SLOTS,
                    sr_period_slots=period,
                )
                ul_p99 = max(
                    (m["hol_p99_ms"] for fk, m in summary["flows"].items()
                     if meta[fk][3] == "UL"),
                    default=0.0,
                )
                row.append(f"{ul_p99:>9.2f}")
            print("".join(row))
    print(
        "\nFINDING (negative result, reported as instructed rather than\n"
        "tuned away): the load-inversion does NOT appear. PF/RoundRobin\n"
        "(non-SPS) show p99 INCREASING with load -- the opposite direction\n"
        "-- up to a sharp collapse to the PDB ceiling (100ms), not a smooth\n"
        "high-to-low curve. TwoTier (SPS-bypassed for these flows) stays\n"
        "flat and small throughout, as expected, but that's the mechanism\n"
        "being absent, not confirmed. Two scenario constructions were\n"
        "tried (sensor_dense_scenario's 30-UE/15ms-PDB setup, and this\n"
        "dedicated N=2-UE/100ms-PDB one) and neither showed the hypothesised\n"
        "shape at any tested load or sr_period_slots value -- this isn't a\n"
        "single miscalibrated point. Diagnosis: the hypothesis requires a\n"
        "regime where the UE is busy enough that its buffer never returns\n"
        "to empty between messages (so SR is skipped after the first one),\n"
        "but not so overloaded that messages miss their PDB outright. In\n"
        "this simulator that middle regime is vanishingly narrow -- the\n"
        "transition from fully-served to PDB-collapsed is a cliff, not a\n"
        "gradual queueing curve, at every calibration tried. Whether that\n"
        "cliff is itself realistic or an artefact of this scenario's\n"
        "capacity/traffic shape is open (README sec 8); it is NOT explained\n"
        "by sr_period_slots, which does not change the qualitative shape,\n"
        "only how early the cliff hits."
    )


def main() -> None:
    print(
        "UL BSR: per-LCG, quantised, event-driven (sim/bsr.py); "
        "Configured Grants bypass it.\n"
        f"DL CQI delay: {CQI_DELAY_SLOTS} slots "
        "(scheduler-visible SNR lags true SNR; SPS uses smoothed CQI)."
    )
    study_overload_sweep()
    study_pdcch_limited()
    study_latency_bound()
    study_ul_access_chain()


if __name__ == "__main__":
    main()
