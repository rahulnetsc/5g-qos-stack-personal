# Product + CG — configured grants (Type 2) on all four schedulers, measured 2026-09-14

**Every number here comes from the artefacts under `sweeps/cg-2026-09-14/`
(produced 2026-09-14, code `b0b0cc7`, TDD-aligned retries) and their
no-CG baseline under `sweeps/g3-proto/rrage-2026-09-14/aligned/` (same
day, same model — CG off is byte-identical, `regression_corpus --check`
clean).** Tables regenerate from `sweeps/cg-2026-09-14/report_tables_cg.py`.
Companion to `docs/results-aligned-2026-09-14.md`, which holds the
no-CG rows in full and the experiment descriptions; this file reports only
what CG changes.

## 0. What was measured

- **The feature:** `sim/configured_grant.py` — Type 2 configured grants as
  a MAC feature ahead of every scheduler (TS 38.321 §5.8.2, 38.214 §6.1.2.3,
  38.331 `ConfiguredGrantConfig`), with a vendor policy stated in the
  module docstring: eligible = a delay-critical uplink bearer whose message
  fits `max_message_bytes` (GBR by contract, Delay class sized from the
  gNB's first report); period = largest allowed periodicity under half the
  PDB, pattern-aligned (160 slots = 40 ms at μ = 2); activation on the first
  report (a CS-RNTI DCI); resize on MCS moves or observed backlog above the
  TB; release only when the LCG goes quiet.
- **Three settings per arm**, and the setting is in the arm's name:
  none · **`+CG`** (restricted — `allowedCG-List` honoured, a COTS or
  patched UE) · **`+CGu`** (unrestricted — the OAI UE today, which
  implements no LCP mapping restriction and therefore multiplexes every
  channel into the CG and suppresses SR for all of them).
- **"Product + CG"**: the faithful ports carry CG too. `Reservation+CG`
  and `TwoTier+CG` are divergences from the deployed C, which has no CG;
  they say what adding CG to the product would do, never what it does.
- Everything else as in the baseline: cap 4, RA + SRB, `cqi_delay_slots` 8,
  10 seeds per point, seed-base 0, 23 workers.

## 1. G3 — liveness

`scripts/g3_stress.py --parts A`, 400 runs per setting (4 arms × 9 fleet
sizes × 10 seeds).

**All four parts, passes of 10; boundary = last N at 10/10**

| arm | N=8 | 10 | 12 | 14 | 16 | 24 | boundary | campaign silences ≥ 2 s |
|---|---|---|---|---|---|---|---|---|
| PF | 10 | 10 | 10 | 10 | 10 | 10 | 24 | 0 |
| PF+CG | 10 | 10 | 10 | 10 | 10 | 10 | 24 | 0 |
| PF+CGu | 10 | 10 | 10 | 10 | 10 | 10 | 24 | 0 |
| Reservation | 6 | 4 | 3 | 0 | 0 | 0 | 6 | 10 |
| **Reservation+CG** | 10 | 10 | 10 | 10 | 10 | 10 | **24** | **0** |
| Reservation+CGu | 10 | 10 | 10 | 10 | 6 | 9 | 14 | 0 |
| TwoTier | 7 | 4 | 0 | 0 | 1 | 1 | 7 | 25 |
| **TwoTier+CG** | 10 | 10 | 10 | 10 | 10 | 10 | **24** | **0** |
| TwoTier+CGu | 10 | 10 | 10 | 8 | 10 | 6 | 12 | 0 |
| ProtoRRageD2 | 10 | 10 | 10 | 10 | 9 | 4 | 14 | 0 |
| ProtoRRageD2+CG | 10 | 10 | 10 | 10 | 10 | 10 | **24** | 0 |
| ProtoRRageD2+CGu | 10 | 10 | 10 | 10 | 10 | 10 | 24 | 0 |

**Telemetry p98, median (ms; bound 95)**

| arm | N=4 | 8 | 12 | 16 | 24 |
|---|---|---|---|---|---|
| PF · +CG · +CGu | 7.0 · 5.2 · 21.5 | 11.6 · 5.5 · 9.1 | 16.5 · 10.8 · 14.6 | 22.8 · 11.8 · 19.8 | 31.9 · 13.0 · 27.2 |
| Reservation · +CG · +CGu | 5.4 · 4.4 · 21.0 | 18.2 · 20.1 · 20.5 | 25.8 · 13.2 · 25.8 | 94.0 · **19.8** · 93.2 | 90.1 · **20.5** · 83.4 |
| TwoTier · +CG · +CGu | 2.8 · 2.2 · 4.0 | 81.6 · **20.5** · 23.2 | 96.8 · **20.5** · 90.8 | 96.6 · **21.0** · 90.8 | 99.8 · **21.0** · 92.4 |
| ProtoRRageD2 · +CG · +CGu | 3.4 · 2.8 · 20.5 | 5.2 · 3.0 · 5.2 | 4.8 · 3.8 · 8.0 | 13.9 · 4.5 · 20.5 | 97.8 · **7.0** · 87.4 |

Telemetry messages missing (of 2 000, sum over seeds) at N = 16 / 24:
Reservation 968 / 876 → +CG **0 / 0** → +CGu 0 / 1; TwoTier 775 / 451 →
**0 / 1** → 22 / 36. Worst silence at N = 16: Reservation 3 020 ms → 120 →
120; TwoTier 9 540 → 121 → 292. Protected uplink throughput is unchanged
under either setting on every arm (the QoS arms still plateau at ~24 Mbps
from N = 10 — that is the camera, which CG does not touch).

**Reading.** With the restriction honoured, **G3 passes 10/10 at every
fleet size on every arm** — the faithful ports' liveness boundary goes
from 6 and 7 to 24, campaign silences from 10 and 25 to 0, and telemetry
p98 sits at a flat ~20 ms (the 40 ms occasion period halved) wherever the
dynamic path had left it at 90–100. Without the restriction, liveness is
still fixed (the occasion carries *something* every 40 ms and the BSR rides
it) but the latency part regresses toward the no-CG figures from N ≈ 12:
the camera's PBR bucket takes the occasion in LCP round 1, telemetry (PBR
0) rarely reaches round 2, and its SR is suppressed all the while. At small
N the unrestricted CG even costs PF and the Proto arm (p98 3–7 → 20.5 ms):
with every channel "covered", the UE waits for the occasion instead of
raising an SR. **The UE-side `allowedCG-List` half of the port-back is
worth 12 robots of G3 boundary on each faithful arm.**

## 2. G7 — containment

`scripts/g7_aggressor.py`, N = 8, B's camera at 2.1× MFBR, 10 seeds; medians.

| | PF · +CG · +CGu | Reservation · +CG · +CGu | TwoTier · +CG · +CGu | ProtoRRageD2 · +CG · +CGu |
|---|---|---|---|---|
| clause 2 — B camera ÷ MFBR | 1.04 · 1.03 · 1.04 | 2.00 · 1.83 · 1.71 | 2.05 · 2.06 · 2.04 | 1.08 · 1.08 · 1.07 |
| clause 1 — A telemetry bps (of 24 000) | 24 000 ×3 | 24 000 ×3 | **7 101 · 24 000 · 6 240** | 24 000 ×3 |
| clause 1 — A telemetry p98 (ms) | 20.6 · 19.4 · 21.2 | 28.0 · 21.0 · 29.5 | 95.0 · **60.5** · 92.0 | 18.6 · 17.2 · 16.8 |
| clause 1 — A camera ÷ GFBR | 1.009 ×3 | 1.005 · 1.008 · 1.008 | 0.993 · 0.977 · 0.979 | 1.009 ×3 |
| clause 3 — B telemetry | pass ×3 | pass ×3 | pass ×3 | pass ×3 |

**Reading.** Restricted CG turns TwoTier's clause-1 failure into a pass —
the victim's heartbeat at contract, p98 60.5 ms against a 100 ms PDB —
where the unrestricted CG leaves it failed (6 240 bps). Clause 2 is
untouched on every arm: CG never carries the camera, so the over-driven
encoder still delivers 1.7–2.06× MFBR on the QoS arms and the product
finding stands. A's camera on TwoTier is marginally worse under CG
(0.993 → 0.977 of GFBR — the occasions' PRBs). Clause 3 passes everywhere.

## 3. G10 — admissible fleet

`scripts/g5_consolidation.py`, N ∈ {2 … 16}, 10 seeds, RA + SRB; seeds with
every GBR flow ≥ 95 % of GFBR.

| arm | N=6 | 7 | 8 | 10 | 12 | 16 | admissible |
|---|---|---|---|---|---|---|---|
| PF · +CG · +CGu | 10 · 10 · 10 | 10 · 10 · 10 | 10 · 10 · 10 | 10 · 10 · 10 | 10 · 10 · 10 | 2 · 0 · 5 | 12 · 12 · 12 |
| Reservation · +CG · +CGu | 10 · 10 · 10 | 5 · 10 · 10 | 2 · 10 · 10 | 0 · 10 · 10 | 0 · 0 · 0 | 0 · 0 · 0 | **6 · 10 · 10** |
| TwoTier · +CG · +CGu | 10 · 10 · 10 | 10 · 10 · 10 | 9 · 10 · 10 | 0 · 0 · 0 | 0 · 0 · 0 | 0 · 0 · 0 | 7 · 8 · 8 |
| ProtoRRageD2 · +CG · +CGu | 10 · 10 · 10 | 10 · 10 · 10 | 10 · 10 · 10 | 10 · 10 · 10 | 7 · 6 · 9 | 0 · 0 · 0 | 10 · 10 · 10 |

Median worst-GBR-flow ÷ GFBR at N = 10: Reservation 0.000 → 0.989 (+CG);
TwoTier 0.561 → 0.114 (+CG) — the worst flow under CG is now the camera.

**Reading.** Reservation's boundary goes 6 → 10 under either setting: its
failure was telemetry-side (UEs never granted at all, the cold-start
lock-out), which a CG removes. TwoTier moves only 7 → 8: from N = 10 its
worst GBR flow is the camera, which CG does not carry, and the contract
boundary is a camera boundary. PF and the Proto arm are unchanged. This is
the guarantee where the restriction does not matter, because it is not
scored on latency.

## 4. G5 — video

`scripts/g5_video.py --parts A,B,C`, 880 runs per setting (4 arms × 22
cells × 10 seeds); parts 1 / 2 / 3 / 4 = sets complete / frame age / windowed
GFBR / telemetry unharmed.

**GT-3.1 fleet axis — parts 1/2/3/4 of 10 · frame-age p95 median (ms), no CG → +CG**

| arm | N=8 | N=12 | N=16 | admissible (parts 1–2) |
|---|---|---|---|---|
| PF → +CG | 10/10/6/10·18 → 10/10/7/10·18 | 10/10/4/10·25 → 10/10/3/10·25 | 5/1/0/10·120 → 5/1/0/10·125 | 14 → 14 |
| Reservation → +CG | 10/10/5/10·20 → 10/10/3/10·20 | 0/0/0/**7**·142 → 0/0/0/**10**·146 | 0/0/0/**0**·144 → 0/0/0/**10**·149 | 10 → 10 |
| TwoTier → +CG | 1/0/0/10·136 → 2/0/0/10·137 | 3/0/0/**0**·142 → 4/0/0/**10**·133 | 0/0/0/**0**·149 → 0/0/0/**10**·148 | 4 → 4 |
| ProtoRRageD2 → +CG | 10/10/5/10·18 → 10/10/5/10·17 | 10/10/5/10·26 → 10/10/2/10·26 | 10/8/4/10·38 → 10/9/2/10·39 | 14 → 14 |

**GT-3.2 load ceiling (N = 7):** unchanged on every arm — PF, Reservation
and the Proto arm pass every part at every step to ×1.5 with and without
CG; TwoTier's knee stays at ×1.2 (8/4 → 7/3 at ×1.2, frame age 68 → 85 ms).

**GT-3.3 cell edge (N = 7) — part 4 (the edge robot's own telemetry), no CG → +CG**

| SNR | PF | Reservation | TwoTier | ProtoRRageD2 |
|---|---|---|---|---|
| −6 dB | **0 → 10** | **0 → 10** | **0 → 10** | **0 → 10** |
| −3 dB | **0 → 10** | **0 → 10** | **0 → 10** | **0 → 10** |
| 0 dB | 8 → 10 | 8 → 10 | 8 → 10 | 8 → 10 |
| ≥ 5 dB | 10 → 10 | 10 → 10 | 10 → 10 | 10 → 10 |

Parts 1–3 at the edge are unchanged to within one seed (PF and the Proto
arm pass 1–2 at every SNR with or without CG; TwoTier fails 1–2 from 0 dB up
with or without CG).

**Reading.** CG does not reach the video guarantee, as sized: admissible
fleets, the load knee and frame age are unchanged on every arm — a 40 ms
occasion carrying a heartbeat cannot help a 30 fps camera whose frames it
never carries. What it changes is the collateral clause, and there it is
decisive: **the cell-edge robot's own telemetry, which died at −6/−3 dB on
every arm including PF (the one result the baseline report called "what a
cell edge costs the robot standing in it, not a scheduler difference"),
now survives on every arm** — 0/10 → 10/10 — because a configured occasion
needs no SR, no BSR and no ranking to win at low SNR. Reservation's
telemetry on the fleet axis likewise goes from 7/0/0/0 to 10/10/10/10 at
N ≥ 12 while its cameras still fail.

**Unrestricted CG (+CGu) — the video guarantee breaks on every arm.**
GT-3.1 fleet axis, parts 1/2/3/4 · frame-age p95 median (ms):

| arm | N=4 | N=8 | N=12 | N=16 | admissible |
|---|---|---|---|---|---|
| PF · +CGu | 10/10/6/10·11 → **10/4/1/10·67** | 10/10/6/10·18 → 10/10/2/10·55 | 10/10/4/10·25 → 10/10/2/10·53 | 5/1/0/10·120 → 8/3/1/10·84 | 14 → **none** |
| Reservation · +CGu | 10/10/6/10·12 → **10/6/1/10·66** | 10/10/5/10·20 → 10/10/1/10·55 | 0/0/0/7·142 → 0/0/0/10·148 | 0/0/0/0·144 → 0/0/0/10·149 | 10 → **none** |
| TwoTier · +CGu | 10/10/2/10·23 → 10/10/1/10·41 | 1/0/0/10·136 → 2/0/0/10·145 | 3/0/0/0·142 → 1/0/0/10·140 | 0/0/0/0·149 → 0/0/0/10·148 | 4 → 6 |
| ProtoRRageD2 · +CGu | 10/10/6/10·12 → **10/10/1/10·40** | 10/10/5/10·18 → 10/10/3/10·41 | 10/10/5/10·26 → 10/10/1/10·39 | 10/8/4/10·38 → 10/8/2/10·48 | 14 → 14 |

At the cell edge (GT-3.3) frame age reads a flat **~55 ms on PF and
Reservation and ~40 ms on the Proto arm at every SNR** (15–19 ms without
CG), and part 3 is 0–1 of 10 everywhere. Part 4 (telemetry) still passes
10/10 — the occasion does carry the heartbeat.

**Reading.** This is the OAI-UE case doing exactly what TS 38.321 §5.4.4
says it will: with an active CG that may carry every channel, **no channel
on the UE raises an SR**, so the camera's buffer status leaves the UE only
as a BSR riding the 40 ms occasion, and every dynamic camera grant waits
for that report. A 30 fps camera gains ~40 ms of age at any load and its
windowed GFBR floor fails almost every window. Even the arm with the best
ordering (`ProtoRRageD2`) is pushed from 12 to 40 ms. **Deploying CG on
an OAI UE without the LCP mapping restriction would take a cell that
passes G5 on PF and Reservation to one that passes it on nothing.**

## 5. Conclusions

| G | what restricted CG (+CG) does | what unrestricted CG (+CGu, the OAI UE) does |
|---|---|---|
| G3 liveness | every arm 10/10 at every N; faithful boundaries 6, 7 → **24**; silences 10, 25 → 0; telemetry p98 → ~20 ms | silences → 0, but latency regresses from N ≈ 12 (boundaries 14, 12); PF/Proto worse at small N |
| G5 video | video parts unchanged; **edge robot's telemetry 0/10 → 10/10 on every arm** | **breaks G5 on every arm**: frame age +30–50 ms, windowed GFBR 0–2/10, PF and Reservation admissible fleet → none |
| G7 containment | TwoTier clause 1 **fail → pass** (7 101 → 24 000 bps); clause 2 unchanged | clause 1 still failed on TwoTier |
| G10 admissible fleet | Reservation 6 → 10; TwoTier 7 → 8 (camera-bound); PF, Proto unchanged | same as +CG |

1. **Restricted CG closes the liveness guarantee on every arm** — G3 at
   10/10 across the fleet axis, silences 0, telemetry p98 ~20 ms — fixes
   TwoTier's G7 clause 1, lifts Reservation's contract boundary from 6 to
   10, and keeps the cell-edge robot's heartbeat alive where every arm
   including PF had lost it. It is the standards-based version of what
   `ProtoRRageD2` achieved by re-ordering: take the small periodic flow off
   the dynamic path. The two compose (`ProtoRRageD2+CG` p98 7 ms at N = 24).
2. **The UE-side restriction is not optional — it is the difference
   between a fix and a regression.** Without `allowedCG-List` the CG
   suppresses SR for every channel on the UE (TS 38.321 §5.4.4), the
   camera's buffer status leaves only on the 40 ms occasion, and G5 fails
   on every arm while G3 is only half-fixed. The port-back design carries
   both halves, and the UE half is the one that decides.
3. **CG does not reach the video guarantees' own parts.** G10's TwoTier
   boundary and G7's clause 2 are camera problems; CG is sized for the
   heartbeat, and a 40 ms occasion cannot carry a 30 fps stream. Video
   stays the scheduler's problem — which is what the configuration-
   scheduler work is for.
4. **Cost:** ~4–11 PRB per robot every 40 ms; 60–75 % of restricted
   occasions are skipped empty on the cells probed (the flow's period is
   100 ms against a 40 ms occasion) and their PRBs are lost. Protected
   throughput on every arm is unchanged to 0.3 Mbps.

## 6. Not covered

G1, G2 (downlink — CG is uplink-only and cannot change them), G4, G6, G9,
G12 not re-run with CG. Held-out seeds not run. No claim registered. The
`skipped_harq_pending` limitation (the per-UE UL HARQ mask skips an
occasion while a dynamic TB is pending, where a real UE would use another
process) is counted in every artefact's `configured_grant` summary and
runs at 3–6 % of occasions on the cells probed (24 of 395 and 44–54 of
1 000).
