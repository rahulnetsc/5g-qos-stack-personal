"""Tier-1 solver: compute per-flow target rates over the next horizon.

Decision variables:
    r_i  (bps)         per-flow target rate
    s_i  (bps, >= 0)   GBR shortfall slack (so the problem stays feasible
                       under overload)

Goal, in words: honour every GBR floor you can, and distribute whatever
capacity is left by weighted proportional fairness.

Constraints:
    sum_{i in DL} r_i / SE_i  <=  C_DL_prbsym_per_sec
    sum_{i in UL} r_i / SE_i  <=  C_UL_prbsym_per_sec
    r_i + s_i  >=  GFBR_i        (for GBR flows)
    r_i  >=  floor_i             (optional hard floor, see below)
    r_i  <=  demand_i            (offered load cap)
    r_i, s_i  >=  0

Where SE_i = bits per PRB-symbol for UE i (function of its current SNR and
target BLER), and capacities are PRB-symbols per second derived from the TDD
pattern.

Why two phases, not one weighted objective
------------------------------------------
The goal above is *lexicographic*: shortfall first, utility second. It used
to be written as a single objective, `max sum w log(r+eps) - sum p_i s_i`,
with `p_i = 1e3` chosen so the penalty "effectively hardens" the floor. It
does -- by a factor of ~1e7 (measured: penalty 2.4e10 against utility 709 on
`factory_robots`). That is not a weighting, it is a lexicographic order
expressed as a magnitude, and it made the program numerically unsolvable:
on the `overload` scenario CLARABEL and SCS both returned
`optimal_inaccurate` and *disagreed with each other* by 3.6x on a flow's
rate, with the Delay class -- the highest-weighted one -- under-served by
28% against the analytic optimum. Rescaling cannot fix this; the dynamic
range is in the model, not the units.

So the order is now stated directly:

    phase 1:  minimize   sum_i p_i s_i  +  p_slice sum_j ss_j
    phase 2:  maximize   sum_i w_class_i log(r_i + eps)
              subject to the phase-1 penalty staying at its optimum

Each phase is well conditioned on its own, and both are posed in normalised
units (rates as a multiple of `rate_scale`, capacity usage as a fraction of
each direction's own budget) so every coefficient is O(1). On the case above
both solvers now return `optimal` and land within 100 bps of the analytic
optimum, agreeing with each other.

`p_i` keeps its meaning as the *relative* worth of closing one flow's GBR
gap versus another's -- which is all the adaptive dual-ascent update and the
spectral-efficiency tilt ever used it for. Its absolute magnitude no longer
matters, and there is no longer a magic constant holding the model together.

Max-min GBR protection (the `solve_maxmin_gbr_level` path)
----------------------------------------------------------
Phase 1 concentrates its shortfall. Reducing flow i's slack by one bit costs
1/SE_i PRB-symbols, so with a uniform `p` the minimiser drops whichever GBR
flows are most expensive per bit -- the cell-edge ones -- and spends the
freed capacity on cheap high-SNR flows. Minimising total shortfall bits
under a capacity budget is a *fractional knapsack*, and its optimum is the
greedy one: served in full or abandoned outright. No reweighting of `p`
changes that, because the solution is a vertex; only a constraint does.

Hence `solve_maxmin_gbr_level`: it returns the largest uniform fraction `t*`
of its contracted floor that *every* GBR flow can hold simultaneously.
Feeding `gbr_maxmin_floors(..., t*)` back into `solve_tier1` as
`gbr_floor_bps` pins that fraction as a hard floor. The guarantee is on the
worst-served GBR flow; the cost is total throughput, paid by the flows the
unconstrained form would have over-served.
"""

import cvxpy as cp
import numpy as np

from .flow import FlowConfig
from .interfaces import GridView
from .link import bits_per_prb

# Offered-load sentinel: `estimate_demand_bps` returns 1e10 for a traffic
# kind it cannot size, meaning "do not cap me", not a real 100 Gbps demand.
# Binding it would put a huge coefficient into an otherwise O(1) program.
_DEMAND_SENTINEL = 1e10


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


def _spectral_efficiency(
    flows: list[FlowConfig], snr_db_per_ue: dict[int, float]
) -> np.ndarray:
    """Bits per PRB-symbol per flow, discounted by the target BLER."""
    se = np.zeros(len(flows))
    for i, f in enumerate(flows):
        snr = snr_db_per_ue.get(f.ue_id, 20.0)
        bits, bler = bits_per_prb(snr, symbols=1)
        se[i] = max(1.0, bits * (1.0 - bler))
    return se


def _capacities(
    grid: GridView, capacity_safety_factor: float
) -> dict[str, float]:
    cap_dl, cap_ul = grid_capacity_prbsym_per_sec(grid)
    return {
        "DL": cap_dl * capacity_safety_factor,
        "UL": cap_ul * capacity_safety_factor,
    }


def _rate_scale(
    flows: list[FlowConfig],
    demand_bps: dict[tuple[int, int], float],
    se: np.ndarray,
    cap_by_dir: dict[str, float],
) -> float:
    """A representative bps magnitude to express rates as multiples of.

    Every rate variable is divided by this, so the program's variables and
    coefficients come out O(1) instead of O(1e7). Any positive value gives
    the same optimum; one near the largest rate in play gives the best
    conditioning. Falls back to the largest rate the carrier could physically
    deliver when nothing else pins the scale.
    """
    candidates = [f.gfbr_bps for f in flows if f.gfbr_bps > 0]
    candidates += [
        d for d in (
            demand_bps.get((f.ue_id, f.qfi), _DEMAND_SENTINEL) for f in flows
        )
        if 0.0 < d < _DEMAND_SENTINEL
    ]
    if candidates:
        return float(max(candidates))
    se_max = float(se.max()) if len(se) else 1.0
    cap_max = max(cap_by_dir.values(), default=0.0)
    return max(1.0, cap_max * se_max)


def _capacity_constraints(
    u: cp.Variable, flows: list[FlowConfig], se: np.ndarray,
    cap_by_dir: dict[str, float], rate_scale: float,
) -> list:
    """Per-direction PRB-symbol budget, divided through by the budget itself
    so each constraint reads "fraction of this direction used <= 1"."""
    cons: list = []
    for direction, cap in cap_by_dir.items():
        idx = [i for i, f in enumerate(flows) if f.direction == direction]
        if not idx or cap <= 0.0:
            continue
        cons.append(
            cp.sum(cp.hstack(
                [u[i] * (rate_scale / (se[i] * cap)) for i in idx]
            )) <= 1.0
        )
    return cons


def _demand_constraints(
    u: cp.Variable, flows: list[FlowConfig],
    demand_bps: dict[tuple[int, int], float], rate_scale: float,
) -> list:
    """Offered-load caps, skipping the "do not cap me" sentinel."""
    cons: list = []
    for i, f in enumerate(flows):
        d = demand_bps.get((f.ue_id, f.qfi), _DEMAND_SENTINEL)
        if d < _DEMAND_SENTINEL:
            cons.append(u[i] <= d / rate_scale)
    return cons


def _slice_floor_constraints(
    u: cp.Variable, flows: list[FlowConfig], se: np.ndarray,
    demand_bps: dict[tuple[int, int], float], cap_by_dir: dict[str, float],
    slice_shares: "dict[int, dict[str, float]] | None", rate_scale: float,
) -> tuple[list, list[tuple[cp.Variable, float]]]:
    """Soft per-(slice, direction) PRB-symbol floors, in normalised units.

    Each floor is capped at the slice's own offered demand so an idle slice
    holds nothing, and it is soft (a penalised slack) so the program stays
    feasible when slice and GBR floors collide. The per-direction capacity
    constraints keep it work-conserving -- a busy slice borrows the unused
    share of an idle one.

    Returns (constraints, [(slack_var, direction_capacity)]). The capacity is
    handed back so the caller can weigh a slack in the original PRB-symbol
    units, keeping `slice_slack_penalty` comparable with the GBR penalty.
    """
    cons: list = []
    slacks: list[tuple[cp.Variable, float]] = []
    if not slice_shares:
        return cons, slacks
    for sid, shares in slice_shares.items():
        for direction, cap in cap_by_dir.items():
            share = float(shares.get(direction, 0.0))
            idx = [
                i for i, f in enumerate(flows)
                if f.slice_id == sid and f.direction == direction
            ]
            if share <= 0.0 or not idx or cap <= 0.0:
                continue
            slice_demand = sum(
                demand_bps.get((flows[i].ue_id, flows[i].qfi), 1e12) / se[i]
                for i in idx
            )
            floor = min(share * cap, slice_demand)
            if floor <= 0.0:
                continue
            ss = cp.Variable(nonneg=True)
            usage = cp.sum(cp.hstack(
                [u[i] * (rate_scale / (se[i] * cap)) for i in idx]
            ))
            cons.append(usage + ss >= floor / cap)
            slacks.append((ss, cap))
    return cons, slacks


def gbr_contract_bps(
    f: FlowConfig, demand_bps: dict[tuple[int, int], float]
) -> float:
    """The GBR floor this flow can actually reach: its GFBR, capped by its
    own offered demand.

    The demand cap matters for the max-min stage: a GBR flow that offers
    less than its GFBR can never reach 100% of it, and without the cap it
    would pin the uniform satisfaction level at its own unreachable ratio
    and drag every other flow down with it. Returns 0.0 for non-GBR flows.
    """
    if f.flow_class != "GBR" or f.gfbr_bps <= 0:
        return 0.0
    d = demand_bps.get((f.ue_id, f.qfi), float("inf"))
    return min(float(f.gfbr_bps), float(d))


def solve_maxmin_gbr_level(
    flows: list[FlowConfig],
    snr_db_per_ue: dict[int, float],
    grid: GridView,
    demand_bps: dict[tuple[int, int], float],
    capacity_safety_factor: float = 1.0,
    slice_shares: "dict[int, dict[str, float]] | None" = None,
    slice_slack_penalty: float = 1e3,
) -> float:
    """Stage A -- the max-min GBR satisfaction level.

    Solves

        maximize  t
        s.t.      r_i >= t * contract_i     for every GBR flow i
                  r_i <= demand_i
                  per-direction PRB-symbol capacity
                  soft slice floors
                  0 <= t <= 1

    and returns `t*`: the largest fraction of its contracted floor that
    *every* GBR flow can be held at simultaneously. `t* == 1` means the GBR
    set is jointly feasible; below that the cell is in GBR overload and `t*`
    is the best guaranteeable floor.

    Non-GBR flows appear only in the capacity constraint and are unrewarded
    by the objective, so this is the level reachable when GBR is the sole
    claimant on the carrier -- deliberately the *most* protective reading.
    Use `gbr_maxmin_floors(..., scale=)` to hold back some of it for the
    best-effort and Delay classes.

    Returns 1.0 when there are no GBR flows (nothing to protect), and 0.0 if
    the solve fails -- either way `gbr_maxmin_floors` then imposes no
    binding floor and `solve_tier1` behaves exactly as it does without one.
    """
    contracts = {(f.ue_id, f.qfi): gbr_contract_bps(f, demand_bps) for f in flows}
    gbr_idx = [
        i for i, f in enumerate(flows) if contracts[(f.ue_id, f.qfi)] > 0.0
    ]
    if not gbr_idx:
        return 1.0

    se = _spectral_efficiency(flows, snr_db_per_ue)
    cap_by_dir = _capacities(grid, capacity_safety_factor)
    scale = _rate_scale(flows, demand_bps, se, cap_by_dir)

    u = cp.Variable(len(flows), nonneg=True)
    t = cp.Variable(nonneg=True)

    constraints: list = [t <= 1.0]
    constraints += _capacity_constraints(u, flows, se, cap_by_dir, scale)
    constraints += _demand_constraints(u, flows, demand_bps, scale)

    # The max-min coupling: every GBR flow held at the same fraction t of
    # its own contract.
    for i in gbr_idx:
        f = flows[i]
        constraints.append(u[i] >= t * (contracts[(f.ue_id, f.qfi)] / scale))

    slice_cons, slice_slacks = _slice_floor_constraints(
        u, flows, se, demand_bps, cap_by_dir, slice_shares, scale
    )
    constraints += slice_cons

    # t and the normalised slice slacks are both fractions in [0, 1], so
    # slice_slack_penalty keeps a "worth this many t-units" meaning rather
    # than being swamped by PRB-symbol magnitudes.
    objective_expr = t
    if slice_slacks:
        objective_expr = objective_expr - slice_slack_penalty * sum(
            ss for ss, _ in slice_slacks
        )

    problem = cp.Problem(cp.Maximize(objective_expr), constraints)
    try:
        problem.solve()
    except Exception:
        return 0.0
    if problem.status not in ("optimal", "optimal_inaccurate"):
        return 0.0
    if t.value is None:
        return 0.0
    return float(min(1.0, max(0.0, t.value)))


def gbr_maxmin_floors(
    flows: list[FlowConfig],
    demand_bps: dict[tuple[int, int], float],
    level: float,
    scale: float = 1.0,
    tolerance: float = 1e-6,
) -> dict[tuple[int, int], float]:
    """Turn a max-min level into per-flow hard floors for `solve_tier1`.

    Floor is `scale * level * contract_i`. `scale` dials how much of the
    achievable protection to actually claim:
        1.0 -> full max-min protection (the guaranteed floor is t*),
        0.0 -> no floor at all (identical to solving without the stage),
    and anything between leaves the balance to the log utility, which is
    also what funds the Delay and best-effort classes. The `tolerance`
    shave keeps the floors strictly inside the region stage A proved
    feasible, so solver round-off cannot make the next solve infeasible.
    """
    frac = (
        max(0.0, min(1.0, scale))
        * max(0.0, min(1.0, level))
        * (1.0 - tolerance)
    )
    if frac <= 0.0:
        return {}
    floors: dict[tuple[int, int], float] = {}
    for f in flows:
        contract = gbr_contract_bps(f, demand_bps)
        if contract > 0.0:
            floors[(f.ue_id, f.qfi)] = frac * contract
    return floors


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
    gbr_floor_bps: "dict[tuple[int, int], float] | None" = None,
) -> dict[tuple[int, int], float]:
    """Solve Tier-1. Returns target rate (bps) per (ue_id, qfi).

    Two phases, in lexicographic order (see the module docstring): phase 1
    minimises weighted GBR/slice shortfall, phase 2 maximises weighted log
    utility without giving any of that shortfall back.

    gbr_slack_penalty may be a scalar (uniform) or a per-flow dict keyed by
    (ue_id, qfi). It sets the *relative* worth of closing one flow's GBR gap
    against another's; its absolute magnitude no longer matters, since the
    shortfall-before-utility ordering is now structural rather than a
    consequence of the penalty being large. The dict form is what TwoTier's
    adaptive dual-ascent update uses to escalate the penalty on GBR flows
    that keep missing their floor.

    se_penalty_exponent (k) tilts each flow's GBR penalty by its spectral
    efficiency: p_i is multiplied by (SE_i / SE_max) ** k.
        k = 0  -> no tilt (default).
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
    share. slice_slack_penalty weighs a missed slice floor against a missed
    GBR floor, in the original bps / PRB-symbol units.

    gbr_floor_bps adds a *hard* per-flow lower bound on top of the usual
    soft GFBR constraint -- the second stage of the max-min path. Build it
    with `gbr_maxmin_floors` from a level returned by
    `solve_maxmin_gbr_level`; floors from anywhere else risk an infeasible
    problem, in which case the solve falls back to demand as it does for any
    other failure. The soft GFBR constraint is kept alongside the floor, so
    phase 2 still has an incentive to close the remaining gap to full GFBR
    wherever that is cheap.
    """
    n = len(flows)
    if n == 0:
        return {}

    se = _spectral_efficiency(flows, snr_db_per_ue)
    cap_by_dir = _capacities(grid, capacity_safety_factor)
    scale = _rate_scale(flows, demand_bps, se, cap_by_dir)

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

    def _demand_fallback() -> dict[tuple[int, int], float]:
        return {
            (f.ue_id, f.qfi): demand_bps.get((f.ue_id, f.qfi), 0.0)
            for f in flows
        }

    u = cp.Variable(n, nonneg=True)          # rate, in units of `scale`
    v = cp.Variable(n, nonneg=True)          # GBR shortfall, same units

    constraints: list = []
    constraints += _capacity_constraints(u, flows, se, cap_by_dir, scale)
    constraints += _demand_constraints(u, flows, demand_bps, scale)

    for i, f in enumerate(flows):
        d = demand_bps.get((f.ue_id, f.qfi), _DEMAND_SENTINEL)
        if f.flow_class == "GBR" and f.gfbr_bps > 0:
            constraints.append(u[i] + v[i] >= f.gfbr_bps / scale)
            if gbr_floor_bps:
                floor = float(gbr_floor_bps.get((f.ue_id, f.qfi), 0.0))
                if floor > 0.0:
                    constraints.append(u[i] >= min(floor, d) / scale)
        else:
            constraints.append(v[i] == 0)

    slice_cons, slice_slacks = _slice_floor_constraints(
        u, flows, se, demand_bps, cap_by_dir, slice_shares, scale
    )
    constraints += slice_cons

    # Total weighted shortfall, in the *original* units (bps for GBR slack,
    # PRB-symbols for slice slack) so the two penalties stay comparable,
    # then divided by a common factor to bring the expression back to O(1).
    shortfall_scale = max(1.0, float(penalty.max()) * scale)
    shortfall = cp.sum(cp.multiply(penalty * scale / shortfall_scale, v))
    if slice_slacks:
        shortfall = shortfall + sum(
            (slice_slack_penalty * cap / shortfall_scale) * ss
            for ss, cap in slice_slacks
        )

    # Phase 1 -- how much shortfall is unavoidable?
    phase1 = cp.Problem(cp.Minimize(shortfall), constraints)
    try:
        phase1.solve()
    except Exception:
        return _demand_fallback()
    if phase1.status not in ("optimal", "optimal_inaccurate") or u.value is None:
        return _demand_fallback()
    min_shortfall = max(0.0, float(phase1.value))
    phase1_rates = np.asarray(u.value, dtype=float).copy()

    # Phase 2 -- best utility that gives none of it back. The budget is
    # nudged out by a hair so phase 1's own solver tolerance cannot make
    # phase 2 infeasible.
    epsilon = 1.0
    utility = cp.sum([
        _utility_weight(f.flow_class) * cp.log(u[i] + epsilon / scale)
        for i, f in enumerate(flows)
    ])
    budget = min_shortfall * (1.0 + 1e-6) + 1e-9
    phase2 = cp.Problem(
        cp.Maximize(utility), constraints + [shortfall <= budget]
    )
    try:
        phase2.solve()
    except Exception:
        phase2 = None
    if (
        phase2 is None
        or phase2.status not in ("optimal", "optimal_inaccurate")
        or u.value is None
    ):
        # Keep phase 1's answer: it already honours every floor it could,
        # which is strictly more useful than falling back to raw demand.
        return {
            (f.ue_id, f.qfi): float(max(0.0, phase1_rates[i] * scale))
            for i, f in enumerate(flows)
        }

    return {
        (f.ue_id, f.qfi): float(max(0.0, u.value[i] * scale))
        for i, f in enumerate(flows)
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
    # Unknown: be generous so the solve doesn't artificially cap us
    return _DEMAND_SENTINEL
