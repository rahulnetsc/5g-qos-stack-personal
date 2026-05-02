"""Reusable scenario definitions, imported by entry-point scripts and tests.

Each scenario is a function returning a ScenarioConfig. Keep these as pure
data so different schedulers can be exercised on identical workloads.
"""

from .config import (
    CarrierConfig,
    FlowConfig,
    ScenarioConfig,
    TDDConfig,
    UEConfig,
)


def smoke_scenario() -> ScenarioConfig:
    """Mixed workload, no overload. All schedulers should serve everyone."""
    return ScenarioConfig(
        name="smoke",
        # 2 seconds at numerology 1 (0.5 ms slots) = 4000 slots
        horizon_slots=4000,
        carrier=CarrierConfig(bandwidth_hz=30_000_000, numerology=1),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=22.0, coherence_slots=2000),
            UEConfig(ue_id=2, mean_snr_db=18.0, coherence_slots=2000),
            UEConfig(ue_id=3, mean_snr_db=25.0, coherence_slots=2000),
        ],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF", pdb_ms=300,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 10_000_000},
            ),
            FlowConfig(
                ue_id=2, qfi=9, direction="DL", flow_class="PF", pdb_ms=300,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
            FlowConfig(
                ue_id=3, qfi=2, direction="UL", flow_class="GBR",
                pdb_ms=30, gfbr_bps=20_000_000,
                traffic_kind="video_frame",
                traffic_params={
                    "period_ms": 16.67,
                    "avg_bytes": 40_000,
                    "i_frame_multiplier": 4.0,
                    "i_frame_period_in_frames": 30,
                },
            ),
            FlowConfig(
                ue_id=2, qfi=1, direction="UL", flow_class="Delay",
                pdb_ms=10,
                traffic_kind="deterministic",
                traffic_params={"period_ms": 5.0, "bytes_per_period": 200},
            ),
        ],
        seed=7,
    )


def vision_scenario() -> ScenarioConfig:
    """Three 30 fps cameras + best-effort traffic. Designed so the cameras'
    bandwidth fits in the carrier but their burst (I-frame) pattern stresses
    a non-SPS scheduler's tail latency.

    Cameras at 30 fps with avg 25 KB / frame and 4x I-frame multiplier every
    30 frames → ~6.6 Mbps avg per camera, ~26 Mbps I-frame burst per camera.
    UL pool ~30 Mbps; offered DL is light.
    """
    return ScenarioConfig(
        name="vision",
        horizon_slots=4000,
        carrier=CarrierConfig(bandwidth_hz=30_000_000, numerology=1),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=22.0, coherence_slots=2000),
            UEConfig(ue_id=2, mean_snr_db=22.0, coherence_slots=2000),
            UEConfig(ue_id=3, mean_snr_db=22.0, coherence_slots=2000),
            UEConfig(ue_id=4, mean_snr_db=22.0, coherence_slots=2000),
        ],
        flows=[
            # Three cameras, I-frames staggered (phase 0/10/20 of 30) so the
            # bursts don't all land in the same slot.
            FlowConfig(
                ue_id=1, qfi=2, direction="UL", flow_class="GBR",
                gfbr_bps=6_500_000, pdb_ms=30,
                traffic_kind="video_frame",
                traffic_params={
                    "period_ms": 33.33, "avg_bytes": 25_000,
                    "i_frame_multiplier": 4.0,
                    "i_frame_period_in_frames": 30,
                    "i_frame_phase": 0,
                },
            ),
            FlowConfig(
                ue_id=2, qfi=2, direction="UL", flow_class="GBR",
                gfbr_bps=6_500_000, pdb_ms=30,
                traffic_kind="video_frame",
                traffic_params={
                    "period_ms": 33.33, "avg_bytes": 25_000,
                    "i_frame_multiplier": 4.0,
                    "i_frame_period_in_frames": 30,
                    "i_frame_phase": 10,
                },
            ),
            FlowConfig(
                ue_id=3, qfi=2, direction="UL", flow_class="GBR",
                gfbr_bps=6_500_000, pdb_ms=30,
                traffic_kind="video_frame",
                traffic_params={
                    "period_ms": 33.33, "avg_bytes": 25_000,
                    "i_frame_multiplier": 4.0,
                    "i_frame_period_in_frames": 30,
                    "i_frame_phase": 20,
                },
            ),
            # Best-effort UL competing with the cameras
            FlowConfig(
                ue_id=4, qfi=9, direction="UL", flow_class="PF", pdb_ms=300,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 5_000_000},
            ),
        ],
        seed=11,
    )


def sensor_dense_scenario(
    num_sensors: int = 30, mean_snr_db: float = 12.0
) -> ScenarioConfig:
    """Many small periodic UL sensor flows. Designed to hit the PDCCH budget,
    where SPS (no DCI per slot) decisively beats dynamic scheduling.

    Each sensor: 5 ms reporting period, 200 bytes (= 320 kbps), tight PDB.
    Total offered: ~10 Mbps (well under PRB capacity), but DCI request rate
    is what pinches when AL > 1 (i.e., when sensors aren't at peak SNR).

    Default SNR=12 dB puts every sensor at AL=2 PDCCH cost, which makes the
    DCI budget the binding constraint and lets SPS shine. At factory-good
    SNR ~22 dB, AL=1 makes PDCCH unbinding and the comparison is muted.
    """
    ues = [
        UEConfig(ue_id=i + 1, mean_snr_db=mean_snr_db, coherence_slots=2000)
        for i in range(num_sensors)
    ]
    flows = [
        FlowConfig(
            ue_id=i + 1, qfi=1, direction="UL", flow_class="Delay", pdb_ms=15,
            traffic_kind="deterministic",
            traffic_params={"period_ms": 5.0, "bytes_per_period": 200},
        )
        for i in range(num_sensors)
    ]
    return ScenarioConfig(
        name=f"sensor_dense_{num_sensors}",
        horizon_slots=4000,
        carrier=CarrierConfig(bandwidth_hz=30_000_000, numerology=1),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=ues,
        flows=flows,
        seed=23,
    )


def overload_scenario() -> ScenarioConfig:
    """Severe DL overload: ~5 Mbps capacity, ~24 Mbps offered. Designed to
    expose scheduler differences in QoS enforcement."""
    return ScenarioConfig(
        name="overload",
        horizon_slots=4000,
        carrier=CarrierConfig(bandwidth_hz=10_000_000, numerology=1),
        tdd=TDDConfig(pattern="DSUUU", s_slot_split=(3, 2, 9)),
        ues=[
            UEConfig(ue_id=1, mean_snr_db=20.0, coherence_slots=2000),
            UEConfig(ue_id=2, mean_snr_db=20.0, coherence_slots=2000),
            UEConfig(ue_id=3, mean_snr_db=20.0, coherence_slots=2000),
        ],
        flows=[
            FlowConfig(
                ue_id=1, qfi=9, direction="DL", flow_class="PF", pdb_ms=300,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 20_000_000},
            ),
            FlowConfig(
                ue_id=2, qfi=2, direction="DL", flow_class="GBR",
                gfbr_bps=4_000_000, pdb_ms=100,
                traffic_kind="poisson",
                traffic_params={"rate_bps": 4_000_000},
            ),
            FlowConfig(
                ue_id=3, qfi=1, direction="DL", flow_class="Delay", pdb_ms=20,
                traffic_kind="deterministic",
                traffic_params={"period_ms": 5.0, "bytes_per_period": 400},
            ),
        ],
        seed=2,
    )
