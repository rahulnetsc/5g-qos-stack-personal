"""U1 -- the workload inversion, traced. `docs/u1-inversion-registration.md`.

TwoTier is worst by 3.5x on the parametric mix and best on `sensor_dense`.
The registered candidate is Tier-1's objective; this measures whether that is
what decides the sort, using the EXISTING rank-trace hook rather than a new
probe.

Two things it does, in order, and the first can invalidate the second:

  A0b  Is the loss even IN the sort? Every parametric UE carries the identical
       flow mix (periodic + XR + saturating), so the sort cannot be expressing
       a preference between flow kinds. If the worst flow's UE is granted at a
       normal rate while its own periodic flow starves, the loss is INTRA-UE
       LCP -- which the rank trace structurally cannot see, because the sort
       ranks UEs and the split happens inside the TB.

  SWAP At the loss points, which factor of `coef = (base_q + urg) * hyp_tbs`
       is SUFFICIENT to flip the comparison. First-difference alone cannot
       answer this: the three terms above `-coef` are coarse gates, so
       `decisive_term` returns `-coef` on nearly every adjacency and
       discriminates nothing. That is what `_UL_FACTORS` is carried for.

Reduces in the worker and returns scalars -- this repo has a 25 GB retention
leak in its record, twice, and a rank stream is exactly that shape.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from code_state import stamp                                  # noqa: E402
from regime_sweep import arm_cost, paired_seeds, run_cells    # noqa: E402
from scheduler.rank_trace import RankSnapshot                 # noqa: E402
from sim.driver import run as driver_run                      # noqa: E402
from sim.parametric import sweep_scenario                     # noqa: E402
from sim.run_record import RunRecord                          # noqa: E402
from sim.resource import ResourceGrid                         # noqa: E402
from sim.trace import GrantCollector                          # noqa: E402
from sim.scenarios import sensor_dense_scenario                # noqa: E402
from g11_campaign import _arm                                 # noqa: E402

#: The three factors of the UL composite, named so an analysis never indexes
#: them positionally. `norm` is a slot-level maximum common to every
#: candidate, so it cancels between any two and is deliberately absent.
FACTORS = ("base_q", "urg", "hyp_tbs_bytes")


class SwapTally:
    """Which factor of `coef` is SUFFICIENT to flip each adjacent pair.

    For a pair (winner `w`, loser `l`), substitute `w`'s value of one factor
    into `l`'s coef and ask whether that alone would have won. Reported as a
    JOINT distribution over the three factors -- including "none singly
    sufficient" and "all three" -- rather than forced onto a single winner,
    because a product of three positive factors has no reason to be decided
    by exactly one.
    """

    def __init__(self, direction: str = "UL") -> None:
        self.direction = direction
        self.slots_seen = 0
        self.pairs = 0
        self.patterns: dict[str, int] = {}
        #: loser ue -> pattern -> count. Keyed by LOSER because the flow
        #: that sets M01 p98 is only known after the run, and a tally over
        #: every pair answers a different question from "why did THIS UE
        #: lose". Bounded O(UEs x patterns), so safe at any horizon.
        self.by_ue: dict[int, dict[str, int]] = {}
        self.factor_sum: dict[str, float] = {f: 0.0 for f in FACTORS}
        self.factor_n = 0
        self._seen = False

    def __call__(self, snap: RankSnapshot) -> None:
        if snap.direction != self.direction:
            return
        self._seen = True
        self.slots_seen += 1
        ents = snap.entries
        for e in ents:
            d = dict(e.factors)
            for f in FACTORS:
                if f in d:
                    self.factor_sum[f] += d[f]
            self.factor_n += 1
        for i in range(len(ents) - 1):
            w, l = ents[i], ents[i + 1]
            fw, fl = dict(w.factors), dict(l.factors)
            if not all(f in fw and f in fl for f in FACTORS):
                continue
            cw = (fw["base_q"] + fw["urg"]) * fw["hyp_tbs_bytes"]
            cl = (fl["base_q"] + fl["urg"]) * fl["hyp_tbs_bytes"]
            if cw <= cl:
                continue                    # tied or gated above coef
            suff = []
            for f in FACTORS:
                sub = dict(fl)
                sub[f] = fw[f]
                c = (sub["base_q"] + sub["urg"]) * sub["hyp_tbs_bytes"]
                if c >= cw:
                    suff.append(f)
            key = "+".join(suff) if suff else "NONE singly sufficient"
            self.pairs += 1
            self.patterns[key] = self.patterns.get(key, 0) + 1
            d = self.by_ue.setdefault(l.ue_id, {})
            d[key] = d.get(key, 0) + 1

    def result(self) -> dict:
        if not self._seen:
            raise RuntimeError(
                "SwapTally saw no snapshot -- the hook did not bind. An empty "
                "tally must never be reported as a flat distribution.")
        n = max(self.factor_n, 1)
        return {"slots_seen": self.slots_seen, "pairs": self.pairs,
                "patterns": self.patterns,
                "by_ue": {str(k): v for k, v in self.by_ue.items()},
                "factor_means": {f: self.factor_sum[f] / n for f in FACTORS}}


def _scenario(workload: str, seed: int, n_ues: int, horizon: int):
    if workload == "parametric":
        return sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                              load_mult=1.0)
    if workload == "sensor_dense":
        # Its UE count and flow mix are the scenario's own -- `n_ues` does not
        # apply and is deliberately not forced in, since a 30-sensor workload
        # reshaped to 10 would no longer be the thing G1 was measured on.
        sc = sensor_dense_scenario()
        return dataclasses.replace(sc, seed=seed, horizon_slots=horizon)
    raise SystemExit(f"unknown workload {workload!r}")


def one(task) -> dict:
    arm, seed, workload, n_ues, horizon = task
    sc = _scenario(workload, seed, n_ues, horizon)
    sched = _arm(arm)
    tally = SwapTally("UL")
    sched.rank_sink = tally
    grants = GrantCollector()
    t0 = time.time()
    summary = driver_run(sc, sched, cqi_delay_slots=8, record_timeseries=False,
                         grant_sink=grants)
    rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name=arm,
                                 seed=seed, flow_configs=sc.flows,
                                 summary=summary, arm={}, meta={})

    # --- A0b: is the loss in the sort, or inside the UE? ------------------
    prot = [f for f in rec.flows.values()
            if f.direction == "UL" and f.qfi in (1, 2)]
    if not prot:
        prot = [f for f in rec.flows.values() if f.direction == "UL"]
    worst = max(prot, key=lambda f: (f.delay_p98_ms or 0.0))
    ue = worst.ue_id
    sib = [f for f in rec.flows.values()
           if f.ue_id == ue and f.direction == "UL"]
    # --- SERVICE CADENCE, the quantity a 0.3 %-of-bytes periodic flow's
    # latency is actually made of. Every arm delivers this flow (ratio ~1.0),
    # so the p98 difference between arms cannot be a delivery difference; it
    # is how long the flow waits between the grants that carry its bytes.
    # Measured per 5QI from the grant's own split, not inferred from totals.
    gl = [g for g in grants.finish() if g.direction == "UL" and g.ue_id == ue]
    last: dict[int, int] = {}
    gaps: dict[int, list[int]] = {}
    # THE DISCRIMINATOR. Counting slots between services cannot separate "the
    # flow waited because its UE got no grant" (a SORT loss, which the rank
    # trace can see) from "the flow waited through grants that carried only
    # its sibling's bytes" (an LCP deferral INSIDE the TB, which it cannot).
    # So count the UE's own intervening grants as well as the elapsed slots.
    since: dict[int, int] = {}
    skipped: dict[int, list[int]] = {}
    carried: dict[int, int] = {}
    for g in gl:
        served = {q for q, b in (g.split or ()) if b > 0}
        for q in list(since):
            if q not in served:
                since[q] += 1
        for q, b in (g.split or ()):
            if b <= 0:
                continue
            carried[q] = carried.get(q, 0) + 1
            if q in last:
                gaps.setdefault(q, []).append(g.slot_index - last[q])
                skipped.setdefault(q, []).append(since.get(q, 0))
            last[q] = g.slot_index
            since[q] = 0
    # Derived from the scenario's own carrier via the grid that owns the
    # definition, never restated as a constant -- `sim/resource.py:23`.
    slot_ms = ResourceGrid(sc.carrier, sc.tdd).slot_duration_s * 1000.0

    def _pct(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] * slot_ms

    def _cnt(xs, p):
        if not xs:
            return None
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]

    cadence = {str(q): {"n_services": len(v) + 1,
                        "gap_p50_ms": _pct(v, 0.50),
                        "gap_p98_ms": _pct(v, 0.98),
                        "gap_max_ms": _pct(v, 1.0),
                        # grants the UE received while THIS flow waited
                        "skipped_p50": _cnt(skipped.get(q, []), 0.50),
                        "skipped_p98": _cnt(skipped.get(q, []), 0.98),
                        "frac_ue_grants_carrying": (
                            carried.get(q, 0) / len(gl) if gl else None)}
               for q, v in sorted(gaps.items())}
    per_ue_ul = {}
    for f in rec.flows.values():
        if f.direction == "UL":
            per_ue_ul[f.ue_id] = per_ue_ul.get(f.ue_id, 0) + f.bytes_delivered
    tot = sorted(per_ue_ul.values())
    rank_of_ue = sorted(per_ue_ul, key=lambda u: per_ue_ul[u]).index(ue)
    return {
        "arm": arm, "seed": seed, "workload": workload, "n_ues": n_ues,
        "horizon": horizon, "wall_s": round(time.time() - t0, 1),
        "worst_flow": worst.key, "worst_ue": ue,
        "worst_p98_ms": worst.delay_p98_ms, "worst_pdb_ms": worst.pdb_ms,
        # A0b (i): does the UE lose in the sort? Its share of UL bytes
        # against the fleet, and where it sits in the fleet's own order.
        "ue_ul_bytes": per_ue_ul[ue],
        "ue_ul_bytes_rank": rank_of_ue,
        "fleet_ul_median": tot[len(tot) // 2],
        # A0b (ii): does the UE win its grant and starve the flow inside it?
        "siblings": {f.key: {"qfi": f.qfi,
                             "delivered": f.bytes_delivered,
                             "arrived": f.bytes_arrived,
                             "ratio": f.delivery_ratio,
                             "p98_ms": f.delay_p98_ms,
                             "pdb_ms": f.pdb_ms} for f in sib},
        "ue_ul_grants": len(gl),
        "cadence": cadence,
        "swap": tally.result(),
    }


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-ues", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    seeds = paired_seeds(a.seeds)
    tasks = [(arm, s, w, a.n_ues if w == "parametric" else 30, a.horizon)
             for w in ("parametric", "sensor_dense")
             for arm in ("PF", "Reservation", "TwoTier")
             for s in seeds]
    rows: list = [None] * len(tasks)
    for i, r in run_cells(one, tasks, a.workers,
                          cost=lambda t: arm_cost(t[0]) * t[4]):
        rows[i] = r
        print(f"  {r['arm']:12s} {r['workload']:13s} seed={r['seed']} "
              f"worst={r['worst_flow']} p98={r['worst_p98_ms']}", flush=True)
    Path(a.out).write_text(json.dumps(
        {"code_state": stamp(), "rows": rows}, indent=1))
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
