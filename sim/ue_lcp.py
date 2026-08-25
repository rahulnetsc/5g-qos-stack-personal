"""UE-side uplink logical-channel prioritisation (TS 38.321 sec 5.4.3.1).

In the uplink the gNB grants a transport block and stops. The **UE** decides
how to fill it, and it does so by a rule the network configured but does not
run: two rounds over the UE's logical channels in decreasing priority order,
the first bounded by each channel's prioritised-bit-rate (PBR) token bucket.

This module is deliberately in ``sim/`` rather than ``scheduler/``. It models
the *UE*, not the gNB, and no gNB implementation may contain it -- putting it
in the scheduler library would be exactly the fidelity error it exists to
correct. See design-docs/oai-phase1-review.md: the OAI port gets this right
and the simulator previously did not.

What the simulator used to do
-----------------------------
``TwoTier._mac_lcp_fill`` chose the uplink split by ``(priority_level, -Q)``
where ``Q`` is the gNB's own drift-plus-penalty virtual queue. That gives the
scheduler a per-slot lever on the uplink byte split that no real scheduler
has, and it flatters multi-flow uplink UEs in particular -- the ue8/ue9/ue10
case that Finding 2 was about.

What happens instead
--------------------
* The **fill** (this module) uses the UE's real backlog and its own token
  buckets. It decides what is actually transmitted.
* The **gNB's estimate** of that split (``TwoTier._estimate_ul_split``) uses
  BSR-reported backlog and drives the virtual-queue drain. It is deliberately
  a different, worse view of the same event.
"""

from dataclasses import dataclass, field

from scheduler import FlowConfig


@dataclass
class _Bucket:
    """One logical channel's PBR token bucket, in bits."""

    pbr_bps: float
    capacity_bits: float  # PBR * BSD -- the bucket ceiling
    tokens: float = 0.0

    def refill(self, dt_s: float) -> None:
        self.tokens = min(self.capacity_bits, self.tokens + self.pbr_bps * dt_s)

    def take(self, bits: float) -> None:
        self.tokens = max(0.0, self.tokens - bits)


class UeLcp:
    """Per-UE uplink transport-block filler.

    One instance models every UE in the run; buckets are keyed per flow. A
    flow with no configured PBR (a plain best-effort bearer) gets a zero-rate
    bucket and is therefore served only from the second round -- out of
    whatever the prioritised round leaves.
    """

    def __init__(self, flows: list[FlowConfig]) -> None:
        self._buckets: dict[tuple[int, int], _Bucket] = {}
        for f in flows:
            if f.direction != "UL":
                continue
            pbr = f.effective_pbr_bps()
            self._buckets[(f.ue_id, f.qfi)] = _Bucket(
                pbr_bps=pbr, capacity_bits=pbr * (f.bsd_ms / 1000.0)
            )

    def refill(self, dt_s: float) -> None:
        """Advance every bucket by one slot. Call once per slot."""
        for b in self._buckets.values():
            b.refill(dt_s)

    def reset_ue(self, ue_id: int) -> None:
        """WP-Join commit 7 (docs/wp-join-plan.md sec1.9): a UE's own
        MAC-layer token buckets restart empty on radio reconnection,
        matching __init__'s own tokens=0.0 default -- a real UE does not
        remember its pre-outage token balance across a lost radio link.
        No-op (nothing to reset) for a UE with no UL flows at all."""
        for key, bucket in self._buckets.items():
            if key[0] == ue_id:
                bucket.tokens = 0.0

    def fill(
        self, ue_flows: list[FlowConfig], tbs_bytes: int, buffers
    ) -> list[tuple[int, int]]:
        """Split one uplink transport block across a UE's flows.

        Round 1 serves each flow, in priority order, up to the smaller of its
        token bucket and its backlog. Round 2 gives whatever is left to the
        same flows in strict priority order, ignoring buckets. Returns
        [(qfi, bytes), ...].
        """
        order = sorted(ue_flows, key=lambda f: f.priority_level)
        taken: dict[int, int] = {}
        remaining = tbs_bytes

        def backlog(f: FlowConfig) -> int:
            # The UE knows its own buffer exactly -- no BSR lag on this side.
            return buffers.state(f.ue_id, f.qfi).bytes_queued - taken.get(f.qfi, 0)

        # Round 1 -- prioritised bit rate, bounded by the token bucket.
        for f in order:
            if remaining <= 0:
                break
            bucket = self._buckets.get((f.ue_id, f.qfi))
            if bucket is None or bucket.tokens <= 0.0:
                continue
            allowance = int(bucket.tokens / 8.0)
            take = min(allowance, backlog(f), remaining)
            if take > 0:
                taken[f.qfi] = taken.get(f.qfi, 0) + take
                bucket.take(take * 8.0)
                remaining -= take

        # Round 2 -- strict priority for the remainder, buckets ignored.
        for f in order:
            if remaining <= 0:
                break
            take = min(backlog(f), remaining)
            if take > 0:
                taken[f.qfi] = taken.get(f.qfi, 0) + take
                remaining -= take

        return [(qfi, byts) for qfi, byts in taken.items() if byts > 0]
