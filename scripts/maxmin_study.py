"""Finding 1 study: does a max-min GBR stage in Tier-1 fix cell-edge starvation?

Finding 1 (NOTES.md, 2026-05-13) is that Tier-1's single-stage log-utility
solve with *soft* GBR floors abandons the lowest-SE GBR flows -- ue4 (16 dB)
and ue7 (14 dB) on `factory_robots` -- to fund cheaper high-SNR ones. Two
mitigations were explored and rejected: the adaptive dual-ascent penalty
(equalises shortfall, which is the wrong objective for a step-function
contract) and the SE-tilt knob k (only relocates the starvation).

This study evaluates the fix the design docs actually committed to: a
max-min satisfaction stage ahead of the utility solve
(`scheduler.solve_maxmin_gbr_level` -> `gbr_maxmin_floors` ->
`solve_tier1(gbr_floor_bps=...)`), with `gbr_maxmin_scale` dialling how
much of the achievable floor to claim.

Three parts:
  1. Load sweep -- min / mean GBR delivery and contract count for PF,
     single-stage TwoTier, the adaptive penalty, and max-min, across the
     same load points as Study 1 in the scheduler study.
  2. Scale sweep -- the fairness/efficiency curve as gbr_maxmin_scale goes
     0 -> 1, at the two loads where the scheduler choice matters.
  3. Per-flow detail -- what actually happens to the cell-edge canaries
     (ue4, ue7) and to the DL Delay class that the hard floor could crowd
     out.

Usage:
    python scripts/maxmin_study.py
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.config import ScenarioConfig
from sim.driver import run
from sim.scenarios import factory_robots_scenario
from sim.baselines.pf import ProportionalFair
from scheduler import load_two_tier

SCHEDULER_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

# Same contract definitions and channel-report settings as
# scripts/scheduler_study.py, so numbers are directly comparable.
GBR_CONTRACT_FRACTION = 0.95
DELAY_ONTIME_DELIVERY = 0.99
UL_BSR_DELAY_SLOTS = 8
CQI_DELAY_SLOTS = 8

# The two cell-edge GBR flows Finding 1 is about (16 dB and 14 dB).
CANARIES = ("ue4_qfi2", "ue7_qfi2")


def _pf():
    return ProportionalFair(ewma_window_slots=200)


def _tt(**overrides):
    return load_two_tier(SCHEDULER_CONFIG, **overrides)


def _scale_capacity(scenario: ScenarioConfig, mult: float) -> ScenarioConfig:
    """Return the scenario with its carrier bandwidth scaled by mult.

    The study reports the inverse as *load* (1/mult x shipped), matching
    the axis convention of scheduler-study.md 7.1 -- higher = worse.
    """
    carrier = dataclasses.replace(
        scenario.carrier,
        bandwidth_hz=int(scenario.carrier.bandwidth_hz * mult),
    )
    return dataclasses.replace(scenario, carrier=carrier)


def _flow_meta(scenario: ScenarioConfig) -> dict:
    return {
        f"ue{f.ue_id}_qfi{f.qfi}": (f.flow_class, f.gfbr_bps, f.pdb_ms)
        for f in scenario.flows
    }


def _profile(scenario: ScenarioConfig, summary: dict) -> dict:
    meta = _flow_meta(scenario)
    flows = summary["flows"]
    gbr, delay = [], []
    for fk, m in flows.items():
        flow_class, gfbr, pdb_ms = meta[fk]
        if flow_class == "GBR":
            gbr.append((m, m["throughput_bps"] >= GBR_CONTRACT_FRACTION * gfbr))
        elif flow_class == "Delay":
            ontime = (
                m["delivery_ratio"] >= DELAY_ONTIME_DELIVERY
                and m["hol_p99_ms"] <= pdb_ms
            )
            delay.append((m, ontime))
    return {
        "total_mbps": sum(f["throughput_bps"] for f in flows.values()) / 1e6,
        "gbr_n": len(gbr),
        "gbr_met": sum(1 for _, ok in gbr if ok),
        "gbr_mean": sum(m["delivery_ratio"] for m, _ in gbr) / max(1, len(gbr)),
        "gbr_min": min((m["delivery_ratio"] for m, _ in gbr), default=0.0),
        "delay_n": len(delay),
        "delay_met": sum(1 for _, ok in delay if ok),
        "canaries": {
            fk: flows[fk]["delivery_ratio"] for fk in CANARIES if fk in flows
        },
    }


def _hr(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


# Load points, expressed as capacity multipliers (load = 1/mult).
LOADS = ((1.0, "1.00x"), (1.5, "0.67x"), (2.0, "0.50x"), (3.0, "0.33x"))


def study_load_sweep() -> None:
    _hr("PART 1 -- Load sweep: does the max-min stage lift the GBR floor?")
    print(
        "factory_robots. GBR contract = delivered >= 95% of GFBR.\n"
        "'min GBR' is the metric Finding 1 is about -- the worst-served GBR "
        "flow.\n"
    )
    base = factory_robots_scenario()
    # gbr_maxmin is now the shipped default, so the single-stage form has to
    # be asked for explicitly to keep the comparison meaningful.
    scheds = [
        ("PF", _pf),
        ("TwoTier-nomaxmin", lambda: _tt(gbr_maxmin=False)),
        ("TwoTier+adaptive", lambda: _tt(gbr_penalty_lr=1e5, gbr_maxmin=False)),
        ("TwoTier (default)", lambda: _tt()),
    ]
    print(
        f"{'load':>6}  {'scheduler':<18}{'total':>8}{'GBR met':>10}"
        f"{'mean GBR':>10}{'min GBR':>9}{'ue4':>7}{'ue7':>7}"
        f"{'Delay on-time':>15}"
    )
    for mult, label in LOADS:
        sc = _scale_capacity(base, mult)
        for name, factory in scheds:
            p = _profile(sc, run(
                sc, factory(),
                ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS,
                cqi_delay_slots=CQI_DELAY_SLOTS,
            ))
            c = p["canaries"]
            print(
                f"{label:>6}  {name:<18}{p['total_mbps']:>6.1f}M"
                f"{p['gbr_met']:>7}/{p['gbr_n']:<2}{p['gbr_mean']:>9.0%}"
                f"{p['gbr_min']:>8.0%}"
                f"{c.get('ue4_qfi2', 0):>7.0%}{c.get('ue7_qfi2', 0):>7.0%}"
                f"{p['delay_met']:>12}/{p['delay_n']:<2}"
            )
        print()


def study_scale_sweep() -> None:
    _hr("PART 2 -- Scale sweep: the fairness/efficiency curve")
    print(
        "gbr_maxmin_scale is the fraction of the achievable max-min level t*\n"
        "claimed as a hard floor. 0.0 == single-stage TwoTier; 1.0 == the\n"
        "shipped default. The point is to see what the floor costs.\n"
    )
    base = factory_robots_scenario()
    print(
        f"{'load':>6}  {'scale':>6}{'t*':>7}{'total':>8}{'GBR met':>10}"
        f"{'mean GBR':>10}{'min GBR':>9}{'ue4':>7}{'ue7':>7}"
    )
    for mult, label in ((1.0, "1.00x"), (2.0, "0.50x")):
        sc = _scale_capacity(base, mult)
        for scale in (0.0, 0.25, 0.5, 0.75, 1.0):
            sched = _tt(gbr_maxmin_scale=scale)
            p = _profile(sc, run(
                sc, sched,
                ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS,
                cqi_delay_slots=CQI_DELAY_SLOTS,
            ))
            c = p["canaries"]
            print(
                f"{label:>6}  {scale:>6.2f}{sched.maxmin_level:>7.2f}"
                f"{p['total_mbps']:>6.1f}M"
                f"{p['gbr_met']:>7}/{p['gbr_n']:<2}{p['gbr_mean']:>9.0%}"
                f"{p['gbr_min']:>8.0%}"
                f"{c.get('ue4_qfi2', 0):>7.0%}{c.get('ue7_qfi2', 0):>7.0%}"
            )
        print()


def study_per_flow() -> None:
    _hr("PART 3 -- Per-flow detail (factory_robots, 1.00x load as shipped)")
    print(
        "Every GBR flow, worst-SNR first. The question is whether max-min\n"
        "lifts the cell-edge flows without collapsing the rest.\n"
    )
    sc = factory_robots_scenario()
    meta = _flow_meta(sc)
    snr_by_ue = {ue.ue_id: ue.mean_snr_db for ue in sc.ues}
    variants = [
        ("no maxmin", lambda: _tt(gbr_maxmin=False)),
        ("default", lambda: _tt()),
        ("s=0.5", lambda: _tt(gbr_maxmin_scale=0.5)),
        ("PF", _pf),
    ]
    results = {}
    for name, factory in variants:
        summary = run(
            sc, factory(),
            ul_bsr_delay_slots=UL_BSR_DELAY_SLOTS,
            cqi_delay_slots=CQI_DELAY_SLOTS,
        )
        results[name] = summary["flows"]

    gbr_keys = [fk for fk, m in meta.items() if m[0] == "GBR"]
    gbr_keys.sort(key=lambda fk: snr_by_ue[int(fk.split("_")[0][2:])])

    header = f"{'flow':<12}{'SNR':>5}{'GFBR':>7}"
    for name, _ in variants:
        header += f"{name:>14}"
    print(header)
    for fk in gbr_keys:
        ue = int(fk.split("_")[0][2:])
        row = f"{fk:<12}{snr_by_ue[ue]:>4.0f}d{meta[fk][1] / 1e6:>6.0f}M"
        for name, _ in variants:
            row += f"{results[name][fk]['delivery_ratio']:>14.0%}"
        print(row)


def main() -> None:
    study_load_sweep()
    study_scale_sweep()
    study_per_flow()


if __name__ == "__main__":
    main()
