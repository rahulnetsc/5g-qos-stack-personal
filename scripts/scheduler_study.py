"""Scheduler study: which scheduler to build, and under what conditions.

Three studies, each framed as an engineering decision rather than a metric
dump:

  1. Overload sweep -- how the PF-vs-TwoTier gap depends on how overloaded
     the cell is. Establishes the regime where a QoS-aware scheduler earns
     its complexity.
  2. PDCCH-limited (sensor_dense) -- many small periodic flows where the
     control channel, not the data channel, is the bottleneck.
  3. Latency-bound -- tight-PDB control loops sharing a congested downlink
     with bulk traffic. Tests deadline awareness.

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


if __name__ == "__main__":
    main()
