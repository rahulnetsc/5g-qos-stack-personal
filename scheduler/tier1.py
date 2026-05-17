"""Tier-1 LP solver: compute per-flow target rates over the next horizon.

Decision variables:
    r_i  (bps)         per-flow target rate
    s_i  (bps, >= 0)   GBR shortfall slack (so the LP stays feasible under
                       overload; the slack carries a large penalty)

Objective:
    maximize  sum_i  w_class_i * log(r_i + epsilon)
            -        gbr_slack_penalty * sum_i s_i

Constraints:
    sum_{i in DL} r_i / SE_i  <=  C_DL_prbs_per_sec
    sum_{i in UL} r_i / SE_i  <=  C_UL_prbs_per_sec
    r_i + s_i  >=  GFBR_i        (for GBR flows)
    r_i  <=  demand_i             (offered load cap)
    r_i, s_i  >=  0

Where SE_i = bits per PRB-symbol for UE i (function of its current SNR and
target BLER), and capacities are PRB-symbols per second derived from the TDD
pattern.
"""

import cvxpy as cp
import numpy as np

from .flow import FlowConfig
from .interfaces import GridView
from .link import bits_per_prb


def _utility_weight(flow_class: str) -> float:
    """Per-class weight on the log-utility term."""
    if flow_class == "Delay":
        return 5.0
    return 1.0


def grid_capacity_prbsym_per_sec(grid: GridView) -> tuple[float, float]:
    """Return (DL, UL) PRB-symbol capacity per second for the grid's TDD cycle."""
    pattern_len = len(grid.pattern)
    cycle_duration_s = pattern_len * grid.slot_duration_s
    dl_sym = 0
    ul_sym = 0
    for i in range(pattern_len):
        sg = grid.slot_grid(i)
        dl_sym += sg.dl_symbols
        ul_sym += sg.ul_symbols
    cap_dl = grid.prb_count * dl_sym / cycle_duration_s
    cap_ul = grid.prb_count * ul_sym / cycle_duration_s
    return cap_dl, cap_ul


def solve_tier1(
    flows: list[FlowConfig],
    snr_db_per_ue: dict[int, float],
    grid: GridView,
    demand_bps: dict[tuple[int, int], float],
    gbr_slack_penalty: "float | dict[tuple[int, int], float]" = 1e3,
    capacity_safety_factor: float = 1.0,
    se_penalty_exponent: float = 0.0,
    slice_shares: "dict[int, dict[str, float]] | None" = None,
    slice_slack_penalty: float = 1e3,
) -> dict[tuple[int, int], float]:
    """Solve Tier-1 LP. Returns target rate (bps) per (ue_id, qfi).

    gbr_slack_penalty may be a scalar (uniform penalty) or a per-flow dict
    keyed by (ue_id, qfi). The dict form is what TwoTier's adaptive
    dual-ascent update uses to escalate the penalty on GBR flows that keep
    missing their floor.

    se_penalty_exponent (k) tilts each flow's GBR slack penalty by its
    spectral efficiency: p_i is multiplied by (SE_i / SE_max) ** k.
        k = 0  -> no tilt (default; identical to the old behaviour).
        k > 0  -> discount poor-SE flows. A low-SE flow's GBR shortfall
                  drags the objective down less ("efficiency-first": spend
                  RBs where they convert to the most rate).
        k < 0  -> boost poor-SE flows. k = -1 equalises the per-RB value of
                  closing a GBR gap (p_i * SE_i) across flows -- "RB-level"
                  parity rather than rate-level.

    slice_shares ({slice_id: {"DL": frac, "UL": frac}}) adds a soft network-
    slice floor: each (slice, direction) is guaranteed its fraction of
    PRB-symbol capacity, capped at the slice's own offered demand. The floor
    is soft (a penalised slack) and the per-direction capacity constraint
    keeps it work-conserving -- a busy slice borrows an idle slice's unused
    share. slice_slack_penalty weighs a missed slice floor.
    """
    n = len(flows)
    if n == 0:
        return {}

    # Spectral efficiency per flow: bits per PRB-symbol, BLER-adjusted.
    se = np.zeros(n)
    for i, f in enumerate(flows):
        snr = snr_db_per_ue.get(f.ue_id, 20.0)
        bits, bler = bits_per_prb(snr, symbols=1)
        se[i] = max(1.0, bits * (1.0 - bler))

    # Per-flow slack penalty vector (scalar broadcasts to all flows).
    if isinstance(gbr_slack_penalty, dict):
        penalty = np.array(
            [float(gbr_slack_penalty.get((f.ue_id, f.qfi), 1e3)) for f in flows]
        )
    else:
        penalty = np.full(n, float(gbr_slack_penalty))

    # Optional spectral-efficiency tilt: p_i *= (SE_i / SE_max) ** k. See the
    # docstring -- k>0 is efficiency-first, k<0 is RB-level parity, k=0 off.
    if se_penalty_exponent != 0.0:
        se_max = float(se.max())
        if se_max > 0.0:
            penalty = penalty * (se / se_max) ** se_penalty_exponent

    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    cap_dl *= capacity_safety_factor
    cap_ul *= capacity_safety_factor

    r = cp.Variable(n, nonneg=True)
    slack = cp.Variable(n, nonneg=True)

    constraints: list = []

    dl_terms = [r[i] / se[i] for i, f in enumerate(flows) if f.direction == "DL"]
    ul_terms = [r[i] / se[i] for i, f in enumerate(flows) if f.direction == "UL"]
    if dl_terms:
        constraints.append(cp.sum(cp.hstack(dl_terms)) <= cap_dl)
    if ul_terms:
        constraints.append(cp.sum(cp.hstack(ul_terms)) <= cap_ul)

    # Demand caps and GBR floors
    for i, f in enumerate(flows):
        d = demand_bps.get((f.ue_id, f.qfi), 1e12)
        constraints.append(r[i] <= d)
        if f.flow_class == "GBR" and f.gfbr_bps > 0:
            constraints.append(r[i] + slack[i] >= f.gfbr_bps)
        else:
            constraints.append(slack[i] == 0)

    # Soft network-slice floors. Each (slice, direction) is guaranteed its
    # share of PRB-symbol capacity, capped at the slice's own offered demand
    # so an idle slice holds nothing. The per-direction capacity constraints
    # above keep this work-conserving -- a busy slice borrows the unused
    # share of an idle one. The floor is soft (a penalised slack) so the LP
    # stays feasible when slice and GBR floors cannot all be met.
    slice_slack_terms: list = []
    if slice_shares:
        cap_by_dir = {"DL": cap_dl, "UL": cap_ul}
        for sid, shares in slice_shares.items():
            for direction, cap in cap_by_dir.items():
                share = float(shares.get(direction, 0.0))
                idx = [
                    i for i, f in enumerate(flows)
                    if f.slice_id == sid and f.direction == direction
                ]
                if share <= 0.0 or not idx:
                    continue
                slice_demand = sum(
                    demand_bps.get((flows[i].ue_id, flows[i].qfi), 1e12) / se[i]
                    for i in idx
                )
                floor = min(share * cap, slice_demand)
                if floor <= 0.0:
                    continue
                ss = cp.Variable(nonneg=True)
                usage = cp.sum(cp.hstack([r[i] / se[i] for i in idx]))
                constraints.append(usage + ss >= floor)
                slice_slack_terms.append(ss)

    # Objective
    epsilon = 1.0
    utility = cp.sum(
        [_utility_weight(f.flow_class) * cp.log(r[i] + epsilon) for i, f in enumerate(flows)]
    )
    slice_penalty = (
        slice_slack_penalty * sum(slice_slack_terms) if slice_slack_terms else 0
    )
    objective = cp.Maximize(
        utility - cp.sum(cp.multiply(penalty, slack)) - slice_penalty
    )

    problem = cp.Problem(objective, constraints)
    try:
        problem.solve()
    except (cp.SolverError, Exception):
        # Fall back to demand
        return {(f.ue_id, f.qfi): demand_bps.get((f.ue_id, f.qfi), 0.0) for f in flows}

    if problem.status not in ("optimal", "optimal_inaccurate"):
        return {(f.ue_id, f.qfi): demand_bps.get((f.ue_id, f.qfi), 0.0) for f in flows}

    return {
        (f.ue_id, f.qfi): float(max(0.0, r.value[i])) for i, f in enumerate(flows)
    }


def estimate_demand_bps(f: FlowConfig) -> float:
    """Best-effort estimate of a flow's offered rate from its FlowConfig."""
    p = f.traffic_params
    kind = f.traffic_kind
    if kind == "poisson":
        return float(p.get("rate_bps", 0.0))
    if kind == "deterministic":
        period_s = p["period_ms"] / 1000.0
        return p["bytes_per_period"] * 8 / period_s
    if kind == "video_frame":
        period_s = p.get("period_ms", 16.67) / 1000.0
        avg_bytes = p["avg_bytes"]
        i_mult = p.get("i_frame_multiplier", 5.0)
        i_period = max(1, p.get("i_frame_period_in_frames", 60))
        # Average frame size accounting for I-frame inflation
        avg_frame_bytes = avg_bytes * (1.0 + (i_mult - 1.0) / i_period)
        return avg_frame_bytes * 8 / period_s
    # Unknown: be generous so the LP doesn't artificially cap us
    return 1e10
