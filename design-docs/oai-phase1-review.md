# Review: OAI Phase-1 two-tier scheduler vs. the reference design

Reviewed 2026-08-07: `~/Projects/Oai_Ran_QoS_Supported_MultiDRB` at `7358e99`,
`openair2/LAYER2/NR_MAC_gNB/ia_p5g_scheduler.{c,h}` (2599 lines) plus its
integration points in `gNB_scheduler_dlsch.c` / `gNB_scheduler_ulsch.c`.
This is the pre-max-min version. Compared against `scheduler/` in this repo
and against [scheduler-design.md](scheduler-design.md).

**Overall: the port is faithful in structure and mostly faithful in
mechanism.** The virtual-queue mathematics, the Tier-1 constraint set, the
LCP fill rule and the thread/atomic-snapshot split all match the design.
What has drifted is *where the metric sits in the decision*, and some
capacity and conditioning details. One issue (§B1) substantially defeats
the purpose of Tier-1 and should be fixed before any further measurement.

**Updated 2026-08-07** after further simulator work: §B9–§B11 are new, and
§B9 (the demand cap) is a one-line change that removes a starvation trap.
§C1 records that adopting the port's uplink model removed one of *our*
headline results, which changes how Phase-1 measurements of multi-flow
uplink UEs should be read.

---

## A. What is faithful — do not disturb these

1. **Virtual queue update** (`ia_p5g_update_vq_dl`) is exactly our formula:
   grow by `target × slot`, clamp to
   `max(0, min(target_W, arrived_W) − delivered_W)`, drain by delivered.
   The windowed ceiling — including using *windowed arrivals* rather than
   instantaneous backlog — is implemented correctly. That subtlety cost us
   a regression in simulation; it is right here.

2. **Tier-2 metric shape** (`ia_p5g_dl_metric`): `(Σ_backlogged Q_f) × SE`,
   summed per UE. Matches `M_u` in §4.3 of the design doc, including the
   restriction to backlogged LCIDs.

3. **Tier-1 constraint set** (`ia_p5g_sca_solve`) matches ours:
   per-direction capacity `Σ r_i/SE_i ≤ C_d`, soft GBR floor
   `r_i + s_i ≥ G_i`, demand cap `r_i ≤ D_i`, `s_i` fixed to 0 for non-GBR.
   Class weights `w_Delay = 5`, `w_PF = 1`. *(Faithful to the design as it
   stood. We have since removed the demand cap from ours — see §B9.)*

4. **DL LCP fill** (`ia_p5g_compute_lcp_budget`): sort by
   `(priority ASC, Q DESC)` then greedy fill. Matches our MAC multiplexer.

5. **Per-UE granting** is inherited correctly from OAI — one DCI per UE,
   TB filled across LCIDs — which is what we refactored the simulator *to*.

6. **Tier-1 as a separate thread** writing an atomic snapshot read
   lock-free by the hot path, with `last_solve_abs_slot` staleness
   detection and graceful fallback before the first solve. This is exactly
   the integration architecture §10 of the design doc specifies.

7. **Two adaptations that were better than the simulator.** Both have since
   been adopted into `sim/`; recorded here because the port had them first.
   - **UL LCP is the UE's decision** (TS 38.321 §5.4.3.1). The gNB grants
     PRBs and the UE splits the TB. `ia_p5g_drain_vq_ul` approximates
     per-LCG delivery proportionally to BSR occupancy. The simulator wrongly
     assumed the gNB controls the split; correcting it (2026-08-07) removed
     a headline result that turned out to be an artifact — see §C1 below,
     because it changes how the port should be evaluated too.
   - **UL demand EWMA (α=0.3)** against TCP/Tier-1 window resonance. We could
     not reproduce the resonance with an AIMD source, but the reasoning is
     sound and the deployment evidence is direct; we defer to it.

---

## B. Issues, in priority order

### B1. CRITICAL — the drift-plus-penalty metric is not actually the ranking rule

`ia_p5g_dl_cmp` (and `ia_p5g_ul_cmp`) order UEs by:

```
1. has_gbr        (dl_has_unfulfilled_gbr)   — hard tier
2. pdb_ms         (dl_best_remaining_pdb_ms) — hard tier
3. coef           (the DPP metric)           — tiebreak only
```

The header comment says these tiers apply *"exactly when coef == 0 (Tier-1
not yet run)"*, i.e. they are intended as a **fallback**. As written they
are applied **unconditionally**, and both fields carry real per-UE values.
So `coef` — the entire output of Tier-1 and the virtual queues — only
discriminates between UEs that have the *same* GBR-deficit flag *and* the
*same* remaining PDB in milliseconds.

Consequences:

- A GBR flow comfortably ahead of its Tier-1 target still outranks a
  best-effort flow that is starving.
- Ordering is effectively **strict priority + EDF**, which is the scheme
  the literature already implements (Zaki 2011 gives GBR bearers strict
  priority; Monghal 2008 partitions by target attainment). The two-tier
  design exists to replace that partition with a metric that decides *how
  much* each flow gets, not merely who goes first.
- Tier-1's rate targets are close to inert for cross-class decisions,
  which makes the LP largely decorative in mixed traffic — exactly the
  workload it was built for.

**Fix.** Make `coef` the primary key and demote the tiers to a genuine
fallback:

```c
if (pp->coef > 0.0f || qq->coef > 0.0f) {      /* Tier-1 is live */
    if (pp->coef < qq->coef) return  1;
    if (pp->coef > qq->coef) return -1;
    return 0;
}
/* coef == 0 for both: Tier-1 not yet solved — original tiers */
if (pp->has_gbr != qq->has_gbr) return pp->has_gbr ? -1 : 1;
if (pp->pdb_ms  != qq->pdb_ms)  return pp->pdb_ms < qq->pdb_ms ? -1 : 1;
return 0;
```

Deadline awareness then re-enters where the design puts it — as the HoL
urgency term folded into `Q̃` (Phase-2 item 1), not as a hard tier above
everything. Until that lands, keeping `pdb_ms` as a *third* key rather than
a second is a reasonable interim.

This one change is worth measuring on its own: it is the difference between
"Tier-1 informs the schedule" and "Tier-1 breaks ties".

### B2. HIGH — Tier-1 capacity ignores the TDD special slot

`ia_p5g_compute_capacity` uses `get_full_dl_slots_per_period()` and
`get_full_ul_slots_per_period()`. On the deployment's **3D+1S+6U per 5 ms**
pattern that discards the S slot entirely.

Symbol-accurate accounting *including the special slot* is an explicit
design goal (design doc §3, and §III of the paper). The S slot typically
carries ~3 DL + ~9 UL symbols of 14; dropping it under-counts capacity by
roughly a slot in ten here, and proportionally more on UL-heavy patterns
like DSUUU where the S slot's UL portion is a larger share.

The direction of the error matters: Tier-1 believes the cell is **more
overloaded than it is**, inflates the slack variables, and — given B4 —
sacrifices more GBR flows than necessary.

**Fix.** Express capacity in **PRB-symbols per second** rather than
PRB-slots, and add the S slot's `dl_symbols` / `ul_symbols`. `SE` must
change units to match (bits per PRB-symbol: divide the current
`nr_compute_tbs(..., 14, ...)` result by 14, or compute for 1 symbol).
`r_i / SE_i` then stays dimensionally consistent.

### B3. HIGH — the Tier-1 objective has a ~1e10 coefficient range

The SCA linearisation sets utility coefficients to `w / (r_prev + 1)`.
For `r ≈ 10⁷` bps that is ~1e-7, against `IA_P5G_TIER1_GBR_PENALTY = 1e3`
on the slack columns. GLPK's simplex therefore sees a coefficient spread of
about **10¹⁰** in one objective row.

This is the same pathology we diagnosed and fixed in the simulator
(NOTES.md, 2026-08-06): two solvers disagreed by 3.6× on a flow's rate and
the highest-weighted class was under-served by 28% against the analytic
optimum. The header here already records symptomatic behaviour — *"causing
the SCA solver to fail convergence (iter → max_iters)"*.

**Fix — and it is smaller than it sounds.** Replace the single weighted
objective with the lexicographic pair:

```
Phase 1:  min  Σ p_i s_i           — a pure LP. One GLPK call, no SCA.
Phase 2:  max  Σ w_i log(r_i)      — SCA as today, but with the extra
          s.t. Σ p_i s_i ≤ S*        constraint row from Phase 1.
```

Phase 1 needs **no SCA at all** (no log term), so it is one clean simplex
solve. Phase 2 keeps the existing SCA loop but now optimises a
well-conditioned objective, because the penalty column is gone from it. Pose
both in normalised units (rates as a multiple of the largest contract,
capacity usage as a fraction of `C_d`) so all coefficients are O(1).

Side benefit, as in the simulator: `IA_P5G_TIER1_GBR_PENALTY` stops being a
magic number — only the *ratio* between flows matters, not its magnitude.

### B4. HIGH — no max-min stage, so cell-edge GBR flows will be abandoned

Expected for this version, but worth stating precisely so the fix is
adopted for the right reason. Once the penalty dominates, the linearised
program is an LP and its optimum is a **vertex**: GBR flows are served in
full or driven to exactly zero, greedily in spectral-efficiency order. The
lowest-SE UE is not degraded, it is dropped. No retuning of
`IA_P5G_TIER1_GBR_PENALTY` prevents this — reweighting only selects a
different victim.

**Fix.** Port `solve_maxmin_gbr_level` + `gbr_maxmin_floors` from
`scheduler/tier1.py`. Stage A is `max t s.t. r_i ≥ t·Ĝ_i` — another pure LP,
so a third GLPK call, no SCA. Then add `r_i ≥ α·t*·Ĝ_i` as extra row bounds
in the main solve. It is self-disabling (`t* = 1` ⇒ non-binding), so it
costs nothing when the GBR set is feasible.

### B5. MEDIUM — both features the study identifies as decisive are deferred

`D-P2-1` (HoL urgency) and `D-P2-2` (SPS / Configured Grants) are both
Phase 2. Those are precisely the two mechanisms our evaluation finds
load-bearing: configured grants give 30/30 deadlines against PF's 2/30 when
the control channel binds, and deadline-aware Tier-2 gives 8/8 against 5/8.
The Tier-1 LP, which Phase 1 *does* deliver, is the component the study
finds earns its place only in the moderate-overload band.

No action beyond what is already planned — the Phase-2 scope is correct.
But it means **Phase 1 measurements will understate the design**, and
should not be read as a verdict on it. Prioritising SPS/CG over the
diagnostic ring buffer would get the biggest observable win soonest.

### B6. MEDIUM — "Delay" class inferred from 3GPP priority ≤ 20

`ia_p5g_weight_from_priority` thresholds on priority to assign `w = 5`.
It is flagged as a judgment call, which is fair, but it will
misclassify: a GBR video bearer with a low priority value gets the Delay
weight, and a delay-critical bearer with a high priority value does not.

**Fix.** The 5QI QoS profile already distinguishes *GBR*, *non-GBR* and
*delay-critical GBR* resource types. Key the weight off resource type and
use `packetDelayBudget` directly, rather than off the priority integer.

### B7. LOW — slot duration is hardcoded to μ=1

`IA_P5G_SLOT_DURATION_S 0.5e-3f`. Correct for the current 30 kHz
deployment, but the virtual-queue growth rate silently doubles in error if
the carrier moves to μ=2 — which our own factory scenario uses (40 MHz,
μ=2). Derive it from `frame_structure` instead. Cheap to fix now, subtle to
debug later.

### B8. LOW — overhead factor 0.80 vs 0.85 in the simulator

Not wrong — the comment correctly explains it is a cell-level factor and
that folding a second per-RB term would double-count. Just note the two
codebases will not produce comparable absolute numbers until they agree.

---

### B9. HIGH — the Tier-1 demand cap is redundant, and it is a starvation trap

`ia_p5g_sca_solve` line 415 sets a hard upper bound per flow:

```c
glp_set_col_bnds(lp, i + 1, GLP_DB, 0.0, flows[i].demand_bps);
```

fed by a BSR-derived estimate (line 630, `arr_W * 8 / elapsed_s`) with EWMA
smoothing. We built the same thing in the simulator, and then measured it
away.

**It is redundant.** Tier-2's windowed ceiling already clamps a flow's
virtual queue to what actually arrived, so a quiet flow is never scheduled
however generous its Tier-1 target. The ceiling does this from
*observation*; the cap needs a *prediction*. Removing the cap reproduced
oracle-demand performance exactly in our simulator (32.4 M, Jain 0.97, with
no demand estimate at all) and left `factory_robots` unchanged.

**It is also actively harmful.** Because the bound is hard, an
under-estimate is unrecoverable within the window while an over-estimate
merely wastes headroom. With demand estimated from arrivals, a flow that
loses out appears to be asking for less, its cap falls, and it loses more:
six contending flows went from 3.9–7.0 Mbps to 0.2–11.8 Mbps, Jain
0.97 → 0.47. And when the estimate collapses below a GBR flow's GFBR, the
hard cap **silently overrides the contract** — the soft floor `r+s ≥ G`
cannot rescue it, the flow simply books a large unavoidable shortfall.

**Recommendation: drop the demand column bound.** Replace
`GLP_DB, 0.0, demand_bps` with `GLP_LO, 0.0` (lower bound only). The EWMA
machinery can stay for reporting and for admission control, where a demand
figure is genuinely wanted. This also deletes the estimator-tuning problem
the UL-demand-oscillation work was fighting.

### B10. HIGH — `arrived_cum` omits discarded bytes, in four places

The port computes cumulative arrivals as delivered plus current backlog:

```c
const uint64_t arr_cum = del_cum + <bytes_in_buffer | estimated_ul_buffer>;
```

at lines 620 and 650 (Tier-1 demand estimate) and 1168 and 2072 (the DL and
UL windowed ceilings). **Bytes discarded on PDB expiry are counted in
neither term**, so they vanish from the arrival history.

The consequence is a feedback loop with no physical cause. As a flow
starves, its data ages out; `delivered + backlog` stops growing while its
true offered rate is unchanged; the flow appears to have stopped asking. In
our simulator this drove a flow to 0% delivery whose arrivals never changed
(2.03 MB offered either way; delivered 0.95 → 0.00 MB, dropped 0.90 → 1.85 MB).

This is worse in the port than it was for us, because the same expression
feeds **both** the demand estimate *and* the windowed ceiling. Even after
B9 removes the demand cap, an arrival count that omits discards makes the
ceiling too low for exactly the flows that are already suffering — clamping
the virtual queue of a starved bursty flow and de-prioritising it further.

**Recommendation:** add a per-LCID discard counter and use
`delivered + backlog + discarded`. The gNB knows its own RLC discards for
DL. For UL the UE discards and does not report it, so the uplink estimate
stays biased; that is an argument for B9 (drop the cap) rather than for
trying to fix the uplink estimate.

### B11. MEDIUM — a better UL split estimator is available

`ia_p5g_drain_vq_ul` apportions a grant across LCGs proportionally to BSR
occupancy. The gNB configured each channel's PBR and bucket-size duration
over RRC, so it can instead run the UE's LCP against a *shadow* copy of the
token buckets and predict the split. We implemented both.

Measured: the shadow copy tracks the UE's real buckets to within ~2% of
capacity on average, and the drift cannot run away because a bucket is
clamped to `[0, PBR·BSD]` — both copies re-synchronise at either rail.

Two caveats worth having before you build it. First, on our workload the
choice **did not change delivered outcomes** (mean GBR 59% either way), so
this is a fidelity improvement rather than a performance one. Second, we
tried closing the loop — feeding BSR-vs-prediction residuals back into the
shadow bucket — and it made divergence *worse* (mean 1.9% → 7.1%), because
new arrivals raise the reported backlog exactly as a mis-prediction would
and the controller cannot tell them apart. If you attempt a correction, use
an unambiguous signal: only correct when the reported backlog *falls*.

## Suggested order of work

1. **B1** (comparator) — smallest diff, largest behavioural effect, and it
   determines whether anything else in Tier-1 is observable.
2. **B9** (drop the demand cap) — a one-line change that deletes a
   starvation trap and an entire estimation problem. Measured free.
3. **B10** (count discards in `arrived_cum`) — small, and it fixes the
   windowed ceiling as well as the demand estimate. Do it even if B9 lands,
   because the ceiling needs it independently.
4. **B2** (S-slot capacity) — contained, removes a systematic bias.
5. **B3** (lexicographic split) — removes the conditioning risk and the
   magic constant; also *simplifies* the solver path, since Phase 1 needs
   no SCA.
6. **B4** (max-min floors) — slots in cleanly once B3 has established a
   two-solve structure.
7. **B6**, **B7**, **B11** — correctness and fidelity, any time.

B1, B9 and B10 are each worth measuring individually before the bigger
Tier-1 changes land, so the Phase-1 baseline stays attributable.

## C. What flowed back into the simulator, and what it cost

### C1. The UL LCP correction removed one of our headline results

Adopting the port's model — the UE fills its own uplink transport block —
changed the simulator's conclusions materially, and the change is relevant
to how Phase-1 measurements should be read.

Our study had reported that the two-tier scheduler protected multi-flow
uplink UEs (a GBR video flow sharing a UE with a greedy best-effort flow)
where the QoS-blind baselines collapsed them to ~3% of contract. With the UE
filling its own block by prioritised bit rate, **the baselines reach
100/90/92% unaided**. The protection was the UE's PBR configuration, not the
scheduler. Correcting it also raised PF's GBR contract count at moderate
overload from 5/10 to 8/10 — most of the margin we had been claiming.

**Implication for the port:** any Phase-1 measurement of multi-flow uplink
UEs should be read the same way. If PBRs are configured sensibly, a large
part of what looks like two-tier benefit on those UEs will be present under
the stock PF scheduler too. Worth checking directly on the testbed, since
it is cheap: configure the PBRs, run stock PF, and see how much of the gap
survives.

### C2. Still owed

**TCP/Tier-1 window resonance.** We built a rate-adaptive source and swept
its period against the Tier-1 window and **could not reproduce** the
oscillation the EWMA was introduced to fix — no peak at ratio 1.0, just a
flat 10–15% cost for estimating demand at all. Either our AIMD source is too
unlike a real TCP sender, or the effect needs dynamics we do not model. The
deployment evidence for it is direct, so we defer to it, but the mechanism is
not yet reproduced outside the testbed and it would be worth a targeted
measurement there.
