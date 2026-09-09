# G1 — slide source

**Status:** ANSWERED as a stress experiment, 2026-09-09 — **and the answer
required correcting what G1 had been measuring at all.**
**Full record:** `docs/g1-stress-experiment-2026-09-09.md`, with Step 0 in
`docs/g1-step0-2026-09-09.md`.
**Artefacts:** `sweeps/g1-stress/g1_stress.json` (960 runs, stamped),
`sweeps/g1-stress/g10_remeasure_cap4.json` (270 runs).
**Checks:** suite green, `--check` re-baselined **shape-only with zero
numbers moved**, `verify_claims --check` 15 as expected / 0 not.

**The previously published G1 row is WITHDRAWN.** *"M01 p98 protected: PF
25.25 / Res 23.00 / TwoTier 87.78 ms vs 100 ms"* is a **worst-uplink-flow**
maximum scored against a **downlink** guarantee's bound, and the
`GUARANTEE-TABLE` row derived from it — *"teleop feels sticky on 7 shifts in
10 on TwoTier"* — goes with it. Nothing here inherits from either.

**In one line:** on the flow the clause is actually about, **G1 passes both
its criteria on every arm, 0 breaches of 960 runs, and TwoTier is the best
arm rather than the worst.**

---

## 1. The question, in operator terms

**Driving a robot feels immediate while the rest of the fleet works.**

- A **p98 breach** is a robot that lurches.
- A **200 ms gap** is a command that never arrives.

**Two pass criteria, not one, and they fail in opposite directions.** p98 is
a percentile of DELIVERED commands, so a scheduler that drops commands
improves it; the gap is receiver-side, so it widens around a command that
never came. Every earlier G1 row reported neither.

---

## 2. What Step 0 corrected before any number was read

**Three things, all measured rather than assumed.**

**The direction was wrong.** G1 is a downlink guarantee — cmd_vel 20 Hz on
5QI 1 DL. **No workload any guarantee is scored on carried a 5QI-1 downlink
flow.** Enumerated rather than recalled: `sim/fleet.py`'s five device
profiles, `sim/parametric.py`, `sim/scenarios/{g9,g11,g12}.py` and the six
YAML scenarios. Two YAML scenarios (2 and 5) do carry one, both `Delay` class
with **GFBR 0** — so even they would not have armed the ranking tier that
matters — and neither is a workload any guarantee is measured on.

The scored statistic landed on **uplink on 9 runs of 9**, and on TwoTier the
winner was the 5QI-2 camera — a video bearer with its own 150 ms budget — not
the telemetry. The downlink flow the clause is about sat at **2.75–4.25 ms**
and could never surface through a maximum.

**The scenario did not exist.** GT-1.1 needs a saturating 5QI-9 DL firmware
pull, and no scenario in the repo has a saturating downlink at all — the
condition the test plan's own text calls *"an idle DL link measures
nothing"*.

**And the reason TwoTier's downlink comparator is a constant was recorded
wrongly.** The observation reproduces — its DL key takes **one** value and
84 % of adjacencies are decided by declaration order. But the recorded cause
(*"the virtual queue is zero for a flow with no GBR target"*) is **refuted by
measurement**: the flooding robot has no GBR target and its coefficient
reaches 4.8e5, while the GBR command flow's stays at zero. **The virtual
queue is a SERVICE DEFICIT** — a flow that is never behind has none. What
actually reaches a command flow is `has_gbr`, a tier *above* the
coefficient, dead on every scenario this repo had and now deciding **12–13 %
of downlink adjacencies at the realistic fleet size** (11.9 % on TwoTier,
13.1 % on Reservation at N=6).

---

## 3. The experiment, and the result

| | |
|---|---|
| **axis A** | fleet size, `n_ues` 4 → 24 at committed ×1.0. **6, 7 and 12 are on the grid because they ARE the three arms' re-measured G10 boundaries** |
| **axis B** | load per robot, `committed_mult` ×0.5 → ×3.0 at **N = 6** |
| **why N = 6 for B** | it is the MINIMUM of the three boundaries, so **every arm is inside its own admissible fleet and the load axis is the only thing that moves.** G1's old 8-UE row sat above Reservation's boundary and 4 robots below PF's — the same point is overload for one arm and comfort for another |
| **the instrument** | cmd_vel, 20 Hz × 100 B, **5QI 1 DL, GBR**. **2 driven robots, FIXED**, so the axis moves load and not the statistic |
| **the load** | a saturating 5QI-9 DL firmware pull, 50 Mbps offered against a downlink that delivers ~17 |
| **grid** | 2 clause parts × 9 UE counts × 3 arms × 10 seeds × 2 caps, and 2 clause parts × 8 load levels × 3 arms × 10 seeds × 2 caps — **960 driver runs** |

**Both criteria pass on every arm at every point. 0 breaches of 960, either
criterion, and the instrument never went silent.**

| | worst in 960 runs | bound | margin |
|---|---|---|---|
| cmd_vel p98 | **9.00 ms** | 95 ms | **10.6×** |
| max | 12.00 ms | — | reported |
| command gap | **103.0 ms** | 200 ms | **1.9×** |

**p99.9 and max, from separate long-horizon passes.** At 50 s (1,000
commands per robot, 72,000 delivered) the worst tail is **4.50–5.25 ms,
18–21× inside the bound, and zero gaps reach 200 ms.**

**One correction worth carrying:** I first reported that pass as making p99.9
a percentile. It does not. The index convention is `min(n-1, int(n·p))`, so
at **any n ≤ 1000** the 99.9th index *is* the maximum — and the percentiles
are computed per flow, where a flow delivers exactly 1,000. The figures are
right; the label was not. **Re-run at 250 s — 5,000 commands per robot,
30,000 per cell — p99.9 is 4.50 ms on every arm at both caps, 21× inside the
bound, and the max separates from it for the first time (4.50 to 5.75 ms).
Zero gaps reach 200 ms in 179,977 delivered commands.**

**The gap criterion is the tight one, by a factor of five** — and its
mechanism is arithmetic: at a 50 ms cadence, 103 ms is exactly one missed
command, and the worst run delivered 199 of 200. **The bound tolerates three
consecutive losses and the worst point used one.**

**And the arm order INVERTS the withdrawn row.**

| | worst cmd_vel p98, N = 4 → 24 |
|---|---|
| **TwoTier** | **3.00 ms, flat** |
| **Reservation** | **3.00 ms, flat** |
| **PF** | 3.00 → **5.50 ms** (cap 4), 3.00 → **9.00 ms** (cap 2) |

**The QoS arms' command latency does not depend on fleet size; PF's does**,
and the narrow carrier roughly doubles PF's degradation while doing nothing
to the other two. **Six-fold offered load changes nothing on any arm.**

**Operator consequence.** On the QoS arms, adding robots or working them
harder does not make driving less responsive — the command lands within one
or two downlink opportunities at any fleet size the cell can host. On PF it
degrades gently with fleet size and still never approaches the bound. **The
old row's "teleop feels sticky on 7 shifts in 10 on TwoTier" is withdrawn:
it was an uplink statistic.**


## 4. What the rank trace says about precedence

**The registered prediction was that drive commands now take precedence.**
It holds, and the trace says by which term.

**5QI 1 is not SRB.** SRB is RRC signalling promoted onto LCG 0 through
`sched_inactive`; drive commands are protected by `priority_level` and the
GBR/PDB tiers, a different mechanism entirely. The trace reads the latter.

**`has_gbr` never demotes a driven robot.** Where a driven robot IS placed
behind the robot above it, the deciding term is `pdb_ms` — it loses to a
flow with a **tighter** deadline (5QI 82's standardised 10 ms against 5QI 1's
100 ms), which is the ordering behaving correctly rather than failing to
reach the command. Every other adjacency is a tie.

**And the tie mattered enough to control for**, because the driven robots are
UEs 1 and 2 and TwoTier's downlink order is a tie on 92 % of the adjacencies
a driven robot loses — so "commands are served first" could be position
rather than priority. That is the artefact that stopped G12's ordering being
promoted. The control is tie-break-only (`scheduler/flow.py::tie_break_term`),
not `permute_flows`, which would move the tie-break and every
first-flow-found-wins lookup at once.

**It fired and CONFIRMED.** 80 runs at cap 2, N ∈ {6, 16}, both QoS arms:
**the p98 median and worst are identical in all four pairs** under a seeded
tie-break. Position supplies none of the commands' precedence. Most controls
in this project have refuted what they were pointed at; this one did not, and
that is what makes `has_gbr` a ranking property rather than a sort artefact.

**Mean downlink rank of a driven robot** (0 = served first): **PF 1.434
(worst 8.385), Reservation 0.467, TwoTier 0.463 — and neither QoS arm ever
falls below rank 1.** That single number is the whole of the arm difference.


## 5. Deployment consequence

**Driving a robot feels immediate, and stays immediate as the floor fills
up.** A command lands in **1.5 to 9 ms** against a 95 ms budget, on every
scheduler, at every fleet size and load measured — including fleet sizes well
past the point the cell stops meeting its other guarantees.

- **Fleet size is not a teleop risk.** Flat on the QoS arms from 4 robots to
  24; 3× worse on PF and still 10× inside the bound. **Whatever bounds the
  fleet, it is not the drive path** — G10's contract clause fails at 6 to 12
  robots while G1 is 10× inside its bound at 24.
- **Working the robots harder changes nothing** — six-fold load moves the
  latency by one 0.25 ms slot.
- **Watch missed commands, not slow ones.** The gap criterion sits 1.9×
  inside its bound where latency sits 10.6× inside its, and §6 shows the two
  coming apart entirely on a bad radio.

**Not established:** robustness to link quality. The clause is robust to load
and fleet size *on this carrier*, which is what GT-1.1 asks; §6 breaks it at
0 dB.


## 6. The positive control — and the sharpest finding of the day

**A pass is information only if failure was reachable.** G1 passes
everywhere, so the radio was degraded until it broke — the one lever that
weakens the cell without touching the instrument, the bound or the scoring.

| SNR | commands (of 200) | worst p98 | worst gap | **p98 ≤ 95 ms** | **zero gaps ≥ 200 ms** |
|---|---|---|---|---|---|
| 20 → 5 dB | 200 | 1.5 – 10.0 ms | 53 – 61 ms | PASS | PASS |
| **0 dB** | **185** | **23.8 – 31.3 ms** | **698.8 ms** | **PASS** | **FAIL** |
| −3 dB | 46 – 49 | 96.3 – 98.0 ms | 2 935 ms | FAIL | FAIL |
| −6 dB | **0** | **56.3 ms** | — | FAIL | FAIL |

**At 0 dB the two criteria come apart on every arm.** The percentile stays
green *because* the 15 missing commands left the sample. In operator terms
that is a robot that did not lurch — it stopped answering for seven tenths
of a second. **A G1 row reporting only p98 would have called this cell
responsive**, which is precisely the hole the second criterion exists to
close, now measured rather than argued.

**And at −6 dB the worst-flow p98 reads 56.3 ms — a comfortable pass — for a
pair of robots one of which received ZERO commands.** The other supplied the
percentile and a worst-of-two maximum reported it. That is why G1 scores
fewer than two completions as a **failure**, where the panel's own M01 and
M03 *exclude* such a flow from their worst contests: excluding the silent
robot is how a total outage scores as the best possible value.


## 7. The caveats that travel with every number here

**Cap 2 is this carrier's faithful derivation at 55 PRB; cap 4 is the
deployment's value on half its bandwidth. Neither is the deployment's
system.** Both are run in full.

**And the horizon is 10 s, not GT-1.1's 10 minutes** — 200 commands per
driven robot per run, so a per-run p99.9 IS the maximum. The p99.9 reported
here comes from a separate 50 s pass where it is a percentile in its own
right.

---

## 8. Process notes worth carrying

- **A pass with no reachable failure is worth nothing**, and G1's passed
  everywhere. The positive control is what turned it into a result — and it
  found the failure mode the clause's second criterion exists for.
- **A check that fails on its own null control is failing on the
  instrument.** The rank-hook identity check reported every arm as
  differing, including PF, because the digest was hashing two live object
  handles whose `repr()` carries a memory address.
- **Two spawn-pool traps hit in one session, both from CLAUDE.md's own
  list:** a scratchpad probe with no `__main__` guard re-entered its own
  pool for six minutes, and `pgrep -f <script>` matched the shell running
  the check, deadlocking an `until` guard so the campaign never launched.
  Both were found by `ps`-ing PIDs, neither by reading output.
- **The cost was extrapolated from the full population before any flag
  narrowed it** — 960 runs, derived. Estimated 18 min at 16 workers; actual
  17.2.

## 9. Open external inputs

- **The 95 ms RAN PDB is a PROPOSED default** (the test plan marks it ▷),
  to be ratified with the client. Every margin here is against that number.
- **The 200 ms gap bound is likewise proposed.** It is the tighter of the
  two criteria by a factor of five, so it is the one whose ratification
  actually matters.
- **GT-1.1 specifies 10 minutes of steady state**; this runs 10 s per graded
  run with a separate 50 s pass for the tail. The full duration is a
  hardware-campaign question, not a simulator one.
