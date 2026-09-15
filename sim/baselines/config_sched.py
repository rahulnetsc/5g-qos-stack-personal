"""Configuration-based scheduler -- the labelled divergence arm of
`docs/config-scheduler-handoff.md` in its section-8a form. PROTOTYPE,
2026-09-15. Arm name `ConfigSched`. It says what a redesign would do; it is
not a port of anything, and the port (`scheduler/two_tier.py`) is untouched.

WHAT EACH LEVEL SOLVES (handoff section 8, step 1)

Tier 1 -- every `resolve_ms` (10 ms), over a receding window of `window_ms`
(100 ms), per direction, for every flow with a contract or a backlog:

    variables   r_i  bytes this window,   n_i  visits this window
    floors      n_i >= ceil(W / T_i)        a visit at least every T_i = PDB_i
                                            (the deadline in its STRONG,
                                            visit-interval form -- section 8a)
                r_i >= GFBR_i * W           the rate contract (GBR flows)
                r_i >= backlog_i            what a Delay-class flow has queued
    budgets     sum_i n_i <= cap * S_dir    the M-6 cap over the window's
                                            S_dir slots carrying this
                                            direction -- LINEAR here, so no
                                            Dantzig-Wolfe is needed
                sum_i r_i * 8 / se_i <= PRB * S_dir   PRB-slots, se_i the
                                            bits per PRB at the CQI-visible SNR
    coupling    r_i <= n_i * TB_max,i       a visit carries at most a full slot
    objective   floors first, in priority order; the residual PRB budget by
                max-min fairness over demand (a separable concave utility on
                a laminar family: greedy is exact, handoff section 2)

Every constraint carries a counter saying whether it bound in a window
(`visit_budget_bound`, `rate_budget_bound`, `floors_unmet`).

Tier 2 -- every slot, PLACEMENT (handoff section 5: the value is in the
deadline constraints, and they are enforced here, not in a rank):

    each flow owes a visit every `interval_i = W / n_i` slots, sized at
    `bytes_per_visit_i = r_i / n_i`; the next due slot is
    `last_visit_i + interval_i`; the slot serves eligible flows in EARLIEST-
    DUE order (EDF on the next due visit), contracted before best-effort,
    then fills leftover capacity work-conservingly in the same order.
    An uplink grant is per UE (the UE's own LCP splits it, TS 38.321
    sec 5.4.3.1): the UE is due when its earliest flow is, sized for the sum
    of its due flows' bytes_per_visit. A grant that carries less than the
    visit's size (a crumb) does NOT stamp the visit (`crumb_not_counted`) --
    the C3 lesson: a crumb must not reset the clock. A visit served more than
    one interval late is `visits_late`. The M-6 per-slot UE cap is applied
    DURING placement: once `cap` UEs hold a grant, every further unit is
    skipped (`cap_skipped_<dir>_due` / `_notdue`) and its clock untouched.
    The first build placed past the cap and let `cap_ues_per_slot` trim the
    list afterwards, so a visit was stamped for a grant that was never sent
    -- measured at N = 24 as 46 of the flood robot's 94 heartbeat stamps.

WHAT IT DOES NOT DO (deliberate, for the prototype): no deficit carried
across windows (the receding backlog is the memory); no per-role group
budgets; no MFBR ceiling beyond capping demand at MFBR * W; UL service
attributed to the UE's due flows in planned order because the gNB cannot
see the UE's split (README section 7). Eligibility is the BSR-visible view
exactly as every other arm reads it, so the cold-start lock-out that lives
in the SR/BSR path is NOT this arm's to fix (configured grants are) -- what
this arm removes is the RANK: a due flow with a report cannot be outvoted.

Must not import `sim.driver` or `sim.config`; reads the `scheduler`
package's views only.
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

__all__ = ["ConfigSched", "FlowPlan"]

_CONTRACT_CLASSES = ("GBR", "Delay")


@dataclass
class FlowPlan:
    """One flow's share of the current window, Tier 1's output."""
    n_visits: int              # visits owed in the window (0 = no share)
    bytes_per_visit: int
    interval_slots: int
    floor_visits: int
    contracted: bool


class ConfigSched:
    """See the module docstring. `min_rb` is the deployed grant floor."""

    def __init__(self, min_rb: int = 5, window_ms: float = 100.0,
                 resolve_ms: float = 10.0) -> None:
        self.min_rb = int(min_rb)
        self.window_ms = float(window_ms)
        self.resolve_ms = float(resolve_ms)
        self.counters: dict[str, int] = defaultdict(int)
        self._flows: list[FlowConfig] = []
        self._plan: dict[tuple[int, int], FlowPlan] = {}
        self._last_visit: dict[tuple[int, int], int] = {}
        self._flows_by_dir: dict[str, list[FlowConfig]] = {"DL": [], "UL": []}
        self._flows_by_ue_dir: dict[tuple[int, str], list[FlowConfig]] = defaultdict(list)
        self._dir_slots_per_window: dict[str, int] = {"DL": 0, "UL": 0}
        self._dir_symbols: dict[str, int] = {"DL": 14, "UL": 14}
        self._window_slots = 1
        self._resolve_slots = 1
        self._prb_count = 0

    # ------------------------------------------------------------ setup

    def configure(self, flows: list[FlowConfig], slot_duration_s: float, grid: Any) -> None:
        require_assigned_lcgs(flows, "ConfigSched")
        self._flows = list(flows)
        self._slot_s = float(slot_duration_s)
        self._grid = grid
        self._window_slots = max(1, int(round(self.window_ms / 1000.0 / self._slot_s)))
        self._resolve_slots = max(1, int(round(self.resolve_ms / 1000.0 / self._slot_s)))
        self._prb_count = int(grid.prb_count)
        for f in flows:
            if f.direction in self._flows_by_dir:
                self._flows_by_dir[f.direction].append(f)
                self._flows_by_ue_dir[(f.ue_id, f.direction)].append(f)
        # How many of a window's slots carry each direction, from the pattern
        # the grid actually runs -- derived, so a pattern change moves it.
        pat_len = len(grid.pattern)
        dl = ul = 0
        dl_sym = ul_sym = 0
        for k in range(pat_len):
            sg = grid.slot_grid(k)
            if sg.dl_symbols > 0:
                dl += 1
                dl_sym = max(dl_sym, int(sg.dl_symbols))
            if sg.ul_symbols > 0:
                ul += 1
                ul_sym = max(ul_sym, int(sg.ul_symbols))
        self._dir_slots_per_window = {"DL": max(1, self._window_slots * dl // pat_len),
                                      "UL": max(1, self._window_slots * ul // pat_len)}
        self._dir_symbols = {"DL": max(1, dl_sym), "UL": max(1, ul_sym)}
        self._plan = {}
        self._last_visit = {}

    def reset_ue(self, ue_id: int, scope: str, buffers: Any) -> None:
        """SchedulerContextReset: a re-joined UE owes nothing from before."""
        for key in [k for k in self._last_visit if k[0] == ue_id]:
            del self._last_visit[key]

    # ------------------------------------------------------------ Tier 1

    def _resolve_tier1(self, slot: Any, buffers: Any, channel: Any) -> None:
        self.counters["t1_resolves"] += 1
        w_s = self._window_slots * self._slot_s
        for direction, flows in self._flows_by_dir.items():
            s_dir = self._dir_slots_per_window[direction]
            visit_budget = int(slot.max_sched_ues) * s_dir
            prb_budget = self._prb_count * s_dir            # PRB-slots
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
                per_visit_max = max(1, tb_max // max(1, int(slot.max_sched_ues)))
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
                raise AssertionError(f"ConfigSched placed more than {cap} UEs in slot "
                                     f"{slot.slot_index} {direction}")
            out.extend(placed)
        return out

    def _due_key(self, key: tuple[int, int], now: int) -> tuple[int, int, int, int]:
        """(due class, due slot, contracted rank, interval): units with a visit
        due now come first, earliest due first, a contracted flow ahead of a
        best-effort one at the same due slot and the tighter interval ahead
        of the looser; then units not yet due, earliest upcoming first (an
        early visit); flows with no share this window last (leftover only).
        A flow never visited is due now."""
        plan = self._plan.get(key)
        if plan is None or plan.n_visits <= 0:
            return (2, now, 1, 10 ** 9)
        last = self._last_visit.get(key)
        due = now if last is None else last + plan.interval_slots
        return (0 if due <= now else 1, due, 0 if plan.contracted else 1, plan.interval_slots)

    def _place(self, slot: Any, buffers: Any, channel: Any, direction: str) -> list[Allocation]:
        now = int(slot.slot_index)
        symbols = slot.dl_symbols if direction == "DL" else slot.ul_symbols
        # eligible flows, grouped by grant unit (UL: the UE; DL: the flow)
        units: dict[tuple[int, int], list[FlowConfig]] = {}
        for f in self._flows_by_dir[direction]:
            if buffers.state(f.ue_id, f.qfi).bytes_reported <= 0:
                continue
            unit = (f.ue_id, -1) if direction == "UL" else (f.ue_id, f.qfi)
            units.setdefault(unit, []).append(f)
        if not units:
            return []
        scored = []
        for unit, flows in units.items():
            best = min(self._due_key((f.ue_id, f.qfi), now) for f in flows)
            scored.append((best, unit, flows))
        scored.sort(key=lambda x: (x[0], x[1]))
        prbs_left = int(slot.prb_count)
        cce_left = int(slot.pdcch_cce_budget)
        cap = int(slot.max_sched_ues)
        granted_ues: set[int] = set()
        out: list[Allocation] = []
        for (cls, _due, _c, _iv), unit, flows in scored:
            if prbs_left <= 0:
                break
            ue_id = unit[0]
            # M-6, with `cap_ues_per_slot`'s exact semantics (distinct UEs; a
            # later flow of a UE already granted still passes): a UE that
            # would need a DCI the slot cannot issue is not placed at all,
            # so its visit clock is not stamped for a grant that is never
            # sent. Counted per kind so a run shows how often the cap bound.
            if cap > 0 and ue_id not in granted_ues and len(granted_ues) >= cap:
                self.counters[f"cap_skipped_{direction.lower()}_{'due' if cls == 0 else 'notdue'}"] += 1
                continue
            snr = channel.get_reported_snr_db(ue_id)
            se, _bler = bits_per_prb(snr, symbols=symbols)
            if se <= 0:
                continue
            cce_cost = cce_aggregation_level(snr)
            if cce_left < cce_cost:
                continue
            # size: the planned visits of this unit's flows (the due ones for a
            # due unit; every planned one for an early visit); a unit with no
            # share this window gets its backlog from whatever is left
            planned = 0
            backlog = 0
            visits: list[tuple[FlowConfig, FlowPlan, int]] = []
            for f in flows:
                key = (f.ue_id, f.qfi)
                reported = int(buffers.state(f.ue_id, f.qfi).bytes_reported)
                backlog += reported
                plan = self._plan.get(key)
                if plan is None or plan.n_visits <= 0 or reported <= 0:
                    continue
                k = self._due_key(key, now)
                if cls == 0 and k[0] != 0:
                    continue            # a due unit serves only its due flows
                want = min(plan.bytes_per_visit, reported)
                planned += want
                visits.append((f, plan, want))
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
            # stamp the visits this grant can honour, in planned order; a
            # grant smaller than the visit is a crumb and stamps nothing
            room = tbs
            for f, plan, want in visits:
                key = (f.ue_id, f.qfi)
                if room >= want and want > 0:
                    last = self._last_visit.get(key)
                    if last is not None and now - (last + plan.interval_slots) > plan.interval_slots:
                        self.counters["visits_late"] += 1
                        self.counters[f"visits_late_qfi{f.qfi}"] += 1
                    self._last_visit[key] = now
                    room -= want
                    self.counters["visits_stamped"] += 1
                else:
                    self.counters["crumb_not_counted"] += 1
            self.counters["grants_" + direction.lower()] += 1
            granted_ues.add(ue_id)
            out.extend(emit_grant(ue_id, direction, prbs_used, tbs, flows, buffers,
                                  cce_cost=cce_cost, snr_used_db=snr))
        return out
