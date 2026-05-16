from collections import defaultdict, deque
from dataclasses import dataclass

from ..buffer import BufferModel
from ..channel import ChannelModel, bits_per_prb, cce_aggregation_level
from ..config import FlowConfig
from ..resource import ResourceGrid, SlotGrid
from ..tier1 import estimate_demand_bps, solve_tier1
from . import Allocation


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

    Per-slot metric:
        metric_i = (Q_i + delay_urgency_bonus_i) * spectral_efficiency_i

    For Delay-class flows, an HoL/PDB urgency term is added equivalent to a
    multiple of the per-slot target inflow. Combined with channel-aware
    spectral_efficiency weighting, the rule is opportunistic but rate-tracking:
    a flow that is behind its target AND has a good channel wins.
    """

    def __init__(
        self,
        tier1_period_slots: int = 2000,
        snr_window_slots: int = 100,
        delay_urgency_weight: float = 4.0,
        delay_exponent: float = 2.0,
        enable_sps: bool = True,
        sps_safety_margin: float = 1.10,
        gbr_penalty_init: float = 1e3,
        gbr_penalty_lr: float = 0.0,
        gbr_penalty_max: float = 1e6,
    ) -> None:
        self.tier1_period = max(1, tier1_period_slots)
        self.snr_window = max(1, snr_window_slots)
        self.delay_w = delay_urgency_weight
        self.delay_exp = delay_exponent
        # SPS: decide PRB reservation for periodic flows after each Tier-1 solve.
        self.enable_sps = enable_sps
        self.sps_safety_margin = sps_safety_margin
        # Adaptive per-flow GBR slack penalty (dual ascent). gbr_penalty_lr=0
        # freezes the penalty at gbr_penalty_init -> identical to the old
        # uniform-scalar behaviour.
        self.gbr_penalty_init = gbr_penalty_init
        self.gbr_penalty_lr = gbr_penalty_lr
        self.gbr_penalty_max = gbr_penalty_max

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
        self._grid: ResourceGrid | None = None
        self._last_solve_slot = -(10**9)
        self._tier1_solve_count = 0

    def configure(self, flows, slot_duration_s, grid):
        self._flows = list(flows)
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

    def _update_sps_reservations(self, snr_in: dict[int, float]) -> None:
        """Decide which periodic flows get SPS reservations and how big.

        Sizes the per-slot PRB reservation so that, averaged across all slots
        of the relevant direction in the TDD cycle, the reserved bandwidth
        meets target_bps * sps_safety_margin.
        """
        self._sps = []
        self._sps_keys = set()
        if not self._grid:
            return

        pattern_len = len(self._grid.pattern)
        # Per-direction slot counts and per-slot symbol counts in the cycle.
        per_dir_slot_count = {"DL": 0, "UL": 0}
        per_dir_avg_symbols = {"DL": 0.0, "UL": 0.0}
        for i in range(pattern_len):
            sg = self._grid.slot_grid(i)
            if sg.dl_symbols > 0:
                per_dir_slot_count["DL"] += 1
                per_dir_avg_symbols["DL"] += sg.dl_symbols
            if sg.ul_symbols > 0:
                per_dir_slot_count["UL"] += 1
                per_dir_avg_symbols["UL"] += sg.ul_symbols
        for d in ("DL", "UL"):
            n = per_dir_slot_count[d]
            per_dir_avg_symbols[d] = per_dir_avg_symbols[d] / n if n > 0 else 0

        cycle_duration_s = pattern_len * self.slot_duration_s
        # Track per-direction PRBs reserved so far (for over-commit guard)
        prbs_reserved_by_dir = {"DL": 0, "UL": 0}

        for f in self._flows:
            if not self._is_sps_eligible(f):
                continue
            key = (f.ue_id, f.qfi)
            target_bps = self._targets_bps.get(key, 0.0)
            if target_bps <= 0:
                continue
            n_dir_slots = per_dir_slot_count[f.direction]
            avg_sym = per_dir_avg_symbols[f.direction]
            if n_dir_slots == 0 or avg_sym == 0:
                continue

            snr = snr_in.get(f.ue_id, 20.0)
            bits_per_rb_avg, bler = bits_per_prb(snr, symbols=int(avg_sym))
            effective_bits = bits_per_rb_avg * (1 - bler)
            if effective_bits <= 0:
                continue

            # Bytes the flow needs per direction-slot to hit target avg rate.
            bytes_per_dir_slot = (
                target_bps * self.sps_safety_margin * cycle_duration_s
                / n_dir_slots
                / 8
            )
            prbs_needed = max(1, int(-(-bytes_per_dir_slot * 8 // effective_bits)))

            # Don't over-commit the carrier
            if prbs_reserved_by_dir[f.direction] + prbs_needed > self._grid.prb_count:
                continue

            self._sps.append(
                _SPSReservation(
                    ue_id=f.ue_id,
                    qfi=f.qfi,
                    direction=f.direction,
                    prbs_per_slot=prbs_needed,
                )
            )
            self._sps_keys.add(key)
            prbs_reserved_by_dir[f.direction] += prbs_needed

    def _update_snr_ewma(self, channel: ChannelModel) -> None:
        alpha = 1.0 - 1.0 / self.snr_window
        for f in self._flows:
            cur = channel.get_snr_db(f.ue_id)
            prev = self._snr_avg.get(f.ue_id, cur)
            self._snr_avg[f.ue_id] = alpha * prev + (1.0 - alpha) * cur

    def allocate(
        self, slot: SlotGrid, buffers: BufferModel, channel: ChannelModel
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
            self._virtual_q[key] += target_bps * self.slot_duration_s

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

    def _allocate_sps(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
        direction: str,
        committed_this_slot: dict[tuple[int, int], int],
    ) -> tuple[list[Allocation], int]:
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        out: list[Allocation] = []
        prbs_used_total = 0
        for sps in self._sps:
            if sps.direction != direction:
                continue
            key = (sps.ue_id, sps.qfi)
            backlog = buffers.state(*key).bytes_queued
            if backlog <= 0:
                # Real SPS would still occupy the PRBs (wasted). Simulator skips
                # them, so other flows benefit. Conservative and matches what
                # release-on-empty implementations do.
                continue
            snr = channel.get_snr_db(sps.ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue

            prbs_avail = slot.prb_count - prbs_used_total
            prbs_for_sps = min(sps.prbs_per_slot, prbs_avail)
            if prbs_for_sps <= 0:
                continue

            # Right-size: don't reserve more PRBs than the buffer needs.
            prbs_needed = (backlog * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_for_sps, max(1, prbs_needed))
            bytes_capacity = min(backlog, (prbs_used * bits_per_rb) // 8)
            if bytes_capacity <= 0:
                continue

            expected_delivered_bits = bytes_capacity * 8 * (1.0 - bler)
            self._virtual_q[key] = max(
                0.0, self._virtual_q[key] - expected_delivered_bits
            )
            # Match the driver's drain accounting (int bytes after BLER).
            committed_this_slot[key] += int(bytes_capacity * (1.0 - bler))
            prbs_used_total += prbs_used

            out.append(
                Allocation(
                    ue_id=sps.ue_id,
                    qfi=sps.qfi,
                    direction=direction,
                    prbs=prbs_used,
                    bytes_capacity=bytes_capacity,
                    cce_cost=0,  # SPS doesn't consume PDCCH per slot
                    is_sps=True,
                )
            )
        return out, prbs_used_total

    def _allocate_dynamic(
        self,
        slot: SlotGrid,
        buffers: BufferModel,
        channel: ChannelModel,
        direction: str,
        prb_budget: int,
        committed_this_slot: dict[tuple[int, int], int],
    ) -> list[Allocation]:
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        now_s = slot.slot_index * self.slot_duration_s

        def remaining_backlog(key):
            return max(
                0,
                buffers.state(*key).bytes_queued - committed_this_slot.get(key, 0),
            )

        # Reference scale for delay-urgency bonus: the largest "effective Q"
        # across all flows. Includes SPS-flow buffer pressure so spillover for
        # I-frame bursts can compete with bulk flows. Backlog used here is
        # net of what SPS already committed this slot.
        eff_q_by_key = {}
        for f in self._flows:
            key = (f.ue_id, f.qfi)
            if key in self._sps_keys:
                eff_q_by_key[key] = remaining_backlog(key) * 8.0
            else:
                eff_q_by_key[key] = self._virtual_q[key]
        max_q = max(eff_q_by_key.values(), default=0.0)

        scored: list[tuple[float, FlowConfig, int, float, tuple[int, int]]] = []
        for f in self._flows:
            if f.direction != direction:
                continue
            key = (f.ue_id, f.qfi)
            if remaining_backlog(key) <= 0:
                continue
            snr = channel.get_snr_db(f.ue_id)
            bits_per_rb, bler = bits_per_prb(snr, symbols=symbols)
            if bits_per_rb <= 0:
                continue

            q = eff_q_by_key[key]
            # Delay urgency: layer on extra virtual deficit scaled to the
            # max effective Q so deadline-pressed delay flows can preempt.
            if f.flow_class == "Delay":
                pdb_s = f.pdb_ms / 1000.0
                if pdb_s > 0:
                    hol = buffers.hol_delay_s(f.ue_id, f.qfi, now_s)
                    if hol > 0:
                        urgency = min(1.0, hol / pdb_s) ** self.delay_exp
                        q += self.delay_w * urgency * max(max_q, 1.0)

            metric = q * bits_per_rb
            scored.append((metric, f, bits_per_rb, bler, key))

        if not scored:
            return []
        scored.sort(key=lambda x: x[0], reverse=True)

        prbs_left = prb_budget
        cce_left = slot.pdcch_cce_budget
        # SPS allocations made earlier consumed 0 CCEs by definition, so
        # the slot's full budget is available for dynamic.
        out: list[Allocation] = []
        for _metric, f, bits_per_rb, bler, key in scored:
            if prbs_left <= 0:
                break
            cce_cost = cce_aggregation_level(channel.get_snr_db(f.ue_id))
            if cce_left < cce_cost:
                continue
            avail_bytes = remaining_backlog(key)
            if avail_bytes <= 0:
                continue
            prbs_needed = (avail_bytes * 8 + bits_per_rb - 1) // bits_per_rb
            prbs_used = min(prbs_left, max(1, prbs_needed))
            bytes_capacity = min(avail_bytes, (prbs_used * bits_per_rb) // 8)
            if bytes_capacity <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost

            expected_delivered_bits = bytes_capacity * 8 * (1.0 - bler)
            self._virtual_q[key] = max(
                0.0, self._virtual_q[key] - expected_delivered_bits
            )
            committed_this_slot[key] += int(bytes_capacity * (1.0 - bler))

            out.append(
                Allocation(
                    ue_id=f.ue_id,
                    qfi=f.qfi,
                    direction=direction,
                    prbs=prbs_used,
                    bytes_capacity=bytes_capacity,
                    cce_cost=cce_cost,
                    is_sps=False,
                )
            )
        return out
