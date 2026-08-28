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

**UE ranking metric composition — corrected and completed at two-tier
commit 3, `docs/oai-port-map.md` rows 44-45; the paragraph below
originally described only the coefficient formula, not the comparator
each one sits inside, which turns out to be the more consequential
fact.** DL's coefficient itself is a pure VQ sum (`ia_p5g_dl_metric`,
`:1896-1923`, `Σ vq_dl × spectral_eff` over active LCIDs) — but it is
only the **final tiebreak** of a 3-tier lexicographic comparator,
`has_gbr → pdb_ms → coef` (`ia_p5g_dl_cmp`, `:1397-1411`), never
revised from the original form. UL's actual comparator metric is richer
than the header's documented `ia_p5g_ul_metric()` (a plain `Σ Q_g × SE`,
`ia_p5g_scheduler.h:391`) — the real `ia_p5g_pf_ul()` computes
`(base_q + W·Φ(u)·max(max_q,1)) × SE` inline (`:2860-2924`, constants
`:443-444,478-481,501`), where **`Φ` is a barrier function, not a plain
power law**: `Φ(u) = u^DELAY_EXP / (1 - min(u, URG_BARRIER_CAP) +
URG_BARRIER_EPS)`, diverging as `u → 1` (correction, two-tier commit
3a, `docs/oai-port-map.md` row 52 — this document's own prior text here
wrote the exponent form `urgency^EXP` without the barrier denominator,
which understates how sharply the term grows near a missed deadline).
`u` (`ue_worst_urgency01`) is itself a max over active LCGs of
`u_lcg × priority_weight × delta`, `delta` scaled by GBR deficit for
GBR flows and 1.0 otherwise. Port the inline composite, not the
documented stub. **But UL's comparator (`ia_p5g_ul_cmp`, `:2112-2125`) is not
DL's 3-tier form with a richer coefficient bolted on — it was
*deliberately revised away* from that exact form**, down to
`sched_inactive → coef` alone, and the C states the architectural
reason directly (`:2092-2111`, quoted in full in port-map row 45):
Tier-1's targets already encode the GBR guarantee, so Tier-2's own VQ
deficit on UL already carries it, and a separate `has_gbr` tier would
double-count it — the clearest statement of the two-tier scheduler's
own design found anywhere in this port. DL keeps its separate tier
only because DL's own coefficient never absorbed a GBR-carrying term
the way UL's composite did.

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
PHR power ceiling (`:3126-3163`). **The full uncapped-to-`available_rb`
sizing described in this paragraph, tied to the GBR-PRB-reserve
`two_tier.py` doesn't have any version of yet, is commit 4a's job, not
commit 4's** — commit 4 itself lands only the minimum sizing needed for
the floor to have any observable effect: a fixed `min_rb`-sized rescue
grant, matching v1's own disposition (a fixed-size grant regardless of
the corrupted demand estimate) rather than v2's fuller enhancement.

**Correction, two-tier commit 4: the comparator is THREE tiers, not
two.** `ia_p5g_ul_cmp` (`:2112-2156`) inserts `floor_fire` as **Tier
1.5**, between `sched_inactive` (Tier 1) and the composite coefficient
(Tier 2) — tie-broken on `floor_sil` (longer silence served first).
This directly contradicts the design-revision comment quoted above
("Revised form has exactly TWO tiers," `:2103-2110`) — a comment
accurate when *written*, overtaken by a *later* change to the code it
describes (the floor itself, added after that revision), not one of
this port's four OAI-inherited comment-vs-code mismatches nor the
self-inflicted `_dl_stamp` citation error — a third, distinct finding
category (`docs/oai-port-map.md` rows 45/56). **Not optional**: the C's
own comment (`:2122-2143`) states why the tier can't be deferred — a
floor-fired UE's composite reads ~0 by construction of the fault it
rescues (both `base_q` and `urgency01` are gated on the same corrupted
per-LCG estimate), so under Tier 2 alone the rescue would sort dead
last and never reach a grant. This is why the state machine and the
tier land in the same commit.

**`has_pending_gbr`** (the floor's own arming precondition, confirmed
in the full OAI checkout — `gNB_scheduler_ulsch.c:42-71`,
`update_ul_qos_priority`, not present in the vendored two-tier subset)
is a UE-level existence check — any LCG with CURRENT
`estimated_ul_buffer_per_lcg > 0` configured with `gbr_ul_max > 0`
(MFBR-keyed) — a simpler, different test from `_ul_gbr_and_pdb`'s
GFBR-keyed, deficit-accumulated `has_gbr`. The same function computes
`best_pending_pdb_ms` (theta's own PDB input): the highest-*priority*
currently-backlogged LCG's PDB, not literally "lowest PDB" despite the
C struct field's own inline comment, with its own 100ms fallback
(confirmed different from `_PDB_FALLBACK_MS`'s 300ms). **Flagged, not
resolved**: this gate reads the SAME per-LCG estimate the floor exists
to route around — if a UE's only GBR LCG is the one whose BSR has
desynced to 0, the floor never arms in exactly the fault it was built
to catch. Tested directly (`docs/oai-port-map.md` row 57); `README.md`
§7 states precisely which of two claims the test establishes (a
faithful port reproducing a real gap, vs. one reproducing something
real hardware additionally guards against that this simulator doesn't
model) — this port's first opportunity to find a bug in ground truth
itself, not in a port of it.

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
| 1 | **Landed.** Skeleton replacing SPS/shadow-split and the entire old Tier-1 apparatus (not just SPS/shadow-split — a VQ-less scheduler has nothing for a Tier-1 target to feed, restated scope, see commit's own message) with LCG-aggregate, UE-level ranking (D1) and no floor/VQ yet (plain PF-shaped fallback, explicitly NOT a ported mechanism — `docs/oai-port-map.md` row 35). Also fixed a real, live bug found verifying `gNB_scheduler.c:246,251` directly: the pre-rewrite file iterated `("DL","UL")`, the wrong order — corrected to UL-then-DL (row 38). Tagged pre-rewrite state as `phase2-pre-twotier-rewrite` (`dc1ab6a`). Deleted 24+6+1 tests whose mechanisms no longer exist (14 of the 24 in `test_smoke.py` permanently, with no successor — SPS entirely, plus the max-min/adaptive-penalty Tier-1 enhancements found to have no ground-truth citation, `README.md` §7); the rest restoration-mapped to specific future commits. Corrected the checklist's own figure while landing this: the corpus has **14** TwoTier-family records, not 16 (`regression/baseline_studies_1_3.json`, confirmed by reading the file directly) — 6 plain `TwoTier` (one per Study-1-mult/Study-2/Study-3) plus 8 `TwoTier-nomaxmin`/`TwoTier-adaptive` (Study 1 only, 4 mults × 2 variants), the latter no longer constructable once `gbr_maxmin`/`gbr_penalty_lr` are deleted kwargs — `scripts/scheduler_study.py`/`scripts/regression_corpus.py` edited to drop those two arms (Study 1: 5 scheduler arms → 3). Their pre-removal comparison is preserved in `docs/phase2-two-tier-delta.md` §1, captured before the arms were deleted. | **Not inert — confirmed exactly as predicted, precisely stated.** `--check`: 6 changed values (all plain `TwoTier`), 8 removed keys (the deleted variant arms), 0 added, 0 diffs on any PF/RoundRobin/Reservation record. `harq_masked_flow_double_grant_count` measured exactly 0 on all three regression-corpus scenarios for the new scheduler (SPS's backlog-pooling was the counter's only source — confirmed by direct measurement, not inferred). `cce_utilization` rose on 5 of 6 records; the sixth (`study1/overload_mult1.0`) moved −0.0001, resolved by direct instrumentation, not left unexplained: at this specific point, SPS was genuinely engaged (10/10 UEs held an SPS reservation, verified via a `phase2-pre-twotier-rewrite` worktree run), so the "removing the only zero-cost path raises CCE" mechanism is not inapplicable here — it held, but was offset by a second, correlated SPS-linked effect that also disappeared: the old scheduler wasted real (nonzero-CCE) *dynamic* grants that the driver then discarded as HARQ double-grants (`harq_masked_flow_double_grant_count`-adjacent — SPS's own non-destructive backlog pooling across a UE's SPS-eligible flows created dynamic-spillover races against an already-pending HARQ process). Measured directly (wrapping `scheduler.allocate()` and `Metrics.record_cce` separately in both the old worktree and the new run, not inferred): the old scheduler *emitted* 10,689 CCE-worth of grants but the driver only *applied* 10,370 — 319 CCE of scheduler effort was discarded as a double-grant, none of it real cost; the new scheduler's emitted and applied totals track much more closely (10,248 emitted vs. 10,355 applied, the small excess being ordinary HARQ-retransmission CCE, not double-grant waste, confirmed `harq_masked_flow_double_grant_count == 0` here). At this one heavily-overloaded operating point (GBR met only 1/10 pre-rewrite), the waste SPS's removal eliminated slightly outweighs the real dynamic-grant cost SPS's removal added, netting a near-zero, direction-flipped move — a second, verified mechanism dominating at the margin, not a failure of the first. Four confounded causes move the six surviving records (SPS removal, old-Tier-1 removal, the UL/DL ordering fix, the corrected blanket-decay EWMA form) — do not attribute any single observed metric movement to one cause alone from the aggregate `--check` numbers without a mechanism-isolated re-run; commits 2 onward will separate them naturally as each mechanism comes back individually. Full suite: 448 passed (440 + 8 new `test_two_tier.py` tests). |
| 2 | **Landed.** Tier-1 SCA/GLPK-equivalent solver (`scipy.optimize.linprog`, D3 resolved — mirrors the C's own per-iteration plain-LP structure, not a single convex solve) at the corrected `tier1_period_s=0.1 ÷ slot_duration_s`-derived period, read directly from `ia_p5g_sca_solve` (`ia_p5g_scheduler.c:974-1103`), not from this document's own §2.1 summary. Confirmed, not merely suspected: no lexicographic two-phase structure, no max-min pre-stage, no adaptive penalty, no slicing, no hard-floor override — five ungrounded pre-Phase-2 mechanisms, permanent loss (`docs/oai-port-map.md` rows 39-40). A sixth, `demand_estimator="oracle"`, was optimistic rather than merely uncited — ground truth's demand is always a windowed-arrival measurement (row 42), DL raw / UL EWMA-smoothed, never a read of a flow's true configured rate. `capacity_safety_factor` resolved as real but fixed (`IA_P5G_TIER1_OVERHEAD_FACTOR=0.80`, row 43) — mechanism restored, old sweepable-knob test not. Weight-on-utility corrected from flow-class-based to priority-threshold-based (row 41). A capacity-discretization fork (whole-slot vs. symbol-granular) decided explicitly, not silently, in favor of ground truth's stricter whole-slot form for Tier-1 specifically, leaving the existing `grid_capacity_prbsym_per_sec` untouched for its other callers. `get_full_dl_slots_per_period`/`get_full_ul_slots_per_period` found in the full OAI checkout (`config.c:313-347`), not merely inferred from naming, confirming the whole-slot reading deliberately, not by default. **A genuine algorithmic finding made writing this commit's own tests, not assumed going in**: the SCA loop does not always converge to a smooth interior optimum — two flows sharing one capacity row at equal SE with comparable weighted coefficients cause `linprog`'s vertex solutions to oscillate, never satisfying the convergence tolerance, so `MAXITERS=150` halts mid-oscillation at a fully deterministic but non-closed-form point (`docs/oai-port-map.md` row 39, `scheduler/tier1.py::solve_tier1`'s own docstring). 11 of 15 real `test_smoke.py` tier1.py-dependent tests are permanent loss (7 no-ground-truth + 2 max-min + 1 max-min-only utility + 1 solver-independence, whose premise — swappable CVXPY backends — no longer applies); 2 rewritten against the new formulation, 1 unaffected (false-positive grep hit), 1 contingent-resolved (capacity helper). `scheduler/tier1.py` was **not** orphaned the way commit 1's docstring assumed — still imported by `scheduler/__init__.py` and `scripts/knapsack_diagnostic.py`; the latter is left untouched but flagged (`README.md` §8's new `[OPEN: PHASE2]` entry) since it will now `ImportError` and its own docstring's claim underpins a live `paper/main.tex` section whose empirical basis this commit's own top finding undercuts — a durable, out-of-simulator consequence, not a drive-by fix. | **Predicted zero `--check` movement** (Tier-1's output is computed and stored but consumed by nothing until commit 3's VQ lands) — the opposite framing from commit 1's "not inert." **Confirmed exactly, verified against commit 1's own output directly (not the frozen — and still uncaptured — pre-Phase-2 baseline file, which would show unrelated commit-1-vs-original diffs)**: a `phase2-pre-twotier-rewrite`-adjacent worktree at two-tier commit 1 (`80609f5`) captured its own regression baseline to a scratch path; `--check` against that scratch baseline from this commit's own code reports `OK — no drift beyond rel_tol=1e-06, abs_tol=1e-09` across all 20 records. Full suite: 439 passed (was 448 at commit 1 — net −9 from 11 deletions + 2 new capacity tests). **Framing for this commit's own message and for commit 8's delta table** (stated explicitly, not left implicit): this commit deletes several hundred lines of capability, but the pre-Phase-2 implementation was not a rough approximation of the deployed scheduler — it was a more elaborate scheduler solving a different and easier problem (perfect future demand, free knobs, extra protective staging), and five of its mechanisms have no counterpart in the deployed code at all. A simplification toward fidelity, not a capability regression. |
| 3 | **Landed, retitled.** Originally scoped as "windowed-ceiling VQ" — split into this row (the GBR-deficit/PDB sort tiers) and a new row **3a** (the VQ itself) once reading `ia_p5g_dl_cmp` directly (`ia_p5g_scheduler.c:1397-1411`) showed DL's real comparator is `has_gbr → pdb_ms → coef`, not the pure-VQ-sum ranking this document's own §2.1 described — a user decision, `docs/oai-port-map.md` rows 44-45 carry the full finding. DL kept the original 3-tier lexicographic form; UL was *deliberately revised away* from it (design-revision comment, `:2092-2111`, quoted in row 45) to `sched_inactive → coef` alone, since Tier-1's targets already encode the GBR guarantee so the VQ deficit already carries it on UL — the clearest architectural statement of the two-tier design found in this port so far, now also corrected into §2.1 below. This row ports the shared GBR-deficit/PDB-remaining computation (confirmed byte-identical, by diff, to `reservation.py`'s own already-fixed `_dl_gbr_and_pdb`/`_ul_gbr_and_pdb` — reused directly, not re-derived, row 46) and wires `has_gbr`/`pdb_ms` as real DL sort tiers; UL's own deficit tracking is built but not yet a sort tier (feeds commit 3a's urgency term instead). Rows 4-9 below are **not** renumbered (reservation's own 3a/4a/10a precedent) — cross-references to "commit 7"/"commit 8" elsewhere stay valid. | **DL confirmed exactly** (real, ranking-affecting tiers move `--check` on any GBR/PDB-diverse scenario). **UL prediction (\"should not move\") was wrong** — 2 of 6 records show real UL movement (`ul_prb_utilization`, per-UE UL bytes) despite `_ul_rank_key`/reported SNR confirmed byte-identical to commit 2. Traced directly (worktree-instrumented, not inferred) to `sim/harq.py::HarqProcessPool.due_this_slot()`'s insertion-order-dependent shared iteration across every `(UE, direction)` pool (`docs/oai-port-map.md` row 48, new `CLAUDE.md` invariant) — a pre-existing simulator property, not a bug in this commit's own tier logic, but a genuine miss on the stated prediction, recorded as such rather than silently corrected. |
| 3a | **Landed.** Windowed-ceiling VQ: DL arrival-delta ceiling (matches header, `ia_p5g_update_vq_dl`) + UL's actual backlog-bound/catchup formula (does not match header — ported the code, `IA_P5G_VQ_UL_CATCHUP_N=5`, `ia_p5g_update_vq_ul`'s bugfix rationale transcribed in full, `docs/oai-port-map.md` row 51). UL's real composite coefficient — `(base_q + DELAY_URGENCY_W·Φ(u)·norm) × SE`, where **Φ is a barrier function** (`u^DELAY_EXP / (1 - min(u,CAP) + EPS)`, diverging as `u→1`), not the plain power law this document's own earlier text implied — replaces the bootstrap placeholder entirely as `_ul_rank_key`'s sole ranking term (row 52); DL's `Σvq_dl × SE` replaces the bootstrap placeholder as the *final tiebreak only* (row 49), since commit 3's `has_gbr`/`pdb_ms` tiers stay ahead of it. `_ul_gbr_and_pdb` extended to also return `worst_urgency01`, folding the priority-weighted urgency computation into its existing per-LCG loop rather than a second walk. **Checkable prediction carried from commit 3, scored here**: `test_ul_gbr_flow_held_near_gfbr_by_vq_alone_no_tier_assists` confirms a UL GBR flow wins real grants against a UE with a substantially better channel, through `_ul_rank_key`'s composite alone — row 45's architectural claim holds under an actual constructed check, not just a citation. **A real behavioral substitution found and flagged, not silently absorbed**: DL's drain (`ia_p5g_drain_vq_dl`) runs against `_dl_fill`'s placeholder split rather than the real LCP fill (`ia_p5g_compute_lcp_budget`, explicitly commit 5's job) — `vq_dl`'s own trajectory is therefore not expected to match ground truth until commit 5 lands, even though the drain arithmetic itself is faithful (`docs/oai-port-map.md` row 50). **A self-inflicted citation error found and fixed**: `_dl_stamp`'s own docstring (written in commit 3) cited unrelated PDU-padding code as the future drain hook — corrected (row 54), the first self-inflicted mismatch on this port's tally, distinct from the four inherited-from-OAI ones. | **Massive movement, as the formula-overhaul magnitude predicted**: `--check` against a commit-3 worktree baseline reports 1725 field-level mismatches across all 6 TwoTier regression records (all of study1's 4 mults + study2 + study3) — every record moved, both directions, unlike commit 3 where only DL was guaranteed. Attribution: (b) Tier-1's first real end-to-end exercise and (a) the VQ port itself are jointly responsible for essentially all of it — every UE's ranking coefficient in both directions changed formula entirely (not just gained a tiebreak tier the way commit 3's DL did), so these two sources cannot be cleanly separated from aggregate `--check` output alone, consistent with the forward note's own warning. (d) HARQ-iteration-order effects are a plausible contributor to the DL-driven UL movement specifically (per commit 3's own confirmed mechanism) but not separately isolated here, given (a)/(b) alone are sufficient to explain movement of this magnitude. (c) vertex-oscillation was not isolated as a distinct signature either — expected, since its effect (slot-to-slot variance for contested equal-SE pairs) is not something aggregate `--check` deltas alone can distinguish from ordinary VQ dynamics without per-slot tracing. `harq_masked_flow_double_grant_count` and every PF/RoundRobin record: confirmed **zero** movement, exactly as predicted (this commit is TwoTier-scoped only). Full suite: 449 passed (18 in `test_two_tier.py`, 3 tests retired outright — they exercised the now-deleted bootstrap EWMA/PF-coefficient mechanism directly, not adapted). |
| 4 | **Landed.** UL floor: the arm/fire state machine (delivery-history arming, `theta`, fruitless decay/shift, ADQ crumb-run/backoff, candidacy-rescue) plus **Tier 1.5** (`floor_fire`), a new comparator tier the design-revision comment quoted at commit 3 turned out not to describe (`docs/oai-port-map.md` rows 45/55/56 — a comment accurate when written, overtaken by a later change to the code, a third finding category distinct from this port's four OAI-inherited comment-vs-code mismatches and its one self-inflicted citation error). Checklist numbers reconciled against the C directly (this row's own prior text was accurate, confirmed rather than corrected): `FRUITLESS_SHIFT_MAX=4` and "16x cap" are the SAME fact; `FRUITLESS_DECAY_MS=500` exact; `ADQ_CRUMB_RUN=8` exact but necessary-not-sufficient (`adq_age>=adq_period` also required, a SECOND independently-capped backoff compounding on the already-shifted `theta_eff`). `has_pending_gbr` (the floor's own arming gate, confirmed in the full OAI checkout, `gNB_scheduler_ulsch.c:42-71`) found to read the SAME per-LCG estimate the floor exists to route around — ported faithfully, not "fixed," tested directly (row 57), outcome recorded in `README.md` §7 with the two possible claims kept distinct (a faithful port reproducing a real gap vs. one reproducing something real hardware additionally guards against). Grant-sizing split to commit 4a per user decision — this commit lands only a fixed `min_rb`-sized rescue grant (v1's own disposition), not v2's full uncapped-to-`available_rb` bypass. `cp_floor`/`reconfig_floor`/`srb_floor` (three separate, unrelated "floor" concepts) confirmed structurally absent, same disposition as `reservation.py`'s own `has_srb` — out of scope, not built (row 58). `min_rb` confirmed the same `mac->min_grant_prb` field `reservation.py`'s follower budget reads — new as a `TwoTier.__init__(min_rb: int = 5)` kwarg, `README.md` §8's `[OPEN: WP9]` entry updated (row 59). | **Predicted zero-or-small movement was a legitimate live possibility, stated before running, not after** — no in-corpus scenario constructs a real BSR/SR desync fault (the condition the floor exists to rescue). **Confirmed exactly**: `--check` against a commit-3a worktree baseline reports `OK — no drift` across all 20 records. A genuine negative result, not evidence of a broken port — the floor's own state machine is fully implementable and fully tested in isolation (property tests below), what's absent is the *fault*, a fourth dormancy category distinct from the three already on `README.md`'s record (`README.md` §7's own new entry). Full suite: 470 passed (31 new tests in `test_two_tier.py`, one pre-existing rank-key assertion updated for the new 4-tuple shape, `test_smoke.py`'s signature-drift guard updated for the new `min_rb` kwarg per its own standing instruction). **Correction, found scoping commit 4a: this fourth-category explanation was only HALF the reason, not stated as such at the time.** `_ul_has_pending_gbr`'s own MFBR gate means the floor would fail to arm even if a desync fault WERE constructed, since `mfbr_bps` is never configured on any flow in any scenario in this repo — and that second reason is not novel at all, it's this port's own existing category (2), "the signal exists but no scenario constructs the situation" (the identical shape `reservation.py`'s own `gbr_bytes_slot` dormancy already has). Both reasons are real and independent; see commit 4a's own row. |
| 4a | Grant-sizing bypass for a fired floor: the GBR-PRB-reserve cap (`gbr_below`, `:3105-3124`, "FIX-2" — the follower-budget-style cap commit 4's own placeholder comment already anticipated), the uncapped-to-`available_rb` sizing for `floor_fire` (replacing commit 4's fixed `min_rb` rescue grant), and the PHR-based PRB ceiling (`:3126-3163`, "FIX-D" — applies to every DATA-class grant, not just floor fires; likely structurally absent pending `sim/power.py`'s own dormant PHR machinery, to be confirmed when this commit is actually planned). Rows 5-9 not renumbered (reservation's own 3a/4a/10a precedent). | Not yet planned. |
| 4a | **Landed.** UL floor's grant-sizing bypass: FIX-2 (`gbr_below`, the GBR-PRB-reserve cap — a general anti-monopolization safeguard on every UL DATA-class grant, not floor-specific, `docs/oai-port-map.md` row 60) and the floor's own uncapped-to-`max_rbSize` sizing (row 62), replacing commit 4's fixed `min_rb` rescue grant. **Confirmed NOT the same shape as `reservation.py`'s own UL follower budget** — two real structural differences (baseline: remaining-PRB-count vs. static `bwp_size`; scope: GBR-specific vs. any-needy-follower), not a naming coincidence (row 60's own Divergence cell). PHR-based capping confirmed structurally out of scope entirely, same disposition `reservation.py`'s own commit 4a already recorded for the identical connection point (row 63). The `B_eff` deficit-accumulated grant-sizing target is deliberately NOT built here — named as its own commit, 4b, per user decision (row 64) — since `ul_total_target_bytes` is real and GFBR-exercised on this corpus, unlike everything actually built in this commit. | **Predicted zero movement, on two independent confirmed grounds, stated before running**: (1) the floor's own sizing change is gated on `floor_fire`, confirmed never to fire on this corpus (commit 4's own result); (2) `gbr_below`'s reserve is gated on `gbr_bytes_slot > 0`, which never fires either — `mfbr_bps` is never configured on any flow in any scenario in this repo, the identical fact `reservation.py`'s own already-landed `gbr_bytes_slot` found for the same quantity (`docs/oai-port-map.md` row 61). **Confirmed exactly**: `--check` against a commit-4 worktree baseline reports `OK — no drift` across all 20 records — every mechanism actually built in this commit is inert on the current corpus by construction, not by coincidence, a repeat of commit 4's own "predicted inert, confirmed inert" result on different (but related) grounds. Full suite: 476 passed (6 new tests). |
| 4b | **Landed.** `B_eff`, the deficit-accumulated UL grant-sizing target, wired into ordinary (non-floor-fired) DATA sizing (`docs/oai-port-map.md` row 64). **Row 46's own flag did not hold, confirmed by direct read**: `ul_total_target_bytes` is `_ul_gbr_and_pdb`'s own third accumulator, not `guaranteed_bytes + be_bytes`'s sum — the divergence is `be_bytes`'s own GBR-LCG overflow term, which `ul_total_target_bytes` excludes (row 65, this port's second self-inflicted finding, a new `CLAUDE.md` invariant). **`reservation.py`'s own `_ul_grant_target` confirmed NOT a template** — a genuine sum in a different C file, plus an extra `has_srb`-cap step two-tier's own `B_eff` lacks (row 66); D1 (PRB-vs-bytes sizing) transferred directly regardless. | **Predicted movement, and it moved — scored, not assumed.** `study1`/factory_robots (GBR): moved, the GFBR mechanism. `study2`/sensor_dense (0 GBR): also moved, confirmed traced to the non-GBR frozen-BSR mechanism specifically (`has_gbr` always `False` there), not assumed. `study3`/latency_bound (0 UL): zero movement, as predicted. Only `TwoTier` records moved. Full suite: 480 passed (4 new tests). |
| 5 | **Landed.** UL's post-grant served-split (`_ul_served_split`, `docs/oai-port-map.md` row 67) — a genuine greedy priority-order walk, neither `reservation.py`'s own full-credit bug nor a proportional split (`_ul_drain`, unaffected). Feeds a fix to commit 3's own `_ul_stamp` (row 68, a fourth "copied from reservation's pattern without checking two-tier's own C" instance) and UL's post-grant GBR-deficit drain, never built before this commit (row 69). DL: the real LCP fill (`ia_p5g_compute_lcp_budget`, priority ASC/vq_dl DESC — structurally almost identical to the commit-1 placeholder it replaces, only the tiebreak field changes) landed TOGETHER with DL's own deficit drain (row 70) — **not split the way reservation's fill/drain were**, decided from the C's actual shape: reservation's own fill fix was a large rewrite justifying a split, two-tier's is a one-field sort-key swap that doesn't need one. Both provably-redundant-guard drain simplifications (`max(0, deficit-x)` for the C's `if(deficit>0): -=; if(<0): =0`) stated, not hidden (row 69/70). Restored 3 of commit 1's own disposition-table tests (the 2 VQ windowed-ceiling tests, orphaned by the 3/3a split — see the process-finding note above the commit-9 row; `test_latency_bound_two_tier_protects_deadlines`, rewritten only for the `TwoTier()` constructor signature). | **Predicted both directions move (`factory_robots`/`sensor_dense` as UL candidates, `factory_robots`'s UE10 as a DL candidate) — scored, hits and misses both recorded, not assumed clean.** Actual: only `study1`/`factory_robots` moved (all 4 overload multipliers, 979 mismatches, all `TwoTier`; PF/RoundRobin/Reservation unchanged) — `sensor_dense`/`latency_bound` showed zero movement. Traced to source: `factory_robots`'s movement is 100% UL (UEs 8/9/10 each pair a GBR flow, always higher-priority, with a PF flow on a different LCG — row 69); DL contributed nothing anywhere in the corpus, confirmed on two independent grounds — no UE anywhere has two same-priority DL flows (so the fill's tiebreak never engages, including UE10, where the two flows' priorities genuinely differ — the specific DL prediction was wrong), and no DL flow in the corpus is GBR-class (so the drain never has anything to act on, row 70). `sensor_dense`'s predicted UL movement was also wrong, explained precisely: it has no UE with more than one active UL LCG, so the served-split provably reduces to the old single-LCG trivial case. Full suite: 493 passed (13 new tests, 3 restored). |
| 6 | **Landed.** MCS-selection call site (`docs/oai-port-map.md` row 72) + OLLA follow-on (row 73), landed as ONE commit — the shared-helper reuse row 6's own forward note anticipated is confirmed TRUE (`scheduler/link.py`'s functions are genuinely scheduler-agnostic, no new helper needed), the first of three checked forward-looking notes in this port to hold. `_OLLA_OFFSET = 0` confirmed independently against two-tier's own C (byte-identical `gNB_scheduler_primitives.c`, identical call-site gates, `rounds[]` increment sites live in two-tier's own `post_process_ulsch`/`_dlsch`) — the same disposition reservation's own commit 9 landed, not merely inherited by assumption. | **D2(i)/(ii)/(iii) blocked, for the identical reason reservation's own commit 9 already found — the D2 decision record's own checklist does not survive contact with ground truth, a second time.** No drift to predict (i); no live ratchet for the compounding test (ii); `README.md` §8's existing entry updated in place, not flipped to `[RESOLVED]` (iii). `--check` against a commit-5 worktree baseline: `OK — no drift`, predicted and proven directly (a staircase-boundary equivalence test, not sampled at midpoints) before running. |
| 7 | **Landed.** `reset_ue`/`SchedulerContextReset` (`docs/oai-port-map.md` rows 74/75) — the "required re-port" framing itself checked, not inherited: genuinely re-derived per field from the Protocol's own scope semantics (the field set now spans commits 1-6, not "2-5" as this row's own stale note said before this commit's doc pass). Reservation's own D6 ("document, don't implement") does NOT transfer — checked structurally: two-tier has no unconditional-per-slot mutator analogous to reservation's thr-EWMA, so state genuinely freezes during an outage rather than converging on its own. `"mac"` scope lands as a no-op regardless — every field independently justified (deficit/VQ explicitly Protocol-mandated; last-grant-slot and MCS index self-correcting; the 9 floor fields traced directly against the C, surviving an explicit challenge during planning). `"full"` scope replaces `_UeState()` wholesale and re-seeds `_arr_hist`/`_del_hist` from current cumulative counters. 6 of 7 commit-1-flagged tests restored; 1 retired (dead mechanism); 1 WP-Join test attempted, found empirically wrong, retired with the finding recorded (row 76). **Also confirmed, cheaply ahead of commit 8**: the pre-rewrite `scheduler/` package runs against current `sim/` unmodified (row 77) — commit 8's delta table will be a genuine live side-by-side. | **Both halves scored separately, as predicted**: inert on `--check` (`OK — no drift` against a commit-6 worktree baseline, confirmed — no WP-Join scenario runs in the base corpus) but NOT inert on the test suite (511 passed, up from 498 — 13 new/restored tests, 1 retired with a documented empirical finding rather than force-passed). |
| 8 | **Old-vs-new TwoTier delta comparison — its own commit, prerequisite to commit 9.** Run the pre-Phase-2 `two_tier.py` (checked out from git history) and the rewritten one side-by-side on the same seeds/scenarios; commit the full per-record delta table as `docs/phase2-two-tier-delta.md`. This is the last point the old numbers are directly comparable to the new ones outside git history. | N/A — a comparison artifact commit, not a code change; must land before commit 9. |
| 9 | Re-capture the 16 existing TwoTier regression records — the sanctioned re-baseline. Commit message states why the major movers moved (stale-2000-slot-default fix, real UL VQ formula, real DL LCP, SPS removal), citing commit 8's delta table rather than re-deriving the explanation. Verification must explicitly check `harq_masked_flow_double_grant_count == 0` across every corpus record for both schedulers. **Also verify every test commit 1's own disposition table marked restore-at-N was actually restored by the commit it names** — see the renumbering-orphaned-obligation note below, found scoping commit 5. | Intended, documented `--capture` — not silencing an unexplained diff. |

**A process finding, found scoping commit 5, not just a restoration**:
commit 1's own disposition table (its commit message, `80609f5`) mapped
two deleted `test_smoke.py` tests (`test_two_tier_virtual_queue_windowed_
ceiling`, `test_two_tier_windowed_ceiling_protects_bursty_gbr`) to
"commit 3" by name — VQ *was* commit 3's whole scope at the time that
table was written. When commit 3 itself split into commit 3 (the sort
tiers) and commit 3a (the VQ), the restoration obligation did not split
with it — neither commit restored the pair, and nothing caught the gap
until commit 5 re-read the original disposition table directly. **Commit
9's own closing check ("every test marked restore-at-N was actually
restored") would have passed the letter of that check while missing this
pair entirely**, since neither commit 3 nor 3a was ever the literal "N"
the table named after the split — the check as originally scoped has no
way to notice a renumbering moved the target out from under an
obligation written before the renumbering existed. **The lesson
generalizes, not a one-off**: when a commit splits, its own inherited
restoration obligations have to be re-mapped to the split's new numbers
explicitly, not left pointing at a number that no longer means what it
meant when the obligation was written — this document's own commit-9 row
above is amended to check for renumbering-orphaned entries specifically,
not just "was every named test restored." **Checked, not assumed, for
the other two splits in this port so far**: commit 1's own message
names no forward obligation pinned to a bare "commit 4" (its "3 to
commit 4-6/verified-at-9" entry was always a range, not a single number,
so the 4/4a/4b insertions — pure additions, never a reassignment of
scope already promised under the name "commit 4" — cannot have orphaned
it the way the bare "commit 3" reference was orphaned); commits 3 and 3a's
own messages were grepped directly for forward references to "commit 4"
and found none. **The VQ pair is the only orphaned obligation found in
this port to date, and this commit (5) closes it** (Test plan, below).

### Ranked falsifiable predictions

Write and record predictions **inline, per commit, before running it** —
not retroactively at the end (`docs/wp-join-plan.md`'s own predictions
section was written after the fact and flagged as a process gap; don't
repeat that here). Minimum set already named above in the per-commit
tables (two-tier commits 1, 2, 4, 6); add to this subsection as each
commit lands, with actual-vs-predicted scored the way every prior WP's
"Update, WP4"/"Confirmed exactly"-style entries do.

**Forward note for commit 3a (the VQ; renamed from a bare "commit 3"
once commit 3 itself split into the tiers, see that row above), written
at commit 3's own close, not retroactively**: commit 3a carries **four**
confounded sources of possible `--check` movement, not one, and should
predict with all four in mind rather than attributing every observed
diff to the VQ port by default — (1) the VQ port itself, the commit's
own nominal subject; (2) the first real end-to-end exercise of Tier-1's
SCA solve, since nothing consumes `_targets_bps` before commit 3a --
numerical behavior under load, convergence across up to 150 iterations,
and whether `scipy.optimize.linprog` behaves at the corpus's actual
scale the way small hand-picked unit-test cases suggest are all
genuinely untested until commit 3a runs it for real; (3) commit 2's own
found vertex-oscillation property (`docs/oai-port-map.md` row 39) — any
scenario with two same-direction, equal-(or near-equal-)SE flows and
comparable weighted coefficients competing for one Tier-1 capacity row
will not converge to a smooth target split, landing instead at whatever
the 150-iteration damped oscillation produces; if that split now feeds a
VQ ceiling, an unexpected `--check` diff could be this, not a VQ bug;
(4) **new, found at commit 3 itself**: `sim/harq.py::HarqProcessPool.
due_this_slot()`'s shared, insertion-order-dependent iteration
(`docs/oai-port-map.md` row 48, `CLAUDE.md`'s new invariant) — commit 3
already confirmed a DL-only change can move UL numbers through this
pre-existing simulator property with zero UL logic involved, so commit
3a's own DL-vs-UL changes (now landing simultaneously, not staggered
the way commit 3's DL-only change was) should expect this mechanism to
contribute too, on top of the other three. Disentangling which of the
four explains a given movement may need the same kind of
mechanism-isolated re-run this session used for commit 1's own
`cce_utilization` anomaly and commit 3's own UL-movement finding
(worktree-based old-vs-new instrumentation),
not an assumption either way.

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

Reservation commits 1, 2, 3, 3a, 4a, 4, 5, 6, 7, 8, 9, 10, 10a and 11
landed — reservation's Phase 2 port is complete. Two-tier commits 1
(the corpus-breaking skeleton), 2 (Tier-1 SCA/GLPK-equivalent solve),
3 (the GBR-deficit/PDB-remaining sort tiers), 3a (the windowed-ceiling
VQ, replacing the bootstrap PF coefficient in both directions), 4 (the
UL service-interval floor's state machine plus the new Tier 1.5
comparator slot it requires), 4a (the floor's grant-sizing bypass,
FIX-2 plus the real uncapped-to-`max_rbSize` sizing), 4b (`B_eff`, the
deficit-accumulated UL grant-sizing target), 5 (UL's post-grant
served-split/stamp-fix/deficit-drain, DL's real LCP fill plus its own
deficit drain), 6 (MCS-selection call site + OLLA follow-on, D2), and 7
(`reset_ue`/`SchedulerContextReset`) have now landed — see this table's
own row 1/row 2/row 3/row 3a/row 4/row 4a/row 4b/row 5/row 6/row 7
entries above for what each did and confirmed; commits 8-9 not started.
Two user decisions (D1, D2) obtained directly and recorded
above before any code, matching
`docs/wp-join-plan.md`'s D0a/D0b precedent. Sequencing (D4): reservation
first, two-tier second.

Commit 2 confirmed, not merely restated, five of the checklist's
inherited-summary claims by reading `ia_p5g_sca_solve` directly rather
than trusting `docs/phase2-plan.md`'s own §2.1: the max-min pre-stage,
the adaptive dual-ascent penalty, and (two findings new to commit 2, not
previously flagged even in commit 1's own scoping pass) network slicing
and a hard-floor override are all confirmed to have zero ground-truth
citation, not merely "none found yet." A sixth mechanism,
`demand_estimator="oracle"`, turned out to be a different class of
problem — optimistic, not merely uncited (`README.md` §7). The commit
also found a genuine algorithmic property of the SCA loop itself (vertex-
oscillating, non-smooth convergence for contested equal-SE flow pairs,
`docs/oai-port-map.md` row 39) that neither this document's own summary
nor the deleted pre-Phase-2 Python's design anticipated, and flagged a
consequence reaching outside the simulator entirely — `paper/main.tex`'s
knapsack-claim section rests on a mechanism (the lexicographic two-phase
form) ground truth never had (`README.md` §8's new `[OPEN: PHASE2]`
entry). Predicted and confirmed exactly: zero `--check` movement,
verified against commit 1's own output directly via a scratch-baseline
worktree capture, since Tier-1's target rates are computed and stored
but consumed by nothing until commit 3a's VQ lands.

Commit 3 itself began as a routine question — does the VQ prepend to
`_rank_key` or replace it — and reading `ia_p5g_dl_cmp` directly to
answer it found DL's real comparator is a 3-tier lexicographic
structure (`has_gbr → pdb_ms → coef`) this document's own §2.1 never
stated, and that UL's comparator was *deliberately revised away* from
that same form for a documented architectural reason (Tier-1's targets
already carry the GBR guarantee into Tier-2's VQ deficit on UL, so a
separate tier would double-count it) — the clearest statement of the
two-tier scheduler's own design found in this port to date, now folded
into §2.1 itself rather than left standing next to source that
contradicted it. The user's decision split the originally-single
"commit 3 = VQ" scope into this commit (the tiers) and a new commit 3a
(the VQ), landing the tiers first since they are the *higher*-precedence
terms in DL's real comparator and the VQ is only ever a tiebreak there —
before this split, a VQ landing under nothing could not have
demonstrated its own mechanism working. The underlying GBR-deficit/PDB
computation is confirmed byte-identical, by direct diff, to
`reservation.py`'s own already-fixed `_dl_gbr_and_pdb`/`_ul_gbr_and_pdb`
— reused directly rather than re-derived, closing that research question
before it could reopen bugs reservation's own port already found and
fixed. The `"unchanged from original pf_ul()"` comment was checked, not
trusted, and — a first for this port's five comment-vs-code checks —
confirmed correct for what it specifically describes, though narrower in
scope than the block it sits in.

**Predicted DL-only movement; confirmed DL moved, but UL moved too, on 2
of 6 records — a real miss on the stated prediction, investigated
directly rather than absorbed as noise.** Traced (not inferred) to
`sim/harq.py::HarqProcessPool.due_this_slot()`'s shared, insertion-
order-dependent iteration across every `(UE, direction)` pool — a
DL-only grant-timing change can shift which UL UE's retransmission
draws first from the shared `harq_rng_ul` stream, with zero change to UL
scheduling logic itself (`_ul_rank_key` and reported SNR confirmed
byte-identical at the point checked). A genuine, now-documented property
of this simulator's own pre-existing infrastructure (`CLAUDE.md`'s new
invariant, `docs/oai-port-map.md` row 48) — not a bug in this commit,
but a real cross-direction sensitivity distinct from (and a sibling of)
the already-documented `pf.py::_r_avg` finding, flagged forward as a
fourth confounded risk source for commit 3a.

**Commit 3a landed the VQ itself — growth, ceiling, drain, and the real
ranking coefficients, finally replacing the bootstrap PF coefficient
every ranking decision had used since commit 1.** Re-reading
`ia_p5g_update_vq_ul`/`ia_p5g_ul_metric`/the composite-coefficient
formation block directly (rather than trusting the "urgency^delay_exp"
shorthand carried in commit 3's own forward note) surfaced two things
this document had not previously stated precisely: UL's urgency term is
a **barrier function** (`Φ(u) = u^DELAY_EXP / (1 - min(u,CAP) + EPS)`,
diverging as `u → 1`), not a plain power law, and UL's own `ia_p5g_ul_
metric` function receives a `spectral_eff` parameter it never uses —
the *caller* multiplies SE in once, after adding urgency, unlike DL's
internal multiply. A genuine behavioral substitution was found and
flagged, not silently absorbed: DL's drain runs against `_dl_fill`'s
still-placeholder split rather than the real LCP fill, so `vq_dl`'s own
trajectory will not match ground truth until commit 5 lands — recorded
as its own port-map Divergence row and folded into commit 5's own
checklist entry now, while the reasoning was fresh, rather than
rediscovered there. Commit 3's own stated expectation (a UL GBR flow
protected by the VQ deficit alone, no sort tier assisting) was scored
directly with a constructed test, not left as a citation — it holds.
`--check` showed the largest movement of any commit in this port
(1725 field-level mismatches across all 6 TwoTier records, every
record, both directions) — expected, since this is the first commit
where every UE's ranking coefficient in both directions changed formula
entirely, not merely gained a tiebreak tier; (a) the VQ port and (b)
Tier-1's first real end-to-end exercise are jointly responsible and not
separable from aggregate `--check` output alone, consistent with the
forward note's own warning about confounded sources. `harq_masked_flow_
double_grant_count` and every PF/RoundRobin record stayed at exactly
zero movement, confirming the change stayed TwoTier-scoped.

**Commit 4 landed the UL floor's arm/fire state machine and a new
comparator tier it structurally requires — Tier 1.5 (`floor_fire`),
between `sched_inactive` and the composite coefficient.** The checklist
row's own "fruitless-shift (16x cap, 500ms decay) + ADQ (8-grant
trigger)" phrase turned out accurate on every number checked directly
against the C (the "16x cap" and "shift caps at 4" are the same fact,
not disagreeing ones; `ADQ_CRUMB_RUN=8` is necessary but not sufficient
— a second, independently-capped backoff also gates it) — the real
under-description was of *scope*, not numbers: this is a full
persistent-per-UE state machine with a real 2026-08-04 production
incident behind it (v1→v2 revision history included), not the compact
mechanism the row's own phrasing implied. **The biggest single finding**:
the design-revision comment commit 3 quoted in full ("Revised form has
exactly TWO tiers") sits immediately above comparator code implementing
three — a comment accurate when *written*, overtaken by a *later*
change to the code it describes, a third finding category on this
port's tally distinct from the four OAI-inherited comment-vs-code
mismatches and the one self-inflicted `_dl_stamp` citation. The tier
can't be deferred to a later commit either: the C's own comment states
why directly (a floor-fired UE's composite reads ~0 by construction of
the fault it rescues, so without the tier the rescue sorts dead last
under Tier 2 and never reaches a grant) — this is why the state machine
and the tier landed together, per the user's own scope decision.
**A genuinely new opportunity for this port**: `has_pending_gbr` (the
floor's own arming gate, confirmed only in the full OAI checkout) reads
the SAME per-LCG estimate the floor exists to route around — ported
faithfully rather than "fixed," and tested directly. This is this
port's first chance to find a bug in ground truth itself rather than in
a port of it or in this repo's own Python; the test result is recorded
in `README.md` §7 with the two distinguishable claims kept separate (a
faithful port reproducing a real gap, vs. one reproducing something
real hardware additionally guards against that this simulator cannot
model). Grant-sizing (the GBR-PRB-reserve cap, the floor's own
uncapped-to-`available_rb` sizing, the PHR ceiling) split to commit 4a
per user decision — this commit's own sizing change is the minimum
needed for the floor to have any observable effect at all (a fixed
`min_rb`-sized rescue grant, matching v1's own disposition), not that
fuller bypass. `cp_floor`/`reconfig_floor`/`srb_floor` (three separate,
unrelated "floor" concepts) confirmed structurally absent, same
disposition as `reservation.py`'s own `has_srb` tier.
**`--check` reported `OK — no drift`** against a commit-3a worktree
baseline — predicted as a legitimate live possibility before running
(no in-corpus scenario constructs a real BSR/SR desync fault), not
retrofitted as an excuse after seeing the number. This is a **fourth
dormancy category**, distinct from the three already on `README.md`'s
record: the floor's every input is real, the state machine runs every
slot and is fully tested in isolation, and what's missing is the fault
itself — a radio-link failure mode, not a missing signal or an
unconstructed scenario. **Correction, found scoping commit 4a: this was
only HALF the explanation, not the whole one.** `_ul_has_pending_gbr`'s
own MFBR gate means the floor would fail to arm even if a desync fault
WERE constructed, since `mfbr_bps` is never configured anywhere in this
repo — and that second reason is NOT novel, it's this port's own
existing category (2), the identical shape `reservation.py`'s own
`gbr_bytes_slot` dormancy already has. `README.md` §7's own entry now
states both reasons, not just the novel one, and names what would close
each independently; `README.md` §10 also flags the consequence for
commit 10's own study — the mechanism most specific to two-tier's own
design, born from a documented production incident, currently
unexercised by any scenario in the regime map. Full suite: 470 passed
(31 new tests, one pre-existing rank-key assertion updated for the
4-tuple key shape, the `min_rb`-kwarg signature-drift guard updated per
its own standing instruction).

**Commit 4a landed the UL floor's grant-sizing bypass: FIX-2 (the
GBR-PRB-reserve cap, `gbr_below`) and the floor's own uncapped-to-
`max_rbSize` sizing, replacing commit 4's fixed `min_rb` rescue
grant.** FIX-2 turned out to be a *general* anti-monopolization
safeguard on every UL DATA-class grant, not floor-specific machinery
the floor merely also respects — its own motivating incident (a
saturating UE locking out a different UE's unmet GBR guarantee) is
independent of the floor entirely. **Confirmed NOT the same shape as
`reservation.py`'s own UL follower budget**, on two real structural
grounds checked directly, not assumed from the shared "PRB reserve"
framing: the baseline it reserves against (this slot's actual remaining
PRB count, vs. reservation's static `bwp_size` — its own docstring
warns against exactly the running-budget quantity two-tier uses), and
its scope (GBR-specific here, any-needy-follower there). **`gbr_below`'s
own reverse-scan condition depends on `gbr_bytes_slot` — confirmed
already ported once, in `reservation.py`'s own commit 4a, and its own
already-documented finding transfers directly: `mfbr_bps` is never
configured on any flow in any scenario in this repo** (confirmed
directly this commit, not assumed inherited). So both mechanisms built
in commit 4a are structurally inert on the current corpus, exactly as
predicted before running on two independent grounds (the floor never
fires; `gbr_below` never counts anything) — `--check` against a
commit-4 worktree baseline: `OK — no drift`, confirmed exactly, a
second "predicted inert, confirmed inert" result in a row on related
but distinct grounds. PHR-based capping confirmed structurally out of
scope entirely, the identical disposition `reservation.py`'s own commit
4a already recorded for the identical connection point — checked
directly rather than assumed to transfer. The `B_eff` deficit-
accumulated grant-sizing target — real, GFBR-exercised, and NOT
confirmed inert — is deliberately not built here, named as its own
future commit (4b) per user decision, with the stale "No GBR-PRB-
reserve/follower budget yet (commit 4a)" comment in `two_tier.py`'s own
grant-sizing loop corrected to point at it rather than left to go stale
a second time. Full suite: 476 passed (6 new tests).

**Commit 4b landed `B_eff`, the deficit-accumulated UL grant-sizing
target, wiring it into ordinary (non-floor-fired) DATA sizing in place
of plain `ue_backlog`.** Two findings, both confirmed by direct read
before writing any code, not assumed from the similar naming or the
similar-looking already-landed reservation mechanism: **(1) row 46's
own forward-looking flag was wrong** — `ul_total_target_bytes` is
`_ul_gbr_and_pdb`'s own THIRD accumulator in the same per-LCG loop,
not `guaranteed_bytes + be_bytes`'s sum; the divergence is specifically
`be_bytes`'s own GBR-LCG overflow term (a GBR flow's live backlog
exceeding its per-slot target), which `ul_total_target_bytes` excludes
(`docs/oai-port-map.md` row 65). This is this port's **second
self-inflicted finding**, distinct in kind from `_dl_stamp`'s stale
citation at commit 3a — a citation points at something readable and
pointed at the wrong lines; row 46's note asserted something about a
consumption not yet written, and was wrong about that. A new `CLAUDE.md`
invariant now generalizes across both: a forward-looking note in this
port's own docs is a hypothesis for the commit that takes it up to
verify, not an instruction to execute unchecked. **(2) `reservation.py`'s
own already-landed `_ul_grant_target` is confirmed NOT a template** —
a third instance of "a similar-looking mechanism differs structurally,"
after FIX-2's own two divergences at commit 4a (row 60). Reservation's
real ground truth lives in a different C file with a genuine sum
(no separate accumulator) and an extra `has_srb`-cap step two-tier's
own `B_eff` block lacks (row 66). D1 (reservation's own sizing decision
— the target sizes PRBs, not delivered bytes) transferred directly, the
one piece of the template that did. **This is the first commit since
3a predicted to move `--check`, and it did — scored, not assumed
clean.** Worktree-verified against a commit-4a (`1d2a714`) baseline:
`study1`/factory_robots (10 GBR UL flows) moved substantially, the
GFBR-driven mechanism predicted; `study2`/sensor_dense (30 UL flows,
0 GBR) also moved, confirmed by direct trace to the non-GBR mechanism
specifically — `has_gbr` is always `False` there (`scenario_config_4.yml`:
every UL flow is `flow_class: Delay`), so the only route left is
`ul_total_target_bytes`'s frozen-between-BSRs per-LCG contribution
exceeding `ue_backlog`'s BSR-independent-drain scalar, confirming the
frozen-BSR mechanism live through a scheduler path (a real finding for
WP9's own UL-sizing reasoning), not folded into "GBR flows only" by
default; `study3`/latency_bound (0 UL flows) showed zero movement,
exactly as predicted, nothing to size. Only `TwoTier`-prefixed records
moved — PF/RoundRobin/Reservation records stayed bit-for-bit identical,
confirming the change stayed scheduler-scoped. Full suite: 480 passed
(4 new tests, 3 existing call sites updated for `_ul_gbr_and_pdb`'s
new 7-tuple return).

**Commit 5 landed the post-grant GBR-deficit drain, in both directions,
plus the real DL LCP fill — closing commit 3a's own "joint VQ-correction
commit" flag.** Neither direction's deficit had ever been drained
before this commit (confirmed by grep — one write site each: commit 3's
own accumulation, plus commit 4's floor-forgiveness reset on UL). Three
genuinely different "who gets how much of this TB" computations were
found to coexist in this file, read end to end rather than assumed from
the deficit-drain lines alone: UL's already-landed VQ drain (commit 3a,
proportional-by-share); UL's NEW served-split (this commit, a genuine
greedy priority-order walk — neither `reservation.py`'s own drain, which
credits the FULL `tb_size` to every active LCG and is a documented bug
in reservation's own C, nor a proportional split); and DL's real fill
(structurally almost identical to the commit-1 placeholder it replaces —
the only change is the tiebreak field, `-bytes_queued` to `-vq_dl`).
**A real bug found in the CURRENT port, a correction to already-landed
commit 3**: `_ul_stamp` stamped every active LCG, copied from
`reservation.py`'s own gate — correct there (reservation credits every
active LCG regardless of priority), wrong here (two-tier's own greedy
walk means an unserved LCG should not be stamped, and was). No test
named `_ul_stamp` directly before this commit, so four commits (3, 3a,
4, 4a) passed with the gap unexercised — a fourth instance of "a
mechanism copied from reservation's pattern without checking two-tier's
own, structurally different C," fixed with a guard test verified to
actually fail under the reverted code before landing.

**Fill and drain landed together, one commit, NOT split the way
reservation's were (its commits 5/6) — decided from the C's actual
shape, not the checklist row's.** Reservation split because its own
fill fix was a large rewrite (a genuine two-pass SRB/DRB loop replacing
a placeholder of an entirely different shape); two-tier's fill fix is a
one-field sort-key swap on a placeholder that already had the right
structure, so the coupling argument that justified reservation's split
does not transfer.

**`--check` scored precisely, hits and misses both recorded — see the
checklist row's own outcome cell above for the full trace.** In brief:
predicted both directions move; only `study1`/`factory_robots` actually
moved (UEs 8/9/10's paired GBR+PF UL flows on different LCGs, under
the overload sweep), 100% attributable to UL — DL's own new machinery
(fill reorder, deficit drain) is confirmed structurally inert across
the ENTIRE corpus on two independent grounds (no same-priority DL-flow
UE anywhere, so the fill's tiebreak never engages even at the one
candidate UE10 the prediction named; zero DL GBR flows anywhere, so
the drain has nothing to act on). `sensor_dense`'s predicted UL
movement was also wrong, explained precisely: no UE there has more
than one active UL LCG, so the served-split provably reduces to the
old single-LCG trivial case. Also closed a process finding from this
same commit: commit 1's own disposition table mapped 2 VQ-ceiling
tests to "commit 3" by name, orphaned when commit 3 split into 3/3a —
restored here (rewritten against the real per-flow ceiling formula,
not the old flat `_virtual_q` structure), alongside
`test_latency_bound_two_tier_protects_deadlines` (restored essentially
as-is, only the constructor signature changed). Full suite: 493 passed
(13 new tests, 3 restored).

**Commit 6 landed MCS-selection + OLLA follow-on (D2), one commit not
two — unlike reservation's own commits 8/9, decided because the
uncertainty that justified reservation's split (whether the ratchet
would prove reachable) is already resolved before this commit starts.**
A persistent per-UE-per-direction MCS index now drives grant sizing via
`scheduler/link.py::mcs_index_for_snr`/`bits_per_prb_for_mcs` — the
SAME free module functions reservation's own commit 8 already made
scheduler-agnostic, confirmed by direct read this commit rather than
assumed from row 6's own forward note ("reuse the shared helper... if
scheduler-agnostic"). **That note is confirmed TRUE — the first of
three checked forward-looking notes in this port to hold, not a
pattern of failure.** Two prior ones (`_dl_stamp`'s stale citation at
commit 3a; port-map row 46's "reused directly" claim at commit 4b) were
wrong; this one wasn't. The invariant is "verify before executing,"
and its evidence is that checking is cheap and the outcome isn't
predictable in advance — not that such notes are unreliable. Three
checked, one held.

**The hard constraint this commit carries and no prior two-tier commit
has had — whatever disposition lands must MATCH reservation's, or a
comparison would measure link adaptation instead of scheduling
policy — is satisfied, confirmed independently rather than assumed
transferred.** `oai-branches/two-tier/gNB_scheduler_primitives.c` is
byte-identical to reservation's copy (`diff`, confirmed this commit);
`ia_p5g_scheduler.c`'s own DL/UL blocks have the identical
`bo->harq_round_max == 1` call-site gate; the `rounds[]` increment
sites live in two-tier's own `post_process_ulsch`/`_dlsch` (already
fully read and ported at commit 5), structurally identical to
reservation's. Since WP5 Decision 4 (retries never reach
`Scheduler.allocate()`) is a simulator-architecture fact, not a
scheduler-specific one, the identical gap applies — `_OLLA_OFFSET = 0`
here for the same reason, not merely because reservation's is.

**D2(i)/(ii)/(iii) are blocked here for the identical reason
reservation's own commit 9 already found — the D2 decision record's
own checklist does not survive contact with ground truth, a second
time.** No drift to predict for `periodic_control`/`condition_monitor`
flows (i) — the offset is 0 regardless of flow kind. No live ratchet
to run the compounding-vs-coincidence test against (ii). `README.md`
§8's existing OLLA entry updated in place to confirm two-tier hit the
identical wall (iii) — not flipped to `[RESOLVED]`, matching
reservation's own retag-to-`[OPEN: WP9]` disposition rather than D2's
original plan.

**Predicted and proven directly, not just observed via `--check`
staying clean: zero movement.** The numeric equivalence the whole
prediction rests on (`bits_per_prb_for_mcs(mcs_index_for_snr(snr), symbols)
== bits_per_prb(snr, symbols)` at offset 0) was swept across every
staircase threshold and just above each one, not sampled at a few
midpoints — a boundary is where a two-path lookup would diverge if it
does at all. `--check` against a commit-5 worktree baseline: `OK — no
drift`, confirmed exactly. Full suite: 498 passed (5 new tests).

**Commit 7 landed `reset_ue`/`SchedulerContextReset`, checking commit 1's
own "required re-port" framing rather than inheriting it.** The field
set had grown to 17 `_UeState` fields across five mechanisms since that
note was written, several with no pre-rewrite counterpart at all.
**Reservation's own D6 ("document, don't implement") does NOT
transfer** — checked structurally, not assumed inert by precedent: D6's
whole argument rests on `reservation.py`'s thr-EWMA decaying
unconditionally every slot regardless of backlog (commit 10a's own fix);
two-tier has no analogous unconditional-per-slot mutator for any of its
17 fields — every one is written only from within the same
backlog-gated candidate-build loop `JoinAwareBufferView` masking
excludes a reconnecting UE from, so state genuinely freezes during an
outage rather than converging on its own.

**`"mac"` scope lands as a no-op regardless — every field independently
justified, not assumed inert by default.** `ul_lcg_deficit_bytes`/
`dl_flow_deficit_bytes`/`vq_dl`/`vq_ul`: kept, per the Protocol
docstring's own "accumulated GBR deficit, demand belief... left alone"
text. `*_last_grant_slot`: kept, the same "no failure mode" shape D6's
own text already found for reservation's analogous `_grant_slot`
stamps. `ul_mcs_index`/`dl_mcs_index`: no memory-based bias either way,
pure function of current SNR. **The 9 floor fields — kept, traced
directly against `ia_p5g_scheduler.c:2306-2530`, surviving an explicit
challenge during this commit's own planning** (a reviewer's "B>0
re-arms regardless of the liveness clock" objection) — checked
precisely against the C and found the challenge itself incomplete: the
C's own `B>0` branch clears `floor_disarmed`/`floor_fruitless` but does
NOT set `armed`, giving a second, independent self-correcting path for
the RLF-recovery case the challenge raised, making it better covered
than either the original derivation or the challenge anticipated. `"full"`
scope replaces `_UeState()` wholesale and re-seeds (not clears)
`_arr_hist`/`_del_hist` from current cumulative counters — the same
"trap found while implementing this method" the pre-rewrite
implementation's own test already caught.

**Commit 1's disposition table, 6 `test_join_reset.py` tests + 1
WP-Join test, outcomes recorded precisely, not uniformly "restored."**
5 of 6 restore cleanly; `test_reset_ue_full_scope_resets_ul_shadow_bucket`
is retired (dead mechanism, `CLAUDE.md`'s own standing invariant against
reintroducing the UL intra-TB estimators). **The WP-Join test was
attempted, ran, and failed — investigated directly, not force-passed.**
Commit 3's own argument for why it would transfer checked out true on
both counts it made, and the outcome was still wrong: instrumented
directly, `vq_dl` for this scenario's own GBR flow reads exactly `0.0`
throughout, not just at reconnection — the windowed-ceiling clamp never
registers a deficit for a flow whose GFBR target is continuously met,
confirmed not a mechanism bug against `factory_robots_scenario`'s own
four-to-five-digit `vq_dl`/`vq_ul` values under real contention. Retired
with the finding and a concrete next step recorded (`docs/oai-port-map.md`
row 76), not left as a bare "retired."

**Confirmed, cheaply, ahead of commit 8**: the pre-rewrite `scheduler/`
package (not just `two_tier.py` — `tier1.py` is its own matched pair,
rewritten wholesale at commit 2) runs against CURRENT `sim/` unmodified,
non-degenerate output on all three regression-corpus scenarios
(`docs/oai-port-map.md` row 77, exact worktree procedure recorded
there). Commit 8's delta table will be a genuine live side-by-side, not
archived numbers.

`--check` against a commit-6 worktree baseline: `OK — no drift`,
confirmed exactly — inert on `--check` as predicted (no WP-Join scenario
in the base corpus), but NOT inert on the test suite (511 passed, up
from 498).

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
