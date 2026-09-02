"""Fleet compositions for WP9's re-scoped sweep (`docs/wp9-plan.md` §5).

**Why this is a new module rather than an edit to `sim/parametric.py`.**
The re-scope is a deliberate CLEAN BREAK from stage 2's workload (plan §6,
decision 2): stage 2 ran three identical flows per UE with load carried by
a synthetic Poisson best-effort filler. That filler is exactly what made
the workload unrealistic. Leaving `sim/parametric.py` untouched keeps
stage 1 and stage 2 reproducible, so their results stay valid *for their
own workload* rather than being silently superseded.

**What the map is indexed by.** Category 2 only -- what the environment
does, not what the deployment fixes (plan §1). Fleet *composition* is a
primary axis alongside size, because "N=16" is not an index in a
heterogeneous deployment: 16 fixed sensors and 16 UGVs differ by an order
of magnitude in flow count, GBR fraction, burst structure, UL/DL split and
LCG occupancy. Flows-per-UE, shared-LCG occurrence, GBR ratio, PDB spread
and UL/DL asymmetry are all CONSEQUENCES of composition here, not
independent knobs.

**Provenance discipline.** Every flow states (5QI, GFBR, PDB, priority,
LCG) and every field is marked:

  - **standardised** -- from a 3GPP table. PDB via
    `scheduler.flow.pdb_for_5qi` (TS 23.501 Table 5.7.4-1); priority via
    `FIVE_QI_PRIORITY`. Neither is authored here.
  - **negotiated** -- GFBR, a per-bearer value an operator provisions. It
    is NOT a 5QI property, so it is authored, and said so explicitly.
  - **simulator default** -- LCG, via `FIVE_QI_LCG`, which that table's own
    comment already flags as invented and non-standardised.
  - **operational** -- rates, periods and duty cycles from device
    datasheets or factory workflow, cited per profile below.

`profile_qos_table()` emits exactly this, and the regime map reports it
alongside results: "the arms diverge at N=8" is uninterpretable without
knowing what was guaranteed to whom, and the hardware campaign configures
real bearers from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from scheduler.flow import (
    DERIVE_PDB_FROM_5QI,
    FlowConfig,
    lcg_for_5qi,
    pdb_for_5qi,
    priority_for_5qi,
)

__all__ = [
    "DeviceProfile", "PROFILES", "COMPOSITIONS", "LIDAR",
    "build_fleet", "profile_qos_table",
]

# --- lidar, the one flow whose shape is a modelling decision -------------
#
# Ouster OS1/OS2 datasheets: 66-255 Mbps (Legacy profile), 11.8-43 Mbps
# (Low Data Rate Profile). Velodyne VLP-16: ~600k points/s ~= 19 Mbps at
# 4 B/point. Against this cell's ~100 Mbps a single raw stream consumes the
# carrier.
#
# **Lidar is DUTY-CYCLED, not continuous.** In a factory an operator
# enables it per task -- docking, tight-tolerance traverse, mapping -- so it
# is an event. Modelling it as a permanently-downscaled continuous feed
# would misrepresent a large transient as a small steady demand, which is
# the precise behaviour the excursion exists to stress.
LIDAR_ACTIVE_BPS = 12_000_000.0      # operational: LDRP-class active rate
LIDAR_LEGACY_BPS = 66_000_000.0      # operational: Legacy, misconfiguration case
# CONCURRENCY IS A BOUND, NOT AN AXIS. Factory tasks are serialised by the
# floor's operation: you do not get eight UGVs docking simultaneously. This
# is a modelling assumption with that justification -- deliberately NOT a
# parameter to sweep as a LOAD SCALE, which is what "more concurrent lidars
# = more offered load" would be.
#
# WP9 stage 5 varies n_ues over {0, 1, 2} anyway, and that is not a
# violation of the above: 1-vs-2 are THE TWO ENDPOINTS OF THIS BOUND -- one
# robot docking versus two, the most the floor's own serialisation allows --
# not a scale extended past it. The clamp below is what makes the
# distinction enforceable rather than a matter of intent, and
# test_lidar_concurrency_is_capped_as_a_bound pins it (docs/wp9-plan.md
# §16.3).
LIDAR_MAX_CONCURRENT = 2


@dataclass(frozen=True)
class LidarActivation:
    """One lidar activation window. See `docs/wp9-plan.md` §5."""
    n_ues: int = 1                    # capped at LIDAR_MAX_CONCURRENT
    start_s: float = 1.5
    duration_s: float = 2.0
    rate_bps: float = LIDAR_ACTIVE_BPS
    synchronised: bool = False        # both UEs at once = herd on a LARGE flow
    # Offset between successive activations when not synchronised. A FIELD
    # rather than the literal it used to be inside build_fleet, because
    # stage 5's scoring windows are derived from this dataclass and nothing
    # else (docs/wp9-plan.md §16.4, "never hardcoded") -- `during_2` is
    # [start_s, start_s + stagger_s + duration_s), which is underivable if
    # the stagger lives only at the point of use. Same value, same
    # behaviour; it just became reachable.
    stagger_s: float = 0.5


LIDAR = LidarActivation


@dataclass(frozen=True)
class _Flow:
    """One flow of a device profile, with its provenance."""
    qfi: int
    direction: Literal["UL", "DL"]
    flow_class: Literal["PF", "GBR", "Delay"]
    gfbr_bps: float                   # NEGOTIATED (0 = non-GBR)
    kind: str
    params: dict
    note: str


@dataclass(frozen=True)
class DeviceProfile:
    name: str
    flows: tuple[_Flow, ...]
    source: str

    def n_flows(self) -> int:
        return len(self.flows)


# --- the five profiles ---------------------------------------------------
# Flow counts stay within the OAI implementation's 7-flow per-UE ceiling.

DRONE = DeviceProfile(
    name="drone",
    source="MAVLink telemetry cadence; H.264 GOP structure; 5QI per role",
    flows=(
        _Flow(1, "UL", "Delay", 0.0, "periodic_control",
              {"period_ms": 100.0, "bytes_per_period": 280},
              "MAVLink telemetry 10 Hz"),
        _Flow(82, "DL", "Delay", 0.0, "periodic_control",
              {"period_ms": 50.0, "bytes_per_period": 120},
              "flight control 20 Hz, delay-critical"),
        _Flow(2, "UL", "GBR", 4_000_000.0, "xr_video",
              {"period_ms": 33.0, "avg_bytes": 16_000, "fragment_bytes": 1500},
              # OFFERED IS BELOW GFBR, deliberately recorded rather than
              # fixed: 16_000 B / 33.0 ms = 3.879 Mbps against a 4.000 Mbps
              # GFBR, so gfbr_fraction has an arithmetic ceiling of ~0.970
              # and this flow starts any load ramp ~0.007 above the 0.95
              # contract line. The 5QI-4 lidar is provisioned offered =
              # guarantee and starts ~0.05 above it, so "camera degrades
              # first" is partly provisioning, not scheduling
              # (docs/wp9-plan.md §36.3). Changing avg_bytes would move the
              # regression corpus and every G10/G12 number -- its own commit.
              "H.264 720p30 with GOP bursts -- offered 3.879 Mbps vs GFBR 4.000, ratio 0.9697"),
        _Flow(9, "UL", "PF", 0.0, "periodic_control",
              {"period_ms": 1000.0, "bytes_per_period": 64},
              "1 Hz heartbeat"),
    ),
)

UGV = DeviceProfile(
    name="ugv",
    source="Ouster/Velodyne datasheets (lidar); e-stop from safety practice",
    flows=(
        _Flow(4, "UL", "GBR", LIDAR_ACTIVE_BPS, "deterministic",
              {"period_ms": 100.0, "bytes_per_period": 150_000},
              "LIDAR -- duty-cycled, gated by LidarActivation"),
        _Flow(2, "UL", "GBR", 4_000_000.0, "xr_video",
              {"period_ms": 33.0, "avg_bytes": 16_000, "fragment_bytes": 1500},
              # Same under-provisioning as DRONE's camera above; see that
              # comment. docs/wp9-plan.md §36.3.
              "forward camera -- offered 3.879 Mbps vs GFBR 4.000, ratio 0.9697"),
        _Flow(83, "UL", "Delay", 0.0, "periodic_control",
              {"period_ms": 20.0, "bytes_per_period": 200},
              "odometry 50 Hz"),
        _Flow(82, "DL", "Delay", 0.0, "periodic_control",
              {"period_ms": 50.0, "bytes_per_period": 120},
              "drive control 20 Hz"),
        _Flow(85, "DL", "Delay", 0.0, "aperiodic_event",
              {"rate_hz": 0.2, "burst_bytes": 40},
              "E-STOP -- tiniest payload, tightest PDB in the panel (5 ms)"),
        _Flow(9, "UL", "PF", 0.0, "poisson",
              {"rate_bps": 500_000.0},
              "logs, non-GBR"),
    ),
)

CAMERA = DeviceProfile(
    name="camera",
    source="fixed-installation IP camera; 5QI 2 conversational video",
    flows=(
        _Flow(2, "UL", "GBR", 6_000_000.0, "xr_video",
              {"period_ms": 33.0, "avg_bytes": 25_000, "fragment_bytes": 1500},
              # Provisioned the OTHER way -- 25_000 B / 33.0 ms = 6.061 Mbps
              # against a 6.000 GFBR, ratio 1.0101. Recorded because it is
              # why exactly 4 of the 5 5QI-2 flows in the mixed/N=8 cell are
              # under-provisioned and one is not (docs/wp9-plan.md §36.3).
              "continuous 1080p30 -- offered 6.061 Mbps vs GFBR 6.000, ratio 1.0101"),
        _Flow(82, "DL", "Delay", 0.0, "periodic_control",
              {"period_ms": 1000.0, "bytes_per_period": 64},
              "PTZ / config"),
    ),
)

SENSOR = DeviceProfile(
    name="sensor",
    source="industrial periodic measurement; 5QI 82 discrete automation",
    flows=(
        _Flow(82, "UL", "Delay", 0.0, "periodic_control",
              {"period_ms": 100.0, "bytes_per_period": 48},
              "measurement 10 Hz, tiny"),
        _Flow(9, "DL", "PF", 0.0, "poisson",
              {"rate_bps": 2_000.0},
              "occasional config"),
    ),
)

ACTUATOR = DeviceProfile(
    name="actuator",
    source="PLC-driven actuator; 5QI 82/83 discrete automation",
    flows=(
        _Flow(82, "DL", "Delay", 0.0, "periodic_control",
              {"period_ms": 20.0, "bytes_per_period": 64},
              "command 50 Hz, tight PDB"),
        _Flow(83, "UL", "Delay", 0.0, "periodic_control",
              {"period_ms": 20.0, "bytes_per_period": 32},
              "status ack 50 Hz"),
    ),
)

PROFILES = {p.name: p for p in (DRONE, UGV, CAMERA, SENSOR, ACTUATOR)}

# Compositions as proportions; build_fleet allocates N across them.
COMPOSITIONS: dict[str, dict[str, float]] = {
    "drone_heavy":  {"drone": 0.60, "ugv": 0.10, "camera": 0.10,
                     "sensor": 0.15, "actuator": 0.05},
    "ugv_heavy":    {"ugv": 0.55, "drone": 0.10, "camera": 0.10,
                     "sensor": 0.15, "actuator": 0.10},
    "sensor_dense": {"sensor": 0.65, "actuator": 0.20, "camera": 0.10,
                     "ugv": 0.03, "drone": 0.02},
    "mixed":        {"drone": 0.20, "ugv": 0.20, "camera": 0.20,
                     "sensor": 0.25, "actuator": 0.15},
}


def _allocate(n_ues: int, comp: dict[str, float]) -> list[str]:
    """Largest-remainder allocation, so the mix is exact at every N rather
    than drifting with rounding -- N is an axis, and a composition that
    silently changes shape across N would confound it."""
    raw = {k: n_ues * w for k, w in comp.items()}
    out = {k: int(v) for k, v in raw.items()}
    rem = n_ues - sum(out.values())
    for k, _ in sorted(raw.items(), key=lambda kv: -(kv[1] - int(kv[1]))):
        if rem <= 0:
            break
        out[k] += 1
        rem -= 1
    seq: list[str] = []
    for k in ("ugv", "drone", "camera", "sensor", "actuator"):
        seq.extend([k] * out.get(k, 0))
    return seq


def build_fleet(
    n_ues: int,
    composition: str,
    lidar: Optional[LidarActivation] = None,
    video_tier: float = 1.0,
) -> tuple[list[FlowConfig], list[str]]:
    """Flows for a fleet of `n_ues` in `composition`.

    `video_tier` scales video bitrate within a realistic device range --
    load intensity comes from per-device rates, NOT from a synthetic
    best-effort filler (plan §6, decision 2).

    Lidar flows are DISABLED unless `lidar` is given: the UGV profile
    carries the flow so its LCG/QoS shape is right, but a duty-cycled
    sensor is off by default. When given, at most
    LIDAR_MAX_CONCURRENT UEs are activated -- a bound, not an axis.
    """
    if composition not in COMPOSITIONS:
        raise ValueError(f"unknown composition {composition!r}")
    seq = _allocate(n_ues, COMPOSITIONS[composition])
    ugv_ids = [i + 1 for i, p in enumerate(seq) if p == "ugv"]
    n_active = min(lidar.n_ues, LIDAR_MAX_CONCURRENT, len(ugv_ids)) if lidar else 0
    active_ids = set(ugv_ids[:n_active])

    flows: list[FlowConfig] = []
    for idx, pname in enumerate(seq):
        ue_id = idx + 1
        for f in PROFILES[pname].flows:
            params = dict(f.params)
            is_lidar = pname == "ugv" and "LIDAR" in f.note
            if is_lidar:
                if ue_id not in active_ids:
                    continue                      # duty-cycled: off
                start = lidar.start_s
                if not lidar.synchronised:
                    # stagger so independent activations do not coincide
                    start += lidar.stagger_s * sorted(active_ids).index(ue_id)
                params["active_from_s"] = start
                params["active_until_s"] = start + lidar.duration_s
                params["bytes_per_period"] = int(
                    lidar.rate_bps / 8.0 * (params["period_ms"] / 1000.0))
            elif f.kind == "xr_video" and video_tier != 1.0:
                params["avg_bytes"] = int(params["avg_bytes"] * video_tier)
            gfbr = f.gfbr_bps
            if is_lidar:
                gfbr = lidar.rate_bps
            elif f.kind == "xr_video":
                gfbr = f.gfbr_bps * video_tier
            flows.append(FlowConfig(
                ue_id=ue_id, qfi=f.qfi, direction=f.direction,
                flow_class=f.flow_class, gfbr_bps=gfbr,
                pdb_ms=DERIVE_PDB_FROM_5QI,       # STANDARDISED, not authored
                traffic_kind=f.kind, traffic_params=params,
            ))
    return flows, seq


def profile_qos_table() -> list[dict[str, Any]]:
    """The per-flow QoS table the regime map reports alongside results.

    Every field carries its provenance, because "the arms diverge at N=8"
    is uninterpretable without knowing what was being guaranteed to whom --
    and the hardware campaign configures real bearers from this.
    """
    rows: list[dict[str, Any]] = []
    for pname, prof in PROFILES.items():
        for f in prof.flows:
            rows.append({
                "profile": pname,
                "5QI": f.qfi,                                  # standardised
                "dir": f.direction,
                "class": f.flow_class,
                "GFBR_bps": f.gfbr_bps,                        # NEGOTIATED
                "PDB_ms": pdb_for_5qi(f.qfi),                  # STANDARDISED
                "priority": priority_for_5qi(f.qfi),           # STANDARDISED
                "LCG": lcg_for_5qi(f.qfi),                     # SIM DEFAULT
                "provenance": {
                    "5QI": "standardised (TS 23.501 Table 5.7.4-1)",
                    "GFBR": "negotiated per bearer (scenario-authored)",
                    "PDB": "standardised (derived, TS 23.501 Table 5.7.4-1)",
                    "priority": "standardised (FIVE_QI_PRIORITY)",
                    "LCG": "simulator default (FIVE_QI_LCG -- invented)",
                    "rate/period": f"operational ({prof.source})",
                },
                "note": f.note,
            })
    return rows
