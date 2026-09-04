# Tier-1's SCA loop has no fixed point, and where it stops decides the allocation

**2026-09-04. A scheduler finding, not a performance note.**

`../lp-degeneracy-2026-09-04/` measured that 41 of 50 Tier-1 solves hit
`_SCA_MAXITERS = 150` without reaching `_SCA_TOL = 1e-6`, and left the
question open. This answers it in three steps: what the loop is doing, what
an unconverged solve returns, and whether the allocation differs.

## 1. It is not converging slowly — it is not converging

`sca_probe.py --trace`, all 50 solves of one 20,000-slot run at N=8, at the
shipped cap and at a cap of 20,000:

| | cap 150 | cap 20,000 |
|---|---|---|
| solves | 50 | 50 |
| converged | **9** | **9** |
| hit the cap | **41** | **41** |
| iterations when it converges | median 56 | median 56 |
| capped solves whose `rel_change` **minimum is at the end** | **0 of 41** | **0 of 41** |
| median best `rel_change` reached | **0.148** | **0.150** |

**Raising the cap 133× changes nothing** — the same 9 converge, the same 41
do not, and the best `rel_change` they ever reach is ~0.15, five orders of
magnitude above the 1e-6 tolerance. A decaying series has its minimum at the
end; **not one of the 41 does.**

The series says what it is:

```
last five rel_change values, one capped solve:
  0.085069, 0.07839963, 0.085069, 0.07839963, 0.085069
```

A **period-2 limit cycle**, with two distinct LP vertex sums. Others cycle
with longer periods or wander the optimal face. This is the degeneracy
finding one level up: the SCA iteration damps toward a vertex the LP selects
by solver path, and when that selection alternates between equally optimal
vertices the damped average has nothing to settle on.

**So "150 is too few" is the wrong diagnosis. There is no fixed point to
reach on 41 of 50 solves, and the cap is not truncating a convergence — it
is picking a point on a cycle.**

## 2. What an unconverged solve returns, downstream

`sca_probe.py --alloc --cap-b 151` — the sharpest form of the question. One
extra iteration, both stopping points equally arbitrary:

| | |
|---|---|
| flows delivering different bytes | **7 of 32** |
| largest relative change in delivered bytes | 1.00 % |
| **panel metrics that moved** | **11 of 20** |

| metric | cap 150 | cap 151 | |
|---|---|---|---|
| **M01 p98** | 21.855 ms | 24.905 ms | **+13.96 %** |
| **M06 p95 frame age** | 24.128 ms | 26.631 ms | **+10.37 %** |
| **M14 availability** | 0.4898 | 0.42857 | **−12.50 %** |
| M03 / M20 max gap | 115.5 ms | 117.25 ms | +1.52 % |
| M15 jitter | 22.58 ms | 22.307 ms | −1.21 % |

Double-digit movement on three panel metrics, from moving an arbitrary
stopping point by one iteration.

## 3. THE SCALE THAT DECIDES WHETHER IT MATTERS

An absolute number cannot say whether 14 % is large. The scale these
guarantees are built on is the **between-arm** difference, so
`cap_vs_arm.py` puts the two side by side — TwoTier at cap 150 against
TwoTier at cap 151, and against PF and Reservation on the identical
scenario and seed. Medians over 5 paired seeds:

| metric | \|TT150−TT151\| | \|TT150−PF\| | **cap / arm** |
|---|---|---|---|
| M09 worst Jain | 5.0e-05 | 0.25 | **0.02 %** |
| M01 p98 | 5.34 ms | 59.44 ms | **8.98 %** |
| M15 jitter | 7.63 ms | 65.44 ms | 11.66 % |
| M06 p95 frame age | 12.48 ms | 63.90 ms | **19.53 %** |
| **M03 max gap** | **48.75 ms** | **55.75 ms** | **87.44 %** |
| **M14 availability** | **0.0612** | **0.0259** | **236.36 %** |

**Read the last two rows.** On M03 — the liveness gap, which M20 computes
the same way — moving the iteration cap by one reproduces **87 % of the
entire TwoTier-vs-PF difference**. On M14 it reproduces **more than twice**
it.

**And this variance is not in the published intervals.** Every confidence
interval in this project is a bootstrap **over seeds**; this is a
**within-seed** source, invisible to that bootstrap. So the intervals on
M03/M20 and M14 are narrower than the quantity they describe, by a
component nobody has estimated.

### What this does and does not license

**It does not say two-tier is unnecessary, and it does not invalidate a
number.** Within a pinned scipy and a fixed cap the whole thing is
deterministic and reproduces; the corpus proves that.

**It does say a specific subset of comparisons is not resolvable at the
precision claimed.** G1 (M01), G8 (M09) and jitter (M15) have arm
separations 5–5,000× the cap noise and are not threatened. **G3 is.** Phase 2
reports G3's TwoTier M20 delta as **+21.34 % [−2.81, +50.02] INCONCLUSIVE**
— and the instrument carrying that verdict has a within-seed movement of
~87 % of the arm difference from an arbitrary stopping point. The
INCONCLUSIVE verdict stands; what this adds is that it would be premature to
resolve it by adding seeds, because seeds do not average this away.

### Is the deployed C exposed?

**Unknown, and it is a hypothesis, not a measurement** (CLAUDE.md's
third-kind rule). The *degeneracy* is a property of the model — a flat
optimal face exists whatever solves it — and the cap
(`IA_P5G_TIER1_SCA_MAXITERS = 150`), the damping
(`IA_P5G_TIER1_SCA_ALPHA = 0.2`) and the tolerance are all ground truth. So
the mechanism is present in the C. Whether GLPK's pivoting produces the same
cycling is not testable from here, and **must not be assumed either way**:
GLPK's vertex selection is not HiGHS's.

**This is the question to put to the hardware team**, and it is answerable
on their side cheaply: log `rel_change` per SCA iteration and count how many
Tier-1 solves reach `IA_P5G_TIER1_SCA_TOL` before the cap. If the deployed
scheduler also runs to its cap on most solves, this is a property of the
product, not of the port.

## Reproducing

```bash
uv run python sweeps/phase2/sca-convergence-2026-09-04/sca_probe.py --trace
uv run python sweeps/phase2/sca-convergence-2026-09-04/sca_probe.py --alloc --cap-b 151
uv run python sweeps/phase2/sca-convergence-2026-09-04/cap_vs_arm.py 1 2 3 4 5
```

**`sca_probe.py` patches `_SCA_MAXITERS` / `_SCA_ALPHA` for the duration of a
probe and restores them. `scheduler/tier1.py` is unchanged** — this asks
what the scheduler would do, without altering what it does.

### A note on the instrument, kept because it nearly published a wrong shape

The first version of `_instrument` delimited solves by *convergence*, so
every solve that hit the cap was concatenated onto the next. It reported
iteration counts of **498, 5,312 and 720,064 against caps of 150 and
20,000** — and would have reported "the series decays, minimum at the end"
for every one of them, i.e. the **opposite** diagnosis. What caught it is
CLAUDE.md's own check: 720,064 cannot be a count of iterations under a
20,000 cap, so it is not a measurement. The probe now delimits by
`solve_tier1` and **asserts no series exceeds the cap**.
