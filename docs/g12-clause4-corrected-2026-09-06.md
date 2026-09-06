# G12 clause 4 — the 0/20 was an instrument, and the corrected result inverts it

**2026-09-06.** *"When the cell is genuinely overloaded, degradation follows
the safety order"* — clause 4: **never starve 5QI 1 (telemetry/commands)
while any lower class still has throughput** (test plan L106, verbatim).

**Previously reported: 0/20 on all three arms. That was a defective
predicate, and the corrected result is the opposite of what it said.**

---

## 1. The predicate could not report success

Clause 4 is a **conjunction**: telemetry starved **while** a lower class
still has throughput. The first predicate tested the second half as
`bg_bps > 0`.

**Measured across all 480 ramp points: `bg_bps` is NEVER exactly 0.** So the
pass branch was reachable only via "telemetry never starves", which also
never happens at a ramp that runs to ×8 of committed load. **The predicate
could not report success** — the mirror of the C1 vacuity, where a predicate
could not report failure.

**And it merged two different verdicts.** At the points where telemetry is
floored:

| arm | background throughput at the starved points | as % of its own 50 Mbps offer |
|---|---|---|
| **PF** | **8.63 Mbps** (median; min 8.09, max 12.25) | **17 %** |
| Reservation | **0.0031 Mbps** — 3.1 kbps | 0.006 % |
| TwoTier | **0.0040 Mbps** — 4.0 kbps | 0.008 % |

**A ~2,800× separation**, scored identically by `bg_bps > 0`.

## 2. Three verdicts, because the clause has three states

| verdict | meaning |
|---|---|
| **VIOLATION** | telemetry starved **while background is meaningfully alive** — what clause 4 prohibits |
| **PREMISE FAILS** | telemetry starved **and background also dead** — the cell is exhausted; clause 4 says nothing about this |
| **PASS** | telemetry never starved |

**The floor for "still has throughput" is NOT stated in the test plan.** That
is a specification gap and is recorded as one. **It does not matter where the
floor goes**, and that was measured rather than assumed:

| τ (Mbps) | PF | Reservation | TwoTier |
|---|---|---|---|
| 0.01 | **20 viol** | 0 viol / 20 premise | 7 viol / 13 premise |
| 0.1 | **20 viol** | 0 viol / 20 premise | 5 viol / 15 premise |
| **1.0** | **20 viol** | **0 viol / 20 premise** | **0 viol / 20 premise** |
| 5.0 | **20 viol** | 0 viol / 20 premise | 0 viol / 20 premise |
| 8.0 | **20 viol** | 0 viol / 20 premise | 0 viol / 20 premise |

**PF is 20/20 VIOLATION at every threshold from 0 to 8 Mbps.** Reservation is
0/20 at any τ ≥ 0.01. TwoTier is intermediate and clean by τ = 1 Mbps.
Reported at **τ = 1 Mbps** (2 % of the background's own offer).

## 3. The corrected result

| arm | clause 4 | violations | premise fails | pass |
|---|---|---|---|---|
| **PF** | **FAILS 20/20** | **20** | 0 | 0 |
| **Reservation** | **holds, 20/20** | **0** | 20 | 0 |
| **TwoTier** | **holds, 20/20** | **0** | 20 | 0 |

**It is not "all three schedulers starve telemetry under overload". It is PF
that sacrifices telemetry to background traffic, and the two QoS arms that do
not.** The previous reading had this exactly backwards.

## 4. The mechanism, read from code

**PF's inter-UE rank is `bits_per_rb / r_avg`** (`sim/baselines/pf.py:77`),
and **`grep` finds zero occurrences of `priority_level`, `has_gbr`, `pdb_ms`
or `flow_class` anywhere in that file.** PF is structurally QoS-blind: a 5QI-9
background flow with a good channel outranks a 5QI-1 telemetry flow with a
worse one. Under overload it therefore keeps serving background *at 17 % of a
50 Mbps flood* while telemetry dies. Confirmed independently in the rank
trace: PF's decisive term is `-metric` on **100 %** of adjacencies, i.e. one
scalar with no tiers above it.

**Both QoS arms rank on QoS class first** — TwoTier's DL key is
`(has_gbr, pdb_ms, -coef)` (`scheduler/two_tier.py:856`), Reservation's UL
ranking is a four-tier `has_gbr`/`pdb_ms` sort. Under overload they starve the
contract-less background **first**, which is the safety order clause 4 exists
to require. Telemetry dies only once the cell has nothing left to give — the
premise-fails state.

**So clause 4 measures exactly what it was written to measure, and the QoS
arms pass it for the reason they were built.**

## 5. What this does and does not license

**Does not license "TwoTier passes G12".** The ordering clause (first-violation
order 9 → 4 → 2) remains **not established** — the permutation control still
flips it, and it is not observable inside the ramp G12 specifies.

**Does not license a PF-vs-QoS headline on this alone.** The ramp runs to ×8
of committed load; at that point every arm's telemetry is floored. What
separates them is *what else was still being served when it happened*.

**Does license retracting the previous 0/20.** It was an artefact of a
predicate that could not pass, and it is corrected in the scorecard, which now
reports the three-way split with its threshold sensitivity.
