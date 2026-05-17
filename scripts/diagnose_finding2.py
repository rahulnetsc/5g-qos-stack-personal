"""Root-cause diagnostic for NOTES.md Finding 2 — within-UE GBR cannibalisation.

UEs that carry a GBR flow plus another flow on the same UE (ue8/9/10 in
factory_robots) get worse GBR delivery under TwoTier than the single-flow
GBR UEs (ue1-7). This script localises the loss by dumping, per GBR flow:

  - the Tier-1 LP target rate (per solve),
  - whether it got an SPS reservation and how big,
  - the Tier-2 delivered throughput,

so the gap can be attributed to Tier-1 (LP under-allocates), SPS (no
reservation), or Tier-2 (target set but not delivered).

Usage:
    python scripts/diagnose_finding2.py
"""

import dataclasses
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.channel import bits_per_prb
from sim.driver import run
from sim.resource import ResourceGrid
from sim.scenarios import factory_robots_scenario
from sim.schedulers.two_tier import TwoTier
from sim.tier1 import grid_capacity_prbsym_per_sec


def main() -> None:
    scenario = factory_robots_scenario()
    sched = TwoTier(tier1_period_slots=2000)

    # Capture Tier-1 targets at every solve.
    solves: list[dict] = []
    orig_resolve = sched._resolve_tier1

    def wrapped_resolve():
        orig_resolve()
        solves.append(dict(sched._targets_bps))

    sched._resolve_tier1 = wrapped_resolve  # type: ignore[method-assign]
    summary = run(scenario, sched)

    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    flows = {(f.ue_id, f.qfi): f for f in scenario.flows}
    sps_prbs = {(s.ue_id, s.qfi): s.prbs_per_slot for s in sched._sps}
    snr = {u.ue_id: u.mean_snr_db for u in scenario.ues}
    last = solves[-1]

    print(f"\nfactory_robots / TwoTier — {len(solves)} Tier-1 solves\n")
    print(f"PRBs per slot: {grid.prb_count}   "
          f"UL PRB-symbol capacity: {cap_ul:,.0f}/s   DL: {cap_dl:,.0f}/s")
    ul_sps = sum(p for (u, q), p in sps_prbs.items()
                 if flows[(u, q)].direction == "UL")
    print(f"UL SPS reserved: {ul_sps} PRB/slot of {grid.prb_count} "
          f"({len([k for k in sps_prbs if flows[k].direction == 'UL'])} "
          f"flows got a reservation)")

    gbr = sorted(k for k, f in flows.items() if f.flow_class == "GBR")
    single = [k for k in gbr if k[0] <= 7]
    mixed = [k for k in gbr if k[0] >= 8]

    def fmt_rows(keys):
        for ue, qfi in keys:
            f = flows[(ue, qfi)]
            fk = f"ue{ue}_qfi{qfi}"
            m = summary["flows"][fk]
            tgt = last.get((ue, qfi), 0.0)
            se_bits, _ = bits_per_prb(snr[ue], symbols=1)
            sps = sps_prbs.get((ue, qfi))
            sps_str = f"{sps}" if sps is not None else "none"
            # per-solve target spread
            tgts = [s.get((ue, qfi), 0.0) / 1e6 for s in solves]
            spread = f"[{min(tgts):.1f}-{max(tgts):.1f}]"
            print(
                f"  ue{ue:<2} snr{snr[ue]:>4.0f}  GFBR {f.gfbr_bps/1e6:>4.1f}M"
                f"  tier1 {tgt/1e6:>5.2f}M ({tgt/f.gfbr_bps:>4.0%})  "
                f"solves {spread:>11}  SPS {sps_str:>5} prb  "
                f"deliv {m['throughput_bps']/1e6:>5.2f}M ({m['delivery_ratio']:>4.0%})  "
                f"drop {m['bytes_dropped']*8/1e6:>5.1f}M"
            )

    print("\n--- Single-flow GBR UEs (ue1-7: only qfi2 in the UL) ---")
    fmt_rows(single)
    print("\n--- Mixed-flow GBR UEs (ue8-10: qfi2 + a PF flow in the UL) ---")
    fmt_rows(mixed)

    print("\n--- The extra UL flow on each mixed UE ---")
    for ue, qfi in sorted(flows):
        f = flows[(ue, qfi)]
        if ue >= 8 and f.direction == "UL" and f.flow_class != "GBR":
            fk = f"ue{ue}_qfi{qfi}"
            m = summary["flows"][fk]
            tgt = last.get((ue, qfi), 0.0)
            print(
                f"  ue{ue:<2} qfi{qfi} {f.flow_class:<3}  "
                f"offered {m['offered_bps']/1e6:>5.2f}M  "
                f"tier1 {tgt/1e6:>5.2f}M  "
                f"deliv {m['throughput_bps']/1e6:>5.2f}M ({m['delivery_ratio']:>4.0%})"
            )

    # Tier-1 sanity: does the LP fund every GBR floor it is asked for?
    tier1_gbr = sum(last.get(k, 0.0) for k in gbr)
    gfbr_total = sum(flows[k].gfbr_bps for k in gbr)
    print(
        f"\nTier-1 GBR allocation: {tier1_gbr/1e6:.1f}M of {gfbr_total/1e6:.1f}M "
        f"GFBR asked ({tier1_gbr/gfbr_total:.0%})"
    )

    # --- Control experiments: is the gap an SPS-reservation artifact? ---
    # Compare SNR-matched single-flow (ue1/2/3) vs mixed-flow (ue8/9/10) GBR
    # UEs. ue4/ue7 are excluded — their starvation is the cell-edge Finding 1.
    single3 = [(u, 2) for u in (1, 2, 3)]
    mixed3 = [(u, 2) for u in (8, 9, 10)]
    wide = dataclasses.replace(
        scenario,
        carrier=dataclasses.replace(
            scenario.carrier,
            bandwidth_hz=int(scenario.carrier.bandwidth_hz * 1.5),
        ),
    )

    def mean_deliv(summ, keys):
        return sum(
            summ["flows"][f"ue{u}_qfi{q}"]["delivery_ratio"] for u, q in keys
        ) / len(keys)

    print("\n=== Control experiments — mean GBR delivery ===")
    print(f"{'config':<34}{'ue1-3 single':>14}{'ue8-10 mixed':>14}{'gap':>8}")
    configs = [
        ("TwoTier, SPS on (default)", scenario,
         lambda: TwoTier(tier1_period_slots=2000)),
        ("TwoTier, SPS off", scenario,
         lambda: TwoTier(tier1_period_slots=2000, enable_sps=False)),
        ("TwoTier, SPS on, 1.5x carrier", wide,
         lambda: TwoTier(tier1_period_slots=2000)),
    ]
    for label, sc, factory in configs:
        s = run(sc, factory())
        sm = mean_deliv(s, single3)
        mm = mean_deliv(s, mixed3)
        print(f"{label:<34}{sm:>13.0%}{mm:>14.0%}{(sm - mm) * 100:>7.0f}pt")


if __name__ == "__main__":
    main()
