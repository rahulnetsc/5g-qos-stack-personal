"""WP9 §20 — the counterfactual probe that corrected §19.5's diagnosis.

§19.5 concluded that truncated BSR cannot fire because this model sizes
transport blocks continuously, and named TB-size quantisation in the
grant-sizing path as "what would close it". This script is the cheap
discriminator that tested that BEFORE any of it was built, and it says the
diagnosis is wrong: quantising the TB changes the padding distribution by
nothing at all at the load the claim was measured at, and the count of
lawful Truncated BSRs goes DOWN (5 -> 4) at light load. See
`docs/wp9-plan.md` §20.0-§20.2.

WHAT THIS IS. A read-only instrument, not a model. It replays every uplink
grant of a real run and asks what padding that grant WOULD have had if
`tbs_bytes` had come from OAI's `nr_find_nb_rb`/`nr_compute_tbs` instead of
`min(ue_backlog, prbs * bits_per_rb // 8)`. Nothing here is imported by
`sim/` or `scheduler/`; the TBS port below is this script's own, and is
deliberately NOT the home a real port would use (that is `scheduler/tbs.py`
-- `sim/resource.py` cannot be, see §20.5).

It is landed rather than left in a scratchpad because a committed document
now carries its numbers, and a count in prose is a claim about code that
drifts silently (CLAUDE.md). Re-run it to re-derive every figure in §20.0.

PROVENANCE, mixed and marked per source (§20.4):
  * `nr_find_nb_rb`  -- oai-branches/reservation/gNB_scheduler_primitives.c
                        :655-712.  VENDORED, checkable in-repo.
  * `nr_compute_tbs`, `Tbstable_nr` (TS 38.214 Table 5.1.3.2-2, 93 entries),
    `NR_MAX_PDSCH_TBS`, `CEILIDIV`/`ROUNDIDIV`
                     -- openair2/LAYER2/NR_MAC_COMMON/nr_compute_tbs_common.c
                        :32-105 and common/utils/nr/nr_common.h:42,347-348.
                        FULL CHECKOUT ONLY -- not in oai-branches/.

Usage:
    uv run python scripts/tbs_counterfactual.py            # §20.0's tables
    uv run python scripts/tbs_counterfactual.py --sizing   # §20.3's deltas
"""

from __future__ import annotations

import argparse
import collections
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scheduler.link import bits_per_prb  # noqa: E402
from sim.driver import run  # noqa: E402
from sim.ue_lcp import UeLcp  # noqa: E402

import bsr_desync_study as bds  # noqa: E402
import scheduler_study as ss  # noqa: E402

# --------------------------------------------------------------------------
# The TBS port. Byte-for-byte from the C cited above.
# --------------------------------------------------------------------------

# nr_compute_tbs_common.c:32-42 -- TS 38.214 Table 5.1.3.2-2.
TBSTABLE_NR = [
    24, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128, 136, 144,
    152, 160, 168, 176, 184, 192, 208, 224, 240, 256, 272, 288, 304, 320,
    336, 352, 368, 384, 408, 432, 456, 480, 504, 528, 552, 576, 608, 640,
    672, 704, 736, 768, 808, 848, 888, 928, 984, 1032, 1064, 1128, 1160,
    1192, 1224, 1256, 1288, 1320, 1352, 1416, 1480, 1544, 1608, 1672, 1736,
    1800, 1864, 1928, 2024, 2088, 2152, 2216, 2280, 2408, 2472, 2536, 2600,
    2664, 2728, 2792, 2856, 2976, 3104, 3240, 3368, 3496, 3624, 3752, 3824,
]

NR_MAX_PDSCH_TBS = 3824  # common/utils/nr/nr_common.h:42


def _ceilidiv(a: int, b: int) -> int:      # nr_common.h:347
    return (a + b - 1) // b


def _roundidiv(a: int, b: int) -> int:     # nr_common.h:348
    return ((a << 1) + b) // (b << 1)


def nr_compute_tbs(Qm: int, R: int, nb_rb: int, nb_symb_sch: int,
                   nb_dmrs_prb: int = 0, nb_rb_oh: int = 0,
                   tb_scaling: int = 0, Nl: int = 1) -> int:
    """TBS in BITS. nr_compute_tbs_common.c:44-105.

    Two places where the C is mirrored rather than 38.214's prose: `n` is a
    `uint32_t` truncation of a double, and `Np_info` is a shift pair, not a
    round. `min(156, ...)` is 38.214's RE cap -- note it never binds at this
    repo's `overhead_factor=0.85` (a full slot is 11 symbols, 12*11=132).
    """
    if Qm == 0 or R == 0 or nb_rb == 0 or Nl == 0:
        return 0
    nbp_re = 12 * nb_symb_sch - nb_dmrs_prb - nb_rb_oh
    nb_re = min(156, nbp_re) * nb_rb
    R_5 = R // 5           # R is tabulated as 10x the spec's Rx1024
    Ninfo = ((nb_re * R_5 * Qm * Nl) >> 11) >> tb_scaling
    if Ninfo <= 0:
        return 0
    if Ninfo <= NR_MAX_PDSCH_TBS:
        n = max(3, int(math.floor(math.log2(Ninfo))) - 6)
        Np_info = max(24, (Ninfo >> n) << n)
        for entry in TBSTABLE_NR:
            if entry >= Np_info:
                return entry
        return 0
    n = int(math.log2(Ninfo - 24) - 5)
    Np_info = max(3840, _roundidiv(Ninfo - 24, 1 << n) << n)
    if R <= 2560:
        C = _ceilidiv(Np_info + 24, 3816)
        return (C << 3) * _ceilidiv(Np_info + 24, C << 3) - 24
    if Np_info > 8424:
        C = _ceilidiv(Np_info + 24, 8424)
        return (C << 3) * _ceilidiv(Np_info + 24, C << 3) - 24
    return (_ceilidiv(Np_info + 24, 8) << 3) - 24


def tbs_bytes(Qm: int, R: int, nb_rb: int, nb_symb_sch: int) -> int:
    return nr_compute_tbs(Qm, R, nb_rb, nb_symb_sch) >> 3


def nr_find_nb_rb(Qm: int, R: int, nb_symb_sch: int, want_bytes: int,
                  nb_rb_min: int, nb_rb_max: int) -> tuple[bool, int, int]:
    """Smallest nb_rb whose TBS covers ``want_bytes``. Returns
    ``(fits, nb_rb, tbs_bytes)``. gNB_scheduler_primitives.c:655-712, with
    transform precoding disabled (the multiple_2_3_5 loop is a no-op then).

    Note the returned TBS is NOT capped at ``want_bytes`` -- that is exactly
    the difference from this repo's `min(ue_backlog, ...)`.
    """
    nb_rb = nb_rb_max
    tbs = tbs_bytes(Qm, R, nb_rb, nb_symb_sch)
    if want_bytes > tbs:
        return False, nb_rb, tbs
    if want_bytes == tbs:
        return True, nb_rb, tbs
    nb_rb = nb_rb_min
    tbs = tbs_bytes(Qm, R, nb_rb, nb_symb_sch) if nb_rb > 0 else 0
    if nb_rb > 0 and want_bytes <= tbs:
        return True, nb_rb, tbs
    hi, lo = nb_rb_max, max(1, nb_rb_min)
    while lo + 1 < hi:
        p = (hi + lo) // 2
        t = tbs_bytes(Qm, R, p, nb_symb_sch)
        if want_bytes == t:
            hi = p
            break
        elif want_bytes < t:
            hi = p
        else:
            lo = p
    nb_rb = hi
    tbs = tbs_bytes(Qm, R, nb_rb, nb_symb_sch)
    return (tbs >= want_bytes and nb_rb <= nb_rb_max), nb_rb, tbs


def se_to_qm_r(se: float) -> tuple[int, int]:
    """`scheduler/link.py::_MCS_TABLE` carries spectral efficiency only;
    `nr_compute_tbs` needs (Qm, R). Qm from TS 38.214 Table 5.1.3.1-1's own
    modulation boundaries, R back-solved so SE is preserved EXACTLY
    (SE == Qm*R/10240) -- the probe must not smuggle in a link-adaptation
    change while measuring a quantisation one. See §20.6 D1, including the
    two extreme staircase rows whose back-solved code rate falls outside
    any real MCS table's range.
    """
    if se < 1.4766:
        qm = 2
    elif se < 2.7305:
        qm = 4
    elif se < 5.5547:
        qm = 6
    else:
        qm = 8
    return qm, int(round(se * 10240.0 / qm))


# --------------------------------------------------------------------------
# Capture: every UL grant of a real run.
# --------------------------------------------------------------------------

_GRANTS: list[dict] = []
_last_ul: dict[int, tuple] = {}
_orig_fill = UeLcp.fill


def _instrument(sched):
    """Wrap the scheduler INSTANCE (stage 3's pattern) so no scheduler file
    changes -- the UL Allocation is where `prbs`/`snr_used_db` live."""
    orig = sched.allocate

    def allocate(slot, buffers, channel):
        out = orig(slot, buffers, channel)
        _last_ul.clear()
        for a in out:
            if getattr(a, "ue_grant", False):
                _last_ul[a.ue_id] = (a.prbs, a.snr_used_db, slot.ul_symbols)
        return out

    sched.allocate = allocate
    return sched


def _patched_fill(self, ue_flows, tbs_bytes_, buffers):
    """`UeLcp.fill` is the one place that sees the TB size, what the UE
    actually put in it, and the true per-flow backlog, all at once."""
    res = _orig_fill(self, ue_flows, tbs_bytes_, buffers)
    if ue_flows and (meta := _last_ul.get(ue_flows[0].ue_id)) is not None:
        prbs, snr, symbols = meta
        _GRANTS.append({
            "prbs": prbs, "snr": snr, "symbols": symbols,
            "tbs_today": tbs_bytes_, "filled": sum(b for _, b in res),
            "true": sum(buffers.state(f.ue_id, f.qfi).bytes_queued
                        for f in ue_flows),
            "reported": sum(buffers.state(f.ue_id, f.qfi).bytes_reported
                            for f in ue_flows),
            "n_lcg": len({f.lcg for f in ue_flows
                          if buffers.state(f.ue_id, f.qfi).bytes_queued > 0}),
        })
    return res


def _lawful_truncated(padding: int, n_lcg: int) -> bool:
    """TS 38.321 §5.4.5 Padding BSR: a truncated format is selected only
    when padding >= the Short BSR size AND more than one LCG has data AND a
    full Long BSR does NOT fit (`padding < n_lcg + 3`)."""
    return padding >= 2 and n_lcg >= 2 and padding < n_lcg + 3


def _analyse(label: str, min_rb: int) -> None:
    n = len(_GRANTS)
    print(f"\n--- {label}  UL grants={n}")
    if not n:
        return
    pad_today = collections.Counter()
    pad_cf = collections.Counter()
    win_today = win_cf = trunc_today = trunc_cf = multi_lcg = 0
    errs: list[int] = []
    # |BSR error| restricted to the grants that pass the >=2-LCG half of the
    # truncation conjunction -- §20.1's headline number. Kept separate from
    # `errs` on purpose: the signed median over ALL grants mixes the
    # over-reporting and under-reporting regimes and cancels.
    errs_multi: list[int] = []
    for g in _GRANTS:
        bits_rb, _ = bits_per_prb(g["snr"], symbols=g["symbols"])
        if bits_rb <= 0:
            continue
        qm, R = se_to_qm_r(bits_rb / (12.0 * g["symbols"]))
        p_today = g["tbs_today"] - g["filled"]
        _fits, _nb, tq = nr_find_nb_rb(qm, R, g["symbols"],
                                       max(1, g["reported"]), min_rb,
                                       max(min_rb, g["prbs"]))
        p_cf = max(0, tq - min(g["true"], tq))
        pad_today[min(p_today, 9)] += 1
        pad_cf[min(p_cf, 9)] += 1
        errs.append(g["reported"] - g["true"])
        if g["n_lcg"] >= 2:
            multi_lcg += 1
            errs_multi.append(abs(g["reported"] - g["true"]))
        win_today += 2 <= p_today <= 5
        win_cf += 2 <= p_cf <= 5
        trunc_today += _lawful_truncated(p_today, g["n_lcg"])
        trunc_cf += _lawful_truncated(p_cf, g["n_lcg"])
    pct = lambda c: f"{c:6d} ({100.0 * c / n:5.2f}%)"  # noqa: E731
    print(f"    LCGs with data at grant : "
          f"{dict(sorted(collections.Counter(g['n_lcg'] for g in _GRANTS).items()))}")
    print(f"    padding hist today (9='>=9'): {dict(sorted(pad_today.items()))}")
    print(f"    padding hist  CF   (9='>=9'): {dict(sorted(pad_cf.items()))}")
    print(f"    padding == 0            : today {pct(pad_today[0])}  CF {pct(pad_cf[0])}")
    print(f"    padding in 2..5         : today {pct(win_today)}  CF {pct(win_cf)}")
    print(f"    >=2 LCGs with data      : {pct(multi_lcg)}")
    print(f"    LAWFUL TRUNCATED BSR    : today {trunc_today}   ->   CF {trunc_cf}")
    print(f"    BSR error (reported-true): median {statistics.median(errs):.0f}  "
          f"p10 {statistics.quantiles(errs, n=10)[0]:.0f}  "
          f"p90 {statistics.quantiles(errs, n=10)[-1]:.0f}")
    if errs_multi:
        print(f"    |BSR error| on >=2-LCG grants: median "
              f"{statistics.median(errs_multi):.0f}"
              + (f"  p90 {statistics.quantiles(errs_multi, n=10)[-1]:.0f}"
                 if len(errs_multi) > 9 else "")
              + "   <-- the window truncation needs is 2..5 BYTES")


def _scaled_desync(load: float, horizon: int = 4000):
    """`bsr_desync_study._scenario` with its offered load scaled -- the
    multi-LCG scenario §19.5's 28,580/28,580 came from."""
    sc = bds._scenario(seed=7, n_ues=6, horizon=horizon)
    for f in sc.flows:
        params = dict(f.traffic_params or {})
        for key in ("rate_bps", "avg_bytes", "bytes_per_period"):
            if key in params:
                params[key] = type(params[key])(params[key] * load)
        f.traffic_params = params
    sc.name = f"{sc.name}_load{load}"
    return sc


def run_counterfactual() -> None:
    """§20.0's two tables."""
    from scheduler import load_two_tier

    UeLcp.fill = _patched_fill
    print("== the desync scenario across offered load (6 UEs x 3 UL LCGs) ==")
    for load in (1.0, 0.3, 0.1, 0.03):
        _GRANTS.clear()
        sched = _instrument(load_two_tier(bds._TT_CONFIG))
        run(_scaled_desync(load), sched, cqi_delay_slots=ss.CQI_DELAY_SLOTS)
        _analyse(f"bsr_desync @ offered-load x{load}", getattr(sched, "min_rb", 5))

    print("\n== the corpus scenarios ==")
    cases = {
        "factory_robots x1.0 / TwoTier":
            (lambda: ss._scale_capacity(ss.factory_robots_scenario(), 1.0), ss._tt),
        "factory_robots x3.0 / TwoTier":
            (lambda: ss._scale_capacity(ss.factory_robots_scenario(), 3.0), ss._tt),
        "sensor_dense / TwoTier": (ss.sensor_dense_scenario, ss._tt),
        "factory_robots x1.0 / Reservation":
            (lambda: ss._scale_capacity(ss.factory_robots_scenario(), 1.0), ss._reservation),
    }
    for label, (make_sc, make_sched) in cases.items():
        _GRANTS.clear()
        sched = _instrument(make_sched())
        run(make_sc(), sched, cqi_delay_slots=ss.CQI_DELAY_SLOTS)
        _analyse(label, getattr(sched, "min_rb", 5))


def run_sizing_deltas() -> None:
    """§20.3's sizing-rule comparison. Pure arithmetic on the two rules --
    no simulation, so this is the cheap half to re-derive."""
    print("== sizing rule: nr_find_nb_rb vs this repo's ceil-div, want=1..4000 ==")
    for snr, symbols, label in ((20.0, 11, "20 dB / U-slot 11 sym"),
                                (12.0, 11, "12 dB / U-slot 11 sym"),
                                (20.0, 7, "20 dB / S-slot 7 sym")):
        bits_rb, _ = bits_per_prb(snr, symbols=symbols)
        qm, R = se_to_qm_r(bits_rb / (12.0 * symbols))
        delta = collections.Counter()
        for want in range(1, 4001):
            prbs_sim = min(55, max(1, -(-(want * 8) // bits_rb)))
            _fits, nb, _tq = nr_find_nb_rb(qm, R, symbols, want, 5, 55)
            delta[nb - prbs_sim] += 1
        same = delta[0]
        print(f"  {label}: bits/PRB={bits_rb} Qm={qm} R={R}")
        print(f"    identical PRB count on {same}/4000 ({100.0 * same / 4000:.1f}%); "
              f"deltas {dict(sorted(delta.items()))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizing", action="store_true",
                    help="only the §20.3 sizing-rule deltas (no simulation)")
    args = ap.parse_args()
    if args.sizing:
        run_sizing_deltas()
    else:
        run_counterfactual()
        print()
        run_sizing_deltas()
