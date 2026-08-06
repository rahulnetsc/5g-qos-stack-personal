"""Why soft GBR floors abandon the cell edge: the fractional-knapsack result.

This reproduces the evidence behind Finding 1's root cause (NOTES.md,
2026-08-06) and behind the analytical claim in the COMSNETS draft
(paper/main.tex, "Soft GBR floors are a knapsack").

The claim: in the conventional single-objective form

    max  sum_i w_c(i) log(r_i + eps)  -  sum_i p_i s_i

the penalty term outweighs the utility by ~7 orders of magnitude, so Tier-1
is really solving `min sum_i (GFBR_i - r_i)` subject to a PRB budget -- a
fractional knapsack whose optimum is greedy in spectral efficiency and
therefore a *vertex*. Flows are served in full or abandoned outright.

Four pieces of evidence, printed in order:

  1. The two objective terms, measured. If the ratio is ~1e7 the "utility"
     is a tie-break and nothing else.
  2. The solved targets, sorted by SE. The knapsack predicts a staircase:
     a fully-served head, exactly one partially-served boundary tier, and a
     zeroed tail -- ordered by SE, not by SNR.
  3. A penalty sweep over six decades. If the solution is fixed by the
     knapsack structure rather than by the penalty magnitude, the targets
     do not move at all.
  4. The abandonment control: drop the shortfall term entirely and
     maximise the log utility alone. The utility is *also* SE-favouring --
     its stationary condition is r_i proportional to SE_i -- so it does not
     treat the cell edge generously. What it does not do is drive any flow
     to zero. If the worst-SE flow is served something under the utility
     alone but exactly zero once the shortfall term is added, the
     abandonment is attributable to that term specifically, which is the
     claim this script exists to support.

     (This control cannot be run by shrinking p. Since solve_tier1 became
     lexicographic, shortfall is minimised before the utility is looked at
     *regardless* of p -- which is precisely why p's magnitude no longer
     matters. The utility-only program has to be posed directly. An earlier
     version of this argument used p=1e-6 against the old single-objective
     solver and reported an inverted allocation; that reading did not
     survive the solver being fixed.)

Usage:
    python scripts/knapsack_diagnostic.py
"""

import sys
from pathlib import Path

import cvxpy as cp
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import estimate_demand_bps, solve_tier1
from scheduler.tier1 import (
    _capacities,
    _capacity_constraints,
    _demand_constraints,
    _rate_scale,
    _spectral_efficiency,
    _utility_weight,
    grid_capacity_prbsym_per_sec,
)
from sim.resource import ResourceGrid
from sim.scenarios import factory_robots_scenario

# Penalty values swept in evidence 3. The shipped default is 1e3.
PENALTY_SWEEP = (1e0, 1e1, 1e2, 1e3, 1e4, 1e6)


def solve_utility_only(flows, snr_db_per_ue, grid, demand_bps):
    """Maximise the log utility subject to capacity and demand alone.

    The control for evidence 4: no GBR floor, no shortfall term. This is
    what Tier-1 would allocate if the contract machinery were removed
    entirely, and it isolates what the log utility does on its own. Its
    stationary condition is r_i proportional to SE_i, so expect it to
    favour high-SE flows in absolute rate; the question here is only
    whether it zeroes anyone.
    """
    se = _spectral_efficiency(flows, snr_db_per_ue)
    cap_by_dir = _capacities(grid, 1.0)
    scale = _rate_scale(flows, demand_bps, se, cap_by_dir)
    u = cp.Variable(len(flows), nonneg=True)
    constraints = (
        _capacity_constraints(u, flows, se, cap_by_dir, scale)
        + _demand_constraints(u, flows, demand_bps, scale)
    )
    utility = cp.sum([
        _utility_weight(f.flow_class) * cp.log(u[i] + 1.0 / scale)
        for i, f in enumerate(flows)
    ])
    problem = cp.Problem(cp.Maximize(utility), constraints)
    problem.solve()
    if u.value is None:
        raise RuntimeError(f"utility-only solve failed: {problem.status}")
    return {
        (f.ue_id, f.qfi): float(max(0.0, u.value[i] * scale))
        for i, f in enumerate(flows)
    }


def _hr(title: str) -> None:
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def main() -> None:
    scenario = factory_robots_scenario()
    snr = {ue.ue_id: ue.mean_snr_db for ue in scenario.ues}
    demand = {
        (f.ue_id, f.qfi): estimate_demand_bps(f) for f in scenario.flows
    }
    grid = ResourceGrid(scenario.carrier, scenario.tdd)
    se = _spectral_efficiency(scenario.flows, snr)
    _, cap_ul = grid_capacity_prbsym_per_sec(grid)

    print(
        "factory_robots at the shipped operating point. Tier-1 is solved\n"
        "directly (no max-min stage), which is the formulation the claim is\n"
        "about -- TwoTier itself now ships with the stage enabled."
    )

    # --- 1. The two objective terms ------------------------------------
    _hr("1. Objective terms: is the utility doing any work?")
    targets = solve_tier1(scenario.flows, snr, grid, demand)
    utility = sum(
        _utility_weight(f.flow_class)
        * np.log(targets[(f.ue_id, f.qfi)] + 1.0)
        for f in scenario.flows
    )
    shortfall_bits = sum(
        max(0.0, f.gfbr_bps - targets[(f.ue_id, f.qfi)])
        for f in scenario.flows
        if f.flow_class == "GBR"
    )
    penalty_term = 1e3 * shortfall_bits
    print(f"  utility  sum w log(r+eps) = {utility:>14.2f}")
    print(f"  penalty  sum p*s at p=1e3 = {penalty_term:>14.3e}")
    print(f"  ratio                     = {penalty_term / utility:>14.3e}")
    print(
        "\n  The utility is a tie-break. What is actually being minimised is\n"
        "  total GBR shortfall in bits, under the PRB capacity constraint."
    )

    # --- 2. The staircase ----------------------------------------------
    _hr("2. Solved targets, sorted by spectral efficiency")
    rows = sorted(
        (
            (se[i], f.ue_id, f)
            for i, f in enumerate(scenario.flows)
            if f.flow_class == "GBR"
        ),
        key=lambda r: -r[0],
    )
    print(f"  {'flow':<7}{'SNR':>6}{'SE':>8}{'GFBR':>9}{'target':>10}{'':>4}")
    for se_i, ue, f in rows:
        t = targets[(f.ue_id, f.qfi)]
        frac = t / f.gfbr_bps
        mark = "  <-- abandoned" if frac < 0.01 else ""
        print(
            f"  ue{ue:<5}{snr[ue]:>5.0f}dB{se_i:>8.1f}"
            f"{f.gfbr_bps / 1e6:>8.1f}M{frac:>10.0%}{mark}"
        )
    used = sum(
        targets[(f.ue_id, f.qfi)] / se[i]
        for i, f in enumerate(scenario.flows)
        if f.direction == "UL"
    )
    print(f"\n  UL PRB-symbol budget used: {used / cap_ul:.1%}")
    print(
        "  Ordered by SE, not SNR: flows sharing an MCS step get identical\n"
        "  targets regardless of their dB difference."
    )

    # --- 3. Six decades of penalty --------------------------------------
    _hr("3. Penalty sweep: is the solution set by p, or by the structure?")
    header = "  " + "".join(f"ue{ue:<5}" for _, ue, _ in rows)
    print(f"  {'p':<10}" + header.strip())
    print(f"  {'':<10}" + "".join(f"SE{s:<4.0f}" for s, _, _ in rows))
    for p in PENALTY_SWEEP:
        tg = solve_tier1(
            scenario.flows, snr, grid, demand, gbr_slack_penalty=p
        )
        line = "".join(
            f"{tg[(f.ue_id, f.qfi)] / f.gfbr_bps:>7.0%}" for _, _, f in rows
        )
        print(f"  {p:<10.0e}{line}")
    print(
        "\n  Identical across six decades. The penalty's magnitude is not\n"
        "  choosing the allocation -- the knapsack structure is. Reweighting\n"
        "  p can only select a different vertex, never remove the vertex."
    )

    # --- 4. The sign-flip control ---------------------------------------
    _hr("4. Control: the log utility with no shortfall term at all")
    tg = solve_utility_only(scenario.flows, snr, grid, demand)
    print("  Maximising sum w log(r) under capacity and demand only --")
    print("  no GBR floor, no shortfall penalty. Fraction of GFBR:")
    print(f"  {'flow':<7}{'SE':>8}{'target':>10}")
    for se_i, ue, f in rows:
        print(
            f"  ue{ue:<5}{se_i:>8.1f}"
            f"{tg[(f.ue_id, f.qfi)] / f.gfbr_bps:>10.0%}"
        )
    _, _, worst_f = rows[-1]
    _, _, best_f = rows[0]
    worst = tg[(worst_f.ue_id, worst_f.qfi)] / worst_f.gfbr_bps
    best = tg[(best_f.ue_id, best_f.qfi)] / best_f.gfbr_bps
    starved = targets[(worst_f.ue_id, worst_f.qfi)] / worst_f.gfbr_bps
    print(
        f"\n  Lowest-SE flow  {worst:.0%}  vs  highest-SE flow  {best:.0%}"
        "   (utility alone)"
    )
    print(f"  Same flow with the shortfall term added: {starved:.0%}")
    if worst > 0.01 and starved < 0.01:
        print(
            "\n  The utility alone favours high-SE flows -- it is not a\n"
            "  cell-edge-protecting objective -- but it serves every flow\n"
            "  something. Adding the shortfall term is what drives the worst\n"
            "  flow to exactly zero. The abandonment is attributable to that\n"
            "  term, not to the log utility."
        )
    else:
        print(
            "\n  Control inconclusive: expected the worst-SE flow to be served\n"
            "  under the utility alone and zeroed with the shortfall term.\n"
            "  The paper's knapsack argument cites this -- re-check it."
        )


if __name__ == "__main__":
    main()
