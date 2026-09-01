"""G9's join/re-join campaign (docs/wp9-plan.md §31, commit 4).

Scores J1-J5. Two assertions run BEFORE any metric is read, and the runner
refuses to report if either fails:

  1. THE EVENT-COUNT ASSERTION (CLAUDE.md's sixth empty-selection instance).
     A scenario that produces no events reads identically to one where
     everything went well: GT-6.3's first fade was half of t310, RLF never
     fired, and M18/M19 reported instant recovery. Every number was correct
     for the events that happened and there were none. So: assert non-zero
     events of the EXPECTED PATH before trusting any metric over them.

  2. THE NEIGHBOURS-POPULATION ASSERTION (§31.6). "Neighbours unaffected"
     is a delta guarantee of exactly G6's shape, and the G6 item cost four
     corrections to the same error. The population is fixed in advance --
     every UE EXCEPT the joiner, protected bearers only -- and asserted by
     printing the flow set and checking the joiner's flows are absent. A
     neighbours statistic that includes the recovering UE measures the
     event, not the containment.

Usage:
    uv run python scripts/g9_campaign.py [--smoke] [--seeds N]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from regime_sweep import bootstrap_ci, paired_seeds  # noqa: E402
from sim.baselines.pf import ProportionalFair  # noqa: E402
from sim.driver import run  # noqa: E402
from sim.run_record import RunRecord  # noqa: E402
from sim.scenarios.g9 import (gt61_warm_rejoin, gt62_cold_attach,  # noqa: E402
                              gt63_rlf_recovery, joiner_ue_id,
                              neighbour_ue_ids)
from sim.scorecard import Scorecard  # noqa: E402
from scheduler import load_two_tier  # noqa: E402
from scheduler.reservation import Reservation  # noqa: E402

_TT = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")
CQI_DELAY_SLOTS = 8
# GT-6.1 expects `warm`, GT-6.2 `cold`, GT-6.3 `reestablish`. Named per
# scenario so the assertion checks the RIGHT path, not merely "some events".
CASES = {
    "GT-6.1_warm": (gt61_warm_rejoin, "warm"),
    "GT-6.2_cold": (gt62_cold_attach, "cold"),
    "GT-6.3_rlf": (gt63_rlf_recovery, "reestablish"),
}


def _arms():
    return {"PF": lambda: ProportionalFair(ewma_window_slots=200),
            "Reservation": lambda: Reservation(min_rb=5),
            "TwoTier": lambda: load_two_tier(_TT, min_rb=5)}


def expected_event_count(sc, want_path: str) -> int | None:
    """How many events the SCENARIO SPECIFIES -- derived from the schedule,
    never restated. `reestablish` is emergent (sim/rlf.py observing the SNR
    trace), so it has no scheduled count and returns None."""
    if want_path == "reestablish":
        return None
    joiner = [ue for ue in sc.ues if ue.join is not None][0]
    kinds = {"warm": ("app_restart",), "cold": ("power_on",)}[want_path]
    return sum(1 for e in joiner.join.events if e.kind in kinds)


def assert_events_fired(rec: RunRecord, want_path: str, label: str,
                        expected: int | None = None) -> int:
    """ASSERTION 1, STRENGTHENED: assert the EXPECTED count, not non-zero.

    The first version asked only "did the mechanism fire at all". That is a
    WEAKER QUESTION than "did it fire as often as the scenario specifies",
    and the gap between them is exactly where a PARTIALLY degenerate run
    hides. It did: TwoTier recorded 3.8 of 10 scripted warm restarts and
    1.0 of 5 cold cycles, and the non-zero check passed on every one --
    so M18/M19/M21 were computed over a different, smaller and
    self-selected event set than the other arms, and the arms were compared
    as though they were not.
    """
    events = [e for e in (rec.join_events or []) if e.path == want_path]
    if not events:
        raise AssertionError(
            f"{label}: ZERO '{want_path}' events. Every metric over them "
            f"would be correct-for-nothing and read as instant success -- "
            f"CLAUDE.md's sixth empty-selection instance. Check the scenario "
            f"fired at all (for reestablish: is the fade longer than t310?).")
    if expected is not None and len(events) != expected:
        raise AssertionError(
            f"{label}: {len(events)} '{want_path}' events but the scenario "
            f"schedules {expected}. A partially-degenerate run is NOT a "
            f"smaller sample of the same thing -- the events that survive "
            f"are self-selected (here: the ones whose predecessor finished "
            f"in time), so arms with different counts are not comparable. "
            f"Known cause: a handshake slower than the scripted period "
            f"overlaps the next event, which is then dropped (§34.4).")
    return len(events)


def assert_neighbour_population(rec: RunRecord, joiner: int,
                                neighbours: list[int], label: str) -> list[str]:
    """ASSERTION 2 (§31.6). Returns the flow keys that entered the
    neighbours statistic, so the population is PRINTED, not assumed."""
    excl = Scorecard.NON_PROTECTED_5QI
    keys = sorted(fr.key for fr in rec.flows.values()
                  if fr.ue_id in neighbours and fr.qfi not in excl)
    bad = [k for k in keys if k.startswith(f"ue{joiner}_")]
    if bad:
        raise AssertionError(
            f"{label}: joiner's flows {bad} entered the NEIGHBOURS "
            f"statistic -- that measures the event, not the containment")
    if not keys:
        raise AssertionError(f"{label}: neighbours statistic selected NO flows")
    return keys


def _neighbour_stats(rec: RunRecord, neighbours: list[int]) -> dict:
    """Protected-bearer aggregates over the neighbours only."""
    excl = Scorecard.NON_PROTECTED_5QI
    flows = [fr for fr in rec.flows.values()
             if fr.ue_id in neighbours and fr.qfi not in excl]
    arr = sum(fr.bytes_arrived for fr in flows)
    bad = sum(fr.bytes_dropped_pdb + fr.bytes_delivered_late_pdb for fr in flows)
    return {"m02": (bad / arr) if arr else 0.0,
            "worst_p98_ms": max((fr.delay_p98_ms for fr in flows), default=0.0)}


def run_one(build, path, arm_name, arm_factory, seed, n_neighbours, joiner_on):
    """One run. `joiner_on=False` builds the paired CONTROL -- same seed,
    same fleet, no join schedule -- so the neighbours delta is within-seed."""
    sc = build(seed=seed, n_neighbours=n_neighbours)
    if not joiner_on:
        ues = [dataclasses.replace(ue, join=None, scripted_fade=())
               for ue in sc.ues]
        sc = dataclasses.replace(sc, ues=ues, name=sc.name + "_control")
    summary = run(sc, arm_factory(), cqi_delay_slots=CQI_DELAY_SLOTS,
                  record_timeseries=True)
    return sc, RunRecord.from_summary(
        scenario_name=sc.name, scheduler_name=arm_name, seed=seed,
        flow_configs=sc.flows, summary=summary, arm={}, meta={})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--neighbours", type=int, default=7)
    ap.add_argument("--out", default="sweeps/wp9/g9_campaign.json")
    args = ap.parse_args(argv[1:])
    n_seeds = 2 if args.smoke else args.seeds
    n_nb = 3 if args.smoke else args.neighbours
    seeds = paired_seeds(n_seeds)
    sc_card = Scorecard()
    out: dict = {}

    for label, (build, want_path) in CASES.items():
        print(f"\n{'=' * 78}\n{label}  ({want_path} path)\n{'=' * 78}", flush=True)
        out[label] = {}
        for arm_name, factory in _arms().items():
            m18, m19, m21, nb_deltas, n_ev = [], [], [], [], []
            nb_p98_deltas = []
            printed_population = False
            for seed in seeds:
                sc, rec = run_one(build, want_path, arm_name, factory, seed,
                                  n_nb, joiner_on=True)
                joiner, neighbours = joiner_ue_id(sc), neighbour_ue_ids(sc)
                n_ev.append(assert_events_fired(
                    rec, want_path, f"{label}/{arm_name}",
                    expected=expected_event_count(sc, want_path)))
                keys = assert_neighbour_population(rec, joiner, neighbours,
                                                   f"{label}/{arm_name}")
                if not printed_population:
                    print(f"  [{arm_name}] neighbours population ({len(keys)} flows): "
                          f"{keys[:4]}{' ...' if len(keys) > 4 else ''}", flush=True)
                    printed_population = True
                scored = sc_card.score(rec)
                for store, key in ((m18, "M18"), (m19, "M19"), (m21, "M21")):
                    v = (scored[key].value or {}).get("by_path", {}).get(want_path)
                    if v and v.get("p95_ms") is not None:
                        store.append(v["p95_ms"])
                _, ctl = run_one(build, want_path, arm_name, factory, seed,
                                 n_nb, joiner_on=False)
                a, b = _neighbour_stats(rec, neighbours), _neighbour_stats(ctl, neighbours)
                nb_deltas.append(a["m02"] - b["m02"])
                # M02 on the neighbours is SATURATED AT ZERO even with bg at
                # 0.876 UL utilisation -- their protected flows sit at p98
                # 15.5 ms against a 100 ms PDB, ~6x headroom. A delta of a
                # floored statistic cannot move, so the sensitive instrument
                # is the p98 delay delta. Both are reported: M02 is the
                # guarantee's own currency, p98 is what can actually detect
                # a change.
                nb_p98_deltas.append(a["worst_p98_ms"] - b["worst_p98_ms"])
                # PER-SEED heartbeat. Without it the only progress signal is
                # process liveness: this runner's first launch wrote a
                # ZERO-LINE log for its entire duration, because Python
                # block-buffers a redirected stdout and the summary prints
                # come only at the end of an arm. Same family as the run
                # logs lost to session-scoped scratchpads.
                print(f"    ... {label}/{arm_name} seed {seed} done", flush=True)
            ci = bootstrap_ci(nb_deltas, seed=4242) if nb_deltas else None
            ci_p98 = bootstrap_ci(nb_p98_deltas, seed=4243) if nb_p98_deltas else None
            rs_p98 = Scorecard.robust_delta_summary(nb_p98_deltas)
            rs = Scorecard.robust_delta_summary(nb_deltas)
            print(f"  {arm_name:<12} events/run={statistics.mean(n_ev):5.1f}  "
                  f"M18 p95={statistics.median(m18) if m18 else None}  "
                  f"M19 p95={statistics.median(m19) if m19 else None}  "
                  f"M21 p95={statistics.median(m21) if m21 else None}", flush=True)
            print(f"  {'':<12} neighbours ΔM02  mean {ci['point']:+.6f} "
                  f"[{ci['lo']:+.6f},{ci['hi']:+.6f}]  median {rs['median']:+.6f} "
                  f"worse {rs['frac_worse']:.0%}  n_seeds={rs['n']} paired")
            print(f"  {'':<12} neighbours Δp98  mean {ci_p98['point']:+.3f} ms "
                  f"[{ci_p98['lo']:+.3f},{ci_p98['hi']:+.3f}]  "
                  f"median {rs_p98['median']:+.3f}  worse {rs_p98['frac_worse']:.0%}",
                  flush=True)
            out[label][arm_name] = {
                "events_per_run": statistics.mean(n_ev),
                "m18_p95_median": statistics.median(m18) if m18 else None,
                "m19_p95_median": statistics.median(m19) if m19 else None,
                "m21_p95_median": statistics.median(m21) if m21 else None,
                "neighbour_dm02": {"ci": ci, **rs},
                "neighbour_dp98_ms": {"ci": ci_p98, **rs_p98},
            }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
