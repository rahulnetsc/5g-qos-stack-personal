# Systematic optimisation pass — G9's grid as the reference

**2026-09-08.** Reference workload: `scripts/g9_stress.py`'s grid — 1 080
rows = **2 160 driver runs**, the artefact committed at `548c0b0`.

**The constraint that splits the work:** every comparison in this project is
within-seed, so the RNG streams and the slot loop's draw ordering are
untouchable. **Category A cannot change a number and bit-identity is the
whole acceptance test. Category B changes what is computed and needs a
different test.**

---

## 1. The profile was re-taken, and the old shares no longer hold

M-9, M-6, RA, SRB and the control-plane floors have all landed since the
last profile. **Every previously-named candidate is now below threshold**:

| old candidate | old share | now |
|---|---|---|
| `_bucket_by_second` | 11.1 % of a record | **not in the top 38** |
| the scoring path | 20-40 % of a record | **not in the top 38** |
| `dataclasses.asdict` persistence | 0.20 s/record | **not in the top 38** |
| `hol_delay_samples_s` as a list | ~12 % of residual | **not in the top 38** |

The workload is now dominated by the **slot loop**, and specifically by the
buffer-view chain. Fresh profile, one representative task (TwoTier, cold
attach, 6 UEs ×1.25 — the arm and point where the scheduler does most
work), 44.0 s under `cProfile`, **16.43 s uninstrumented**:

| site | cumulative | note |
|---|---|---|
| `two_tier._allocate_direction` | 25.2 s (57 %) | |
| `join.state` → `harq.state` → `harq.is_pending` | 18.2 s (41 %) | 5.86 M calls |
| `harq.is_pending`'s generator | **94.3 M iterations** | the single largest line |
| `buffer._resolve` | 5.5 s | 17.8 M calls |
| `metrics.snapshot_slot` | 5.1 s | 40 k calls |

**Threshold taken: every site ≥ 2 % of profiled time for which an
identity-preserving change exists.** Below that the change is not worth the
risk of touching the slot loop.

## 2. Category A — five changes, all bit-identical

| # | change | what it was | gain |
|---|---|---|---|
| **A1** | `HarqProcessPool.is_pending` → O(1) counters | `any(p.busy ...)` over up to 16 slots, 5.9 M calls = **94.3 M generator steps** | **16.43 → 13.82 s** |
| **A3** | per-`(ue, direction)` flow index in `TwoTier`, built once in `configure()` | **ten** hot loops each scanning all 15 flows, per UE per direction per slot | (in the above) |
| **A2** | `BufferModel._resolve` fast path for unambiguous keys | two dict lookups + a length check, 17.8 M calls | 13.82 → 13.56 s |
| **A4** | `snapshot_slot`'s eager `setdefault`; cached `buffers.keys()` | `setdefault` built a dict of five empty lists **per flow per slot** and threw it away — ~3 M wasted allocations per run | 13.56 → 13.20 s |
| **A5** | memoise the buffer view **within one slot** | `state()` walked JoinAware → HarqAware → BufferModel 5.86 M times | 13.20 → **12.27 s** |

**One task: 16.43 s → 12.27 s, a 25.3 % reduction.**

**Three of these needed a correctness argument, not just a rewrite:**

- **A1 must still call `self._pool(ue, dir)`** even though it no longer
  reads the pool. That call lazily *creates* the `(ue, direction)` entry,
  and `_pools` insertion order is what `due_this_slot()` iterates, which
  orders the HARQ RNG draws (CLAUDE.md's cross-direction invariant).
  Dropping it would have reordered draws and changed results — a silent
  divergence that no test of `is_pending` itself would have caught.
  Equivalence proved separately over **200 000 random allocate/free/flush
  mutations**, asserting the counters answer exactly what the scan did.
- **A3 preserves declaration order.** Declaration order is attach order
  here, and several QoS lookups are first-flow-found-wins, so the index is
  built by appending in `self._flows` order — the filtered sequence is
  identical to what the scan produced.
- **A5 is opt-in and defaults OFF.** Caching `state()` within a slot is
  valid only because no scheduler mutates buffers during `allocate()` —
  verified, not assumed: `scheduler/*.py` and `sim/baselines/*.py` contain
  no `buffers.drain/expire/enqueue` call at all, and two-tier's
  `_ul_drain`/`_dl_drain` move its *own* virtual queues. `sim/driver.py`
  builds the view fresh per slot and is the only caller that passes
  `cache_within_slot=True`; every other construction keeps the uncached
  path rather than inheriting an invariant it may not satisfy.

## 3. Category B — measured, and declined on the measurement

The exact greedy for `tier1.py` was the only Category B item on the table.
**Two fresh measurements say not to take it, and the second is the one that
matters.**

**The speed case is ~2.4 %.** On the reference workload the entire LP path —
`solve_tier1`, `scipy.optimize.linprog` and every scipy internal it reaches
— is **0.719 s of 28.0 s, 2.6 %**. A 15.6× speedup on the solver call
therefore buys ~2.4 % overall, below the 2 %-per-site threshold once the
risk is priced in. CLAUDE.md already deferred both LP follow-ups and said
**re-opening needs a new measurement**; this is a new measurement, and it
confirms the deferral rather than overturning it.

**The correctness case is already closed, and this is the finding.** The
question worth answering was not "is the greedy faster" but *"does any
published number rest on a suboptimal solve?"* — and that can be answered
**without swapping the solver**. CLAUDE.md established that the LP is badly
*scaled*, not degenerate, and that K=1e3 and K=1e6 sit on a conditioning
plateau. So: capture every LP the reference task issues and re-solve each at
100× the shipped scale.

**5 639 solves captured. Objective differs on ZERO of them** — worst
relative gap **1.155e-16**, machine epsilon. **The argmax `x` differs on 25
(0.44 %)**, and since the objective is identical those are **ties: alternate
vertices on the same optimal face, both optimal.**

**So no verdict rests on a suboptimal solve, because there are no
suboptimal solves.** The 0.44 % that move under rescaling are exactly the
non-unique optima the registration predicted, and at a tie there is no
better answer to find. Swapping in the greedy would still need a declared
tie-break for those 25 — with no Tier-1 ground truth in this repo to
adjudicate it — in exchange for 2.4 %.

**Declined, with the numbers.** Re-opening needs a workload where the LP is
a materially larger share, not a re-reading of this one.

## 4. On what was optimised, and why

Two-tier is just another scheduler here. It was profiled because it is the
arm that does the most work per slot, so it bounds the grid's wall clock —
not because its numbers deserve improving. Every change in §2 is
scheduler-agnostic except A3, and A3 is a lookup index, not a policy: PF and
Reservation gain from A1, A2, A4 and A5 identically. Nothing in this pass
changes any arm's behaviour, which is what "bit-identical" means.
