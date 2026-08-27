# Phase 2 plan — both schedulers, written fresh against verified OAI source

Follows `docs/wp5-plan.md`/`docs/wp6-plan.md`/`docs/wp-join-plan.md`'s
format: ground truth cited exactly, decisions made explicitly with
alternatives surfaced, a commit checklist with per-commit predictions, and
a ranked falsifiable-predictions subsection (this WP is comparably complex
to WP-Join, so it gets its own numbered subsection the way WP-Join's did,
rather than WP5/WP6's unheaded-prose treatment of the same idea).

Read `README.md` (§2, §4's Phase 2 table, §7, §8), `CLAUDE.md`,
`docs/p5g-sim-plan.md` §9 (WP2a/WP2b/WP8, now superseded/absorbed — see §0),
and `docs/wp-join-plan.md` (for the plan-doc format this follows) first.

---

## 0. Scope, and the central methodological question this plan exists to answer

No `p5g-sim-plan.md` §9 entry scopes "Phase 2" as such — WP2a (read the
reservation branch), WP2b (build `reservation.py`), and WP8 (two-tier
alignment audit) are superseded and absorbed into one pass per
`README.md:121-131`: rather than port one scheduler, audit it, then build
the second one, both schedulers are written once, at the end of Phase 1,
directly against already-verified OAI source. This plan's charter is
`README.md` §4's Phase 2 table, §7's ground truth, §8's `[OPEN: PHASE2]`
items, and CLAUDE.md's standing invariants — not `p5g-sim-plan.md` §9's
original WP2a/WP2b/WP8 text, which is left as history, same treatment
every other superseded section of that document gets.

**Every prior WP had an objective, falsifiable check** — a test passing, a
`--check` diff, a measured number against a prediction. Phase 2's
deliverable is different in kind: *fidelity to C source*. No test can
verify "this Python is a faithful port" by running it — a faithful port
and a plausible-looking unfaithful one both pass `pytest`, both produce
some numbers, and `regression_corpus.py --check` can only tell you the
numbers changed, never whether they changed *correctly*. Silent
unfaithfulness — a port that runs, looks reasonable, and is simply wrong
in a way nothing catches — is this WP's actual failure mode, not a crash
or a red test.

**How this plan makes faithfulness checkable rather than asserted — three
layers, combined:**

1. **Extend `docs/oai-port-map.md`** (exists today, ~164 lines: one
   `## WPn — title` section per work package, each holding a
   `# | Mechanism | C source | Python | Test(s) | Divergence` table,
   ordered load-bearing-first, plus a closing worked-numeric-trace
   section). Add `## Phase 2 — reservation` and `## Phase 2 — two-tier`
   sections in the same format, one row per mechanism ported. This is the
   primary mechanism: "is this faithful" becomes a table lookup against
   an exact C `file:line` ↔ Python `file:line` correspondence, not a
   re-read of a diff. Land each scheduler's port-map rows in the same
   commit as the mechanism they document — never batched at the end.
2. **Property tests derived from the C's own invariants**, alongside the
   port-map rows, the same species of check `sim/tests/test_bsr.py`
   already runs byte-for-byte against `NR_SHORT_BSR_TABLE`/
   `NR_LONG_BSR_TABLE`. Concretely for this WP: `reservation.py` at
   `n_followers=0` must degenerate to the follower-budget formula's own
   identity (unconstrained budget = full `bwpSize`/`max_rbSize`); the UL
   floor's fruitless-shift must cap at exactly 16× (shift=4), never 15×
   or 17×; the ADQ trigger must fire at exactly 8 consecutive `min_rb`
   grants, never 7 or 9. Each such test cites the exact constant it's
   checking against, in the port-map row it belongs to.
3. **A worked numeric trace per scheduler**, mirroring `oai-port-map.md`'s
   existing BSR trace exactly: hand-computed slot-by-slot for one small,
   fixed scenario, checked against both the C's own arithmetic and the
   Python's actual runtime output (not hand-derived and then transcribed
   — the existing BSR trace's own stated discipline).

**Why not a fourth layer — a mechanical structural control-flow diff:**
considered and rejected. OAI's C and a from-scratch Python scheduler have
deliberately different control structures in real places — the SCA/GLPK
outer loop (two-tier's Tier-1) has no Python-native control-flow
analogue to diff against; `qsort`+two-pass-iteration in C naturally
becomes `sorted()`+one dataclass-driven loop in Python. A mechanical diff
would flag every faithful port as divergent, producing noise that trains
reviewers to ignore the tool. The port-map's file:line correspondence
table, at the mechanism altitude rather than the statement altitude, is
the right substitute — same reasoning `docs/wp-join-plan.md` used when it
picked a calibrated delay distribution over full RACH contention
simulation: match the fidelity the actual question needs, not the most
literal possible translation.

---

## 1. The mechanism, plain language

### 1.1 What's being replaced, and what's being added

`scheduler/two_tier.py` (1148 lines, `TwoTier` class) is rewritten in
place. It currently carries two mechanisms confirmed **absent from real
hardware**: SPS/Configured-Grant (`_SPSReservation`, `_allocate_sps`,
`_is_sps_eligible`, `two_tier.py:22-38,540-671,997-1058`) and UL
intra-TB per-flow byte-split estimators (`_shadow_lcp_split`,
`_occupancy_split`, `two_tier.py:888-963`) that model something the real
gNB structurally cannot observe (only aggregate per-LCG BSR). Both are
deleted outright, not ported — see §2 for the C-source confirmation of
their absence, and §3/D1 for what replaces the split estimators'
*sim-bookkeeping* role.

`scheduler/reservation.py` does not exist on `main` or this branch today.
It is written from scratch against `oai-branches/reservation/`.

Both conform to the existing `Scheduler` Protocol
(`scheduler/interfaces.py:148-161`, `configure()`/`allocate()`) — no
interface change. Both are candidates for `SchedulerContextReset`
(`scheduler/interfaces.py:164-195`) — two-tier keeps it (re-ported against
its new state layout), reservation gets a documented no-reset-needed
finding (§4, reservation commit 11).

### 1.2 Two-tier: three-part mechanism (Tier-1 LP, Tier-2 VQ, UL floor), one LCP fill

Real hardware's `ia_p5g_scheduler.c` layers three things per direction:

- **Tier-1**: a slow (0.1 s-period, not 1.0 s — see §2) rate-allocation
  solve, re-run on its own cadence, producing a *target* bps per
  flow (DL, per-LCID) or per-LCG (UL). Implemented as an SCA outer loop
  wrapping repeated GLPK simplex solves of a PF-log-linearized LP with a
  soft GBR-floor slack row — not a bare LP, and not a hard GBR
  constraint.
- **Tier-2**: every slot, a windowed-ceiling virtual queue (VQ) per
  flow/LCG accumulates at the Tier-1 target rate and is capped by a
  window-based ceiling — DL's ceiling is an arrival-delta formula; UL's
  is a *different*, backlog-bound + N-window-catchup formula (a real,
  in-code-documented divergence from what the header claims — §2).
  The VQ magnitude (plus, for UL, an urgency-barrier term) replaces the
  PF coefficient as the per-UE ranking metric for that slot's grant
  decision.
- **UL floor**: a per-UE anti-starvation subsystem layered on top of the
  ranking, independent of VQ/Tier-1 — an exponential-backoff
  "fruitless counter" (caps at 16×) that force-includes a starved UE in
  scheduling, and a separate "ADQ" trigger that detects a UE stuck
  receiving only crumb-sized (`≤min_rb`) grants and forces a full-budget
  grant instead of demand-sized one.
- **DL LCP fill**: once a UE is granted PRBs, filling its TB across
  logical channels is a single greedy pass over DRBs (sorted by
  `(priority, VQ)`) with a per-LCID byte budget, plus SRBs pulled
  uncapped regardless of pass — **not** the two-stage 3GPP LCP the header
  itself labels "deferred to Phase 2" (an OAI Phase 2 that was never
  built; not this document's Phase 2).

### 1.3 Reservation: four-tier sort + follower budget, real two-pass DL LCP

`oai-branches/reservation/`'s scheduler has no LP, no VQ, no floor state
machine — it is a per-slot sort-and-greedily-fill design:

- Every UE candidate for a slot's grant gets a comparator key: SRB
  presence, then liveness (keepalive/SR), then GBR-obligation presence,
  then (UL only) `sched_inactive`-last, then PDB (tighter first), then a
  PF coefficient (`tbs/thr`, thr floored at 1.0) as the final tiebreak.
  `qsort` on this comparator produces the grant order for the slot.
- Before granting, each UE's `max_rbSize` is capped by a **follower
  budget** — PRBs reserved for UEs ranked behind the current one that
  still need service, so a single saturating UE can't starve everyone
  behind it. UL and DL compute this differently (§2) — not a shared
  formula.
- GBR flows accumulate a deficit against their obligation; a grant drains
  that deficit. **UL's drain has a real, comment-contradicting bug**
  (§2) that must be ported bug-for-bug, not fixed.
- DL's LCP fill genuinely is two-pass: an SRB round over `lc_config`,
  then a DRB round — the actual 3GPP-§5.4.3.1-shaped structure the
  charter originally described for *both* schedulers, but which (per §2)
  only reservation actually implements.

---

## 2. Ground truth, cited exactly

All citations `file:line` against `oai-branches/{two-tier,reservation}/`
unless noted. `gNB_scheduler.c` and `gNB_scheduler_primitives.c` are
confirmed byte-identical across both branches (`oai-branches/README.md`)
— `gNB_scheduler_primitives.c` predates both forks (stock upstream OAI,
commit `f548643`), and is where OLLA's `get_mcs_from_bler`
(`:785-822`, `sim/olla.py`'s own citation) lives — confirming OLLA's
ground truth is genuinely shared, not branch-specific.

### 2.1 Two-tier

**Tier-1 is SCA-wrapped GLPK simplex, not a bare LP.**
`ia_p5g_sca_solve()`, `ia_p5g_scheduler.c:974-1103`. Per-iteration
objective coefficient `weight_i / (r_prev_i + ε)` (`:1070`) — the
PF-log-utility linearization; real `glp_simplex()` call (`:1074`); damped
update `damped = α·v + (1-α)·r_prev`, `α = IA_P5G_TIER1_SCA_ALPHA = 0.2`
(`:373`, applied `:1089-1090`); converges at `1e-6` relative change or
`IA_P5G_TIER1_SCA_MAXITERS = 150` iterations (`:374-375`, loop `:1068`,
break `:1096`). GBR floor is a **soft** slack-penalized row
(`IA_P5G_TIER1_GBR_PENALTY = 1.0e3`, `:372`, penalty on slack in the
objective `:1019`), not a hard constraint — "always feasible by
construction" per the code's own comment (`:969-973`).

**Tier-1 period: confirmed 0.1 s, header stale at 1.0 s** —
`IA_P5G_TIER1_PERIOD_S` macro, `ia_p5g_scheduler.c:74-76` (`#define
IA_P5G_TIER1_PERIOD_S 0.1f`), assigned into state at `:311`; header
comment claims `1.0 s default` (`ia_p5g_scheduler.h:211`, restated
`:5,67`). Confirmed as the value every downstream computation uses
(`target_W_bits = r_bps * tier1_period_s`, `:1879,3662`;
`usleep(tier1_period_s * 1e6f)`, `:1132`).

**This repo's current Python already got this wrong, independently —
found scoping this plan, recorded in `README.md` §7 and `CLAUDE.md`
directly (not only here).** `scheduler/two_tier.py:77`'s
`tier1_period_slots` default is `2000`; at this repo's default
`numerology=1` (`sim/config.py:35`) → `slot_duration_s=0.5ms`
(`sim/resource.py:23`) → `2000 × 0.5ms = 1.0s`, i.e. the current default
silently encodes the *header's* stale value, not the confirmed-real
macro. Phase 2 defaults to 200 slots at numerology 1, and should derive
the slot count from `tier1_period_s=0.1 ÷ grid.slot_duration_s` rather
than hardcoding a slot count, so a numerology change can't silently
re-break this.

**Windowed-ceiling VQ — DL matches the header, UL does not.**
DL (`ia_p5g_update_vq_dl`, `:1835-1894`): growth
`vq_dl[idx][lcid] += r_bps * IA_P5G_SLOT_DURATION_S` (`:1866`,
`IA_P5G_SLOT_DURATION_S=0.5e-3f`, `ia_p5g_scheduler.h:63`); ceiling
`min(vq_dl, max(0, min(arr_W*8, target_W_bits) - del_W*8))` (`:1868-1890`)
— matches `ia_p5g_scheduler.h:178-186`'s documented formula exactly.
LCID≥4 only (DRBs; SRBs skipped, `:1856`).

UL (`ia_p5g_update_vq_ul`, `:3578-3687`): growth identical pattern
(`:3606`). **Ceiling formula genuinely diverges from the header**, which
documents the same arrival-delta approach for UL — the actual code
(`:3608-3685`, justified by an in-code bugfix comment `:3609-3654`,
"starvation inverts the metric": arrival-delta collapses to 0 exactly
when a flow is starved and stops absorbing "arrivals") uses instead:

```
backlog_bits   = estimated_ul_buffer_per_lcg[lcg] * 8
target_W_bits  = r_bps * tier1_period_s
catchup_W_bits = IA_P5G_VQ_UL_CATCHUP_N * target_W_bits    (N=5, :77-79)
del_W_bits     = (mac_stats.ul.lc_bytes[lcg+3] - ul_delivered_hist[idx][lcg]) * 8
ceiling        = max(0, min(backlog_bits, catchup_W_bits) - del_W_bits)
vq_ul[idx][lcg] = min(vq_ul[idx][lcg], ceiling); floor 0
```

**Port the code's UL formula, not the header's.** This is CLAUDE.md's
"reproduce measured behavior, not documented intent" rule, a second
confirmed instance beyond the deficit-drain case it was written for (and
the current Python's `tier1_period_slots` default is now a third — see
above). LCG 0 (SRB) excluded (`:3597`); `lcid = lcg + 3` mapping
(`:3658`).

**UE ranking metric composition**: DL is a pure VQ sum
(`ia_p5g_dl_metric`, `:1896-1923`, `Σ vq_dl × spectral_eff` over active
LCIDs). UL's actual comparator metric is richer than the header's
documented `ia_p5g_ul_metric()` (a plain `Σ Q_g × SE`,
`ia_p5g_scheduler.h:391`) — the real `ia_p5g_pf_ul()` computes
`base_q + W·urgency^EXP·max(max_q,1)` inline (`:2891-2917`, constants
`:443-444,478-481,501`), a deadline-urgency barrier term the exported
stub doesn't reflect. Port the inline composite, not the documented
stub.

**UL service-interval floor** (`ia_p5g_ul_summary_t` struct,
`:682-744`; constants `:80-107`): `theta = max(pdb_ms / 8 / slot_ms, 2)`
(`IA_P5G_UL_FLOOR_PDB_DIV=8`, `IA_P5G_UL_FLOOR_MIN_SLOTS=2`, `:2388-2393`).
Fruitless-shift: increments on a "blackout" fire (armed, empty, silent
≥ theta_eff, `:2482`), capped at `IA_P5G_UL_FLOOR_FRUITLESS_SHIFT_MAX=4`
→ `theta << 4` = **16× confirmed**; decays 1 step per
`IA_P5G_UL_FLOOR_FRUITLESS_DECAY_MS=500` ms of age (`:2412-2426`).
One-time deficit forgiveness gates separately on `floor_fruitless ≥
IA_P5G_UL_FLOOR_FRUITLESS_MAX=3` (`:2488-2493`) — a different threshold
from the shift cap, do not conflate the two. Arming is
**delivery-history-based**, not BSR-based (`floor_alive_valid` +
`IA_P5G_UL_FLOOR_ALIVE_MS=2000`, `:2364-2375`) — a documented v1→v2 fix
against a corruptible signal. ADQ: `floor_crumb_run` increments on every
`rbSize ≤ min_rb` grant, resets on any larger one (`:3319-3323`); fires at
`floor_crumb_run ≥ IA_P5G_UL_FLOOR_ADQ_CRUMB_RUN=8` (**confirmed
exactly 8**, `:2477-2480`), gated by its own doubling backoff period
(also capped at the shift max, `:2460-2475`), resets `floor_crumb_run`
to 0 and increments `floor_adq_backoff` on fire (`:2500-2506`). On either
fire type: grant sizing bypasses `nr_find_nb_rb`'s demand-based sizing
entirely, using the full `available_rb` directly (`:3232-3258`), while
still respecting the GBR PRB reserve (`:3105-3124`, "FIX-2" — not
independently required by README's Phase 2 table, see §6 Flags) and the
PHR power ceiling (`:3126-3163`).

**DL LCP fill is NOT two-pass** — a correction to `README.md` §4/§7's
charter text, which currently states "two-pass DL LCP" for *both*
schedulers (see §6, Flags). Real structure
(`ia_p5g_compute_lcp_budget`, `:1945-2000`, consumed by
`nr_generate_dlsch_pdu`, `gNB_scheduler_dlsch.c:1361-1429`): SRBs
(LCID<4) get budget `-1` (uncapped, pulled freely regardless of order,
`:1962-1965`); DRBs (LCID≥4) are sorted `(priority ASC, vq_dl DESC)`
(`lcp_cmp`, `:1934-1943`) and greedily filled against `tbs_bytes` in a
**single pass** (`:1992-1999`). The header explicitly labels the real
3GPP two-stage PBR-token-bucket LCP as deferred
(`ia_p5g_scheduler.h:19-31,321`, "Phase 2 D-P2-3") — an OAI roadmap item
never built, not this document's own Phase 2. Port the real single-pass
+ SRB-exempt structure.

**SPS/Configured-Grant: confirmed absent from the C source entirely.**
`ia_p5g_scheduler.h:28-30` ("Deferred to Phase 2: ... D-P2-2");
`nr_ue_procedures.c:412` (`// TODO ... SPS-Config ... not implemented`);
`nr_ue_procedures.c:886,1352` (`NULL, // SPS not implemented`);
`nr_mac_common.c:3265` ("Semi-persistent scheduling ignored for now").
The only UL "Configured Grant" reference
(`UL_SCH_LCID_CONFIGURED_GRANT_CONFIRMATION`,
`gNB_scheduler_ulsch.c:560-562`) is a no-op MAC-CE-recognition `case:
break;`, not allocation logic. `_SPSReservation`/`_allocate_sps` exist
only in this repo's stale Python; delete, don't port.

**`min_rb` = `nrmac->min_grant_prb`, static config scalar, confirmed.**
Read-only at every use site (e.g. `ia_p5g_scheduler.c:2210`,
`gNB_scheduler_ulsch.c:2055`); never derived from SNR/MCS/payload.
Assignment site not present in any vendored file (minor provenance gap,
§6 Flags — model as a fixed Python config parameter regardless).

**Retransmission priority — confirmed not a porting gap.** OAI's C
services retransmissions inline, ahead of and outside the PF/tier
`qsort`, in both `pf_ul`/`pf_dl`. This simulator's driver already gives
every scheduler an equivalent property structurally: `sim/driver.py:434`
(`harq_pool.due_this_slot(slot_index)`, serviced before
`scheduler.allocate()`) and `:559-562` (`HarqAwareBufferView` wraps
`buffers` before the call, masking any pending flow's backlog to 0) both
run *before* `scheduler.allocate()` is invoked, for every scheduler,
today — confirmed by reading the file directly. No new scheduler-side
retransmission-priority code is needed; record as a resolved
non-finding (§6).

### 2.2 Reservation

**Follower budget — UL confirmed exactly as charter states, DL is a
genuine asymmetry not previously documented.** UL
(`gNB_scheduler_ulsch.c:2421-2430`): `budget = bwpSize -
n_followers_need × min_rb`, floored at `min_rb`
(`min_rb = nrmac->min_grant_prb`, `:2061`). DL
(`gNB_scheduler_dlsch.c:850,909-924`) uses a **different base**
(`max_rbSize`, contiguous free RBs found by greedy scan from `rbStart`,
not `bwpSize`) and a **hardcoded literal** `min_rbSize = 5` (`:850`),
**not** `nrmac->min_grant_prb`. Port both formulas exactly as measured —
do not assume DL mirrors UL.

**Four/five-tier sort — genuinely different tier counts per direction.**
UL comparator (`gNB_scheduler_ulsch.c:2010-2039`): SRB → liveness → GBR
→ `sched_inactive`-last → PDB → PF-coefficient tiebreak — **5 comparison
tiers**, with the starvation-fix comment confirmed verbatim at `:2027`
("was -1 = front, a bug"). DL comparator
(`gNB_scheduler_dlsch.c:692-715`): SRB → liveness → GBR → PDB/coef —
**4 tiers, no `sched_inactive` field or tier exists in DL's `UEsched_t`
at all** (`:681-690`), and no such bug-fix comment appears anywhere in
the DL file (grep-confirmed absent). Port each as measured; do not force
a single shared 5-tier comparator onto both directions.

**GBR/BE byte split**, both directions confirmed: UL
(`gNB_scheduler_ulsch.c:2229-2284`) and DL
(`gNB_scheduler_dlsch.c:324-411`) — obligation floored at 1
(`:2253-2254`/`:379-380`), deficit accumulated and capped
(`:2256-2259`/`:381-385`), target spread over remaining PDB capped at
2× max-burst (`:2262-2270`/`:390-400`), overflow beyond target credited
to best-effort (`:2271-2278`/`:401-409`).

**Deficit-drain bug, confirmed bug-for-bug, UL only.** Comment at
`gNB_scheduler_ulsch.c:2772`: *"distribute tb_size drain proportionally
across active LCGs."* Code at `:2769-2775`:

```c
for (int _lcg = 0; _lcg < 8; _lcg++) {
  if (sched_ctrl->estimated_ul_buffer_per_lcg[_lcg] <= 0) continue;
  sched_ctrl->ul_lcg_last_grant_slot[_lcg] = grant_slot_abs;
  if (sched_ctrl->ul_lcg_deficit_bytes[_lcg] > 0) {
    sched_ctrl->ul_lcg_deficit_bytes[_lcg] -= sched_pusch->tb_size;   // FULL tb_size, no split
    if (sched_ctrl->ul_lcg_deficit_bytes[_lcg] < 0)
      sched_ctrl->ul_lcg_deficit_bytes[_lcg] = 0;
  }
}
```

No division, no `tb_size / n_active_lcgs`, no proportional split anywhere
in this loop — the **full** `tb_size` is credited independently to
*every* active LCG (i.e. every LCG with `estimated_ul_buffer_per_lcg >
0`) with a positive deficit. **Port exactly this** (full-credit, floored
at 0, per active LCG). DL's equivalent
(`gNB_scheduler_dlsch.c:1455-1460`) is genuinely correct — it drains
`dl_lcid_deficit_bytes[lcid]` by the actual `lcid_bytes` written to that
specific LC during the two-pass LCP loop below — no bug on DL, do not
port the UL shortcut there.

**Two-pass DL LCP — this is where the real structure lives.**
`gNB_scheduler_dlsch.c:1394-1463`: `for (_pass = 0; _pass < 2; ++_pass)`
(`:1397`), pass 0 restricted to SRB (`lcid==1 || lcid==2`, `:1402-1404`),
pass 1 to DRB, both passes iterating `lc_config` in existing order.
Confirmed exactly as the charter describes — port faithfully. This is
the one scheduler for which "two-pass DL LCP" is accurate (see §6,
Flags, for two-tier's contrasting reality).

**PF coefficient**: `tbs/thr`, `thr` floored at `1.0`, confirmed both
directions (`gNB_scheduler_ulsch.c:2301-2302`,
`gNB_scheduler_dlsch.c:823-824`), used **only** as the final comparator
tiebreak (`:2036-2037`/`:712-713`), not an earlier tier and not part of
RB sizing directly.

**`estimated_ul_buffer_per_lcg` freezing** — confirmed identical to
existing WP3/CLAUDE.md documentation: written only at BSR receipt
(short `:625-644`, long `:646-678`), read-only (a guard condition,
`:2769`) in the drain loop, never decremented by a grant — only
`ul_lcg_deficit_bytes[]` is. No new finding here beyond confirming the
existing documented behavior also holds in the reservation source.

**Acceptance criterion** (`README.md:864`, pre-approved) — **corrected
scoping, found planning commit 4**: the provable identity is that at
`n_followers_need=0` the follower-budget CLAMP is a no-op — algebraically,
`budget=base` and `base<=base` always, so `max_rbSize>budget` never
holds, regardless of `min_rb`/base. This matches PF's own unconstrained
`ceil(backlog*8/bpr)` sizing, but it is **not** a claim that all of
`Reservation` collapses to `PF`: the sort tiers (commits 2/3) and 4a's
target-based sizing are untouched by the follower-budget mechanism and
remain real differences from PF whenever a GBR deficit is active. This
document's own D4 (below) and `README.md` §10 previously stated the
broader, incorrect version ("reservation reduces to plain PF") —
corrected in both places, the same treatment commit 3 gave commit 2's
`pdb_ms` bug and 3a gave commit 3's arithmetic. Build the narrower,
correct claim as an automated property test on the follower-budget
function directly (§4, reservation commit 4), not an eyeball check.

**Call graph** (both branches, `gNB_scheduler.c:147-268`): UL is
scheduled strictly before DL in the same slot
(`nr_schedule_ulsch` `:246`, then `nr_schedule_ue_spec` `:251`) — a hard
per-slot ordering dependency to replicate, not an artifact of the C's
locking. Within each direction: a retransmission pass first (inline,
bypassing the sort entirely — already covered by this simulator's
existing driver-level HARQ seam, §2.1), then build ranking candidates,
`qsort`, then walk the sorted list computing follower budget → RB sizing
→ grant emission.

---

## 3. Decisions

### D1 — UL intra-TB per-flow byte split (user decision, obtained directly)

**Decided**: the scheduler's own ranking/allocation logic operates purely
on LCG-aggregate quantities — matching `ia_p5g`'s `vq_ul[UE][LCG]`
exactly, the real gNB's own granularity (confirmed by §2: DL's VQ is
genuinely per-LCID because the gNB owns DL RLC buffers, but UL's is
per-LCG because the gNB only ever sees aggregate BSR — the asymmetry is
real, not an oversight to smooth over).

**Correction, found scoping reservation commit 1 — the paragraph
originally here described a *new* sim-only bookkeeping step needing to
be built (proportional-to-reported-backlog arithmetic, stripped-down
`_occupancy_split`). That was wrong: it already exists.** `sim/ue_lcp.py`
is a real UE-side PBR-token-bucket LCP simulation — exactly the "more
faithful, more code" alternative considered below, except it turns out
to already be built, already tested, and already used by every existing
scheduler (PF, RoundRobin, Gradient, and TwoTier's own `ue_grant=True`
fallback path). A UL grant that follows the existing convention —
`Allocation(qfi=-1, direction="UL", ue_grant=True, bytes_capacity=<whole
TB>)` (`sim/baselines/_mac.py:60-72`) — never computes a per-flow split
itself; `sim/driver.py:613` calls `ue_lcp.fill(...)` entirely outside any
scheduler's code once the grant is emitted. So D1's requirement is met
with **zero new code**: `reservation.py` (and, later, the rewritten
`two_tier.py`) just needs to conform to the same `ue_grant=True`
convention every other scheduler already uses, not build a new
bookkeeping mechanism.

**Binding requirement on implementation** (stated by the user, still
holds, now enforced by an existing rather than a new boundary): this
split must be **structurally** unable to reach the scheduler, not
conventionally separate by docstring or code review discipline — the
same "consume, don't extend" enforcement `sim/join.py`'s relationship to
`sim/rlf.py` already demonstrates. This is already true today: every
`scheduler/*.py` file's imports were checked directly, and none imports
anything from `sim` — `scheduler/` depends only on stdlib, `cvxpy`/
`numpy`, and itself (`two_tier.py`'s own docstring already claims this).
`sim/ue_lcp.py` lives in `sim/`, so as long as `reservation.py` never
imports it or reimplements its own version, this requirement is met by
the existing package boundary, not by anything `reservation.py` itself
has to enforce. A durable, package-wide test (walk every file under
`scheduler/`, assert none contains `import sim`/`from sim`) makes this
checkable going forward rather than an assumption re-verified by
re-reading imports each commit — see reservation commit 1's checklist.

**Why the alternatives were rejected, as originally framed** (record
both, since the framing shaped the original decision even though it
turned out to be based on an incomplete picture of what already
exists): a full UE-side PBR-token-bucket LCP simulation was framed as
"more faithful to how the split is actually produced on real hardware,
but materially more code" — true of building one from scratch, false of
reusing `sim/ue_lcp.py`, which the framing didn't know existed at the
time. Punting entirely on a single-flow-per-LCG assumption was rejected
because that assumption is *exactly* what makes `README.md`'s H5 finding
untestable in the first place (`README.md` §8) — building Phase 2 around
it would entrench the gap rather than leave it open for the H5 follow-up
scenario `README.md` already calls for. That reasoning still stands; only
the "more code" premise for the rejected first alternative needed
correcting.

### D2 — OLLA activation (user decision, obtained directly)

**Decided**: activate in Phase 2, as its own commit per scheduler, in two
steps. (a) Land a real per-UE-per-direction MCS-selection call site in
both new schedulers first, using the existing static staircase
(`scheduler/link.py`'s `bits_per_prb`/`mcs_threshold_for_snr`) — this
alone gives grant-time MCS a persistent home neither scheduler has today
(link adaptation is currently entirely stateless). (b) A dedicated
follow-on commit swaps that static lookup for `sim/olla.py`'s ratchet
(`OllaState`/`update_mcs_from_bler`), reading/writing only at this one
call site — `ChannelView.get_reported_snr_db()` reads used for
PF-ranking/Tier-1-capacity/SNR-EWMA purposes elsewhere in each scheduler
are explicitly **not** touched, per `sim/olla.py`'s own docstring warning
against wrapping that method (doing so would silently feed OLLA's
ratcheted value into every unrelated consumer of reported SNR).

**The follow-on commit's checklist must include**, per the user's
instruction:
(i) A specific, stated-before-running prediction of drift direction for
    the low-rate control flows OLLA's `num_dl_sched ≤ 3` ratchet-down
    branch targets (`periodic_control`/`condition_monitor` kinds),
    checked against actual `--check` output, not left as "some drift
    expected."
(ii) Running the compounding-vs-coincidence test `docs/wp5-plan.md`
     commit 6 designed but flagged as undeployable until OLLA activates:
     per-UE aggregate degradation (not per-flow) compared between UEs
     with *both* a low-rate/OLLA-ratcheted DL flow and a low-rate/
     SR-access-chain-limited UL flow, against UEs with only one
     condition — additive = coincidental co-occurrence, supra-additive =
     a genuine interaction worth naming. It is deployable now; run it,
     record the result whichever way it comes out, don't skip it because
     it wasn't originally scoped as this WP's own test.
(iii) Flipping `README.md` §8's `[OPEN: PHASE2]` OLLA entry to
      `[RESOLVED]` with this commit's SHA, once landed.

### D3 — Tier-1 solver library

`scipy.optimize.linprog` (already an allowed dependency; no new one
needed) is sufficient for the small bounded LP (2 capacity rows + 1 soft
slack row per GBR flow). `cvxpy` (also allowed) is more legible for
expressing the weighted-log-utility SCA framing directly if that proves
easier to keep correct across iterations. Pick one when writing two-tier
commit 2; record the choice and rationale in the port-map row for that
mechanism — this is an implementation detail, not a fidelity question
(GLPK simplex and either scipy/cvxpy backend solve the same small LP to
the same optimum; the fidelity that matters is the SCA loop structure
around it, not the solver internals).

### D4 — Sequencing: reservation before two-tier

Reservation has zero existing Python (no unfaithful reference to
accidentally anchor on) and a structurally simpler mechanism — sort +
follower-budget + PF coefficient, no persistent cross-slot LP/VQ/floor
state machines. Its `n_followers=0` follower-budget-clamp-is-a-no-op
acceptance criterion (corrected scoping, §2.2 above — not a claim that
all of `Reservation` collapses to `PF`) gives an early, strong, fully
automatable falsifiable check, unlike anything two-tier's mechanism
offers this cheaply. Two-tier is harder (SCA/GLPK,
a UL-specific VQ ceiling formula that diverges from its own header, the
fruitless/ADQ floor state machine) but uniquely has a "wrong" existing
implementation to structurally diff against as a sanity check reservation
never gets (§4, two-tier commit 8's delta comparison). Net: build the
easier, previously-nonexistent one first to bank an early falsifiable
win; tackle the harder, comparison-anchored one second, once the
port-map/property-test/worked-trace discipline (§0) has been exercised
once already on the simpler case.

### D5 — `FlowConfig.mfbr_bps`, added scoping reservation commit 3

Reservation's GBR/BE target-spread caps at 2× a per-slot burst derived
from MFBR (`gbr_ul_max`/`gbr_dl_max`) — a value `scheduler/flow.py
::FlowConfig` had no field for at all before this commit. Added
`mfbr_bps: float = 0.0`, following the exact precedent
`effective_pbr_bps()` already sets for `pbr_bps`/`gfbr_bps`: `0.0` means
"not configured," and the cap then falls back to its own floor
(`2×obligation`) — matching the C's behavior when a QoS profile has no
MFBR set, not an invented default. Purely additive, safe default, every
existing `FlowConfig()` call and scenario unaffected; the same shape of
change WP7 already made repeatedly to this same dataclass.

### D6 — `SchedulerContextReset`/`reset_ue`: document, don't implement

Same disposition `docs/wp-join-plan.md` D8 reached for `PF`/`gradient`:
`Reservation`'s only per-UE state a join/re-join event could plausibly
leave stale is `_UeState.ul_thr_bytes_per_slot`/`dl_thr_bytes_per_slot`
(the throughput-EWMA coefficient denominator) — everything else
(`ul_lcg_deficit_bytes`, `dl_flow_deficit_bytes`, the `_grant_slot`
stamps, `ul_mcs_index`/`dl_mcs_index`) either re-derives fully from
current buffer/channel state every slot or is itself gated on real
backlog reappearing, with no "stale positive value biases a decision
after reconnection" failure mode the way an unreset EWMA would have.

The checkable arithmetic, run only after commit 10a's fix (before it,
this argument did not hold — see below): `_THR_EWMA_ALPHA = 0.01`, so
`thr` decays by a factor of `(1 - 0.01)^n` after `n` slots of the
now-blanket per-slot decay. At `n = 4000` (WP-Join's own GT-6-scale
citation: "a 2 s fade is 4000 slots at µ=1"): `0.99^4000 ≈ 3.47e-18`.
Applied to any realistic pre-outage `thr_bytes_per_slot` — even an
absurdly generous 10^9 bytes/slot, far beyond any real per-slot
throughput at this codebase's carrier bandwidths — the post-outage
residual is `~3.47e-9`, still many orders of magnitude below the
coefficient's own `max(thr, 1.0)` floor (`_allocate_direction`'s
`coef = hyp_tbs_bytes / max(thr, 1.0)`). So after a GT-6-scale outage,
`max(thr, 1.0)` evaluates to exactly `1.0` in double precision — bit-
for-bit identical to a freshly-configured UE's `max(0.0, 1.0)` — not
merely "small," genuinely indistinguishable from fresh. A `reset_ue` no-
op there is a checkable identity, not an untested assumption.

**This argument depends on commit 10a's fix and would NOT have held
before it.** Pre-10a, the decay was gated on candidacy (backlog>0 this
slot) — a UE masked to zero backlog for the whole outage (the exact
`JoinAwareBufferView` mechanism a real join/RLF event uses) would never
appear in `ue_flows`, so `thr_bytes_per_slot` would have been FROZEN,
not decayed, for the entire outage — the opposite of "decays to
negligible." Discovering this dependency while scoping this decision is
what surfaced 10a's bug in the first place (see commit 10a and
`docs/oai-port-map.md` row 14) — the two are not independent findings.

`Scheduler.configure`/`allocate` stay untouched; `Reservation` stays
fully protocol-conformant without implementing `SchedulerContextReset`,
the same additive-and-optional shape `two_tier.py`'s own implementation
already established (`scheduler/interfaces.py`'s docstring).

---

## 4. Commit checklist

### Reservation (new file — every commit before the capture commit must
be provably inert by construction: nothing in this branch calls a
scheduler named `"Reservation"` yet, the same "nothing imports it"
argument `docs/wp-join-plan.md` commit 1 used for `sim/join.py`)

| # | Commit | Predicted `--check` impact |
|---|---|---|
| 1 | Skeleton: `Scheduler` protocol conformance, per-UE/per-LCG state dataclasses, bare PF coefficient ranking, no follower budget (unbounded grant), UL-then-DL per-slot order (corrected — this row previously said DL-then-UL, which contradicted this document's own §2.2 citation of `gNB_scheduler.c:246,251`; caught scoping this commit). Port-map: `## Phase 2 — reservation` section opened. | Inert — zero call sites in any registered scenario/study. |
| 2 | **Three-tier-of-five** (UL) / **three-tier-of-four** (DL) sort — two independently-sourced comparators (`_ul_rank_key`/`_dl_rank_key`), never one shared function even though their tuples currently coincide in shape. **Scope correction, found scoping this commit, two gaps not one**: (a) ground truth's UL comparator is genuinely 5 tiers (SRB → liveness → GBR → `sched_inactive`-last → PDB/coef) and DL's is genuinely 4 (SRB → liveness(TA) → GBR → PDB/coef — DL has no `sched_inactive` field or tier at all, confirmed absent by reading `gNB_scheduler_dlsch.c:681-690` directly, not merely expressed differently); (b) UL's `liveness`/`sched_inactive` need a `do_sched`-equivalent (SR-or-inactivity trigger for a zero-backlog UE) and DL's `liveness` needs a TA-pending signal — neither reaches the `Scheduler` protocol today (`README.md` §8's broadened `[OPEN: PHASE2]` entry, one root cause, two missing signals); (c) `has_srb` — the TOP tier on both sides — has no data source of a different, more fundamental kind: this simulator has no SRB/RRC-signaling traffic model at all (`README.md` §8's second, separate `[OPEN: PHASE2]` entry), so it is hardcoded `False` structurally rather than approximated. Net effect: UL lands 3-of-5 tiers (SRB[no-op] → GBR[coarse] → PDB/coef), DL lands 3-of-4 (SRB[no-op] → GBR[coarse] → PDB/coef) — the only tier with real behavioral effect this commit is the coarse GBR flag (real deficit substance lands commit 3/5 without touching tier structure again). Also recorded: a hedged, not-asserted-as-fact reading of `gNB_scheduler_ulsch.c`'s own boolean relationship between `liveness` and `sched_inactive` suggesting T4 may never produce a decisive comparator result even in the real C — ported verbatim regardless, since faithful porting means replicating actual runtime behavior, not deciding for the C what it "should" do. Property tests: ordering matches the port-map table exactly on constructed multi-UE fixtures, one fixture per tier boundary so a wrong tier ORDER fails distinguishably from wrong tier CONTENT; plus a durable anti-dedup guard (`inspect.getsource`-based) asserting `_ul_rank_key`/`_dl_rank_key` stay textually and citationally distinct, so a future refactor can't quietly collapse them into one shared comparator just because they look identical today. | Inert. |
| 3 | GBR/BE byte split + deficit accumulate/cap/spread, both directions — landed. Replaces commit 2's coarse `has_gbr` proxy with the real per-LCG(UL)/per-flow(DL) deficit computation, without moving either comparator's tier position (`_ul_rank_key`/`_dl_rank_key` untouched). **A real, previously-unflagged asymmetry found reading the exact source, beyond the "identical formula" summary**: UL gates the *whole* per-LCG block (accumulation included) on `estimated_ul_buffer_per_lcg > 0` (`gNB_scheduler_ulsch.c:2230`) — a UL LCG's deficit freezes when its estimate reads 0; DL accumulates deficit and sets `has_unfulfilled_gbr` **unconditionally** for every GBR-configured LCID (`gNB_scheduler_dlsch.c:381-388`) — only the target/overflow sub-step gates on `bytes_queued > 0`. So a DL GBR flow's deficit keeps growing through silence; a UL one does not — the arithmetic is identical, when it runs is not. **Also fixes commit 2's `pdb_ms` bug**: it used HOL delay as a stand-in for "remaining PDB," but ground truth's `ul_best_remaining_pdb_ms`/`dl_best_remaining_pdb_ms` is time-since-last-grant (`:2239-2249`/`:358-367`) — a different quantity. No commit-2 test could have caught this: every fixture starts from "never granted," where both proxies coincide, so the tests were correct tests of the wrong general quantity. Last-grant-slot *stamping* lands here (needed for the fix); deficit *draining* on a grant stays commit 5's job, a different field the C updates in the same code block. `guaranteed_bytes`/`be_bytes` are computed and real but not yet consumed by grant sizing — see 4a below. | Inert — confirmed (23rd prediction). |
| 4 | **Landed.** Follower budget, both directions, their two genuinely different bases (UL: fixed `slot.prb_count`/`min_rb`, a deliberate operator-choice constant defaulting to 5, cited to the calibration campaign — not the config-parser default it numerically coincides with; DL: the *current* `prbs_left` at each candidate's turn/hardcoded `min_rbSize=5`). `needs_service` ported as the real formula (`_ul_needs_service`/`_dl_needs_service`) though structurally always-`True` today given the candidate pre-filter. **Automated property test: `n_followers=0` degenerates to unconstrained budget** — the acceptance criterion, checked directly, not eyeballed, and corrected in scope (§2.2, §7) from an earlier "reservation reduces to plain PF" overclaim. Port-map rows 27/28. | Inert — confirmed (26th prediction). |
| 3a | **Correction commit, added after commit 3 landed — its own commit, not an amendment, following the precedent commit 3 itself set for commit 2's `pdb_ms` bug.** Commit 3 ported the deficit block's right quantities in the wrong *type*: float ms where the C is integer throughout (grant age truncated to whole ms before subtraction, `window` truncating the ratio, `rem_slots` truncated then floored at 1, `target` an integer division, deficit stored as int). Load-bearing rather than cosmetic: `pdb_ms` is a comparator tier, so int-ms granularity makes UEs within one millisecond tie there and fall through to the PF coefficient — live on the corpus's own numerology for any odd slot count since a grant. Also lands the `pdb > 0 ? pdb : 300` fallback and the `9999` best-remaining sentinel, both found in the same read. **Checked and found symmetric across UL/DL** (all four truncation sites identical, including that both truncate the window's ratio not its product) — one shared port-map row 24, not a fifth asymmetry. Moved one existing commit-3 expectation (201 → 100), kept as evidence the correction is behavioural. | Inert at landing — same "nothing imports it" claim as commits 1-3; the arithmetic change was not itself neutral, and **commit 10 confirms it**: the corrected int-ms truncation is live in every captured Study 1-3 record now that the scheduler is wired in. |
| 4a | **Landed.** Wired `guaranteed_bytes + be_bytes` (commit 3's own output, previously computed but unconsumed) into grant *sizing* as the `nr_find_nb_rb`-equivalent target (`_ul_grant_target`/`_dl_grant_target`, pure functions; `gNB_scheduler_ulsch.c:2492-2512`/`_dlsch.c:1003-1019`), replacing backlog-only sizing. Also landed `gbr_bytes_slot` (`:2304-2316`, a MAX-not-sum, non-deduped, unfloored per-slot rate) and its own separate MFBR-keyed gate `_ul_has_pending_gbr` (`:38-67`) — found scoping this commit, not in the original plan text: `gbr_bytes_slot`'s whole loop is gated on `has_pending_gbr`, itself set by a *third*, independently-per-LCG-deduped scan keyed on `mfbr_bps` (MFBR), not `gfbr_bps`. D1/D2/D3 (§3) implemented as decided. See `docs/oai-port-map.md` rows 25/26 for full citations and the three structurally-unreachable sub-mechanisms this commit ports anyway (`gbr_bytes_slot`'s two independent dormancy reasons, the `B`-floor branch, and the permanent `has_srb` no-op) — each tested directly through the pure functions, not via a constructed scenario. | Inert — confirmed (25th prediction). |
| 5 | **Landed.** Deficit-drain: UL bug-for-bug (full `tb_size` credited per active LCG, comment vs. code quoted verbatim in `docs/oai-port-map.md` row 29); DL's genuinely-correct per-LC drain by actual delivered bytes (row 30) — confirmed directly against source, not inherited from this table. Also folds in two found-scoping-this-commit corrections to commit 3's own stamping, in opposite directions: UL was under-stamping/under-draining (iterated `c.flows`, gated on the crumb-gated `bytes_reported` view, instead of `self._flows` gated on the true `estimated_ul_buffer_per_lcg`); DL was over-stamping (iterated all of `c.flows` instead of only the flows `_dl_fill` actually gave bytes to). DL's stamp fix is live on `scenario_config_6.yml`'s UE 10 (two DL flows) once commit 10 wires this scheduler in — not purely hypothetical. | Inert — confirmed (27th prediction). |
| 6 | **Landed.** Real two-pass DL LCP (`docs/oai-port-map.md` row 31), replacing commit 1's priority-sorted placeholder (row 17). Confirmed genuinely two-pass (unlike two-tier's own single-pass-despite-comment DL LCP) but NOT priority-ordered within the DRB pass — "existing lc_config order," confirmed by reading the loop directly (the only `qsort` in the file is the inter-UE comparator). SRB pass recorded not-applicable (no SRB data model to gate on at all). `scheduler/flow.py`'s `FIVE_QI_PRIORITY` docstring corrected to scope its reordering-fragility rationale to UL only; `README.md` sec8 records the DL consequence. | Inert — confirmed (28th prediction). |
| 7 | **Landed by commit 4, confirmed doc-only here.** Re-read every `min_rb`/`min_grant_prb`/`min_rbSize` use site in both directions and diffed against what commit 4 (and commit 6) already ported: the follower-budget formula and the post-budget skip's `available_rb<min_rb` clause are both fully ported (`docs/oai-port-map.md` row 27/28). The skip's OTHER clause (`rbStart+min_rb>bwpSize`) is **provably redundant**, not merely unmodeled — the `available_rb` scan's own loop bound guarantees `rbStart+available_rb<=bwpSize` always, so `available_rb>=min_rb` already implies the first clause is false; commit 4's single-clause port is complete, not approximate. Two real gaps found and corrected in row 27: UL's own per-beam pre-check (`:2376`, never previously flagged — DL's twin at `:877` was already in row 28) and the missing citation for it. `min_rb`'s remaining use sites (`nr_find_nb_rb`'s PRB-search bound, `nr_ue_max_mcs_min_rb`'s power-shrink input) are independently out of scope already — the former is the real TBS-table search this whole codebase substitutes with `scheduler/link.py`'s staircase everywhere (D2's own decision), the latter is WP1's already-dormant `sim/power.py::shrink_to_power_budget`. No code change. | **A different kind of inert than every prior commit**: not "nothing imports Reservation" (still separately true) but "no code changed at all" — the 29th prediction is trivially inert, not scored against the usual mechanism. |
| 8 | **Landed.** MCS-selection call site (static staircase) — `docs/oai-port-map.md` row 32. Persistent per-UE-per-direction MCS index (`_UeState.ul_mcs_index`/`dl_mcs_index`), computed at candidate-build time matching the C's own per-candidate timing, via a new shared `scheduler/link.py::mcs_index_for_snr` (extracted from `_mcs_row_for_snr`'s existing one walk, not a second independent one — checked before writing). Not yet consumed anywhere. | **Doubly inert, for two independent reasons** (row 32's Divergence cell) — confirmed (30th prediction). |
| 9 | **Landed.** OLLA's grant-sizing consumption (D2(b)) — `docs/oai-port-map.md` row 33. Grant sizing (coefficient's hypothetical TBS AND the real grant's TBS — ground truth's `selected_mcs` feeds both, row 15) now reads `scheduler/link.py::bits_per_prb_for_mcs(mcs_index, symbols)` off commit 8's persisted index, closing commit 8's reason (2). **The ratchet itself is NOT wired in — a considered disposition, not a deferral.** Ground truth's `rounds[0]`/`[1]` are incremented by the SAME component that issues both new-tx and retry grants; WP5 Decision 4 moved retry-grant issuance to `sim/driver.py` alone, so round-1 telemetry never reaches `Scheduler.allocate()` here — structurally unobservable, not a missing protocol hook of the `do_sched`/TA kind. Given that, the offset from `mcs_index_for_snr(snr)` is provably 0 (not merely initialized at 0): `num_dl_sched` permanently 0 forces the C's own `num_dl_sched <= 3` branch every window, clamped at `min_mcs` from the first update. `_OLLA_OFFSET = 0`, cited to this reasoning, rather than a live call to `sim/olla.py::update_mcs_from_bler` against counters that can only ever read 0. Three ways to wire a live call anyway were considered (import `sim.olla` directly — breaks `reservation.py`'s own "never on sim" boundary, load-bearing for the UL intra-TB split citation; duplicate the primitives into `scheduler/link.py` — drift risk for code that cannot execute; move `sim/olla.py` into `scheduler/` — a diff spanning CLAUDE.md/README.md/`docs/wp5-plan.md`/`docs/oai-port-map.md` to relocate a module nothing calls) and none taken — the `sim`/`scheduler` boundary question is deferred, not resolved, until a real call site exists (`README.md` sec8 `[OPEN: WP9]`, retagged from `[OPEN: PHASE2]`). **The compounding-vs-coincidence test (D2, item ii) stays blocked** — it needs a live ratchet to produce the degradation being compared, which this commit deliberately does not build. **Applies identically to two-tier's own future OLLA commit** (a WP5-Decision-4 consequence, not reservation-specific) — both arms must land the same offset-pinned-at-zero disposition for a two-tier-vs-reservation comparison to measure a real scheduling difference rather than "one arm has OLLA." | **Existing assertions do NOT move** — `_OLLA_OFFSET == 0` makes the new call path numerically identical to commit 8's, proven directly (`test_bits_per_prb_for_mcs_matches_bits_per_prb_via_mcs_index_for_snr`) not just observed; confirmed by the full suite + `--check` running clean (31st prediction, and the first of this lineage to correctly predict NO assertions move rather than predicting some kind of movement). |
| 10 | **Landed.** Wired into `scripts/scheduler_study.py` and `scripts/regression_corpus.py` as a new arm across all three studies (`docs/oai-port-map.md` row 34) — one arm each, not just Study 1's minimum bar. Study 4 deliberately excluded (its N=2 scenario would reproduce the hardware campaign's own confound, `README.md` sec8 `[OPEN: WP9]`). Also added `scheduler.__init__`'s `Reservation` export and a `sim/tests/test_smoke.py` end-to-end driver run — the first time this scheduler executes outside its own synthetic fixtures. | **Landed exactly as predicted**: `--check` before wiring was clean; after wiring, before `--capture`, it reported exactly 6 "new case" mismatches (`study{1×4,2,3}/.../Reservation`) and zero diffs on any existing PF/RoundRobin/TwoTier record — the gate that would have stopped a `--capture` held clean, so capture proceeded. Verified at the JSON-key level (6 added, 0 removed, 0 of 22 existing records changed value) rather than by `git diff` line count, which shows large spurious churn purely from `sort_keys=True` reordering the file once new keys interleave alphabetically among existing ones. 32nd prediction in the lineage, and the first "net-new, zero drift" form rather than "nothing imports Reservation." |
| 10a | **Landed — a correction, not an amendment, following the precedent 3a set for 3's arithmetic.** The throughput-EWMA decay (`docs/oai-port-map.md` row 14) was gated on candidacy (backlog>0 this slot) since commit 1; ground truth gates it only on `nr_mac_ue_is_active()` (UL-failure/DRX, checked directly against `gNB_scheduler_primitives.c:3802` — nothing about backlog), decaying every connected UE every slot. Row 14 didn't merely omit this — it asserted the opposite as a deliberate, C-sourced design choice, contrasting favorably with `pf.py`'s blanket decay. Fixed to a standalone loop over every `_UeState`, gate treated as permanently open (no UL-failure/DRX signal exists on the `Scheduler` protocol — a structurally-absent input, same category as `has_srb`/`do_sched`/TA/OLLA telemetry). Found investigating commit 11's `reset_ue` argument, not by reading the C fresh — **the first bug in this port found by running the scheduler rather than by reading the source**, after nine commits of reading-based correction. | **Not inert — the first commit in this lineage where a re-capture legitimately changes existing numbers rather than adding them.** Predicted before running: exactly the 6 `Reservation` records change, zero diffs on any PF/RoundRobin/TwoTier record. Confirmed exactly: `--check` before capture reported 1601 field-level mismatches, all six confined to `study{1×4,2,3}/.../Reservation`, none elsewhere; JSON key diff after capture: 0 added, 0 removed, 6 changed. Full suite 466 passed (+1 guard test, verified to fail under the old gating before landing). Study 2's PF-comparison bimodal p99 split (README sec7) survives this fix nearly unchanged in shape and magnitude — the coefficient staleness was not the split's cause, ruling out one candidate explanation before its own investigation commit. |
| 11 | **Landed.** `SchedulerContextReset`/`reset_ue`: **document, don't implement** (D6 above) — `0.99^4000 ≈ 3.47e-18` after a GT-6-scale (4000-slot) outage, driving `max(thr, 1.0)` to exactly `1.0`, bit-for-bit identical to a fresh UE's floor. Argument depends on commit 10a's fix (pre-10a, the candidacy-gated decay would have FROZEN thr during the exact outage this argument is about, not decayed it) — found while scoping this row, not independently. Doc-only, closing the reservation half of Phase 2: also corrects three accumulated "once commit 10 wires this in" hedges to their now-confirmed status (`docs/oai-port-map.md` rows 29/30, this table's own row 3a and row 5's UE-10 note). | Inert (no code change to `reservation.py`; docs only). |

### Two-tier (rewrite in place — commit 1 is explicitly **not** inert; it
is the corpus-breaking commit, name it as such)

| # | Commit | Predicted `--check` impact |
|---|---|---|
| 1 | Skeleton replacing SPS/shadow-split entirely with LCG-aggregate ranking (D1) and no floor/VQ yet (plain PF-shaped fallback). | **Not inert.** All 16 existing TwoTier records move. `harq_masked_flow_double_grant_count` drops toward 0 immediately (no more UE-level SPS backlog pooling). `pdcch_cce_utilization` rises (SPS's zero-DCI grants disappear; CCE cost reappears on every UE). |
| 2 | Tier-1 SCA/GLPK solver at the corrected 0.1s-derived period (D3 for solver choice). | DL/UL target-rate responsiveness tightens (10× faster re-solve than the old 2000-slot/1.0s default) — predict which per-flow latency percentiles move, and in which direction, before capturing. |
| 3 | Windowed-ceiling VQ: DL arrival-delta (matches header) + UL's actual backlog-bound/catchup formula (does not match header — port the code). | UL-heavy scenarios' per-flow fairness/latency shift; DL comparatively stable (formula matches what stale-header intuition would already assume). |
| 4 | UL floor: fruitless-shift (16× cap, 500ms decay) + ADQ (8-grant trigger). Property tests: shift caps at exactly 4; ADQ fires at exactly 8, not 7 or 9. | Crumb-fraction metric and UL starvation-adjacent percentiles move; predict direction (starved UEs should show *improved* tail latency once floor logic is real, not absent). |
| 5 | DL LCP: single greedy DRB pass + SRB-exempt fill (the corrected, non-two-pass structure — see §6 Flags for the README correction this implies). | DL per-flow byte-fill patterns shift modestly; SRB-adjacent flows (if any in-corpus) most affected. |
| 6 | MCS-selection call site + OLLA follow-on (D2) — reuse the shared helper from reservation commits 8/9 if the staircase/ratchet wiring is scheduler-agnostic. | Per D2(i): predicted drift for `periodic_control`/`condition_monitor` flows, checked against actual output. Run D2(ii)'s compounding test; record result. |
| 7 | `reset_ue`/`SchedulerContextReset` — **required re-port**, not a copy-forward: the existing implementation (`two_tier.py:295-375`) resets VQ/deficit/demand fields whose names and structure change under commits 2-5 above. | Inert on its own (only fires on a join-event reconnection edge; no WP-Join scenario runs in the base corpus). |
| 8 | **Old-vs-new TwoTier delta comparison — its own commit, prerequisite to commit 9.** Run the pre-Phase-2 `two_tier.py` (checked out from git history) and the rewritten one side-by-side on the same seeds/scenarios; commit the full per-record delta table as `docs/phase2-two-tier-delta.md`. This is the last point the old numbers are directly comparable to the new ones outside git history. | N/A — a comparison artifact commit, not a code change; must land before commit 9. |
| 9 | Re-capture the 16 existing TwoTier regression records — the sanctioned re-baseline. Commit message states why the major movers moved (stale-2000-slot-default fix, real UL VQ formula, real DL LCP, SPS removal), citing commit 8's delta table rather than re-deriving the explanation. Verification must explicitly check `harq_masked_flow_double_grant_count == 0` across every corpus record for both schedulers. | Intended, documented `--capture` — not silencing an unexplained diff. |

### Ranked falsifiable predictions

Write and record predictions **inline, per commit, before running it** —
not retroactively at the end (`docs/wp-join-plan.md`'s own predictions
section was written after the fact and flagged as a process gap; don't
repeat that here). Minimum set already named above in the per-commit
tables (two-tier commits 1, 2, 4, 6); add to this subsection as each
commit lands, with actual-vs-predicted scored the way every prior WP's
"Update, WP4"/"Confirmed exactly"-style entries do.

---

## 5. `config/metric_panel.yml` — status moves

**None.** Checked against the file directly (all 19 rows): M01/M02/M03/
M05-M08/M10-M15/M17/M18 are already `status: ok`, computed directly from
`RunRecord`/`Allocation` fields both new schedulers continue to emit —
`is_sps` simply stops appearing (always `False`/absent post-SPS-removal).
M11 (`prb_utilization`)/M12 (`pdcch_cce_utilization`) will show real
*numeric* movement from losing SPS's zero-DCI/zero-grant-cost accounting
(see two-tier commit 1's prediction above), with **zero `status` change**
— a metric changing value is expected and fine; a metric changing
`status` without its `requires:` being satisfied would not be. M04/M09/
M16/M19 stay `proxy`; none of their `requires:` fields name Phase 2, the
scheduler, or anything this WP touches (WP7+timeseries, timeseries,
timeseries+named-flow-pair, WP-Join+timeseries respectively) — do not
promote any of them as a side effect of this work.

---

## 6. Flags

- **Two-tier's DL LCP is not actually two-pass; only reservation's is.**
  `README.md` §4/§7's "two-pass DL LCP" language currently describes
  both schedulers identically — confirmed wrong for two-tier (§2.1). Once
  this WP's rewrite lands, correct `README.md`'s Phase 2 table text to
  distinguish the two (cite the relevant port-map rows) rather than
  leaving the charter's simplification silently uncorrected.
- **`nrmac->min_grant_prb`'s assignment site is not present in any
  vendored file** — read-only everywhere it's used, but its origin
  (presumably RRC/config parsing elsewhere in the full OAI tree) isn't in
  `oai-branches/`. Not blocking — model as a fixed Python config scalar
  regardless — but flagged so a future session doesn't assume line 2055
  (an earlier, incorrect citation for this) is the assignment site.
- **Two real, ground-truth mechanisms found but not in README's original
  "must reproduce" list**: the C source's "Change 2" work-conserving UL
  fill pass (leftover PRBs offered to the highest-metric ungranted UE
  once per slot, `ia_p5g_scheduler.c:3368-3398+`) and the DL "FIX-2" GBR
  PRB reserve cross-cutting mechanism (`:3105-3124`). **Decided**: land
  the four named mechanisms first. When this rewrite lands, add both as
  new `[OPEN: PHASE2]` entries in `README.md` §8, citing these exact
  file:line ranges, so they're a tracked, explicit decision for later
  rather than something that silently evaporates or gets folded in
  unreviewed.
- **Retransmission-priority-pass: confirmed not a porting gap** — the
  driver's existing `harq_pool.due_this_slot()` / `HarqAwareBufferView`
  seam (`sim/driver.py:434,559-562`) already gives every scheduler the
  "retransmissions serviced first, never enter the new-data ranking"
  property OAI's C gets via inline priority. Recorded as a resolved
  non-finding, not left implicit.
- **D1's structural-isolation test is a new kind of check for this
  codebase's test suite** (asserting an *absence* of an import edge,
  not a behavior) — flagged so whoever writes it doesn't reach for a
  runtime behavioral test instead, which wouldn't catch the case D1 is
  actually guarding against (a future commit passing per-flow bytes into
  the scheduler through some other path).

---

## 7. Status

Reservation commits 1, 2, 3, 3a, 4a, 4, 5, 6, 7 and 8 landed; two-tier
not started. Two user decisions (D1, D2) obtained directly and recorded
above before any code, matching `docs/wp-join-plan.md`'s D0a/D0b
precedent. Sequencing (D4): reservation first, two-tier second.

4a landed ahead of commit 4 (follower budget) — the stronger sequence
argued for below turned out to be the one taken. `guaranteed_bytes`/
`be_bytes` fed grant sizing (`docs/oai-port-map.md` rows 25/26) before
commit 4's follower budget capped it (rows 27/28), avoiding the
"correct cap on the wrong quantity" failure shape commit 2's `pdb_ms`
bug and commit 3's float-vs-int one both had. Commit 5 lands the
post-grant deficit drain (rows 29/30), plus two corrections to commit
3's own stamping found scoping it, in opposite directions (UL under-
stamped, DL over-stamped). Commit 6 lands the real two-pass DL LCP
(row 31), replacing commit 1's priority-sorted placeholder (row 17) —
DL fill order turns out to be declaration order, not priority, a rule
the placeholder never had. Commit 7 turned out to be **doc-only**: every
`min_rb`/`min_grant_prb`/`min_rbSize` use site in both directions was
re-read and diffed against commits 4/6 — the follower budget and the
post-budget skip's live clause were already fully ported, the skip's
other clause is provably redundant (not merely unmodeled), and the two
real gaps found (UL's own beam pre-check, never previously flagged; the
missing redundancy proof) are now recorded in row 27. No code changed.
Commit 8 lands D2(a) — a persistent per-UE-per-direction MCS index
(row 32), the first commit to touch a file outside `reservation.py`/
its own tests/docs (`scheduler/link.py::mcs_index_for_snr`, shared
groundwork two-tier's own future commit will need identically).
**Doubly inert, not singly**: nothing imports `Reservation` yet (as
always), and separately the stored MCS index is written but read by
nothing this commit — verified directly (pre-seeding a nonsense index
before `allocate()` leaves the emitted grant byte-for-byte unchanged),
not just asserted.

Commit 9 (D2(b), row 33) removes the SECOND of those two reasons, not
the first, exactly as flagged: grant sizing now reads the persisted
index via a new `bits_per_prb_for_mcs`, verified the same way (a
monkeypatch-based guard, checked to fail under a simulated reversion).
**OLLA's own ratchet stays unwired, deliberately**: ground truth's
`rounds[0]`/`[1]` are populated by the same component that issues both
new-tx and retry grants, a symmetry WP5 Decision 4 breaks in this
simulator (retry grants never reach `Scheduler.allocate()`) — so the
offset from the instantaneous SNR pick is provably, not just currently,
0. Existing assertions do not move, the first correct "no movement"
prediction in this lineage (commits 2/3/3a/4a/5/6/8 all moved something
or landed genuinely inert; commit 7 landed no code at all). The
`sim`/`scheduler` boundary question this raises (how a live
`update_mcs_from_bler` call would ever get wired, given the package's
own "never on `sim`" rule) is recorded as deferred, not answered, in
`README.md` sec8's `[OPEN: WP9]` (retagged from `[OPEN: PHASE2]`) —
answering it now, for a call site that doesn't exist, would be deciding
on behalf of code that cannot execute.

**Commit 6, like commit 5, is not another "mostly dead" commit.** Its
core effect — draining the invented priority sort and using the real
declared-order fill instead — is fully live for any current or future
multi-DL-flow scenario, not gated behind a scenario construction that
doesn't exist. Its only dormant-category addition is the SRB pass,
which is **not applicable** (no SRB data model to gate a filter on at
all, same category as commit 4's DL beam pre-check) — bumping that
tally from one item to two, not adding a new dead branch under a new
cause. The MAC-subheader-overhead finding (row 31) is a real,
always-present, quantified bias on every DL grant with actual payload
(a directional over-delivery of roughly one subheader's worth per
SDU) — worth tracking, but it is neither dormant nor not-applicable,
so it is not counted in either tally below; it is simply a known,
small, live divergence.

**Commit 5 is not another instance of "mostly dead code," and stating
it that way would misrepresent it.** Unlike 4/4a's novel sub-mechanisms
(`gbr_bytes_slot`, the B-floor, the follower-budget `has_srb` init),
commit 5's *core* mechanism — draining a GBR flow's deficit by the
bytes just granted — is live for any ordinary single-flow-per-LCG(UL)/
per-flow(DL) GBR scenario already in this repo (e.g.
`scenario_config_6.yml`'s UE 10 has a GBR UL flow). Only two specific,
found-and-fixed **edge-case** bugs in commit 3's stamping are dormant
or partially so — see below. The running "more dead than live per
commit" observation does not extend cleanly to this one; it should not
be repeated by default without checking each future commit the same
way, not assumed to continue.

**Scoping honesty — recomputed from the current row set, not
hand-patched onto 4a's tally.** Every commit since 3 has widened this
port's structurally-unreached surface faster than its live one, and the
count must be redone from scratch each time rather than incrementally
patched, or it silently drifts stale exactly the way the checklist
summary this WP was warned not to trust already had. Two distinct
categories, kept separate per instruction — merging them into one
number would hide which kind of gap each is:

**Dormant but ported** (real code, faithfully built and tested,
currently unreachable given this repo's scenarios/signals) — **twelve
branches across six causes**:
- *Cause A — no SRB/RRC-signaling traffic model (`has_srb` always
  `False`), five branches*: the sort tier in both comparators (row 18,
  row 19); both control-only caps from 4a (row 25, row 26); UL's
  `max_rbSize` `has_srb`-gated init, new in commit 4 (row 27, test 5).
- *Cause B — no `do_sched`-equivalent protocol signal, two branches*:
  UL's `liveness`/`sched_inactive` tier (row 18); `needs_service`'s
  non-backlog terms, new in commit 4 (rows 27/28, test 6) —
  specifically the `or has_gbr` term, which never gets to matter
  because the candidate list's own backlog>0 pre-filter is itself what
  "no `do_sched`" forces (a UE the real C would admit via `do_sched`
  alone, at `B=0`, never reaches this port's candidate list at all).
  `needs_service`'s `or has_srb` sub-terms are separately dead for
  cause A's reason (has_srb's own value), already counted there, not
  double-counted here.
- *Cause C — no TA model, one branch*: DL's `liveness`(TA) tier (row
  19).
- *Cause D — `gbr_bytes_slot`'s own two independent dormancy reasons,
  one branch* (row 25): no scenario configures `mfbr_bps`, and every
  scenario is single-flow-per-LCG.
- *Cause E — the shared-LCG construction no scenario produces, two
  branches*: the `if (ul_target < B)` floor (row 25); UL's deficit-
  drain/stamp fix, new in commit 5 (row 29) — under-stamping/under-
  draining an LCG with a real estimate but a crumb-gated zero report
  is, structurally, the same shared-LCG gap H5 exists to close.
- *Cause F — no scenario configures two or more GBR-class DL flows on
  one UE, one branch, new in commit 5*: the DRAIN half of DL's stamp
  fix (row 30). **Not the same branch as the STAMP half** — see below,
  the stamp half is not dormant.

**Not applicable** (a different category — there is no signal here to
port at all, not a signal this port carries but can't currently
trigger) — **one item**: DL's per-beam pre-check (row 28) — no beam
modeling exists anywhere in `scheduler/`/`sim/`.

**Live, not dormant — worth stating separately since it cuts against
this section's usual direction.** DL's stamp fix (row 30) has a live
half: `_dl_gbr_and_pdb` folds `remaining_pdb` into `best_remaining_pdb`
for *every* DL flow of a UE regardless of `flow_class` (gated only on
`bytes_queued > 0`), so the fix shifts PDB-tier sort order for any
multi-DL-flow UE, GBR or not — `sim/scenarios/scenario_config_6.yml`'s
UE 10 already has two DL flows (qfi 9, qfi 82), and that scenario is
Study 1: **confirmed live in the commit-10/10a captured records** (both
flows show real delivered bytes there), not merely hypothetical anymore.
Recorded here rather
than folded into either count above, since it is neither dormant-but-
ported nor not-applicable — it is simply real, on an existing scenario,
today.

Only two of the six dormancy causes are unlocked, even partially, by
`README.md` §8's H5 follow-up scenario (two same-class UL flows forced
onto one `lcg`): cause E fully (both the B-floor branch and UL's drain
fix need nothing else), cause D partially (`gbr_bytes_slot` needs the
shared-LCG construction **plus** a nonzero `mfbr_bps`, so H5 alone is
necessary but not sufficient). Causes A, B, C, and F are unrelated to
H5 entirely — they need a SRB/RRC traffic model, a `do_sched`-
equivalent protocol signal, a TA model, and a GBR-class multi-DL-flow
scenario respectively, none of which the H5 construction fixes.

This is a scoping fact, not a defect: each branch was ported faithfully,
cited, and tested directly through the pure functions/methods rather
than left looking exercised — precisely because a mechanism this
simulator cannot currently trigger is exactly the case where silent
approximation is most tempting and least visible. But it is the single
most important input to what commit 10's study can honestly claim: what
it will actually *exercise* end-to-end is a meaningfully smaller port
than what has been written, and the regime map commit 10 feeds can only
speak to the part of this scheduler that current scenarios actually
run.

Standing fixture discipline, learned twice now: any new fixture must
include a post-grant state, and where timing is involved, an age that is
NOT a whole number of milliseconds. Both bugs so far survived a green
suite because every fixture sat exactly on the point where the wrong
implementation and the right one agree. 4a's own fixtures (`sim/tests/
test_reservation.py`) followed this for the two tests that needed a real
GBR magnitude to discriminate against a backlog-only implementation, and
additionally separated `estimated_ul_buffer_per_lcg` (high) from
`bytes_reported` (low) via explicit `_FakeBuffers` overrides rather than
letting one default from the other — the real crumb-collapse condition
D1 exists for, not an arbitrary small number chosen to make an assertion
pass.
