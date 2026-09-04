# Tier-1's LP has multiple optima, and its SCA loop does not converge

**2026-09-04. This is a NEGATIVE result for an optimisation and a finding
about the scheduler, and the second is much the more important of the two.**

Found while trying to take `scipy.optimize.linprog`'s per-call wrapper off
the Tier-1 hot path — measured at **43.5 % of a TwoTier driver run**
(`../profile-2026-09-04/`). The swap was gated on bit-identity over the
paired-seed regression corpus. **It failed the gate, and the reason is not
the swap.**

## The measurement

`lp_probe.py --degen --sca`, output verbatim in `result.json`. One real run
(`sweep_scenario` N=8, `factory` mix, seed 1, `cqi_delay_slots=8`); every
Tier-1 LP solved twice — once by `scipy.optimize.linprog(method="highs")`,
once by a HiGHS model built directly with scipy's own options. **scipy's
answer is the one returned to the caller, so the run is unperturbed and the
comparison is a pure observation.**

| | |
|---|---|
| LP solves observed | **2,437** |
| solves where the two paths return a DIFFERENT `x` | **1,781 (73 %)** |
| median max abs difference in `x` | **3,290,041** |
| largest | **8,660,788** |
| **relative objective gap, max** | **9.5e-11** |
| relative objective gap above 1e-9 | **0** |
| both solutions feasible in the model | **2,437 of 2,437** |
| status disagreements (optimal vs not) | **0** |

**Read those two rows together.** The objective values agree to eleven
digits and both points satisfy every constraint. The paths are not
disagreeing about the optimum — **they are returning different vertices of
the same optimal face.** The LP is degenerate, and which vertex comes back
is a property of the solver's path, not of the model.

Checked and eliminated as explanations: `presolve` ∈ {on, choose, off}
(divergence present at all three), `simplex_strategy` (scipy's own value,
transcribed), and infeasibility or a status difference (zero of each).

## Why the optimisation cannot land

Tier-1's SCA loop damps `r_prev` toward the returned `x`, so a different
vertex changes the NEXT iteration's objective, and the loop diverges from
there. Both variants were run against `regression_corpus.py --check`:

| | corpus |
|---|---|
| warm HiGHS (reuse the model, change only `c`) | **drifts** |
| cold HiGHS (rebuild the model each call) | **drifts** |

Sample of the cold drift: `study3/latency_bound/TwoTier` `ue9_qfi9`
`throughput_bps` 5,521,232 → 5,340,428, `message_count` 1,020 → 984.

**These are not rounding.** A pure speedup that moves real numbers is not a
speedup, and `CLAUDE.md` is explicit that re-baselining to make a diff go
away is not available. **So the change was reverted rather than landed**,
and `scheduler/tier1.py` is untouched. The 41× per-call figure in
`../profile-2026-09-04/` remains true and remains unusable at this bar.

## The finding that outlives it

**Tier-1's targets are not uniquely determined by Tier-1's own LP.** On 73 %
of solves the model admits at least one other equally optimal answer, and
the one this project gets is whichever vertex HiGHS reaches through scipy's
particular calling sequence. Within a pinned scipy this is deterministic and
the corpus reproduces — **the corpus is pinning a solver path as tightly as
it is pinning the scheduler.** A scipy upgrade is a scheduler change here,
and nothing in the repo currently says so.

**And the loop is not converging.** Same run, `--sca`:

| | |
|---|---|
| Tier-1 solves | 50 |
| `_SCA_MAXITERS` / `_SCA_TOL` | 150 / 1e-6 |
| iterations: min / median / mean | 56 / **150** / 133.1 |
| **reached the tolerance before the cap** | **9 of 50** |
| **hit the cap** | **41 of 50** |
| total LP solves | 6,656 |

So on **82 % of solves** Tier-1's output is not a converged fixed point of
the SCA iteration — it is wherever the damped sequence stood at iteration
150, over a sequence of 150 degenerate LPs each of which could have answered
differently. The cap itself is faithful to ground truth
(`IA_P5G_TIER1_SCA_MAXITERS = 150`), so this is not a porting error; **what
is unknown is whether the deployed C, on GLPK, converges where this does
not** — a different simplex makes different vertex choices, and GLPK's
selection is not HiGHS's.

## What would unblock the optimisation

Not more option matching — that was tried. The LP would have to select a
vertex by a rule of its own rather than inheriting the solver's, e.g. a
lexicographic tie-break or a tiny secondary objective. **That is a
behaviour change to the scheduler, not a speedup**, it would move the
corpus deliberately, and it needs its own decision against ground truth —
including whether the deployed C's GLPK path has the same freedom. Filed,
not taken.

## Reproducing

```bash
uv run python sweeps/phase2/lp-degeneracy-2026-09-04/lp_probe.py --degen --sca
uv run python sweeps/phase2/lp-degeneracy-2026-09-04/lp_probe.py --diff --presolve choose
```

`lp_probe.py` is self-contained and imports no module that this pass
deleted. It needs `highspy`, which is present as a transitive dependency of
cvxpy under that package's `python_full_version >= '3.11'` marker; on 3.10
the `--diff`/`--degen` modes will not import and `--sca` still works.
