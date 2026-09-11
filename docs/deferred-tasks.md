# Deferred tasks — decided, not forgotten

**Created 2026-09-11.** Everything here was raised, costed and consciously put
off. The distinction this file exists to keep: a deferred task has a **decision
and a reason** behind it; an omission has neither, and the two look identical in
a repository six months later.

Each entry states what it is, what it costs, why it waits, and what would
re-open it.

---

## 1. G4 — resume-after-silence

**Deferred 2026-09-10.** *"After a robot goes quiet, its next message still
arrives promptly."* First-packet-after-silence p99 ≤ 300 ms for silence gaps of
1 s / 5 s / 60 s.

**Cost: ~96 min.** A p99 is only a p99 above 100 samples, so the grid is sized
by trials rather than seeds: 10 cycles per run × 10 seeds gives 100 trials per
bucket, which is 96 min at three arms. The **60 s bucket alone is 79 % of that
cost** (280 000 slots per cycle against 44 000 for the 1 s bucket).

**Why it waits:** not effective use of the time right now. The scenario builder
already exists (`sim/scenarios/g3.py::build_gt23_scenario`) and G3 deliberately
did not score G4's KPIs, so nothing is half-done.

**What re-opens it:** a decision that resume latency matters, or a cheaper
statistic than a p99. Two Step-0 findings are already recorded and should not be
re-derived — 5G-ACIA's own mobile-device table puts a robot's pause time at
**5-3600 s**, so the 1 s bucket is below anything the industry models and is a
probe of the floor's 2 s arming horizon rather than a realistic pause; and
**"time-to-steady = p98 within PDB inside 1 s" is not computable at 10 Hz**,
since 1 s holds ten messages and a p98 needs more than fifty.

## 2. The 22 stale published-claim stamps

**Deferred 2026-09-11.** Adding `M23` to `sim/scorecard.py` moved the scoped AST
hash for every artefact whose import graph reaches the scorer, so 22 claims in
`config/published_claims.yml` read STALE.

**No published number moved** — `regression_corpus.py --check` is clean, and M23
is purely additive.

**Cost: ~63 min** of faithful campaign re-runs (G2 1320 rows, G1 960, G3 576,
G10 270), each with its ORIGINAL invocation: G1 `--fixed-n 6` and caps [4, 2],
G2 `--fixed-n 12 --fixed-stop 2`, G3 `--fixed-n 6` with `--long-horizon
200000`, G10 via `g5_consolidation.py --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10
--horizon 20000`.

**Why re-running rather than annotating:** the file's own precedent for a
shape-only change is to re-run and record what changed in `code_state` (see the
`post delay_p999_ms/delay_max_ms (shape-only…)` claims). Marking them
`historical:` would pass the check by **permanently disarming** it on every
headline figure in G1, G2, G3 and G10.

**What re-opens it:** publishing anything that quotes those claims, or a second
additive scorer change — this is already the second time one has done this, and
a third makes it a structural problem rather than an incident.

## 3. The TwoTierProto write-up

**Deferred 2026-09-10.** No proto figure is registered in
`config/published_claims.yml` and no proto row appears in
`docs/GUARANTEE-RESULTS.md` or the guarantee table, so **none of the arm's
numbers is quotable** under this repo's own convention.

**Why it waits:** putting *"what a change would do"* beside *"what the product
does"* in the guarantee table before the guarantee set is complete is the
confusion `scheduler/two_tier_proto.py`'s docstring exists to prevent.

**Note the scope, corrected 2026-09-10:** the deferral is about PROMOTING
figures, never about declining to measure. **Every new guarantee campaign runs
the Proto arm alongside the faithful ones.**

**What re-opens it:** all guarantees rebuilt. See §6 for where that stands.

**One finding to carry forward when it opens, because it is about the DEPLOYED
scheduler rather than the divergence:** on the faithful arm G7 runs the uplink
band at **45.6 % utilisation while a protected asset starves**.

## 4. E3 — a deadline term in uplink grant sizing

**Registered, never implemented.** The flag exists and RAISES rather than
silently returning the faithful arm's numbers.

**Why it waits:** it was inert behind the ungated reserve, and the sweep then
showed sizing is not the binding constraint — once the reserve is bounded,
ordinary grants already run at ~54 of 55 PRB. **Rank order binds, not grant
size.**

**What re-opens it:** evidence that a grant is too small for a reason other than
the reserve.

## 5. GT-2.1 — heartbeat vs the robot's own camera

**Deferred 2026-09-09**, with the plan's own reason: a failure there is fixed
UE-side (`prioritisedBitRate` configuration) rather than in the scheduler, so it
discriminates the arms weakly. The builder exists and is tested; it was never
run as a scored pass.

**What re-opens it:** the same fault is already documented on hardware — one
flow taking ~85 MB while two siblings on the same UE got ~10 MB and ~4 bytes —
so a UE-side investigation would have a real target.

## 6. Is the per-slot UE cap applied before or after allocation in the C?

**Open, and NOT claimed either way.** `scheduler/link.py::cap_ues_per_slot`
truncates to the first `max_sched_ues` UEs **after** `_allocate_direction` has
decremented `prbs_left`, so band handed to the fifth-ranked candidate and beyond
is discarded with its grant. Measured on the faithful port at cap 4: **0.7 % of
allocated UL PRB discarded at N = 4, 36.7 % at N = 8, 65.2 % at N = 16.**

That is the most likely explanation for G7's 45.6 % uplink utilisation, and if
the C applies the cap BEFORE the search then this is a porting defect rather
than faithful behaviour.

**Why it waits:** `max_sched_ues` does not appear anywhere in the vendored
`oai-branches/` subset, so the port's own note that the deployed schedulers
"apply the limit before any CCE search and pass it into the scheduler" is
**unverified**. Settling it needs the real call site in the full OAI checkout,
not the convenience copy.

**What re-opens it:** access to the full checkout, or any decision that turns on
uplink utilisation.

---

## Guarantee status, as of 2026-09-11

| rebuilt as a stress experiment | G1, G2, G3, G5, G9, G12 |
|---|---|
| **deferred** | **G4** (§1) |
| **runners only, used as regression checks** | G7, G10 |
| **not started** | G6, G8, G11 |

**The standing rule for regression:** at guarantee *n*, the scheduler is scored
against **G1 through G*n*, minus anything deferred**. At n = 5 that is G1, G2,
G3 and G5.
