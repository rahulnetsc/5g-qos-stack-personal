"""WP9 §18 commit 5 — does the desync exist at scale, and does the floor fire?

Scores the four expectations pre-registered in `docs/wp9-plan.md` §18.5,
which were written before the mechanism existed:

  1. Does two-tier's UL service-interval floor FIRE under a constructed
     desync -- or does `_ul_has_pending_gbr` block ARMING in exactly the
     fault, because it reads the same per-LCG estimate the floor exists to
     route around (README §7)?
  2. Do arming and firing separate? Stage 3's `gate_passes=73285, fires=9`
     came from a 16-cell smoke grid at horizon 1000 on a run that DIED at
     cell 51/52 and was never confirmed at scale (§18.3). This settles it.
  3. G2's STOP statistic under the fault vs without it.
  4. Desync WIDTH under spec- vs OAI-truncation -- registered as a
     measurement, not a predicted magnitude.

Instrumentation is study-layer only: the floor counters wrap the scheduler
INSTANCE (the `_instrumented_two_tier` pattern from stage 3, so no
scheduler file changes), and desync width is observed by subclassing
`BsrModel` and patching `sim.driver`'s reference to it. Nothing here is
imported by `sim/`.

Usage:
    uv run python scripts/bsr_desync_study.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sim.driver as driver_mod  # noqa: E402
from sim.bsr import BsrModel  # noqa: E402
from sim.config import CarrierConfig, ScenarioConfig, TDDConfig, UEConfig  # noqa: E402
from scheduler import load_two_tier  # noqa: E402
from scheduler.flow import FlowConfig  # noqa: E402

_TT_CONFIG = str(Path(__file__).resolve().parent.parent
                 / "scheduler" / "scheduler_config.yaml")

MODES = ("off", "oai", "spec")


class _ObservingBsr(BsrModel):
    """Counts, per slot, LCG-slots holding `estimate == 0 while backlog > 0`.

    That is commit 0b's discriminating state (§8a). Observed in
    `broadcast()`, which the driver calls once per slot for every UE, so
    the count is a WIDTH in LCG-slots rather than a count of events.
    """

    stats: dict = {}

    def _select_format(self, active_lcgs, tb_size, filled_bytes):
        fmt = super()._select_format(active_lcgs, tb_size, filled_bytes)
        key = f"fmt_{fmt}"
        self.stats[key] = self.stats.get(key, 0) + 1
        pad = max(0, int(tb_size) - int(filled_bytes or 0))
        self.stats.setdefault("pad_hist", {})
        self.stats["pad_hist"][min(pad, 9)] = \
            self.stats["pad_hist"].get(min(pad, 9), 0) + 1
        return fmt

    def broadcast(self, buffers, ul_access):
        super().broadcast(buffers, ul_access)
        for ue_id, st in self._state.items():
            per_lcg_true: dict[int, int] = {}
            for f in self._ue_flows[ue_id]:
                per_lcg_true[f.lcg] = per_lcg_true.get(f.lcg, 0) + \
                    buffers.state(f.ue_id, f.qfi).bytes_queued
            for lcg, backlog in per_lcg_true.items():
                if backlog > 0 and st.estimated_ul_buffer_per_lcg[lcg] == 0:
                    self.stats["desync_lcg_slots"] = \
                        self.stats.get("desync_lcg_slots", 0) + 1
                    self.stats.setdefault("desync_ues", set()).add(ue_id)


def _scenario(seed: int = 7, n_ues: int = 6, horizon: int = 8000):
    """A UE with several UL LCGs, GBR + mfbr so the floor can ARM.

    `mfbr_bps > 0` is the floor's other dormancy half (README §7): without
    it the floor never arms regardless of any fault, so a desync alone
    would prove nothing.
    """
    flows: list[FlowConfig] = []
    for ue in range(1, n_ues + 1):
        flows += [
            # GBR UL on its own LCG -- the flow the floor protects.
            FlowConfig(ue_id=ue, qfi=2, direction="UL", flow_class="GBR",
                       gfbr_bps=4_000_000.0, mfbr_bps=8_000_000.0,
                       pdb_ms=150.0, traffic_kind="xr_video",
                       traffic_params={"period_ms": 33.0, "avg_bytes": 16_000,
                                       "fragment_bytes": 1500}),
            # Tight-PDB control traffic, a different LCG.
            FlowConfig(ue_id=ue, qfi=83, direction="UL", flow_class="Delay",
                       gfbr_bps=0.0, pdb_ms=20.0,
                       traffic_kind="periodic_control",
                       traffic_params={"period_ms": 20.0,
                                       "bytes_per_period": 200}),
            # Bulk best-effort, a third LCG -- keeps several LCGs active so
            # the truncated formats have something to omit.
            FlowConfig(ue_id=ue, qfi=9, direction="UL", flow_class="PF",
                       gfbr_bps=0.0, pdb_ms=300.0, traffic_kind="poisson",
                       traffic_params={"rate_bps": 2_000_000.0}),
        ]
    ues = [UEConfig(ue_id=i + 1, mean_snr_db=12.0, coherence_slots=2000)
           for i in range(n_ues)]
    return ScenarioConfig(
        name=f"bsr_desync_n{n_ues}", horizon_slots=horizon,
        carrier=CarrierConfig(bandwidth_hz=20_000_000, numerology=1),
        tdd=TDDConfig(pattern="DSUUU"), ues=ues, flows=flows, seed=seed,
    )


def _instrumented(tally: dict):
    """Stage 3's pattern: wrap the INSTANCE so no scheduler file changes.

    `_ul_has_pending_gbr` is the ARMING gate; `_update_ul_floor` returns
    (fired, silence). Counting them separately is the only way "no fires"
    can distinguish *never armed* from *armed but never fired*.
    """
    sched = load_two_tier(_TT_CONFIG, min_rb=5)
    real_gate = sched._ul_has_pending_gbr
    real_floor = sched._update_ul_floor

    def gate(ue_id, buffers):
        ok = real_gate(ue_id, buffers)
        tally["gate_calls"] = tally.get("gate_calls", 0) + 1
        if ok:
            tally["gate_passes"] = tally.get("gate_passes", 0) + 1
        return ok

    def floor(ue_id, buffers, slot_index, *a, **k):
        fired, sil = real_floor(ue_id, buffers, slot_index, *a, **k)
        if fired:
            tally["fires"] = tally.get("fires", 0) + 1
        return fired, sil

    sched._ul_has_pending_gbr = gate
    sched._update_ul_floor = floor
    return sched


def run_mode(mode: str, seed: int = 7) -> dict:
    tally: dict = {}
    _ObservingBsr.stats = {}
    orig = driver_mod.BsrModel
    driver_mod.BsrModel = _ObservingBsr
    try:
        summary = driver_mod.run(
            _scenario(seed=seed), _instrumented(tally),
            cqi_delay_slots=8, truncated_bsr=mode,
        )
    finally:
        driver_mod.BsrModel = orig

    ul = [v for k, v in summary["flows"].items()
          if v.get("direction") == "UL"] or list(summary["flows"].values())
    delivered = sum(v.get("bytes_delivered", 0) for v in summary["flows"].values())
    dropped = sum(v.get("bytes_dropped_pdb", 0) for v in summary["flows"].values())
    late = sum(v.get("bytes_delivered_late_pdb", 0) for v in summary["flows"].values())
    resolved = delivered + dropped
    worst_p99 = max((v.get("delay_p99_ms") or 0.0) for v in ul) if ul else 0.0
    return {
        "mode": mode,
        "desync_lcg_slots": _ObservingBsr.stats.get("desync_lcg_slots", 0),
        "desync_ues": len(_ObservingBsr.stats.get("desync_ues", set())),
        "gate_calls": tally.get("gate_calls", 0),
        "gate_passes": tally.get("gate_passes", 0),
        "fires": tally.get("fires", 0),
        "pdb_violation_rate": ((dropped + late) / resolved) if resolved else 0.0,
        "worst_ul_p99_ms": worst_p99,
        "delivered_bytes": delivered,
        "fmts": {k: v for k, v in _ObservingBsr.stats.items()
                 if k.startswith("fmt_")},
        "pad_hist": dict(sorted(_ObservingBsr.stats.get("pad_hist", {}).items())),
    }


def main() -> int:
    seeds = (7, 11, 23)
    print("WP9 §18.5 — pre-registered expectations, scored")
    print("=" * 78)
    rows = {m: [run_mode(m, s) for s in seeds] for m in MODES}

    def avg(m, k):
        return sum(r[k] for r in rows[m]) / len(rows[m])

    print(f"{'mode':<6}{'desync LCG-slots':>18}{'UEs':>5}{'gate_passes':>13}"
          f"{'fires':>8}{'M02-ish':>10}{'worst p99':>11}")
    for m in MODES:
        print(f"{m:<6}{avg(m,'desync_lcg_slots'):>18.0f}"
              f"{avg(m,'desync_ues'):>5.0f}{avg(m,'gate_passes'):>13.0f}"
              f"{avg(m,'fires'):>8.0f}{avg(m,'pdb_violation_rate'):>10.4f}"
              f"{avg(m,'worst_ul_p99_ms'):>11.1f}")

    print()
    print("E4 (desync WIDTH, measured not predicted):")
    for m in MODES:
        print(f"    {m:<5} {avg(m,'desync_lcg_slots'):>10.0f} LCG-slots")
    print()
    print("Which formats were actually SELECTED (padding BSRs only):")
    for m in MODES:
        print(f"    {m:<5} {rows[m][0]['fmts']}")
    print("Padding-length histogram (0..8, 9=9+), first seed:")
    for m in MODES:
        print(f"    {m:<5} {rows[m][0]['pad_hist']}")
    print()
    print("E1/E2 (does the floor fire; do arming and firing separate):")
    for m in MODES:
        gp, fr = avg(m, "gate_passes"), avg(m, "fires")
        if gp == 0:
            verdict = "NEVER ARMED — mfbr/gate half unsatisfied"
        elif fr == 0:
            verdict = "ARMED, NEVER FIRED — the two halves separate"
        else:
            verdict = "ARMED AND FIRED"
        print(f"    {m:<5} gate_passes={gp:>10.0f} fires={fr:>7.0f}  {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
