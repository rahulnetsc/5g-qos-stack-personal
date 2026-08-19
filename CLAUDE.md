# 5g-qos-stack — working notes for Claude

Read `README.md` first; it is the branch charter and is authoritative wherever
it conflicts with `docs/p5g-sim-plan.md`. This file is only the things that
get re-explained every session.

## Commands

```bash
uv sync                                          # set up env (first time)
uv run pytest sim/tests -q                       # full suite (~45s, must stay green)
uv run pytest sim/tests/test_scorecard.py -q     # one file
uv run python scripts/regression_corpus.py --check   # numeric drift vs snapshot
uv run python scripts/regression_corpus.py --capture # re-baseline (see rules below)
uv run python scripts/scheduler_study.py         # the published studies 1-3
```

Everything runs under `uv run`. There is no `pip install -e .` step and no
bare `python` invocation that works.

## Project layout

- `sim/` — simulator: `driver.py` (slot loop), `channel.py`, `buffer.py`,
  `traffic.py`, `resource.py`, `ue_lcp.py`, `metrics.py`.
- `sim/power.py` — WP1. Tx power headroom (`ph_factor`, `shrink_to_power_budget`).
  Dormant: not imported by `driver.py` or any scheduler. PHR is inert on
  hardware (README §4).
- `sim/run_record.py`, `sim/scorecard.py` — WP0. The scoring layer.
  `scorecard.py` must not import `sim/driver.py` or `sim/config.py`; it
  consumes `RunRecord` only, so it can score records from any producer.
- `config/metric_panel.yml` — the pre-registered metric panel. See rules below.
- `scheduler/` — `two_tier.py`, `tier1.py`, `link.py`, `flow.py`.
- `sim/baselines/` — PF, RoundRobin, Gradient. The Phase 1 comparison arms.
- `oai-branches/{two-tier,reservation}/` — read-only verified OAI C source.
  Ground truth for Phase 2. Same filenames in both dirs with *different*
  contents; never merge or dedupe them.
- `regression/baseline_studies_1_3.json` — 22-record numeric snapshot.
- `docs/` — planning docs. `p5g-sim-plan.md` §9 has the per-WP technical spec.

## Non-obvious invariants

These are the ones where the "helpful" fix is the wrong one.

**Reproduce measured behavior, not documented intent.** Where the OAI C
source's comment disagrees with its code, the *code* is what shipped and
what produced the hardware numbers. Known case: reservation's post-grant
deficit drain comments "distribute tb_size drain proportionally across
active LCGs" and then credits the full `tb_size` to every active LCG
independently. Port the full-credit behavior. Do not make it proportional.
If you find another comment/code mismatch, flag it and ask — do not
reconcile it silently in either direction.

**Do not add SPS / Configured Grant to the schedulers.** `main`'s
`scheduler/two_tier.py` has it (`_SPSReservation`, `_allocate_sps`); the real
hardware scheduler defers SPS to a Phase 2 that was never built. The Python
model must match the deployed scheduler, not exceed it.

**The gNB cannot see a UE's intra-TB per-flow split.** Only aggregate
per-LCG BSR. `main` has `_shadow_lcp_split` / `_occupancy_split` /
`_mac_lcp_fill` doing this anyway; it is a known modeling error, not a
pattern to extend. When adding any mechanism, ask which network element
would actually learn this and how.

**Tier-1 period is 0.1 s, not the 1.0 s in `ia_p5g_scheduler.h`'s doc
comment.** The `.c` file hoists the macro; the gNB startup banner confirms
100 ms is what ran.

**`min_rb` is a static gNB config constant (`nrmac->min_grant_prb`), not
derived from SNR or payload.** Don't compute it from channel quality —
that's a different, sim-only quantity (`scheduler/link.py::snr_to_prb_floor`,
WP1). See README §7 for the full distinction; WP2's reservation follower
budget needs the real one.

**When porting an OAI C function, check every call site before collapsing
or defaulting a parameter.** WP1 almost shipped `compute_ph_factor`'s
`include_bw` as always-`true` after checking 3 of its 6 call sites; the
other 3 (`phr_txpower_calc`) pass `false`. Also mirror `AssertFatal`
preconditions as raises rather than dropping them (silently wrong beats
loudly wrong), and mirror `roundf()` (half-away-from-zero) explicitly
instead of Python's `round()` (half-to-even) — they disagree at exact
`.5`. `sim/power.py` is the worked example for all three.

**One fidelity change per commit.** Land it, run the full suite, run
`regression_corpus.py --check`, and record which numbers moved and why.
Bundling two changes makes the deltas uninterpretable, which is the whole
point of the corpus.

## Rules for the WP0 machinery

**`config/metric_panel.yml` is pre-registered.** Adding a metric is fine.
Removing one, or changing a definition to something that happens to separate
two schedulers better, defeats the multiplicity guard. Every metric keeps a
`status` of `ok` / `proxy` / `pending` and a `requires` naming the WP that
promotes it — a WP that claimed to unlock a metric but left its status
unchanged is a finding, not a detail.

**A `pending` metric emits a row with `value=None` and a reason.** Never
omit it. An omitted row is indistinguishable from a forgotten one.

**Do not `--capture` a new regression baseline to make a diff go away.**
Re-baseline only when a change is *intended* to move the numbers, and say so
in the commit message. `--check` failing is information.

## Known issues (flagged deliberately, do not fix as a drive-by)

- `sim/metrics.py::record_hol_delay` drops zero-delay samples, biasing every
  latency percentile pessimistic at low load. Left as-is so the regression
  baseline matches the published numbers. Fixing it is its own commit with
  its own regression diff.
- `average_agg_level` is hardcoded to 4 in the OAI DL scheduler
  (`// TODO find a better estimation`). Decide deliberately whether the sim
  models it fixed or SNR-dependent.

## Style

- Comments explain *why*, especially why something deviates from the obvious.
  A comment saying what the line does is noise.
- Docstrings on new modules state what the module is for and what it must not
  depend on.
- No new runtime dependencies. Current set: numpy, cvxpy, matplotlib, pyyaml,
  scipy (+ solvers). Stdlib `csv`/`json` over pandas.
- Type hints on new public functions.
