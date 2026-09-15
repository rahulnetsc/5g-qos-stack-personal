# ConfigSched first measurement -- expectations, registered before the artefact is read

Written 2026-09-15 17:05, while `g3_probe.json` (ConfigSched, G3 part A, fleet
axis 4..24, cap 4, seeds 0..2, deployed cell) was still running. The paired
control is the campaign's `sweeps/cell-2026-09-15/aligned/g3.json`
(PF / Reservation / TwoTier / ProtoRRageD2, same seeds 0..9, seeds 0..2 pair).

Nothing here is a registered claim (`docs/config-scheduler-handoff.md` §8b);
the point is to be scorable afterwards, hits and misses both.

E1  **Telemetry part 1 (max gap <= 500 ms) passes on every seed at every fleet
    size up to and including 16.** Mechanism: no rank -- a due visit is placed
    before any backlog, so the camera flood cannot demote the heartbeat.
    Would be falsified by: any `part1_pass < n_seeds` at N <= 16.

E2  **The strict form (`part1s_pass`, head and tail included) is NOT fully
    fixed.** The head silence is the SR -> grant -> BSR path, which is
    eligibility, and the arm sees the same BSR view as every other arm. So
    `head_worst_ms` on ConfigSched is within 20 % of TwoTier's on the same
    seeds. Would be falsified by: ConfigSched's head being materially shorter
    (that would mean the arm reaches something it is not supposed to).

E3  **At N = 24 the camera floors do not fit and `floors_unmet > 0`; telemetry
    still passes part 1** (floors are placed in priority order, telemetry's
    5QI ranks first). Would be falsified by a telemetry failure at N = 24 with
    the camera floors reported unmet -- that would mean priority order is not
    what protects it.

E4  **Part 3 (p98 <= 95 ms) is no better than TwoTier's**: the visit interval
    the floor implies is one visit per 100 ms window, so a message can wait
    up to a full interval; the residual buys more visits only where PRBs are
    left. Would be falsified by ConfigSched's p98 passing where every other
    arm fails at N >= 12.

E5  **Camera throughput is lower than PF's at N <= 8** (max-min residual over
    demand capped at MFBR, vs PF's rate-proportional share on a good link),
    within 10 % of TwoTier's.

Scoring rule: a miss is recorded as a miss with the number beside it; no
expectation is edited after the artefact is read.
