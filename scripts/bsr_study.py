"""BSR degradation sweep: how does the PF-vs-TwoTier gap depend on the
uplink BSR round-trip delay and BSR loss rate?

Two things are being tested:

  A) A **delay sweep** at zero loss -- how much of the win comes from
     Configured Grants bypassing the BSR round-trip that all dynamic
     schedulers pay.

  B) A **loss sweep** at a realistic 8-slot delay -- what happens when
     BSR updates are lost (SR-on-PUCCH loss or a lost BSR MAC CE on
     PUSCH), so the gNB continues to schedule from stale info.

Both are run on:
  - factory_robots at 0.50x shipped load (moderate-overload GBR band,
    the regime where the PF-vs-TwoTier gap is cleanest -- see
    design-docs/scheduler-study.md Section 7.1).
  - sensor_dense at 1.0x (as-shipped) -- to make explicit that TwoTier's
    SPS-served flows are invariant to BSR degradation while dynamic PF is
    not.

Delay values (slots) are those factory_robots' numerology mu=2 map to
{0.25, 1, 2, 4} ms of round-trip; sensor_dense's mu=1 maps them to
{0.5, 2, 4, 8} ms. Loss values are picked to span "quiet" through
"stressed" radio conditions.

Metric contract as in scheduler_study.py: a GBR flow's contract is met
at delivered >= 95% of GFBR; a Delay flow's is met at >= 99% on-time
within its PDB.

Usage:
    python scripts/bsr_study.py
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.config import ScenarioConfig
from sim.driver import run
from sim.scenarios import factory_robots_scenario, sensor_dense_scenario
from sim.baselines.pf import ProportionalFair
from scheduler import load_two_tier

SCHEDULER_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

GBR_CONTRACT_FRACTION = 0.95
DELAY_ONTIME_DELIVERY = 0.99

# Sweep points. Loss=0 for the delay sweep; delay=8 for the loss sweep.
DELAY_SLOTS_SWEEP = (0, 2, 4, 8, 16)
LOSS_RATE_SWEEP = (0.00, 0.05, 0.10, 0.20)
LOSS_SWEEP_AT_DELAY = 8


def _pf():
    return ProportionalFair(ewma_window_slots=200)


def _tt():
    return load_two_tier(SCHEDULER_CONFIG)


def _scale_capacity(scenario: ScenarioConfig, mult: float) -> ScenarioConfig:
    carrier = dataclasses.replace(
        scenario.carrier,
        bandwidth_hz=int(scenario.carrier.bandwidth_hz * mult),
    )
    return dataclasses.replace(scenario, carrier=carrier)


def _gbr_summary(scenario: ScenarioConfig, summary: dict) -> dict:
    """Count-of-contracts-met + min/mean delivery_ratio + total. Uses the
    same metric as scheduler_study.py's _profile so the two are directly
    comparable: 'met' is delivered >= 95% of GFBR (contract compliance);
    mean/min are of delivery_ratio (delivered / offered), which reflects
    both scheduling and PDB drops."""
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


def _delay_summary(scenario: ScenarioConfig, summary: dict) -> dict:
    """Count on-time (delivery >=99% and p99 HoL <= PDB) + worst p99."""
    delay = {(f.ue_id, f.qfi): f.pdb_ms for f in scenario.flows if f.flow_class == "Delay"}
    rows = []
    for fk, m in summary["flows"].items():
        ue = int(fk.split("_")[0][2:])
        qfi = int(fk.split("_")[1][3:])
        if (ue, qfi) in delay:
            pdb_ms = delay[(ue, qfi)]
            ok = m["delivery_ratio"] >= DELAY_ONTIME_DELIVERY and m["hol_p99_ms"] <= pdb_ms
            rows.append((m["delivery_ratio"], m["hol_p99_ms"], ok))
    total_mbps = sum(m["throughput_bps"] for m in summary["flows"].values()) / 1e6
    return {
        "met": sum(1 for *_, ok in rows if ok),
        "n": len(rows),
        "mean": sum(r for r, *_ in rows) / len(rows) if rows else 0.0,
        "worst_p99": max(p for _, p, _ in rows) if rows else 0.0,
        "total_mbps": total_mbps,
    }


def _hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def study_delay_sweep_factory() -> None:
    _hr("STUDY A -- BSR delay sweep, factory_robots @ 0.50x load, loss = 0")
    print(
        "Uplink-heavy GBR workload in the moderate-overload band. Delays\n"
        "in slots (numerology mu=2 -> 0.25 ms/slot).\n"
    )
    sc = _scale_capacity(factory_robots_scenario(), 2.0)
    slot_ms = 1.0 / (2 ** sc.carrier.numerology)  # slot = 1 / 2^mu ms
    print(
        f"{'delay':>8}{'':>8}"
        + f"{'PF met':>10}{'TT met':>9}{'PF minGBR':>12}{'TT minGBR':>12}"
        + f"{'PF total':>12}{'TT total':>12}"
    )
    for d in DELAY_SLOTS_SWEEP:
        pf = _gbr_summary(sc, run(sc, _pf(), ul_bsr_delay_slots=d))
        tt = _gbr_summary(sc, run(sc, _tt(), ul_bsr_delay_slots=d))
        label = f"{d}sl ({d * slot_ms:.1f}ms)"
        print(
            f"{label:>16}"
            f"{pf['met']:>7}/{pf['n']:<2}{tt['met']:>6}/{tt['n']:<2}"
            f"{pf['min']:>11.0%}{tt['min']:>12.0%}"
            f"{pf['total_mbps']:>10.1f}M{tt['total_mbps']:>11.1f}M"
        )


def study_loss_sweep_factory() -> None:
    _hr(
        f"STUDY B -- BSR loss sweep, factory_robots @ 0.50x load, "
        f"delay = {LOSS_SWEEP_AT_DELAY} slots"
    )
    print(
        "Same workload as A. BSR losses are per-slot per-UL-flow Bernoulli;\n"
        "on a loss the gNB keeps the last successfully reported value.\n"
    )
    sc = _scale_capacity(factory_robots_scenario(), 2.0)
    print(
        f"{'loss':>6}"
        + f"{'PF met':>10}{'TT met':>9}{'PF minGBR':>12}{'TT minGBR':>12}"
        + f"{'PF total':>12}{'TT total':>12}"
    )
    for p_loss in LOSS_RATE_SWEEP:
        pf = _gbr_summary(sc, run(
            sc, _pf(), ul_bsr_delay_slots=LOSS_SWEEP_AT_DELAY,
            ul_bsr_loss_rate=p_loss,
        ))
        tt = _gbr_summary(sc, run(
            sc, _tt(), ul_bsr_delay_slots=LOSS_SWEEP_AT_DELAY,
            ul_bsr_loss_rate=p_loss,
        ))
        print(
            f"{p_loss:>5.0%}"
            f"{pf['met']:>8}/{pf['n']:<2}{tt['met']:>6}/{tt['n']:<2}"
            f"{pf['min']:>11.0%}{tt['min']:>12.0%}"
            f"{pf['total_mbps']:>10.1f}M{tt['total_mbps']:>11.1f}M"
        )


def study_delay_sweep_sensor_dense() -> None:
    _hr("STUDY C -- BSR delay sweep, sensor_dense, loss = 0")
    print(
        "30 periodic UL sensors, PDCCH- and BSR-sensitive. TwoTier serves\n"
        "them via Configured Grants -- expected invariant to BSR.\n"
    )
    sc = sensor_dense_scenario()
    slot_ms = 1.0 / (2 ** sc.carrier.numerology)
    print(
        f"{'delay':>8}{'':>8}"
        + f"{'PF ontime':>12}{'TT ontime':>12}"
        + f"{'PF worst p99':>15}{'TT worst p99':>15}"
    )
    for d in DELAY_SLOTS_SWEEP:
        pf = _delay_summary(sc, run(sc, _pf(), ul_bsr_delay_slots=d))
        tt = _delay_summary(sc, run(sc, _tt(), ul_bsr_delay_slots=d))
        label = f"{d}sl ({d * slot_ms:.1f}ms)"
        print(
            f"{label:>16}"
            f"{pf['met']:>9}/{pf['n']:<2}{tt['met']:>9}/{tt['n']:<2}"
            f"{pf['worst_p99']:>13.1f}ms{tt['worst_p99']:>13.1f}ms"
        )


def study_loss_sweep_sensor_dense() -> None:
    _hr(
        f"STUDY D -- BSR loss sweep, sensor_dense, "
        f"delay = {LOSS_SWEEP_AT_DELAY} slots"
    )
    print(
        "Same workload as C. TwoTier's SPS bypass should keep on-time at\n"
        "30/30 across loss rates; PF has no such bypass.\n"
    )
    sc = sensor_dense_scenario()
    print(
        f"{'loss':>6}"
        + f"{'PF ontime':>12}{'TT ontime':>12}"
        + f"{'PF worst p99':>15}{'TT worst p99':>15}"
    )
    for p_loss in LOSS_RATE_SWEEP:
        pf = _delay_summary(sc, run(
            sc, _pf(), ul_bsr_delay_slots=LOSS_SWEEP_AT_DELAY,
            ul_bsr_loss_rate=p_loss,
        ))
        tt = _delay_summary(sc, run(
            sc, _tt(), ul_bsr_delay_slots=LOSS_SWEEP_AT_DELAY,
            ul_bsr_loss_rate=p_loss,
        ))
        print(
            f"{p_loss:>5.0%}"
            f"{pf['met']:>10}/{pf['n']:<2}{tt['met']:>9}/{tt['n']:<2}"
            f"{pf['worst_p99']:>13.1f}ms{tt['worst_p99']:>13.1f}ms"
        )


def main() -> None:
    study_delay_sweep_factory()
    study_loss_sweep_factory()
    study_delay_sweep_sensor_dense()
    study_loss_sweep_sensor_dense()


if __name__ == "__main__":
    main()
