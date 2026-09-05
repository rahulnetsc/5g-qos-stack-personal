"""Can an ALREADY-SERVED UE lose its per-LCG estimate and fall back into the
never-granted fault?

**This is the question that decides whether the cold-start finding
transfers.** Model C and the re-join seed both supply a BSR the sim never
generates, so both answer *"does a successful attach clear the lock-out"* —
yes. Neither answers *"can a UE that HAS been served lose its estimate
again"*, and that is the route hardware takes, because hardware always
grants during attach.

TWO ROUTES EXIST IN `sim/bsr.py`, AND THEY ARE NOT EQUALLY REACHABLE.

  * **truncation** — `_assemble` memsets the per-LCG array and repopulates
    only the LCGs the chosen format reports. `short_trunc` writes exactly
    ONE LCG, so a UE with several backlogged LCGs loses the rest.
    **BUT: `_select_format` reaches `short_trunc` only on an exact
    `padding == SHORT_BSR_SZ`, and `long_trunc` reports ALL active LCGs
    unless `truncated_bsr == "spec"` (the default is "off").** WP9 §20.1
    measured padding at 0 on 13,214 of 13,214 grants at this load. So this
    route is expected to be structurally unreachable here.
  * **momentary emptiness** — the `kind == "regular"` path selects
    `fmt = "none"` when no LCG is backlogged, and `on_ul_grant` memsets the
    array BEFORE `_assemble` returns early. **A UE that momentarily drains
    every LCG loses its whole array**, and it stays zero until the next BSR.

**The second route needs no truncation, no padding coincidence and no
special mode.** It is the one the warm re-join path already uses, arrived at
from the other direction.

WHAT IS MEASURED, per UE that has had at least one prior grant:
  1. does the all-zero-with-backlog state occur at all (the precondition);
  2. how long each episode lasts;
  3. whether any UE LATCHES -- never granted again after entering it.

Outcome 3 is the one that decides the question. Registered meanings are in
`docs/rejoin-seed-and-desync-registration.md` Part 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sim.bsr as B                                        # noqa: E402
from code_state import stamp                               # noqa: E402
from sim.driver import run as driver_run                   # noqa: E402
from sim.parametric import sweep_scenario                  # noqa: E402
from sim.trace import GrantCollector                       # noqa: E402
from g11_campaign import _arm                              # noqa: E402


def one(arm: str, seed: int, n_ues: int, horizon: int, load_mult: float,
        duty_cycle: float = 1.0, shared_lcg: bool = False) -> dict:
    # duty_cycle and shared_lcg are the two knobs that could REACH the
    # emptiness route: bursty traffic lets every LCG drain together, and a
    # shared LCG reduces how many must drain at once. Trying them is what
    # separates "unreachable" from "not attempted".
    sc = sweep_scenario(seed=seed, n_ues=n_ues, horizon_slots=horizon,
                        load_mult=load_mult, duty_cycle=duty_cycle,
                        shared_lcg=shared_lcg)
    fmt_counts: dict[str, int] = {}
    _asm = B.BsrModel._assemble

    def spy_assemble(self, st, ue_id, fmt, per_lcg_true, active_lcgs, *a, **k):
        # count the format chosen AND how many LCGs it will omit -- the
        # truncation route's precondition, measured rather than assumed
        omitted = 0
        if fmt in ("short", "short_trunc"):
            omitted = max(0, len(active_lcgs) - 1)
        key = f"{fmt}|omits{omitted}"
        fmt_counts[key] = fmt_counts.get(key, 0) + 1
        return _asm(self, st, ue_id, fmt, per_lcg_true, active_lcgs, *a, **k)

    # per-UE episode tracking, streamed -- nothing retained per slot
    # EPISODES CARRY THEIR START SLOT. Without it the initial cold-start
    # episode -- every UE has one, before its first grant -- is counted as a
    # desync. The first version did exactly that and reported "8 episodes"
    # on 8 UEs, which is 1 per UE: a number that factors into the run's own
    # dimensions is almost never a measurement (CLAUDE.md).
    state: dict[int, dict] = {}
    slot_now = [0]
    _bc = B.BsrModel.broadcast

    def spy_broadcast(self, buffers, ul_access):
        r = _bc(self, buffers, ul_access)
        slot_now[0] += 1
        for ue_id, flows in self._ue_flows.items():
            est = [buffers.state(f.ue_id, f.qfi).estimated_ul_buffer_per_lcg
                   for f in flows]
            rep = [buffers.state(f.ue_id, f.qfi).bytes_reported for f in flows]
            s = state.setdefault(ue_id, {"in": False, "len": 0, "eps": [],
                                         "start": 0, "slots_faulted": 0})
            faulted = any(x > 0 for x in rep) and all(e <= 0 for e in est)
            if faulted:
                s["slots_faulted"] += 1
                if not s["in"]:
                    s["start"] = slot_now[0]
                s["in"] = True
                s["len"] += 1
            elif s["in"]:
                s["eps"].append((s["start"], s["len"]))
                s["in"] = False
                s["len"] = 0
        return r

    B.BsrModel._assemble = spy_assemble
    B.BsrModel.broadcast = spy_broadcast
    grants = GrantCollector()
    driver_run(sc, _arm(arm), cqi_delay_slots=8, record_timeseries=True,
               grant_sink=grants)
    B.BsrModel._assemble = _asm
    B.BsrModel.broadcast = _bc

    first_grant, last_grant, n_grant = {}, {}, {}
    for g in grants.finish():
        if g.direction != "UL" or g.retx_count:
            continue
        first_grant.setdefault(g.ue_id, g.slot_index)
        last_grant[g.ue_id] = g.slot_index
        n_grant[g.ue_id] = n_grant.get(g.ue_id, 0) + 1

    served = sorted(first_grant)
    per_ue = {}
    for ue in served:
        s = state.get(ue, {"eps": [], "slots_faulted": 0, "in": False,
                           "len": 0, "start": 0})
        eps = s["eps"] + ([(s["start"], s["len"])] if s["in"] else [])
        fg = first_grant[ue]
        # THE DISCRIMINATION: an episode is a DESYNC only if it begins after
        # the UE has already been served. Episodes starting before the first
        # grant are the cold start, which is a different finding and one this
        # project has already made four times.
        post = [(st_, ln) for st_, ln in eps if st_ > fg]
        pre = [(st_, ln) for st_, ln in eps if st_ <= fg]
        per_ue[str(ue)] = {
            "n_grants": n_grant[ue], "first_grant": fg,
            "last_grant": last_grant[ue],
            "slots_after_last_grant": horizon - last_grant[ue],
            "cold_start_episodes": len(pre),
            "desync_episodes": len(post),
            "slots_faulted": s["slots_faulted"],
            "longest_desync": max((ln for _st, ln in post), default=0),
            "median_desync": (sorted(ln for _st, ln in post)[len(post)//2]
                              if post else 0),
            # LATCHED: entered the fault after being served, and never
            # granted again.
            "latched": bool(post and last_grant[ue] < max(st_ for st_, _l in post)),
        }
    return {"arm": arm, "seed": seed, "n_ues": n_ues, "horizon": horizon,
            "load_mult": load_mult, "duty_cycle": duty_cycle,
            "shared_lcg": shared_lcg, "bsr_formats": fmt_counts,
            "n_served_ues": len(served),
            "n_never_granted": n_ues - len(served), "per_ue": per_ue}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="PF,Reservation,TwoTier")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n-ues", type=int, default=8)
    ap.add_argument("--horizon", type=int, default=20_000)
    ap.add_argument("--load-mult", type=float, default=1.0)
    ap.add_argument("--duty-cycle", type=float, default=1.0)
    ap.add_argument("--shared-lcg", action="store_true")
    ap.add_argument("--out", default="sweeps/postscaling-2026-09-05/desync.json")
    a = ap.parse_args()
    from regime_sweep import paired_seeds
    rows = []
    for arm in a.arms.split(","):
        for s in paired_seeds(a.seeds):
            r = one(arm, s, a.n_ues, a.horizon, a.load_mult,
                    a.duty_cycle, a.shared_lcg)
            rows.append(r)
            lat = sum(1 for v in r["per_ue"].values() if v["latched"])
            eps = sum(v["desync_episodes"] for v in r["per_ue"].values())
            cold = sum(v["cold_start_episodes"] for v in r["per_ue"].values())
            print(f"  {arm:<12} seed={s} served={r['n_served_ues']}/{a.n_ues} "
                  f"cold_start_eps={cold} DESYNC_eps={eps} latched={lat}",
                  flush=True)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"code_state": stamp(), "rows": rows}, indent=1))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
