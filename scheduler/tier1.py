"""Tier-1 solver: SCA-wrapped LP for per-flow target rates (bps).

Phase 2 (`docs/phase2-plan.md`, two-tier commit 2): rewritten from
`oai-branches/two-tier/ia_p5g_scheduler.c`'s `ia_p5g_sca_solve`
(`:974-1103`) and `ia_p5g_tier1_thread`'s flow-building loop
(`:1120-1345`), read directly, not from any prior summary. This is a
*simpler* mechanism than what it replaces, not a smaller version of it:
the pre-Phase-2 implementation was not a rough approximation of the
deployed scheduler, it was a more elaborate scheduler solving a different
and easier problem (perfect future demand, several free knobs, extra
protective staging) -- five of its mechanisms have no counterpart in the
deployed code at all, and a sixth (demand) was optimistic in a specific,
citable sense, not merely simplified. See `README.md` §7 for each,
individually confirmed against this file, not inherited:

- No lexicographic two-phase split. `ia_p5g_sca_solve` is a *single* SCA
  outer loop: each iteration re-linearizes the log-utility objective
  (`coef_i = weight_i / (r_prev_i + ε)`), solves *one* plain LP, damps the
  result, checks convergence. There is no "phase 1 minimise shortfall,
  phase 2 maximise utility" structure -- that split, and the numerical-
  conditioning argument that motivated it, was specific to the deleted
  Python's own cvxpy log-utility formulation, not something ground truth
  needs.
- No max-min GBR pre-stage, no adaptive dual-ascent penalty, no
  spectral-efficiency penalty tilt, no network slicing, no hard-floor
  override on top of the soft GFBR constraint. Every GBR flow's slack
  column gets the *same fixed* penalty (`_GBR_PENALTY = 1.0e3`,
  `IA_P5G_TIER1_GBR_PENALTY`), set once, never adjusted.
- Weight is priority-*threshold*-based (`priority ∈ (0, 20] → 5.0, else
  1.0`, `ia_p5g_weight_from_priority`, `:959-962`), not flow-class-based.
  The C's own comment admits this is a judgment call ("no explicit
  traffic-class field exists in the C struct... flagged as tunable") --
  ported as the real rule against `FlowConfig.priority_level`, not
  `flow_class == "Delay"`, which coincides with it on this repo's current
  scenarios but is not the same rule.
- Demand is *always* a windowed-arrival measurement, never an oracle.
  DL: raw `(delivered_cum + backlog) − last-cycle snapshot`, divided by
  elapsed time, never smoothed (`:1256`, `:1289-1290` -- the RLC buffer is
  exact and stable). UL: the same base quantity, EWMA-smoothed at
  `_UL_DEMAND_ALPHA = 0.3` (`:1291-1294`) with a raw-value fallback when
  the smoothed estimate is still zero (`:1299-1301`, first cycle after
  attach), further capped by the UE's PHR power headroom (`:1303-1313` --
  a WP1/`sim/power.py` connection point; `sim/power.py` stays dormant per
  this repo's own convention, not wired here). The demand cap on `r_i` is
  *unconditional* (`GLP_DB(0, demand_bps)` on every column, always) --
  not a toggle, unlike the deleted Python's `apply_demand_cap=False`
  default.
- Capacity gets a *fixed* overhead factor (`_OVERHEAD_FACTOR = 0.80`,
  `IA_P5G_TIER1_OVERHEAD_FACTOR`, "PDCCH/DMRS/CSI-RS, per §7.3"), baked
  into the capacity computation itself (`ia_p5g_compute_capacity`,
  `:889-917`) -- not a free, sweepable `capacity_safety_factor` kwarg.
- Capacity is **whole-slot** granularity, not per-symbol: only slots that
  are wholly DL or wholly UL count at all (`get_full_dl_slots_per_period`/
  `get_full_ul_slots_per_period`, confirmed in the full OAI checkout,
  `openair2/LAYER2/NR_MAC_gNB/config.c:313-347` -- a mixed/special slot
  contributes to *neither* direction's capacity). This is deliberately
  **not** the same computation as `grid_capacity_prbsym_per_sec` below
  (symbol-granular, credits a special slot's actual DL/UL symbol split,
  and is left untouched for whatever else still calls it) -- see
  `tier1_capacity_prbslot_per_sec`'s own docstring for the fork.

`docs/phase2-plan.md` D3 (solver choice): `scipy.optimize.linprog`, not
cvxpy. Ground truth's "utility" solve is never a real convex log
objective -- it's a *sequence* of plain LP re-solves, log-utility only in
the limit of the SCA iteration. `linprog` inside a Python-level loop
mirrors that control structure directly (one plain LP per iteration,
exactly like the C's one `glp_simplex` call per iteration); cvxpy's
natural expression as a single high-level convex solve would be a
structural mismatch to what ground truth actually does.
"""

import numpy as np
from scipy.optimize import linprog

from .flow import FlowConfig
from .interfaces import GridView
from .link import bits_per_prb

# ia_p5g_scheduler.c:371-388, values transcribed directly, not re-derived.
_EPSILON = 1.0            # IA_P5G_TIER1_EPSILON -- r_prev seed, SCA coef
                           # denominator, AND the zero-demand threshold --
                           # three roles for one named constant in the C.
_GBR_PENALTY = 1.0e3       # IA_P5G_TIER1_GBR_PENALTY, fixed, every GBR
                           # flow, every cycle -- not adaptive.
_SCA_ALPHA = 0.2           # IA_P5G_TIER1_SCA_ALPHA
_SCA_MAXITERS = 150        # IA_P5G_TIER1_SCA_MAXITERS
_SCA_TOL = 1e-6            # IA_P5G_TIER1_SCA_TOL

# --- objective scaling: a numerical fix, NOT a model change --------------
#
# `linprog` is handed `c * _OBJ_SCALE`. Scaling a linear objective by a
# positive constant is EXACTLY argmax-invariant -- the feasible set, the
# optimal face and the optimal `x` are unchanged as mathematics. It is here
# because the unscaled objective is not solvable to its own optimum at
# HiGHS's default tolerances.
#
# THE MEASUREMENT (docs/tier1-lp-analysis-2026-09-05.md, 6,842 captured LPs
# from one real run):
#   * the objective spans 9.85 orders -- min |c_j| = 1.40e-7, a factor 1.4
#     above HiGHS's 1e-7 default dual feasibility tolerance, against the
#     GBR penalty at 1e3. A reduced cost that close to the tolerance is not
#     distinguishable from zero by the solver's own optimality test.
#   * the problem separates by direction into a continuous knapsack, so a
#     greedy solves it EXACTLY. Against that exact reference the unscaled
#     call is never better, STRICTLY WORSE on 57 of 856 solves, and returns
#     the correct x on only 11.3 %. Scaled, 98.8 %.
#   * under an argmax-invariant column permutation the unscaled answer
#     changes on 88.6 % of solves; scaled, 1.8 %.
#
# WHY 1e4 IS NOT A TUNED CONSTANT. The regression corpus is BYTE-IDENTICAL
# for every K in [1e3, 1e6] -- four decades -- and differs at 1e2 and at
# 1e7 and above. 1e4 sits in the interior of that band, and it puts the
# smallest coefficient ~4 orders above the dual tolerance (1.4e-3) while
# leaving the penalty at 1e7, far from any precision concern. Choosing a
# plateau interior is the point; the specific decade is not load-bearing.
#
# NOT a speedup -- the LP remains ~43.5 % of TwoTier's driver time. NOT the
# missing `glp_scale_prob(lp, GLP_SF_GM)` the C calls at
# ia_p5g_scheduler.c:1053, which is a MATRIX treatment for a 2.83-order
# span and is a separate item.
_OBJ_SCALE = 1.0e4
_DELAY_PRIO_THRESH = 20    # IA_P5G_TIER1_DELAY_PRIO_THRESH
_DELAY_WEIGHT = 5.0        # IA_P5G_TIER1_DELAY_WEIGHT
_PF_WEIGHT = 1.0           # IA_P5G_TIER1_PF_WEIGHT
_OVERHEAD_FACTOR = 0.80    # IA_P5G_TIER1_OVERHEAD_FACTOR, "PDCCH/DMRS/CSI-RS"
_UL_DEMAND_ALPHA = 0.3     # IA_P5G_UL_DEMAND_ALPHA

# scheduler/link.py's own established convention (bits_per_prb's default
# arg, repeated at every call site in that file) -- this simulator's
# GridView/SlotView protocol has no symbols-per-slot field of its own.
_SYMBOLS_PER_SLOT = 14


def _weight_from_priority(priority_level: int) -> float:
    """ia_p5g_weight_from_priority, ia_p5g_scheduler.c:959-962."""
    if 0 < priority_level <= _DELAY_PRIO_THRESH:
        return _DELAY_WEIGHT
    return _PF_WEIGHT


def grid_capacity_prbsym_per_sec(grid: GridView) -> tuple[float, float]:
    """Return (DL, UL) PRB-*symbol* capacity per second for the grid's TDD
    cycle -- unchanged from before Phase 2, symbol-granular (credits a
    special slot's actual DL/UL symbol split). Kept for whatever else
    still calls it; Tier-1 itself uses `tier1_capacity_prbslot_per_sec`
    instead (see that function's own docstring for why they differ)."""
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


def tier1_capacity_prbslot_per_sec(grid: GridView) -> tuple[float, float]:
    """Return (DL, UL) PRB-*slot* capacity per second, Tier-1's own unit
    (`ia_p5g_compute_capacity`, `ia_p5g_scheduler.c:889-917`, comment:
    "Capacity (PRB-slot-units/sec)").

    Whole-slot discretization: a slot counts toward `full_dl` iff it is
    wholly DL (`ul_symbols == 0` and `dl_symbols > 0`), toward `full_ul`
    iff wholly UL (`dl_symbols == 0` and `ul_symbols > 0`) -- a mixed
    (special) slot has both `> 0` and counts toward neither, matching the
    C's `get_full_dl_slots_per_period`/`get_full_ul_slots_per_period`
    (confirmed in the full OAI checkout, `config.c:313-347`: a `slot_type
    == TDD_NR_DOWNLINK_SLOT`/`_UPLINK_SLOT` bitmap check, deliberately the
    *stricter* of two available helpers -- a sibling pair,
    `get_dl_slots_per_period`/`get_ul_slots_per_period`, explicitly
    documented as "full DL slots **+ mixed slots with DL symbols**",
    exists in the same file and is NOT what `ia_p5g_compute_capacity`
    calls). This simulator's `SlotView` has no `slot_type` enum, but the
    derived condition above is exactly equivalent by construction -- a
    "downlink slot" has zero UL symbols, structurally.

    Genuinely different from `grid_capacity_prbsym_per_sec`, not a
    unit-conversion of it: on this repo's own `"DSUUU"` pattern with a
    mixed S slot, the symbol-granular function credits that slot's actual
    DL/UL split to each direction; this one credits it to neither. Ported
    as its own function, not a parameter on the shared one, so a caller
    that still wants symbol granularity for something else is unaffected.
    """
    pattern_len = len(grid.pattern)
    cycle_duration_s = pattern_len * grid.slot_duration_s
    full_dl = 0
    full_ul = 0
    for i in range(pattern_len):
        sg = grid.slot_grid(i)
        if sg.ul_symbols == 0 and sg.dl_symbols > 0:
            full_dl += 1
        elif sg.dl_symbols == 0 and sg.ul_symbols > 0:
            full_ul += 1
    slots_per_sec_dl = full_dl / cycle_duration_s
    slots_per_sec_ul = full_ul / cycle_duration_s
    cap_dl = grid.prb_count * slots_per_sec_dl * _OVERHEAD_FACTOR
    cap_ul = grid.prb_count * slots_per_sec_ul * _OVERHEAD_FACTOR
    return cap_dl, cap_ul


def _spectral_efficiency_per_slot(
    flows: list[FlowConfig], snr_db_per_ue: dict[int, float]
) -> np.ndarray:
    """Bits per PRB per *slot* (14 symbols) per flow, discounted by target
    BLER -- matches `tier1_capacity_prbslot_per_sec`'s own unit
    (`ia_p5g_estimate_se_dl`/`_ul`, `ia_p5g_scheduler.c:924-942`,
    `nr_compute_tbs(Qm, R, 1, 14, ...)`). NOT the old per-symbol
    `_spectral_efficiency` (`symbols=1`) -- that convention belonged to
    `grid_capacity_prbsym_per_sec`'s own units, not this one's."""
    se = np.zeros(len(flows))
    for i, f in enumerate(flows):
        snr = snr_db_per_ue.get(f.ue_id, 20.0)
        bits, bler = bits_per_prb(snr, symbols=_SYMBOLS_PER_SLOT)
        se[i] = max(1.0, bits * (1.0 - bler))
    return se


def solve_tier1(
    flows: list[FlowConfig],
    snr_db_per_ue: dict[int, float],
    grid: GridView,
    demand_bps: dict[tuple[int, int], float],
) -> dict[tuple[int, int], float]:
    """SCA-wrapped LP, `ia_p5g_sca_solve` (`ia_p5g_scheduler.c:974-1103`).

    Decision variables per flow: `r_i` (bps, target rate) and `s_i` (bps,
    GBR shortfall slack, GBR flows only). Each SCA iteration re-linearizes
    the log-utility around the previous iterate (`coef_i = weight_i /
    (r_prev_i + EPSILON)`), solves one LP maximizing `sum coef_i*r_i -
    GBR_PENALTY*sum s_i` subject to the per-direction capacity budget and
    (for GBR flows) `r_i + s_i >= gfbr_i`, then damps the result toward
    the previous iterate (`ALPHA=0.2`) and checks relative convergence
    (`TOL=1e-6`, up to `MAXITERS=150`).

    Returns `{}` if the very first iteration fails to solve -- the C's own
    comment calls this "essentially never triggers in practice" (the GBR
    floor is a soft constraint, so the LP is always feasible by
    construction) -- signaling the caller to keep its own last-known-good
    targets unchanged, the same fail-soft behavior `t1out.dl_target_bps`/
    `ul_target_bps` get for free in the C by never being overwritten on a
    failed cycle (this simulator has no equivalent persistent output
    buffer, so the caller must implement the "don't overwrite" half
    itself -- see `two_tier.py::_resolve_tier1`). A LATER iteration
    failing (rare; only the first is "essentially never") keeps whatever
    the last successful iteration wrote, matching the C's `r_out` buffer
    retaining its last-written value when `glp_simplex` fails mid-loop.

    **Finding, made writing this port's own test coverage, not assumed**:
    this loop does NOT always converge to the smooth weighted-log-utility
    optimum a real log-utility solve would have. `linprog` returns a
    *vertex* solution (matching GLPK's own simplex) -- when two flows
    share one capacity row at equal (or near-equal) spectral efficiency
    with comparable `weight/(r_prev+EPSILON)` coefficients, the LP puts
    the *entire* contested residual on whichever flow currently has the
    larger coefficient, so successive iterations can toggle which flow
    "wins," and the damped average never settles below `TOL` -- `rel_
    change` sits near `ALPHA` indefinitely rather than shrinking. This is
    a genuine mathematical property of a linear objective over a shared
    polytope, not a bug this port introduced: real hardware's GLPK-backed
    loop has the identical structure and would oscillate the same way
    under the same conditions (two same-direction, equal-SE flows with
    comparable weight). The `MAXITERS=150` cap then simply stops the loop
    mid-oscillation -- fully deterministic given fixed inputs (confirmed:
    repeated calls with identical arguments return byte-identical
    results), but not a "closed-form optimum" any single flow's rate can
    be hand-derived to. What DOES stay closed-form-checkable: the total
    residual pool split between the oscillating flows is conserved
    (`sim/tests/test_smoke.py::test_tier1_pool_conservation_and_gbr_floor_
    on_overload`), and any flow that dominates on weight or is otherwise
    not contested at a shared vertex still converges cleanly. Two-tier's
    own commit 3 (the VQ) is the first place this feeds a real scheduling
    decision -- flagged there as a second source of unexplained `--check`
    movement to consider alongside the VQ port itself, not attributed to
    one or the other by default.
    """
    n = len(flows)
    if n == 0:
        return {}

    se = _spectral_efficiency_per_slot(flows, snr_db_per_ue)
    cap_dl, cap_ul = tier1_capacity_prbslot_per_sec(grid)
    cap_by_dir = {"DL": cap_dl, "UL": cap_ul}

    keys = [(f.ue_id, f.qfi) for f in flows]
    weights = np.array([_weight_from_priority(f.priority_level) for f in flows])
    demand = np.array(
        [max(0.0, demand_bps.get(k, 0.0)) for k in keys]
    )
    gbr_idx = [i for i, f in enumerate(flows) if f.flow_class == "GBR" and f.gfbr_bps > 0]
    gfbr = np.array([float(f.gfbr_bps) for f in flows])

    # Column layout: [r_0..r_{n-1}, s_0..s_{n-1}] -- 2n variables, matching
    # the C's n_cols = 2*n exactly.
    n_cols = 2 * n

    # Bounds: r_i in [0, demand_i] unless demand_i <= EPSILON, in which
    # case r_i is pinned to exactly 0 (ia_p5g_scheduler.c:1004-1014's
    # GLP_FX workaround -- a GLPK bound-validity artifact this port
    # doesn't need, since scipy accepts a degenerate (0, 0) bound
    # directly; the underlying reason, zero demand -> zero rate,
    # deterministically, is what's ported, not the GLPK mechanics).
    r_bounds = [
        (0.0, float(demand[i])) if demand[i] > _EPSILON else (0.0, 0.0)
        for i in range(n)
    ]
    # s_i in [0, inf) for GBR flows, pinned to 0 otherwise -- non-GBR
    # flows have no GBR row, so their slack can never be usefully
    # nonzero; fixing it at 0 matches the C's GLP_FX(0,0) for the same
    # columns.
    s_bounds = [
        (0.0, None) if i in gbr_idx else (0.0, 0.0) for i in range(n)
    ]
    bounds = r_bounds + s_bounds

    # Capacity rows (2, always present) + one GBR row per GBR flow --
    # n_rows = 2 + n_gbr, matching the C exactly.
    dl_idx = [i for i, f in enumerate(flows) if f.direction == "DL"]
    ul_idx = [i for i, f in enumerate(flows) if f.direction == "UL"]

    A_ub = []
    b_ub = []
    cap_row_dl = np.zeros(n_cols)
    for i in dl_idx:
        cap_row_dl[i] = 1.0 / se[i]
    A_ub.append(cap_row_dl)
    b_ub.append(cap_dl)
    cap_row_ul = np.zeros(n_cols)
    for i in ul_idx:
        cap_row_ul[i] = 1.0 / se[i]
    A_ub.append(cap_row_ul)
    b_ub.append(cap_ul)
    for i in gbr_idx:
        row = np.zeros(n_cols)
        row[i] = -1.0        # r_i
        row[n + i] = -1.0    # s_i
        A_ub.append(row)      # -(r_i + s_i) <= -gfbr_i  <=>  r_i+s_i >= gfbr_i
        b_ub.append(-gfbr[i])
    A_ub = np.array(A_ub)
    b_ub = np.array(b_ub)

    r_prev = np.full(n, _EPSILON)
    r_out: dict[tuple[int, int], float] | None = None

    for _it in range(_SCA_MAXITERS):
        coef = weights / (r_prev + _EPSILON)
        # linprog minimizes; ground truth maximizes
        # sum(coef_i*r_i) - GBR_PENALTY*sum(s_i).
        c = np.zeros(n_cols)
        c[:n] = -coef
        c[n:] = _GBR_PENALTY

        result = linprog(c * _OBJ_SCALE, A_ub=A_ub, b_ub=b_ub,
                         bounds=bounds, method="highs")
        if not result.success:
            break

        v = np.maximum(0.0, result.x[:n])
        damped = _SCA_ALPHA * v + (1.0 - _SCA_ALPHA) * r_prev
        rel_change = np.max(np.abs(damped - r_prev) / (r_prev + 1.0)) if n else 0.0
        r_out = {k: float(damped[i]) for i, k in enumerate(keys)}
        r_prev = damped
        if rel_change < _SCA_TOL:
            break

    return r_out if r_out is not None else {}
