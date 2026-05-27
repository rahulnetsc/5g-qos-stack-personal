from collections import defaultdict, deque
from dataclasses import dataclass

from .flow import FlowConfig
from .interfaces import (
    Allocation,
    BufferView,
    ChannelView,
    GridView,
    SlotView,
)
from .link import bits_per_prb, cce_aggregation_level, bler_sigmoid
from .tier1 import estimate_demand_bps, solve_tier1


@dataclass
class _SPSReservation:
    """A per-slot PRB reservation for one (UE, QFI) flow in one direction."""

    ue_id: int
    qfi: int
    direction: str  # 'DL' or 'UL'
    prbs_per_slot: int


class TwoTier:
    """Tier-1 LP (every N slots) sets per-flow target rates; Tier-2 uses
    drift-plus-penalty (Lyapunov optimization) to steer actual rates to targets.

    Virtual queue per flow:
        Q_i += target_i * slot_duration_s          (grow at the Tier-1 target)
        Q_i  = min(Q_i, windowed_ceiling_i)        (clamp, see below)
        Q_i  = max(0, Q_i - delivered_i)           (drain by delivered bits)
    The virtual queue is a control accumulator, not a buffer of real bits.
    Its arrivals are the Tier-1 *target* rate (the only lever Tier-1 has on
    Tier-2).

    The ceiling is the bits the flow legitimately should have delivered over
    the last `tier1_period` slots but didn't:
        ceiling_i = max(0, min(target_i * W, arrived_W_i) - delivered_W_i)
    where W is the window in seconds and arrived_W / delivered_W are bits
    over the trailing window. A flow can't be owed more than its target,
    nor more than what actually arrived. Using a *windowed* arrival count
    rather than instantaneous backlog is essential: a bursty flow's RLC
    buffer momentarily empties between frames, and clamping Q to that
    instantaneous (near-zero) backlog destroys the legitimate rate-tracking
    debt, letting continuous flows starve bursty GBR ones.

    Per-slot scheduling is per UE, mirroring the 5G MAC. Each UE is granted
    PRBs once (one DCI), ranked by the summed drift-plus-penalty deficit of
    its backlogged flows times its spectral efficiency:
        ue_metric = (sum_f  Q_f + delay_urgency_f) * spectral_efficiency_ue
    The grant's transport block is then filled by the MAC multiplexer
    (_mac_lcp_fill) across the UE's flows -- logical-channel prioritization:
    by priority_level, then by drift-plus-penalty deficit. For Delay-class
    flows an HoL/PDB urgency term is folded into Q_f. The rule stays
    opportunistic but rate-tracking: a UE whose flows are behind target and
    which has a good channel wins the grant.
    """

    def __init__(
        self,
        tier1_period_slots: int = 2000,
        snr_window_slots: int = 100,
        delay_urgency_weight: float = 4.0,
        delay_exponent: float = 2.0,
        enable_sps: bool = True,
        sps_safety_margin: float = 1.10,
        sps_budget_fraction: float = 0.85,
        sps_min_scale: float = 0.75,
        gbr_penalty_init: float = 1e3,
        gbr_penalty_lr: float = 0.0,
        gbr_penalty_max: float = 1e6,
        gbr_penalty_se_exponent: float = 0.0,
        slice_shares: "dict[int, dict[str, float]] | None" = None,
        slice_slack_penalty: float = 1e3,
    ) -> None:
        self.tier1_period = max(1, tier1_period_slots)
        self.snr_window = max(1, snr_window_slots)
        self.delay_w = delay_urgency_weight
        self.delay_exp = delay_exponent
        # SPS: decide PRB reservation for periodic flows after each Tier-1 solve.
        self.enable_sps = enable_sps
        self.sps_safety_margin = sps_safety_margin
        # SPS reserves at most this fraction of the carrier, leaving a
        # dynamic pool for burst spillover.
        self.sps_budget_fraction = sps_budget_fraction
        # If a priority tier's SPS reservations would be scaled below this
        # fraction of their desired size, the tier is run dynamically
        # instead -- unless that would overrun the PDCCH/CCE budget.
        self.sps_min_scale = sps_min_scale
        # Adaptive per-flow GBR slack penalty (dual ascent). gbr_penalty_lr=0
        # freezes the penalty at gbr_penalty_init -> identical to the old
        # uniform-scalar behaviour.
        self.gbr_penalty_init = gbr_penalty_init
        self.gbr_penalty_lr = gbr_penalty_lr
        self.gbr_penalty_max = gbr_penalty_max
        # Spectral-efficiency tilt exponent k on the GBR slack penalty (see
        # solve_tier1): 0 = off, k>0 efficiency-first, k<0 RB-level parity.
        self.gbr_penalty_se_exponent = gbr_penalty_se_exponent
        # Network-slice RB shares {slice_id: {"DL": frac, "UL": frac}};
        # None disables slicing. Enforced as a soft Tier-1 floor.
        self.slice_shares = slice_shares
        self.slice_slack_penalty = slice_slack_penalty

        self._flows: list[FlowConfig] = []
        self._snr_avg: dict[int, float] = {}
        self._targets_bps: dict[tuple[int, int], float] = {}
        self._demand_bps: dict[tuple[int, int], float] = {}
        self._virtual_q: dict[tuple[int, int], float] = {}
        self._gbr_penalty: dict[tuple[int, int], float] = {}
        # Trailing-window snapshots of cumulative arrived/delivered bytes,
        # one append per slot, length tier1_period -> a sliding window.
        self._arr_hist: dict[tuple[int, int], deque] = {}
        self._del_hist: dict[tuple[int, int], deque] = {}
        self._sps: list[_SPSReservation] = []
        self._sps_keys: set[tuple[int, int]] = set()
        self.slot_duration_s = 0.0
        self._grid: GridView | None = None
        self._last_solve_slot = -(10**9)
        self._tier1_solve_count = 0

    def configure(self, flows, slot_duration_s, grid):
        self._flows = list(flows)
        self._flow_by_key = {(f.ue_id, f.qfi): f for f in flows}
        self.slot_duration_s = slot_duration_s
        self._grid = grid
        self._snr_avg = {}
        self._demand_bps = {(f.ue_id, f.qfi): estimate_demand_bps(f) for f in flows}
        self._targets_bps = dict(self._demand_bps)
        self._virtual_q = {(f.ue_id, f.qfi): 0.0 for f in flows}
        self._gbr_penalty = {
            (f.ue_id, f.qfi): self.gbr_penalty_init for f in flows
        }
        self._arr_hist = {
            (f.ue_id, f.qfi): deque(maxlen=self.tier1_period) for f in flows
        }
        self._del_hist = {
            (f.ue_id, f.qfi): deque(maxlen=self.tier1_period) for f in flows
        }

    def _resolve_tier1(self) -> None:
        snr_in = {
            f.ue_id: self._snr_avg.get(f.ue_id, 20.0) for f in self._flows
        }
        self._targets_bps = solve_tier1(
            flows=self._flows,
            snr_db_per_ue=snr_in,
            grid=self._grid,
            demand_bps=self._demand_bps,
            gbr_slack_penalty=self._gbr_penalty,
            se_penalty_exponent=self.gbr_penalty_se_exponent,
            slice_shares=self.slice_shares,
            slice_slack_penalty=self.slice_slack_penalty,
        )
        self._tier1_solve_count += 1
        self._update_gbr_penalties()
        if self.enable_sps:
            self._update_sps_reservations(snr_in)

    def _update_gbr_penalties(self) -> None:
        """Dual ascent on the per-flow GBR slack penalty.

        A GBR flow that misses its GFBR has its penalty raised by
        gbr_penalty_lr * (shortfall / GFBR). The shortfall is normalized by
        GFBR so it lands in [0, 1] and the learning rate is scale-free. The
        penalty is capped at gbr_penalty_max so a genuinely infeasible flow
        cannot diverge -- hitting the cap is itself the signal that the flow
        needs admission control rather than more penalty.

        With gbr_penalty_lr == 0 this is a no-op: the penalty stays at its
        uniform initial value, identical to the old scalar behaviour.
        """
        if self.gbr_penalty_lr <= 0.0:
            return
        for f in self._flows:
            if f.flow_class != "GBR" or f.gfbr_bps <= 0:
                continue
            key = (f.ue_id, f.qfi)
            shortfall = max(0.0, f.gfbr_bps - self._targets_bps.get(key, 0.0))
            if shortfall <= 0.0:
                continue
            self._gbr_penalty[key] = min(
                self.gbr_penalty_max,
                self._gbr_penalty[key]
                + self.gbr_penalty_lr * (shortfall / f.gfbr_bps),
            )

    @staticmethod
    def _is_sps_eligible(f: FlowConfig) -> bool:
        return f.traffic_kind in ("deterministic", "video_frame")

    def _sps_floor_bps(self, f: FlowConfig) -> float:
        """The contracted baseline an SPS reservation should carry: a GBR
        flow's GFBR, otherwise a periodic flow's deterministic offered rate.
        This is a Tier-1 *input* (the contract), not the LP's derived target,
        so SPS sizing stays decoupled from the LP's overload arbitration."""
        if f.flow_class == "GBR" and f.gfbr_bps > 0:
            return f.gfbr_bps
        return estimate_demand_bps(f)

    def _update_sps_reservations(self, snr_in: dict[int, float]) -> None:
        """Decide which periodic flows get SPS reservations and how big.

        Each SPS reservation is sized to the flow's contracted floor (see
        _sps_floor_bps). Reservations are allocated per direction in priority
        order (lower flow.priority_level first). Within a priority tier, if
        the floors over-subscribe the remaining PRB budget, every reservation
        in the tier is scaled back proportionally -- so no flow is dropped
        merely for being late in the flow list (NOTES.md Finding 2). Leftover
        budget carries to the next tier. SPS is capped at sps_budget_fraction
        of the carrier, leaving a dynamic pool for burst spillover.
        """
        self._sps = []
        self._sps_keys = set()
        if not self._grid:
            return

        pattern_len = len(self._grid.pattern)
        # Per-direction slot counts, per-slot symbol counts, and the per-slot
        # PDCCH/CCE budget seen in the cycle.
        per_dir_slot_count = {"DL": 0, "UL": 0}
        per_dir_avg_symbols = {"DL": 0.0, "UL": 0.0}
        per_dir_cce_budget = {"DL": 0, "UL": 0}
        for i in range(pattern_len):
            sg = self._grid.slot_grid(i)
            if sg.dl_symbols > 0:
                per_dir_slot_count["DL"] += 1
                per_dir_avg_symbols["DL"] += sg.dl_symbols
                per_dir_cce_budget["DL"] = sg.pdcch_cce_budget
            if sg.ul_symbols > 0:
                per_dir_slot_count["UL"] += 1
                per_dir_avg_symbols["UL"] += sg.ul_symbols
                per_dir_cce_budget["UL"] = sg.pdcch_cce_budget
        for d in ("DL", "UL"):
            n = per_dir_slot_count[d]
            per_dir_avg_symbols[d] = per_dir_avg_symbols[d] / n if n > 0 else 0

        cycle_duration_s = pattern_len * self.slot_duration_s
        budget = int(self._grid.prb_count * self.sps_budget_fraction)

        for direction in ("DL", "UL"):
            n_dir_slots = per_dir_slot_count[direction]
            avg_sym = per_dir_avg_symbols[direction]
            if n_dir_slots == 0 or avg_sym == 0:
                continue

            eligible = [
                f for f in self._flows
                if self._is_sps_eligible(f) and f.direction == direction
            ]
            remaining = budget
            # Priority tiers: lower priority_level number == higher priority.
            for plevel in sorted({f.priority_level for f in eligible}):
                if remaining <= 0:
                    break
                tier = [f for f in eligible if f.priority_level == plevel]

                # PRBs each flow wants to carry its contracted floor.
                desired: list[tuple[FlowConfig, int]] = []
                for f in tier:
                    floor_bps = self._sps_floor_bps(f)
                    if floor_bps <= 0:
                        continue
                    snr = snr_in.get(f.ue_id, 20.0)
                    bits_per_rb, _ = bits_per_prb(snr, symbols=int(avg_sym))
                    effective_bits = bits_per_rb * (
                        1.0 - bler_sigmoid(snr - self._snr_avg.get(f.ue_id, snr))
                    )
                    if effective_bits <= 0:
                        continue
                    bytes_per_dir_slot = (
                        floor_bps * self.sps_safety_margin * cycle_duration_s
                        / n_dir_slots / 8
                    )
                    prbs = max(1, int(-(-bytes_per_dir_slot * 8 // effective_bits)))
                    desired.append((f, prbs))

                total = sum(p for _, p in desired)
                if total <= 0:
                    continue
                # Scale the whole tier proportionally if it over-commits, so
                # every flow keeps a (smaller) standing grant rather than the
                # last-listed flows getting none.
                scale = min(1.0, remaining / total)

                # Viability floor. If SPS would be undersized (scale below
                # sps_min_scale), a fixed reservation tends to lose to the
                # adaptive dynamic scheduler, so drop the tier to dynamic.
                # Exception: if running the tier dynamically would overrun
                # the per-slot PDCCH/CCE budget, SPS's zero-DCI property
                # still makes it the lesser evil, so keep it.
                if scale < self.sps_min_scale:
                    tier_cce = sum(
                        cce_aggregation_level(snr_in.get(f.ue_id, 20.0))
                        for f, _ in desired
                    )
                    if tier_cce <= per_dir_cce_budget[direction]:
                        continue  # dynamic can absorb the tier -- skip SPS
                    # else: keep the undersized reservation for CCE relief.

                for f, prbs in desired:
                    granted = max(1, round(prbs * scale))
                    self._sps.append(
                        _SPSReservation(
                            ue_id=f.ue_id,
                            qfi=f.qfi,
                            direction=direction,
                            prbs_per_slot=granted,
                        )
                    )
                    self._sps_keys.add((f.ue_id, f.qfi))
                    remaining -= granted
                remaining = max(0, remaining)

    def _update_snr_ewma(self, channel: ChannelView) -> None:
        alpha = 1.0 - 1.0 / self.snr_window
        for f in self._flows:
            cur = channel.get_snr_db(f.ue_id)
            prev = self._snr_avg.get(f.ue_id, cur)
            self._snr_avg[f.ue_id] = alpha * prev + (1.0 - alpha) * cur

    def allocate(
        self, slot: SlotView, buffers: BufferView, channel: ChannelView
    ) -> list[Allocation]:
        self._update_snr_ewma(channel)
        if slot.slot_index - self._last_solve_slot >= self.tier1_period:
            self._resolve_tier1()
            self._last_solve_slot = slot.slot_index

        # Grow each virtual queue at its Tier-1 target rate, then clamp to a
        # windowed ceiling: the bits the flow legitimately should have
        # delivered over the last tier1_period slots but didn't. A windowed
        # arrival count (not instantaneous backlog) is what lets a bursty
        # flow keep its rate-tracking debt across the gaps between frames.
        window_s = self.tier1_period * self.slot_duration_s
        for f in self._flows:
            key = (f.ue_id, f.qfi)
            target_bps = self._targets_bps.get(key, 0.0)
            total_prbs = self._grid.prb_count
            capacity_fraction = slot.prb_count / max(1, total_prbs)
            self._virtual_q[key] += target_bps * self.slot_duration_s * capacity_fraction

            arr_now = buffers.arrived_cum(*key) * 8
            del_now = buffers.delivered_cum(*key) * 8
            arr_hist = self._arr_hist[key]
            del_hist = self._del_hist[key]
            arrived_w = arr_now - (arr_hist[0] if arr_hist else 0)
            delivered_w = del_now - (del_hist[0] if del_hist else 0)
            arr_hist.append(arr_now)
            del_hist.append(del_now)

            # Can't be owed more than the target, nor more than what arrived.
            should_deliver = min(target_bps * window_s, arrived_w)
            ceiling = max(0.0, should_deliver - delivered_w)
            if self._virtual_q[key] > ceiling:
                self._virtual_q[key] = ceiling

        # Tracks bytes the scheduler has committed (drained-equivalent) to
        # each flow within this slot, so SPS + dynamic for the same flow
        # don't both allocate against the original backlog.
        committed_this_slot: dict[tuple[int, int], int] = defaultdict(int)

        out: list[Allocation] = []
        # Per direction: SPS first, then dynamic on remaining PRBs.
        for direction in ("DL", "UL"):
            symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
            if symbols <= 0:
                continue

            sps_outs, sps_prbs_used = self._allocate_sps(
                slot, buffers, channel, direction, committed_this_slot
            )
            out.extend(sps_outs)

            remaining_prbs = slot.prb_count - sps_prbs_used
            if remaining_prbs > 0:
                out.extend(
                    self._allocate_dynamic(
                        slot,
                        buffers,
                        channel,
                        direction,
                        remaining_prbs,
                        committed_this_slot,
                    )
                )
        return out

    def _remaining_backlog(self, key, buffers, committed) -> int:
        """Real bytes still queued for a flow, net of whatever has already
        been committed to it this slot (so SPS then dynamic for the same
        flow do not both allocate against the original backlog)."""
        return max(0, buffers.state(*key).bytes_queued - committed.get(key, 0))

    def _compute_flow_q(self, direction, buffers, committed, now_s):
        """Per-flow effective virtual deficit for `direction`: the Tier-2
        virtual queue (or, for an SPS flow's dynamic spillover, its real
        backlog) plus an HoL/PDB urgency bonus for Delay-class flows."""
        base = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            key = (f.ue_id, f.qfi)
            if key in self._sps_keys:
                base[key] = self._remaining_backlog(key, buffers, committed) * 8.0
            else:
                base[key] = self._virtual_q[key]
        max_q = max(base.values(), default=0.0)

        q_by_key = {}
        for f in self._flows:
            if f.direction != direction:
                continue
            key = (f.ue_id, f.qfi)
            q = base[key]
            if f.flow_class == "Delay" and f.pdb_ms > 0:
                hol = buffers.hol_delay_s(f.ue_id, f.qfi, now_s)
                if hol > 0:
                    urgency = min(1.0, hol / (f.pdb_ms / 1000.0)) ** self.delay_exp
                    q += self.delay_w * urgency * max(max_q, 1.0)
            q_by_key[key] = q
        return q_by_key

    def _mac_lcp_fill(self, ue_flows, tbs_bytes, q_by_key, buffers, committed):
        """MAC logical-channel multiplexer: fill one UE's transport block
        across its flows. Flows are served in priority order (lower
        priority_level first), and within a priority tier by drift-plus-
        penalty deficit -- the flow furthest behind its Tier-1 target first.
        Returns [(flow_key, bytes), ...]."""
        order = sorted(
            ue_flows,
            key=lambda f: (f.priority_level, -q_by_key.get((f.ue_id, f.qfi), 0.0)),
        )
        fills: list[tuple[tuple[int, int], int]] = []
        remaining = tbs_bytes
        for f in order:
            if remaining <= 0:
                break
            key = (f.ue_id, f.qfi)
            take = min(self._remaining_backlog(key, buffers, committed), remaining)
            if take > 0:
                fills.append((key, take))
                remaining -= take
        return fills

    def _emit_grant(
        self, ue_id, direction, prbs_used, tbs_bytes, bler, ue_flows,
        q_by_key, buffers, committed, cce_cost, is_sps,
    ) -> list[Allocation]:
        """Fill a UE's transport block via the MAC multiplexer and emit one
        per-flow Allocation per filled flow. The grant's PRB count and DCI
        cost ride on the first Allocation -- one DCI per UE grant."""
        fills = self._mac_lcp_fill(ue_flows, tbs_bytes, q_by_key, buffers, committed)
        out: list[Allocation] = []
        for i, (key, byts) in enumerate(fills):
            delivered_bits = byts * 8 * (1.0 - bler)
            self._virtual_q[key] = max(0.0, self._virtual_q[key] - delivered_bits)
            committed[key] += byts
            out.append(
                Allocation(
                    ue_id=ue_id, qfi=key[1], direction=direction,
                    prbs=prbs_used if i == 0 else 0,
                    bytes_capacity=byts,
                    cce_cost=cce_cost if i == 0 else 0,
                    is_sps=is_sps,
                )
            )
        return out

    def _allocate_sps(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
        committed_this_slot: dict[tuple[int, int], int],
    ) -> tuple[list[Allocation], int]:
        """Serve the SPS configured grants for `direction`, per UE. A UE's
        reservations (one per SPS-eligible flow) are pooled into a single
        grant whose transport block the MAC multiplexer fills across the
        UE's flows. SPS consumes no PDCCH."""
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        now_s = slot.slot_index * self.slot_duration_s
        q_by_key = self._compute_flow_q(
            direction, buffers, committed_this_slot, now_s
        )

        ue_reservations: dict[int, list[_SPSReservation]] = defaultdict(list)
        for sps in self._sps:
            if sps.direction == direction:
                ue_reservations[sps.ue_id].append(sps)

        out: list[Allocation] = []
        prbs_used_total = 0
        for ue_id, reservations in ue_reservations.items():
            ue_flows = [self._flow_by_key[(s.ue_id, s.qfi)] for s in reservations]
            ue_backlog = sum(
                self._remaining_backlog((f.ue_id, f.qfi), buffers, committed_this_slot)
                for f in ue_flows
            )
            if ue_backlog <= 0:
                # Empty configured grant: a real gNB wastes the PRBs; the
                # simulator releases them (release-on-empty CG).
                continue
            snr = channel.get_snr_db(ue_id)
            bits_per_rb, _ = bits_per_prb(snr, symbols=symbols)
            bler = bler_sigmoid(snr - self._snr_avg.get(ue_id, snr))
            if bits_per_rb <= 0:
                continue

            reserved_prbs = sum(s.prbs_per_slot for s in reservations)
            prbs_for_sps = min(reserved_prbs, slot.prb_count - prbs_used_total)
            if prbs_for_sps <= 0:
                continue
            # Right-size the grant to the UE's actual backlog.
            prbs_needed = (ue_backlog * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_for_sps, max(1, prbs_needed))
            tbs_bytes = min(ue_backlog, (prbs_used * bits_per_rb) // 8)
            if tbs_bytes <= 0:
                continue
            prbs_used_total += prbs_used

            out.extend(self._emit_grant(
                ue_id, direction, prbs_used, tbs_bytes, bler, ue_flows,
                q_by_key, buffers, committed_this_slot, cce_cost=0, is_sps=True,
            ))
        return out, prbs_used_total

    def _allocate_dynamic(
        self,
        slot: SlotView,
        buffers: BufferView,
        channel: ChannelView,
        direction: str,
        prb_budget: int,
        committed_this_slot: dict[tuple[int, int], int],
    ) -> list[Allocation]:
        """Per-UE dynamic scheduling. Each UE is granted PRBs once (one DCI),
        sized to a transport block; the MAC multiplexer then fills the TB
        across the UE's flows. UEs are ranked by the summed drift-plus-
        penalty deficit of their backlogged flows times spectral efficiency."""
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        now_s = slot.slot_index * self.slot_duration_s
        q_by_key = self._compute_flow_q(
            direction, buffers, committed_this_slot, now_s
        )

        # Group this direction's backlogged flows by UE.
        ue_flows: dict[int, list[FlowConfig]] = defaultdict(list)
        for f in self._flows:
            if f.direction != direction:
                continue
            if self._remaining_backlog(
                (f.ue_id, f.qfi), buffers, committed_this_slot
            ) > 0:
                ue_flows[f.ue_id].append(f)

        # Rank UEs by total deficit x spectral efficiency.
        scored: list[tuple[float, int, list, int, float]] = []
        for ue_id, flows in ue_flows.items():
            snr = channel.get_snr_db(ue_id)
            bits_per_rb, _ = bits_per_prb(snr, symbols=symbols)
            bler = bler_sigmoid(snr - self._snr_avg.get(ue_id, snr))
            if bits_per_rb <= 0:
                continue
            ue_q = sum(q_by_key.get((f.ue_id, f.qfi), 0.0) for f in flows)
            effective_bits = bits_per_rb * (1.0 - bler)
            scored.append((ue_q * effective_bits, ue_id, flows, bits_per_rb, bler))
        scored.sort(key=lambda x: x[0], reverse=True)

        prbs_left = prb_budget
        cce_left = slot.pdcch_cce_budget
        out: list[Allocation] = []
        for _metric, ue_id, flows, bits_per_rb, bler in scored:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(channel.get_snr_db(ue_id))
            if cce_left < cce_cost:
                continue
            ue_backlog = sum(
                self._remaining_backlog((f.ue_id, f.qfi), buffers, committed_this_slot)
                for f in flows
            )
            if ue_backlog <= 0:
                continue
            prbs_needed = (ue_backlog * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_left, max(1, prbs_needed))
            tbs_bytes = min(ue_backlog, (prbs_used * bits_per_rb) // 8)
            if tbs_bytes <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            out.extend(self._emit_grant(
                ue_id, direction, prbs_used, tbs_bytes, bler, flows,
                q_by_key, buffers, committed_this_slot,
                cce_cost=cce_cost, is_sps=False,
            ))
        return out
