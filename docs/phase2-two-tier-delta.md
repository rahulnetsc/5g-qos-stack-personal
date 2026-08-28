# Two-tier Phase 2: old-vs-new delta

> **PRE-FIX NUMBERS — read this first (added by WP9's SR-trigger fix).**
> Every figure in this document was produced before the `sim/ul_access.py`
> SR-trigger defect was found and fixed (`README.md` §8's `[RESOLVED]`
> entry, `docs/oai-port-map.md` row 79, `docs/wp9-plan.md` §8b/§8c). That
> fix moved 15 of the corpus's 20 records. **This is not a blanket
> disclaimer** — the record split says precisely what is and is not still
> known, and the load-bearing part survives:
>
> - **§2's `study3` near-parity control row (0.4665 vs 0.4481) SURVIVES,
>   for a checkable reason**: `latency_bound_scenario` carries no UL
>   traffic at all, so the fix moves **none** of its four records
>   (confirmed: 0 mismatches). The control is the anchor of this table's
>   whole argument — that the gaps track where the old arm's privileges
>   applied, read as an *ordering* rather than as individual numbers — and
>   that anchor is intact.
> - **§2's `study2` row (0.9999 vs 0.3924) is UNVERIFIED.** It sits on the
>   records the fix moves hardest (`study2/pdcch_limited/TwoTier` UE9 UL
>   `delivery_ratio` 0.0486 → 0.9994). Both arms ran under the defect, so
>   the gap may be unaffected or may have been partly this — **not assumed
>   either way**, and not resolvable by reasoning. Settling it needs the
>   old arm re-run via `docs/oai-port-map.md` row 77's overlay procedure,
>   which was out of scope for the fix commit.
> - **§2's `study1` rows are pre-fix**, on records that moved.
> - §1's variant-arm comparison is a historical snapshot of arms that no
>   longer exist and is unaffected by this in the sense that it cannot be
>   re-run either way.
>
> The numbers below are left exactly as captured. Nothing here has been
> restated post-fix, so no row should be compared against a post-fix figure
> without re-running both arms.


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
2. **Old-vs-new TwoTier delta** (commit 8, landed) — the per-record
   comparison of the pre-Phase-2 `two_tier.py` (tagged
   `phase2-pre-twotier-rewrite`, `dc1ab6a`) against the rewritten one,
   run side-by-side on the same seeds/scenarios. Prerequisite to commit
   9's re-capture.

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

**This is not a faithful-port-vs-faithful-port comparison, and the
table below should be read with that stated first, not as a footnote.**
The old scheduler's default `TwoTier` arm ran `gbr_maxmin=True`,
`enable_sps=True`, `demand_estimator="oracle"` (perfect knowledge of
each flow's *future* offered rate — not an unfaithful estimate, one no
real scheduler could ever produce), and `tier1_period_slots=2000`
(1.0s, against the deployed macro's real 0.1s, `CLAUDE.md`'s own
stale-default invariant). None of `gbr_maxmin`/the adaptive dual-ascent
penalty/network slicing/the hard-floor override/the lexicographic
two-phase structure (`gbr_contract_bps` is the concrete function
implementing the max-min stage's own per-flow floor, §1's own subject)
have any citation in `ia_p5g_scheduler.c` (`docs/oai-port-map.md` rows
39-40, five ungrounded mechanisms, permanent loss). Where the table
below shows the old arm ahead, the first question is whether that
margin is real scheduling-policy fidelity or one of these five
privileges plus the oracle — not "the rewrite regressed."

**The three regression-corpus scenarios form a gradient in exactly how
many of those privileges apply, and the ordering is the evidence — more
convincing than any single number on its own.** Captured this commit,
`phase2-pre-twotier-rewrite` (`dc1ab6a`)'s own `scheduler/` package
(both `two_tier.py` and its matched-pair `tier1.py`, row 77's exact
procedure) run against CURRENT `sim/`, alongside current HEAD's own
capture:

| scenario | privileges in play | old delivery ratio | new delivery ratio |
|---|---|---:|---:|
| study3/latency_bound (DL-only) | none — no SPS (UL-only), max-min/oracle margin doesn't bind on this DL-only, non-GBR-overload shape | 0.4481 | 0.4665 |
| study1/overload_mult1.0-1.5 | oracle + max-min, moderate load | 0.4493 / 0.5839 | 0.4813 / 0.5887 |
| study1/overload_mult2.0-3.0 | oracle + max-min, GBR overload (max-min's own binding regime) | 0.8526 / 0.8862 | 0.6023 / 0.6134 |
| study2/pdcch_limited (sensor_dense) | + SPS, this scenario's own namesake constraint | 0.9999 | 0.3924 |

**study3 (DL-only, no SPS relevance, no GBR-overload for max-min to
bind on) is the closest thing this project has to a controlled
comparison — new arm is very slightly AHEAD (0.4665 vs 0.4481) with
none of the old arm's privileges able to explain a gap either
direction.** This is what licenses reading the other three rows as
privilege-attributable rather than as a broken rewrite: the gap grows
exactly as more of the old arm's ungrounded advantages come into play,
not uniformly. study1's low-mult rows (moderate load, max-min mostly
non-binding per §1's own finding that the stage self-disables once the
GBR set is jointly feasible) show a small, new-arm-favoring gap similar
to study3's control. study1's high-mult rows (max-min's own designed
binding regime, GBR overload) flip to a large old-arm-favoring gap.
study2 — SPS's own namesake scenario (`sensor_dense_scenario`, PDCCH-
limited by construction; SPS's entire purpose is bypassing per-slot
DCI/CCE contention for periodic flows) — shows the single largest gap
in the whole table, specifically where the old arm's own strongest,
most directly-applicable privilege applies.

**Attribution to the new arm's own lineage where plausible, not an
undifferentiated diff.** Five commits are confirmed to have moved
`--check`-tracked metrics across commits 1-7: **1** (SPS/old-Tier-1
removal, the UL/DL ordering fix, the corrected blanket-decay EWMA — 4
confounded causes, not separable from aggregate `--check` alone), **3**
(DL's real sort tiers; UL moved too, but via `HarqProcessPool`'s shared
iteration order, not `_ul_rank_key` itself), **3a** (the VQ port, the
largest single movement in this whole lineage), **4b** (`B_eff`, the
GFBR and frozen-BSR mechanisms), **5** (UL-only, `factory_robots`'s
UEs 8/9/10 specifically, the served-split/deficit-drain fix). study1's
own UL PRB utilization is consistent with commit 5's confirmed
UEs-8/9/10 effect layering onto the oracle/SPS/max-min gap above,
though fully decomposing a delta across 5+ confounded factors (each of
the five commits above, plus the four old-arm privileges) would need
dedicated mechanism-isolated re-runs per row — not this commit's own
job, stated as a scoping boundary rather than a decomposition not
actually done.

**An open question, not an explained one, found producing this
table**: new arm's own UL PRB utilization FALLS as offered load rises
through `study1`'s mult2.0→3.0 (0.617 → 0.432) — counterintuitive, more
load should mean more PRBs used, not fewer. Old arm's own UL
utilization does not show this (0.858 → 0.601, still falling but from
a much higher base and a different shape entirely — old's own trough is
at mult1.5, 0.798, rising again after). Plausibly related to commit 5's
own UE-8/9/10 mechanism, but not decomposed here (see the attribution
paragraph above) — named as a standing question, not absorbed into that
paragraph's attribution, since it is exactly the kind of pattern that
turns out to be either a real property of the ported scheduler under
overload or a bug nobody has looked for yet, and WP9 runs precisely
this regime. `README.md` §8 carries the full four-data-point entry.

**The 8 `-nomaxmin`/`-adaptive` variant-arm records are still
constructible from the old package** (its own `scripts/regression_
corpus.py`/`scripts/scheduler_study.py` need overlaying alongside
`scheduler/` — row 77's procedure covers `scheduler/` only, extended
here) — **freshly captured against current `sim/` this commit, and
numerically IDENTICAL to §1's own already-captured table**, cross-
checked directly, not assumed: `ue10_qfi2`'s `delivery_ratio`/
`throughput_bps` match at every mult (e.g. mult1.0: `0.0785`/`581072`
both times). §1's own table is confirmed still valid, unaffected by
`sim/`'s own drift since `dc1ab6a` — cite it directly for what removing
max-min/the adaptive penalty cost or saved; not re-derived here.

**A second, distinct instance of the oracle-vs-real framing, added at
commit 2**: the old scheduler's `demand_estimator` defaulted to
`"oracle"` — every pre-Phase-2 `TwoTier` record ran Tier-1 with perfect
knowledge of each flow's *future* offered rate (`README.md` §7). A
second, independent reason not to default to "the rewrite introduced a
regression" when the new arm performs differently, before checking
whether the old arm's number was ever achievable on real hardware.

**A third caveat for this table's own methodology, added at commit 2**:
`scheduler/tier1.py::solve_tier1` has a confirmed, non-porting-defect
property — its SCA loop does not always converge to a smooth interior
optimum for two same-direction, near-equal-SE flows with comparable
weighted coefficients (`docs/oai-port-map.md` row 39). A seed-to-seed
or scenario-to-scenario old-vs-new delta on such a flow pair may show
what looks like noise or instability that is actually this
deterministic-but-non-smooth oscillation, not a comparison artifact or
a bug in either arm.

**Five dormancy categories plus two shared unswept config parameters
in the NEW arm, stated so the comparison above is not read as a
full-capability contest in either direction**: (1) signal structurally
absent (`has_srb`/`do_sched`/TA/PHR since WP1); (2) signal exists but no
scenario constructs the situation (e.g. `mfbr_bps` never configured
anywhere); (3) not applicable (e.g. DL fill order, the SRB LCP pass);
(4) the UL floor's own BSR/SR-desync-fault dormancy, no scenario
constructs the fault; (5) PHR, sim-only and confirmed inert on real
hardware. Plus two shared, unswept parameters (`min_grant_prb`,
`mfbr_bps`) pinned at values that keep real, already-ported mechanisms
inactive in BOTH schedulers. None of these explain the deltas above —
both old and new arms are compared as actually run — but a reader
should not additionally read the new arm's own dormant capability as a
further deficiency on top of the four privileges already named.
