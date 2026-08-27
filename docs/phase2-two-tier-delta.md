# Two-tier Phase 2: old-vs-new delta

This document has two sections, landed at different points in the
two-tier rewrite (`docs/phase2-plan.md`'s commit checklist):

1. **Pre-removal variant-arm comparison** (below) — captured in commit 1,
   *before* `scripts/regression_corpus.py::_cases()` drops the
   `TwoTier-nomaxmin`/`TwoTier-adaptive` arms. Those two arms cannot be
   constructed once `gbr_maxmin`/`gbr_penalty_lr` are deleted constructor
   kwargs (neither is grounded in `docs/phase2-plan.md` §2.1's Tier-1
   ground truth — see `README.md` §7), so this is the last point their
   effect is checkable against a live run rather than only against git
   history and `design-docs/scheduler-study.md`'s prose.
2. **Old-vs-new TwoTier delta** (commit 8) — the full per-record
   comparison of the pre-Phase-2 `two_tier.py` (tagged
   `phase2-pre-twotier-rewrite`, `dc1ab6a`) against the rewritten one,
   run side-by-side on the same seeds/scenarios. Prerequisite to commit
   9's re-capture. Not yet written.

## 1. Pre-removal variant-arm comparison (commit 1)

Source: `regression/baseline_studies_1_3.json`, Study 1
(`factory_robots_scenario`, `ue10_qfi2` — the GBR flow the max-min stage
exists to protect), before commit 1's edits. All three variants share
`cqi_delay_slots=8` and are otherwise identical except
`gbr_maxmin`/`gbr_penalty_lr`.

| capacity mult | variant | delivery_ratio | throughput_bps |
|---:|---|---:|---:|
| 1.0 | TwoTier | 0.0785 | 581,072 |
| 1.0 | TwoTier-nomaxmin | 0.0966 | 714,648 |
| 1.0 | TwoTier-adaptive | 0.0966 | 714,648 |
| 1.5 | TwoTier | 0.0848 | 627,424 |
| 1.5 | TwoTier-nomaxmin | 0.0660 | 488,384 |
| 1.5 | TwoTier-adaptive | 0.0660 | 488,384 |
| 2.0 | TwoTier | 0.8105 | 5,997,440 |
| 2.0 | TwoTier-nomaxmin | 0.8105 | 5,997,440 |
| 2.0 | TwoTier-adaptive | 0.8105 | 5,997,440 |
| 3.0 | TwoTier | 0.8206 | 6,072,760 |
| 3.0 | TwoTier-nomaxmin | 0.8205 | 6,071,752 |
| 3.0 | TwoTier-adaptive | 0.8205 | 6,071,752 |

Observations, stated as what the numbers show, not interpreted further
than that:

- **`TwoTier-adaptive` is byte-identical to `TwoTier-nomaxmin` at every
  mult.** The adaptive dual-ascent penalty (`gbr_penalty_lr=1e5`) made no
  measurable difference beyond turning `gbr_maxmin` off — consistent
  with `design-docs/scheduler-study.md` §8.4's own "negative result"
  verdict on the mechanism (`:1297`), captured here as a live data point
  rather than only as prior prose.
- **The max-min stage's effect is not one-directional in this table.**
  At 1.0×, `TwoTier` (maxmin on) delivers *worse* than the two maxmin-off
  variants for this specific flow (0.0785 vs 0.0966). At 1.5×, the
  opposite: `TwoTier` delivers *better* (0.0848 vs 0.0660). At 2.0×/3.0×
  the three are within noise of each other — consistent with the
  mechanism's own designed self-disabling property once the GBR set
  becomes jointly feasible.
- This is one flow's numbers from one scenario, kept here as a record of
  what these arms measured before they left the corpus — not a
  restatement of `design-docs/scheduler-study.md`'s own fuller study,
  which remains the authoritative source for the max-min/adaptive-penalty
  finding.

## 2. Old-vs-new TwoTier delta (commit 8)

Not yet written — lands with commit 8, comparing
`phase2-pre-twotier-rewrite` (`dc1ab6a`) against the rewritten scheduler
on the same seeds/scenarios. Its own framing must note that this
comparison is partly a comparison *against* non-ground-truth mechanisms:
the old scheduler's default `TwoTier` arm ran with `gbr_maxmin=True` by
default, itself one of the mechanisms §1 above and `README.md` §7 flag as
absent from `docs/phase2-plan.md` §2.1's Tier-1 ground truth — so a
"faithful new port vs. old Python" framing is not accurate on every row;
some of the delta is old-Python-exceeds-hardware vs. new-Python-matches-
hardware, not old-approximation vs. new-precision.
