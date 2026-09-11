# G7 — slide source

**Status:** ANSWERED, 2026-09-11.
**Artefacts:** `sweeps/g7-aggressor/g7_n8.json` (four arms, N = 8, 10 seeds),
`sweeps/g7-aggressor/g7_m1.json` (the attempted fix).

**In one line:** **the MFBR ceiling is not enforced anywhere — not by either
QoS arm, and not by the deployed C** — so a misconfigured encoder delivers
**twice** its contracted maximum, and on TwoTier it starves a *different*
robot's heartbeat to 37 % of contract.

---

## 1. The question, in operator terms

**One robot's encoder is mis-set to twice its licensed bitrate. Does the fleet
survive it?** The realistic fault is not malice, it is a wrong value in a
config file. The guarantee a multi-vendor operator needs is that **entitlement
is a ceiling, not a suggestion**.

## 2. THREE CLAUSES, and the third is the one usually dropped

| | clause | result |
|---|---|---|
| **1** | Asset A entirely within its SLOs | **FAILS on TwoTier** |
| **2** | B's camera delivered ≤ MFBR + tolerance | **FAILS on every QoS arm** |
| **3** | B's OWN other flows within SLO — containment *inside* the faulty asset | **PASSES everywhere** |

A scheduler that protected the fleet by letting the faulty robot destroy itself
would fail clause 3. None does.

## 3. THE RESULT — N = 8, B's camera offered at 2.1× MFBR, 10 seeds

| | PF | Reservation | TwoTier | Proto |
|---|---|---|---|---|
| **clause 2** — B delivered ÷ MFBR | **1.05×** | 2.05× | 2.05× | 1.92× |
| **clause 1** — A's telemetry, bps of 24 000 | 24 000 | 24 000 | **8 885** | 21 640 |
| A's camera, share of GFBR | 1.00 | 0.999 | **0.930** | 1.00 |
| A's camera p98 (ms) | 21.7 | 23.2 | **119.2** | 55.5 |
| **clause 3** — B's own telemetry | pass | pass | pass | pass |
| uplink utilisation | 0.932 | 0.903 | **0.647** | 0.932 |

**Proportional fair is the only arm that clips — and it has no contract
machinery at all.** It shares proportionally, so the clipping is a *side
effect* of fairness rather than enforcement of a ceiling. The two arms that
know what an MFBR is are the two that ignore it.

**Clause 1 fails on TwoTier, and that was predicted to PASS.** The victim's
heartbeat is starved to **37 % of its contract** while a neighbour's encoder
runs at twice its ceiling. That is the guarantee's central promise broken: one
misconfigured robot *does* take down another robot's liveness.

## 4. WHY NOTHING CLIPS — and it is a PRODUCT finding, not a port defect

**The cap exists and caps the wrong thing.** `two_tier.py:1716-1724` computes
`max_burst` from `mfbr_bps` and caps `target` — but `target` feeds
`guaranteed_bytes`, and everything above it is moved into `be_bytes` and stays
**fully eligible**. Grant sizing then reads
`b_eff = max(ul_total_target_bytes, ue_backlog)`, and `ue_backlog` is the whole
reported backlog. **So the ceiling decides how much of the demand counts as
guaranteed; it never decides what is delivered.**

**AND THE DEPLOYED C DOES EXACTLY THE SAME.**
`ia_p5g_scheduler.c:2663-2665` computes `_max_burst` from `_c->gbr_ul_max`,
caps `_target`, and adds only `_target` to `ul_total_target_bytes`. **There is
no enforcement step anywhere in it.** So clause 2's failure describes the
product, and any fix is a deliberate divergence rather than a repaired port.

## 5. AN ATTEMPTED FIX THAT DID NOT WORK, and why it is worth recording

**M1** enforced the ceiling by wrapping `BufferView` and exposing a GBR flow's
`bytes_reported` only up to a per-flow token bucket at `mfbr_bps` — this repo's
documented pattern for hiding backlog from scheduling without touching
scheduler code.

**It binds and it does not work.** The bucket drains to 48 bytes of 500 and
withholds 6.2 GB of reported backlog; B still delivers **2.007×** MFBR.

**The reason is an invariant this project already records: `bytes_reported` is
the gNB's ESTIMATE and delivery comes from the UE's REAL queue.** Shrinking the
estimate shrinks the block the scheduler asks for; it does not stop the UE
filling the blocks it gets. **Enforcement has to act on the transport block
actually granted — `tbs_bytes` after sizing — or on eligibility, not on the
demand signal feeding the size.**

**Two process notes, kept because they cost time.** The first M1 measurement
was of a **no-op**: a string replace whose anchor did not match left the debit
step unwired, and a full campaign was run and reported before instrumentation
caught it. Every other edit in this arm asserts its anchor; this one did not.
And the unit question was settled before building rather than after: **a PRB
threshold cannot enforce a bitrate**, because a PRB carries different bytes at
every modulation, so an *n*-PRB cap gives a cell-edge robot a different ceiling
than one beside the gNB. Aggregate-load triggers are wrong for the same clause:
a ceiling that relaxes when the cell is quiet is not a ceiling.

## 6. THE PREDICTIONS, SCORED

Registered 2026-09-05, **before the runner existed**
(`docs/next-expectations-2026-09-05.md`):

| | registered | outcome |
|---|---|---|
| **clause 1** | PASS | **REFUTED on TwoTier** — A's telemetry at 37 % of contract |
| **clause 2** | **FAIL on TwoTier and Reservation alike** | **HELD**, 2.05× on both |
| **clause 3** | PASS | **HELD** on all four arms |

## 7. WHAT THIS DOES NOT SAY

- **No claim is registered.** G7 publishes nothing into
  `config/published_claims.yml` yet.
- **One fleet size only.** N = 8, offered at 2.1× MFBR. The runner exposes
  fleet size, offered multiple and load as axes and **none has been swept** —
  so nothing here is a boundary.
- **The Proto arm is a labelled DIVERGENCE**, and M1 stays behind its own flag,
  default off, with the arm byte-identical to the port when every flag is off.
