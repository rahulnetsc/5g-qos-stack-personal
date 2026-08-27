"""Reservation 5G QoS scheduler -- built fresh from ``oai-branches/reservation/``.

Phase 2 (``docs/phase2-plan.md``): unlike ``two_tier.py``, no prior Python
exists for this scheduler at all. This module is built up commit by commit,
each one landing a single mechanism from the vendored C source; see
``docs/oai-port-map.md``'s "Phase 2 -- reservation" section for the
file:line correspondence and ``docs/phase2-plan.md`` sec4 for the full
checklist.

Commit 1 built: ``Scheduler`` protocol conformance, per-UE throughput
state, and the bare PF coefficient as the only ranking criterion.

Commit 2 (this commit) adds sort tiers ABOVE the coefficient -- but only
the tiers this simulator can actually source. Ground truth is 5 tiers on
UL (SRB -> liveness -> GBR -> sched_inactive-last -> PDB/coef) and 4 on
DL (SRB -> liveness(TA) -> GBR -> PDB/coef; DL genuinely has no
sched_inactive tier at all, confirmed absent by reading
gNB_scheduler_dlsch.c's UEsched_t struct directly, not merely expressed
differently). Two tiers are current no-ops, for two DIFFERENT reasons,
both recorded as README.md sec8 [OPEN: PHASE2] entries rather than
silently approximated:

- ``has_srb`` (T1, top tier, BOTH directions): hardcoded False. This
  simulator has no SRB/RRC-signaling traffic model at all --
  ``scheduler/flow.py::FlowConfig`` only ever represents a QFI-based DRB,
  and the LCG0-holds-a-GBR-DRB case (FIVE_QI_LCG's QFI 1/3 mapping) is
  exactly what the C's own ``lcg0_is_drb`` check excludes from counting
  as SRB -- so even an "LCG==0" heuristic would be a wrong port, not a
  degraded one. A standing limitation, not a "revisit later" gap.
- ``liveness``/``sched_inactive`` (UL tiers 2/4, DL tier 2): need a
  ``do_sched``-equivalent (UL: SR-or-inactivity trigger for a
  zero-backlog UE) or a TA-pending signal (DL) that the ``Scheduler``
  protocol does not expose today. ``sim/ul_access.py``'s SR-report-floor
  is not a usable proxy -- verified it only fires when
  ``bytes_queued > 0`` (``sim/bsr.py:381-392``), i.e. for real backlog
  the estimate under-reports, not for a genuinely-empty UE. Unblocking
  this is a cross-cutting ``Scheduler``-protocol change affecting every
  scheduler, not a sort-tier-commit-sized change -- its own future
  commit if ever taken up.

Commit 3 (this commit) replaces the coarse GBR proxy with the real thing:
per-LCG (UL) / per-flow (DL) deficit accumulate/cap/target-spread/
overflow-to-BE, verified element-for-element against
``gNB_scheduler_ulsch.c:2251-2278`` / ``gNB_scheduler_dlsch.c:377-409``.
``has_gbr`` now means "this UE has an active unfulfilled deficit," not
"has a GBR flow with any backlog." This does NOT move either
comparator's tier position -- ``_ul_rank_key``/``_dl_rank_key`` are
untouched by this commit; only the *content* feeding their GBR slot
changed. Also fixes a real bug found scoping this commit: commit 2's
``pdb_ms`` used HOL delay as a stand-in for "remaining PDB," but ground
truth's ``ul_best_remaining_pdb_ms``/``dl_best_remaining_pdb_ms`` is
time-since-last-grant, a different quantity -- see
``docs/oai-port-map.md`` rows 18/19 for the full correction note.

What commit 3 deliberately does NOT do: wire ``guaranteed_bytes``/
``be_bytes`` into grant *sizing* (ground truth's own ``ul_target``/
``dl_target``, ``gNB_scheduler_ulsch.c:2496``/``_dlsch.c:1009``) -- grant
sizing stays backlog-based, same as every other scheduler in this repo,
pending a future commit (see ``docs/phase2-plan.md``'s reservation
checklist). Nor does it build the UL-only "silence detection" deficit
reset (``gNB_scheduler_ulsch.c:2286-2296``) or the post-grant deficit
*drain* (the already-known bug-for-bug full-``tb_size``-credit
mechanism, commit 5) -- last-grant-slot *stamping* lands here (needed to
fix the ``pdb_ms`` bug above), but *decrementing* the deficit on a grant
is a different field, cleanly separable, and stays commit 5's job.

Commit 3a corrects commit 3's arithmetic *type* (not its quantities):
the C computes this whole block in integers and truncates the grant age
to whole milliseconds before subtracting it, which matters because
``pdb_ms`` feeds a comparator tier -- see the truncation note above the
constants and ``docs/oai-port-map.md`` row 24.

Commit 4a wires commit 3's ``guaranteed_bytes``/``be_bytes`` (previously
computed and discarded) into grant *sizing* as the
``nr_find_nb_rb``-equivalent target
(``gNB_scheduler_ulsch.c:2492-2512``/``_dlsch.c:1003-1019``), replacing
the prior backlog-only sizing (identical in mechanism to
``sim/baselines/pf.py``'s own). Three decisions, made with the user
before writing this commit:

- The target sizes PRBs, not delivered bytes: ``prbs_needed =
  ceil(target*8/bits_per_rb)``, but ``tbs_bytes`` stays
  ``min(ue_backlog, capacity)`` -- the C grants PRBs for bytes not yet
  in the buffer when a deficit-carrying GBR flow pushes the target
  above real backlog; ported on the resource the scheduler controls,
  without manufacturing delivered bytes. Visible effect is PRB
  consumption (M11), not throughput.
- DL's ``oh = 3*4 + (ta_apply ? 2 : 0)`` is a flat ``12`` here -- no TA
  model exists (see the C's own "Fix me" comment: RLC doesn't report a
  PDU count). UL has no equivalent overhead term -- a real asymmetry.
- ``has_srb``'s control-only cap (``min(target, LCG0 estimate)`` UL,
  ``min(target, SRB1+SRB2+oh)`` DL) is built structurally, cited, but
  is a permanent no-op, since ``has_srb`` is hardcoded ``False`` -- the
  same treatment commit 2 gave the ``has_srb`` sort tier.

``gbr_bytes_slot`` (``:2304-2316``) is ported bug-for-bug: a MAX over
LCGs (not a sum), and it lacks the ``if (_obl < 1) _obl = 1`` floor the
deficit loop applies fifty-ish lines earlier in the same function
(``:2254``). Its whole loop is additionally gated on
``sched_ctrl->has_pending_gbr`` (``:2305``), set by a *separate*
per-LCG-deduped scan, ``update_ul_qos_priority`` (``:38-67``), keyed on
``c->gbr_ul_max > 0`` -- **MFBR**, not GFBR, and a different field from
``has_gbr``/``ul_has_unfulfilled_gbr``. Because that gate's own scan
dedups per LCG (breaks on the first matching LCID), whichever flow is
first in a shared LCG is the one whose ``mfbr_bps`` decides whether the
gate opens at all. Net effect: ``gbr_bytes_slot`` is inert on every
scenario in this repo today for two independent reasons -- no scenario
configures a nonzero ``mfbr_bps`` (row 23), and every scenario is
single-flow-per-LCG, so the shared-LCG dedup-vs-non-dedup asymmetry
that would let ``gbr_bytes_slot`` exceed ``guaranteed_bytes+be_bytes``
never arises either (single-LCG: ``target >= obligation >=
gbr_bytes_slot`` always, since ``gbr_bytes_slot`` is the same per-slot
rate as ``obligation`` minus only the ``max(1,...)`` floor).

A third unreachable branch, same category: ``if (ul_target < B)
ul_target = B`` (the "B is a floor" line) never fires on any
single-flow-per-LCG scenario either. ``guaranteed_bytes``/``be_bytes``
derive from the *ungated* ``estimated_ul_buffer_per_lcg``, so per LCG
``guaranteed+be == max(lcg_estimate, target) >= lcg_estimate``; ``B``
sums the *gated* ``bytes_reported``, and ``bytes_reported <=
estimated_ul_buffer_per_lcg`` by construction (WP3). So
``guaranteed+be >= B`` already, before this line runs, on any UE where
each LCG has exactly one flow. Reachable only in the shared-LCG case,
where ``ue_backlog`` sums ``bytes_reported`` once per *flow*
(double-counting a shared LCG's identical report) while the deficit
loop counts that LCG's estimate once.

Commit 4 lands the follower budget: a per-UE cap on granted PRBs so a
saturating BE UE cannot zero a starved UE ranked behind it
(``gNB_scheduler_ulsch.c:2414-2437``/``_dlsch.c:909-926``). Two
findings from reading the exact source, not captured by
``docs/phase2-plan.md``'s summary:

- **UL and DL's budget bases are different KINDS of quantity, not just
  a different ``min_rb`` source.** UL's base (``bi.bwpSize``, :2416) is
  a per-UE STATIC width, unaffected by what earlier-ranked candidates
  already consumed this slot (occupancy is tracked separately via a
  ``rballoc_mask`` bitmap this simulator doesn't have). DL's base
  (``max_rbSize``, :915-919) is a contiguous-free-RB SCAN from
  ``rbStart`` -- it DOES shrink as earlier grants land in the same
  slot. This simulator has no RB bitmap, just a decrementing
  ``prbs_left`` counter, so the faithful mapping is UL base ->
  ``slot.prb_count`` (the slot's fixed total pool), DL base ->
  ``prbs_left`` (the actual remaining pool AT THAT CANDIDATE'S TURN in
  the grant loop, not hoisted or captured once for the whole slot --
  using a fixed value for DL would silently collapse this asymmetry
  into UL's semantics).
- **``needs_service`` is structurally always-``True`` in this port
  today, both directions.** ``_allocate_direction``'s candidate list is
  pre-filtered to ``bytes_reported > 0`` before a ``_Candidate`` is
  ever built, so the backlog term dominates unconditionally, making
  ``or has_srb``/``or has_gbr``/``or ta_apply`` currently unreachable
  -- the same root cause as the existing ``do_sched``/liveness no-op (a
  B=0-but-``do_sched``-True candidate, which the C's own gate admits,
  never reaches our candidate list at all). Ported as the full formula
  anyway (a real ``_Candidate.needs_service`` field), not hardcoded
  ``True`` -- matching how ``has_srb``/``sched_inactive``/``ta_apply``
  are already ported as full-but-inert expressions elsewhere in this
  file. ``sched_inactive`` itself has no stored field anywhere in this
  module (confirmed absent from ``_ul_rank_key``'s actual tuple, not
  merely unused), so UL's ``max_rbSize`` init reduces in code to
  ``has_srb ? min_rb : bwp_size``.

DL's per-beam pre-check (``:877``, ``remainUEs``/``n_rb_sched``) is
**not applicable** -- no beam modeling exists anywhere in
``scheduler/``/``sim/`` (confirmed by grep). A different category from
"dormant but ported": there is no signal here to port at all.

``min_rb`` (UL's ``nrmac->min_grant_prb``) defaults to 5 --
**a deliberate operator/experimenter choice for the calibration
campaign** (set so no UE is starved of a grant and BSRs keep being
reported), not a physical constant and not a coincidence with the
config-parser's own ``defintval=5`` (``MACRLC_nr_paramdef.h:141`` in
the full OAI checkout, not the vendored subset -- the vendored four
``.c`` files have no assignment site for this at all). Corroborated
empirically by 486/486 ``NPRB 5`` lines in
``calibration-logs/twotier_startup_gnb.log``, whose own ``CMDLINE``
cites the exact deployed conf (``ci-scripts/conf_files/
gnb.sa.band78.106prb.rfsim.conf`` in that checkout) with no override
present. That log is a two-tier run; applying the value to reservation
is an inference (both branches read the same MACRLC-layer field), not
a direct observation -- would be falsified by a reservation-specific
config override not present in this checkout. DL's own ``min_rbSize=5``
(``:850``) is a SEPARATE constant, numerically identical but not the
same kind of quantity (source-fixed literal vs. operator choice) --
never unified into one shared constant.

Commit 5 lands the post-grant deficit drain, both directions --
genuinely different, not a shared mechanism with incidentally-matching
arithmetic:

- **UL is the already-known bug, confirmed directly, not inherited
  from the charter.** Comment at ``gNB_scheduler_ulsch.c:2772``, quoted
  verbatim: *"distribute tb_size drain proportionally across active
  LCGs."* The code (``:2769-2775``) does not divide -- it subtracts
  the FULL ``tb_size`` from every active LCG's deficit independently.
  Ported bug-for-bug: the code, not the comment.
- **DL is genuinely correct, confirmed directly** (``:1451-1460``) --
  "drain GBR deficit by bytes actually delivered," and the code does
  exactly that: each LC's deficit drains by the real, per-LC bytes
  ``_dl_fill`` (this module's placeholder two-pass LCP, commit 6's job
  to replace) actually gave it, never a shared or aggregate amount.
  No comment/code mismatch here; not the UL shortcut, ported anyway.
- **A found-and-fixed asymmetry in the OTHER direction from the known
  one, in commit 3's own stamping, not the drain itself.** Both
  directions' stamp+drain are gated identically (``if (cur_harq->round
  == 0)`` UL, the ``else { /* initial transmission */ }`` branch DL --
  a genuine symmetry, not an asymmetry, and a non-issue for this port:
  every grant ``allocate()`` emits is that case, since retransmissions
  never reach the candidate-building/grant-sizing code at all -- they
  are serviced by the driver's own HARQ seam before ``scheduler.
  allocate()`` is ever called, the same "confirmed not a porting gap"
  finding ``docs/phase2-plan.md`` sec2.1 already records). But WITHIN
  that shared gate, UL and DL are gated on genuinely different
  conditions, and commit 3's existing stamp code got BOTH wrong, in
  OPPOSITE directions:
  - UL's true gate is ``estimated_ul_buffer_per_lcg > 0`` (every active
    LCG, regardless of which one's report happened to trigger the
    grant) -- commit 3's stamp iterated the candidate's ``c.flows``
    instead, which is filtered to ``bytes_reported > 0`` (the
    crumb-gated view) and is therefore a possibly-STRICT SUBSET of the
    C's own set (``bytes_reported <= estimated_ul_buffer_per_lcg``
    always, WP3). Net effect: UNDER-stamping/under-draining -- an LCG
    with a real backlog but a crumb-gated zero report was silently
    skipped.
  - DL's true gate is ``lcid_bytes > 0`` (only the specific LC that
    actually received bytes in THIS fill) -- commit 3's stamp iterated
    ALL of ``c.flows`` unconditionally, a SUPERSET whenever ``_dl_fill``
    doesn't reach every eligible flow. Net effect: OVER-stamping -- a
    flow entirely starved of bytes this slot would have been stamped
    as if freshly served.
  Both corrected here, in the same commit as the drain itself, since
  the C updates stamp and drain together in one conditional block off
  one per-LCG/per-LC value (``tb_size`` UL, ``lcid_bytes`` DL) -- not
  two separable changes. UL's fix is dormant on every current scenario
  (needs a shared-LCG construction, the same H5 gap already flagged
  elsewhere). **DL's is not purely hypothetical**: the DRAIN half needs
  a GBR-class multi-DL-flow UE (no scenario has one), but the STAMP
  half feeds ``best_remaining_pdb`` for *every* DL flow regardless of
  GBR status -- ``sim/scenarios/scenario_config_6.yml``'s UE 10 already
  has two DL flows (qfi 9, qfi 82), so this bug would be live there,
  shifting PDB-tier sort order, the moment commit 10 wires this
  scheduler in.

Commit 6 replaces ``_dl_fill``'s placeholder with the real two-pass
SRB/DRB LCP (``gNB_scheduler_dlsch.c:1394-1463``). Findings beyond the
charter, from reading the full range and its surroundings, not just
the cited lines:

- **Genuinely two-pass, confirmed directly** -- the only ``qsort`` in
  this file is the inter-UE ``UE_sched`` comparator (``:847``); nothing
  reorders ``lc_config``. Unlike two-tier's DL LCP (single-pass despite
  its own header's "two-pass" comment), reservation's really is
  two-pass.
- **The DRB pass is NOT priority-sorted -- not in the charter.**
  "Existing lc_config order" (the C's own comment) means static,
  config-declared order. ``qc->priority`` feeds ``dl_best_priority``
  but is never assigned into ``UE_sched`` (checked every assignment
  directly, ``:834-841``) -- log-only (``:828``), zero scheduling
  effect. The placeholder this commit replaces
  (``sorted(ue_flows, key=(priority_level, -bytes_queued))``)
  implemented a rule the real hardware doesn't have. Ported: drop the
  sort, iterate in declared order.
- **The SRB pass is uncodable, not just dormant.** Every other
  ``has_srb`` no-op in this file has a real boolean (hardcoded
  ``False``) to be false about; here there is nothing to gate a pass-0
  filter on at all -- ``FlowConfig`` has no SRB representation.
  Recorded as **not applicable** (same category as commit 4's DL beam
  pre-check), not "dormant but ported."
- **No PBR/token-bucket state involved -- confirmed.** No bucket/PBR
  reference anywhere in the fill loop. ``sim/ue_lcp.py``'s own UL-only
  filter (``if f.direction != "UL": continue``, ``:63``) confirms
  ``FlowConfig.pbr_bps``/``bsd_ms``/``effective_pbr_bps()`` stay
  UL-only constructs; no new plumbing needed here.
- **Per-SDU MAC subheader overhead -- a quantified disagreement between
  two landed commits, not just an abstraction limit.** The C applies
  header overhead on BOTH sides of this mechanism: ``oh = 3*4`` at
  sizing time (``:1003-1019``, ported in 4a as
  ``_DL_LCP_FIXED_OVERHEAD_BYTES``) reserves headroom in the *target*
  for headers before PRBs are requested; ``sizeof(
  NR_MAC_SUBHEADER_LONG)`` per RLC chunk at fill time (this commit's
  own range) actually spends that headroom on real per-SDU headers,
  not payload. This port has the first (4a) but not the second (here)
  -- so ``_dl_fill`` treats the entire granted TB as payload, silently
  reclaiming the +12 bytes of header headroom 4a reserved and handing
  it out as extra payload instead. Directional, not neutral: this
  port's fill over-delivers relative to the C by roughly one MAC
  subheader's worth per SDU (~3 bytes for the common single-chunk
  case), always in the same direction -- never less. See
  ``docs/oai-port-map.md`` row 31.
- **Commit 5's hoist contract, verified to still hold.** The real fill
  keeps the exact ``if take > 0: fills.append(...)`` convention the
  placeholder already used -- a flow computing ``take == 0`` is never
  appended, preserving "one entry per flow that got bytes" for commit
  5's stamp/drain gating.
- **``FIVE_QI_PRIORITY``'s own reordering-fragility rationale
  (``scheduler/flow.py``) is UL-only, corrected there directly**: true
  for ``sim/ue_lcp.py``'s real priority sort, false for reservation's
  DL LCP -- a DL scenario's flow declaration order now silently IS the
  fill order, unguarded, by design. ``README.md`` sec8 records the
  consequence; the discriminating test below is what currently guards
  it.

Commit 8 (D2(a), ``docs/phase2-plan.md``) lands a real per-UE-per-
direction MCS-selection call site -- link adaptation has had no
persistent home anywhere in this scheduler until now (every prior
commit re-derives ``bits_per_rb``/``bler`` fresh from instantaneous SNR
every slot, nothing stored). Uses the existing static staircase
(``scheduler/link.py``'s new ``mcs_index_for_snr``, built as a thin
wrapper sharing ``_mcs_row_for_snr``'s one staircase-walk implementation
rather than a second, independent walk of ``_MCS_TABLE`` -- checked
before writing it, not assumed). ``sim/olla.py``'s own
``MCS_INDEX_COUNT = 12`` already matches this table's size exactly --
built against it from the start (WP5), so no table-size reconciliation
is needed here.

Computed at candidate-build time, matching the C's own timing
(``gNB_scheduler_ulsch.c:2192``, inside the per-UE ranking loop, before
the ``qsort`` -- for every candidate considered this slot, not just the
eventual winner). At commit 8 this was **not yet consumed by anything**:
grant sizing still read ``bits_per_rb``/``bler`` directly from
``bits_per_prb``, unchanged, making that commit doubly inert for two
independent reasons -- (1) nothing imports ``Reservation`` yet (the
standing reason, same as every prior commit in this lineage), (2) the
stored ``ul_mcs_index``/``dl_mcs_index`` value was written but never
read by anything in this module.

Commit 9 (D2(b)) removes reason (2) alone, not reason (1) -- scoring its
prediction must credit exactly that, not "nothing imports Reservation"
(still true). Grant sizing (both the PF-coefficient's hypothetical TBS
and the real grant's TBS -- ground truth's ``selected_mcs`` feeds both,
port-map row 15) now reads ``bits_per_prb_for_mcs(mcs_index, symbols)``
instead of recomputing ``bits_per_prb(snr, symbols)`` independently.

**OLLA's own ratchet is NOT wired in, and this is a considered
disposition, not a placeholder for a future commit to fill in.** Ground
truth's ``get_mcs_from_bler`` (``gNB_scheduler_primitives.c:785-822``,
byte-identical across both branches, ``sim/olla.py``'s own citation)
ratchets ``bler_stats->mcs`` by +-1 per ``BLER_UPDATE_FRAME`` (10-frame,
100ms) window, driven by ``NR_mac_dir_stats_t.rounds[0]``/``[1]`` --
new-tx and first-retry grant counts, incremented at grant-finalization
time (``gNB_scheduler_dlsch.c:1203`` / ``_ulsch.c:2756``, inside
``post_process_dlsch`` / the PUSCH PDU build -- NOT a separate ACK/NACK
feedback loop). In ground truth this is the SAME component that issues
both new-tx and retry grants (``pf_dl``/``pf_ul``), so both counts are
directly observable to it. That symmetry doesn't hold here: WP5 Decision
4 made retransmission scheduling an "orthogonal driver-level model, zero
required scheduler changes" -- retry grants are issued entirely by
``sim/driver.py``'s own HARQ seam and never reach ``Scheduler.
allocate()`` at all. Already confirmed directly, not assumed, by this
module's own commit-5 finding above: "every grant ``allocate()`` emits
is [round 0] ... retransmissions never reach the candidate-building/
grant-sizing code at all." So round-1 (retry) telemetry is structurally
unobservable here -- an architectural consequence specific to this
port's driver/scheduler split, not a missing ``Scheduler``-protocol hook
of the do_sched/TA kind (that class of gap is a signal ranking needs but
nothing supplies; this one is a grant class that never reaches this
component to begin with).

Given that, the ratchet's offset from ``mcs_index_for_snr``'s
instantaneous pick is PROVABLY zero, not merely initialized at zero:
``update_mcs_from_bler`` called with a round-counter pair that never
increments has ``num_dl_sched`` permanently 0, so the ``num_dl_sched <=
3`` branch fires every ``BLER_UPDATE_FRAME`` window and clamps at
``min_mcs`` immediately (``max(old_mcs - 1, min_mcs) == min_mcs`` from
the very first update, since ``old_mcs == min_mcs`` already) -- ``mcs``
never leaves ``min_mcs``, so offset ``= mcs - min_mcs == 0``
unconditionally, forever. Since that result is fully determined without
ever executing the function, this commit does not call ``sim/olla.py``'s
``OllaState``/``OllaRoundCounters``/``update_mcs_from_bler`` at all --
there is no live call site for them, and building one anyway would add a
``sim`` import this package explicitly rules out for itself two
paragraphs below ("never on ``sim``"). ``_OLLA_OFFSET`` below is the
constant `0`, cited to this reasoning; see ``sim/olla.py`` for the
reference implementation this offset would use if retry telemetry ever
reached ``allocate()``.

**The ``sim``/``scheduler`` boundary question for OLLA is DEFERRED, not
resolved, by that same fact.** Three ways to wire a live
``update_mcs_from_bler`` call were considered and all rejected as
premature: importing ``sim.olla`` directly (breaks this file's own
"never on ``sim``" boundary, which is load-bearing for a different
reason -- the UL intra-TB split, two paragraphs below -- weakening it
here weakens that citation too); duplicating the primitives into
``scheduler/link.py`` (takes on the exact two-copies drift risk this
codebase warns against elsewhere, for a function that cannot execute);
moving ``sim/olla.py`` into ``scheduler/`` (a diff spanning CLAUDE.md/
README.md/``docs/wp5-plan.md``/``docs/oai-port-map.md`` to relocate a
module nothing calls). It becomes a real decision only once retry
telemetry reaches ``allocate()`` -- there is no call site to justify one
answer over another before then. README.md sec8 [OPEN: WP9].

**Sharing note for two-tier's own future OLLA commit**: this dormancy is
a consequence of WP5 Decision 4 (driver-owned retransmission), not of
reservation's scheduling policy, so it applies identically to two-tier's
own future MCS-selection commit. Both arms must land the identical
offset-pinned-at-zero disposition, or a two-tier-vs-reservation
comparison would measure "one arm has OLLA, one doesn't" rather than a
real scheduling difference.

Like ``two_tier.py``, this package depends only on stdlib and its own
modules -- never on ``sim``. That boundary is what makes the uplink
intra-TB split a non-issue here: a UL grant is emitted as a single opaque
``ue_grant=True`` Allocation (the same convention ``sim/baselines/_mac.py``
and ``two_tier.py`` already use), and ``sim/ue_lcp.py`` performs the real
per-flow split entirely on the driver side. This scheduler's ranking reads
only UE-aggregate quantities (``bytes_reported`` summed across a UE's
flows in a direction, and a per-UE throughput EWMA) -- never a per-flow
split -- matching the real gNB's own visibility (README.md sec7: UL
virtual-queue state in ``ia_p5g_scheduler.c`` is per-LCG, not per-flow).
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

# Commit 9 (D2(b)): OLLA's ratchet offset from mcs_index_for_snr's
# instantaneous pick -- provably 0 given this scheduler's available
# inputs, not a placeholder. See the module docstring's commit-9 section
# for the full derivation (num_dl_sched permanently 0 -> the C's own
# "num_dl_sched <= 3" branch fires every window -> clamped at min_mcs
# from the first update) and for why sim/olla.py's OllaState/
# OllaRoundCounters/update_mcs_from_bler have no live call site here.
_OLLA_OFFSET = 0

# gNB_scheduler_ulsch.c:2205-2213, gNB_scheduler_dlsch.c:814-821: the PF
# coefficient's `tbs` is a hypothetical grant at a hardcoded rbSize=1 and a
# fixed 10-symbol duration -- nr_compute_tbs(Qm, R, 1, 10, 0, 0, 0, layers)
# -- NOT the slot's real dl_symbols/ul_symbols. The "10" is symbols, not
# slots, despite the C's own inline comment ("hypothetical number of
# slots"): it lines up with nr_compute_tbs's 4th parameter at every other
# call site in this codebase (e.g. sim/power.py's nrOfSymbols), and this
# scheduler has no other notion of "10 slots" anywhere. Verified directly
# against both C files while scoping this commit, not assumed.
_PF_COEF_HYPOTHETICAL_SYMBOLS = 10

# gNB_scheduler_ulsch.c:2083-2087, gNB_scheduler_dlsch.c:750-752:
# thr_ue = (1-a)*thr_ue + a*current_bytes, a=0.01, units bytes (not bits).
_THR_EWMA_ALPHA = 0.01

# gNB_scheduler_ulsch.c:2236, gNB_scheduler_dlsch.c:353: an unconfigured
# or zero PDB in the QoS profile falls back to 300 ms, not to 0. Both
# directions use the identical literal. Unreachable from any current
# scenario (`FlowConfig.pdb_ms` defaults to 100.0 and sim/config_loader.py
# :84 defaults the same), but ported because the guard is one line and its
# absence would silently produce remaining_pdb=0 -- the maximum-urgency
# value -- for exactly the case the C treats as least urgent.
_PDB_FALLBACK_MS = 300

# The C computes every deficit quantity in integer arithmetic, and
# truncates the grant age to whole milliseconds before subtracting it
# (`_rem_pdb = _pdb - (int)_age`, gNB_scheduler_ulsch.c:2245;
# `remaining_pdb = pdb - (int)age_ms`, gNB_scheduler_dlsch.c:365). This
# is not incidental: `pdb_ms` feeds a comparator TIER, so int-millisecond
# granularity makes two UEs within the same millisecond TIE at that tier
# and fall through to the PF coefficient. A float port resolves them at
# the PDB tier instead -- a different grant order, on the corpus's own
# numerology (1, 0.5 ms slots), whenever the slot count since a grant is
# odd. Ported as written; see docs/oai-port-map.md row 24.
#
# NOT ported: the C's SFN-wrap modulo on the slot difference
# (`(now - last + 1024*spf) % (1024*spf)`, :2243-2244 / :361-363). This
# simulator's `slot_index` is monotonic for the whole run and never
# wraps, so the modulo would be a no-op at best and would silently
# convert a long idle gap into a small one at worst.

# gNB_scheduler_dlsch.c's own comment, quoted directly: "Fix me: currently,
# the RLC does not give us the total number of PDUs awaiting. Therefore,
# for the time being, we put a fixed overhead of 12 (for 4 PDUs) and
# optionally + 2 for TA." No TA model exists in this simulator (ta_apply
# is always False here), so this is always the flat 12, never 14. UL's
# grant-sizing target (gNB_scheduler_ulsch.c:2492-2512) has no equivalent
# overhead term at all -- a real asymmetry, not an omission.
_DL_LCP_FIXED_OVERHEAD_BYTES = 12

# gNB_scheduler_dlsch.c:850 -- DL's follower-budget floor is a bare C
# literal, self-supplying (no config, no decision needed). Kept as its
# own constant, never unified with `Reservation.min_rb` (UL's own
# follower-budget floor, a configure() parameter defaulting to the same
# number 5) -- the two are not the same KIND of quantity even though
# they currently coincide numerically. See module docstring's commit-4
# section for min_rb's full provenance.
_DL_FOLLOWER_MIN_RB_SIZE = 5


def _ul_follower_budget(
    bwp_size: int, n_followers_need: int, min_rb: int, has_srb: bool,
) -> int:
    """UL's per-UE PRB cap (gNB_scheduler_ulsch.c:2414-2437). `bwp_size`
    is a per-UE STATIC width in the C (unaffected by same-slot grants to
    earlier-ranked candidates) -- callers must pass `slot.prb_count`,
    never a running `prbs_left`, or this collapses into DL's semantics
    (module docstring). `sched_inactive` has no stored field anywhere in
    this module (always False, no-op) -- omitted from the `has_srb`
    check below rather than passed as a separate always-False parameter.
    """
    max_rb_size = min_rb if has_srb else bwp_size
    budget = bwp_size - n_followers_need * min_rb
    if budget < min_rb:
        budget = min_rb
    if max_rb_size > budget:
        max_rb_size = budget
    return max_rb_size


def _ul_needs_service(ue_backlog: int, has_srb: bool, has_gbr: bool) -> bool:
    """gNB_scheduler_ulsch.c:2340-2341. Currently always True in this
    port: ``_allocate_direction``'s candidate list is pre-filtered to
    ``bytes_reported > 0`` before a candidate ever reaches this
    function, so the backlog term alone already decides it every time
    -- see module docstring's commit-4 section. The ``do_sched`` term
    is dropped entirely (no stored field, matching the liveness/
    sched_inactive no-op elsewhere in this module), not passed as an
    always-False parameter.
    """
    return ue_backlog > 0 or has_srb or has_gbr


def _dl_needs_service(ue_backlog: int, has_srb: bool) -> bool:
    """gNB_scheduler_dlsch.c:840-842. No ``has_gbr`` term -- a real
    asymmetry from UL, ported as measured. ``ta_apply``: permanent
    no-op, no TA model -- dropped rather than passed as an always-False
    parameter, same treatment as UL's ``do_sched`` above.
    """
    return ue_backlog > 0 or has_srb


def _dl_follower_budget(
    max_rb_size: int, n_followers_need: int, min_rb_size: int,
) -> int:
    """DL's per-UE PRB cap (gNB_scheduler_dlsch.c:909-926). `max_rb_size`
    is the contiguous-free-RB SCAN result in the C -- callers must pass
    the CURRENT `prbs_left` at this candidate's turn in the grant loop,
    never a value captured once for the whole slot (module docstring).
    """
    budget = max_rb_size - n_followers_need * min_rb_size
    if budget < min_rb_size:
        budget = min_rb_size
    if max_rb_size > budget:
        max_rb_size = budget
    return max_rb_size


def _ul_grant_target(
    backlog_bytes: int,
    guaranteed_bytes: int,
    be_bytes: int,
    has_gbr: bool,
    gbr_bytes_slot: int,
    has_srb: bool,
    srb_lcg0_estimate: int,
) -> int:
    """UL's ``nr_find_nb_rb``-equivalent sizing target
    (``gNB_scheduler_ulsch.c:2492-2512``). Pure function -- see the
    module docstring's commit-4a section for the three ground-truth
    decisions this encodes (target sizes PRBs not delivered bytes;
    ``gbr_bytes_slot``'s MAX-not-sum; ``has_srb``'s permanent no-op) and
    for why the ``backlog_bytes`` floor branch below is itself
    structurally unreachable from ``_allocate_direction`` today.
    """
    target = guaranteed_bytes + be_bytes
    if target < backlog_bytes:
        target = backlog_bytes
    if has_gbr and gbr_bytes_slot > 0 and target < gbr_bytes_slot:
        target = gbr_bytes_slot
    if has_srb:  # permanent no-op -- has_srb is hardcoded False
        srb_target = max(1, srb_lcg0_estimate)
        if srb_target < target:
            target = srb_target
    return target


def _dl_grant_target(
    backlog_bytes: int,
    guaranteed_bytes: int,
    be_bytes: int,
    has_srb: bool,
    srb1_srb2_bytes: int,
) -> int:
    """DL's ``nr_find_nb_rb``-equivalent sizing target
    (``gNB_scheduler_dlsch.c:1003-1019``). ``backlog_bytes`` here is
    ``num_total_bytes`` -- for DL, ``bytes_reported == bytes_queued``
    always (``interfaces.py``), so the existing ``ue_backlog`` variable
    already *is* this quantity; no new plumbing needed.
    """
    oh = _DL_LCP_FIXED_OVERHEAD_BYTES
    target = guaranteed_bytes + be_bytes + oh
    if target < backlog_bytes + oh:
        target = backlog_bytes + oh
    if has_srb:  # permanent no-op -- has_srb is hardcoded False
        floor_target = srb1_srb2_bytes + oh
        if floor_target < target:
            target = floor_target
    return target


@dataclass
class _UeState:
    """Per-UE throughput EWMA, one instance per UE, both directions.

    Real hardware's `current_bytes` accumulation site (grant-time vs.
    confirmed-delivery-time) isn't visible in the vendored C -- the
    ``Scheduler`` protocol has no post-grant delivery-confirmation
    callback, so (matching every existing scheduler's identical
    constraint) this is updated at grant time from an *expected*-delivery
    estimate (``tbs_bytes * (1 - bler)``), not a later confirmed outcome.

    Commit 3: GBR deficit + last-grant-slot tracking, keyed by LCG on UL
    (matching ground truth's own per-LCG granularity) and by qfi on DL
    (matching ground truth's own per-LCID granularity) -- see
    docs/phase2-plan.md sec2.2's DL/UL granularity asymmetry. Last-grant-
    slot stamping feeds the "remaining PDB" computation (the commit-2
    pdb_ms fix); deficit *draining* on a grant is commit 5's job, a
    different field the C happens to update in the same code block.
    """

    dl_thr_bytes_per_slot: float = 0.0
    ul_thr_bytes_per_slot: float = 0.0
    ul_lcg_deficit_bytes: dict[int, int] = field(default_factory=dict)
    ul_lcg_last_grant_slot: dict[int, int] = field(default_factory=dict)
    dl_flow_deficit_bytes: dict[int, int] = field(default_factory=dict)
    dl_flow_last_grant_slot: dict[int, int] = field(default_factory=dict)
    # Commit 8 (D2(a)): a persistent per-UE-per-direction MCS index --
    # link adaptation has no stored home anywhere in this scheduler
    # before this. Computed at candidate-build time (matching the C's
    # own timing, gNB_scheduler_ulsch.c:2192, inside the per-UE loop
    # before the qsort -- for every candidate, not just the eventual
    # winner) from the SAME instantaneous SNR bits_per_rb/bler already
    # use. NOT yet read by anything -- grant sizing still calls
    # bits_per_prb directly, unchanged. Provably inert this commit;
    # commit 9's OLLA ratchet is what starts reading and updating this.
    ul_mcs_index: int = 0
    dl_mcs_index: int = 0


# Deficit accumulation gating differs between directions -- a real
# asymmetry, not shared code. UL's outer per-LCG loop
# (gNB_scheduler_ulsch.c:2230) gates the WHOLE block -- obligation,
# deficit accumulate/cap, and target -- on
# estimated_ul_buffer_per_lcg > 0: a UL LCG's deficit FREEZES the moment
# its per-LCG estimate reads 0. DL's block (gNB_scheduler_dlsch.c:377-410)
# accumulates the deficit and updates has_unfulfilled_gbr UNCONDITIONALLY
# for every GBR-configured LCID (:381-388) -- only the target/overflow
# sub-step is gated on `bytes_in_buffer > 0` (:391). So a DL GBR flow's
# deficit keeps growing through silence; a UL one does not. Verified by
# reading both exact ranges directly, not assumed from the charter's
# "identical formula" summary (true for the arithmetic; false for when
# it runs).


@dataclass
class _Candidate:
    ue_id: int
    flows: list[FlowConfig]
    bits_per_rb: int
    bler: float
    snr_db: float
    coef: float
    # Sort-tier fields (commit 2). has_srb is a permanent, hardcoded
    # no-op (see module docstring); has_gbr is a coarse placeholder
    # pending commit 3/5's real deficit tracking; pdb_ms is fully real.
    has_srb: bool = False
    has_gbr: bool = False
    # int ms, not float: the C's own type, and load-bearing -- see the
    # truncation note at the top of this module.
    pdb_ms: int = 9999
    # Commit 4a: guaranteed_bytes/be_bytes were computed by commit 3 but
    # discarded until now. gbr_bytes_slot/srb_lcg0_estimate are UL-only
    # (0 on DL) -- see module docstring's commit-4a section.
    guaranteed_bytes: int = 0
    be_bytes: int = 0
    gbr_bytes_slot: int = 0
    srb_lcg0_estimate: int = 0
    # Commit 4: real backlog (reused by both needs_service and the grant
    # loop, computed once) and the full needs_service formula -- see
    # module docstring's commit-4 section for why this is currently
    # always True given the candidate pre-filter, and why it's ported
    # as the real formula anyway.
    ue_backlog: int = 0
    needs_service: bool = True


class Reservation:
    """Per-slot sort-and-greedily-fill scheduler -- no LP, no virtual
    queue, no floor state machine (those belong to two-tier). Every UE
    candidate for a slot's grant gets a comparator key; ``qsort`` on that
    key (here, Python's ``sorted``) produces the grant order.
    """

    def __init__(self) -> None:
        self._flows: list[FlowConfig] = []
        self._ue_state: dict[int, _UeState] = {}
        self.min_rb: int = 5

    def configure(
        self,
        flows: list[FlowConfig],
        slot_duration_s: float,
        grid: GridView,
        min_rb: int = 5,
    ) -> None:
        # min_rb: UL's follower-budget floor (nrmac->min_grant_prb) --
        # a deliberate operator/experimenter choice for the calibration
        # campaign, not a physical constant. See module docstring's
        # commit-4 section for the full provenance and why DL's own
        # floor (_DL_FOLLOWER_MIN_RB_SIZE) is a separate constant.
        self._flows = list(flows)
        self.slot_duration_s = slot_duration_s
        self.min_rb = min_rb
        self._ue_state = {f.ue_id: _UeState() for f in flows}

    def allocate(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
    ) -> list[Allocation]:
        # gNB_scheduler.c:246,251: nr_schedule_ulsch runs strictly before
        # nr_schedule_ue_spec within a slot -- a hard ordering dependency,
        # not a threading artefact (docs/phase2-plan.md sec2.2). This
        # commit has no cross-direction state, so the order isn't yet
        # independently observable in output, but getting it right now
        # avoids a silent reorder once one exists.
        out: list[Allocation] = []
        if slot.ul_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "UL"))
        if slot.dl_symbols > 0:
            out.extend(self._allocate_direction(slot, buffers, channel, "DL"))
        return out

    def _allocate_direction(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
    ) -> list[Allocation]:
        symbols = slot.ul_symbols if direction == "UL" else slot.dl_symbols

        # Commit 10a correction (docs/oai-port-map.md row 14): ground
        # truth decays EVERY connected UE's thr_ue every slot --
        # gNB_scheduler_ulsch.c:2074,2083-2085 / _dlsch.c:742,750-752 --
        # gated only on nr_mac_ue_is_active() (gNB_scheduler_
        # primitives.c:3802: sched_ctrl->ul_failure / a DRX-style
        # transm_interrupt timer -- nothing about backlog). Commits 1-10
        # gated this on candidacy (backlog>0 this slot) instead -- the
        # OPPOSITE of ground truth, not merely an unmodeled detail; see
        # the port-map row for the full correction. This simulator has no
        # UL-failure/DRX signal on the Scheduler protocol -- a
        # structurally-absent input in the same category as has_srb/
        # do_sched/TA/OLLA's round telemetry -- so the gate is treated as
        # permanently open: every configured UE decays every slot,
        # regardless of whether it has backlog this slot or ever appears
        # in ue_flows below.
        if direction == "UL":
            for state in self._ue_state.values():
                state.ul_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA
        else:
            for state in self._ue_state.values():
                state.dl_thr_bytes_per_slot *= 1.0 - _THR_EWMA_ALPHA

        ue_flows: dict[int, list[FlowConfig]] = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            ue_flows.setdefault(f.ue_id, []).append(f)
        if not ue_flows:
            return []

        candidates: list[_Candidate] = []
        for ue_id, flows in ue_flows.items():
            state = self._ue_state[ue_id]

            snr = channel.get_reported_snr_db(ue_id)
            # Below-lowest-MCS-threshold viability gate -- a sim-only
            # concept (real 3GPP MCS 0 is always transmittable; this
            # crude staircase's floor threshold is not). Deliberately
            # still keyed on the raw SNR walk (bits_per_prb), not the
            # persisted MCS index below: mcs_index_for_snr floors at 0
            # rather than returning "no viable MCS" (commit 8's own
            # documented convention for a persisted field), so routing
            # this gate through it would silently make an
            # arbitrarily-low-SNR UE look transmittable. Found scoping
            # this commit, not previously an issue since grant sizing
            # didn't yet consume the persisted index.
            if bits_per_prb(snr, symbols=symbols)[0] <= 0:
                continue

            # Commit 9 (D2(b)): the persisted MCS index now feeds grant
            # sizing -- module docstring's commit-9 section. _OLLA_OFFSET
            # is provably 0 given this scheduler's available inputs, not
            # merely defaulted; mcs_index_for_snr(snr) alone still drives
            # the result, matching commit 8's own value exactly.
            mcs_index = mcs_index_for_snr(snr) + _OLLA_OFFSET
            if direction == "UL":
                state.ul_mcs_index = mcs_index
            else:
                state.dl_mcs_index = mcs_index

            # gNB_scheduler_ulsch.c:2203-2213 / _dlsch.c:812-824: Qm/R
            # (here, bits_per_rb/bler) derive from selected_mcs, not a
            # fresh SNR pick -- ground truth's own call site, closing
            # port-map row 15's flagged temporary substitution.
            bits_per_rb, bler = bits_per_prb_for_mcs(mcs_index, symbols=symbols)

            # gNB_scheduler_ulsch.c:2205-2213,2301-2302 /
            # _dlsch.c:814-824: coef = hypothetical_1rb_tbs / max(thr, 1.0).
            # Same selected_mcs feeds this hypothetical TBS too (ground
            # truth uses one Qm/R pick for both) -- port-map row 15.
            hyp_bits, _ = bits_per_prb_for_mcs(
                mcs_index, symbols=_PF_COEF_HYPOTHETICAL_SYMBOLS
            )
            hyp_tbs_bytes = hyp_bits // 8
            thr = (
                state.ul_thr_bytes_per_slot
                if direction == "UL"
                else state.dl_thr_bytes_per_slot
            )
            coef = hyp_tbs_bytes / max(thr, 1.0)

            # has_srb: hardcoded False -- no SRB/RRC-signaling traffic
            # model exists in this simulator (README.md sec8
            # [OPEN: PHASE2], module docstring above). Not a heuristic;
            # a documented permanent no-op.
            has_srb = False

            # has_gbr / pdb_ms: real GBR deficit accumulate/cap/target-
            # spread/overflow-to-BE (gNB_scheduler_ulsch.c:2251-2278 /
            # _dlsch.c:377-409), replacing commit 2's coarse "any GBR
            # flow has backlog" placeholder -- has_gbr now means "has an
            # active unfulfilled deficit." pdb_ms is now the C's actual
            # "remaining PDB" (time since last grant, not HOL delay --
            # a correction to commit 2, see docs/oai-port-map.md rows
            # 18/19 for the full note on why HOL delay was the wrong
            # proxy for this specific field).
            # Commit 4a: guaranteed_bytes/be_bytes are now consumed (grant
            # sizing, below), not discarded. gbr_bytes_slot/lcg0 estimate
            # are UL-only quantities feeding the same sizing target.
            if direction == "UL":
                has_gbr, pdb_ms, guaranteed_bytes, be_bytes = self._ul_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )
                gbr_bytes_slot = self._ul_gbr_bytes_slot(ue_id, buffers)
                srb_lcg0_estimate = self._ul_lcg0_estimate(ue_id, buffers)
            else:
                has_gbr, pdb_ms, guaranteed_bytes, be_bytes = self._dl_gbr_and_pdb(
                    ue_id, buffers, slot.slot_index
                )
                gbr_bytes_slot = 0
                srb_lcg0_estimate = 0

            # Commit 4: real backlog, computed once and reused by both
            # needs_service (below) and the grant loop -- replaces that
            # loop's own former `ue_backlog = sum(...)` recomputation.
            ue_backlog = sum(
                buffers.state(f.ue_id, f.qfi).bytes_reported for f in flows
            )
            if direction == "UL":
                needs_service = _ul_needs_service(ue_backlog, has_srb, has_gbr)
            else:
                needs_service = _dl_needs_service(ue_backlog, has_srb)

            candidates.append(
                _Candidate(
                    ue_id, flows, bits_per_rb, bler, snr, coef,
                    has_srb=has_srb, has_gbr=has_gbr, pdb_ms=pdb_ms,
                    guaranteed_bytes=guaranteed_bytes, be_bytes=be_bytes,
                    gbr_bytes_slot=gbr_bytes_slot,
                    srb_lcg0_estimate=srb_lcg0_estimate,
                    ue_backlog=ue_backlog, needs_service=needs_service,
                )
            )

        if not candidates:
            return []

        candidates.sort(key=lambda c: self._rank_key(c, direction))

        # Commit 4: n_followers_need, computed once for the whole sorted
        # list (gNB_scheduler_ulsch.c:2424-2426 / _dlsch.c:911-913 --
        # the C's own single pass, not recomputed per candidate). Index
        # i holds the count of needs_service=True candidates STRICTLY
        # AFTER i in this sorted order.
        n_followers_after = [0] * len(candidates)
        running = 0
        for i in range(len(candidates) - 1, -1, -1):
            n_followers_after[i] = running
            if candidates[i].needs_service:
                running += 1

        prbs_left = slot.prb_count
        cce_left = slot.pdcch_cce_budget
        out: list[Allocation] = []
        for idx, c in enumerate(candidates):
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(c.snr_db)
            if cce_left < cce_cost:
                # Try lower-AL candidates further down the list.
                continue

            ue_backlog = c.ue_backlog
            if ue_backlog <= 0:
                continue

            # Commit 4: the follower budget -- caps this candidate's
            # PRBs so a saturating BE UE cannot zero a starved UE ranked
            # behind it. Called fresh HERE, per candidate, not hoisted
            # above the loop: DL's base is `prbs_left` AT THIS
            # CANDIDATE'S TURN (it shrinks as earlier candidates in this
            # same slot consume PRBs, matching the C's contiguous-scan
            # semantics), while UL's base is the slot-wide constant
            # `slot.prb_count` (matching the C's per-UE-static bwpSize).
            # Using the same base for both would collapse the asymmetry
            # the module docstring's commit-4 section documents.
            if direction == "UL":
                max_rb_size = _ul_follower_budget(
                    slot.prb_count, n_followers_after[idx], self.min_rb, c.has_srb,
                )
                min_rb_here = self.min_rb
            else:
                max_rb_size = _dl_follower_budget(
                    prbs_left, n_followers_after[idx], _DL_FOLLOWER_MIN_RB_SIZE,
                )
                min_rb_here = _DL_FOLLOWER_MIN_RB_SIZE
            if max_rb_size < min_rb_here:
                # gNB_scheduler_ulsch.c:2437 / _dlsch.c:926 -- not enough
                # budget left to grant this UE at all this slot.
                continue

            # Commit 4a: size PRBs off the guaranteed+be target, not
            # backlog alone (gNB_scheduler_ulsch.c:2492-2512 /
            # _dlsch.c:1003-1019) -- D1: this sizes the PRB *resource*,
            # not delivered bytes; tbs_bytes below stays backlog-capped.
            if direction == "UL":
                target = _ul_grant_target(
                    ue_backlog, c.guaranteed_bytes, c.be_bytes, c.has_gbr,
                    c.gbr_bytes_slot, c.has_srb, c.srb_lcg0_estimate,
                )
            else:
                target = _dl_grant_target(
                    ue_backlog, c.guaranteed_bytes, c.be_bytes,
                    c.has_srb, srb1_srb2_bytes=0,
                )
            prbs_needed = -(-(target * 8) // c.bits_per_rb)  # ceil div
            prbs_used = min(prbs_left, max_rb_size, max(1, prbs_needed))
            tbs_bytes = min(ue_backlog, (prbs_used * c.bits_per_rb) // 8)
            if tbs_bytes <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            expected_bytes = tbs_bytes * (1.0 - c.bler)
            state = self._ue_state[c.ue_id]
            fills: list[tuple[int, int]] | None = None
            if direction == "UL":
                state.ul_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes
                # Commit 5: stamp + drain (gNB_scheduler_ulsch.c:2760-2777,
                # cur_harq->round==0 -- see module docstring for why every
                # grant this port emits is that case).
                self._ul_drain_and_stamp(c.ue_id, buffers, slot.slot_index, tbs_bytes)
            else:
                state.dl_thr_bytes_per_slot += _THR_EWMA_ALPHA * expected_bytes
                # fills computed once here (not inside _emit_grant) so the
                # SAME per-flow breakdown drives both the drain/stamp and
                # the emitted Allocations -- gNB_scheduler_dlsch.c's own
                # lcid_bytes feeds both in one conditional block.
                fills = self._dl_fill(c.flows, tbs_bytes, buffers)
                self._dl_drain_and_stamp(fills, c.ue_id, slot.slot_index)

            out.extend(
                self._emit_grant(
                    c.ue_id, direction, prbs_used, tbs_bytes,
                    cce_cost, c.snr_db, fills,
                )
            )
        return out

    def _ul_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int]:
        """UL GBR deficit accumulate/cap/target-spread/overflow-to-BE
        (gNB_scheduler_ulsch.c:2229-2284), plus the remaining-PDB
        computation the same per-LCG loop drives (:2239-2249). Returns
        ``(has_gbr, remaining_pdb_ms, guaranteed_bytes, be_bytes)`` --
        the last two are real (fidelity-checkable), but NOT yet consumed
        by grant sizing (see module docstring / docs/phase2-plan.md).

        Gated per-LCG on ``estimated_ul_buffer_per_lcg > 0`` (:2230) --
        NOT on ``bytes_reported`` (the crumb-collapsed view eligibility
        elsewhere uses) -- matching the C exactly: a UL LCG's deficit
        freezes the moment its per-LCG estimate reads 0, whether or not
        the UE itself is a candidate this slot. Iterates ``self._flows``
        directly (every one of this UE's UL flows), not the pre-filtered
        eligible subset passed into the candidate loop, so a
        currently-crumb-collapsed LCG still gets evaluated here.

        Per-LCG, first-flow-found wins a shared LCG (matching the C's
        own ``lc_config`` linear-scan-then-``break``, :2232-2234,2282) --
        dormant/unexercised today, the same H5 scenario gap
        ``README.md`` sec8 already names for BSR aliasing.
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0

        seen_lcgs: set[int] = set()
        has_gbr = False
        # gNB_scheduler_ulsch.c:2223 seeds this at 9999, not at an
        # infinity -- ordering-equivalent for any real PDB, ported as the
        # literal so the "no eligible LCG" value is the C's own.
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            lcg_estimate = buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
            if lcg_estimate <= 0:
                continue
            seen_lcgs.add(f.lcg)

            # :2236 -- int ms, with the 300 ms fallback for an
            # unconfigured PDB.
            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.ul_lcg_last_grant_slot.get(f.lcg)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                # :2243-2245 -- age truncated to whole ms BEFORE the
                # subtraction, clamped at 0.
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += lcg_estimate  # non-GBR LCG: entire buffer is BE
                continue

            # :2253-2270 -- integer arithmetic throughout, matching the C's
            # own int locals and int `ul_lcg_deficit_bytes[]` array.
            obligation = max(1, int((f.gfbr_bps / 8.0) / slots_per_sec))
            deficit = state.ul_lcg_deficit_bytes.get(f.lcg, 0) + obligation
            # :2257 -- the RATIO is truncated, then multiplied (not the
            # product). Dormant at every real numerology, where an integer
            # pdb_ms over a 0.5/0.25 ms slot always divides evenly.
            window = obligation * int(pdb_ms / slot_ms)
            deficit = min(deficit, window)
            state.ul_lcg_deficit_bytes[f.lcg] = deficit
            if deficit > 0:
                has_gbr = True

            rem_slots = int(remaining_pdb / slot_ms)
            if rem_slots < 1:
                rem_slots = 1
            target = (deficit + obligation) // rem_slots
            if target < obligation:
                target = obligation
            # :2268 -- computed unconditionally; an unset MFBR yields 0,
            # which the floor below then raises to 2x obligation. The C has
            # no "is MFBR configured" branch and neither does this.
            max_burst = int((f.mfbr_bps / 8.0) / slots_per_sec) * 2
            if max_burst < obligation * 2:
                max_burst = obligation * 2
            if target > max_burst:
                target = max_burst

            guaranteed_bytes += target
            overflow = lcg_estimate - target
            if overflow > 0:
                be_bytes += overflow

        return has_gbr, best_remaining_pdb, guaranteed_bytes, be_bytes

    def _ul_has_pending_gbr(self, ue_id: int, buffers: BufferView) -> bool:
        """The gate on ``_ul_gbr_bytes_slot``'s whole loop
        (``gNB_scheduler_ulsch.c:2305``), itself set by
        ``update_ul_qos_priority`` (``:38-67``). A *separate* per-LCG
        first-match dedup from ``_ul_gbr_and_pdb``'s ``seen_lcgs`` --
        same shape, different loop, different field -- gated on
        ``mfbr_bps > 0`` (``c->gbr_ul_max``), **not** ``gfbr_bps``. No
        current scenario configures a nonzero ``mfbr_bps``
        (``docs/oai-port-map.md`` row 23), so this is always ``False``
        today -- confirmed by its own test, not assumed.
        """
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            seen_lcgs.add(f.lcg)
            if f.mfbr_bps > 0:
                return True
        return False

    def _ul_gbr_bytes_slot(self, ue_id: int, buffers: BufferView) -> int:
        """``gNB_scheduler_ulsch.c:2304-2316``. Structurally separate
        from ``_ul_gbr_and_pdb``'s per-LCG deficit loop: gated on
        ``_ul_has_pending_gbr`` (above), then iterates *every*
        qualifying UL flow with **no** ``seen_lcgs`` dedup (unlike the
        deficit loop's first-flow-wins-a-shared-LCG break) and takes
        the running **MAX**, not a sum. The per-slot rate itself also
        omits the deficit loop's ``max(1, ...)`` floor (``:2254``) --
        both divergences are bug-for-bug, confirmed by reading the
        exact ranges directly, not incidental simplifications.
        """
        if not self._ul_has_pending_gbr(ue_id, buffers):
            return 0
        slots_per_sec = 1.0 / self.slot_duration_s
        gbr_bytes_slot = 0
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL":
                continue
            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            # :2313 -- NOT floored at 1, unlike the deficit loop's `_obl`.
            floor = int((f.gfbr_bps / 8.0) / slots_per_sec)
            if floor > gbr_bytes_slot:
                gbr_bytes_slot = floor
        return gbr_bytes_slot

    def _ul_lcg0_estimate(self, ue_id: int, buffers: BufferView) -> int:
        """``gNB_scheduler_ulsch.c:2504``: the ``has_srb`` control-only
        cap reads LCG0's raw per-LCG estimate. Permanently unreachable
        in this simulator -- ``has_srb`` is hardcoded ``False`` (module
        docstring) -- built for structural/citation completeness only,
        the same treatment the ``has_srb`` sort tier already gets.
        """
        for f in self._flows:
            if f.ue_id == ue_id and f.direction == "UL" and f.lcg == 0:
                return buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
        return 0

    def _ul_drain_and_stamp(
        self, ue_id: int, buffers: BufferView, slot_index: int, tbs_bytes: int,
    ) -> None:
        """``gNB_scheduler_ulsch.c:2760-2777`` (``post_process_ulsch``,
        gated ``cur_harq->round == 0`` -- every grant this port emits is
        that case, since retransmissions are handled entirely by the
        driver's own HARQ seam before ``allocate()`` is ever called;
        see the module docstring's commit-5 section).

        Comment at ``:2772``, quoted verbatim: *"distribute tb_size
        drain proportionally across active LCGs."* The code does not
        divide -- it subtracts the FULL ``tb_size`` from every active
        LCG's deficit independently. Ported bug-for-bug: the code, not
        the comment.

        Iterates ``self._flows`` (matching ``_ul_gbr_bytes_slot``'s own
        pattern), **not** the candidate's ``c.flows`` -- ``c.flows`` is
        filtered to ``bytes_reported > 0`` (the crumb-gated view), but
        the C's own iteration gate is ``estimated_ul_buffer_per_lcg > 0``
        (the true per-LCG BSR estimate), and ``bytes_reported <=
        estimated_ul_buffer_per_lcg`` always (WP3) -- so ``c.flows``
        deduped by LCG is a possibly-STRICT subset of the C's own
        iteration set. Found and fixed scoping this commit: an LCG with
        a positive estimate but a crumb-gated zero report would
        otherwise be silently skipped here -- under-stamped (a stale
        ``last_grant_slot`` inflates that LCG's age, shrinking
        ``remaining_pdb`` and raising its urgency at the PDB comparator
        tier once commit 10 wires this scheduler in -- live ordering
        behaviour, not just bookkeeping) and under-drained.
        """
        state = self._ue_state[ue_id]
        seen_lcgs: set[int] = set()
        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "UL" or f.lcg in seen_lcgs:
                continue
            if buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg <= 0:
                continue
            seen_lcgs.add(f.lcg)
            state.ul_lcg_last_grant_slot[f.lcg] = slot_index
            deficit = state.ul_lcg_deficit_bytes.get(f.lcg, 0)
            if deficit > 0:
                state.ul_lcg_deficit_bytes[f.lcg] = max(0, deficit - tbs_bytes)

    def _dl_drain_and_stamp(
        self, fills: list[tuple[int, int]], ue_id: int, slot_index: int,
    ) -> None:
        """``gNB_scheduler_dlsch.c:1451-1460``, gated ``lcid_bytes > 0``
        per LC. No comment/code mismatch on DL's side -- "drain GBR
        deficit by bytes actually delivered," and the code does exactly
        that (confirmed directly, not assumed from the charter).

        ``fills`` (from ``_dl_fill``) already IS that per-flow
        breakdown -- a flow with ``take == 0`` is never appended there.
        Correction to commit 3, found scoping this commit: the existing
        stamp iterated ALL of ``c.flows`` unconditionally, not just the
        ones ``_dl_fill`` actually gave bytes to. What commit 3 did:
        stamped every flow of a granted UE, every slot. What the C
        does: stamps (and drains) only the specific LCID that received
        nonzero bytes in *this* fill. Why no test caught it: every
        scenario to date is single-flow-per-UE-per-direction, where
        "the UE got a grant" and "this flow got bytes" trivially
        coincide.

        The DRAIN half of this fix is dormant on every current scenario
        -- ``dl_flow_deficit_bytes`` only ever gets an entry for a
        GBR-class flow, and no scenario configures a UE with two or
        more GBR DL flows. But the STAMP half is **not** purely
        hypothetical: ``_dl_gbr_and_pdb`` folds ``remaining_pdb`` into
        ``best_remaining_pdb`` for *every* DL flow of a UE regardless of
        ``flow_class`` (gated only on ``bytes_queued > 0``), reading
        ``dl_flow_last_grant_slot`` per flow -- so a wrongly-over-stamped
        flow's inflated "recently served" illusion feeds the PDB
        comparator tier for any multi-DL-flow UE, GBR or not.
        ``sim/scenarios/scenario_config_6.yml``'s UE 10 already has two
        DL flows (qfi 9, PF; qfi 82, Delay-class) -- this bug would be
        live there the moment commit 10 wires this scheduler in, not a
        purely constructed-for-testing scenario.
        """
        state = self._ue_state[ue_id]
        for qfi, byts in fills:
            state.dl_flow_last_grant_slot[qfi] = slot_index
            deficit = state.dl_flow_deficit_bytes.get(qfi, 0)
            if deficit > 0:
                state.dl_flow_deficit_bytes[qfi] = max(0, deficit - byts)

    def _dl_gbr_and_pdb(
        self, ue_id: int, buffers: BufferView, slot_index: int,
    ) -> tuple[bool, int, int, int]:
        """DL GBR deficit accumulate/cap/target-spread/overflow-to-BE
        (gNB_scheduler_dlsch.c:377-409), plus remaining-PDB (:358-367).
        Returns ``(has_gbr, remaining_pdb_ms, guaranteed_bytes,
        be_bytes)`` -- same not-yet-sizing-consumed caveat as UL's.

        Deficit accumulation and ``has_unfulfilled_gbr`` are UNCONDITIONAL
        for every GBR-configured flow (:381-388) -- unlike UL, this does
        NOT gate on current buffer occupancy, so a DL GBR flow's deficit
        keeps growing through silence. Only the target/overflow sub-step
        gates on ``bytes_queued > 0`` (:391). A real asymmetry, verified
        by reading both exact ranges directly -- see this module's
        top-of-file note.
        """
        state = self._ue_state[ue_id]
        slots_per_sec = 1.0 / self.slot_duration_s
        slot_ms = self.slot_duration_s * 1000.0

        has_gbr = False
        # gNB_scheduler_dlsch.c:330 -- 9999, same as UL's own seed.
        best_remaining_pdb = 9999
        guaranteed_bytes = 0
        be_bytes = 0

        for f in self._flows:
            if f.ue_id != ue_id or f.direction != "DL":
                continue
            bytes_queued = buffers.state(f.ue_id, f.qfi).bytes_queued

            # :353 -- int ms, 300 ms fallback, identical to UL's.
            pdb_ms = int(f.pdb_ms) if f.pdb_ms > 0 else _PDB_FALLBACK_MS

            last_grant = state.dl_flow_last_grant_slot.get(f.qfi)
            if last_grant is None:
                remaining_pdb = pdb_ms
            else:
                # :363-366 -- same whole-ms age truncation as UL's.
                age_ms = (slot_index - last_grant) * slot_ms
                remaining_pdb = max(0, pdb_ms - int(age_ms))
            if bytes_queued > 0:
                best_remaining_pdb = min(best_remaining_pdb, remaining_pdb)

            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                be_bytes += bytes_queued  # non-GBR: entire buffer is BE
                continue

            # :379-399 -- integer throughout, and truncating at exactly the
            # same four sites as UL's block (verified line by line: the
            # window truncates the ratio, not the product, on both sides).
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

    def _rank_key(self, candidate: _Candidate, direction: str) -> tuple:
        """Dispatch to the direction's own comparator. UL and DL are
        genuinely different tier structures in ground truth (5 vs. 4
        tiers) -- see ``_ul_rank_key``/``_dl_rank_key``, kept as two
        independently-sourced methods even where their output currently
        coincides, never merged into one shared function.
        """
        if direction == "UL":
            return self._ul_rank_key(candidate)
        return self._dl_rank_key(candidate)

    def _ul_rank_key(self, c: _Candidate) -> tuple:
        """UL ground truth: 5 tiers, SRB -> liveness -> GBR ->
        sched_inactive-last -> PDB/coef (gNB_scheduler_ulsch.c:2010-2039).

        T1 (has_srb) is a permanent no-op here -- no SRB/RRC traffic
        model exists in this simulator (README.md sec8 [OPEN: PHASE2]).
        T2/T4 (liveness/sched_inactive) are a DEFERRED no-op pending a
        do_sched-equivalent signal (README.md sec8's other new entry).
        Commit 1's own coefficient (-c.coef) remains the tuple's final
        element, unchanged -- this method PREPENDS tiers ahead of it,
        it does not restructure the sort.

        Hedged, not asserted as fact: working through
        gNB_scheduler_ulsch.c's own boolean relationship between T2
        (liveness = sched_inactive && !ul_has_srb, :2339) and T4
        (sched_inactive, :2332) by exhaustive case analysis suggests T4
        may never produce a decisive comparator result in the real C
        either -- whenever sched_inactive=True, either has_srb=True (T1
        already resolves it) or liveness=True (T2 already resolves it
        ahead of T4). This is my own reading of the C, not verified by
        instrumenting it at runtime, and does not change what's ported:
        T4 is implemented exactly as the C runs it (moot today anyway,
        since sched_inactive itself is a deferred no-op).
        """
        return (
            0 if c.has_srb else 1,
            0 if c.has_gbr else 1,
            c.pdb_ms,
            -c.coef,
        )

    def _dl_rank_key(self, c: _Candidate) -> tuple:
        """DL ground truth: 4 tiers, SRB -> liveness(TA) -> GBR ->
        PDB/coef (gNB_scheduler_dlsch.c:692-715). DL's UEsched_t
        (:681-690) has NO sched_inactive field at all -- confirmed
        absent by reading the struct directly, not expressed
        differently -- so there is no T4-equivalent tier on this side,
        ever, regardless of the UL hedge above.

        T1 (has_srb) and T2 (TA-pending liveness) are no-ops for the
        same two reasons as UL's (README.md sec8), independently cited
        here even though this tuple currently comes out the same shape
        as ``_ul_rank_key``'s -- that is a data-availability coincidence
        (both directions happen to have exactly one real tier -- GBR --
        implementable today), not a decision to share a comparator.
        """
        return (
            0 if c.has_srb else 1,
            0 if c.has_gbr else 1,
            c.pdb_ms,
            -c.coef,
        )

    def _emit_grant(
        self,
        ue_id: int,
        direction: str,
        prbs_used: int,
        tbs_bytes: int,
        cce_cost: int,
        snr_used_db: float,
        fills: list[tuple[int, int]] | None,
    ) -> list[Allocation]:
        if direction == "UL":
            # The gNB sizes the block; the UE fills it (TS 38.321
            # sec5.4.3.1). sim/ue_lcp.py performs the real split on the
            # driver side -- see this module's docstring and
            # docs/phase2-plan.md sec3/D1.
            return [
                Allocation(
                    ue_id=ue_id, qfi=-1, direction=direction,
                    prbs=prbs_used, bytes_capacity=tbs_bytes,
                    cce_cost=cce_cost, snr_used_db=snr_used_db,
                    ue_grant=True,
                )
            ]

        # Commit 5: fills is computed once by the caller (alongside the
        # drain/stamp, which needs the exact same per-flow breakdown),
        # not recomputed here.
        assert fills is not None
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
        """Real two-pass SRB/DRB LCP fill
        (``gNB_scheduler_dlsch.c:1394-1463``), replacing commit 1's
        priority-sorted placeholder -- see module docstring's commit-6
        section for the full citation trail.

        Pass 0 (SRB) is **not applicable** here, not merely dormant --
        ``FlowConfig`` has no SRB representation to gate a filter on at
        all (docs/oai-port-map.md row 31).

        Pass 1 (DRB) fills every flow in **``ue_flows``'s own existing
        order** -- confirmed directly, not assumed: no `sort`/`qsort`
        touches ``lc_config`` anywhere in the C file (the only `qsort`
        in it is the inter-UE comparator, ``:847``); the C's own
        comment states DRBs drain "in existing lc_config order,
        unchanged." ``priority_level`` plays NO role in DL fill order
        -- do not sort by it here, unlike ``sim/ue_lcp.py``'s UL fill,
        which genuinely does (``scheduler/flow.py``'s
        ``FIVE_QI_PRIORITY`` docstring, corrected to scope that
        rationale to UL only). ``ue_flows`` is the caller's ``c.flows``,
        itself built by iterating ``self._flows`` and appending in
        order -- plain list iteration + append preserves relative
        order, so no re-sort is needed here; just don't add one.

        Per-flow: ``take = min(backlog, remaining)``, appended only if
        ``take > 0`` -- the exact convention the placeholder already
        used, preserving commit 5's "one entry per flow that got
        bytes" stamp/drain contract unchanged.

        NOT ported: per-SDU MAC subheader overhead
        (``sizeof(NR_MAC_SUBHEADER_LONG)`` per RLC chunk) -- see module
        docstring's commit-6 section for the quantified, directional
        (over-delivery) disagreement this creates with 4a's own
        ``oh=12`` sizing headroom.
        """
        fills: list[tuple[int, int]] = []
        remaining = tbs_bytes
        for f in ue_flows:  # existing declared order -- do NOT sort
            if remaining <= 0:
                break
            backlog = buffers.state(f.ue_id, f.qfi).bytes_queued
            take = min(backlog, remaining)
            if take > 0:
                fills.append((f.qfi, take))
                remaining -= take
        return fills
