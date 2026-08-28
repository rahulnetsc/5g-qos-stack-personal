"""WP9 stage runner (`docs/wp9-plan.md` §6.3/§6.4, build item B5+B6).

Stage 1 is a **star design**: a dense core plane (N x load) plus
one-axis-at-a-time excursions from the base point. That shape is chosen
deliberately and has a consequence the runner enforces rather than merely
documents -- `regime_sweep.check_contiguity` needs grid-ADJACENT cells, and
excursions structurally cannot supply them, so **a regime-boundary claim
from stage 1 is impossible by construction, not merely discouraged**. Stage
1 selects; stage 2 confirms.

Every run's full RunRecord is persisted (build item B3) so that M13/M16 and
every scoring-parameter variation (§3) can be computed afterwards without
re-running a single cell.

Usage:
    uv run python scripts/wp9_sweep.py --stage 1 --out sweeps/wp9/stage1
    uv run python scripts/wp9_sweep.py --stage 1 --smoke     # tiny grid
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sim.parametric import sweep_scenario
from sim.run_record import RunRecord
from sim.scorecard import Scorecard
from sim.baselines.pf import ProportionalFair
from scheduler.reservation import Reservation
from scheduler import load_two_tier

from regime_sweep import axis_aware, sweep, write_csv
import wp9_gate

_TT_CONFIG = str(Path(__file__).resolve().parent.parent / "scheduler" / "scheduler_config.yaml")

# docs/wp9-plan.md §1: the base point. Every excursion is one key away.
BASE: dict[str, Any] = {
    "n_ues": 8,
    "load_mult": 1.0,
    "min_rb": 5,
    "mix": "factory",
    "duty_cycle": 1.0,
    "snr_spread_db": 0.0,
    "pdb_ms": None,
    "shared_lcg": False,
    "mfbr_multiple": 0.0,
    "bg": False,
    "inf_scenario": None,
    "sr_period_slots": 10,
    "k2_slots": 2,
}

CORE_PLANE = {
    "n_ues": [2, 4, 8, 16, 24, 32],
    "load_mult": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0],
}

# One-axis-at-a-time excursions (§3). The base level of each is already run
# by the core plane, so only the off-base levels are listed here.
EXCURSIONS: dict[str, list[Any]] = {
    "min_rb": [1, 20],
    "mfbr_multiple": [2.0],
    "duty_cycle": [0.5, 0.1],
    "snr_spread_db": [6.0, 12.0],
    "pdb_ms": [10.0, 1000.0],
    "sr_period_slots": [1, 40],
    "shared_lcg": [True],
    "k2_slots": [1, 4],
    "inf_scenario": ["DL", "DH"],
    "bg": [True],
}

DRIVER_AXES = ("sr_period_slots", "k2_slots")
CQI_DELAY_SLOTS = 8   # pinned, never swept (§3 exclusions)


def _arms() -> dict:
    """The three arms (§4). `min_rb` is an ARM-CONFIG axis, so the two
    schedulers that read it are `axis_aware`; PF does not take it."""
    return {
        "PF": lambda: ProportionalFair(ewma_window_slots=200),
        "Reservation": axis_aware(lambda min_rb=5, **_: Reservation(min_rb=min_rb)),
        "TwoTier": axis_aware(lambda min_rb=5, **_: load_two_tier(_TT_CONFIG, min_rb=min_rb)),
    }


def _driver_kwargs(**axis_values):
    dk = {
        "cqi_delay_slots": CQI_DELAY_SLOTS,
        "record_timeseries": True,     # M04/M09/M19 are `pending` without it
    }
    for k in DRIVER_AXES:
        dk[k] = axis_values.get(k, BASE[k])
    return dk


def _build(seed: int, **axis_values):
    kwargs = {**BASE, **axis_values}
    kwargs.pop("min_rb", None)          # arm-config, not a scenario property
    for k in DRIVER_AXES:
        kwargs.pop(k, None)             # driver kwarg, not a scenario property
    return sweep_scenario(seed=seed, horizon_slots=axis_values.get(
        "horizon_slots", _HORIZON[0]), **kwargs)


_HORIZON = [20_000]


class _RecordSink:
    """Build item B3. One JSONL per stage; records are what make M13/M16 and
    the scoring-parameter variations computable without re-running."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w")
        self.n = 0

    def __call__(self, record: RunRecord, axis_values: dict) -> None:
        self._fh.write(json.dumps(
            {"axis_values": axis_values, "record": record.to_dict()}) + "\n")
        self.n += 1

    def close(self):
        self._fh.close()


def _study_layer_metrics(records: list[tuple[dict, RunRecord]], out_dir: Path) -> None:
    """Build item B6: M13 and M16, which `Scorecard.score()` deliberately
    does NOT compute -- M13 is a cross-run load-ramp metric and M16 needs a
    named flow pair. A runner that forgets these silently under-reports two
    guarantees (G12, and the shared-bearer half of G1/G2/G3), which is why
    they are here and not left to the analyst.
    """
    sc = Scorecard()
    rows: list[dict] = []

    # -- M13: per (N, arm), the load column in ascending order -------------
    groups: dict[tuple, list[tuple[float, RunRecord]]] = {}
    for axis_values, rec in records:
        if set(axis_values) - {"n_ues", "load_mult"}:
            continue                     # core-plane cells only
        key = (axis_values.get("n_ues"), rec.scheduler_name, rec.seed)
        groups.setdefault(key, []).append((axis_values.get("load_mult", 0.0), rec))
    for (n_ues, arm, seed), pairs in groups.items():
        pairs.sort(key=lambda p: p[0])
        ordered = [r for _, r in pairs]
        if len(ordered) < 2:
            continue
        class_of = {fr.key: fr.qfi for fr in ordered[0].flows.values()}
        res = sc.first_violation_order(ordered, class_of)
        rows.append({"metric": "M13", "n_ues": n_ues, "scheduler": arm,
                     "seed": seed, "status": res.status, "value": res.value})

    # -- M16: the T1/T2 bearer pair -- UL telemetry (5QI 1) against DL
    # -- command (5QI 82). NOT one bidirectional bearer: this simulator keys
    # -- flows by (ue_id, qfi) with no direction term, so the hardware plan's
    # -- shared-bearer construct cannot be represented (sim/parametric.py's
    # -- _QFI_COMMAND note, docs/wp9-plan.md §5).
    for axis_values, rec in records:
        try:
            res = sc.correlate_flows(rec, (1, 1), (1, 82))
        except (KeyError, StopIteration):
            continue
        rows.append({"metric": "M16", **axis_values,
                     "scheduler": rec.scheduler_name, "seed": rec.seed,
                     "status": res.status, "value": res.value})

    (out_dir / "study_layer_metrics.json").write_text(json.dumps(rows, indent=2))
    print(f"  study-layer metrics (M13/M16): {len(rows)} rows")


def run_stage_1(out_dir: Path, n_seeds: int, horizon: int, smoke: bool) -> None:
    _HORIZON[0] = horizon
    out_dir.mkdir(parents=True, exist_ok=True)
    core = CORE_PLANE if not smoke else {"n_ues": [2, 4], "load_mult": [1.0, 2.0]}
    excursions = EXCURSIONS if not smoke else {"min_rb": [20]}

    sink = _RecordSink(out_dir / "records.jsonl")
    kept: list[tuple[dict, RunRecord]] = []

    def keeping_sink(rec, axis_values):
        sink(rec, axis_values)
        kept.append((dict(axis_values), rec))

    print(f"stage 1: core plane {core}")
    rows = sweep(
        axes=core, build_scenario=_build, schedulers=_arms(),
        n_seeds=n_seeds, driver_kwargs=_driver_kwargs,
        record_sink=keeping_sink,
    )
    for axis, levels in excursions.items():
        print(f"stage 1: excursion {axis}={levels}")
        rows += sweep(
            axes={axis: levels}, build_scenario=_build, schedulers=_arms(),
            n_seeds=n_seeds, driver_kwargs=_driver_kwargs,
            record_sink=keeping_sink,
        )
    sink.close()

    write_csv(rows, str(out_dir / "stage1_rows.csv"))
    print(f"  {len(rows)} rows, {sink.n} records -> {out_dir}")
    _study_layer_metrics(kept, out_dir)

    # -- the gate, run as committed code, output recorded verbatim ---------
    arm_pairs = [("PF", "Reservation"), ("PF", "TwoTier"), ("Reservation", "TwoTier")]
    verdicts = []
    for axis, levels in {**core, **excursions}.items():
        base_level = BASE.get(axis)
        all_levels = list(levels) + ([base_level] if base_level not in levels else [])
        verdicts.append(wp9_gate.evaluate_axis(rows, axis, all_levels, arm_pairs))
    selection = wp9_gate.select_for_stage_2(verdicts)
    report = wp9_gate.format_verdicts(verdicts, selection)
    (out_dir / "gate_verdict.txt").write_text(report + "\n")
    print("\n" + report)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stage", type=int, default=1, choices=(1, 2))
    p.add_argument("--out", default="sweeps/wp9/stage1")
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--horizon", type=int, default=20_000)
    p.add_argument("--smoke", action="store_true",
                   help="tiny grid, for exercising the machinery only")
    a = p.parse_args()
    if a.stage != 1:
        raise SystemExit("stage 2 is gated on stage 1's verdict -- not runnable yet")
    run_stage_1(Path(a.out), a.seeds, a.horizon, a.smoke)


if __name__ == "__main__":
    main()
