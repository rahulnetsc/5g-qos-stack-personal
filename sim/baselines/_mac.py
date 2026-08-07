"""Shared MAC logical-channel multiplexer for the per-UE baselines.

The baselines grant one transport block per UE (one DCI). This module
fills that block across the UE's flows the way a 5G MAC LCP does -- by
priority (lower priority_level first), then by backlog. Unlike the
two-tier scheduler's _mac_lcp_fill, the baselines carry no virtual
queues, so the within-priority tiebreak is plain backlog rather than
drift-plus-penalty deficit.
"""

from scheduler import Allocation, FlowConfig


def lcp_fill(
    ue_flows: list[FlowConfig], tbs_bytes: int, buffers
) -> list[tuple[int, int]]:
    """Split one UE's transport block (`tbs_bytes`) across its flows.

    Flows are served in priority order (lower priority_level first), then
    by backlog. Returns [(qfi, bytes), ...] -- the per-flow byte split.
    """
    order = sorted(
        ue_flows,
        key=lambda f: (
            f.priority_level,
            -buffers.state(f.ue_id, f.qfi).bytes_queued,
        ),
    )
    fills: list[tuple[int, int]] = []
    remaining = tbs_bytes
    for f in order:
        if remaining <= 0:
            break
        backlog = buffers.state(f.ue_id, f.qfi).bytes_queued
        take = min(backlog, remaining)
        if take > 0:
            fills.append((f.qfi, take))
            remaining -= take
    return fills


def emit_grant(
    ue_id: int,
    direction: str,
    prbs_used: int,
    tbs_bytes: int,
    ue_flows: list[FlowConfig],
    buffers,
    cce_cost: int,
    snr_used_db: float,
) -> list[Allocation]:
    """Fill a UE's transport block via the MAC multiplexer and emit one
    Allocation per filled flow. The grant's PRB count and DCI/CCE cost
    ride on the first Allocation only -- one DCI per UE grant.

    ``snr_used_db`` is the CQI-visible SNR the scheduler used to pick the
    MCS for this grant; the driver uses it to compute a mismatch-aware
    BLER against the true SNR at transmission time (see driver.py).
    """
    if direction == "UL":
        # Uplink: the gNB sizes the block, the UE fills it. Emit a single
        # per-UE grant and let the host apply the UE's own LCP -- the
        # baselines must model this the same way the two-tier scheduler
        # does, or the comparison stops being like-for-like.
        return [
            Allocation(
                ue_id=ue_id, qfi=-1, direction=direction,
                prbs=prbs_used, bytes_capacity=tbs_bytes,
                cce_cost=cce_cost, is_sps=False,
                snr_used_db=snr_used_db, ue_grant=True,
            )
        ]

    fills = lcp_fill(ue_flows, tbs_bytes, buffers)
    out: list[Allocation] = []
    for i, (qfi, byts) in enumerate(fills):
        out.append(
            Allocation(
                ue_id=ue_id,
                qfi=qfi,
                direction=direction,
                prbs=prbs_used if i == 0 else 0,
                bytes_capacity=byts,
                cce_cost=cce_cost if i == 0 else 0,
                is_sps=False,
                snr_used_db=snr_used_db,
            )
        )
    return out
