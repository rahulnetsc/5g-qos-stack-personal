"""Two-tier 5G QoS scheduler -- rewritten from ``oai-branches/two-tier/``.

Phase 2 (``docs/phase2-plan.md``): unlike ``reservation.py``, this is a
rewrite of a scheduler that already had 1148 lines of pre-Phase-2 Python
and was wired into the regression corpus and ~65 test functions across
three files. The pre-rewrite file is preserved at git tag
``phase2-pre-twotier-rewrite`` (``dc1ab6a``) -- commit 8 diffs against it
directly. See ``docs/oai-port-map.md``'s "Phase 2 -- two-tier" section for
the file:line correspondence and ``docs/phase2-plan.md`` sec4 for the
full checklist.

This commit (1) is explicitly **not inert** -- unlike reservation's own
commit 1, this immediately changes the behavior of a scheduler already
exercised by the regression corpus and the wider test suite. It deletes,
outright, two mechanisms confirmed absent from real hardware
(``docs/phase2-plan.md`` sec2.1): SPS/Configured-Grant (``_SPSReservation``,
``_allocate_sps``, ``_is_sps_eligible``, and everything that fed them) and
the UL intra-TB per-flow byte-split estimators (``_shadow_lcp_split``/
``_occupancy_split``/``_estimate_ul_split``) that modeled something the
real gNB structurally cannot observe. It also drops, for now, the entire
old Tier-1 LP apparatus (``_resolve_tier1``, the "measured"/"tracking"
demand estimators, the adaptive dual-ascent GBR penalty, the max-min GBR
pre-stage) -- not because those specific pieces are this commit's job,
but because a VQ-less scheduler (see below) has nothing for a Tier-1
target rate to feed. Two of those Tier-1 pieces do not come back at all:
see ``README.md`` sec7's new bullet -- the adaptive penalty
(``gbr_penalty_lr``) and the max-min pre-stage (``gbr_maxmin``) have no
citation in ``docs/phase2-plan.md`` sec2.1's ground truth (which
describes only a *fixed*-constant soft-slack penalty,
``IA_P5G_TIER1_GBR_PENALTY = 1.0e3``) and were already a documented
negative result (``design-docs/scheduler-study.md`` sec8.4) before this
commit removed them from the live scheduler.

Explicitly NOT here yet, each landing in its own later commit: the
PHR-based PRB ceiling (structurally out of scope entirely -- not
merely deferred, see commit 4a's own module-docstring section below),
and a re-port of ``reset_ue``/``SchedulerContextReset`` against the new
field layout (commit 7) -- this class implements no ``reset_ue`` at all
until then; ``sim/driver.py`` discovers it via ``getattr(scheduler,
"reset_ue", None)``, so its absence simply means TwoTier is treated
like PF (no context reset) in the interim, not an oversight.

**Commit 6 (this commit) lands MCS-selection call site + OLLA
follow-on (D2), one commit not two -- unlike ``reservation.py``'s own
commits 8/9, which split BECAUSE landing commit 8 didn't yet know
whether the ratchet would prove reachable. That uncertainty is already
resolved by the time this commit starts (see below), so there is
nothing left to stage across two commits.** A persistent per-UE-
per-direction MCS index (``_UeState.ul_mcs_index``/``dl_mcs_index``)
now drives grant sizing, via ``scheduler/link.py``'s already-shared
``mcs_index_for_snr``/``bits_per_prb_for_mcs`` -- confirmed genuinely
scheduler-agnostic this commit (free module functions, no
``reservation.py`` coupling), not assumed from ``docs/phase2-plan.md``
row 6's own forward note.

**This commit carries a hard constraint no prior two-tier commit has
had: whatever disposition lands must MATCH ``reservation.py``'s, or a
two-tier-vs-reservation comparison would measure link adaptation
instead of scheduling policy.** ``reservation.py``'s own commit 9
proved its OLLA offset is 0 -- ``get_mcs_from_bler``'s own trigger
(``NR_mac_dir_stats_t.rounds[0]``/``[1]``) is incremented at grant-
finalization by the SAME component that issues both new-tx and retry
grants, a symmetry WP5 Decision 4 breaks (retries never reach
``Scheduler.allocate()``). **Confirmed here, independently, against
two-tier's own C, not merely cited from reservation's identical
finding**: ``oai-branches/two-tier/gNB_scheduler_primitives.c`` is
byte-identical to reservation's copy (``get_mcs_from_bler`` is the
literal same function); two-tier's own ``ia_p5g_scheduler.c`` has the
identical ``bo->harq_round_max == 1`` call-site gate at both its DL
(``:1526-1536``) and UL (``:2540-2552``) blocks; the ``rounds[]``
increment sites (``UE->mac_stats.ul.rounds[cur_harq->round]++``/
``.dl.rounds[harq->round]++``) live in two-tier's OWN ``post_process_
ulsch``/``_dlsch`` (``gNB_scheduler_ulsch.c:2724``, already fully read
and ported at commit 5; ``_dlsch.c:1168``). Since WP5 Decision 4 is a
simulator-architecture fact, not a scheduler-specific one, the
identical gap applies: ``_OLLA_OFFSET = 0`` here for the same reason,
not merely because reservation's is.

**D2(i)/(ii)/(iii) are blocked here for the identical reason
reservation's own commit 9 already found -- the D2 decision record's
own checklist does not survive contact with ground truth, a second
time.** D2(i) (predict drift for ``periodic_control``/
``condition_monitor`` flows) has nothing to predict -- the offset is 0
regardless of flow kind. D2(ii) (the compounding-vs-coincidence test)
needs a live ratchet to produce the degradation it compares; none
exists. D2(iii) (flip ``README.md`` sec8's OLLA entry to
``[RESOLVED]``) -- reservation's own commit 9 retagged it
``[OPEN: PHASE2]`` to ``[OPEN: WP9]`` instead (the ``sim``/``scheduler``
boundary question stays open, deferred until a live call site exists);
same disposition here, the existing entry updated in place rather than
flipped or duplicated.

**The below-lowest-MCS-threshold viability gate stays keyed on the raw
SNR walk (``bits_per_prb``), not the persisted MCS index** --
``mcs_index_for_snr`` floors at index 0 rather than signaling "no
viable MCS" (its own documented convention: a persisted field must
always be a concrete int), so routing the gate through it would
silently make an arbitrarily-low-SNR UE look transmittable. Same
disposition ``reservation.py``'s own commit 9 already landed.

**Row 6's own "reuse the shared helper... if scheduler-agnostic"
forward note held under check -- the first of three checked in this
port to hold, not a pattern of failure.** `_dl_stamp`'s stale citation
(commit 3a) and port-map row 46's "reused directly" claim (commit 4b)
were both wrong; this one wasn't. The invariant is "verify before
executing," not "such notes are unreliable" -- checking is cheap and
the outcome isn't predictable in advance, which is exactly why all
three needed checking regardless of how the first two turned out.

**Predicted, and confirmed by direct proof, not just by ``--check``
staying clean: zero movement, the same shape as reservation's own
commit 9 (its first correctly-predicted-inert result in that
lineage).** `bits_per_prb_for_mcs(mcs_index_for_snr(snr), symbols)` is
numerically identical to `bits_per_prb(snr, symbols)` at every point on
the staircase when `_OLLA_OFFSET == 0` -- proven by a dedicated
boundary-by-boundary test (every threshold, and just below each one),
not sampled at a few midpoints, since a boundary is exactly where a
two-path lookup would diverge if it does at all.

**Commit 5 (already landed) lands the post-grant GBR-deficit drain, in
both directions, plus the real DL LCP fill -- closing the "joint
VQ-correction commit" 3a's own docstring flagged.** Neither direction's
deficit (``ul_lcg_deficit_bytes``/``dl_flow_deficit_bytes``) had ever
been drained before this commit -- confirmed by grep, one write site
each (commit 3's own accumulation step; UL also has the floor's own
forgiveness reset, commit 4).

**UL and DL are NOT the same mechanism wearing two names -- three
genuinely different "who gets how much of this TB" computations exist
in this file, read end to end (not just the deficit-drain lines) to
confirm this.** (1) UL's VQ drain (``_ul_drain``, ``ia_p5g_drain_vq_ul``,
commit 3a): proportional split of the FULL raw ``tb_size`` by BSR-buffer
share -- unaffected by this commit. (2) UL's NEW mechanism, this
commit's own job (``post_process_ulsch``, ``gNB_scheduler_ulsch.c:
2756-2802``): a genuine greedy priority-order walk (``_ul_served_
split``) -- neither ``reservation.py``'s own drain (which credits the
FULL ``tb_size`` to every active LCG, ``CLAUDE.md``'s "port the code not
the comment" rule, a documented bug in reservation's own C) nor a
proportional split. Two-tier's own C comment (``:2743-2746``) names
that exact bug as "the old bug" and this walk as its fix -- **the two
OAI branches' C genuinely differ here, not a porting error on either
side.** (3) DL's real fill (``ia_p5g_compute_lcp_budget``,
``ia_p5g_scheduler.c:1945-2000``): sort DRBs ``(priority ASC, vq_dl
DESC)``, greedy ``min(backlog, remaining)`` -- structurally almost
identical to the placeholder it replaces (same sort-then-greedy shape,
the ONLY change is the tiebreak field, ``-bytes_queued`` to
``-vq_dl``). DL's own deficit drain lives INSIDE this same fill loop in
the C (``gNB_scheduler_dlsch.c:1417-1427``), draining by the real
``lcid_bytes`` each flow got -- the same gate ``_dl_stamp`` already got
right via ``_dl_fill``'s own ``fills`` list since commit 3a.

**A real bug found in the CURRENT port, a correction to already-landed
commit 3, not new-mechanism scoping.** ``_ul_stamp`` stamped every LCG
with ``estimated_ul_buffer_per_lcg > 0``, copied from
``reservation.py::_ul_drain_and_stamp``'s own gate -- **correct there**
(reservation credits every active LCG the full TB regardless of
priority, so "active" and "served" coincide trivially), **wrong here**
(two-tier's own greedy walk means a small TB with 2+ active LCGs only
serves the highest-priority one(s); a lower-priority active LCG was
stamped by this port's prior code but is NOT stamped in the C,
inflating its apparent freshness and shrinking ``_ul_gbr_and_pdb``'s
``remaining_pdb`` incorrectly). No test named ``_ul_stamp`` or
referenced ``ul_lcg_last_grant_slot`` directly before this commit --
exercised only indirectly through ``_ul_gbr_and_pdb``'s own
consumption, so four commits (3, 3a, 4, 4a) passed with this gap
unexercised. **This is what makes the category dangerous -- a pattern
correct where it was copied FROM, wrong where it landed, with nothing
built to notice**: the fourth instance of "a mechanism copied from
reservation's own pattern without checking two-tier's own,
structurally different C" (after FIX-2 vs. follower budget, ``B_eff``
vs. ``_ul_grant_target``, and now this). Fixed here as part of building
the real served-list; the guard test is verified to actually fail
under the reverted (pre-fix) code before landing, the same standard
``docs/oai-port-map.md`` rows 29/30's own discriminating tests are
held to.

**Diffed against reservation's own already-landed commits 5/6, as this
port's standing discipline requires.** UL diverges (row 29's bug is
reservation-only, per point (2) above). DL's own drain arithmetic
genuinely MATCHES reservation's (row 30: stamp and drain update
together off one value, in one conditional block -- confirmed true of
two-tier's C too). But reservation SPLIT fill (its commit 6) from drain
(its commit 5) because ITS OWN fill fix was a large rewrite (a genuine
two-pass SRB/DRB loop replacing a placeholder of an entirely different
shape, row 31). **Two-tier's own fill fix is not that -- a one-field
sort-key swap on a placeholder that already had the right structure.
The coupling argument that justified reservation's split does not
transfer; this commit lands fill and drain together**, matching
``docs/phase2-plan.md`` row 5's own "joint commit" framing rather than
reservation's split precedent -- decided from the C's actual shape, not
from the checklist row.

**Both provably-redundant-guard simplifications, stated not hidden**:
the C's ``if (deficit>0): -=; if(<0): =0`` drain form reduces to an
unconditional ``max(0, deficit - served_or_delivered)`` in both
directions, since deficit is provably never negative anywhere else it's
written (accumulation and, on UL, the floor's own forgiveness reset,
both floor at 0) -- same category as ``docs/oai-port-map.md`` row 27's
reservation finding, not a silent simplification.

**A process finding, recorded here and in ``docs/phase2-plan.md`` next
to the commit-9 checklist: commit 1's own disposition table mapped two
now-restored tests (the VQ windowed-ceiling pair) to "commit 3" by
name, written when VQ WAS commit 3's whole scope -- when commit 3 split
into 3 and 3a, that obligation did not split with it, and neither
commit restored the pair until this one.** Generalizes: a commit split
has to re-map its own inherited restoration obligations explicitly, not
leave them pointing at a number that no longer means what it meant when
written. Checked, not assumed, that no other split (4/4a/4b) orphaned
anything else -- see the doc for the full check.

**Commit 4b (already landed) lands `B_eff`, the deficit-accumulated UL
grant-sizing target, replacing `ue_backlog`-only sizing for ordinary
(non-floor-fired) DATA UEs.** Ground truth (`ia_p5g_scheduler.c:3195-
3204`): `ul_target = ul_total_target_bytes; if ul_target < B: ul_target
= B; if has_gbr and gbr_bytes_slot > 0: ul_target = max(ul_target,
gbr_bytes_slot); B_eff = ul_target` -- computed independently of
commit 4a's own `max_rbSize`/`available_rb` (the two combine only at
the sizing step: `max_rbSize` bounds the PRB search space, `B_eff` is
the byte demand searched for within it -- confirmed no reordering
needed, `max_rbSize` already computed first in this file's own loop).
Floor-fire sizing is untouched -- it bypasses `B_eff` entirely, per
ground truth.

**`ul_total_target_bytes` does NOT equal `guaranteed_bytes + be_bytes`
-- confirmed by reading both accumulations side by side in the same
per-LCG loop, not assumed from the similar naming. This is a real,
self-inflicted finding: commit 3's own port-map row 46 said these
values would be "reused directly here, not re-derived" once a future
commit took up this consumption -- checked here, not executed
unchecked, and found wrong.** For a GBR LCG, both accumulate the same
capped `target` -- no divergence there. For a non-GBR LCG, both
accumulate the same raw `estimated_ul_buffer_per_lcg` -- no divergence
there either. **The divergence is specifically the GBR-LCG overflow
term**: `be_bytes` additionally accumulates `overflow = lcg_estimate -
target` when a GBR flow's current backlog exceeds its computed target
this slot; `ul_total_target_bytes` does NOT include this term at all --
only the capped `target` counts toward it. `ul_total_target_bytes` is
therefore its own, third accumulator inside `_ul_gbr_and_pdb`'s
existing loop (matching the established "extend the existing loop"
precedent from `worst_urgency01`/`gbr_bytes_slot`), not a sum of the
two return values already there.

**This is this port's SECOND self-inflicted finding, distinct in kind
from `_dl_stamp`'s own (commit 3a's stale citation).** `_dl_stamp`'s
was a wrong *citation* -- a citation points at something readable, and
it pointed at the wrong lines. Row 46's was a wrong *plan* -- forward
guidance for a consumption not yet verified, written before the
quantities involved had actually been compared. A plan asserts
something about code not yet written; a citation points at code that
already exists to be checked. Both wrong, differently -- see
`CLAUDE.md`'s new invariant generalizing across both instances.

**`reservation.py`'s own already-landed `_ul_grant_target` is
confirmed NOT a template for `B_eff` -- a third instance of "a
similar-looking mechanism differs structurally," after FIX-2's own two
divergences from the follower budget at commit 4a.** Confirmed via the
full OAI checkout, not assumed: reservation's real ground truth
(`gNB_scheduler_ulsch.c:2492-2513`, a *different* C file from
two-tier's `ia_p5g_scheduler.c`) computes `ul_target = ul_guaranteed_
bytes + ul_be_bytes` directly -- a genuine sum, since reservation's own
real C has no separate `ul_total_target_bytes`-style accumulator at
all. A second, smaller, also-confirmed divergence: reservation's own
`B_eff` has a THIRD step two-tier's genuinely lacks -- an `has_srb`
control-only cap. Two-tier's own `B_eff` block ends at `B_eff =
ul_target` with no such step -- confirmed absent from the source, not
omitted by oversight, so not ported (`has_srb` is a permanent no-op in
both schedulers regardless, so this makes no practical difference, but
copying reservation's shape here would have been porting reservation's
mechanism, not two-tier's own).

**D1's sizing decision (reservation's own commit 4a) IS directly
reusable -- the one piece of the "template" that does transfer,
confirmed by the same direct read.** "The target sizes PRBs, not
delivered bytes": `prbs_needed` derives from `B_eff` (which may exceed
true backlog when a deficit-carrying GBR flow pushes the target up),
but `tbs_bytes` stays `min(ue_backlog, capacity)` -- grants PRBs for
bytes not yet in the buffer without manufacturing delivered bytes. This
decision is about the sizing MECHANISM's own shape, independent of the
`B_eff` FORMULA divergence above -- reused directly, not re-derived.

**Movement prediction refined beyond "GBR flows only," found checking
scenario UL composition directly.** `factory_robots_scenario`: 13 UL
flows, 10 GBR -- expect real movement (GFBR-based deficit
target-spreading now floors sizing above raw backlog). `sensor_dense_
scenario`: 30 UL flows, but 0 GBR -- MAY ALSO move, via a second,
distinct source: `ul_total_target_bytes`'s non-GBR contribution is the
raw `estimated_ul_buffer_per_lcg` (frozen between BSRs, WP3/WP4's own
confirmed invariant), not `bytes_reported` (drained on grant
regardless of BSR timing) -- whenever a grant has been issued but the
per-LCG array hasn't refreshed yet, `Σ(estimated_ul_buffer_per_lcg) >
bytes_reported` is a real, expected state, independent of any GBR
mechanism. `latency_bound_scenario`: 0 UL flows -- confirmed no
movement possible.

**Commit 4a (this commit) lands the UL floor's grant-sizing bypass: the
GBR-PRB-reserve cap (`gbr_below`, "FIX-2") and the floor's own
uncapped-to-`max_rbSize` sizing, replacing commit 4's fixed `min_rb`
rescue grant.** FIX-2 (`:2987-3030,3105-3124`) is a **general
anti-monopolization cap on every UL DATA-class grant, not floor-specific
machinery the floor merely also respects** -- its own motivating
incident: before this fix, a saturating UE was granted the whole BWP
every slot, so a DIFFERENT UE holding an unmet GBR guarantee never got
PRBs at all (MCS never recovered, SE stayed pinned low, the composite
metric kept ranking it last -- a self-perpetuating lockout). The fix
reserves ``min_rb`` PRBs per still-unserved, live-obligation GBR UE
ranked below the current candidate, via a reverse scan over the sorted
UL candidate list. Applies to every UL candidate, floor-fired or not --
floor-fired grants need it noted only because they were newly routed
onto the same uncapped baseline this fix already protects.

**Genuinely NOT the same shape as ``reservation.py``'s own UL follower
budget -- two confirmed structural differences.** (1) **Baseline**:
reservation's own follower budget reserves against ``bwp_size`` -- a
per-UE STATIC width, its own docstring warns callers never to pass a
running ``prbs_left``. Two-tier's FIX-2 reserves against the slot's
ACTUAL REMAINING PRB count at this candidate's turn -- exactly the
running-budget quantity reservation's own docstring warns against.
(2) **Scope**: reservation's follower budget protects ANY still-needy
follower (backlog, SRB, or GBR). Two-tier's ``gbr_below`` protects GBR
UEs specifically, from monopolization by any UE. Two different
schedulers' answers to a similar-sounding problem.

**Confirmed structurally inert on this corpus, on two independent
grounds -- not a floor-firing question at all for this part.**
``gbr_below``'s own reverse-scan condition requires ``gbr_bytes_slot >
0`` for a downstream UE, which requires ``has_pending_gbr`` (commit 4's
MFBR-keyed gate). **``mfbr_bps`` is never configured on any flow in any
scenario in this repo** -- confirmed directly this commit
(``grep -rn "mfbr_bps" sim/scenarios/ scripts/scheduler_study.py``
returns zero matches), the identical fact ``reservation.py``'s own
already-landed ``gbr_bytes_slot`` port found and documented for the
same quantity (port-map row 25). So ``gbr_below`` is always all-zeros
on this corpus, and FIX-2's cap never binds for ordinary DATA UEs
either -- ported as real, fully testable machinery anyway (this port's
standing practice for confirmed-currently-unreachable mechanisms), not
skipped.

**A correction owed to commit 4, found scoping this commit: the
floor's own dormancy has TWO independent reasons, and commit 4's own
docs stated only one.** Commit 4 attributed the floor's ``--check``
inertness solely to "no in-corpus scenario constructs a BSR/SR desync
fault" -- true, and still the genuinely novel fourth dormancy category.
But ``_ul_has_pending_gbr``'s own MFBR gate means the floor would fail
to arm even if a desync fault WERE constructed, since ``mfbr_bps`` is
never configured anywhere -- and that second reason is NOT novel, it's
this port's own existing category (2), "the signal exists but no
scenario constructs the situation" (the same shape as ``gbr_bytes_
slot``'s own dormancy in ``reservation.py``). Both reasons are real and
independent: fix ``mfbr_bps`` and the floor still needs a fault to fire;
construct a fault and the floor still needs ``mfbr_bps`` configured.
Corrected in ``README.md`` §7/§8 and ``docs/phase2-plan.md``'s own
commit-4 row as part of this commit's doc pass, not a separate commit,
since it was found scoping this one directly.

**PHR-based capping (the ``N_max_prb`` ceiling, and the power-safety
shrink loop a fired floor's grant would otherwise need) is structurally
out of scope -- the same disposition ``reservation.py``'s own commit 4a
already recorded for the identical connection point, confirmed to
transfer rather than assumed.** No PHR-related field exists anywhere in
``scheduler/interfaces.py``'s protocol -- the ``Scheduler`` protocol
structurally cannot see PHR data, the same category of structurally-
absent signal as ``do_sched``/``has_srb``/TA (category 1, not category
2 the way ``mfbr_bps`` is above: ``sim/power.py`` exists but is dormant
*by convention*, and no field crosses the protocol boundary regardless
of what a scenario configures). ``README.md``'s own citation goes
further than "we don't have the signal": "PHR noted sim-only (inert on
hardware)" -- ground truth's own calibration campaign didn't observe
this path bind in practice either. Both C mechanisms' own gates
collapse to permanently-false here with no new code needed. A fifth
``README.md`` §7 dormancy-category entry.

`B_eff`, the deficit-accumulated UL grant-sizing target, was
deliberately NOT built in this commit (4a) -- named as its own future
commit (4b) rather than bundled in here, per user decision, since
`gbr_bytes_slot`'s own contribution was already confirmed inert
(`mfbr_bps` never configured) but `ul_total_target_bytes` was not
(GFBR-based deficit target-spreading IS exercised by this corpus's
real GBR flows). **See commit 4b's own module-docstring section above
for what landed, including a correction to this port's own row-46
plan** (``reservation.py``'s already-landed `_ul_grant_target` turned
out NOT to be a reusable template, and `guaranteed_bytes + be_bytes`
turned out NOT to equal `ul_total_target_bytes` -- neither was known
at commit 4a's own landing).

**Commit 4 (this commit) lands the UL service-interval floor's arm/fire
state machine and a new comparator tier it structurally requires.** The
checklist row's "fruitless-shift (16x cap, 500ms decay) + ADQ (8-grant
trigger)" undersold the mechanism badly -- it is a persistent per-UE
state machine (delivery-history arming, evidence-based deficit
forgiveness, two independently-capped exponential backoffs that
compound) motivated by a real 2026-08-04 production incident (a 5QI-1
MAVLink probe suffering 300-400ms UL blackouts from a BSR/SR desync --
``estimated_ul_buffer`` reading 0 while the UE still holds data).
Numbers reconciled against the C directly: ``FRUITLESS_SHIFT_MAX=4``
and "16x cap" are the *same* fact (``theta_eff = theta << shift``,
``2**4 = 16``), not two disagreeing ones; ``FRUITLESS_DECAY_MS=500``
confirmed exact; ``ADQ_CRUMB_RUN=8`` confirmed exact but **necessary,
not sufficient** -- the real gate is ``crumb_run>=8 AND
adq_age>=adq_period``, where ``adq_period`` compounds the
already-shifted ``theta_eff`` with a *second*, independent backoff
shift (``floor_adq_backoff``, also capped at 4).

**The design-revision comment commit 3 quoted in full ("Revised form
has exactly TWO tiers") is immediately followed by comparator code
implementing THREE** (``ia_p5g_ul_cmp``, ``:2112-2156``): ``sched_
inactive`` → **``floor_fire`` (Tier 1.5, new)** → ``coef``. This is a
third, distinct category of finding on this port's tally -- not one of
the four comment-vs-code mismatches inherited from OAI (comments wrong
about the code they sat next to when *written*), not the self-inflicted
``_dl_stamp`` citation (a citation this project wrote and got wrong).
**This comment was accurate when written and was overtaken by a later
change to the code it describes** -- the *argument* in the same comment
(Tier-1's targets already carry the GBR guarantee into the VQ deficit)
held up under commit 3a's own constructed test; the *tier count* did
not. ``docs/oai-port-map.md`` row 45 is corrected accordingly.

**Tier 1.5 is not optional and cannot be deferred to a later commit --
the C's own comment (``:2122-2143``) states why directly**: a
floor-fired UE is, by construction, in the exact fault state where both
composite inputs read ~0 (the urgency loop is gated on the same
corrupted per-LCG estimate; ``vq_ul`` stopped accruing for the same
reason) -- under Tier 2 alone the rescued UE would sort dead last,
behind every ordinary flow, and never reach a grant. The state machine
is inert without the tier; this is why they land together.

**A related, separate signal found while reading the arming
precondition, confirmed in the full OAI checkout** (not the vendored
subset, which never assigns it): ``has_pending_gbr``
(``gNB_scheduler_ulsch.c:42-71``) is a simpler, different test from
commit 3's ``has_gbr`` -- true if ANY LCG with *current*
``estimated_ul_buffer_per_lcg > 0`` is configured with ``gbr_ul_max >
0`` (MFBR-keyed, not GFBR; existence-based, not deficit-accumulated).
**Flagged, not resolved -- this port's first opportunity to find a bug
in ground truth itself, not in a port of it**: this gate reads the SAME
per-LCG estimate the floor exists to route around. If a UE's only GBR
LCG is the one whose BSR has desynced to 0, ``has_pending_gbr`` reads
``false`` that slot and the floor never arms in exactly the fault it
was built to catch. Ported faithfully (not "fixed"), and tested
directly -- see ``test_ul_floor_has_pending_gbr_gate_reads_the_same_
estimate_it_exists_to_route_around`` and ``README.md`` §7's own new
entry for which of two distinct claims the test result actually
establishes (a faithful port reproducing a real gap, vs. a faithful
port reproducing something real hardware additionally guards against
that this simulator doesn't model).

``mac->min_grant_prb`` (``:2210``) is confirmed the same deployment-
configured field ``reservation.py``'s own follower budget reads
(``CLAUDE.md``'s existing invariant) -- new as a ``TwoTier.__init__``
kwarg here (``min_rb: int = 5``, same default/citation), since the ADQ
crumb-run detector needs it. ``README.md`` §8's ``[OPEN: WP9]`` entry
updated: the sweep parameter is now shared across both schedulers, so a
``min_grant_prb`` sweep can no longer isolate either scheduler's own
sensitivity to it. (``ia_p5g_scheduler.c:1632``'s ``min_rbSize = 5`` is
a *separate*, hardcoded DL-side literal inside ``ia_p5g_pf_dl`` --
unrelated, not to be conflated, the same trap ``CLAUDE.md``'s own
``min_rb`` invariant already documents ``reservation.py``'s commit 4
hitting.)

**``cp_floor``/``reconfig_floor``/``srb_floor`` (``:2743-2796``) are
three separate, unrelated "floor" concepts -- out of scope, not
built.** None touch ``theta``/``fruitless``/``ADQ``/``floor_fire`` at
all. ``cp_floor`` (a UE whose only backlog is control-plane),
``reconfig_floor`` (RRC-reconfig-pending), ``srb_floor`` (explicit SRB
protection) are all structurally absent from this simulator -- no
SRB/RRC-signaling traffic model exists at all, the same finding
``reservation.py``'s own ``has_srb`` tier already made. They feed
``sched_inactive`` (``:2782-2796``), whose full formula (``((B==0 &&
do_sched) || cp_floor) && !has_gbr``) still collapses to permanently
``False`` here since every one of ``do_sched``/``cp_floor``/``srb_
floor``/``reconfig_floor`` is structurally absent -- confirming, more
rigorously than before, commit 3's own hardcoded disposition rather
than changing it.

**A fourth dormancy category, distinct from the three already on
record in `README.md` §7/§8** (see that document for the full
statement): the floor's every input is real, the state machine runs
every slot once landed, and arming/firing are fully testable in
isolation -- what's missing, in this corpus's own scenarios, is the
*fault* (a BSR/SR desync), which is a radio-link failure mode, not a
traffic pattern or a missing signal/scenario the way the other three
categories are. **Correction, commit 4a: this is only HALF of why the
floor never arms on this corpus, not the whole reason.**
``_ul_has_pending_gbr``'s own MFBR gate means the floor would fail to
arm even if a desync fault WERE constructed, since ``mfbr_bps`` is
never configured on any flow in any scenario in this repo (confirmed
directly, commit 4a) -- and THAT reason is not novel at all, it's this
port's own existing category (2), "the signal exists but no scenario
constructs the situation" (the identical shape ``gbr_bytes_slot``'s own
dormancy in ``reservation.py`` already has). Both reasons are real and
independent: fixing one alone does not arm the floor. See commit 4a's
own module-docstring section for the full restatement.

**Commit 3a (this commit) lands the windowed-ceiling virtual queue
itself -- growth, ceiling, drain, and the real ranking coefficients --
finally replacing the bootstrap PF-coefficient placeholder every
ranking decision has used since commit 1.** Commit 3 (``8829e2a``)
landed the GBR-deficit/PDB-remaining sort tiers first, since the VQ is
the *final* tiebreak in both real comparators and a VQ landing under
nothing couldn't have demonstrated its own mechanism.

DL (``ia_p5g_update_vq_dl``, ``ia_p5g_scheduler.c:1835-1894``, re-read
directly this commit): grows by Tier-1's target rate each slot, clamped
to an **arrival-delta** windowed ceiling -- ``min(arr_W, target_W) -
del_W``, where ``arr_W``/``del_W`` are deltas against ``_arr_hist``/
the new ``_del_hist`` snapshots, both frozen once per Tier-1 cycle
inside ``_compute_demand_bps`` (confirmed directly: ``dl_arrived_hist``/
``dl_delivered_hist`` are written only inside the C's Tier-1 demand
block, ``:1264-1265`` -- read-only inside the VQ-update function
itself). This form matches the mechanism's own header intent. LCID < 4
(SRBs) skipped. Ranking coefficient (``ia_p5g_dl_metric``, ``:1896-
1923``): pure ``(Σ vq_dl over backlogged LCIDs) × spectral_eff``,
multiplied *internally*, no urgency folded in -- becomes ``_dl_rank_
key``'s final tiebreak.

UL (``ia_p5g_update_vq_ul``, ``:3578-3687``): grows identically, but
the ceiling is the **backlog-bound/catchup** form -- confirmed again
this commit that the function no longer reads ``ul_arrived_hist``/
``arr_W`` at all. The in-code bugfix comment (``:3608-3654``) explains
why directly: the old arrival-delta form collapsed to ~0 exactly when a
flow was starved hard enough to saturate its buffer (arrivals stop, so
does ``arr_W``) -- "being denied service erases the evidence you were
denied," with a cited incident (UE 5ce4, 2.9 MB backlogged, 435 bytes
delivered in 1 s, ``vq_ul`` read 0.0). The fix bounds by backlog level
instead (``min(backlog, N × target_W) - del_W``, ``N = _VQ_UL_CATCHUP_N
= 5``), which survives starvation. **This is the second of this port's
four documented comment-vs-code instances -- port the code, not the
header.** LCG 0 excluded structurally (no ``FlowConfig`` models SRB
traffic, same convention ``_ul_gbr_and_pdb``/``_ul_stamp`` already use),
``lcid = lcg + 3``.

UL's base ranking term (``ia_p5g_ul_metric``, ``:3696-3726``): ``Σ
vq_ul`` over LCGs gated by an **OR condition** -- include if EITHER
``estimated_ul_buffer_per_lcg > 0`` OR ``vq_ul > 0`` -- a separate,
documented starvation-prevention bugfix (cited incident: "the exact
failure that left d639 with zero grants for 55s"; a BSR-decayed-to-zero
flow during a grant freeze must still be visible via its durable VQ
deficit). Confirmed the function's own ``spectral_eff`` parameter is
read but unused (``(void)spectral_eff``) -- the *caller* forms
``(base_q + urgency) × SE`` and multiplies SE once, unlike DL's
internal multiply. UL's real (and, per commit 3's finding, *sole*)
ranking term is this composite: ``urgency = DELAY_URGENCY_W × Φ(u) ×
norm``, where ``norm = max(base_q across the slot's UL candidates,
1.0)`` and **Φ is a barrier function, not a plain power law** -- ``Φ(u)
= u^DELAY_EXP / (1 - min(u, URG_BARRIER_CAP) + URG_BARRIER_EPS)``,
diverging as ``u → 1``. ``u`` (``ue_worst_urgency01``, ``:2576-2647``)
is the max over active LCGs of ``u_lcg × priority_weight × delta``,
where ``delta = 1.0`` for non-GBR flows and a GBR-deficit-scaled floor
form for GBR ones -- folded into ``_ul_gbr_and_pdb``'s own per-LCG loop
(same ``rem_pdb``/``obligation``/``window`` arithmetic that method
already computed for commit 3) rather than a second duplicate walk,
mirroring the C's own single-pass organization. Constants confirmed by
direct grep: ``IA_P5G_DELAY_URGENCY_W=4.0``, ``_DELAY_EXP=2.0``,
``_URG_PRIO_W_MIN=0.35``, ``_URG_PRIO_MAX=90.0``, ``_URG_BARRIER_
CAP=0.97``, ``_URG_BARRIER_EPS=0.03``, ``_URG_GBR_FLOOR=0.15``. (Note,
not acted on: ``_DELAY_URGENCY_W``/``_DELAY_EXP`` numerically match the
deleted pre-Phase-2 Python's own ``delay_urgency_weight``/
``delay_exponent`` -- magnitude coincidence only; that code's
*structure*, plain power law applied to DL too with no barrier/
priority-weight/GBR-floor terms, was still wrong.)

**``spectral_eff``/``tbs`` is the same hypothetical-TBS quantity for
both directions, and it already existed in this file before this
commit.** Both C call sites (``:1543``, ``:2707``) compute
``nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, l) >> 3`` -- a hypothetical
1-PRB, 10-symbol TBS in bytes at the UE's current MCS. ``_PF_COEF_
HYPOTHETICAL_SYMBOLS = 10`` (commit 1) already computes exactly this
fixed 10-symbol hypothetical, evidently chosen anticipating this reuse
even though commit 1 had no two-tier citation for it at the time.
**Units note, deliberate, not a bug to "fix": ``vq_dl``/``vq_ul`` are
bits, ``hyp_tbs_bytes`` is bytes -- ground truth multiplies them
directly with no conversion. This is an internal ranking score, not a
physical quantity; the mixed units are ported as-is.**

**The bootstrap PF coefficient (``dl_thr_bytes_per_slot``/
``ul_thr_bytes_per_slot``, the per-UE throughput EWMA, and
``_THR_EWMA_ALPHA``) is deleted in this commit, exactly as commit 1's
own docstring already promised** ("Deleted (DL) or replaced (UL) along
with the rest of this placeholder in commit 3a") -- no longer read or
written anywhere in this file.

**A real, self-inflicted finding, distinct in kind from the four
comment-vs-code mismatches inherited from OAI**: ``_dl_stamp``'s own
docstring (landed in commit 3) cited ``gNB_scheduler_dlsch.c:1451-
1460`` as the future VQ-drain hook. Read directly this commit: that
range is unrelated DL-SCH PDU padding-byte fill code, nothing to do
with VQ drain. Corrected to the real citation (``ia_p5g_scheduler.c:
1821`` call site, ``:2002-2035`` the function) -- this project's own
citation, written in commit 3, checked and found wrong in 3a, not
something ported incorrectly from OAI. ``_ul_stamp``'s own citation
(``gNB_scheduler_ulsch.c:2760-2777``) was checked the same way and
found accurate.

DL's drain (``ia_p5g_drain_vq_dl``, ``:2002-2035``): per-LCID,
``(1 - bler)``-discounted, reusing ``_Candidate.bler`` (already computed
per candidate for the pre-existing threshold bookkeeping, now repurposed
here). **Ground truth drains against ``dl_lcid_budget``, populated by
the real LCP fill (``ia_p5g_compute_lcp_budget``, sorted ``(priority
ASC, vq_dl DESC)``, greedy) -- explicitly commit 5's job, not this
one's** (``_dl_fill``'s own docstring already flags this: a placeholder
sorted ``(priority, -bytes_queued)``, "upgraded in commit 5"). **This
commit drains against that placeholder's ``fills`` output instead --
a real behavioral substitution, not a plumbing detail.** The drain
arithmetic itself (the ``(1-bler)`` discount, the per-LCID subtract,
the zero-floor) is faithful; its INPUT (which LCID gets how many of a
TB's bytes) is not yet the real order, so ``vq_dl``'s own trajectory is
not expected to match ground truth until commit 5 lands the real fill.
**Consequence recorded now, not rediscovered at commit 5: commit 5 is a
joint VQ-correction commit, not a pure LCP commit** -- landing the real
fill order will also change which LCID each TB's bytes drain from,
which changes ``vq_dl``, which changes DL ranking downstream, on top of
whatever LCP itself changes about grant composition (also noted in
``docs/phase2-plan.md``'s own commit-5 row).

UL's drain (``ia_p5g_drain_vq_ul``, ``:3728-3769``): proportional split
of the FULL raw ``tb_size`` across active LCGs by BSR-buffer share
(``1/n_active`` fallback when total buffer reads 0), confirmed by
reading the whole function body this commit -- **no BLER discount
anywhere in it**, a genuine DL/UL asymmetry, not an oversight.

**Score commit 3's own stated expectation, tested directly rather than
left as a citation**: if Tier-1's targets genuinely carry the GBR
obligation into the UL VQ deficit, a UL GBR flow should be protected by
the VQ alone with no sort tier assisting it (unlike DL, where
``has_gbr`` protects explicitly) -- see
``test_ul_gbr_flow_held_near_gfbr_by_vq_alone_no_tier_assists`` in the
test file, and this file's own docstring/port-map entry for the
outcome.

``docs/oai-port-map.md``'s port-map rows for this commit carry the full
citation detail for growth/ceiling/drain in both directions and the
composite UL coefficient, plus a dedicated Divergence row for the
DL-drain-against-placeholder substitution above.

**Commit 2 wired the real Tier-1 SCA/GLPK solve
(``scheduler/tier1.py``, rewritten from ``ia_p5g_scheduler.c`` -- see
that module's own docstring for the full ground-truth citation) in,
with its output unconsumed until this commit.** ``_targets_bps`` (real,
computed every ``tier1_period_slots`` slots since commit 2, predicted
and confirmed to move zero `--check` numbers on its own) finally feeds
the VQ growth term above -- this is the first commit where Tier-1's
solve runs genuinely end-to-end. ``tier1_period_slots`` is
derived from ``_TIER1_PERIOD_S = 0.1`` ÷ ``slot_duration_s`` at
``configure()`` time (numerology-robust), not hardcoded, closing the
stale-default finding ``README.md`` §7 already flagged. Demand feeding
the solve is windowed-arrival, DL raw / UL EWMA-smoothed with a
zero-fallback guard -- see ``_resolve_tier1``'s own docstring, which
cites the exact C lines; not an oracle, unlike the deleted pre-Phase-2
default.

Like ``reservation.py``, this package depends only on stdlib and its own
modules -- never on ``sim``. A UL grant is emitted as a single opaque
``ue_grant=True`` Allocation (unchanged from the pre-rewrite file's own
``_emit_grant``); ``sim/ue_lcp.py`` performs the real per-flow split
entirely on the driver side. This scheduler's ranking and grant sizing
read only UE-aggregate quantities (``bytes_reported`` summed across a
UE's flows in a direction) -- never a per-flow split, and never a
per-flow virtual queue on the UL side either (``vq_ul`` is keyed by
LCG, not ``qfi``), matching ``docs/phase2-plan.md`` D1's requirement
that UL state be LCG-aggregate, the real gNB's own visibility
(``ia_p5g_scheduler.c``'s ``vq_ul[UE][LCG]``, not per-flow).

**The bootstrap PF coefficient/throughput-EWMA placeholder that ranked
every UE from commit 1 through commit 3 is gone as of this commit** --
``dl_thr_bytes_per_slot``/``ul_thr_bytes_per_slot``/``_THR_EWMA_ALPHA``
are deleted outright, exactly as commit 1's own docstring already
promised ("Deleted (DL) or replaced (UL)... in commit 3a"). It was
never ground truth at any point it existed (two-tier's own coefficient
is never PF-coefficient-shaped, unlike ``reservation.py``'s, where the
identical formula *is* the real final tiebreak) -- do not add a C
file:line citation for it retroactively in the port-map row; its own
row already records "no ground truth -- temporary bootstrap, removed
commit 3a."

The one piece of this file that *is* a live-source citation:
``gNB_scheduler.c:246,251`` (confirmed byte-identical across both
branches, ``oai-branches/README.md``) runs ``nr_schedule_ulsch`` before
``nr_schedule_ue_spec`` (DL) unconditionally, every slot -- UL-then-DL.
**The pre-rewrite ``two_tier.py`` had this backwards**: its own
``allocate()`` iterated ``("DL", "UL")``, DL first -- a real, live bug in
the scheduler that produced every existing TwoTier regression record,
not a cosmetic one. Fixed here.
"""

from dataclasses import dataclass, field

from .flow import FlowConfig
from .interfaces import Allocation, BufferView, ChannelView, GridView, SlotView
from .link import (
    bits_per_prb,
    bits_per_prb_for_mcs,
    cce_aggregation_level,
    mcs_index_for_snr,
)
from .tier1 import solve_tier1

# ia_p5g_scheduler.c:74-76 -- the deployed macro, not ia_p5g_scheduler.h's
# stale "1.0 s default" doc comment (README.md sec7's own stale-default
# finding, now closed here rather than merely documented). Slot count is
# derived from this at configure() time, never hardcoded.
_TIER1_PERIOD_S = 0.1

# ia_p5g_scheduler.c:388 -- UL-only demand EWMA smoothing (see
# scheduler/tier1.py's own citation of the same constant; duplicated here
# rather than imported since it's a two_tier.py-local demand-tracking
# concern, the same "small shared constant, not a cross-module import"
# convention _PF_COEF_HYPOTHETICAL_SYMBOLS already uses).
_UL_DEMAND_ALPHA = 0.3

# GRADUATES to real ground truth as of commit 3a: ia_p5g_scheduler.c:1540
# (DL) and :2681-ish (UL) both compute nr_compute_tbs(Qm, R, 1, 10, 0, 0,
# 0, l) >> 3 -- a hypothetical 1-PRB, 10-symbol TBS in bytes at the UE's
# current MCS -- as the "spectral_eff"/"tbs" argument to
# ia_p5g_dl_metric/ia_p5g_ul_metric. The fixed "10" matches this constant
# exactly. Commit 1 chose it as a bootstrap-only PF-coefficient
# convention borrowed from reservation.py, with no two-tier citation;
# this commit confirms it was -- by coincidence or foresight -- already
# the real value. Used below as _Candidate.hyp_tbs_bytes, the real
# spectral-efficiency factor both directions' ranking coefficients
# multiply by.
_PF_COEF_HYPOTHETICAL_SYMBOLS = 10

# gNB_scheduler_dlsch.c:352/:2216 (two-tier's own files -- confirmed
# byte-identical to reservation's own citation of the same constant at
# the same fallback value, docs/oai-port-map.md rows 18/19). Applies to
# both directions.
_PDB_FALLBACK_MS = 300

# ia_p5g_scheduler.c:3676 -- UL VQ ceiling's catch-up horizon (windows of
# guaranteed bits the virtual queue may accumulate before the backlog/
# ceiling clamp binds), part of the backlog-bound bugfix form (see
# _update_vq_ul's own docstring) -- NOT the arrival-delta form the
# module's own header describes.
_VQ_UL_CATCHUP_N = 5

# Commit 6 (D2(b)) -- OLLA's offset from the instantaneous MCS pick
# (mcs_index_for_snr), provably 0 given this scheduler's available
# inputs, not merely a placeholder. get_mcs_from_bler's own trigger
# (NR_mac_dir_stats_t.rounds[0]/[1]) is incremented at grant-
# finalization by the SAME component that issues both new-tx and retry
# grants (post_process_ulsch:2724/post_process_dlsch:1168, two-tier's
# own files) -- a symmetry this simulator's WP5 Decision 4 breaks
# (retransmission scheduling moved entirely to sim/driver.py's HARQ
# seam, never reaching Scheduler.allocate()). With round-1 telemetry
# structurally unobservable, the C's own bler ratchet clamps at
# min_mcs from the first update -- offset = mcs - min_mcs == 0,
# unconditionally, forever, fully determined without executing
# sim/olla.py::update_mcs_from_bler. Confirmed independently against
# two-tier's own C this commit (byte-identical gNB_scheduler_
# primitives.c, byte-identical bo->harq_round_max call-site gate in
# ia_p5g_scheduler.c's own DL/UL blocks) -- the identical disposition
# reservation.py's own commit 9 already landed and cited here, not
# re-derived, since the underlying argument (a sim/driver.py-level
# fact, not a scheduling-policy one) is the same for both schedulers.
_OLLA_OFFSET = 0

# ia_p5g_scheduler.c:443-444,478-481,501 -- UL's composite-coefficient
# urgency term (barrier function + priority weight + GBR-deficit floor).
# _DELAY_URGENCY_W/_DELAY_EXP numerically match the deleted pre-Phase-2
# Python's own delay_urgency_weight/delay_exponent (4.0/2.0) -- magnitude
# coincidence only; that code's structure (plain power law, applied to DL
# too, no barrier/priority-weight/GBR-floor terms) was still wrong.
# Ported fresh from this commit's own ground-truth reading, not reused
# from the deleted file.
_DELAY_URGENCY_W = 4.0
_DELAY_EXP = 2.0
_URG_PRIO_W_MIN = 0.35
_URG_PRIO_MAX = 90.0
_URG_BARRIER_CAP = 0.97
_URG_BARRIER_EPS = 0.03
_URG_GBR_FLOOR = 0.15

# ia_p5g_scheduler.c:80-107 -- UL service-interval floor constants,
# confirmed by direct grep this commit. theta = min-PDB / PDB_DIV,
# floored at MIN_SLOTS. FRUITLESS_MAX gates evidence-based deficit
# forgiveness (a DIFFERENT threshold from FRUITLESS_SHIFT_MAX -- see
# module docstring's "16x cap" reconciliation). FRUITLESS_SHIFT_MAX
# also caps the independent ADQ backoff shift (floor_adq_backoff).
_UL_FLOOR_PDB_DIV = 8
_UL_FLOOR_ALIVE_MS = 2000.0
_UL_FLOOR_MIN_SLOTS = 2
_UL_FLOOR_FRUITLESS_MAX = 3
_UL_FLOOR_FRUITLESS_SHIFT_MAX = 4
_UL_FLOOR_FRUITLESS_DECAY_MS = 500.0
_UL_FLOOR_ADQ_CRUMB_RUN = 8

# gNB_scheduler_ulsch.c:46 (update_ul_qos_priority) -- the floor's own
# theta-input PDB fallback. Confirmed a DIFFERENT constant from
# _PDB_FALLBACK_MS (300ms, used by _dl_gbr_and_pdb/_ul_gbr_and_pdb for a
# different purpose) -- two independently-chosen fallbacks in the same
# C file, not a copy-paste of one into the other.
_UL_FLOOR_PDB_FALLBACK_MS = 100


@dataclass
class _UeState:
    """Per-UE state: commit 3's GBR-deficit/last-grant-slot tracking
    (real ground truth, adapted directly from ``reservation.py``'s own
    ``_UeState``, same field shapes, since the underlying C is confirmed
    byte-identical between branches for this mechanism), commit 3a's
    virtual queues -- ``vq_dl`` keyed by DL flow ``qfi`` (≈ LCID),
    ``vq_ul`` keyed by UL LCG, matching ``ia_p5g_scheduler.c``'s own
    ``vq_dl[UE][LCID]``/``vq_ul[UE][LCG]`` shapes (module docstring's
    D1 note: UL state is LCG-aggregate, never per-flow) -- plus this
    commit's UL floor state. Floor fields are persistent, NOT reset per
    slot or per window (``ia_p5g_ul_summary_t``'s own comment: "NOT
    reset by the window flush"). Pure telemetry fields (``floor_fires_w``/
    ``floor_adq_fires_w``/``floor_silence_snap``) are not ported --
    they feed no regression metric, matching this port's convention of
    skipping C logging infrastructure that doesn't.
    """

    ul_lcg_deficit_bytes: dict[int, int] = field(default_factory=dict)
    ul_lcg_last_grant_slot: dict[int, int] = field(default_factory=dict)
    dl_flow_deficit_bytes: dict[int, int] = field(default_factory=dict)
    dl_flow_last_grant_slot: dict[int, int] = field(default_factory=dict)
    vq_dl: dict[int, float] = field(default_factory=dict)
    vq_ul: dict[int, float] = field(default_factory=dict)
    # Commit 6 (D2(a)) -- a persistent per-UE-per-direction MCS index,
    # mirroring reservation.py's own _UeState fields (same shape, same
    # ground truth -- gNB_scheduler_primitives.c confirmed byte-identical
    # between branches). Link adaptation had no stored home anywhere in
    # this scheduler before this.
    ul_mcs_index: int | None = None
    dl_mcs_index: int | None = None
    floor_rx_lastseen: int = 0
    floor_last_move_slot: int | None = None
    floor_alive_slot: int | None = None
    floor_fruitless: int = 0
    floor_fruitless_slot: int | None = None
    floor_adq_backoff: int = 0
    floor_adq_slot: int | None = None
    floor_crumb_run: int = 0
    floor_disarmed: bool = False


@dataclass
class _Candidate:
    ue_id: int
    flows: list[FlowConfig]
    bits_per_rb: int
    bler: float
    snr_db: float
    coef: float
    # DL sort tiers (ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411) -- real
    # for DL, unused by UL's own ranking (see _ul_rank_key). As of
    # commit 4a, also set for UL candidates -- not for ranking, but as
    # gbr_below's own reverse-scan input (module docstring).
    has_gbr: bool = False
    pdb_ms: int = 9999
    # UL's own top tier (ia_p5g_ul_cmp, :2112-2125) -- structurally
    # absent (no do_sched-equivalent signal exists), same disposition
    # reservation.py's own liveness/sched_inactive finding already made.
    # Unused by DL.
    sched_inactive: bool = False
    # Real spectral-efficiency factor both directions' coefficients
    # multiply by -- see module docstring's _PF_COEF_HYPOTHETICAL_SYMBOLS
    # note. Computed once per candidate at build time.
    hyp_tbs_bytes: int = 0
    # UL only (ue_worst_urgency01, ia_p5g_scheduler.c:2576-2647) -- DL
    # leaves this at the default since ia_p5g_dl_metric folds in no
    # urgency term at all.
    urgency01: float = 0.0
    # UL only (ia_p5g_ul_ue_t.floor_fire/.floor_sil, :2082-2089) --
    # Tier 1.5 in _ul_rank_key (commit 4). Unused by DL.
    floor_fire: bool = False
    floor_sil: int = 0
    # UL only -- has_pending_gbr-gated MAX-over-backlogged-GBR-LCGs
    # (gfbr_bps/8/slots_per_sec) (ia_p5g_scheduler.c:2710-2722). Real
    # value as of commit 4b (was a bool, commit 4a -- only gbr_below's
    # own reverse scan needed the boolean then; B_eff's own floor
    # (commit 4b) needs the numeric value too). gbr_below's condition
    # reads `> 0` on this field now, same effect as the old bool.
    # Confirmed always 0 on this corpus (module docstring -- mfbr_bps
    # never configured), ported anyway.
    gbr_bytes_slot: int = 0
    # UL only, commit 4b -- _ul_gbr_and_pdb's OWN third accumulator,
    # NOT guaranteed_bytes+be_bytes (module docstring's row-46
    # correction). Feeds B_eff for ordinary (non-floor-fired) DATA
    # sizing.
    ul_total_target_bytes: int = 0


class TwoTier:
    """Rewritten in place from the pre-Phase-2 file (tag
    ``phase2-pre-twotier-rewrite``). Commit 1: ``Scheduler`` protocol
    conformance, a per-UE throughput-EWMA bootstrap ranking, no VQ, no
    UL floor, no Tier-1 -- see module docstring for what's deleted and
    what lands in later commits.
    """

    def __init__(self, min_rb: int = 5) -> None:
        # mac->min_grant_prb, ia_p5g_scheduler.c:2210 -- confirmed the
        # SAME deployment-configured field reservation.py's own follower
        # budget reads (CLAUDE.md's existing invariant), new here as a
        # constructor kwarg since the UL floor's ADQ crumb-run detector
        # needs it (module docstring). NOT ia_p5g_scheduler.c:1632's
        # separate, hardcoded min_rbSize=5 DL-side literal.
        self.min_rb = min_rb
        self._flows: list[FlowConfig] = []
        self._ue_state: dict[int, _UeState] = {}
        self._snr_avg: dict[int, float] = {}
        self._targets_bps: dict[tuple[int, int], float] = {}
        self._arr_hist: dict[tuple[int, int], float] = {}
        self._del_hist: dict[tuple[int, int], float] = {}
        self._ul_demand_smooth: dict[tuple[int, int], float] = {}
        self._last_solve_slot = -(10**9)
        self.tier1_period_slots = 1

    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: GridView,
    ) -> None:
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        self._grid = grid
        self._ue_state = {f.ue_id: _UeState() for f in flows}
        self._snr_avg = {}
        self._targets_bps = {}
        self._arr_hist = {(f.ue_id, f.qfi): 0.0 for f in flows}
        self._del_hist = {(f.ue_id, f.qfi): 0.0 for f in flows}
        self._ul_demand_smooth = {
            (f.ue_id, f.qfi): 0.0 for f in flows if f.direction == "UL"
        }
        self.tier1_period_slots = max(1, round(_TIER1_PERIOD_S / slot_duration_s))
        self._last_solve_slot = -(10**9)

    def allocate(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
    ) -> list[Allocation]:
        self._update_snr_ewma(channel)
        if slot.slot_index - self._last_solve_slot >= self.tier1_period_slots:
            self._resolve_tier1(slot.slot_index, buffers)
            self._last_solve_slot = slot.slot_index

        # gNB_scheduler.c:246,251 -- UL before DL, unconditionally, every
        # slot. See module docstring: the pre-rewrite file had this
        # backwards (DL-then-UL); fixed here, verified directly against
        # the C rather than inherited from the old Python or the plan
        # doc's own prose.
        out: list[Allocation] = []
        if slot.ul_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "UL"))
        if slot.dl_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "DL"))
        return out

    def _update_snr_ewma(self, channel: ChannelView) -> None:
        """Tier-1's own SNR input -- solve_tier1 needs a per-UE SNR to
        compute spectral efficiency. A plain smoothed CQI-visible read,
        the same convention the pre-rewrite file used for the identical
        purpose (not itself a claim about ground truth's own SNR-smoothing
        specifics for Tier-1, which ia_p5g_scheduler.c does not appear to
        smooth at all before ia_p5g_estimate_se_dl/_ul -- flagged, not
        resolved, since it doesn't change this commit's own predicted-
        zero-movement outcome either way; Tier-1's output is unconsumed
        this commit regardless of exactly how its own inputs are formed)."""
        for f in self._flows:
            cur = channel.get_reported_snr_db(f.ue_id)
            self._snr_avg[f.ue_id] = cur

    def _resolve_tier1(self, slot_index: int, buffers: BufferView) -> None:
        """ia_p5g_tier1_thread's per-cycle body (ia_p5g_scheduler.c:1120-
        1345): build each flow's windowed-arrival demand, call
        solve_tier1, and -- fail-soft, matching the C's own "keep last
        good targets" behavior (scheduler/tier1.py::solve_tier1's own
        docstring) -- only overwrite self._targets_bps when the solve
        actually produced something. Not consumed by ranking until commit
        3a (VQ); computed and stored here regardless, so commit 3a doesn't
        also have to wire the solve itself.
        """
        if slot_index - self._last_solve_slot >= 10**8:
            # First call this run (_last_solve_slot still at its sentinel
            # init) -- no real prior cycle to measure elapsed time against.
            # ia_p5g_scheduler.c:1137-1139's own fallback: use the nominal
            # period, not a wall-clock delta that doesn't exist yet.
            elapsed_s = _TIER1_PERIOD_S
        else:
            elapsed_s = (slot_index - self._last_solve_slot) * self.slot_duration_s
        demand_bps = self._compute_demand_bps(buffers, elapsed_s)
        targets = solve_tier1(self._flows, self._snr_avg, self._grid, demand_bps)
        if targets:
            self._targets_bps = targets

    def _compute_demand_bps(
        self, buffers: BufferView, elapsed_s: float
    ) -> dict[tuple[int, int], float]:
        """Windowed-arrival demand per flow -- ia_p5g_scheduler.c:1238-
        1334. DL: raw arr_W/elapsed, never smoothed (:1256, ":1289-1290
        must NOT be smoothed" -- the RLC buffer is exact and stable). UL:
        the same base quantity, EWMA-smoothed at _UL_DEMAND_ALPHA with a
        raw-value fallback when the smoothed estimate is still zero
        (:1291-1301, first cycle after attach). Ground truth additionally
        caps UL demand at the UE's PHR power headroom (:1303-1313) --
        NOT wired here; sim/power.py stays dormant per this repo's own
        convention (README.md sec4), a flagged gap, not a silent omission.

        Also freezes ``_del_hist`` (delivered-only cumulative, no
        backlog term) alongside the pre-existing ``_arr_hist`` --
        confirmed directly against the C this commit (3a): both
        ``dl_arrived_hist``/``dl_delivered_hist`` (and their UL
        counterparts) are written ONLY inside this same per-Tier-1-cycle
        block (``:1264-1265``, ``:1332-1333``), never inside the VQ
        growth/ceiling functions themselves (``ia_p5g_update_vq_{dl,
        ul}``, which read them but never write them) -- so the VQ
        ceiling's window comparison is against a snapshot frozen at
        Tier-1 cadence, not updated every slot.

        Known, pre-existing simulator limitation, not introduced here:
        multiple flows sharing one UL LCG would each read the identical
        estimated_ul_buffer_per_lcg and get independent (duplicated)
        demand entries -- the same H5-gap shape already documented
        elsewhere in this port (README.md sec8); no current scenario
        triggers it.
        """
        demand: dict[tuple[int, int], float] = {}
        for f in self._flows:
            key = (f.ue_id, f.qfi)
            st = buffers.state(f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            if f.direction == "DL":
                arr_cum = del_cum + st.bytes_queued
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
                self._del_hist[key] = del_cum
                demand[key] = max(0.0, arr_w * 8.0 / elapsed_s)
            else:
                arr_cum = del_cum + st.estimated_ul_buffer_per_lcg
                arr_w = arr_cum - self._arr_hist.get(key, 0.0)
                self._arr_hist[key] = arr_cum
                self._del_hist[key] = del_cum
                demand_raw = max(0.0, arr_w * 8.0 / elapsed_s)
                prev_smooth = self._ul_demand_smooth.get(key, 0.0)
                smooth = (
                    _UL_DEMAND_ALPHA * demand_raw
                    + (1.0 - _UL_DEMAND_ALPHA) * prev_smooth
                )
                self._ul_demand_smooth[key] = smooth
                demand[key] = smooth if smooth > 0.0 else demand_raw
        return demand

    def _allocate_direction(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.ul_symbols if direction == "UL" else slot.dl_symbols

        # D1 (docs/phase2-plan.md sec3): UE-aggregate only, never a
        # per-flow split. Multiple flows sharing one LCG would each read
        # the identical bytes_reported and be summed here more than
        # once -- a known, currently-untriggered gap (no scenario in
        # this repo shares an LCG across UL flows -- README sec8's H5
        # follow-up), the same shape reservation.py's own ue_backlog sum
        # carries, not fixed here either.
        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)

        # [FLOOR] UL only. ia_p5g_scheduler.c:2306-2538 -- the floor's
        # own arming/firing must be evaluated for EVERY UL UE, including
        # ones the bytes_reported>0 filter above just excluded (B==0 is
        # exactly do_sched's structurally-absent-implied "_empty", the
        # condition the floor exists to route around -- module
        # docstring). Runs once per UE, in self._flows' own order, not a
        # second independently-ordered scan -- see module docstring's
        # note on why this pre-pass is itself a candidate source of
        # iteration-order-driven movement, distinct from the floor
        # mechanism actually firing.
        floor_fire_for: dict[int, int] = {}
        if direction == "UL":
            seen_ue: set[int] = set()
            for f in self._flows:
                if f.direction != "UL" or f.ue_id in seen_ue:
                    continue
                seen_ue.add(f.ue_id)
                fired, sil = self._update_ul_floor(f.ue_id, buffers, slot.slot_index)
                if not fired:
                    continue
                floor_fire_for[f.ue_id] = sil
                if f.ue_id not in ue_flows:
                    ue_flows[f.ue_id] = [
                        ff for ff in self._flows
                        if ff.ue_id == f.ue_id and ff.direction == "UL"
                    ]

        if not ue_flows:
            return []

        candidates: list[_Candidate] = []
        for ue_id, flows in ue_flows.items():
            state = self._ue_state[ue_id]

            snr = channel.get_reported_snr_db(ue_id)
            # Below-lowest-MCS-threshold viability gate -- deliberately
            # stays keyed on the raw SNR walk (bits_per_prb), not the
            # persisted MCS index below: mcs_index_for_snr floors at 0
            # rather than signaling "no viable MCS" (its own documented
            # convention, a persisted field must always be a concrete
            # int), so routing this gate through it would silently make
            # an arbitrarily-low-SNR UE look transmittable. Same
            # disposition reservation.py's own commit 9 already landed.
            if bits_per_prb(snr, symbols=symbols)[0] <= 0:
                continue

            # Commit 6 (D2(a)/D2(b)): a persistent per-UE-per-direction
            # MCS index now drives sizing, matching ground truth's own
            # selected_mcs (gNB_scheduler_{ul,dl}sch.c). _OLLA_OFFSET is
            # provably 0 given this scheduler's available inputs, not
            # merely defaulted -- module docstring's own section, and
            # confirmed independently against two-tier's own C, not
            # merely cited from reservation.py's identical finding.
            mcs_index = mcs_index_for_snr(snr) + _OLLA_OFFSET
            if direction == "UL":
                state.ul_mcs_index = mcs_index
            else:
                state.dl_mcs_index = mcs_index
            bits_per_rb, bler = bits_per_prb_for_mcs(mcs_index, symbols=symbols)

            # Real spectral-efficiency factor -- see module docstring's
            # _PF_COEF_HYPOTHETICAL_SYMBOLS note (ia_p5g_scheduler.c:1540,
            # :2707). Ground truth's selected_mcs feeds both this
            # hypothetical TBS and the real grant's TBS (row 15) -- reads
            # the same persisted index, not a fresh SNR pick.
            hyp_bits, _ = bits_per_prb_for_mcs(
                mcs_index, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS
            )
            hyp_tbs_bytes = hyp_bits // 8

            candidate = _Candidate(
                ue_id, flows, bits_per_rb, bler, snr, coef=0.0,
                hyp_tbs_bytes=hyp_tbs_bytes,
            )
            if direction == "DL":
                self._update_vq_dl(ue_id, buffers)
                has_gbr, pdb_ms, _guaranteed, _be = self._dl_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )
                candidate.has_gbr = has_gbr
                candidate.pdb_ms = pdb_ms
                # ia_p5g_dl_metric, :1896-1923 -- pure product, no
                # urgency, only backlogged LCIDs contribute.
                sum_q = sum(
                    state.vq_dl.get(f.qfi, 0.0)
                    for f in flows
                    if buffers.state(f.ue_id, f.qfi).bytes_queued > 0
                )
                candidate.coef = sum_q * hyp_tbs_bytes
            else:
                self._update_vq_ul(ue_id, buffers)
                # UL's own has_gbr/pdb_ms aren't sort tiers (see module
                # docstring's design-revision finding) -- called for the
                # deficit-tracking + urgency side effect. has_gbr IS
                # stored (not for ranking -- for gbr_below's own
                # reverse-scan input below); pdb_ms stays unread.
                (
                    has_gbr, _pdb_ms, _guaranteed, _be, urgency01,
                    gbr_bytes_slot, ul_total_target_bytes,
                ) = self._ul_gbr_and_pdb(ue_id, buffers, slot.slot_index)
                candidate.has_gbr = has_gbr
                candidate.gbr_bytes_slot = gbr_bytes_slot
                candidate.ul_total_target_bytes = ul_total_target_bytes
                candidate.urgency01 = urgency01
                # ia_p5g_ul_metric, :3696-3726 -- base_q only; the
                # urgency term and the SE multiply happen in
                # _finalize_ul_coef below, once max_q across this slot's
                # UL candidates is known. coef temporarily holds base_q
                # until then.
                candidate.coef = self._ul_base_q(ue_id, buffers)
                # [FLOOR] Tier 1.5 -- ia_p5g_ul_ue_t.floor_fire/.floor_sil
                # (:2082-2089). A fired floor still gets a real coef
                # computed above (ground truth's own UE_sched[] does
                # too); it's simply irrelevant to this candidate's final
                # rank position once _ul_rank_key's new tier applies.
                if ue_id in floor_fire_for:
                    candidate.floor_fire = True
                    candidate.floor_sil = floor_fire_for[ue_id]
            candidates.append(candidate)

        if not candidates:
            return []

        if direction == "UL":
            self._finalize_ul_coef(candidates)

        rank_key = self._dl_rank_key if direction == "DL" else self._ul_rank_key
        candidates.sort(key=rank_key)

        # [FIX-2] UL only. ia_p5g_scheduler.c:3016-3030 -- gbr_below[i]
        # = count of still-unserved, live-obligation GBR UEs ranked
        # STRICTLY AFTER candidate i in the sorted (served) order.
        # sched_inactive is always False here, so the C's own exclusion
        # of it from both sides of the count is a no-op -- kept in the
        # condition anyway per this port's "port even when currently a
        # no-op" convention. Confirmed always all-zero on this corpus
        # (module docstring -- mfbr_bps never configured, so
        # gbr_bytes_slot is never > 0) -- computed anyway as real,
        # testable machinery.
        gbr_below: list[int] = [0] * len(candidates)
        if direction == "UL":
            running = 0
            for i in range(len(candidates) - 1, -1, -1):
                gbr_below[i] = running
                c = candidates[i]
                if (
                    not c.sched_inactive
                    and c.has_gbr
                    and c.gbr_bytes_slot > 0
                ):
                    running += 1

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        out: list[Allocation] = []
        for i, c in enumerate(candidates):
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(c.snr_db)
            if cce_left < cce_cost:
                continue

            # [FIX-2] UL only -- max_rbSize baseline is the whole slot
            # (this simulator's single-BWP deployment has no narrower
            # per-UE BWP concept, matching the C's own "grant width is
            # the sole lever" framing), then the GBR-PRB reserve for
            # still-unserved GBR UEs ranked below this one. DL is
            # unaffected -- max_rbSize stays the slot's own remaining
            # budget, same as before commit 4a. The max(cap, min_rb)
            # floor can never let max_rbSize exceed what prbs_left
            # alone would have allowed: the final sizing step below
            # always wraps this in min(prbs_left, max_rbSize, ...), so
            # a cap raised above prbs_left is harmless by construction,
            # not merely by this specific corpus's own numbers.
            max_rbSize = slot.prb_count
            if direction == "UL":
                reserve_rb = gbr_below[i] * self.min_rb
                cap = prbs_left - reserve_rb
                cap = max(cap, self.min_rb)
                max_rbSize = min(max_rbSize, cap)

            ue_backlog = sum(
                buffers.state(f.ue_id, f.qfi).bytes_reported for f in c.flows
            )
            if ue_backlog <= 0:
                if not c.floor_fire:
                    continue
                # [FLOOR] ia_p5g_scheduler.c:3232-3253 -- a fired floor
                # bypasses nr_find_nb_rb's demand-based sizing entirely
                # (the demand estimate is exactly what the fault
                # corrupted), taking the full max_rbSize (already
                # bounded by the FIX-2 reserve above) instead of commit
                # 4's own fixed min_rb rescue grant.
                prbs_used = min(prbs_left, max_rbSize)
                tbs_bytes = (prbs_used * c.bits_per_rb) // 8
                if tbs_bytes <= 0:
                    continue
            else:
                # [B_eff] UL only -- ia_p5g_scheduler.c:3195-3204.
                # ul_total_target_bytes is DL-irrelevant (0 by default
                # on _Candidate) and gbr_bytes_slot likewise, so this
                # reduces to plain ue_backlog sizing for DL exactly as
                # before. Independent of max_rbSize above (computed
                # separately in the C too) -- combined only here, at
                # the sizing call, matching ground truth's own order.
                b_eff = ue_backlog
                if direction == "UL":
                    b_eff = max(c.ul_total_target_bytes, ue_backlog)
                    if c.has_gbr and c.gbr_bytes_slot > 0:
                        b_eff = max(b_eff, c.gbr_bytes_slot)
                prbs_needed = -(-(b_eff * 8) // c.bits_per_rb)  # ceil div
                prbs_used = min(prbs_left, max_rbSize, max(1, prbs_needed))
                # D1 (reservation.py's own commit-4a decision, reused
                # directly): the target sizes PRBs, not delivered bytes
                # -- b_eff may exceed true backlog when a deficit-
                # carrying GBR flow pushes the target up, but tbs_bytes
                # never manufactures bytes beyond real backlog.
                tbs_bytes = min(ue_backlog, (prbs_used * c.bits_per_rb) // 8)
                if tbs_bytes <= 0:
                    continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes, c.flows,
                    buffers, cce_cost, c.snr_db, slot.slot_index, c.bler,
                )
            )
        return out

    def _finalize_ul_coef(self, candidates: list[_Candidate]) -> None:
        """Second pass of ia_p5g_scheduler.c:2860-2924's composite
        formation -- needs max_q (base_q's max across the slot's whole
        UL candidate set) before any single candidate's coef can be
        finalized, so this can't happen inline during candidate-building
        the way DL's single-pass metric can. Before this runs,
        candidate.coef temporarily holds base_q (this method's own
        input); overwritten here with the real composite. sched_inactive
        is always False (module docstring), so "non-sched_inactive
        candidates" collapses to "all candidates" for the max_q scan.
        """
        norm = max((c.coef for c in candidates), default=0.0)
        norm = max(norm, 1.0)
        for c in candidates:
            base_q = c.coef
            u = c.urgency01
            ub = min(u, _URG_BARRIER_CAP)
            phi = (u**_DELAY_EXP) / (1.0 - ub + _URG_BARRIER_EPS)
            urg = _DELAY_URGENCY_W * phi * norm
            c.coef = (base_q + urg) * c.hyp_tbs_bytes

    def _dl_rank_key(self, candidate: _Candidate) -> tuple:
        """ia_p5g_dl_cmp, ia_p5g_scheduler.c:1397-1411 -- the *original*,
        never-revised lexicographic form: has_gbr (top), then pdb_ms,
        then the coefficient as final tiebreak -- as of commit 3a, the
        real ia_p5g_dl_metric product (module docstring), not the
        bootstrap placeholder. Independently sourced from _ul_rank_key,
        not a shared function -- DL and UL's real comparators have
        genuinely different tier counts (see module docstring's
        design-revision finding), matching reservation.py's own
        precedent of never merging its _ul_rank_key/_dl_rank_key even
        when their shapes coincide.
        """
        return (0 if candidate.has_gbr else 1, candidate.pdb_ms, -candidate.coef)

    def _ul_rank_key(self, candidate: _Candidate) -> tuple:
        """ia_p5g_ul_cmp, ia_p5g_scheduler.c:2112-2156 -- the *revised*
        comparator. Commit 3 quoted the design-revision comment's own
        "Revised form has exactly TWO tiers" as authoritative; reading
        the comparator code directly this commit (4) found it
        immediately implements THREE. A comment accurate when written,
        overtaken by a later change to the code it describes -- not one
        of the four OAI-inherited comment-vs-code mismatches, not the
        self-inflicted _dl_stamp citation; a third, distinct category
        (module docstring). The *argument* in the same comment (Tier-1's
        targets already encode the GBR guarantee, so has_gbr/pdb_ms
        would double-count it) still held up under commit 3a's own
        test -- only the tier count was stale.

        Tier 1 -- sched_inactive (structurally absent here, hardcoded
        False -- see module docstring). Tier 1.5 -- floor_fire (new,
        commit 4): a fired floor outranks every ordinary data UE
        regardless of coef, tie-broken on floor_sil (longer silence
        served first, -floor_sil sorts that way; inert 0 when
        floor_fire is False on both sides, so it never perturbs Tier 2).
        The C's own comment (:2122-2143) states why this tier can't be
        skipped: a floor-fired UE's composite reads ~0 by construction
        of the fault it rescues, so without this tier the rescue would
        sort dead last under Tier 2 and never reach a grant. Tier 2 --
        the composite coefficient (_finalize_ul_coef). Deliberately does
        NOT include has_gbr/pdb_ms as their own tier -- the argument
        above.
        """
        return (
            0 if candidate.sched_inactive else 1,
            0 if candidate.floor_fire else 1,
            -candidate.floor_sil if candidate.floor_fire else 0,
            -candidate.coef,
        )

    def _dl_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int]:
        """DL GBR deficit accumulate/cap/target-spread/overflow-to-BE,
        plus remaining-PDB -- gNB_scheduler_dlsch.c:325-410 (two-tier's
        own file). Confirmed byte-identical, by direct diff, to
        oai-branches/reservation/gNB_scheduler_dlsch.c's own version of
        this same block -- adapted line-for-line from
        reservation.py::_dl_gbr_and_pdb (same int-ms-truncation
        discipline, same 300 ms PDB fallback, same unconditional-deficit-
        accumulation-vs-gated-target asymmetry that method's own
        docstring already documents), not re-derived. Returns
        ``(has_gbr, remaining_pdb_ms, guaranteed_bytes, be_bytes)`` --
        the last two are real (computed, matching the C) but NOT yet
        consumed by anything (grant sizing is a later commit, mirroring
        reservation's own commit-3-then-4a split).
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0

        has_gbr = False
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            bytes_queued = buffers.state(f.ue_id, f.qfi).bytes_queued

            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.dl_flow_last_grant_slot.get(f.qfi)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            if bytes_queued > 0:
                best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += bytes_queued
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.dl_flow_deficit_bytes.get(f.qfi, 0) + obligation
            window = obligation * int(pdb_ms / slot_ms)
            deficit = min(deficit, window)
            state.dl_flow_deficit_bytes[f.qfi] = deficit
            if deficit > 0:
                has_gbr = True

            if bytes_queued <= 0:
                continue  # accumulation is unconditional; target is not

            rem_slots = int(remaining_pdb / slot_ms)
            if rem_slots < 1:
                rem_slots = 1
            target = (deficit + obligation) // rem_slots
            if target < obligation:
                target = obligation
            max_burst = int((f.mfbr_bps / 8.0) / slots_per_sec) * 2
            if max_burst < obligation * 2:
                max_burst = obligation * 2
            if target > max_burst:
                target = max_burst

            guaranteed_bytes += target
            overflow = bytes_queued - target
            if overflow > 0:
                be_bytes += overflow

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes

    def _ul_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int, float, int, int]:
        """UL GBR deficit accumulate/cap/target-spread/overflow-to-BE,
        remaining-PDB, (as of commit 3a) worst-case priority-weighted
        urgency, (as of commit 4a) gbr_below's own reverse-scan input,
        and (as of commit 4b) B_eff's own grant-sizing target --
        gNB_scheduler_ulsch.c:2196-2280 (two-tier's own file)
        and ia_p5g_scheduler.c's own inlined UL ranking loop (:2570-2674,
        commented "unchanged from original pf_ul()" -- checked, not
        trusted: byte-diffed the deficit/PDB/target arithmetic
        specifically (:2649-2672 vs. gNB_scheduler_ulsch.c:2231-2260) and
        confirmed the claim holds exactly for what it describes. The
        claim's SCOPE is narrower than the block it sits in, though --
        ia_p5g_scheduler.c interleaves genuinely new logic in the same
        loop (the priority-weighted urgency computation this method now
        also folds in, :2576-2647) that the "unchanged" comment does not
        cover; don't over-read "unchanged" as "the whole block is a
        verbatim copy."

        Deficit/PDB arithmetic confirmed byte-identical, by direct diff,
        to oai-branches/reservation/gNB_scheduler_ulsch.c's own version
        -- adapted line-for-line from reservation.py::_ul_gbr_and_pdb
        (same int-ms-truncation discipline, same per-LCG gate on
        estimated_ul_buffer_per_lcg > 0, same first-flow-found-wins-a-
        shared-LCG dedup), not re-derived.

        Urgency (ia_p5g_scheduler.c:2576-2647, new in this commit):
        u_lcg = clamp(1 - remaining_pdb/pdb_ms, 0, 1), computed for
        EVERY active LCG regardless of GBR status -- only the delta term
        below branches on it. priority_weight is a linear ramp from
        _URG_PRIO_W_MIN (low priority) to 1.0 (priority 1), clamped.
        delta = 1.0 for non-GBR flows; for GBR flows,
        _URG_GBR_FLOOR + (1-_URG_GBR_FLOOR) * min(1, deficit/window) --
        reusing the SAME deficit/window this method already computes,
        one pass, matching the C's own single-pass organization rather
        than a second duplicate walk. worst_urgency01 is the max of
        u_lcg * priority_weight * delta over this UE's active LCGs.

        gbr_bytes_slot (ia_p5g_scheduler.c:2710-2722): has_pending_gbr-
        gated MAX (not sum) over GBR-configured, currently-backlogged
        LCGs of floor(gfbr_bps/8/slots_per_sec) -- the SAME per-LCG
        quantity this method's own `obligation` local already computes,
        tracked by MAX instead of accumulated, and WITHOUT
        `obligation`'s own max(1, ...) floor (ported bug-for-bug,
        matching reservation.py's own already-landed identical port).
        Returns the real int value as of commit 4b (was a bare bool at
        commit 4a -- gbr_below's own reverse scan only needed the
        boolean then; B_eff's own floor, commit 4b, needs the numeric
        value too). Confirmed always 0 on this corpus -- mfbr_bps is
        never configured on any flow in any scenario in this repo
        (module docstring) -- ported anyway as real, testable
        machinery, not skipped.

        ul_total_target_bytes (ia_p5g_scheduler.c:2574,2649-2670,
        commit 4b): a THIRD accumulator, distinct from guaranteed_
        bytes/be_bytes above despite the similar shape -- confirmed by
        reading both side by side, not assumed. For a GBR LCG, adds the
        SAME capped `target` guaranteed_bytes already accumulates -- no
        divergence there. For a non-GBR LCG, adds the SAME raw
        `lcg_estimate` be_bytes already accumulates -- no divergence
        there either. The divergence is specifically the GBR-LCG
        overflow term: be_bytes additionally adds `overflow =
        lcg_estimate - target` when positive; ul_total_target_bytes
        does NOT -- only the capped target counts toward it. This port's
        own port-map row 46 said guaranteed_bytes+be_bytes would be
        "reused directly" for this consumption -- checked here, not
        executed unchecked, and found wrong (module docstring's own
        self-inflicted-finding note).

        Returns a 7-tuple now: (has_gbr, remaining_pdb_ms,
        guaranteed_bytes, be_bytes, worst_urgency01, gbr_bytes_slot,
        ul_total_target_bytes) -- guaranteed_bytes/be_bytes still real
        but unconsumed by B_eff specifically (their own correctness is
        unaffected by anything since commit 3 -- checked, not assumed);
        worst_urgency01 feeds _finalize_ul_coef; gbr_bytes_slot feeds
        gbr_below's reverse scan AND B_eff's own floor;
        ul_total_target_bytes feeds B_eff's own base term
        (_allocate_direction, commit 4b).
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0
        has_pending_gbr = self._ul_has_pending_gbr(ue_id, buffers)

        seen_lcgs: set[int] = set()
        has_gbr = False
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0
        worst_urgency01 = 0.0
        gbr_bytes_slot_max = 0
        ul_total_target_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            lcg_estimate = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if lcg_estimate <= 0:
                continue
            seen_lcgs.add(f.lcg)

            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.ul_lcg_last_grant_slot.get(f.lcg)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            u_lcg = max(0.0, min(1.0, 1.0 - remaining_pdb / pdb_ms))
            priority_weight = _URG_PRIO_W_MIN + (1.0 - _URG_PRIO_W_MIN) * (
                1.0 - (f.priority_level - 1) / (_URG_PRIO_MAX - 1)
            )
            priority_weight = max(_URG_PRIO_W_MIN, min(1.0, priority_weight))

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += lcg_estimate
                # ul_total_target_bytes (:2667-2669) -- the non-GBR
                # branch adds the SAME raw lcg_estimate be_bytes does;
                # no divergence here (module docstring's own note --
                # the divergence is GBR-only, below).
                ul_total_target_bytes += lcg_estimate
                worst_urgency01 = max(worst_urgency01, u_lcg * priority_weight)
                continue

            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.ul_lcg_deficit_bytes.get(f.lcg, 0) + obligation
            window = obligation * int(pdb_ms / slot_ms)
            deficit = min(deficit, window)
            state.ul_lcg_deficit_bytes[f.lcg] = deficit
            if deficit > 0:
                has_gbr = True

            # gbr_bytes_slot (:2710-2722) -- same per-LCG rate as
            # obligation above, MAX-tracked (not accumulated), WITHOUT
            # obligation's own max(1, ...) floor -- ported bug-for-bug.
            gbr_bytes_slot_max = max(
                gbr_bytes_slot_max, int((f.gfbr_bps / 8.0) / slots_per_sec)
            )

            delta = _URG_GBR_FLOOR + (1.0 - _URG_GBR_FLOOR) * (
                min(1.0, deficit / window) if window > 0 else 0.0
            )
            worst_urgency01 = max(worst_urgency01, u_lcg * priority_weight * delta)

            rem_slots = int(remaining_pdb / slot_ms)
            if rem_slots < 1:
                rem_slots = 1
            target = (deficit + obligation) // rem_slots
            if target < obligation:
                target = obligation
            max_burst = int((f.mfbr_bps / 8.0) / slots_per_sec) * 2
            if max_burst < obligation * 2:
                max_burst = obligation * 2
            if target > max_burst:
                target = max_burst

            guaranteed_bytes += target
            # ul_total_target_bytes (:2666) -- the GBR branch adds only
            # the capped `target`, matching guaranteed_bytes's own
            # contribution exactly -- NOT the overflow term below,
            # which be_bytes alone accumulates. This is the confirmed
            # divergence (module docstring's own row-46 correction).
            ul_total_target_bytes += target
            overflow = lcg_estimate - target
            if overflow > 0:
                be_bytes += overflow

        gbr_bytes_slot = gbr_bytes_slot_max if has_pending_gbr else 0
        return (
            has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes,
            worst_urgency01, gbr_bytes_slot, ul_total_target_bytes,
        )

    def _dl_stamp(
        self, fills: list[tuple[int, int]], ue_id: int, slot_index: int,
    ) -> None:
        """Last-grant-slot stamping only. Needed so _dl_gbr_and_pdb's
        remaining_pdb computation reflects real grant history instead of
        "never granted" every cycle. Gated per filled flow, matching
        reservation.py::_dl_drain_and_stamp's own (found-and-fixed)
        stamp gate -- stamps only flows _dl_fill actually gave bytes to,
        not every flow of a granted UE.
        """
        state = self._ue_state[ue_id]
        for qfi, _byts in fills:
            state.dl_flow_last_grant_slot[qfi] = slot_index

    def _dl_drain(
        self, fills: list[tuple[int, int]], ue_id: int, bler: float,
    ) -> None:
        """ia_p5g_drain_vq_dl, ia_p5g_scheduler.c:2002-2035 -- per-LCID,
        (1-bler)-discounted. As of commit 5, ``fills`` is the real
        (priority ASC, vq_dl DESC) LCP order (``_dl_fill``), not the
        commit-1 placeholder this method drained against from commit 3a
        through commit 4b -- the arithmetic here was always faithful,
        only its input has now caught up (module docstring's own
        "joint VQ-correction commit" note).
        """
        state = self._ue_state[ue_id]
        delivery_rate = max(0.0, min(1.0, 1.0 - bler))
        for qfi, byts in fills:
            delivered_bits = byts * 8.0 * delivery_rate
            state.vq_dl[qfi] = max(0.0, state.vq_dl.get(qfi, 0.0) - delivered_bits)

    def _dl_deficit_drain(
        self, fills: list[tuple[int, int]], ue_id: int,
    ) -> None:
        """gNB_scheduler_dlsch.c:1417-1427 -- drains dl_flow_deficit_bytes
        by the real per-flow delivered bytes (fills, the real LCP order
        as of this commit), gated implicitly on fills' own "only flows
        that got bytes" contract (if take > 0: fills.append(...),
        _dl_fill). The unconditional max(0, ...) form is a confirmed-
        equivalent simplification of the C's `if (deficit>0): -=;
        if(<0): =0` -- deficit is provably never negative anywhere else
        it's written (the accumulation step's own window-cap floors at
        0, and it's the only other writer), so the two forms are
        identical; a provably-redundant guard, same category as
        docs/oai-port-map.md row 27's reservation one and _ul_deficit_
        drain's own identical simplification above.
        """
        state = self._ue_state[ue_id]
        for qfi, byts in fills:
            state.dl_flow_deficit_bytes[qfi] = max(
                0, state.dl_flow_deficit_bytes.get(qfi, 0) - byts
            )

    def _ul_served_split(
        self, ue_id: int, buffers: BufferView, tbs_bytes: int,
    ) -> list[tuple[int, int]]:
        """post_process_ulsch, gNB_scheduler_ulsch.c:2756-2802 -- commit 5.

        A genuine greedy priority-order allocation walk, NOT a
        proportional split (that's _ul_drain/ia_p5g_drain_vq_ul, a
        DIFFERENT mechanism on the SAME tb_size -- ground truth runs
        both, independently, and this port keeps them independent too)
        and NOT reservation.py's own drain (which credits the FULL
        tb_size to every active LCG -- CLAUDE.md's "port the code not
        the comment" rule, a documented bug in reservation's own C).
        Two-tier's own C comment (:2743-2746) names that exact bug as
        "the old bug" and this walk as its fix -- the two OAI branches'
        C genuinely differ here, not a porting error on either side.

        Build the active-LCG set (estimated_ul_buffer_per_lcg > 0,
        deduped by LCG via self._flows, same pattern _ul_gbr_and_pdb/
        _ul_drain already use), sort ascending by the representative
        flow's priority_level, then walk tbs_bytes: each LCG in order
        gets served = min(remaining, available). Only LCGs with
        served > 0 are returned -- a TB too small to reach every active
        LCG leaves the rest out entirely, feeding both the stamp and
        the deficit drain below.

        Tie-break note: every 5QI in FIVE_QI_PRIORITY has a distinct
        priority value (scheduler/flow.py), so a tie requires two
        DIFFERENT LCGs whose representative flows both fall back to
        DEFAULT_PRIORITY_LEVEL -- unreached on this corpus, not chased
        further. Python's stable sort (LCG-ascending among ties) is not
        proven identical to the C's own non-stable exchange sort in
        that case; flagged, not fixed, since it's provably unreachable
        here.
        """
        candidates: list[tuple[int, int, int]] = []  # (priority, lcg, available)
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            available = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if available <= 0:
                continue
            seen_lcgs.add(f.lcg)
            candidates.append((f.priority_level, f.lcg, available))
        candidates.sort(key=lambda c: c[0])

        served: list[tuple[int, int]] = []
        remaining = tbs_bytes
        for _priority, lcg, available in candidates:
            if remaining <= 0:
                break
            s = min(remaining, available)
            if s <= 0:
                continue
            served.append((lcg, s))
            remaining -= s
        return served

    def _ul_stamp(
        self, served: list[tuple[int, int]], ue_id: int, slot_index: int,
    ) -> None:
        """Last-grant-slot stamping, gated on served > 0 -- corrects a
        bug in commit 3's own port, found scoping commit 5.

        Commit 3 gated this on estimated_ul_buffer_per_lcg > 0 ("every
        active LCG"), copied from reservation.py::_ul_drain_and_stamp's
        own gate -- CORRECT there, since reservation credits every
        active LCG the full tb_size regardless of priority, so "active"
        and "served" coincide trivially. Two-tier's own C does NOT
        coincide: post_process_ulsch's greedy priority walk (see
        _ul_served_split) means a small TB with 2+ active LCGs only
        serves the highest-priority one(s) -- a lower-priority active
        LCG is not stamped in the C, but was stamped by this port's own
        prior code, inflating its apparent freshness and shrinking
        _ul_gbr_and_pdb's remaining_pdb incorrectly. A fourth instance
        of "a mechanism copied from reservation's own pattern without
        checking two-tier's own, structurally different C" (after
        FIX-2 vs. follower budget, B_eff vs. _ul_grant_target). No test
        named _ul_stamp or referenced ul_lcg_last_grant_slot directly
        before this commit -- exercised only indirectly through
        _ul_gbr_and_pdb's own consumption, so four commits (3, 3a, 4,
        4a) passed with this gap unexercised.
        """
        state = self._ue_state[ue_id]
        for lcg, _byts in served:
            state.ul_lcg_last_grant_slot[lcg] = slot_index

    def _ul_deficit_drain(
        self, served: list[tuple[int, int]], ue_id: int,
    ) -> None:
        """post_process_ulsch, gNB_scheduler_ulsch.c:2795-2800 -- drains
        ul_lcg_deficit_bytes by the modelled served bytes (from
        _ul_served_split), NOT the full tb_size -- the fix two-tier's
        own C comment names explicitly (see _ul_served_split). The
        unconditional max(0, ...) form is a confirmed-equivalent
        simplification of the C's `if (deficit>0): -=; if(<0): =0` --
        deficit is provably never negative anywhere else it's written
        (accumulation and the floor's own forgiveness both floor at 0),
        so the two forms produce identical results; a provably-
        redundant guard, the same category as docs/oai-port-map.md
        row 27's reservation one, not silently simplified.
        """
        state = self._ue_state[ue_id]
        for lcg, byts in served:
            state.ul_lcg_deficit_bytes[lcg] = max(
                0, state.ul_lcg_deficit_bytes.get(lcg, 0) - byts
            )

    def _ul_drain(
        self, ue_id: int, buffers: BufferView, tb_size_bytes: int,
    ) -> None:
        """ia_p5g_drain_vq_ul, ia_p5g_scheduler.c:3728-3769 -- proportional
        split of the FULL raw tb_size across active LCGs by BSR-buffer
        share (1/n_active fallback when total buffer reads 0). Confirmed
        by reading the whole function body this commit: NO bler discount
        anywhere in it, unlike DL's drain -- a genuine asymmetry, not an
        oversight. Iterates self._flows directly (same pattern as
        _ul_stamp), not a pre-filtered candidate list.
        """
        state = self._ue_state[ue_id]
        active: dict[int, int] = {}
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in active:
                continue
            buf = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if buf <= 0:
                continue
            active[f.lcg] = buf
        if not active:
            return
        total_buf = sum(active.values())
        grant_bits = tb_size_bytes * 8.0
        for lcg, buf in active.items():
            fraction = (buf / total_buf) if total_buf > 0 else (1.0 / len(active))
            state.vq_ul[lcg] = max(
                0.0, state.vq_ul.get(lcg, 0.0) - grant_bits * fraction
            )

    def _update_vq_dl(self, ue_id: int, buffers: BufferView) -> None:
        """ia_p5g_update_vq_dl, ia_p5g_scheduler.c:1835-1894 -- grow by
        Tier-1's DL target rate this slot, then clamp to the
        ARRIVAL-DELTA windowed ceiling (matches the header; see module
        docstring for the UL case, which does not). Ceiling inputs
        (_arr_hist/_del_hist) are frozen once per Tier-1 cycle inside
        _compute_demand_bps, not updated here -- confirmed directly
        against the C: dl_arrived_hist/dl_delivered_hist are written
        only inside the Tier-1 demand block (:1264-1265), read-only in
        this function. LCID < 4 (SRBs) skipped.
        """
        state = self._ue_state[ue_id]
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            r_bps = self._targets_bps.get((f.ue_id, f.qfi), 0.0)
            vq = state.vq_dl.get(f.qfi, 0.0) + r_bps * self.slot_duration_s

            key = (f.ue_id, f.qfi)
            st = buffers.state(f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            arr_cum = del_cum + st.bytes_queued
            arr_w_bits = (arr_cum - self._arr_hist.get(key, 0.0)) * 8.0
            del_w_bits = (del_cum - self._del_hist.get(key, 0.0)) * 8.0
            target_w_bits = r_bps * _TIER1_PERIOD_S
            ceiling = max(0.0, min(arr_w_bits, target_w_bits) - del_w_bits)

            state.vq_dl[f.qfi] = max(0.0, min(vq, ceiling))

    def _update_vq_ul(self, ue_id: int, buffers: BufferView) -> None:
        """ia_p5g_update_vq_ul, ia_p5g_scheduler.c:3578-3687 -- grows
        identically to DL, but the ceiling is the BACKLOG-BOUND/CATCHUP
        form (the bugfix, :3608-3654), not arrival-delta -- confirmed
        again this commit: the function no longer reads ul_arrived_hist/
        arr_W at all. See module docstring for the full in-code
        rationale (starvation collapses arrival-delta to ~0 exactly when
        the evidence of starvation is most needed) -- this is the
        second of this port's four documented comment-vs-code instances;
        port the code, not the header. Catch-up horizon is
        _VQ_UL_CATCHUP_N Tier-1 windows. LCG 0 excluded structurally (no
        FlowConfig models SRB traffic, same convention _ul_gbr_and_pdb/
        _ul_stamp already use), lcid = lcg + 3, per-LCG gate on
        estimated_ul_buffer_per_lcg > 0.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            st = buffers.state(f.ue_id, f.qfi)
            if st.estimated_ul_buffer_per_lcg <= 0:
                continue
            seen_lcgs.add(f.lcg)

            r_bps = self._targets_bps.get((f.ue_id, f.qfi), 0.0)
            vq = state.vq_ul.get(f.lcg, 0.0) + r_bps * self.slot_duration_s

            key = (f.ue_id, f.qfi)
            del_cum = buffers.delivered_cum(f.ue_id, f.qfi)
            del_w_bits = (del_cum - self._del_hist.get(key, 0.0)) * 8.0
            target_w_bits = r_bps * _TIER1_PERIOD_S
            backlog_bits = st.estimated_ul_buffer_per_lcg * 8.0
            catchup_w_bits = _VQ_UL_CATCHUP_N * target_w_bits
            ceiling = max(0.0, min(backlog_bits, catchup_w_bits) - del_w_bits)

            state.vq_ul[f.lcg] = max(0.0, min(vq, ceiling))

    def _ul_base_q(self, ue_id: int, buffers: BufferView) -> float:
        """ia_p5g_ul_metric, ia_p5g_scheduler.c:3696-3726 -- Sigma vq_ul
        over LCGs where EITHER estimated_ul_buffer_per_lcg > 0 OR
        vq_ul > 0 (the OR-gate starvation-prevention bugfix, cited
        incident: "d639 zero grants for 55s"). Iterates self._flows
        directly, not a pre-filtered candidate flow list -- matching
        _ul_stamp/_ul_gbr_and_pdb's own established pattern: a flow
        whose BSR has decayed to zero (and so was excluded from this
        UE's candidate flow list upstream, by the bytes_reported > 0
        pre-filter in _allocate_direction) must still contribute here
        if its vq_ul is still positive. NOTE: that upstream pre-filter
        is itself NOT OR-gate-aware in general -- a UE with zero
        bytes_reported on EVERY UL flow never becomes a candidate via
        this method's own OR-gate, only via some OTHER flow clearing the
        gate. As of commit 4, a narrower path exists for exactly this
        case too: the UL floor's own candidacy-rescue pre-pass
        (_allocate_direction) can add such a UE back in when the floor
        fires -- gated on has_pending_gbr/theta/arming, not on this
        method's OR-gate. Still flagged as a known caveat (README.md
        sec8) for the GENERAL case (a non-GBR UE, or a GBR UE the floor
        hasn't armed for yet), not fully closed.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        total = 0.0
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            seen_lcgs.add(f.lcg)
            buf = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            vq = state.vq_ul.get(f.lcg, 0.0)
            if buf <= 0 and vq <= 0.0:
                continue
            total += vq
        return total

    def _ul_has_pending_gbr(self, ue_id: int, buffers: BufferView) -> bool:
        """update_ul_qos_priority, gNB_scheduler_ulsch.c:42-71 (found in
        the full OAI checkout -- the vendored two-tier subset never
        assigns this field). A UE-level EXISTENCE check, recomputed
        fresh every call: true if ANY LCG with CURRENT
        estimated_ul_buffer_per_lcg > 0 is configured with gbr_ul_max >
        0 (MFBR-keyed, i.e. mfbr_bps here) -- a simpler, different test
        from _ul_gbr_and_pdb's has_gbr (GFBR-keyed, deficit-accumulated
        over time). This is the floor's own arming gate, and it reads
        the SAME per-LCG estimate the floor exists to route around --
        see module docstring and _update_ul_floor's own docstring for
        the flagged, not-resolved consequence.
        """
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL":
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            if f.mfbr_bps > 0:
                return True
        return False

    def _ul_rx_bytes(self, ue_id: int, buffers: BufferView) -> int:
        """ia_p5g_scheduler.c:2329-2331 -- Sigma UL data-LCID MAC bytes
        delivered (cumulative), one representative flow per LCG (D1's
        LCG-aggregate convention, same dedup pattern _ul_stamp/
        _ul_drain already use). The floor's own delivery-evidence
        signal -- movement here is what re-arms/resets the state
        machine, independent of any BSR/estimate-derived quantity.
        """
        seen_lcgs: set[int] = set()
        total = 0
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            seen_lcgs.add(f.lcg)
            total += buffers.delivered_cum(f.ue_id, f.qfi)
        return total

    def _ul_best_pending_pdb_ms(self, ue_id: int, buffers: BufferView) -> int:
        """update_ul_qos_priority, gNB_scheduler_ulsch.c:42-71 -- the
        PDB of the HIGHEST-PRIORITY currently-backlogged LCG (not
        literally "lowest PDB" despite the C struct field's own inline
        comment). Own 100ms fallback (_UL_FLOOR_PDB_FALLBACK_MS),
        confirmed a DIFFERENT constant from _PDB_FALLBACK_MS (300ms,
        used elsewhere in this file for a different purpose) -- two
        independently-chosen fallbacks in the same C file.
        """
        best_priority: int | None = None
        best_pdb = 9999
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL":
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            if best_priority is None or f.priority_level < best_priority:
                best_priority = f.priority_level
                best_pdb = int(f.pdb_ms) if f.pdb_ms > 0 else 9999
        if best_pdb <= 0 or best_pdb >= 9999:
            best_pdb = _UL_FLOOR_PDB_FALLBACK_MS
        return best_pdb

    def _update_ul_floor(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int]:
        """ia_p5g_scheduler.c:2306-2530 -- the UL service-interval
        floor's per-UE arm/fire logic (v2). Gated on has_pending_gbr --
        if that fails, the C skips the WHOLE block, so no arming state
        advances this slot either; ported the same way (early return,
        nothing touched). transm_interrupt has no simulator analogue
        (structurally absent, same category as do_sched) -- its guard
        is always-true here, so it's omitted rather than modeled as an
        inert variable.

        B (backlog evidence) is this UE's bytes_reported summed across
        UL flows -- the same quantity _allocate_direction's own
        top-level candidacy pre-filter already treats as "empty" when
        <= 0 (D1's bytes_reported<->B correspondence). do_sched is
        structurally absent (commit 3's finding), so ground truth's
        `_empty = (B==0 && !do_sched)` collapses to exactly `B==0` --
        exactly the candidacy pre-filter's own gate. This is the fact
        the candidacy-rescue pre-pass in _allocate_direction depends on.

        Absolute-slot wraparound (real hardware wraps at 1024 frames)
        is dropped -- this simulator's slot_index has no such limit, a
        hardware-counter artifact, not a fidelity loss (same
        simplification category _ul_gbr_and_pdb's own age arithmetic
        already uses). A never-yet-armed UE's silence is treated as 0
        rather than the C's huge zero-init sentinel -- observably
        equivalent, since `armed` is also False until first delivery is
        observed, so neither form can fire on a UE's first-ever visit.

        Returns (fired, silence_slots_at_fire).
        """
        state = self._ue_state[ue_id]
        if not self._ul_has_pending_gbr(ue_id, buffers):
            return False, 0

        slot_ms = self.slot_duration_s * 1000.0
        rx = self._ul_rx_bytes(ue_id, buffers)
        b = sum(
            buffers.state(f.ue_id, f.qfi).bytes_reported
            for f in self._flows
            if f.ue_id == ue_id and f.direction == "UL"
        )

        sil = (
            0 if state.floor_last_move_slot is None
            else max(0, slot_index - state.floor_last_move_slot)
        )
        if rx != state.floor_rx_lastseen:
            state.floor_rx_lastseen = rx
            state.floor_last_move_slot = slot_index
            state.floor_alive_slot = slot_index
            state.floor_fruitless = 0
            state.floor_disarmed = False
            sil = 0

        alive_max = _UL_FLOOR_ALIVE_MS / slot_ms
        armed = (
            state.floor_alive_slot is not None
            and (slot_index - state.floor_alive_slot) <= alive_max
        )

        if b > 0:
            state.floor_disarmed = False
            state.floor_fruitless = 0
        if not armed:
            state.floor_last_move_slot = slot_index
            sil = 0

        pdb_ms = self._ul_best_pending_pdb_ms(ue_id, buffers)
        theta = max(
            _UL_FLOOR_MIN_SLOTS,
            round((pdb_ms / _UL_FLOOR_PDB_DIV) / slot_ms),
        )

        fr_decay = max(1, round(_UL_FLOOR_FRUITLESS_DECAY_MS / slot_ms))
        if state.floor_fruitless > 0:
            fr_age = (
                0 if state.floor_fruitless_slot is None
                else max(0, slot_index - state.floor_fruitless_slot)
            )
            steps = fr_age // fr_decay
            if steps > 0:
                state.floor_fruitless = max(0, state.floor_fruitless - steps)
                state.floor_fruitless_slot = slot_index
                if state.floor_fruitless == 0:
                    state.floor_disarmed = False

        shift = min(state.floor_fruitless, _UL_FLOOR_FRUITLESS_SHIFT_MAX)
        theta_eff = theta << shift

        adq_age = (
            0 if state.floor_adq_slot is None
            else max(0, slot_index - state.floor_adq_slot)
        )
        if state.floor_adq_backoff > 0 and adq_age >= fr_decay:
            asteps = adq_age // fr_decay
            state.floor_adq_backoff = max(0, state.floor_adq_backoff - asteps)

        adq_shift = min(state.floor_adq_backoff, _UL_FLOOR_FRUITLESS_SHIFT_MAX)
        adq_period = theta_eff << adq_shift

        adq_fire = (
            armed and b > 0
            and state.floor_crumb_run >= _UL_FLOOR_ADQ_CRUMB_RUN
            and adq_age >= adq_period
        )
        empty_fire = armed and b == 0 and sil >= theta_eff

        if not (empty_fire or adq_fire):
            return False, 0

        if (
            state.floor_fruitless >= _UL_FLOOR_FRUITLESS_MAX
            and not state.floor_disarmed
        ):
            state.floor_disarmed = True
            state.ul_lcg_deficit_bytes = {
                lcg: 0 for lcg in state.ul_lcg_deficit_bytes
            }

        state.floor_last_move_slot = slot_index
        if adq_fire:
            state.floor_adq_slot = slot_index
            state.floor_crumb_run = 0
            if state.floor_adq_backoff <= _UL_FLOOR_FRUITLESS_SHIFT_MAX:
                state.floor_adq_backoff += 1
        else:
            if state.floor_fruitless <= _UL_FLOOR_FRUITLESS_SHIFT_MAX:
                state.floor_fruitless += 1
            state.floor_fruitless_slot = slot_index

        return True, sil

    def _ul_floor_track_crumb_run(self, ue_id: int, prbs_used: int) -> None:
        """ia_p5g_scheduler.c:3315-3323 -- ADQ's trickle detector: a RUN
        of consecutive <=min_rb grants is the crumb signature; any
        larger grant resets it. Runs at grant-COMMIT time (the actual
        PRBs granted this slot), not selection time -- same "stamp/drain
        at grant-emission time" pattern _ul_stamp/_ul_drain already use.
        """
        state = self._ue_state[ue_id]
        if prbs_used <= self.min_rb:
            state.floor_crumb_run += 1
        else:
            state.floor_crumb_run = 0

    def _emit_grant(
        self,
        ue_id: int,
        direction: str,
        prbs_used: int,
        tbs_bytes: int,
        ue_flows: list[FlowConfig],
        buffers: BufferView,
        cce_cost: int,
        snr_used_db: float,
        slot_index: int,
        bler: float,
    ) -> list[Allocation]:
        if direction == "UL":
            served = self._ul_served_split(ue_id, buffers, tbs_bytes)
            self._ul_stamp(served, ue_id, slot_index)
            self._ul_deficit_drain(served, ue_id)
            self._ul_drain(ue_id, buffers, tbs_bytes)
            self._ul_floor_track_crumb_run(ue_id, prbs_used)
            # The gNB sizes the block; the UE fills it (TS 38.321
            # sec5.4.3.1). sim/ue_lcp.py performs the real split on the
            # driver side -- unchanged from the pre-rewrite file's own
            # convention, see module docstring and docs/phase2-plan.md
            # sec3/D1.
            return [
                Allocation(
                    ue_id=ue_id, qfi=-1, direction=direction,
                    prbs=prbs_used, bytes_capacity=tbs_bytes,
                    cce_cost=cce_cost, snr_used_db=snr_used_db,
                    ue_grant=True,
                )
            ]

        fills = self._dl_fill(ue_flows, tbs_bytes, buffers)
        self._dl_stamp(fills, ue_id, slot_index)
        self._dl_drain(fills, ue_id, bler)
        self._dl_deficit_drain(fills, ue_id)
        out: list[Allocation] = []
        for i, (qfi, byts) in enumerate(fills):
            out.append(
                Allocation(
                    ue_id=ue_id, qfi=qfi, direction=direction,
                    prbs=prbs_used if i == 0 else 0,
                    bytes_capacity=byts,
                    cce_cost=cce_cost if i == 0 else 0,
                    snr_used_db=snr_used_db,
                )
            )
        return out

    def _dl_fill(
        self, ue_flows: list[FlowConfig], tbs_bytes: int, buffers: BufferView
    ) -> list[tuple[int, int]]:
        """The real single-pass SRB-exempt LCP fill,
        ``ia_p5g_compute_lcp_budget``, ``ia_p5g_scheduler.c:1945-2000``
        -- landed commit 5, replacing commit 1's placeholder. Sort DRBs
        ``(priority ASC, vq_dl DESC)``, greedy ``min(backlog,
        remaining)`` per flow -- structurally identical to the
        placeholder it replaces (same sort-then-greedy shape); the ONLY
        change is the tiebreak field, ``-bytes_queued`` to ``-vq_dl``.
        Pass 0 (SRB) is not applicable -- ``FlowConfig`` has no SRB
        representation, same disposition as ``reservation.py``'s own
        commit 6 (``docs/oai-port-map.md`` row 31).
        """
        order = sorted(
            ue_flows,
            key=lambda f: (
                f.priority_level,
                -self._ue_state[f.ue_id].vq_dl.get(f.qfi, 0.0),
            ),
        )
        fills: list[tuple[int, int]] = []
        remaining = tbs_bytes
        for f in order:
            if remaining <= 0:
                break
            backlog = buffers.state(f.ue_id, f.qfi).bytes_queued
            take = min(backlog, remaining)
            if take > 0:
                fills.append((f.qfi, take))
                remaining -= take
        return fills
