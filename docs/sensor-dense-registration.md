# sensor_dense: expectations registered before scoring

**2026-09-05.** The queue's first item, and the reason it leads: **it is the
only workload in this repository where the control channel is under real
pressure.** Measured just now, one run per arm:

| arm | CCE utilisation | UL PRB | binds |
|---|---|---|---|
| PF | **0.641** | 0.708 | PRB, narrowly |
| **Reservation** | **0.632** | 0.479 | **CCE** |
| TwoTier | **0.467** | 0.930 | PRB |

Against the parametric mix's **7.3–9.4 % CCE at 93 % PRB**. So this is a
different regime, and `docs/wp9-regime-map.md` §0.1's *"the ranking does not
generalise"* gets its first test on a control-channel-bound workload.

**And the PDB is 15 ms, against the parametric mix's tightest of 100 ms.**
That is the latency-critical reading no parametric result can supply.

## THE SCENARIO, and what it can and cannot score

30 UEs, **30 UL flows, all qfi 1, all `Delay` class, PDB 15 ms**, horizon
4,000 slots at μ=1 (2.0 s). **No GBR flows and no `xr_video` flows.**

| guarantee | scoreable here? | why |
|---|---|---|
| **G1** (M01 p98, M15 jitter) | **YES — and this is the point** | the bound is the flows' own **15 ms** PDB, not the parametric 100 ms |
| **G3** (M20 liveness gap) | **YES** | |
| **G8** (M09 Jain, M22 starvation) | **YES** | |
| G5 (M05/M06) | **no** | no flow carries a `frame_id`; both metrics go `pending` |
| G10 (M07/M08) | **no** | no GBR flow, so there is no GFBR to score against |
| G4, G6, G12 | **no** | need a duty-cycle axis, a background aggressor, and a load ramp respectively |

## THE EXPECTATION THAT MATTERS MOST — the study's headline is NOT reproducible here

`scheduler-study.md` §7.2 / `adoption-decision.md` §1 report **TwoTier 30/30
on-time against PF's 2/30** on this scenario, *"from Configured Grants and a
deadline-aware Tier-2"*.

**Configured Grants do not exist in this branch.** `_SPSReservation`,
`_allocate_sps` and `_is_sps_eligible` were deleted at Phase 2 two-tier
commit 1 and survive only in the docstring recording their removal.

> **PREDICTION: TwoTier will NOT reach 30/30 here, and the gap to PF will be
> far smaller than 30/30 vs 2/30 — because the mechanism the study credits
> for that result is absent.** Statistic: count of flows with p98 ≤ 15 ms.
> Level: the count, per arm. Direction: TwoTier > PF, but by a margin
> measured in a few flows rather than 28.
> **Falsifier:** TwoTier reaches ≥ 28/30, which would mean the win did not
> depend on CG after all and the study's attribution needs revisiting.

## The rest, each with statistic / level / direction / falsifier

| # | statistic | level | prediction | falsifier |
|---|---|---|---|---|
| **1** | flows with p98 ≤ **15 ms** | count per arm | **PF worst; TwoTier and Reservation better but neither near 30/30** | TwoTier ≥ 28/30 (see above), or PF best |
| **2** | M01 p98, protected fleet | per-arm ms | **all three FAIL the 15 ms bound on most seeds** — the parametric-mix reading (all pass at 100 ms) does not transfer | any arm passing 15 ms on ≥ 8/10 seeds |
| **3** | `n_never_granted` | count per arm | **0 on every arm** — 30 UEs each with ONE flow, so there is no per-LCG array to empty across LCGs and the cold-start lock-out has no purchase | any arm > 0 |
| **4** | M09 per-second Jain, protected | per-arm scalar | **all ≥ 0.90** — 30 identical flows is the easiest possible fairness case | any arm < 0.90 |
| **5** | **does any verdict DIFFER from the parametric mix's?** | per-guarantee | **YES for G1** — it passes at 100 ms and should fail at 15 ms. **NO for G3/G8** | G1 passing here, or G3/G8 flipping |

**Expectation 3 is the control and the one I would flag if it moves**: the
lock-out needs a UE whose per-LCG array is empty while other LCGs carry
backlog. With one flow per UE there is nothing to desync against, so a
non-zero count would mean the mechanism is broader than
`docs/g5-mechanism-2026-09-05.md` claims.

**Expectation 5 is the coverage question the queue is for.** A verdict that
differs by workload is a finding in itself.
