"""G3 as a stress experiment: can the network make a healthy robot look dead?

Registered in `docs/g3-registration-2026-09-09.md`; the result is
`docs/g3-stress-experiment-2026-09-09.md`.

WHAT IS DIFFERENT FROM EVERY EARLIER G3 ROW, and why each difference had to be
made before a number was worth taking:

  * **ALL THREE CLAUSE PARTS, SCORED SEPARATELY.** L97 is *"max telemetry
    inter-arrival gap <= T_live/4 (500 ms)"* AND *"zero gaps >= T_live over
    the full campaign"* AND *"p98 <= PDB"*. Part 2 is a CAMPAIGN-wide zero,
    not a per-run rate: a 9/10 pass rate reads as 90 % and the clause is
    failed by one gap anywhere. Part 3 is numerically G1's own statistic under
    a different guarantee's name, so it is labelled rather than left to carry
    two verdicts silently.

  * **IT SCORES THE TELEMETRY FLOW.** The published row read `M03` over the
    protected fleet -- better than all-flow, which is what made a saturating
    flood's own starvation score as a telemetry failure, but still a
    worst-of-every-protected-bearer maximum. Measured on the artefact the row
    came from (`sweeps/m6-2026-09-07/plain/core.json`, 30 rows): part 1's
    winner IS telemetry on 30 of 30, but **part 3's winner is the 5QI-2
    CAMERA on 8 of 30** -- a video bearer with its own 150 ms budget, scored
    against telemetry's 95 ms.

  * **PART 3 IS A CAPPED STATISTIC AND PART 1 IS NOT.** Telemetry's PDB is
    100 ms and its period is 100 ms, so `sim/buffer.py::expire()` discards a
    message that waits longer than one period and it never enters a latency
    percentile. p98 therefore cannot exceed ~100.25 ms whatever happens --
    it can fail its 95 ms bound, but a catastrophic cell and a marginal one
    look nearly identical. **The gap criterion has no such ceiling**, because
    a discarded message widens the receiver-side gap around it. This is G2's
    finding in a milder form and it is why part 1 is the instrument here.

  * **AND AN INTER-ARRIVAL MAXIMUM CANNOT SEE A ROBOT THAT GOES DARK AND
    STAYS DARK.** A gap needs a message on BOTH sides of it, so a flow whose
    last message lands at t=1.7 s of a 10 s run has no gap describing the
    8.3 s of silence that follows. **Measured on this campaign's own first
    artefact, before any verdict was published: 19 flow-runs where a robot was
    silent for up to 9.5 s while the scored maximum read 114-342 ms.** One
    delivered **3 of 100** messages and scored 185 ms -- a comfortable pass.

    That is the same defect class as the G3 row this campaign withdraws, and
    the same shape as G2's, **reproduced inside the instrument built to replace
    it.** The fix does NOT redefine the clause. Two statistics are reported:

      - `part1_pass` -- the clause **as literally written**, a maximum over
        inter-arrival gaps. Kept unchanged, because that is what L97 says.
      - `part1s_pass` -- the same 500 ms bound over the **longest silence the
        window can observe**, which adds the head (session start to the first
        message) and the tail (last message to run end).

    Both are published. The gap between them IS the finding: a clause phrased
    as an inter-arrival statistic cannot express its own worst failure, and
    saying so is more useful than quietly widening the definition. Part 2's
    count uses the extended set, because *"zero gaps >= T_live"* is a claim
    about the MEC seeing nothing for two seconds and a terminal silence is
    exactly that.

    **The head and the tail are LOWER BOUNDS**, since a silence may extend past
    the window on either side; the head also contains attach, which is G9's
    clause rather than G3's, so it is reported separately as well as scored.

  * **A FLOW THAT DELIVERED FEWER THAN TWO MESSAGES FAILS ALL THREE PARTS.**
    `sim/scorecard.py`'s M03 EXCLUDES such a flow from its worst-gap contest,
    which is right for a worst-of-fleet statistic and exactly wrong here: for
    G3 the instrument going silent IS the failure. G1 found the same and made
    the same choice.

  * **GT-2.3'S SCRIPTED SILENCE IS NOT A LIVENESS FAILURE, so the clock
    starts at RESUME.** A 60 s waypoint pause produces a 60 s receiver-side
    gap by construction; scoring that against a 500 ms bound would fail the
    clause on the application's own behaviour. The scored quantity is
    `first completion after resume - resume instant`, derived from the same
    windows the scenario is built from (`sim/scenarios/g3.py::resume_times_s`)
    so schedule and scoring cannot disagree. The raw straddling gap is
    reported beside it.

  * **THE UL FLOOR'S FIRES ARE COUNTED, WITH NO SCHEDULER CHANGE.** GT-2.2's
    pass line asks to *"verify [P5G-UL-FLOOR] arming under the right-sized
    profile and count fires"*, and CLAUDE.md's audit lists the floor as
    unobservable -- *"OAI's counters not ported; activation unknowable"*.

    It turns out the counter was already there. `floor_fire` is **tier 1.5 of
    two-tier's own UL ranking key** (`scheduler/two_tier.py::_ul_rank_key`,
    `0 if candidate.floor_fire else 1`), and `scheduler/rank_trace.py`
    records that key verbatim for every candidate in every slot. So
    `FloorFireTally` below reads the fires out of the existing rank stream --
    a hook whose bit-identity is a property of its construction ("every value
    recorded here is one the arm already computed for its own sort").

    **THIS REPLACED SIX COUNTERS ADDED TO `scheduler/two_tier.py` AND THEN
    REVERTED**, and the reason is worth recording because it is a cost that
    is easy to miss: `scripts/code_state.py` stamps each artefact with the
    AST hash of its runner's transitive import closure, and every campaign
    that runs a TwoTier arm reaches `two_tier.py`. The six counters were pure
    telemetry -- `regression_corpus --check` moved **zero numbers**, 30
    shape-only lines -- and they still invalidated **12 published claims
    across G1, G2 and G10**, at roughly ten minutes of re-running each. The
    rank stream costs none of that. What is lost is the ARMING decomposition
    (`has_pending_gbr` passing, and `armed`), which is internal state no hook
    reaches; that only matters if the fire count comes back zero, and §4 of
    the result reports what it actually came back as.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                    # noqa: E402
from regime_sweep import (arm_cost, invocation_config, paired_seeds,  # noqa: E402
                          RunLedger, run_cells)
from scheduler.rank_trace import RankSnapshot                    # noqa: E402
from sim.driver import run as driver_run                         # noqa: E402
from sim.random_access import RandomAccessConfig                 # noqa: E402
from sim.run_record import RunRecord                             # noqa: E402
from sim.scenarios.g3 import (                                   # noqa: E402
    MAX_GAP_BOUND_MS, QFI_CAMERA, QFI_TELEMETRY, RAN_PDB_MS, SILENCE_ACTIVE_S,
    SILENCE_CYCLES, SILENCE_TAIL_S, SLOT_S, T_LIVE_S, TELEMETRY_PERIOD_MS,
    assert_telemetry_instrument_live, build_gt21_scenario,
    build_gt22_scenario, build_gt23_scenario, flood_ue_id, instrument_ue_ids,
    minimum_horizon_slots_gt23, resume_times_s, silence_windows,
)
from sim.srb import with_srb                                     # noqa: E402
from g11_campaign import _arm                                    # noqa: E402


def _resolve_arm(name: str):
    """The three faithful arms, plus `TwoTierProto`'s flagged divergences.

    WHY THIS IS HERE AND NOT IN `g11_campaign._arm`. That function is inside the
    published artefacts' own `code_state` scope (every G1/G2/G3/G10/G12 stamp
    reaches it), so adding an import of `scheduler/two_tier_proto.py` there
    would stale every claim in `config/published_claims.yml` for a file those
    campaigns never ran. Resolving Proto arms in the runner instead leaves the
    faithful scopes untouched -- checked with `verify_claims --check`, not
    assumed.

    Names are `Proto` + the flags, so an artefact's `arm` column says which
    divergence produced it. `ProtoOff` exists to make "off is the port"
    checkable from a campaign as well as from the unit tests.
    """
    if not name.startswith("Proto"):
        return _arm(name)
    from scheduler.two_tier_proto import TwoTierProto
    flags = {
        "ProtoOff": {},
        "ProtoE1": {"gate_follower_reserve": True},
    }
    if name not in flags:
        raise ValueError(
            f"unknown Proto arm {name!r}; known: {sorted(flags)}. A typo must "
            f"not silently fall through to the faithful arm and be reported "
            f"under a divergence name.")
    return TwoTierProto(min_rb=5, **flags[name])

#: Every real study in this branch runs with a delayed CQI rather than the
#: driver's bare 0 (CLAUDE.md's `cqi_delay_slots` invariant).
CQI_DELAY_SLOTS = 8

#: 40,000 slots at mu=2 (0.25 ms) is 10.0 s -- **100 telemetry messages per
#: robot per run** at 10 Hz. Same horizon `scripts/g1_stress.py` uses, so the
#: two campaigns' cells are directly comparable.
#:
#: WHAT 100 SUPPORTS AND WHAT IT DOES NOT. p98 needs n > 1/(1-p) = 50 to be a
#: percentile at all rather than the maximum wearing one, so 100 clears it by
#: 2x and the p98 index is the 2nd-largest sample. p99 would need 100 and p99.9
#: would need 1,000, so NEITHER is quoted from this grid -- the long-horizon
#: pass exists for the tail. The gap criterion is a MAXIMUM, so its sample
#: size is 99 gaps per robot per run and the window must be able to CONTAIN
#: the gap it forbids: 10 s can hold five 2 s gaps, and the positive control
#: demonstrates a >500 ms gap at this exact horizon rather than leaving it
#: argued.
HORIZON_SLOTS = 40_000

#: Sub-experiment A. Brackets every arm's re-measured G10 boundary
#: (PF 12 / Reservation 6 / TwoTier 7, `sweeps/g1-stress/g10_remeasure_cap4.json`)
#: so each falls strictly inside the swept range rather than at an endpoint --
#: the defect that put G10's own answer inside an unresolved 2x gap. 24 is past
#: the largest by 2x so the table shows a trend rather than a row of passes.
UE_AXIS: tuple[int, ...] = (4, 6, 7, 8, 10, 12, 14, 16, 24)

#: Sub-experiment B. The committed axis, same shape as G1's and G12's: the
#: whole committed workload, offered bytes and contract together. Telemetry is
#: NOT scaled -- a robot asked to carry more video does not send a different
#: heartbeat (`sim/scenarios/g3.py`).
LOAD_AXIS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 3.0)

#: Sub-experiment C. GT-2.1's own axis: how hard the robot's own camera is
#: driven, as a multiple of its GFBR. 2.0 IS "at MFBR", which is what the test
#: asks for; 1.0 is the nominal control and 3.0 is past the entitlement.
CAM_AXIS: tuple[float, ...] = (1.0, 1.5, 2.0, 3.0)

#: Sub-experiment D. GT-2.3's buckets, from the plan verbatim. They straddle
#: two-tier's 2 s floor-arming horizon deliberately: 1 s inside, 5 s and 60 s
#: outside. REPORTED SEPARATELY AND NEVER POOLED -- a pass at 1 s and a fail
#: at 60 s is a finding about the SR path, not noise.
SILENCE_AXIS: tuple[float, ...] = (1.0, 5.0, 60.0)

#: The positive control's SNR ladder, same shape as G1's: the one lever that
#: weakens the cell without touching the instrument, the bound or the scoring.
SNR_AXIS: tuple[float, ...] = (20.0, 15.0, 10.0, 5.0, 0.0, -3.0, -6.0)

_T_LIVE_MS = T_LIVE_S * 1000.0

#: The key element two-tier's comparator sets for a fired floor
#: (`_ul_rank_key`: `0 if candidate.floor_fire else 1`). 0 sorts first, which
#: is the whole point of Tier 1.5. Pinned by
#: `sim/tests/test_g3_floor_tally.py`, which counts fires independently and
#: requires the two to agree -- so a polarity flip in the comparator is a test
#: failure rather than a silent zero here.
_FLOOR_FIRED_KEY_VALUE = 0
_FLOOR_TERM = "floor_fire"


class FloorFireTally:
    """Counts UL service-interval-floor fires out of the rank stream.

    O(candidates) per snapshot and retains nothing per slot, so it is safe at
    any horizon -- the parent never sees a snapshot (`docs/wp9-plan.md`'s
    25 GB retention lesson, which was reintroduced one layer down inside a
    worker the first time).

    `arm_declares_floor` is False for PF and Reservation, whose keys have no
    such tier at all -- **Reservation has no floor even in principle**
    (`docs/hardware-findings.md`), so a zero from those arms is a structural
    fact and is reported as `None` rather than as an observed zero. Telling
    those two apart is the whole reason the term index is looked up by NAME
    from the snapshot's own `term_names` instead of being a literal.
    """

    def __init__(self) -> None:
        self.arm_declares_floor: Optional[bool] = None
        self._idx: Optional[int] = None
        self.fires = 0
        self.fire_slots = 0
        self.by_ue: dict[int, int] = {}
        self.snapshots = 0
        self.candidate_slots = 0

    def __call__(self, snap: RankSnapshot) -> None:
        if snap.direction != "UL":
            return
        self.snapshots += 1
        self.candidate_slots += len(snap.entries)
        if self.arm_declares_floor is None:
            self.arm_declares_floor = _FLOOR_TERM in snap.term_names
            if self.arm_declares_floor:
                self._idx = snap.term_names.index(_FLOOR_TERM)
        if not self.arm_declares_floor:
            return
        hit = 0
        for e in snap.entries:
            if e.key[self._idx] == _FLOOR_FIRED_KEY_VALUE:
                hit += 1
                self.by_ue[e.ue_id] = self.by_ue.get(e.ue_id, 0) + 1
        self.fires += hit
        if hit:
            self.fire_slots += 1

    def report(self) -> dict[str, Any]:
        if not self.arm_declares_floor:
            # NOT zero: this arm's comparator has no such tier.
            return {"floor_fires": None, "floor_fire_slots": None,
                    "floor_fire_ues": None,
                    "rank_snapshots": self.snapshots,
                    "rank_candidate_slots": self.candidate_slots}
        return {"floor_fires": self.fires, "floor_fire_slots": self.fire_slots,
                "floor_fire_ues": len(self.by_ue),
                "rank_snapshots": self.snapshots,
                "rank_candidate_slots": self.candidate_slots}


# ------------------------------------------------------------------ scoring

def _completions(fr) -> list[float]:
    """Every fully-delivered message's completion timestamp, seconds, sorted.

    Telemetry is single-role (`periodic_control` with no `streams`), so the
    roles are pooled rather than one being picked by name -- picking would
    silently drop a sub-stream if one were ever added.
    """
    out: list[float] = []
    for ts in (fr.completion_ts_by_role_s or {}).values():
        out += list(ts)
    return sorted(out)


def _steady_state_gaps(ts: list[float]) -> list[float]:
    return [(b - a) * 1000.0 for a, b in zip(ts, ts[1:])]


def _resume_scoring(ts: list[float], resumes: tuple[float, ...],
                    horizon_s: float, silence_s: float) -> dict[str, Any]:
    """GT-2.3's own statistic, and the reason it is not the raw gap.

    For each scripted resume: how long after the robot started talking again
    did the MEC hear it. A resume with NO completion before the next pause is
    a FAILURE with the remaining run as a lower bound -- `docs/wp9-plan.md`
    §34.5a's point that firing and finishing are different questions.

    Gaps that lie entirely inside an active window are ordinary steady-state
    gaps and are returned separately; the gap that straddles a silence is
    reported raw so a reader can see the scripted pause is its dominant term.
    """
    post: list[float] = []
    raw_straddle: list[float] = []
    never_returned = 0
    for r in resumes:
        after = [t for t in ts if t >= r]
        before = [t for t in ts if t < r]
        if not after:
            never_returned += 1
            post.append((horizon_s - r) * 1000.0)
            continue
        post.append((after[0] - r) * 1000.0)
        if before:
            raw_straddle.append((after[0] - before[-1]) * 1000.0)
    # Steady-state gaps: every consecutive pair NOT separated by a resume.
    inside: list[float] = []
    for a, b in zip(ts, ts[1:]):
        if any(a < r <= b for r in resumes):
            continue
        inside.append((b - a) * 1000.0)
    return {
        "post_silence_gaps_ms": post,
        "raw_straddle_gaps_ms": raw_straddle,
        "inside_window_gaps_ms": inside,
        "n_resumes_scheduled": len(resumes),
        "n_resumes_observed": len(resumes) - never_returned,
        "n_never_returned": never_returned,
    }


def _percentile(xs: list[float], p: float) -> Optional[float]:
    """The repo's own index convention (`sim/metrics.py::_percentile`), reused
    so a number computed here cannot disagree with one computed there."""
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * p))]


def _m05_for(fr) -> Optional[float]:
    """PDU-set completeness for one framed flow, `sim/scorecard.py::
    _m05_pdu_set_completeness`'s own formula: on-time complete frames over
    every frame generated. None for a flow that generated no frames."""
    fc = fr.frame_completions or {}
    total = fc.get("total") or 0
    if not total:
        return None
    ages = fc.get("complete_ages_ms") or []
    on_time = sum(1 for a in ages if a <= fr.pdb_ms)
    return on_time / total


# ------------------------------------------------------------------ one run

def _build(task: dict[str, Any]):
    kind = task["kind"]
    common = dict(seed=task["seed"], n_ues=task["n_ues"],
                  committed_mult=task["committed_mult"],
                  telemetry_gbr=task["telemetry_gbr"],
                  bsd_ms=task["bsd_ms"], snr_db=task["snr_db"])
    if kind == "gt21":
        return build_gt21_scenario(
            horizon_slots=task["horizon"],
            camera_offer_x_gfbr=task["cam_x"], **common)
    if kind == "gt22":
        return build_gt22_scenario(horizon_slots=task["horizon"], **common)
    if kind == "gt23":
        return build_gt23_scenario(
            silence_s=task["silence_s"], horizon_slots=task["horizon"],
            cycles=SILENCE_CYCLES, pause_whole_ue=task["pause_ue"], **common)
    raise ValueError(f"unknown kind {kind!r}")


def one(packed: tuple) -> dict[str, Any]:
    task = dict(packed)
    sc = _build(task)
    assert_telemetry_instrument_live(sc)
    instr = instrument_ue_ids(sc)
    flood = flood_ue_id(sc)
    horizon_s = sc.horizon_slots * SLOT_S
    resumes = (resume_times_s(task["silence_s"], cycles=SILENCE_CYCLES)
               if task["kind"] == "gt23" else ())

    sched = _resolve_arm(task["arm"])
    tally = FloorFireTally()
    sched.rank_sink = tally
    ra = {**RandomAccessConfig.deployed().to_dict(), "srb": True}
    t0 = time.time()
    summ = driver_run(with_srb(sc), sched, cqi_delay_slots=CQI_DELAY_SLOTS,
                      max_sched_ues=task["cap"], random_access=ra)
    wall = time.time() - t0
    rec = RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=task["arm"], seed=task["seed"],
        flow_configs=sc.flows, summary=summ,
        arm={"cqi_delay_slots": CQI_DELAY_SLOTS, "max_sched_ues": task["cap"]},
        meta={})

    # --- how many telemetry messages the source SHOULD have produced -----
    # Derived from the schedule, never restated: §34.5's rule is that a
    # mechanism must be shown to fire at the EXPECTED COUNT, because a
    # partially-degenerate run's surviving events are self-selected.
    if resumes:
        active_s = sum(min(b, horizon_s) - a
                       for a, b in silence_windows(task["silence_s"],
                                                   cycles=SILENCE_CYCLES)
                       if a < horizon_s)
    else:
        active_s = horizon_s
    expect_instrument = int(math.floor(active_s * 1000.0 / TELEMETRY_PERIOD_MS))
    expect_neighbour = int(math.floor(horizon_s * 1000.0 / TELEMETRY_PERIOD_MS))

    per_flow: list[dict[str, Any]] = []
    for ue in instr:
        key = f"ue{ue}_qfi{QFI_TELEMETRY}"
        fr = rec.flows[key]
        ts = _completions(fr)
        paused = bool(resumes) and ue == 1
        if paused:
            rs = _resume_scoring(ts, resumes, horizon_s, task["silence_s"])
            scored = rs["post_silence_gaps_ms"] + rs["inside_window_gaps_ms"]
        else:
            rs = {}
            scored = _steady_state_gaps(ts)
        # THE HEAD AND THE TAIL. Real observed silences at the MEC that no
        # inter-arrival gap describes -- see the module docstring. Both are
        # LOWER BOUNDS (the silence may continue past the window), and for a
        # paused flow the head/tail are measured against its own first and
        # last ACTIVE instants rather than the run's, or the scripted pause
        # would be counted twice.
        head_ms = (ts[0] * 1000.0) if ts else None
        tail_ms = ((horizon_s - ts[-1]) * 1000.0) if ts else None
        if paused and ts:
            wins = silence_windows(task["silence_s"], cycles=SILENCE_CYCLES)
            head_ms = (ts[0] - wins[0][0]) * 1000.0
            tail_ms = (min(horizon_s, wins[-1][1]) - ts[-1]) * 1000.0
        extended = list(scored) + [x for x in (head_ms, tail_ms)
                                   if x is not None]
        # An instrument with fewer than two completions is a FAILURE, not an
        # exclusion -- see the module docstring.
        silent = len(ts) < 2
        row = {
            "flow": key, "ue": ue, "paused": paused,
            "msgs": fr.message_count, "silent": silent,
            "expect_msgs": expect_instrument if paused else expect_neighbour,
            "p50": fr.delay_p50_ms, "p98": fr.delay_p98_ms,
            "p99": fr.delay_p99_ms, "max": fr.delay_max_ms,
            "dropped_bytes": fr.bytes_dropped_pdb,
            # the clause AS WRITTEN: a maximum over inter-arrival gaps
            "max_gap_ms": max(scored) if scored else None,
            # the longest silence the window can observe, head and tail
            # included -- the statistic that can express a robot going dark
            "max_silence_ms": max(extended) if extended else None,
            "n_gaps_over_tlive": sum(1 for g in extended if g >= _T_LIVE_MS),
            "n_gaps_over_half_tlive": sum(1 for g in extended
                                          if g >= _T_LIVE_MS / 2.0),
            "n_gaps_over_bound": sum(1 for g in extended
                                     if g > MAX_GAP_BOUND_MS),
            "n_gaps": len(extended),
            # Reported separately as well as scored: the head contains attach,
            # which is G9's clause rather than G3's.
            "first_completion_ms": head_ms,
            "tail_silence_ms": tail_ms,
        }
        row.update({k: v for k, v in rs.items() if k != "inside_window_gaps_ms"})
        if paused:
            row["max_post_silence_ms"] = (
                max(rs["post_silence_gaps_ms"])
                if rs["post_silence_gaps_ms"] else None)
            row["max_raw_straddle_ms"] = (
                max(rs["raw_straddle_gaps_ms"])
                if rs["raw_straddle_gaps_ms"] else None)
        per_flow.append(row)

    silent_any = any(r["silent"] for r in per_flow)
    gap_worst = max((r["max_gap_ms"] or 0.0) for r in per_flow)
    sil_worst = max((r["max_silence_ms"] or 0.0) for r in per_flow)
    head_worst = max((r["first_completion_ms"] or 0.0) for r in per_flow)
    tail_worst = max((r["tail_silence_ms"] or 0.0) for r in per_flow)
    p98_worst = max((r["p98"] or 0.0) for r in per_flow)
    n_over_tlive = sum(r["n_gaps_over_tlive"] for r in per_flow)
    n_over_bound = sum(r["n_gaps_over_bound"] for r in per_flow)
    msgs_short = sum(max(0, (r["expect_msgs"] or 0) - (r["msgs"] or 0))
                     for r in per_flow)

    # --- GT-2.1's fourth pass criterion: B's SLOs unaffected -------------
    # "and B's SLOs unaffected (epsilon per G6)". Epsilon is unspecified in
    # the plan, so this reports B's own absolute statistics and leaves the
    # relative bound to the analyser -- the same disposition
    # `scripts/guarantee_scorecard.py` records for G7's clause 1.
    nb_gap, nb_p98, nb_m05 = [], [], []
    for k, fr in rec.flows.items():
        if fr.ue_id in instr:
            continue
        if fr.qfi == QFI_TELEMETRY and fr.direction == "UL":
            g = _steady_state_gaps(_completions(fr))
            if g:
                nb_gap.append(max(g))
            if fr.delay_p98_ms is not None:
                nb_p98.append(fr.delay_p98_ms)
        if fr.qfi == QFI_CAMERA:
            m5 = _m05_for(fr)
            if m5 is not None:
                nb_m05.append(m5)
    # ... and the flooding robot's own camera/telemetry, which GT-2.2 scores
    # as an instrument, so its M05 is reported separately from the bystanders.
    instr_m05 = [m for m in (_m05_for(fr) for fr in rec.flows.values()
                             if fr.qfi == QFI_CAMERA and fr.ue_id in instr)
                 if m is not None]

    ul = sum(fr.throughput_bps for fr in rec.flows.values()
             if fr.direction == "UL")
    dl = sum(fr.throughput_bps for fr in rec.flows.values()
             if fr.direction == "DL")
    flood_bps = 0.0
    if flood is not None:
        fk = f"ue{flood}_qfi9"
        if fk in rec.flows and rec.flows[fk].direction == "UL":
            flood_bps = rec.flows[fk].throughput_bps
    prot_bps = sum(fr.throughput_bps for fr in rec.flows.values()
                   if fr.direction == "UL" and fr.qfi not in (8, 9))

    counters = summ.get("scheduler_counters") or {}
    out = {
        **{k: task[k] for k in _TASK_KEYS},
        "wall_s": round(wall, 2),
        "sim_s": round(horizon_s, 3),
        # the three clause parts
        "part1_pass": (not silent_any) and gap_worst <= MAX_GAP_BOUND_MS,
        # THE SAME BOUND OVER THE STATISTIC THAT CAN EXPRESS THE FAILURE.
        "part1s_pass": (not silent_any) and sil_worst <= MAX_GAP_BOUND_MS,
        "part2_pass": (not silent_any) and n_over_tlive == 0,
        "part3_pass": (not silent_any) and p98_worst <= RAN_PDB_MS,
        "silent_instrument": silent_any,
        "gap_worst_ms": round(gap_worst, 3),
        "silence_worst_ms": round(sil_worst, 3),
        "head_worst_ms": round(head_worst, 3),
        "tail_worst_ms": round(tail_worst, 3),
        "p98_worst_ms": p98_worst,
        "n_gaps_over_tlive": n_over_tlive,
        "n_gaps_over_bound": n_over_bound,
        "n_gaps_total": sum(r["n_gaps"] for r in per_flow),
        "msgs_short": msgs_short,
        "msgs_expected": sum(r["expect_msgs"] or 0 for r in per_flow),
        "msgs_delivered": sum(r["msgs"] or 0 for r in per_flow),
        "n_never_returned": sum(r.get("n_never_returned", 0) for r in per_flow),
        "n_resumes_scheduled": sum(r.get("n_resumes_scheduled", 0)
                                   for r in per_flow),
        "n_resumes_observed": sum(r.get("n_resumes_observed", 0)
                                  for r in per_flow),
        "max_post_silence_ms": max(
            (r.get("max_post_silence_ms") or 0.0 for r in per_flow),
            default=0.0),
        "max_raw_straddle_ms": max(
            (r.get("max_raw_straddle_ms") or 0.0 for r in per_flow),
            default=0.0),
        # the second asset
        "nb_gap_worst_ms": round(max(nb_gap), 3) if nb_gap else None,
        "nb_p98_worst_ms": max(nb_p98) if nb_p98 else None,
        "nb_m05_worst": min(nb_m05) if nb_m05 else None,
        "instr_m05_worst": min(instr_m05) if instr_m05 else None,
        # the cell
        "ul_mbps": round(ul / 1e6, 3), "dl_mbps": round(dl / 1e6, 3),
        "flood_mbps": round(flood_bps / 1e6, 3),
        "prot_ul_mbps": round(prot_bps / 1e6, 3),
        # the UL floor, reported beside the verdict per GT-2.2's own text
        **tally.report(),
        "cp_floor_fired": counters.get("cp_floor_fired", 0),
        "per_flow": per_flow,
    }
    return out


# ------------------------------------------------------------- aggregation

_FIGURE_FIELDS = (
    "kind", "arm", "seed", "cap", "n_ues", "committed_mult", "cam_x",
    "silence_s", "telemetry_gbr", "bsd_ms", "snr_db", "horizon", "pause_ue",
    "wall_s",
    "sim_s", "part1_pass", "part1s_pass", "part2_pass", "part3_pass",
    "silent_instrument", "gap_worst_ms", "silence_worst_ms", "head_worst_ms",
    "tail_worst_ms", "p98_worst_ms", "n_gaps_over_tlive", "n_gaps_over_bound",
    "n_gaps_total", "msgs_short", "msgs_expected", "msgs_delivered",
    "n_never_returned", "n_resumes_scheduled", "n_resumes_observed",
    "max_post_silence_ms", "max_raw_straddle_ms", "nb_gap_worst_ms",
    "nb_p98_worst_ms", "nb_m05_worst", "instr_m05_worst", "ul_mbps",
    "dl_mbps", "flood_mbps", "prot_ul_mbps", "floor_fires",
    "floor_fire_slots", "floor_fire_ues", "rank_snapshots",
    "rank_candidate_slots", "cp_floor_fired",
)


def _summarise(rows: list[dict], axis_key: str, axis: tuple) -> dict[str, Any]:
    """Per axis point: pass count for each clause part plus the reported
    figures. The BOUNDARY is the last axis point passing on every seed,
    contiguous from the smallest -- G10's own standing rule, so a
    non-monotone arm is reported rather than smoothed."""
    n_seeds = max((sum(1 for r in rows if r[axis_key] == a) for a in axis),
                  default=0)
    points = []
    for a in axis:
        cell = [r for r in rows if r[axis_key] == a]
        if not cell:
            continue
        assert len(cell) == n_seeds, (
            f"axis point {axis_key}={a} has {len(cell)} rows, expected "
            f"{n_seeds} -- never score a short or empty selection")
        gaps = [r["gap_worst_ms"] for r in cell]
        sils = [r["silence_worst_ms"] for r in cell]
        p98s = [r["p98_worst_ms"] or 0.0 for r in cell]
        points.append({
            axis_key: a, "n_seeds": len(cell),
            "part1_pass": sum(1 for r in cell if r["part1_pass"]),
            "part1s_pass": sum(1 for r in cell if r["part1s_pass"]),
            "silence_median_ms": round(statistics.median(sils), 3),
            "silence_worst_ms": round(max(sils), 3),
            "head_worst_ms": round(max(r["head_worst_ms"] for r in cell), 3),
            "tail_worst_ms": round(max(r["tail_worst_ms"] for r in cell), 3),
            "part2_pass": sum(1 for r in cell if r["part2_pass"]),
            "part3_pass": sum(1 for r in cell if r["part3_pass"]),
            "all_pass": sum(1 for r in cell if r["part1_pass"]
                            and r["part2_pass"] and r["part3_pass"]),
            "all_pass_strict": sum(1 for r in cell if r["part1s_pass"]
                                   and r["part2_pass"] and r["part3_pass"]),
            "silent_seeds": sum(1 for r in cell if r["silent_instrument"]),
            "gap_median_ms": round(statistics.median(gaps), 3),
            "gap_worst_ms": round(max(gaps), 3),
            "p98_median_ms": round(statistics.median(p98s), 3),
            "p98_worst_ms": round(max(p98s), 3),
            "n_gaps_over_tlive": sum(r["n_gaps_over_tlive"] for r in cell),
            "n_gaps_over_bound": sum(r["n_gaps_over_bound"] for r in cell),
            "n_gaps_total": sum(r["n_gaps_total"] for r in cell),
            "msgs_short": sum(r["msgs_short"] for r in cell),
            "msgs_expected": sum(r["msgs_expected"] for r in cell),
            "n_never_returned": sum(r["n_never_returned"] for r in cell),
            "max_post_silence_ms": round(
                max(r["max_post_silence_ms"] for r in cell), 3),
            "nb_gap_worst_ms": max((r["nb_gap_worst_ms"] or 0.0)
                                   for r in cell),
            "nb_m05_worst": min((r["nb_m05_worst"] if r["nb_m05_worst"]
                                 is not None else 1.0) for r in cell),
            "flood_mbps_median": round(statistics.median(
                [r["flood_mbps"] for r in cell]), 3),
            "prot_ul_mbps_median": round(statistics.median(
                [r["prot_ul_mbps"] for r in cell]), 3),
            # None (the arm has no such tier) is kept distinct from 0 (it
            # has one and it never fired) -- the difference between a
            # structural absence and a measured silence.
            "floor_fires": (None if cell[0]["floor_fires"] is None
                            else sum(r["floor_fires"] for r in cell)),
            "floor_fire_slots": (None if cell[0]["floor_fire_slots"] is None
                                 else sum(r["floor_fire_slots"] for r in cell)),
            "rank_candidate_slots": sum(r["rank_candidate_slots"]
                                        for r in cell),
            "wall_s_total": round(sum(r["wall_s"] for r in cell), 1),
        })

    def boundary(field: str) -> Optional[Any]:
        best = None
        for p in points:
            if p[field] == p["n_seeds"]:
                best = p[axis_key]
            else:
                break
        return best

    return {
        "axis": axis_key, "points": points,
        "boundary_part1": boundary("part1_pass"),
        "boundary_part1s": boundary("part1s_pass"),
        "boundary_part2": boundary("part2_pass"),
        "boundary_part3": boundary("part3_pass"),
        "boundary_all": boundary("all_pass"),
        "boundary_all_strict": boundary("all_pass_strict"),
        "n_runs": len(rows),
        "wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
    }


def _campaign_part2(rows: list[dict]) -> dict[str, Any]:
    """Part 2 is a CAMPAIGN-wide criterion: *"zero gaps >= T_live over the
    full campaign"*. So it gets one verdict over every scored gap, not a
    per-run pass rate -- and the demonstrable bound when the count is zero is
    §5.3's rule of three over the gap population, which is what makes the
    denominator worth carrying."""
    n_gaps = sum(r["n_gaps_total"] for r in rows)
    n_over = sum(r["n_gaps_over_tlive"] for r in rows)
    out = {
        "gaps_scored": n_gaps, "gaps_over_t_live": n_over,
        "t_live_ms": _T_LIVE_MS,
        "verdict": "PASS" if n_over == 0 else "FAIL",
        "runs": len(rows),
    }
    if n_over == 0 and n_gaps:
        out["rule_of_three_bound"] = 3.0 / n_gaps
    return out


# ------------------------------------------------------------------- driver

_TASK_KEYS = ("kind", "arm", "seed", "cap", "n_ues", "committed_mult",
              "cam_x", "silence_s", "telemetry_gbr", "bsd_ms", "snr_db",
              "horizon", "pause_ue")


def _task(**kw) -> tuple:
    """A task is a tuple of (key, value) pairs so the LEDGER KEY CARRIES THE
    WHOLE RUN-DEFINING CONFIG. G11 lost real records to a `--smoke`
    invocation sharing a production `--out` because its key did not."""
    base = dict(kind="gt22", arm="PF", seed=0, cap=4, n_ues=6,
                committed_mult=1.0, cam_x=1.0, silence_s=0.0,
                telemetry_gbr=True, bsd_ms=0.0, snr_db=20.0,
                horizon=HORIZON_SLOTS, pause_ue=False)
    base.update(kw)
    if base["bsd_ms"] == 0.0:
        base["bsd_ms"] = None
    return tuple((k, base[k]) for k in _TASK_KEYS)


def _cost(t: tuple) -> float:
    d = dict(t)
    return arm_cost(d["arm"]) * d["n_ues"] * (d["horizon"] / HORIZON_SLOTS)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=10)
    # CAP 4 ONLY BY DEFAULT -- the deployment's value (106 PRB), and the one
    # to quote. Cap 2 (this carrier's faithful derivation at 55 PRB) is a
    # second full grid and is added only if a verdict comes out close enough
    # for the cap to decide it. Scope decision recorded 2026-09-09; for G2 the
    # cap WAS the dominant term, so this is a judgement about G3's own
    # margins, not a general rule.
    ap.add_argument("--caps", default="4")
    ap.add_argument("--fixed-n", type=int, required=True,
                    help="the fleet size sub-experiments B/C/D hold; DERIVED "
                         "from the re-measured G10 boundaries, never a default")
    # A, D, the two configuration controls and the positive control.
    #
    # WHAT IS DEFERRED AND WHY, so neither gets rediscovered as an
    # opportunity:
    #   * **B, the committed-load axis.** Fleet size is the axis that ranges
    #     across G10's re-measured boundaries and is therefore comparable with
    #     G1's and G9's cells; load is a second grid that follows only if
    #     fleet size shows nothing.
    #   * **C, GT-2.1.** The plan's own text says a GT-2.1 failure is fixed
    #     UE-side ("the fix is UE-side `prioritisedBitRate` configuration, not
    #     the gNB scheduler"), so it discriminates the ARMS weakly -- which is
    #     the thing this evaluation exists to do. Its mechanism is not lost:
    #     the `ctl` pass measures the same PBR lever on GT-2.2's cell, where
    #     the flood makes grants scarce, so the intra-UE effect is still
    #     observed under the condition that makes it bite.
    # Both remain buildable (`--parts B,C`); neither is in the default grid.
    ap.add_argument("--parts", default="A,D,E,ctl,snr",
                    help="which sub-experiments to run")
    ap.add_argument("--long-horizon", type=int, default=200_000,
                    help="the flatness pass's horizon (0 disables)")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--out", default="sweeps/g3-stress/g3_stress.json")
    # SIZE THE GRID BEFORE RUNNING IT. The budgeting defect this repo has
    # recorded fails by making someone launch a run they abandon, and there is
    # no artefact afterwards to catch it -- so the cost model is printed from
    # the FULL population before anything narrows it, with the per-arm
    # per-Mslot constants measured rather than guessed.
    ap.add_argument("--dry-run", action="store_true",
                    help="print the grid and its projected cost, run nothing")
    a = ap.parse_args(argv[1:])

    arms = [x for x in a.arms.split(",") if x]
    caps = [int(x) for x in a.caps.split(",") if x]
    parts = {x for x in a.parts.split(",") if x}
    seeds = paired_seeds(a.seeds)
    N = a.fixed_n

    tasks: list[tuple] = []
    for cap in caps:
        for arm in arms:
            for s in seeds:
                if "A" in parts:                    # GT-2.2, fleet axis
                    for n in UE_AXIS:
                        tasks.append(_task(kind="gt22", arm=arm, seed=s,
                                           cap=cap, n_ues=n))
                if "B" in parts:                    # GT-2.2, load axis
                    for cm in LOAD_AXIS:
                        tasks.append(_task(kind="gt22", arm=arm, seed=s,
                                           cap=cap, n_ues=N,
                                           committed_mult=cm))
                if "C" in parts:                    # GT-2.1, over-drive axis
                    for cx in CAM_AXIS:
                        tasks.append(_task(kind="gt21", arm=arm, seed=s,
                                           cap=cap, n_ues=N, cam_x=cx))
                if "D" in parts:                    # GT-2.3, silence buckets
                    for sil in SILENCE_AXIS:
                        tasks.append(_task(
                            kind="gt23", arm=arm, seed=s, cap=cap, n_ues=N,
                            silence_s=sil,
                            horizon=minimum_horizon_slots_gt23(sil)))
                if "E" in parts:
                    # THE CONFIGURATION THAT ACTUALLY REACHES GT-2.3'S NAMED
                    # MECHANISM. With only telemetry paused the robot's camera
                    # keeps buying grants, so the resumed heartbeat rides one
                    # and no scheduling request is ever sent -- measured at
                    # 0.5-15.7 ms post-silence, below one SR opportunity. Here
                    # the WHOLE robot's uplink pauses, so it must re-acquire a
                    # grant from scratch. See `sim/scenarios/g3.py`.
                    for sil in SILENCE_AXIS:
                        tasks.append(_task(
                            kind="gt23", arm=arm, seed=s, cap=cap, n_ues=N,
                            silence_s=sil, pause_ue=True,
                            horizon=minimum_horizon_slots_gt23(sil)))
                if "ctl" in parts:
                    # TWO CONFIGURATION CONTROLS, on GT-2.2's own cell.
                    #   * `telemetry_gbr=False` -- the configuration EVERY
                    #     earlier G3 number was measured on (Delay class, no
                    #     GFBR, and therefore no LCP token bucket). This is
                    #     what keeps GT-2.1's mechanism measured even though
                    #     GT-2.1 itself is deferred: the flood makes grants
                    #     scarce, which is the condition that makes the
                    #     intra-UE split bite.
                    #   * `bsd_ms=5.0` -- the bucket duration, the one number
                    #     in the mechanism with no provenance, at the only
                    #     value the deployed source states anywhere
                    #     (`mac_rrc_dl_handler.c:227-228`, the SRB path's
                    #     `bucketSizeDuration_ms5`). 100 ms biases TOWARD the
                    #     starvation, so this is the robustness check in the
                    #     direction that could withdraw the finding.
                    tasks.append(_task(kind="gt22", arm=arm, seed=s, cap=cap,
                                       n_ues=N, telemetry_gbr=False))
                    tasks.append(_task(kind="gt22", arm=arm, seed=s, cap=cap,
                                       n_ues=N, bsd_ms=5.0))
                if a.long_horizon and "A" in parts:
                    tasks.append(_task(kind="gt22", arm=arm, seed=s, cap=cap,
                                       n_ues=N, horizon=a.long_horizon))
    if "snr" in parts:
        # The positive control: cap 4 only (the deployment's value) and two
        # seeds, because it is a demonstration that failure is REACHABLE, not
        # a graded measurement.
        for arm in arms:
            for s in seeds[:2]:
                for snr in SNR_AXIS:
                    tasks.append(_task(kind="gt22", arm=arm, seed=s, cap=4,
                                       n_ues=N, snr_db=snr))
    tasks = list(dict.fromkeys(tasks))

    # THE COST IS EXTRAPOLATED FROM THE FULL POPULATION, before any flag
    # narrows it -- the budgeting defect (`docs/wp9-plan.md`'s --time-cell
    # instance) fails by making someone launch a run they abandon, and there
    # is no artefact to catch it afterwards.
    slot_total = sum(dict(t)["horizon"] for t in tasks)
    print(f"G3 stress: {len(tasks)} driver runs, "
          f"{slot_total/1e6:.1f}M slots ({slot_total*SLOT_S/3600:.2f} "
          f"simulated hours)\n"
          f"  parts {sorted(parts)}  arms {arms}  caps {caps}  "
          f"seeds {a.seeds}  fixed N={N}\n"
          f"  bounds: max gap <= {MAX_GAP_BOUND_MS:g} ms, zero gaps >= "
          f"{_T_LIVE_MS:g} ms (campaign), p98 <= {RAN_PDB_MS:g} ms",
          flush=True)
    for kind in ("gt21", "gt22", "gt23"):
        k = [t for t in tasks if dict(t)["kind"] == kind]
        if k:
            print(f"    {kind}: {len(k)} runs, "
                  f"{sum(dict(t)['horizon'] for t in k)/1e6:.1f}M slots",
                  flush=True)

    # Measured on this machine, 2026-09-09, one run per (arm, cell) at N=6 and
    # N=24 (`docs/g3-registration-2026-09-09.md` §5). Seconds per million
    # slots at N=6, and the linear N term, both from that calibration -- NOT a
    # guess, and stated with the configuration they were taken in, since a
    # cost quoted outside its configuration is the error this project has
    # recorded three times.
    _PER_MSLOT_N6 = {"PF": 177.8, "Reservation": 240.7, "TwoTier": 472.6}
    _N_SLOPE = 1.544 / 11.90        # fractional cost per extra UE, from
    #                                 mean 11.90 s at N=6 -> 39.70 s at N=24
    cpu = 0.0
    for t in tasks:
        d = dict(t)
        base = _PER_MSLOT_N6.get(d["arm"], 300.0) * d["horizon"] / 1e6
        cpu += base * (1.0 + _N_SLOPE * (d["n_ues"] - 6))
    eff = 0.77                      # measured pool efficiency (wp9-g11 §1.3)
    print(f"  projected cost: {cpu/3600:.2f} h CPU -> "
          f"{cpu/(a.workers*eff)/60:.0f} min wall at {a.workers} workers "
          f"(x{eff:g} measured pool efficiency)", flush=True)

    # AND THE PEAK MEMORY, because on this campaign memory bound the grid and
    # time did not. Measured 2026-09-09: a pool of 14 workers on 800,000-slot
    # GT-2.3 runs reached 17.0 GB resident with 1.5 GB of machine memory left,
    # projecting ~56 GB against 31 GB of RAM -- the run was killed and the
    # grid re-sized. `sim/messages.py`'s per-message ledger over a 50 Mbps
    # saturating flood is the cost, and it scales with SLOTS.
    #
    # A PER-PROCESS CEILING WOULD NOT HAVE CAUGHT IT (no single worker
    # approached one) and `regime_sweep.run_cells` watches memory not at all --
    # it carries the pool's other four measured lessons and not this one. So
    # the projection lives here, at the point of use, where it is checkable
    # against `free` before a launch rather than after an OOM.
    _MB_PER_KSLOT = 2.5             # at N=6 with the flood; scales with slots
    worst_mb = max((dict(t)["horizon"] / 1000.0) * _MB_PER_KSLOT
                   * max(1.0, dict(t)["n_ues"] / 6.0) for t in tasks)
    print(f"  projected peak memory: {a.workers * worst_mb / 1024:.1f} GB "
          f"({worst_mb:.0f} MB x {a.workers} workers, worst task "
          f"{max(dict(t)['horizon'] for t in tasks):,} slots)", flush=True)
    if a.dry_run:
        print("  --dry-run: nothing was run")
        return 0

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    ledger = RunLedger(out.with_suffix(".runs.jsonl"),
                       {**invocation_config(a), "cqi": CQI_DELAY_SLOTS,
                        "cycles": SILENCE_CYCLES,
                        "active_s": SILENCE_ACTIVE_S, "tail_s": SILENCE_TAIL_S},
                       _TASK_KEYS)
    done = ledger.done_keys()
    rows: list[dict] = list(ledger.banked())
    todo = [t for t in tasks
            if tuple(dict(t)[k] for k in _TASK_KEYS) not in done]
    print(f"  {len(rows)} banked, {len(todo)} to run", flush=True)

    t0 = time.time()
    for _i, r in run_cells(one, todo, a.workers, cost=_cost):
        rows.append(r); ledger.bank(r)
        if len(rows) % 25 == 0:
            print(f"    ... {len(rows)}/{len(tasks)} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    wall = time.time() - t0

    # ROWS IN TASK ORDER, NOT COMPLETION ORDER. `run_cells` is a generator
    # yielding whichever run finishes first, so appending as they arrive makes
    # the artefact's row order depend on the WORKER COUNT -- and a resume's
    # banked rows arrive in ledger-file order on top of that.
    #
    # CAUGHT BY `scripts/verify_parallel.py`, not by reading the code: the
    # serial and parallel artefacts differed at `.rows[0].dl_mbps`, 0.077
    # against 0.23, which is the same run appearing in a different position.
    # Every aggregate in this file is order-independent, so **no verdict was
    # affected** -- but an artefact whose row order moves with `--workers` is
    # not byte-identical, and byte-identity is this project's acceptance
    # criterion for a pool rather than a nicety (CLAUDE.md: "it is a
    # CORRECTNESS change, not a speedup").
    #
    # Sorted on the task key, stringified so the `bsd_ms` column's `None`
    # sorts against floats without raising. That is total and deterministic,
    # and it survives a resume as well as a re-run.
    rows.sort(key=lambda r: tuple(str(r[k]) for k in _TASK_KEYS))
    doc: dict[str, Any] = {
        "code_state": stamp(),
        "rows": [{k: r[k] for k in _FIGURE_FIELDS} for r in rows],
        "_horizon_slots": HORIZON_SLOTS, "_long_horizon": a.long_horizon,
        "_max_gap_bound_ms": MAX_GAP_BOUND_MS, "_t_live_ms": _T_LIVE_MS,
        "_ran_pdb_ms": RAN_PDB_MS, "_fixed_n": N,
        "_ue_axis": list(UE_AXIS), "_load_axis": list(LOAD_AXIS),
        "_cam_axis": list(CAM_AXIS), "_silence_axis": list(SILENCE_AXIS),
        "_snr_axis": list(SNR_AXIS), "_caps": caps, "_seeds": a.seeds,
        "_cycles": SILENCE_CYCLES,
        "_wall_s_this_invocation": round(wall, 1),
        "_ran_this_invocation": len(todo),
        # NAMED so `scripts/verify_parallel.py`'s timing-exclusion guard can
        # recognise it as a clock. That guard requires an excluded name to end
        # in `_s` or contain wall/time/elapsed, precisely so a RESULT cannot be
        # slipped into the exclusion list to make a diff disappear. This is a
        # sum of per-run wall times and must differ between a serial and a
        # parallel invocation; `_cpu_s_total` did not satisfy the rule, and
        # renaming it was the right fix rather than widening the rule.
        "_cpu_wall_s_total": round(sum(r["wall_s"] for r in rows), 1),
        "_n_runs": len(rows),
    }

    def sel(**eq):
        return [r for r in rows
                if all(r[k] == v for k, v in eq.items())]

    for cap in caps:
        for arm in arms:
            base = dict(cap=cap, arm=arm, telemetry_gbr=True, bsd_ms=None,
                        snr_db=20.0)
            aa = sel(kind="gt22", committed_mult=1.0, pause_ue=False,
                     horizon=HORIZON_SLOTS, **base)
            if aa:
                doc[f"A/cap{cap}/{arm}"] = _summarise(aa, "n_ues", UE_AXIS)
            bb = sel(kind="gt22", n_ues=N, horizon=HORIZON_SLOTS,
                     pause_ue=False, **base)
            if bb:
                doc[f"B/cap{cap}/{arm}"] = _summarise(
                    bb, "committed_mult", LOAD_AXIS)
            cc = sel(kind="gt21", n_ues=N, committed_mult=1.0,
                     pause_ue=False, **base)
            if cc:
                doc[f"C/cap{cap}/{arm}"] = _summarise(cc, "cam_x", CAM_AXIS)
            dd = sel(kind="gt23", n_ues=N, committed_mult=1.0,
                     pause_ue=False, **base)
            if dd:
                # NEVER POOLED. Each bucket is its own row, per the plan's own
                # instruction that a pass at 1 s and a fail at 60 s is a
                # finding about the SR path.
                doc[f"D/cap{cap}/{arm}"] = _summarise(
                    dd, "silence_s", SILENCE_AXIS)
    for cap in caps:
        for arm in arms:
            ee = sel(kind="gt23", n_ues=N, committed_mult=1.0, cap=cap,
                     arm=arm, telemetry_gbr=True, bsd_ms=None, snr_db=20.0,
                     pause_ue=True)
            if ee:
                doc[f"E/cap{cap}/{arm}"] = _summarise(
                    ee, "silence_s", SILENCE_AXIS)
    # The positive control and the two configuration controls, kept out of
    # the graded tables so a degraded cell cannot enter a boundary.
    doc["snr_control"] = [
        {k: r[k] for k in ("arm", "seed", "snr_db", "part1_pass",
                           "part1s_pass", "part2_pass", "part3_pass",
                           "gap_worst_ms", "silence_worst_ms",
                           "p98_worst_ms", "msgs_delivered", "msgs_expected",
                           "n_gaps_over_tlive", "silent_instrument")}
        for r in sorted(sel(kind="gt22", n_ues=N, cap=4, telemetry_gbr=True,
                            bsd_ms=None, committed_mult=1.0, pause_ue=False,
                            horizon=HORIZON_SLOTS),
                        key=lambda r: (r["arm"], -r["snr_db"], r["seed"]))
        if r["snr_db"] != 20.0]
    for label, eq in (("ctl_telemetry_delay", dict(telemetry_gbr=False)),
                      ("ctl_bsd_5ms", dict(bsd_ms=5.0))):
        doc[label] = {}
        for cap in caps:
            for arm in arms:
                cell = sel(kind="gt22", arm=arm, cap=cap, n_ues=N,
                           committed_mult=1.0, snr_db=20.0, pause_ue=False,
                           horizon=HORIZON_SLOTS, **eq)
                if cell:
                    doc[label][f"cap{cap}/{arm}"] = _summarise(
                        cell, "n_ues", (N,))
    doc["long_horizon"] = {}
    if a.long_horizon:
        for cap in caps:
            for arm in arms:
                cell = sel(kind="gt22", arm=arm, cap=cap, n_ues=N,
                           committed_mult=1.0, telemetry_gbr=True,
                           bsd_ms=None, snr_db=20.0, pause_ue=False,
                           horizon=a.long_horizon)
                if cell:
                    doc["long_horizon"][f"cap{cap}/{arm}"] = _summarise(
                        cell, "n_ues", (N,))
    # PART 2 IS CAMPAIGN-WIDE. Computed over the graded population only --
    # the SNR control is a deliberately broken cell and must not enter it.
    graded = [r for r in rows
              if r["snr_db"] == 20.0 and r["telemetry_gbr"] and
              r["bsd_ms"] is None and not r["pause_ue"]]
    doc["part2_campaign"] = _campaign_part2(graded)
    doc["part2_campaign_by_arm"] = {
        arm: _campaign_part2([r for r in graded if r["arm"] == arm])
        for arm in arms}
    doc["part2_campaign_gt23_by_bucket"] = {
        f"{sil:g}": _campaign_part2([r for r in graded
                                     if r["kind"] == "gt23"
                                     and r["silence_s"] == sil])
        for sil in SILENCE_AXIS}

    out.write_text(json.dumps(doc, indent=2, default=str))
    print(f"\nwrote {out}  ({wall:.0f}s, {len(rows)} runs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
