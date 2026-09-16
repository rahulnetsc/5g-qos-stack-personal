# Does fleet composition change the arm ranking? — REGISTERED BEFORE RUNNING

**2026-09-16.** Written before the probe executes. Prompted by the observation
that **every arm in this evaluation was ranked on a single fleet composition.**

## 1. The gap

`sim/fleet.py` defines four compositions over five UE roles —
`mixed` (20/20/20/…), `ugv_heavy` (55 % ugv), `drone_heavy` (60 % drone),
`sensor_dense` (65 % sensor) — and its own docstring argues composition is a
primary axis: *"'N=16' is not an index in a heterogeneous deployment: 16 fixed
sensors and 16 UGVs differ by an order of magnitude in flow count, GBR
fraction, burst structure, UL/DL split and LCG occupancy."*

**Only `sim/scenarios/g12.py` imports it.** G1/G2/G3/G5/G6/G9 route through
`sweep_scenario`, whose composition is a fixed `mix="factory"`. G11 declines it
explicitly. And G12 itself ran only `mixed:6` and `mixed:4` — so the axis exists,
is wired, and **was never turned**.

## 2. Why G12 and not G5

G5's `build_gt31_scenario` takes no composition parameter, so re-testing the
fleet-24 claim across compositions needs a new axis plumbed into a guarantee
builder — the kind of change that has silently altered test meaning twice today.
**G12 needs zero new code**: `g12_campaign.py` already declares
`CANDIDATE_COMPOSITIONS = ("mixed", "ugv_heavy", "drone_heavy", "sensor_dense")`
and `g12_stress.py` takes `--cells`. Start where the axis is free; plumb it
elsewhere only if it earns that.

## 3. Parameters, and one cell deliberately excluded

7 cells x 2 arms x 10 seeds x 2 tie-break settings = 280 ramp sweeps,
3 080 driver runs. Cap 4 (the deployed value; cap 2 is retired as of today).
Ramp x0.5–x2.0, 11 points, unchanged.

**`sensor_dense:4` is EXCLUDED by construction, not discovered in the output.**
`_allocate(4, sensor_dense)` = `['sensor','sensor','sensor','actuator']` — no
UGV, therefore no 5QI-4 flow, and `assert_cell_is_scoreable` refuses a cell with
fewer than two GBR classes because it cannot produce an ordering. Running it
would emit excluded-by-name cells that read like data.

**`mixed:6` and `mixed:4` are the CONTROL**: they must reproduce the campaign
artefacts for these arms. If they do not, the probe is measuring something other
than composition and nothing else in it is quotable.

## 4. Registered expectations and falsifiers

| # | expectation | falsified by |
|---|---|---|
| 1 | `mixed:6`/`mixed:4` reproduce the existing artefacts for both arms | any disagreement — the probe is then not comparable and is void |
| 2 | clause-4 (safety last standing) holds 10/0/0 on every composition | a VIOLATION appearing — a composition-dependent safety failure, the most consequential outcome available here |
| 3 | the degradation ORDER differs by composition | identical orders everywhere — composition would not reach the thing G12 measures |
| 4 | the two arms' relative standing is unchanged across compositions | the ranking inverting on any composition — which would mean **every arm ranking in this evaluation is conditional on one fleet mix**, and the axis must be plumbed into G5/G10 before any recommendation stands |
| 5 | telemetry M02 at x1.8/x2.0 varies materially by composition | flat — composition would not stress the density budget as argued |

**Expectation 4 is the decisive one.** It is the whole reason for the probe: if
arm ranking is composition-invariant, the single-composition evaluation is
defensible and this closes. If it inverts, the recommendation in
`docs/qos-scheduler-result-2026-09-16.md` is scoped to `mixed` and must say so.

## 5. What this probe CANNOT answer

It tests composition-sensitivity on **G12 only** — degradation ordering under a
load ramp. It says nothing directly about G5's admissible fleet (24 vs 10), which
is the headline capacity claim and whose scenario has no composition axis. A
positive result here is grounds to build that axis, not a substitute for it.

---

## 6. TWO CONFOUNDS FOUND IN THE CONTROL, BEFORE THE PROBE RETURNED

Captured from the existing artefacts while the probe ran. Both weaken
expectations registered in §4, and both are recorded now rather than discovered
in the output.

### 6.1 One arm is already order-unstable on a FIXED composition

Control cells, `mixed:4` and `mixed:6`, both tie-break settings:

| arm | `orders_seen` | `order_agreement` |
|---|---|---|
| `ConfigSched2X7+CG` | `[[4, 2]]` in all four cells | **10/10, 10/10, 10/10, 10/10** |
| `ProtoRRageD2+CG` | `[[], [4], [4,2]]` / `[[2,4],[4,2]]` / `[[], [4], [4,2]]` / `[[4],[4,2]]` | **8/10, 8/10, 7/10, 6/10** |

**`ProtoRRageD2+CG`'s degradation order already varies seed-to-seed with
composition held constant.** So expectation 3 — "the degradation ORDER differs
by composition" — cannot be scored on that arm by comparing `orders_seen` sets
between compositions: a difference there is the arm's own baseline instability,
not the axis. It must be a **paired within-seed** comparison (same seed, same
tie-break, composition the only thing that moves), or it attributes noise to
composition. Same decompose-before-attributing failure this work has already
made three times.

`ConfigSched2X7+CG` has no such confound (10/10 everywhere), so expectation 3 is
scoreable on that arm directly.

### 6.2 Expectation 5 has no dynamic range on the control

Telemetry M02 reads **0.000 at x1.0, x1.4, x1.8 and x2.0, on both arms, in all
four control cells.** Expectation 5 predicted it would "vary materially by
composition" — but on `mixed` it is pinned at the floor, so it can only move
upward. If it stays 0.000 across every composition, that is **not** a
confirmation that composition does not stress the density budget; it is an
expectation that had no room to be contradicted on the control, which is this
project's most-recorded defect shape.

**Expectation 5 is therefore downgraded to a one-sided observation** — a rise is
informative, flatness is not — and it must not be reported as a passed check.

---

## 7. FIRST ATTEMPT CRASHED — `sensor_dense` is unusable, and my viability check was wrong

The probe died after 90 of 280 sweeps with
`ValueError: min() iterable argument is empty`, raised at
`g12_campaign.py:236` — `min()` over the flows of a GBR class that has **no
flows**.

**The cause is the vacuity §3 tried to design out, one cell further along than I
guarded.** `GBR_CLASSES` is `(2, 4)` and the ramp needs both to produce an
ordering. Census:

| cell | GBR census | verdict |
|---|---|---|
| `mixed:4`, `mixed:6` | `{4:1, 2:3}` | scoreable |
| `ugv_heavy:4`, `ugv_heavy:6` | `{4:2, 2:3}` / `{4:2, 2:5}` | scoreable |
| `drone_heavy:4`, `drone_heavy:6` | `{4:1, 2:3}` / `{4:1, 2:5}` | scoreable |
| `sensor_dense:4` | `{}` | vacuous |
| **`sensor_dense:6`** | `{2:1}`, **missing 5QI-4** | **vacuous — this raised** |

**§3's viability check was wrong, and the error is instructive.** It confirmed
`sensor_dense:6` *gains a camera* relative to N=4 and concluded it was
scoreable. It never checked the thing that actually matters: whether the cell
still has **no UGV**, hence no 5QI-4. At a 3 % UGV share `sensor_dense` does not
acquire one at N=8 either, so **it is unusable for G12's ordering test at any
practical fleet size** — not merely at N=4.

**Corrected cell set: 6 cells** — `mixed`, `ugv_heavy`, `drone_heavy` at N=4 and
N=6. 6 x 2 arms x 10 seeds x 2 tie-break = 240 ramp sweeps, 2 640 driver runs.

**The 90 completed sweeps are DISCARDED, not salvaged**, under the standing
fresh-runs rule: they are a self-selected subset (whatever happened to schedule
before the crash) and re-entering them would publish a result over a population
nobody chose.

**Consequence for the probe's reach.** `sensor_dense` was the composition
furthest from `mixed` — the one most likely to stress a per-flow density budget,
since it is many small periodic flows and almost no video. Losing it means the
probe now spans a narrower range (`ugv_heavy` and `drone_heavy` both still carry
UGVs, drones and a camera), so **a null result is weaker evidence than §4
assumed**: it would say composition does not matter *across the compositions
G12 can actually score*, not across the deployment's plausible range.

## 8. A LATENT GUARD GAP, recorded separately

`sim/scenarios/g12.py:365` defines `assert_cell_is_scoreable` precisely for this
— its docstring names the `sensor_dense` case and says such a cell "must be
EXCLUDED by name, not scored to a one-element order that reads like a result".

**The guard exists and IS called — but only on the path that did not crash.**
`g12_campaign.py:126` calls it while selecting candidate cells. `g12_stress.py`
builds its task list directly from `--cells` and never calls it, so `run_ramp`
reaches the `min()` at `g12_campaign.py:236` unguarded. A vacuous cell therefore
raises inside a worker and kills the entire pool, instead of being excluded by
name at task-build time.

**This is the fix-at-one-site pattern this repo has recorded repeatedly**: a
guard written for one entry point, with a second entry point added later that
bypasses it. The same shape as the three private arm registries found this
morning, and as the `bootstrap_ci` ordering note in `g9_stress`'s own source.

**The fix is one line in `g12_stress.py`** — call `assert_cell_is_scoreable`
when building the task list and drop the cell by name with a reason. Not bundled
into this probe: it is a runner change, it would land mid-run, and the probe's
own correctness does not depend on it now that the vacuous cells are excluded by
hand. Registered as owed.
