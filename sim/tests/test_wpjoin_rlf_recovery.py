"""WP-Join commit 8 -- the GT-6.3 acceptance-criterion demo. Last commit
in this WP.

Scoped to GT-6.3 (RLF-and-reestablish) only, per the user-confirmed D0b:
it is the only one of the three GT-6 paths that exercises every prior
commit (the delay sampler, RLF wiring, the radio gate, the app gate, the
scheduler reset) in one run. GT-6.1/6.2 got unit-level coverage in their
own commits (sim/tests/test_join_handshake.py, sim/tests/
test_join_gate.py); their 50-cycle/10-cycle repeated campaigns are WP9's
job, not this commit's.

**Stays OUTSIDE scripts/regression_corpus.py's 22-record corpus
entirely** -- built in-line here, not as a `sim/scenarios/*.yml` file --
for WP6 commit 4's own three reasons (docs/wp6-plan.md sec4), which
apply here essentially unchanged, plus one WP-Join-specific fourth:
1. The corpus format is one fixed run per (scenario, scheduler); this
   demo's whole point is comparing the SAME base scenario at multiple
   fade-duration settings (baseline / GT-6.3a / GT-6.3b), which doesn't
   fit that shape without picking one arbitrary setting (defeating the
   point) or inventing a multi-record convention no other WP needed.
2. This scenario is deliberately extreme (2 UEs, a 30dB scripted fade,
   opt-in JoinConfig/handshake flows) to make ONE mechanism legible, not
   a realistic workload meant to anchor future comparisons the way
   factory_robots_scenario/sensor_dense_scenario/latency_bound_scenario
   are.
3. Joining the corpus means every future WP's --check diff would carry
   this scenario's own join/RLF timing numbers, adding noise to
   attribution for changes that have nothing to do with WP-Join --
   against the corpus's own stated purpose.
4. (WP-Join-specific) M19 requires record_timeseries=True, which the
   22-record corpus deliberately does not carry at all (scripts/
   regression_corpus.py's own collect_records() never passes it) --
   adding it here would also change what the corpus format has to
   support, for a demo that doesn't need to live there.

**Ground truth this demo is built from, restated here (not just cited in
docs/wp-join-plan.md sec6's flag), per this commit's own review point 1:**
commit 3 found extra_loss_db must exceed 25dB at this deployment's
mean_snr_db=20 to cross the -5.0dB RLF floor at all (30dB used here, a
5dB margin); a fade shorter than n310+t310=4,010 slots (2.005s) never
declares RLF, regardless of depth; and the GT-6.3a/6.3b boundary --
whether the true reestablishment path is reachable before t311's search
window expires -- is EXACTLY n310+t310+cell_search_ceiling_slots=10,010
slots (5.005s). GT-6.3a's fade (6,000 slots = 3.0s) sits comfortably
under that boundary; GT-6.3b's fade (20,000 slots = 10.0s, the guarantee
test plan's own literal duration) sits at just under 2x past it --
stated here in the numbers themselves, not only in the flag.
"""

import pytest

from sim.config import CarrierConfig, ScenarioConfig, ScriptedFadeWindow, UEConfig
from sim.driver import run
from sim.join import JoinConfig
from sim.run_record import RunRecord
from sim.scorecard import Scorecard
from sim.baselines.pf import ProportionalFair
from scheduler import TwoTier
from scheduler.flow import FlowConfig

SLOT_DURATION_S = 0.0005
FADE_START_SLOT = 1000
GT63A_FADE_SLOTS = 6_000  # 3.0s -- comfortably under the 10,010-slot boundary
GT63B_FADE_SLOTS = 20_000  # 10.0s -- the guarantee test plan's own literal duration
REESTABLISH_BOUNDARY_SLOTS = 10_010  # commit 3, confirmed exactly: n310+t310+cell_search_ceiling_slots
HORIZON_SLOTS = 30_000

assert GT63A_FADE_SLOTS < REESTABLISH_BOUNDARY_SLOTS
assert GT63B_FADE_SLOTS > 2 * REESTABLISH_BOUNDARY_SLOTS - 500  # "just under 2x past it"

# Handshake flows get a deliberately generous PDB (20s) -- a scenario-
# authoring choice, not a mechanism change. Finding from building THIS
# demo: sim/join.py's RRC_ESTABLISH/PDU_SESSION completion is not itself
# SNR-gated (only CELL_SEARCH is), so on the IDLE-fallback path (GT-6.3b)
# a UE can "logically" reach APP_HANDSHAKE while the scripted fade is
# still physically active -- true SNR there makes any real grant fail
# outright (draw_harq_outcome), so the handshake request just waits,
# undelivered, until the channel actually clears. At the default
# JoinConfig sizing this repo's other tests use (pdb_ms=1000) that wait
# exceeds the PDB and the message is silently dropped, expired, before
# the event can ever complete -- confirmed directly while building this
# demo (bytes_dropped=64 the whole message, at pdb_ms=1000). A generous
# PDB is what a scenario author configuring a GT-6.3b-shaped run needs
# to choose; it is not something sim/join.py or sim/driver.py should
# assume or default to, since a shorter, ordinary handshake flow (as
# GT-6.1's own warm-path demo uses) has no reason to expect this.
HANDSHAKE_PDB_MS = 20_000.0


def _scenario(fade_slots, seed=123):
    ue1 = UEConfig(
        ue_id=1, mean_snr_db=20.0, coherence_slots=1000,
        join=JoinConfig(handshake_ul_qfi=90, handshake_dl_qfi=91),
    )
    if fade_slots is not None:
        ue1.scripted_fade = (
            ScriptedFadeWindow(start_slot=FADE_START_SLOT, end_slot=FADE_START_SLOT + fade_slots, extra_loss_db=30.0),
        )
    ue2 = UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=1000)  # undisturbed neighbour
    flows = [
        FlowConfig(ue_id=1, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000, pdb_ms=50,
                   traffic_kind="deterministic", traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
        FlowConfig(ue_id=1, qfi=90, direction="UL", flow_class="PF", pdb_ms=HANDSHAKE_PDB_MS,
                   traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
        FlowConfig(ue_id=1, qfi=91, direction="DL", flow_class="PF", pdb_ms=HANDSHAKE_PDB_MS,
                   traffic_kind="poisson", traffic_params={"rate_bps": 0.0}),
        FlowConfig(ue_id=2, qfi=1, direction="DL", flow_class="GBR", gfbr_bps=2_000_000, pdb_ms=50,
                   traffic_kind="deterministic", traffic_params={"period_ms": 5.0, "bytes_per_period": 1000}),
    ]
    return ScenarioConfig(
        name="wpjoin_gt63_demo", horizon_slots=HORIZON_SLOTS, seed=seed,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1), ues=[ue1, ue2], flows=flows,
    )


def _run_and_score(fade_slots, scheduler):
    sc = _scenario(fade_slots)
    summary = run(sc, scheduler, record_timeseries=True)
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=type(scheduler).__name__, seed=sc.seed,
        flow_configs=sc.flows, summary=summary,
    )
    return summary, rec, Scorecard().score(rec)


@pytest.mark.parametrize("scheduler_factory", [TwoTier, ProportionalFair])
def test_gt63a_short_fade_completes_the_true_reestablish_path(scheduler_factory):
    summary, rec, scored = _run_and_score(GT63A_FADE_SLOTS, scheduler_factory())
    assert len(summary["join_events"]) == 1
    event = summary["join_events"][0]
    assert event["path"] == "reestablish"
    assert event["timer_expiries"] == {}  # no expiry -- true reestablishment, not a fallback
    assert event["rf_restore_slot"] is not None
    assert event["attached_slot"] is not None

    m18 = scored["M18"]
    assert m18.status == "ok"
    reest = m18.value["by_path"]["reestablish"]
    assert reest["n_never_completed"] == 0
    assert reest["timer_expiry_count"] == 0
    # GT-6.3's own pass line, measured the way the test plan measures it
    # (from RF-restore, not from RLF declaration) -- comfortably inside
    # the (provisional) 10s target.
    assert reest["rf_restore_to_attached_p95_ms"] is not None
    assert reest["rf_restore_to_attached_p95_ms"] < 10_000.0

    m19 = scored["M19"]
    assert m19.status == "proxy"
    assert m19.value["by_path"]["reestablish"]["n_never_recovered"] == 0


@pytest.mark.parametrize("scheduler_factory", [TwoTier, ProportionalFair])
def test_gt63b_literal_fade_falls_back_through_idle(scheduler_factory):
    """The test plan's own literal 10s fade -- confirmed here to exercise
    the IDLE-fallback/full-reattach path, not the true reestablishment
    path its own wording ("<=10s including re-establishment") describes,
    exactly as docs/wp-join-plan.md D6 predicted from the timer numbers
    alone. timer_expiries["cell_search"]==1 is the direct, observable
    proof (t311 expired), not an inference from the path label -- the
    label stays "reestablish" either way (sim/driver.py's own scope-
    selection finding from commit 7)."""
    summary, rec, scored = _run_and_score(GT63B_FADE_SLOTS, scheduler_factory())
    assert len(summary["join_events"]) == 1
    event = summary["join_events"][0]
    assert event["path"] == "reestablish"
    assert event["timer_expiries"] == {"cell_search": 1}
    # Finding: RF-restore (CELL_SEARCH's own SNR-restoration detection)
    # never fires on this path by construction -- it timed out BEFORE the
    # channel could satisfy it, so there is no RF-restore instant to
    # report for this event at all, only a trigger-to-attached span.
    assert event["rf_restore_slot"] is None
    assert event["attached_slot"] is not None

    m18 = scored["M18"]
    assert m18.status == "ok"
    reest = m18.value["by_path"]["reestablish"]
    assert reest["n_never_completed"] == 0
    assert reest["timer_expiry_count"] == 1
    # No RF-restore timestamp on the one event this run has -> nothing to
    # average -> None, not a fabricated number. GT-6.3's own pass line
    # cannot be evaluated against this specific run for that reason, a
    # limitation of the IDLE-fallback path stated here, not hidden.
    assert reest["rf_restore_to_attached_p95_ms"] is None
    # The trigger-to-attached span IS computable, and -- in this specific
    # constructed scenario -- still lands under 10s, though it is not the
    # quantity GT-6.3's own criterion is measured against.
    assert reest["p95_ms"] < 10_000.0

    m19 = scored["M19"]
    assert m19.status == "proxy"


@pytest.mark.parametrize("scheduler_factory", [TwoTier, ProportionalFair])
def test_undisturbed_neighbour_throughput_and_pdb_violations_never_worse(scheduler_factory):
    """The primary isolation mechanism (docs/wp-join-plan.md sec5): a
    two-arm, seed-matched comparison needing zero new scoring code --
    UE 2's own M01-style throughput/M02-style violations, compared
    across arms directly from RunRecord.flows, same seed, only UE 1's
    own fade/join config differing."""
    baseline_summary, baseline_rec, _ = _run_and_score(None, scheduler_factory())
    for fade_slots in (GT63A_FADE_SLOTS, GT63B_FADE_SLOTS):
        _, demo_rec, _ = _run_and_score(fade_slots, scheduler_factory())
        base_ue2 = baseline_rec.flow(2, 1)
        demo_ue2 = demo_rec.flow(2, 1)
        assert demo_ue2.throughput_bps >= base_ue2.throughput_bps - 1.0  # never worse (float tolerance)
        assert demo_ue2.bytes_dropped_pdb <= base_ue2.bytes_dropped_pdb


def test_two_tier_shows_a_transient_neighbour_delay_bump_only_on_the_mac_scope_arm():
    """NOT asserted away: this is docs/wp-join-plan.md sec4's own ranked
    Prediction 5 (Low confidence), confirmed here, not contradicted.
    "mac" scope (GT-6.3a) deliberately RETAINS UE 1's virtual-queue
    deficit across reestablishment -- so the moment it reconnects, it
    carries real, legitimate catch-up priority that transiently
    outranks UE 2 in TwoTier's own ranking, nudging UE 2's own p99 delay
    up slightly (never its throughput or its PDB violations -- see the
    test above). "full" scope (GT-6.3b) clears that deficit to zero, so
    the same effect does not appear there: nothing for the reconnecting
    UE to catch up on. This is exactly the kind of question D7 flagged
    "mac" scope's retention as needing GT-6.3-shaped evidence to answer,
    not asserted away by writing a "never worse, no exceptions" test
    that this run would have failed."""
    baseline_summary, baseline_rec, _ = _run_and_score(None, TwoTier())
    _, mac_rec, _ = _run_and_score(GT63A_FADE_SLOTS, TwoTier())
    _, full_rec, _ = _run_and_score(GT63B_FADE_SLOTS, TwoTier())

    base_p99 = baseline_rec.flow(2, 1).delay_p99_ms
    mac_p99 = mac_rec.flow(2, 1).delay_p99_ms
    full_p99 = full_rec.flow(2, 1).delay_p99_ms

    assert mac_p99 > base_p99  # the transient bump, confirmed, not hidden
    assert full_p99 == pytest.approx(base_p99, abs=1e-6)  # "full" scope shows no such bump
