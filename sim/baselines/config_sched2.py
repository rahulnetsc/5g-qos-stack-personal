"""ConfigSched2 -- the configuration scheduler being rebuilt toward the v2
formulation of docs/config-scheduler-handoff.md section 8c, one fidelity
change per commit, each measured on the 2026-09-16 campaign's own seeds
against the frozen prototype (`sim/baselines/config_sched.py`, arm
`ConfigSched`, which stays as measured).

Increment 0 (this file's first commit): a byte-for-byte copy of the
prototype after its two bug fixes (65d45ae, f6aa911), asserted identical
on a full G3 run so every later diff is one mechanism. The prototype's own
docstring follows unchanged until an increment rewrites the part it
describes; the increment log lives in docs/campaign-cell-2026-09-16-linux.md
section 8.

Increment 1: a contracted flow with backlog and no plan is served ahead of
every planned unit, shortest PDB first (G2's between-re-solves STOPs).

Increment 5 (the v2 core, handoff section 8c): Tier 1 gives every planned
flow a HARMONIC PERIOD T_i (a power of two in slots, W / T_i >= its visits;
for a contracted flow also T_i <= PDB_i - the retry margin) and fits
`sum_i 1 / T_i <= cap` per direction -- the M-6 cap as a density, which
with harmonic periods is Kraft's inequality, so a residue class
`t = r_i (mod T_i)` on one of `cap` TRACKS exists for every flow and the
classes are pairwise disjoint (`allocate_tracks`). Spare density shortens
T_i for contracted flows, shortest PDB first. Tier 2 is the TABLE: in slot
t each track's mapped flow is placed first; a mapped slot the pattern gives
to the other direction, or the cap (a retransmission's DCI) takes, leaves
the flow OWED and it is served at the next free DCI; a mapped flow with
nothing reported frees its DCI. Freed DCIs go, in order, to owed and mapped
contracted flows, an unplanned contracted flow (increment 1), mapped
best-effort, then leftover -- contracted by soonest next mapped slot, best-
effort round-robin. A contracted visit carries what the flow reports up to
a cap-th of the slot (a message is the unit of service, never split by the
plan's r/n share). The visit clock, EDF, the early / no-share classes and
the ue_id tie-break of the prototype are gone: the maximum gap between a
flow's mapped slots is T_i, by construction, and increments 2-3 showed
that under the old order more planned visits only meant more contention
for the last robots in the order.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from scheduler.flow import FlowConfig, require_assigned_lcgs
from scheduler.interfaces import Allocation
from scheduler.link import bits_per_prb, cce_aggregation_level

from ._mac import emit_grant

__all__ = ["ConfigSched2", "FlowPlan", "allocate_tracks"]

_CONTRACT_CLASSES = ("GBR", "Delay")


def _pow2_floor(x: int) -> int:
    """The largest power of two <= x (x >= 1)."""
    return 1 << (max(1, int(x)).bit_length() - 1)


def allocate_tracks(periods: dict, cap: int, prefer: dict | None = None) -> dict:
    """Kraft's construction: `periods` maps a key to a harmonic period T (a
    power of two, in direction-slots); returns key -> (track, residue) so that
    on each of `cap` tracks the residue classes `t = r (mod T)` are pairwise
    disjoint. Flows take the coarsest period first; a free block (r, m) with
    m <= T is split into (r, 2m), (r + m, 2m) until modulus T. First-fit over
    tracks. `prefer` (the previous map) is honoured when the flow's old
    (track, residue) is still free at its period, so a flow's phase survives
    a re-solve and the max-gap bound holds across windows, not only within
    one. Whenever `sum 1/T <= cap` every key is placed (checked on 2 000
    random instances and on the deployed cell's G3 at N = 24, density 3.75
    of 4). A key that does not fit is absent; the caller counts it."""
    tracks: list[list[tuple[int, int]]] = [[(0, 1)] for _ in range(max(1, cap))]
    out: dict = {}
    prefer = prefer or {}

    def take(ti: int, r: int, m: int, T: int) -> int:
        free = tracks[ti]
        free.remove((r, m))
        while m < T:
            # keep the sibling that does NOT contain the wanted residue
            free.append((r + m, 2 * m))
            m *= 2
        return r

    for key, T in sorted(periods.items(), key=lambda kv: (kv[1], str(kv[0]))):
        placed = False
        if key in prefer:
            pti, pr = prefer[key]
            pr %= T
            if 0 <= pti < len(tracks):
                for (r, m) in tracks[pti]:
                    if m <= T and (pr - r) % m == 0:
                        # split toward pr: at each doubling keep the half holding pr
                        free = tracks[pti]
                        free.remove((r, m))
                        while m < T:
                            other = r + m if (pr - r) % (2 * m) == 0 else r
                            keep = r if other == r + m else r + m
                            free.append((other, 2 * m))
                            r, m = keep, 2 * m
                        out[key] = (pti, r)
                        placed = True
                        break
            if placed:
                continue
        for ti, free in enumerate(tracks):
            cands = [(m, r) for (r, m) in free if m <= T]
            if not cands:
                continue
            m, r = min(cands)
            out[key] = (ti, take(ti, r, m, T))
            break
    return out


@dataclass
class FlowPlan:
    """One flow's share of the current window, Tier 1's output."""
    n_visits: int              # visits owed in the window (0 = no share)
    bytes_per_visit: int
    interval_slots: int
    floor_visits: int
    contracted: bool


class ConfigSched2:
    """See the module docstring. `min_rb` is the deployed grant floor."""

    def __init__(self, min_rb: int = 5, window_ms: float = 100.0,
                 resolve_ms: float = 10.0, deadline_margin_slots: int = 6,
                 min_period_slots: int = 2) -> None:
        self.min_rb = int(min_rb)
        self.window_ms = float(window_ms)
        self.resolve_ms = float(resolve_ms)
        # Increment 5: a contracted flow's period is at most PDB - margin, the
        # margin being the DL HARQ retry gap `k1 + k2` = 6 slots of
        # sim/driver.py (CHOSEN to match the driver), so a message arriving
        # just after its mapped slot gets the next one and one retry inside
        # its PDB. `min_period_slots` bounds how far spare density may
        # shorten a period.
        self.deadline_margin_slots = int(deadline_margin_slots)
        self.min_period_slots = max(1, int(min_period_slots))
        self.counters: dict[str, int] = defaultdict(int)
        self._flows: list[FlowConfig] = []
        self._plan: dict[tuple[int, int], FlowPlan] = {}
        self._last_visit: dict[tuple[int, int], int] = {}
        # Increment 5 state, per direction: the period of every planned flow,
        # its (track, residue), the slot from which a flow is owed a missed
        # mapped visit, and the last slot placement ran (to see slips).
        self._period: dict[str, dict[tuple[int, int], int]] = {"DL": {}, "UL": {}}
        self._tracks: dict[str, dict[tuple[int, int], tuple[int, int]]] = {"DL": {}, "UL": {}}
        self._owed: dict[tuple[int, int], int] = {}
        # The table is indexed over each direction's OWN slots (the 120 UL
        # slots of a 100 ms window on DDSUU, not the 200 absolute ones): a
        # residue class over absolute slots would put two of every five UL
        # visits on a D-slot, and the first build did exactly that -- 19 684
        # pattern slips in one 10 s run, an owed backlog that snowballed
        # against the cap, and the flood robot's heartbeat at 76 of 100.
        self._dir_index: dict[str, int] = {"DL": 0, "UL": 0}
        self._cap_seen = 1
        self._flows_by_dir: dict[str, list[FlowConfig]] = {"DL": [], "UL": []}
        self._flows_by_ue_dir: dict[tuple[int, str], list[FlowConfig]] = defaultdict(list)
        self._dir_slots_per_window: dict[str, int] = {"DL": 0, "UL": 0}
        self._dir_prbslots_per_window: dict[str, float] = {"DL": 0.0, "UL": 0.0}
        self._dir_symbols: dict[str, int] = {"DL": 14, "UL": 14}
        self._window_slots = 1
        self._resolve_slots = 1
        self._prb_count = 0

    # ------------------------------------------------------------ setup

    def configure(self, flows: list[FlowConfig], slot_duration_s: float, grid: Any) -> None:
        require_assigned_lcgs(flows, "ConfigSched2")
        self._flows = list(flows)
        self._slot_s = float(slot_duration_s)
        self._grid = grid
        # Increment 1: which flows carry a contract, by key, so placement can
        # tell an unplanned contracted flow (due now) from best-effort leftover.
        self._contracted = {(f.ue_id, f.qfi): f.flow_class in _CONTRACT_CLASSES for f in flows}
        self._pdb_slots = {(f.ue_id, f.qfi): max(1, int(round(f.pdb_ms / 1000.0 / self._slot_s))) for f in flows}
        self._window_slots = max(1, int(round(self.window_ms / 1000.0 / self._slot_s)))
        self._resolve_slots = max(1, int(round(self.resolve_ms / 1000.0 / self._slot_s)))
        self._prb_count = int(grid.prb_count)
        for f in flows:
            if f.direction in self._flows_by_dir:
                self._flows_by_dir[f.direction].append(f)
                self._flows_by_ue_dir[(f.ue_id, f.direction)].append(f)
        # Two budgets per direction, both from the pattern the grid actually
        # runs -- derived, so a pattern change moves them:
        #   * VISITS: how many of a window's slots carry the direction at all.
        #     A DCI in a special slot is a whole DCI, so this is a slot COUNT.
        #   * PRBs: the direction's symbols, in units of a full slot's symbols
        #     (`_dir_symbols`, which is also what Tier 1's `se_i` is computed
        #     at). A special slot carries 6 of 14 symbols per direction on the
        #     deployed cell; the first build counted it as a full slot for
        #     BOTH directions and planned 22 % more PRB-time than the cell has.
        pat_len = len(grid.pattern)
        dl = ul = 0
        dl_sym = ul_sym = 0
        dl_sym_sum = ul_sym_sum = 0
        for k in range(pat_len):
            sg = grid.slot_grid(k)
            if sg.dl_symbols > 0:
                dl += 1
                dl_sym = max(dl_sym, int(sg.dl_symbols))
                dl_sym_sum += int(sg.dl_symbols)
            if sg.ul_symbols > 0:
                ul += 1
                ul_sym = max(ul_sym, int(sg.ul_symbols))
                ul_sym_sum += int(sg.ul_symbols)
        self._dir_slots_per_window = {"DL": max(1, self._window_slots * dl // pat_len),
                                      "UL": max(1, self._window_slots * ul // pat_len)}
        self._dir_symbols = {"DL": max(1, dl_sym), "UL": max(1, ul_sym)}
        self._dir_prbslots_per_window = {
            "DL": self._window_slots * dl_sym_sum / (pat_len * self._dir_symbols["DL"]),
            "UL": self._window_slots * ul_sym_sum / (pat_len * self._dir_symbols["UL"])}
        self._plan = {}
        self._last_visit = {}
        self._period = {"DL": {}, "UL": {}}
        self._tracks = {"DL": {}, "UL": {}}
        self._owed = {}
        self._dir_index = {"DL": 0, "UL": 0}

    def reset_ue(self, ue_id: int, scope: str, buffers: Any) -> None:
        """SchedulerContextReset: a re-joined UE owes nothing from before, and
        is owed nothing; its tracks stay until the next re-solve maps it."""
        for key in [k for k in self._last_visit if k[0] == ue_id]:
            del self._last_visit[key]
        for key in [k for k in self._owed if k[0] == ue_id]:
            del self._owed[key]

    # ------------------------------------------------------------ Tier 1

    def _resolve_tier1(self, slot: Any, buffers: Any, channel: Any) -> None:
        self.counters["t1_resolves"] += 1
        w_s = self._window_slots * self._slot_s
        # The cap the plan is made for: the largest seen, so a re-solve that
        # lands on a slot whose DCIs a retransmission took does not shrink
        # the whole window's tracks (the reduced view lowers max_sched_ues).
        self._cap_seen = max(self._cap_seen, int(slot.max_sched_ues))
        cap = self._cap_seen
        for direction, flows in self._flows_by_dir.items():
            s_dir = self._dir_slots_per_window[direction]
            visit_budget = cap * s_dir
            # PRB-slots at `_dir_symbols[direction]` symbols -- the same unit
            # `se` below is computed in, so bytes / se is comparable to it.
            prb_budget = int(self._prb_count * self._dir_prbslots_per_window[direction])
            symbols = self._dir_symbols[direction]
            rows = []
            for f in flows:
                st = buffers.state(f.ue_id, f.qfi)
                backlog = int(st.bytes_reported)
                contracted = f.flow_class in _CONTRACT_CLASSES
                if backlog <= 0 and not (contracted and f.gfbr_bps > 0):
                    continue
                snr = channel.get_reported_snr_db(f.ue_id)
                se, _ = bits_per_prb(snr, symbols=symbols)
                if se <= 0:
                    continue
                tb_max = (self._prb_count * se) // 8
                pdb_slots = max(1, int(round(f.pdb_ms / 1000.0 / self._slot_s)))
                floor_visits = int(math.ceil(self._window_slots / pdb_slots)) if contracted else 0
                floor_bytes = int(math.ceil(f.gfbr_bps * w_s / 8.0)) if (contracted and f.gfbr_bps > 0) else 0
                if contracted and f.flow_class == "Delay":
                    floor_bytes = max(floor_bytes, backlog)
                demand = max(backlog, floor_bytes)
                if f.mfbr_bps > 0:
                    demand = min(demand, max(floor_bytes, int(f.mfbr_bps * w_s / 8.0)))
                rows.append([f, contracted, floor_visits, floor_bytes, demand, se, tb_max])
            # floors first, most urgent contract first (priority, then PDB)
            rows.sort(key=lambda r: (not r[1], r[0].priority_level, r[0].pdb_ms, r[0].ue_id, r[0].qfi))
            visits_left, prb_left = visit_budget, prb_budget
            grant_bytes: dict[tuple[int, int], int] = {}
            grant_visits: dict[tuple[int, int], int] = {}
            for f, contracted, fv, fb, demand, se, tb_max in rows:
                key = (f.ue_id, f.qfi)
                need_prb = int(math.ceil(fb * 8 / se)) if fb > 0 else 0
                if fv > visits_left or need_prb > prb_left:
                    self.counters["floors_unmet"] += 1
                    fv = min(fv, visits_left)
                    need_prb = min(need_prb, prb_left)
                    fb = (need_prb * se) // 8
                grant_visits[key] = fv
                grant_bytes[key] = fb
                visits_left -= fv
                prb_left -= need_prb
            # residual PRB budget: max-min fair over demand above the floor
            residual = {(r[0].ue_id, r[0].qfi): max(0, r[4] - grant_bytes[(r[0].ue_id, r[0].qfi)])
                        for r in rows}
            se_of = {(r[0].ue_id, r[0].qfi): r[5] for r in rows}
            active = [k for k, d in residual.items() if d > 0]
            while active and prb_left > 0:
                share = prb_left / len(active)
                progressed = False
                for key in list(active):
                    can = min(residual[key], int(share * se_of[key] / 8))
                    if can <= 0:
                        active.remove(key)
                        continue
                    grant_bytes[key] += can
                    residual[key] -= can
                    prb_left -= int(math.ceil(can * 8 / se_of[key]))
                    progressed = True
                    if residual[key] <= 0:
                        active.remove(key)
                if not progressed:
                    break
            if prb_left <= 0 and any(d > 0 for d in residual.values()):
                self.counters["rate_budget_bound"] += 1
            # visits for the residual: enough that a visit never exceeds a slot
            for f, contracted, fv, fb, demand, se, tb_max in rows:
                key = (f.ue_id, f.qfi)
                r_i = grant_bytes[key]
                n_i = grant_visits[key]
                # a visit may take at most a cap-th of a slot, so `cap` due units
                # can share one slot -- otherwise four due cameras each wanting a
                # whole slot turn three of them into crumbs
                # a visit may take at most a cap-th of a slot, in PRBs FIRST and
                # bytes second, so that `cap` visits fit after each is rounded
                # up to whole PRBs (bytes-first gave 4 x 27 = 108 PRBs on a
                # 106-PRB slot: every mapped camera visit a 29 B crumb)
                per_visit_max = max(1, ((self._prb_count // max(1, cap)) * se) // 8)
                need = int(math.ceil(r_i / per_visit_max)) if per_visit_max > 0 else 0
                extra = max(0, need - n_i)
                if extra > 0:
                    take = min(extra, visits_left)
                    if take < extra:
                        self.counters["visit_budget_bound"] += 1
                    n_i += take
                    visits_left -= take
                if r_i > 0 and n_i == 0 and visits_left > 0:
                    n_i, visits_left = 1, visits_left - 1
                if n_i <= 0:
                    self._plan[key] = FlowPlan(0, 0, self._window_slots, fv, contracted)
                    continue
                self._plan[key] = FlowPlan(
                    n_visits=n_i,
                    bytes_per_visit=max(1, int(math.ceil(r_i / n_i))),
                    interval_slots=max(1, self._window_slots // n_i),
                    floor_visits=fv, contracted=contracted)
            self._assign_periods_and_tracks(direction, rows, cap)

    def _assign_periods_and_tracks(self, direction: str, rows: list, cap: int) -> None:
        """Increment 5, Tier 1's second half: a harmonic period per planned
        flow, the density fit, spare density to the tightest deadlines, and
        the Kraft track map for the coming window."""
        W = self._window_slots
        W_dir = max(1, self._dir_slots_per_window[direction])     # the table's unit
        periods: dict[tuple[int, int], int] = {}
        bound: dict[tuple[int, int], int] = {}
        for f, contracted, fv, fb, demand, se, tb_max in rows:
            key = (f.ue_id, f.qfi)
            plan = self._plan.get(key)
            if plan is None or plan.n_visits <= 0:
                continue
            T = _pow2_floor(max(1, W_dir // plan.n_visits))
            if contracted:
                # the deadline bound, converted to direction-slots
                pdb_dir = max(1, (self._pdb_slots.get(key, W) - self.deadline_margin_slots) * W_dir // W)
                dl = _pow2_floor(pdb_dir)
                T = min(T, dl)
                bound[key] = dl
            periods[key] = max(1, T)
        density = sum(1.0 / T for T in periods.values())
        # Over the cap: lengthen periods, best-effort first (the densest
        # first), then contracted flows -- their deadline bound is exceeded
        # only under overload, and that is counted.
        while density > cap and periods:
            cands = sorted(periods, key=lambda k: (self._contracted.get(k, False), -1.0 / periods[k], str(k)))
            k = cands[0]
            T = periods[k]
            if not self._contracted.get(k, False) and 2 * T > W_dir:
                density -= 1.0 / T
                del periods[k]                      # leftover only this window
                self.counters["track_dropped_best_effort"] += 1
                continue
            if self._contracted.get(k, False) and 2 * T > bound.get(k, T):
                self.counters["period_over_deadline"] += 1
            periods[k] = 2 * T
            density += 1.0 / (2 * T) - 1.0 / T
        # Spare density: shorten contracted periods, shortest PDB first.
        for k in sorted((k for k in periods if self._contracted.get(k, False)),
                        key=lambda k: (self._pdb_slots.get(k, W), str(k))):
            while periods[k] > self.min_period_slots and density + 1.0 / periods[k] <= cap:
                density += 1.0 / periods[k]
                periods[k] //= 2
        tracks = allocate_tracks(periods, cap, prefer=self._tracks.get(direction))
        if len(tracks) < len(periods):
            self.counters["track_unplaced"] += len(periods) - len(tracks)
        self._period[direction] = {k: periods[k] for k in tracks}
        self._tracks[direction] = tracks
        self.counters["tracks_mapped"] += len(tracks)
        # a flow that lost its track owes nothing from the old map
        for k in [k for k in self._owed if k in periods and k not in tracks]:
            del self._owed[k]

    # ------------------------------------------------------------ Tier 2

    def allocate(self, slot: Any, buffers: Any, channel: Any) -> list[Allocation]:
        if slot.slot_index % self._resolve_slots == 0 or not self._plan:
            self._resolve_tier1(slot, buffers, channel)
        out: list[Allocation] = []
        cap = int(slot.max_sched_ues)
        for direction, symbols in (("DL", slot.dl_symbols), ("UL", slot.ul_symbols)):
            if symbols <= 0:
                continue
            placed = self._place(slot, buffers, channel, direction)
            # The M-6 cap is applied INSIDE `_place` (it stops placing once
            # `cap` UEs hold a grant), so nothing here has to trim. Asserted
            # rather than re-applied: `cap_ues_per_slot` would silently hide
            # a regression to place-then-trim, which stamped visits for
            # grants that never left the gNB (2026-09-15, N = 24: 46 of the
            # flood robot's 94 heartbeat stamps, 70 % of all DL stamps).
            if cap > 0 and len({a.ue_id for a in placed}) > cap:
                raise AssertionError(f"ConfigSched2 placed more than {cap} UEs in slot "
                                     f"{slot.slot_index} {direction}")
            out.extend(placed)
        return out


    # ------------------------------------------------------------ Tier 2: the table

    def _next_mapped(self, direction: str, key: tuple[int, int], now: int) -> int:
        """Direction-slots until this flow's next mapped slot (0 = now, `now`
        being the direction-slot index); a large number for a flow with no
        track."""
        tr = self._tracks[direction].get(key)
        if tr is None:
            return 10 ** 9
        T = self._period[direction][key]
        return (tr[1] - now) % T

    def _rank(self, direction: str, key: tuple[int, int], now: int, mapped_now: set) -> tuple:
        """The order a slot's DCIs are given out in (lower first).

        Increment 6 (2026-09-16): ONE rule for every contracted flow with
        backlog -- **shortest PDB first**, and at equal PDB the flow mapped
        here, then one owed a missed visit (oldest first), then one with no
        plan, then one between its mapped slots -- ahead of every
        best-effort unit; best-effort mapped or owed next; best-effort
        leftover last, least recently served first. Increment 5 ranked by
        claim (mapped, owed, unplanned, mapped best-effort, leftover
        contracted, leftover best-effort) and measured two losses to that
        list: a 5 ms STOP with no plan waited behind 10 ms fleet messages
        mapped on their tracks (G2 cap 2: 1 390 -> 2 297 misses), and a
        heartbeat between its mapped slots waited behind best-effort mapped
        slots (G3 part 3 boundary 10 -> 8, G10 10 -> 8). The deadline is the
        order; the map decides where a flow is CERTAIN of a DCI, not who wins
        a free one. Mapped stays ahead of owed at equal PDB so a missed visit
        fills a free DCI rather than displacing the next slot's visit (the
        cascade of the first build, 32 992 misses)."""
        contracted = self._contracted.get(key, False)
        plan = self._plan.get(key)
        if contracted:
            pdb = self._pdb_slots.get(key, 10 ** 9)
            if key in mapped_now:
                return (0, pdb, 0, 0)
            if key in self._owed:
                return (0, pdb, 1, self._owed[key])
            if plan is None or plan.n_visits <= 0:
                self.counters["unplanned_contracted_due"] += 1
                return (0, pdb, 2, 0)
            return (0, pdb, 3, self._next_mapped(direction, key, now))
        if key in mapped_now or key in self._owed:
            return (1, self._owed.get(key, now), 0, 0)
        return (2, self._last_visit.get(key, -1), 0, 0)

    def _place(self, slot: Any, buffers: Any, channel: Any, direction: str) -> list[Allocation]:
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        tracks = self._tracks[direction]
        periods = self._period[direction]
        # `now` is this direction's own slot counter: the driver calls _place
        # only for a slot carrying the direction, so the table never maps a
        # visit onto a slot the pattern gives to the other direction.
        now = self._dir_index[direction]
        self._dir_index[direction] = now + 1
        mapped_now = {key for key, (tr, r) in tracks.items() if (now - r) % periods[key] == 0}
        # eligible flows, grouped by grant unit (UL: the UE; DL: the flow)
        units: dict[tuple[int, int], list[FlowConfig]] = {}
        for f in self._flows_by_dir[direction]:
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            unit = (f.ue_id, -1) if direction == "UL" else (f.ue_id, f.qfi)
            units.setdefault(unit, []).append(f)
        # a mapped flow with nothing reported frees its DCI; it is not owed
        for key in mapped_now:
            if buffers.state(key[0], key[1]).bytes_reported <= 0:
                self.counters["mapped_slot_empty"] += 1
        if not units:
            return []
        scored = []
        for unit, flows in units.items():
            best = min(self._rank(direction, (f.ue_id, f.qfi), now, mapped_now) for f in flows)
            scored.append((best, unit, flows))
        scored.sort(key=lambda x: (x[0], x[1]))
        prbs_left = int(slot.prb_count)
        cce_left = int(slot.pdcch_cce_budget)
        cap = int(slot.max_sched_ues)
        granted_ues: set[int] = set()
        out: list[Allocation] = []
        for rank, unit, flows in scored:
            if prbs_left <= 0:
                break
            ue_id = unit[0]
            keys = [(f.ue_id, f.qfi) for f in flows]
            promised = [k for k in keys if k in mapped_now or k in self._owed]
            # M-6 with `cap_ues_per_slot`'s semantics (distinct UEs; a later
            # flow of a UE already granted still passes). A promised flow the
            # cap turns away (a retransmission took its DCI) is owed instead.
            if cap > 0 and ue_id not in granted_ues and len(granted_ues) >= cap:
                for k in promised:
                    self._owed.setdefault(k, now)
                self.counters["cap_skipped_" + ("promised" if promised else "leftover")] += 1
                continue
            snr = channel.get_reported_snr_db(ue_id)
            se, _bler = bits_per_prb(snr, symbols=symbols)
            if se <= 0:
                continue
            cce_cost = cce_aggregation_level(snr)
            if cce_left < cce_cost:
                for k in promised:
                    self._owed.setdefault(k, now)
                continue
            per_visit_cap = max(1, ((int(slot.prb_count) // max(1, cap)) * se) // 8)   # PRBs first (see Tier 1)
            # size: what this grant is for. A PLANNED contracted flow carries
            # its plan share, an UNPLANNED one what it reports, a best-effort
            # visit its r/n share -- each bounded by a cap-th of the slot so
            # `cap` units fit. Increment 9 (2026-09-16) removed a floor of a
            # cap-th on contracted flows: increment 3 added it to stop a
            # two-visit plan halving a 300 B message, increment 2 (that plan)
            # was then reverted, and the floor only inflated afterwards --
            # the telemetry's share IS its whole message (300 B) while a
            # camera's is ~800 B and the floor handed it 1 530 B. Measured as
            # the over-driven camera served past its MFBR-capped plan (G7
            # clause 2 0.92 -> 1.08x, A-telemetry p98 31.5 -> 70.0 ms) and
            # G5's admissible fleet 7 -> 6 with its load knee at x1.0.
            planned = 0
            backlog = 0
            served: list[tuple[FlowConfig, int]] = []
            for f in flows:
                key = (f.ue_id, f.qfi)
                reported = int(buffers.state(f.ue_id, f.qfi).bytes_reported)
                backlog += reported
                if reported <= 0:
                    continue
                plan = self._plan.get(key)
                contracted = self._contracted.get(key, False)
                if contracted:
                    if plan is not None and plan.n_visits > 0:
                        want = min(reported, max(1, plan.bytes_per_visit), per_visit_cap)
                    else:
                        want = min(reported, per_visit_cap)
                elif key in mapped_now or key in self._owed:
                    want = min(reported, plan.bytes_per_visit if plan is not None and plan.n_visits > 0 else reported)
                elif rank[0] >= 2:
                    want = min(reported, plan.bytes_per_visit if plan is not None and plan.n_visits > 0 else per_visit_cap)
                else:
                    continue    # a best-effort flow riding a contracted unit's grant: the UE's LCP decides
                planned += want
                served.append((f, want))
            target = planned if planned > 0 else backlog
            if target <= 0:
                continue
            prbs_needed = (target * 8 + se - 1) // se
            prbs_used = min(prbs_left, max(self.min_rb, prbs_needed))
            tbs = min(backlog, (prbs_used * se) // 8)
            if tbs <= 0:
                continue
            prbs_left -= prbs_used
            cce_left -= cce_cost
            # book-keeping: a promised flow this grant can carry is no longer
            # owed; a grant smaller than the flow's want is a crumb and settles
            # nothing. `visits_late` counts a promised visit served more than
            # one period after the previous one.
            room = tbs
            for f, want in served:
                key = (f.ue_id, f.qfi)
                if room >= want and want > 0:
                    room -= want
                    prev = self._last_visit.get(key)
                    T = periods.get(key)
                    if prev is not None and T is not None and now - prev > 2 * T:
                        self.counters["visits_late"] += 1
                        self.counters[f"visits_late_qfi{f.qfi}"] += 1
                    self._last_visit[key] = now
                    self._owed.pop(key, None)
                    self.counters["visits_stamped"] += 1
                    if key in mapped_now:
                        self.counters["mapped_visits_served"] += 1
                else:
                    self.counters["crumb_not_counted"] += 1
                    self.counters[f"crumb_qfi{f.qfi}"] += 1
                    self.counters[f"crumb_short_bytes_qfi{f.qfi}"] += max(0, want - room)
            self.counters["grants_" + direction.lower()] += 1
            granted_ues.add(ue_id)
            out.extend(emit_grant(ue_id, direction, prbs_used, tbs, flows, buffers,
                                  cce_cost=cce_cost, snr_used_db=snr))
        # a promised flow with backlog that got no grant this slot is owed
        for key in mapped_now:
            if buffers.state(key[0], key[1]).bytes_reported > 0 and key[0] not in granted_ues:
                self._owed.setdefault(key, now)
                self.counters["mapped_visit_missed"] += 1
        return out
