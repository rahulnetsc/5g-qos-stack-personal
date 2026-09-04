"""Per-metric cost of one Scorecard.score() call on a real N=8 20k record,
plus what a per-axis dispatch would leave. Measures, does not reason."""
import sys, time, json, collections
from pathlib import Path
REPO = Path("/home/smart/projects/5g-qos-stack-personal")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import wp9_sweep as W
from sim.driver import run
from sim.run_record import RunRecord
from sim.scorecard import Population, Scorecard
from scheduler import load_two_tier

W._HORIZON[0] = 20000
av = {"n_ues": 8, "load_mult": 1.0}
sc = W._build(seed=1, **av)
dk = W._driver_kwargs(**av)
summary = run(sc, load_two_tier(W._TT_CONFIG, min_rb=5), **dk)
rec = RunRecord.from_summary(scenario_name=sc.name, scheduler_name="TwoTier",
                             seed=1, flow_configs=sc.flows, summary=summary,
                             arm=dict(dk), meta=dict(av))

card = Scorecard()
# Map each out["Mxx"] = self.<method>(...) line to its metric id, by wrapping.
import sim.scorecard as SC
METHODS = {
    "M01": "_m01_latency_percentiles", "M02": "_m02_pdb_violation_rate",
    "M03": "_m03_liveness_gap_distribution", "M20": "protected_fleet_liveness_gap",
    "M21": "slo_recovery_time_by_delivery", "M22": "_m22_starvation_epochs",
    "M04": "_m04_survival_time_failures", "M05": "_m05_pdu_set_completeness",
    "M06": "_m06_frame_age_at_mec", "M07": "_m07_gbr_contract_count",
    "M08": "_m08_worst_flow_gfbr_fraction", "M09": "_m09_per_second_jain",
    "M10": "_m10_aggregate_throughput", "M11": "_m11_prb_utilization",
    "M12": "_m12_cce_utilization", "M14": "_m14_communication_service_availability",
    "M15": "_m15_command_jitter", "M17": "_m17_frame_freeze_and_effective_fps",
    "M18": "_m18_rejoin_interruption_time", "M19": "_m19_slo_recovery_time",
}
times = collections.Counter()
for mid, name in METHODS.items():
    orig = getattr(Scorecard, name)
    def make(orig=orig, mid=mid):
        def wrapper(self, *a, **k):
            t0 = time.perf_counter()
            try:
                return orig(self, *a, **k)
            finally:
                times[mid] += time.perf_counter() - t0
        return wrapper
    setattr(Scorecard, name, make())

orig_restrict = Population.restrict
def timed_restrict(self, record):
    t0 = time.perf_counter()
    try:
        return orig_restrict(self, record)
    finally:
        times["__restrict__"] += time.perf_counter() - t0
Population.restrict = timed_restrict

REPS = 5
out = {}
for pop_name, pop in (("all_flows", Population.all_flows),
                      ("protected_fleet", Population.protected_fleet)):
    times.clear()
    t0 = time.perf_counter()
    for _ in range(REPS):
        card.score(rec, population=pop())
    out[pop_name] = ((time.perf_counter() - t0) / REPS,
                     {k: v / REPS for k, v in times.items()})
wall = out["all_flows"][0]
per = out["all_flows"][1]
tot = sum(per.values())
print("SCORE CALL COST BY POPULATION (s):",
      {k: round(v[0], 4) for k, v in out.items()})
print("M09+M22 share by population:",
      {k: round(100*(v[1]["M09"]+v[1]["M22"])/sum(v[1].values()), 1) for k, v in out.items()})
AX = {"survival_miss_n": ["M04"], "t_live_s": ["M03","M20","M14"],
      "gbr_contract_fraction": ["M07","M08"], "slo_green_dwell_s": ["M19"]}
tot_full = sum(12 * v[0] for v in out.values())
tot_disp = sum(sum(3*sum(v[1][m] for m in ms) for ms in AX.values()) for v in out.values())
print(f"12 variations x 2 populations, as shipped : {tot_full:.3f} s")
print(f"same, with per-axis dispatch             : {tot_disp:.3f} s")
print(f"saving                                   : {tot_full-tot_disp:.3f} s  ({tot_full/max(tot_disp,1e-9):.1f}x)")

HARVESTED = ("M03", "M04", "M07", "M08", "M14", "M19")
# What each variation axis actually changes (score()'s own cfg wiring).
AXIS_NEEDS = {
    "survival_miss_n": ["M04"],
    "t_live_s": ["M03", "M20", "M14"],
    "gbr_contract_fraction": ["M07", "M08"],
    "slo_green_dwell_s": ["M19"],
}
print(json.dumps({
    "score_call_s": wall,
    "sum_of_metric_times_s": tot,
    "per_metric_ms": {k: round(1000*v, 3) for k, v in
                      sorted(per.items(), key=lambda kv: -kv[1])},
    "harvested_only_ms": round(1000*sum(per[m] for m in HARVESTED), 3),
    "harvested_share_pct": round(100*sum(per[m] for m in HARVESTED)/tot, 2),
    "per_axis_dispatch_cost_ms": {
        ax: round(1000*sum(per[m] for m in ms), 3) for ax, ms in AXIS_NEEDS.items()},
    "full_12_variation_cost_ms": round(1000 * 12 * 2 * wall, 1),
    "dispatched_12_variation_cost_ms": round(1000 * 2 * sum(
        3 * sum(per[m] for m in ms) for ms in AXIS_NEEDS.values()), 1),
}, indent=2))
