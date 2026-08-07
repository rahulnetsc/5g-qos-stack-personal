"""CQI-staleness and SPS-conservative-MCS sensitivity sweep.

Two things are being tested:

  E) A **CQI delay sweep** at loss=0 on the factory scenario -- how much
     of the scheduler's performance depends on having a fresh channel
     estimate. Real 5G reports CQI on a period of 5-160 ms; at mu=1 that
     is 10-320 slots.

  F) A **SPS-margin sweep** at a realistic CQI delay -- SPS uses a fixed
     MCS chosen at reservation time from (smoothed CQI SNR - margin). A
     larger margin trades spectral efficiency (larger reservations) for
     BLER robustness against CQI drift, and is only worth paying for on
     channels that actually drift meaningfully.

Each is run on both the default factory channel (coherence 2000 slots ~
1 s, near-static -- realistic for a warehouse or fixed AGV routes) and on
a **short-coherence variant** (coherence 30 slots ~ 15 ms, representative
of moving robots), because the tradeoff hinges on channel volatility.
The comparison is meant to make explicit *when* the SPS conservative MCS
earns its keep and when it is pure overhead.

Note on terminology: our ChannelModel is direction-agnostic (one
``get_snr_db(ue)`` per UE). "CQI delay" here therefore covers both DL
CQI reports and UL SRS-based channel estimation -- the gNB in both cases
has a delayed view of the per-UE channel, and MCS decisions live off it.

Metrics as in scheduler_study.py: GBR contract at delivered >= 95% of GFBR;
min/mean are of ``delivery_ratio`` (delivered/offered).

Usage:
    python scripts/cqi_study.py
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.config import ScenarioConfig, UEConfig
from sim.driver import run
from sim.scenarios import factory_robots_scenario
from sim.baselines.pf import ProportionalFair
from scheduler import load_two_tier

SCHEDULER_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

GBR_CONTRACT_FRACTION = 0.95

# Sweep points.
CQI_DELAY_SLOTS_SWEEP = (0, 4, 8, 16, 32)
SPS_MARGIN_DB_SWEEP = (0.0, 1.0, 2.0, 3.0, 5.0)
CQI_SWEEP_AT_DELAY = 8      # default when sweeping SPS margin
UL_BSR_DELAY_SLOTS = 8      # kept consistent with scheduler_study.py
FACTORY_CAPACITY_MULT = 2.0  # sim knob; expressed to the reader as
                             # `load = 1 / FACTORY_CAPACITY_MULT` shipped.
FACTORY_LOAD_LABEL = f"{1.0 / FACTORY_CAPACITY_MULT:.2f}x load"

# Channel-coherence variants.
STATIC_COHERENCE_SLOTS = 2000    # near-static -- factory as shipped
MOBILE_COHERENCE_SLOTS = 30      # short-coherence -- moving robots


def _pf():
    return ProportionalFair(ewma_window_slots=200)


def _tt(sps_margin_db: float = 0.0):
    return load_two_tier(SCHEDULER_CONFIG, sps_snr_margin_db=sps_margin_db)


def _scale_capacity(scenario: ScenarioConfig, mult: float) -> ScenarioConfig:
    carrier = dataclasses.replace(
        scenario.carrier,
        bandwidth_hz=int(scenario.carrier.bandwidth_hz * mult),
    )
    return dataclasses.replace(scenario, carrier=carrier)


def _override_coherence(scenario: ScenarioConfig, coherence_slots: int) -> ScenarioConfig:
    """Rewrite every UE's coherence -- everything else stays."""
    ues = [dataclasses.replace(u, coherence_slots=coherence_slots) for u in scenario.ues]
    return dataclasses.replace(scenario, ues=ues)


def _gbr_summary(scenario: ScenarioConfig, summary: dict) -> dict:
    """Contract compliance + min/mean delivery_ratio across GBR flows."""
    gfbr = {(f.ue_id, f.qfi): f.gfbr_bps for f in scenario.flows if f.flow_class == "GBR"}
    met, ratios = 0, []
    for fk, m in summary["flows"].items():
        ue = int(fk.split("_")[0][2:])
        qfi = int(fk.split("_")[1][3:])
        if (ue, qfi) in gfbr:
            g = gfbr[(ue, qfi)]
            if g > 0 and m["throughput_bps"] >= GBR_CONTRACT_FRACTION * g:
                met += 1
            ratios.append(m["delivery_ratio"])
    total_mbps = sum(m["throughput_bps"] for m in summary["flows"].values()) / 1e6
    return {
        "met": met,
        "n": len(ratios),
        "mean": sum(ratios) / len(ratios) if ratios else 0.0,
        "min": min(ratios) if ratios else 0.0,
        "total_mbps": total_mbps,
    }


def _hr(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def study_cqi_delay(coherence_slots: int, label: str) -> None:
    _hr(
        f"STUDY E ({label}) -- CQI delay sweep, factory @ {FACTORY_LOAD_LABEL}, "
        f"UL BSR delay = {UL_BSR_DELAY_SLOTS}"
    )
    print(
        f"UE coherence = {coherence_slots} slots. Default TwoTier (sps_snr_margin = 0).\n"
    )
    sc = _scale_capacity(factory_robots_scenario(), FACTORY_CAPACITY_MULT)
    sc = _override_coherence(sc, coherence_slots)
    print(
        f"{'cqi delay':>10}{'':>2}"
        + f"{'PF met':>9}{'TT met':>9}{'PF minGBR':>12}{'TT minGBR':>12}"
        + f"{'PF total':>12}{'TT total':>12}"
    )
    for d in CQI_DELAY_SLOTS_SWEEP:
        pf = _gbr_summary(sc, run(
            sc, _pf(),
            ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS, cqi_delay_slots=d,
        ))
        tt = _gbr_summary(sc, run(
            sc, _tt(sps_margin_db=0.0),
            ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS, cqi_delay_slots=d,
        ))
        print(
            f"{d:>8}sl{'':>2}"
            f"{pf['met']:>6}/{pf['n']:<2}{tt['met']:>6}/{tt['n']:<2}"
            f"{pf['min']:>11.0%}{tt['min']:>12.0%}"
            f"{pf['total_mbps']:>10.1f}M{tt['total_mbps']:>11.1f}M"
        )


def study_sps_margin(coherence_slots: int, label: str) -> None:
    _hr(
        f"STUDY F ({label}) -- SPS margin sweep, factory @ {FACTORY_LOAD_LABEL}, "
        f"CQI delay = {CQI_SWEEP_AT_DELAY}, UL BSR delay = {UL_BSR_DELAY_SLOTS}"
    )
    print(
        f"UE coherence = {coherence_slots} slots. Sweep TwoTier's sps_snr_margin_db;\n"
        "PF is shown once for reference (invariant to SPS margin).\n"
    )
    sc = _scale_capacity(factory_robots_scenario(), FACTORY_CAPACITY_MULT)
    sc = _override_coherence(sc, coherence_slots)
    # PF reference row.
    pf = _gbr_summary(sc, run(
        sc, _pf(),
        ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS, cqi_delay_slots=CQI_SWEEP_AT_DELAY,
    ))
    print(
        f"{'PF (reference)':<24}"
        f"{pf['met']:>6}/{pf['n']:<2}{pf['mean']:>11.0%}"
        f"{pf['min']:>10.0%}{pf['total_mbps']:>12.1f}M"
    )
    print(
        f"{'SPS margin (dB)':<24}{'TT met':>9}"
        + f"{'TT mean':>11}{'TT min':>10}{'TT total':>13}"
    )
    for margin in SPS_MARGIN_DB_SWEEP:
        tt = _gbr_summary(sc, run(
            sc, _tt(sps_margin_db=margin),
            ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS, cqi_delay_slots=CQI_SWEEP_AT_DELAY,
        ))
        print(
            f"{margin:<24.1f}"
            f"{tt['met']:>6}/{tt['n']:<2}{tt['mean']:>11.0%}"
            f"{tt['min']:>10.0%}{tt['total_mbps']:>12.1f}M"
        )


def main() -> None:
    study_cqi_delay(STATIC_COHERENCE_SLOTS, "static channel")
    study_cqi_delay(MOBILE_COHERENCE_SLOTS, "mobile channel")
    study_sps_margin(STATIC_COHERENCE_SLOTS, "static channel")
    study_sps_margin(MOBILE_COHERENCE_SLOTS, "mobile channel")


if __name__ == "__main__":
    main()
