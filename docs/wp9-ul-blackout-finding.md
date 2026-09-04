# The UL blackout: three schedulers, three relationships to one fault

**2026-09-04.** A UE's entire uplink goes dark for a whole run — protected
GBR bearers included — while its downlink is unaffected. Found in Phase 2,
investigated to mechanism, and the mechanism is the answer to *is two-tier
needed*.

## The mechanism first

**Configuring one real per-bearer QoS parameter takes two-tier from 35 % to
5 % and does nothing at all for Reservation** — because Reservation has no
equivalent mechanism to configure. PF is immune for a third, unrelated
reason. Three arms, three different relationships to the same fault.

| arm | rate | why |
|---|---|---|
| **PF** | **0 %** | Structurally immune. It ranks on `bits_per_rb / r_avg`, and a starved UE's `r_avg` collapses, so its rank **rises as it starves**. The signal PF uses improves under the fault. |
| **TwoTier** | **35 % → 5 %** | Has two named protections (FIX-2's GBR PRB reserve, the UL service-interval floor), both gated on `has_pending_gbr`, which requires `mfbr_bps > 0`. Configuring MFBR switches them on. |
| **Reservation** | **65 %, unchanged** | Has neither. Its `needs_service` is not MFBR-gated, so nothing switched on. No configuration change can help it. |

## The mechanism split — the reserve is NOT sufficient, the floor is

They switch on together via the same gate, so they were counted apart:

| run | `has_pending_gbr` TRUE | FLOOR_FIRED | dead flows |
|---|---|---|---|
| rescued seed, mfbr=0 | **0** of 424,959 calls | 0 | 9 |
| rescued seed, mfbr=2.0 | 304,913 | **3** | **0** |
| still-dead seed, mfbr=2.0 | 110,218 | **0** | 9 |

**Row 3 is the load-bearing one.** The still-dead seed has the gate true in
110,218 calls — FIX-2's reserve fully active — and still loses nine flows.
The rescued seed differs only in that the **floor fired three times**.

**Three fires clear nine dead flows.** That is breaking a deadlock, not
adding capacity: one grant carries a BSR, the estimate resyncs, service
resumes.

**Row 1 is the configuration diagnosis in one number:** at `mfbr=0` the gate
is true **zero times in 424,959 calls**. Not weakened — unreachable.

## The fault, measured end to end

Reservation, seed 1097657231, N=8. UE8's three UL flows deliver **zero
bytes** against full arrivals; its DL command flow is unaffected.

1. Never granted → never a BSR → `estimated_ul_buffer_per_lcg = 0` in **all
   40,000 slots** (measured).
2. `bytes_reported` therefore never exceeds the **150-byte SR floor**, and
   only in 11,520 slots — so UE8 is a candidate in **9,216 of 40,000**
   slot-appearances against ~30,900 for every peer.
3. `has_gbr = False` (derived from the same estimate) pins it in the lower
   sort tier. Measured rank: **7th of 8 in 6,940 of 9,216 appearances**,
   never 1st or 2nd; all seven peers granted ahead of it ~3,900 times each.
4. 55 PRBs, ~3 UEs served per slot → the loop never reaches rank 7.
5. No grant → back to 1.

**The thr floor works and cannot help.** `coef` reaches 52.0, equal to a
healthy UE's — but `coef` is **tier 4** and `has_gbr` is **tier 2**, which
separates first. A protection in the last tier cannot rescue a UE pinned by
the second.

## The 5 % residue is for the hardware campaign, and the sim cannot answer it

The C's floor arms on `has_pending_gbr`, computed by skipping any LCG whose
`estimated_ul_buffer_per_lcg <= 0` (`gNB_scheduler_ulsch.c:48-66`). That
array is **frozen between BSRs and never drained on a grant** (CLAUDE.md's
own invariant), which is exactly what makes it a durable arming signal for
the fault the C describes: *"BSR desync / SR loss on real RF"* — a UE that
**had service and lost it**. Its scalar reads 0 while the array still holds
the last BSR.

**Our residual UE never had a first grant at all.** Never-served, not
desynced. Both histories present the same zero, and the arming signal cannot
distinguish them — so **the deployed two-tier's floor cannot arm for a UE
that never got a first grant, because arming reads the estimate a first
grant would populate.**

**Whether that is reachable on real hardware is the campaign's question, and
this simulator cannot answer it.** RACH and attach are modelled
(`sim/join.py`, `sim/rlf.py`), but whether a real UE is *guaranteed* an
initial grant after attach is a property of the deployed gNB's own
scheduling, not of anything modelled here. State it to the team as an
uncovered case with a known trigger condition, not as a predicted failure
rate.

---

# CORRECTION TO THE RECORD: MFBR was never configured ANYWHERE

**The claim, corrected.** It was asserted during this investigation — by the
person directing it, and repeated by me without checking — that *"the fleet
workloads already set MFBR to 150 Mbps"*, making `mfbr_multiple = 0.0` in
the parametric mix a fix applied in one place and not another.

**That is false.** Checked directly:

- `mfbr_bps` is assigned in **exactly one non-test site in the repository**:
  `sim/parametric.py:258`, `mfbr_bps=mfbr_multiple * gfbr`, with
  `mfbr_multiple` defaulting to **0.0**.
- `sim/fleet.py` **never assigns it at all**, so every fleet flow takes
  `FlowConfig`'s default of `0.0`:

  | composition | flows with `mfbr_bps > 0` |
  |---|---|
  | `drone_heavy` | **0 of 29** |
  | `ugv_heavy` | **0 of 30** |
  | `sensor_dense` | **0 of 16** |
  | `mixed` | **0 of 26** |

- The only MFBR-shaped value anywhere in configuration is
  `sim/scenarios/scenario_config_6.yml:28`, at **2 Mbps**, annotated *"not
  enforced in sim"*.

**Why this matters more than a corrected number.** It changes the finding
from *"a fix applied at one site and not another"* to **"a fix never
applied"**, and it widens the scope from the parametric half of the evidence
base to **all of it**:

> **Two-tier's FIX-2 GBR reserve and its UL service-interval floor have been
> unreachable in every workload this project has ever run** — stage 1, 2, 4
> and 5; G6's conjunction; G10's admissible-fleet numbers; G11's soak
> scenario; and G12's entire campaign, which runs on the fleet builder.
> Every arm comparison ever published was measured against a two-tier with
> its two named mechanisms switched off.

Stated the way the SR-trigger deadlock's scope was stated, rather than as a
caveat: this is not a qualifier on some results, it is a property of all of
them.

**And it costs a claimed pattern.** The "fix at the site of discovery rather
than at the category" pattern was offered with two instances. With MFBR
corrected it has **one clean instance** — the population defect (§24.2 fixed
it for G6 via M20; nobody asked whether other guarantees had it; nine work
packages later it was inverting G1 and G8 in opposite directions). MFBR is a
**different** failure: not a fix applied narrowly, but a parameter that was
diagnosed as inert three separate times (two-tier commit 4a's `gbr_below`,
`max_burst` at its floor, the UL floor's arming gate), understood each time,
and never configured anywhere. The pattern is recorded with one instance and
MFBR recorded beside it as its own shape, rather than keeping a
two-instance pattern built partly on a wrong premise.

---

# THE PARAMETRIC MIX CONTAINS NO LATENCY-CRITICAL FLOW

Found by diffing the parametric mix against the fleet config — the cheap
check nobody had run. It is the more consequential half of that diff and
does not belong in a table under MFBR.

| | classes present | tightest PDB |
|---|---|---|
| **parametric mix** | 5QI 1 (100 ms UL), 2 (150 ms UL), 9 (300 ms UL), 82 (100 ms DL) | **100 ms** |
| **fleet** | the same, **plus 5QI 83 (10 ms UL odometry) and 5QI 85 (5 ms DL e-stop)** | **5 ms** |

**The parametric mix's tightest PDB is 100 ms. It contains no flow that any
reasonable reading would call latency-critical** — no e-stop, no odometry,
nothing under 100 ms.

## Which results this touches

Everything built on `sweep_scenario`, which is the WP9 core:

- **stage 1** (59 cells, 1,770 runs) — the axis-screening gate
- **stage 2** (252 cells, 7,560 runs) — the contiguous grid, and G10's
  admissible-fleet numbers
- **G6's conjunction** at n_seeds=40
- **G11's soak** (`build_g11_scenario` wraps `sweep_scenario`)
- **G1's 100 ms bound and G3's 500 ms liveness numbers**, which is where it
  bites hardest: G1's bound was evaluated against a workload whose tightest
  configured budget **equals that bound**, and G3's liveness against flows
  whose slowest cadence is 300 ms.

Stages 4 and 5 use `build_fleet` and are **not** affected — they carry both
classes.

## Does the sweep's tight-PDB evidence survive?

**A scope question, answered as one — not a measurement.**

**No, and the reason is structural rather than statistical.** The sweep never
contained the population its tight-PDB conclusions are about. This is not a
sample-size or a noise problem that more seeds would fix; it is the
empty-selection shape at the level of the workload. A conclusion of the form
*"tight-PDB flows behave thus under load"* drawn on a mix whose tightest PDB
is 100 ms is a statement about a population with zero members.

**What survives:** every result about 5QI 1 / 2 / 9 / 82 behaviour on the
core plane. Those classes are really there and really measured. The arm
separation at N=8, the load dependence, G10's per-arm admissible counts —
all are claims about the classes actually present.

**What does not:** any generalisation from the sweep to latency-critical
behaviour, and in particular **§15.5's open hypothesis about tight-PDB
density**, which cannot be tested on a workload with no tight-PDB flows. It
needs re-running on a mix that has 5QI 83 and 85 — either `build_fleet`'s
compositions or a parametric mix extended to carry them.

**Recommendation, and it is a scoping decision rather than a fix:** do not
retrofit the classes into the parametric mix as a drive-by. Two of the three
`MIXES` levels (`video_heavy`, `telemetry_only`) are already dormant with no
non-test caller, and adding classes changes every existing sweep number at
once. Either extend the mix in its own commit with its own before/after, or
run tight-PDB questions on the fleet builder, which already has them.
