# Forward plan, agreed 2026-09-14 — configured grants first, then the configuration scheduler

**Status:** agreed sequence, nothing built. Both items are **labelled
divergences** beside the faithful ports (`two_tier_proto.py`'s docstring
rule): they say what a change would do, never what the product does. The
baseline they are measured against is `docs/results-aligned-2026-09-14.md`
(ten guarantees, four arms, TDD-aligned retries).

## 0. Why this order

The aligned results split by direction. On the uplink every failure traced
— cold-start lock-out, crumb resets of the deadline clock, BSR desync, the
300 ms visit tail, the per-slot DCI cap — is a **dynamic-grant** pathology
on **small, periodic, delay-critical** flows. Configured grants remove all
five for those flows structurally (no SR, no BSR, no DCI, no ranking to
lose); the test plan's own §12 says so. Doing CG first changes what a new
Tier-2 has left to order, so the scheduler design is written *after* the
CG measurement, not before. On the downlink the two-tier deadline tier is
what wins G2; neither item touches it.

## 1. Configured grants — Type 2, as an arm on every scheduler

### 1.1 What the standard fixes and what is vendor
Parameters (periodicity, offset, HARQ processes, `configuredGrantTimer`,
`repK`) are RRC in both types — TS 38.331 `ConfiguredGrantConfig`. Type 2
adds activation / release by DCI scrambled with CS-RNTI, carrying the
time/frequency allocation and MCS (TS 38.214 §6.1.2.3; DCI 0_1 fields
TS 38.212 §7.3.1.1.2); the UE confirms with the CG-confirmation MAC CE
(TS 38.321 §6.1.3.7 / §6.1.3.31, which the vendored gNB already parses).
On each occasion the UE transmits if a mapped LCH has data and nothing
otherwise (the PRBs are lost — CG's cost). **Which UEs, which LCHs, what
period and size, when to activate and release** is the vendor decision.

### 1.2 The UE-side restriction is part of the design, not an assumption
An LCH is mapped to a CG through the LCP restrictions of TS 38.321
§5.4.3.1.2 — `allowedCG-List` for Type 2 (`configuredGrantType1Allowed`
is Type 1 only). **The vendored OAI UE (`nr_ue_scheduler.c` @ `63f3fb5`)
implements no LCP mapping restriction** — its SR path says
`// LCP mapping restrictions — TODO not implemented`, and `nr_ue_get_sdu`
fills any grant by priority and Bj. So an OAI UE given a CG multiplexes
every LCH into it. The simulator models the restriction as an **explicit
switch** and measures both: enforced (COTS / patched UE) and not enforced
(OAI UE today). The port-back therefore has two halves — gNB CG Type 2 and
a UE-side `allowedCG-List` check in `nr_ue_get_sdu` — and the second is not
optional.

### 1.3 The allocator (the vendor part, gNB-observable only)
Detect a periodic LCH from regular-BSR trigger intervals and BSR levels
(period, size, phase); activate a CG with period from the 38.331 set, TB =
observed size + headers + margin, offset = observed phase; resize via DCI;
release after N unused occasions. A small state machine with its own tests:
does it detect telemetry and *not* the Poisson filler; does it decline the
camera (a 4 Mbps variable-frame source wastes CG PRBs). Cost at the
numbers here: 300 B / 100 ms per robot ≈ 2 PRB every 400 slots ≈ 0.2 % of
the band per robot.

### 1.4 Where it lives in the simulator
`sim/pre_sched.py::Occupancy` was built as "the ONE map HARQ retx, RA and
(Build 2) CG all add to". CG occasions enter it before dynamic scheduling,
consume **no** cap slot (no DCI), and retransmit through the existing
TDD-aligned HARQ path with a dynamic grant. CG-served data bypasses SR/BSR
in `sim/ul_access.py` / `sim/bsr.py` for the mapped LCH only. Every
scheduler sees the reduced slot, so the arm can be measured on all four —
labelled, since the deployed C has no CG.

### 1.5 Measurement plan — DONE 2026-09-14, results in `docs/results-cg-2026-09-14.md`
Built as `sim/configured_grant.py` (commit `b0b0cc7`) and measured on G3,
G5, G7 and G10, both restriction settings, all four arms. Headline:
restricted CG takes G3 to 10/10 at every fleet size on every arm and fixes
TwoTier's G7 clause 1; unrestricted CG fixes silences but not latency (G3
boundary 12–14, not 24, on the faithful arms) and costs PF at small fleets
— the UE-side `allowedCG-List` half is worth 12 robots of boundary. CG
does not reach the video guarantees, except that the cell-edge robot's own
telemetry now survives on every arm. The plan below is what was run.
G3, G5, G7, G10 first (the UL failures), both restriction settings, all
four arms, 10 seeds, the aligned model — same runners, one flag. Then G4,
G6, G9. Register expectations before running; the one that matters: does
the cold-start lock-out become structurally impossible for the mapped LCH.
Counters: occasions offered / used / wasted PRB / LCH bytes on CG vs
dynamic.

### 1.6 Decisions and what is still open
**DECIDED 2026-09-14 — "product + CG": every arm, the faithful ports
included, is measured with configured grants.** The CG machinery is a MAC
feature that lives in `sim/` ahead of `scheduler.allocate()`, not in any
scheduler, so all four arms take it through one flag. A faithful arm with
CG on is **labelled `+CG`** everywhere it is reported (arm name, artefact
`arm` column, tables) and is a divergence from the deployed C, which has no
CG — the port stays the port. Recorded in `README.md` §8 and CLAUDE.md.

Still open: the μ = 2 periodicity set from 38.331 is transcribed in
`sim/configured_grant.py` (never recalled); what the allocator does with
the flood robot's telemetry (the one G3 miss no ranking reaches) is a
measurement, not a design choice.

## 2. The configuration-based scheduler — written after §1's measurement

The handoff (`docs/config-scheduler-handoff.md`, with the 2026-09-14
addendum) stands, reframed on three points the RRageD2 result settled:

1. **Tier-1's leverage on UL outcomes is sizing, not ranking**; the winning
   arm discards the composite. Decide the Tier-2 rule first, from data:
   deadlines belong in placement.
2. **Tier-1 solves for `(r_i, n_i)` — rate and visits per window** — under
   laminar families (PRB per direction, visits per direction ≤ cap × W,
   per-flow boxes from GFBR / PDB / frame period / MFBR / demand) and one
   per-flow coupling `r_i ≤ n_i · TB_max,i`. Separable concave utility,
   greedy-exact on the laminar part; the M-6 cap becomes a linear visit
   budget over a window, so no Dantzig–Wolfe. PDCCH's indicator is real
   and does not bind.
3. **Tier-2 = placement**: EDF on next-due visit with `bytes_per_visit`
   sizing, plus the proto lessons (every-slot ordering; reserve bounded by
   what the cap keeps; a crumb must not stamp the clock; a best-effort
   bearer casts no urgency vote). Two candidates to measure:
   deficit-weighted age round-robin, and EDF over per-flow deadlines.

Horizon: receding — re-solve every 10 ms over a 100 ms look-ahead with
per-flow deficit carried forward (the window cannot be shorter than the
longest period it reasons about; BSR-derived demand is the other limit).
Every constraint gets a counter saying whether it bound in a window.

**Standards inputs surveyed 2026-09-14** (`docs/standards-survey-beyond-cg-2026-09-14.md`):
TSCAI / UE traffic info replace the CG period detector; multi-slot CG with
UTO-UCI (Rel-18) is the CG for video; the Delay Status Report (Rel-18) and
PDU-set deadlines (PSDB) are Tier-2 inputs; per-LCH SR configurations
(Rel-15) are the cheapest next measurement; DL SPS is the only lever on
G2's DCI count. **Re-scoped 2026-09-15 to the Rel-16 baseline**
(`docs/rel16-baseline-2026-09-15.md` §4.3): multi-slot CG, the Delay Status
Report and PDU-set deadlines are out on the UE side; the camera CG's
Rel-16 form is several staggered configurations with dynamic top-up, and
Tier-2's uplink deadline stays the LCG-clock inference.

## 3. Still owed before either can be promoted
G8 needs a scenario, a per-role statistic and a defined load level. The
22 stale claim stamps are now every stamp (the driver is in every scope);
registration restarts from the aligned model once G8 exists. Held-out
seeds under the aligned model. Reservation's edit list (R1–R4) stays
unbuilt, so Proto-vs-Reservation compares an improved arm with an
unimproved one.
