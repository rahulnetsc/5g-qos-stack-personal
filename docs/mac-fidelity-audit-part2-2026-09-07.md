# Part 2 — per-guarantee scenario & clause audit

**2026-09-07.** Companion to `docs/mac-fidelity-audit-2026-09-07.md` (Part 1,
findings **M-1 … M-13**) and to `docs/system-audit-2026-09-07.md` (the earlier
pass, **P1-1 … P1-4**, **P2-1 … P2-4**, **P3-1 … P3-3**).

**What this part asks, per guarantee, six questions:** (1) can the scenario
produce the failure the clause names; (2) which parts of the clause nobody
scored, and does the artefact already carry them; (3) which Part 1 absences the
clause depends on, and whether they move the **verdict** or only the **margin**;
(4) which mechanisms are inert in this scenario; (5) the flag state it was
measured in; (6) provenance.

**Inherited without re-deriving:** P2-1 (most clauses have 2–3 parts, one
scored; G8's second half fails on `core`), P2-2 (G1 scores uplink telemetry;
its clause names a downlink command), P2-3 (GT-1.2 and GT-7's scenarios were
never built; G4's axis is `duty_cycle`, not silence length), P2-4 (provenance,
MFBR-zero on `sensor_dense`).

**Build nothing.** Findings recorded where found, ranked at the end.

---

## Q6 first, because it bounds everything below

**The ten scored artefacts predate the ledger-key fix by ~25 minutes.**
`sweeps/fixed-2026-09-07/{plain,attach}/*.json` are timestamped
**07:38–07:51**; the derivation fix is commit `fe5e2f4` at **08:13**. P2-4's
statement *"all ten scorecard artefacts are from today, after the ledger-key
fix"* was written about `sweeps/rerun-2026-09-06/` and **does not describe the
directory the scorecard now reads**.

**They are nonetheless clean, and this is verified rather than argued.** The
two columns wrote to **separate `--out` directories**, so each carries its own
`core.runs.jsonl` (30 lines each) and no resume could cross between them. The
positive check — the one the fix commit itself names as the discriminator —
is that the columns **differ**: same arm, same seed, `wall_s` 13.8 vs 14.0,
`G1_M01_p98_prot` 22.0 vs 24.0, worst flow `ue8_qfi1` vs `ue5_qfi1`. **A
contaminated column would be byte-identical.**

**But G11 and G12's "with attach" column is the without-attach artefact.**
`guarantee_scorecard.load()` implements `--attach` as
`rel.replace(SEV_DIR, ATT_DIR)`. `_nested()` loads
`sweeps/rerun-2026-09-06/g11_c1_soak.json` and
`sweeps/g12-rescore-2026-09-06/g12.json` — **neither path contains `SEV_DIR`**,
so the replacement is a no-op and both rows load the same file in both columns.
The published table shows G11 and G12 identical in both columns, which reads as
*"the attach path does not affect them"*; **the truth is that no with-attach run
of either exists.** `g11_campaign.py` and `g12_campaign.py` take no attach
argument at all (`grep attach_seed` returns nothing in either).

**That is defect #31 recurring one row over** — the fix commit's own words:
*"the symptom is an artefact byte-identical to the column it should differ
from — indistinguishable from 'the flag did nothing', which is how it was read
twice."* It has now been read a third time.

**Also worth stating once rather than per row:** five of the twelve guarantees
(**G4, G6, G9, G11, G12**) are scored — or declared not-computable — from
`sweeps/rerun-2026-09-06/` and `sweeps/g12-rescore-2026-09-06/`, i.e. **a
different, older sweep that was never regenerated after the 2026-09-07 audit
fixes** (G3's population correction, G10's de-confounding, G7 c2's tolerance,
the uniform severity column). The seven scored rows and the five unscored ones
are not from the same evidence base.

---

## The five Part-1 absences, mapped to clauses once

Referenced per guarantee below rather than restated.

| Part 1 item | what it is | direction | which clauses read it |
|---|---|---|---|
| **M-9** | deployed UL gate rescues any UE unscheduled for **100 ms** (`high_inactivity`); absent here, every arm | sim **starves harder** than deployed | G8 (both halves), G3, G5, G10, G12 c4, G2 (UL), G11 |
| **M-6** | deployed cap of **4 UEs/slot/direction**; absent here. Measured excess: TwoTier 46–49 % of UL slots, **Reservation 87.4 %** at N=16, **PF 0.0 %** | sim **serves more UEs** than deployed, **arm-differentially** | G10, G8, G5, G12, G1 (DL), G2 (DL) |
| **M-1** | the dead-tier evidence is **uplink only**; every DL comparator unobserved | unknown | G1, G2 (DL half) |
| **M-4** | LCP's **BSD** (flat 100 ms vs deployed 20/50/100/150) and **PBR** (exact GFBR vs enum-rounded; **0 vs kBps8** for non-GBR) | sim's intra-TB split is **more skewed** than deployed | G1, G2 (UL), G3, G5, G7 |
| **M-2** | SR→grant→PUSCH costs **0 slots**; `k2` prices retransmissions only | sim is **1–2 ms optimistic per UL grant** | G1, G2 (UL), G3, G4 |

**M-6 and M-9 oppose each other and are NOT netted here.** Where both appear in
a row's dependency list, that row's verdict is **not deployment-representative
until both are built**, whatever the sign of either alone.

### One M-4 consequence that is specific enough to state as its own finding

**In every built scenario, exactly ONE flow has a non-zero PBR.** Measured
across the parametric `factory` mix and `sensor_dense`:

| flow | class | priority | GFBR | **effective PBR** | BSD |
|---|---|---|---|---|---|
| 5QI **1** UL telemetry | Delay | **20** | 0 | **0** | 100 ms |
| 5QI **2** UL video | GBR | 40 | 4 Mbps | **4 Mbps** | 100 ms |
| 5QI **82** DL command | Delay | 19 | 0 | **0** | 100 ms |
| 5QI **9** UL background | PF | 90 | 0 | **0** | 100 ms |
| `sensor_dense` 5QI 1 UL | Delay | 20 | 0 | **0** | 100 ms |

`sim/ue_lcp.py`'s round 1 iterates in priority order but **skips any flow with
no tokens**, so on a UE carrying telemetry + video + background, **round 1
serves the VIDEO flow first — ahead of the higher-priority telemetry** — up to
its bucket, and telemetry is only reached in round 2. Under the deployed config
(M-4) telemetry would hold a `kBps8` bucket and would be served **first** in
round 1, and video's bucket would be **half** the size (BSD ms50 at a 150 ms
PDB, not ms100).

**So the simulator inverts the intra-UE priority order inside every uplink
transport block, for the protected instrument flow specifically.** Direction:
against telemetry, in favour of video.

**Measured magnitude at the current load: small, and the honest reading is that
it is not yet biting.** From `sweeps/rerun-2026-09-06/traces.json`, UE 1 under
PF: `qfi1` rides 3.0 % of UL grants with `gap_p50 = 98.5 ms` — which is the
flow's own 10 Hz generation period, i.e. it is being served on arrival, not
starved. Round 2 has room at this load. **It is a margin effect that becomes a
verdict effect exactly where the TB is small (the crumb regime) or the cell is
loaded — G12's ramp top and G10's N=16.**

---

## Per guarantee

### G1 — "every drive command reaches the robot in time"

**1. Can the scenario produce the failure?** **Partly, and not for the flow the
clause names.** GT-1.1 specifies M1-DL cmd_vel **20 Hz × 100 B on 5QI 1 DL**
plus *"saturating 5QI-9 DL (firmware pull) so the DL link is genuinely
loaded — an idle DL link measures nothing."* The built mix has a DL command
flow (5QI **82**, `periodic_control`, PDB 100 ms) and **no DL background at
all**: every 5QI-9 flow is uplink. **The DL link is exactly the idle link the
GT spec says measures nothing.** Measured in Part 1: only **160–214 slots per
run carry any DL grant**. P2-2 established that the scored statistic lands on
`qfi1`/`qfi2` (both UL) 30/30 times; this adds *why* — there is no DL
contention to produce a DL failure.

**2. Unscored parts.** Clause is *"p98 ≤ 95 ms; p99.9 reported"* (2 parts) and
GT-1.1 adds a third, *"zero command gaps ≥ 200 ms"*.
- **p99.9** — **not in the artefact**, needs a run. The guarantee's own
  reporting obligation is unmet (P2-1 recorded this).
- **zero command gaps ≥ 200 ms** — **not carried**; `G3_M03_*` is a 500 ms
  gap over the protected fleet, a different threshold on a different flow.
  Needs a run.
- **G3's own third part, `p98 ≤ PDB`, IS this clause** and is scored under G1's
  name — worth knowing before commissioning a run for it.

**3. Part 1 dependencies.** **M-1** (the DL comparator has never been observed —
and this is the one clause about a DL flow); **M-6's DL half** (deployed cap 4
UEs/slot, measured **8 at N=8 and 16 at N=16** here, on 50–63 % of DL-granting
slots); **M-4** and **M-2** for the statistic actually scored, which is UL
telemetry. **Verdict or margin:** for the UL statistic, **margin only** —
TwoTier's 3 failures are 2–4 ms over a 95 ms bound, and M-2 alone (1–2 ms per
grant) is the same size as the miss, so **TwoTier's 7/10 could plausibly become
10/10 or 4/10 under a correct UL round trip.** That is a verdict change. For
the DL command flow there is **no number at all**, so neither.

**4. Inert here.** MFBR (0 on 5QI 1 and 82) → two-tier's MFBR-dependent
protections; PBR (0 on both Delay flows) → LCP round 1; padding/truncated BSR
(M-3); the DL background flow the GT spec requires.

**5. Flag state.** `core.json`, N=8, `load_mult 1.0`, `sim_s 10.0`,
`cqi_delay_slots=8`, `min_rb=5`, both attach columns, no stagger,
`truncated_bsr="off"`, PBR/BSD at defaults, MFBR 8 Mbps on 5QI 2 only.

**6. Provenance.** 2026-09-07 07:50/07:51, columns verified distinct.

**VERDICT: NOT deployment-representative.** Needs **M-1 (DL trace), M-6 (DL
cap), M-2 (UL k2)**, and a **DL-loaded scenario** before either the UL number
or a DL number means anything.

### G2 — "a STOP always lands"

**1. Can the scenario produce the failure?** **No, and P2-3 said why for the DL
side; the UL side is now built but under-specified.** GT-1.2 requires *both
assets at full committed profile, cell saturated both directions with 5QI-9
(worst legal case), simultaneous STOPs*; GT-7.2 adds *50 storms/run of 5 × 300 B
bursts within a 10 ms window*. What ran: `g2_ul_stop`, N=8, nominal load, no
saturation, no simultaneity, no storms.

**2. Unscored parts — AND THE ARTEFACT ALREADY CARRIES THE DOWNLINK HALF.**
`g2_ul_stop.json` has `DL_stop_flows` (**2**), `DL_stop_p98_ms`,
`DL_stop_p50_ms`, `DL_stop_starved`. **The scorecard scores `UL_stop_p98_ms`
only.** Scored here for the first time:

| arm | **DL STOP p98 ≤ 100 ms** | UL STOP p98 ≤ 100 ms | DL starved |
|---|---|---|---|
| PF | **10/10** | 10/10 | 0 |
| Reservation | **10/10** | 10/10 | 0 |
| TwoTier | **10/10** | 10/10 | 0 |

Identical in both columns. **GT-1.2's STOP is a downlink datagram**, so the
scored row has been answering the mirror-image question — the same shape as
P2-2's G1 finding, in a case where the right column was sitting in the file.
Remaining unscored: the clause says **100 % of STOPs**, i.e. the **maximum**;
the artefact carries p98, which the scorecard labels as weaker rather than
equating (correctly). The **max** needs a run. So G2 is **1 of 3 → now 2 of 3**.

**3. Part 1 dependencies.** UL half: **M-2** (the SR round trip is a large
fraction of a 2–4 ms measured latency — this is the clause where a 1–2 ms
omission is proportionally largest), **M-4**, **M-9**. DL half: **M-6's DL cap**,
**M-1**. **Verdict or margin: margin, comfortably** — 25× headroom absorbs all
of them. **The scenario, not the fidelity, is what invalidates G2.**

**4. Inert here.** MFBR on the STOP flow; PBR on it (Delay class → 0);
padding/truncated BSR; the saturating background and the storm generator, both
of which the GT spec requires and which do not exist.

**5. Flag state.** `g2_ul_stop.json`, N=8, `build_fleet(..., ul_stop=True)`,
nominal load, both columns, defaults otherwise.

**6. Provenance.** 2026-09-07 07:41/07:45, clean.

**VERDICT: NOT deployment-representative — but the gap is the SCENARIO, not
Part 1.** GT-1.2's saturated/simultaneous/storm scenario has to be **built**;
no Part 1 item changes a 25× margin.

### G3 — "the network never makes a healthy robot look dead"

**1. Can the scenario produce the failure?** **Not at this operating point** —
10/10 on every arm on all three parts, one point (N=8, ×1.0). The failure the
clause names is a **liveness stall**, and Part 1 found the deployed system's own
guard against it (**M-9**) is missing here — so the sim is if anything *more*
able to produce the failure than hardware, and still does not.

**2. Unscored parts.** Three parts (P2-1). All three are now accounted for:
- max gap ≤ 500 ms — **scored**, 10/10 all arms.
- zero gaps ≥ T_live — **carried** as `G3_M03_gaps_over_tlive_prot`; **0
  breaches, 10/10 on every arm, both columns** (P2-1 measured this; re-confirmed
  on the current artefact).
- p98 ≤ PDB — **carried**, and it is numerically **G1's own clause**
  (`G1_M01_p98_prot ≤ 95`): PF 10/10, Reservation 10/10, **TwoTier 7/10**
  without attach, 9/10 with. **So G3's third part FAILS on TwoTier 3/10 while
  G3's published row reads 10/10** — the same statistic, scored under one
  guarantee's name and not the other's.

**3. Part 1 dependencies.** **M-9** (dominant: a 100 ms rescue bounds the gap
structurally, so the deployed max gap can barely approach 500 ms), **M-6**
(opposes), **M-4**, **M-2**. **Verdict or margin: margin for parts 1–2** (they
pass and would pass harder); **verdict for part 3**, which is G1's and inherits
G1's answer.

**4. Inert here.** As G1 (same artefact).

**5. Flag state.** As G1.

**6. Provenance.** As G1.

**VERDICT: parts 1–2 are ROBUST to Part 1** (both absences push toward failure
and it does not occur). **Part 3 is G1's and carries G1's verdict.** The
published G3 row understates what its own clause requires.

### G4 — "after a robot goes quiet, its next message still arrives promptly"

**1. Can the scenario produce the failure?** **No — the axis is wrong** (P2-3):
the sweep varies `duty_cycle ∈ {1.0, 0.5, 0.1}` while the clause names silence
lengths **{1 s, 5 s, 60 s}** (and the plan contradicts itself: GT-2.3 says
{1 s, 10 s, 60 s}). Under `_burstify`'s constant-mean-rate design, duty cycle
moves message size and silence together, so the two are confounded.
**New here:** GT-2.3's own stated reason for those buckets is that they
**straddle the floor's 2 s arming horizon** — *"gap < 2 s (floor armed) and
gap > 2 s (floor disarmed)"*. Part 1 measured `floor_fire` decisive **27 times
in 5.3 M adjacencies**, so the mechanism the buckets were chosen to
discriminate is essentially never active here regardless of the axis.

**2. Unscored parts.** **0 of 3** (P2-1), unchanged. The scorecard declares it
NOT_COMPUTABLE for a further reason: the artefact stores **p98, not p99**, and
substituting would be optimistic; its rows are keyed
`(duty, ue, qfi, bucket)`, not per run. **A run is needed for all three
buckets.**

**3. Part 1 dependencies.** **M-2 is the dominant one and this is the clause
where it is structural, not marginal**: "first packet after silence" is
*precisely* the SR→grant→PUSCH round trip, and the simulator prices **zero**
slots for it. GT-2.3 also marks itself **`Env: RF` essential — "SR fragility
does not manifest in rfsim"**. **M-9** (the 100 ms rescue is what bounds a
post-silence first packet on hardware), **M-4**.

**4. Inert here.** The UL floor (27 fires in 5.3 M); MFBR; PBR on the telemetry
flow; padding/truncated BSR; `sr_prohibit_ms`/`sr_trans_max`/
`rach_recovery_ms`/`sr_report_floor_bytes`, all four unreachable from `run()`
(M-2) — **and `sr_report_floor_bytes = 150` is the single number that sets how
much the first post-silence grant can carry.**

**5. Flag state.** `sweeps/rerun-2026-09-06/g4.json`, attach **OFF only**, no
with-attach column exists.

**6. Provenance.** 2026-09-06, i.e. **before the audit fixes**; not regenerated.

**VERDICT: NO NUMBER, and the axis is wrong.** Needs **M-2 built** before any
post-silence number is meaningful, plus a scenario that decouples silence from
payload.

### G5 — "operators always see fresh, complete video"

**1. Can the scenario produce the failure?** **Yes — it is one of only three
rows that separates the arms** (Reservation 3/10, TwoTier 6/10 without attach).

**2. Unscored parts.** Three parts (P2-1).
- ≥ 99 % PDU sets — **scored**.
- frame age p95 ≤ 67 ms — **carried** as `G5_M06_all_ms`, re-measured on the
  current artefact: **10/10 on every arm, both columns**; medians PF **25.0**,
  Reservation **21.6**, TwoTier **44.8** ms. **TwoTier sits at 67 % of the
  bound against PF's 37 %.** *New caveat:* this is the **only** G5 key with no
  `_prot` variant — it sums over **all** flows. Harmless in fact (PDU sets exist
  only on the framed video flow) but it is an undeclared population in a
  scorecard that now refuses undeclared populations elsewhere.
- per-2 s-window goodput ≥ GFBR — **not carried**, needs a run. `M07` in
  `g10_attach.json` is the whole-run GBR contract, a different question.

**3. Part 1 dependencies.** **M-9 and M-6 both, and they oppose.** The failure
mechanism is the cold-start lock-out, which is a **candidacy** fault (M-9's
rescue attacks it directly); the cap (M-6) binds Reservation on **87.4 %** of UL
slots at N=16 and would concentrate service further. **Verdict, not margin** —
this row already moves 3/10 → 10/10 on a single flag, so it is demonstrably
sensitive to exactly this class of change. Also **M-4**: video is the one flow
with a token bucket, and its bucket is **2× oversized** here (BSD ms100 vs the
deployed ms50 at a 150 ms PDB), so the sim's video takes **more** of each TB
than deployed — **flattering G5 and disadvantaging telemetry**.

**4. Inert here.** The UL floor; padding/truncated BSR; PBR on every flow except
this one; `survival_time_ms` (never non-zero, so M14 has never measured what it
defines).

**5. Flag state.** As G1 (`core.json`). **MFBR 8 Mbps IS configured on this
flow** — G5 is one of the few rows where the MFBR-dependent paths are not inert.

**6. Provenance.** As G1.

**VERDICT: NOT deployment-representative.** Needs **M-9 AND M-6 built
together**, and **M-4's BSD corrected**. This is the row where the three
interact most directly.

### G6 — "background traffic can never impair the fleet"

**1. Can the scenario produce the failure?** **Unknown — the clause is
unscoreable**, so the question has never been asked. GT-4.1 also requires a
**DL** flood (GT-4.2, marked **P0**, *"a firmware push to one robot cannot blunt
another robot's controls"*), and as established under G1 **there is no DL
background flow in any built scenario.** So half of the G6 family cannot be run
at all.

**2. Unscored parts.** **0 of 2.** The bound is stated (+20 % relative) but the
clause needs the **unperturbed baseline per statistic** as a paired control, and
the artefact stores only the perturbed arm's summary. **A run is needed — a
paired one.**

**3. Part 1 dependencies.** **M-6** (a per-slot UE cap is exactly what
determines whether a background flood displaces a protected flow), **M-9**,
**M-4** (the background flow has **PBR 0** here and **kBps8** deployed, so on
hardware background enters LCP round 1 and here it never does — this clause is
about background's impact and the sim gives it strictly less intra-UE weight
than deployed). **Verdict** — there is no verdict to move yet.

**4. Inert here.** DL background (absent); PBR on background; MFBR on
background; the UL floor.

**5. Flag state.** `sweeps/rerun-2026-09-06/g6/`, attach OFF only.

**6. Provenance.** 2026-09-06, before the audit fixes.

**VERDICT: NO NUMBER.** Needs a **paired baseline run** and a **DL background
flow**; then M-6/M-9/M-4.

### G7 — "one misbehaving robot cannot take down the others"

**1. Can the scenario produce the failure?** **Yes for c2 — and it is
inverted**: 0/10 on both QoS arms at 2.1× MFBR, i.e. no arm clips. P3-2 already
noted the sweep should run **downward**. For c1 the answer is **no**: the victim
passes 10/10 everywhere, so the scenario never produces the failure c1 names.

**2. Unscored parts — GT-4.3 states THREE, not two, and the third is in the
artefact.** The guarantee-table line (L101) has two; **GT-4.3's own KPI line has
three**: *"A entirely within SLO; B's camera delivered ≤ MFBR + tolerance;
**B's other flows (its own telemetry!) still within SLO** — the containment must
also hold inside the misbehaving asset."* Scored here for the first time:

| part | statistic | PF | Reservation | TwoTier |
|---|---|---|---|---|
| c1 (scored) | `A_camera_m05 ≥ 0.99` | 10/10 | 10/10 | 10/10 |
| **c1 fuller form** | `A_camera_p98 ≤ PDB` | **10/10** | **10/10** | **10/10** |
| **c1 fuller form** | `A_telemetry_p98 ≤ PDB` | **10/10** | **10/10** | **10/10** |
| **c3 (NEW)** | `B_telemetry_p98 ≤ PDB` | **10/10** | **10/10** | **10/10** |
| c2 (scored) | `B_camera/MFBR ≤ 1.0` | 1/10 | 0/10 | 0/10 |

Identical in both columns. **So the containment holds inside the misbehaving
asset on every arm — a real, previously unreported positive result**, and it
sharpens c2: the aggressor's excess is not exported to A **or** to B's own
telemetry; it is simply not clipped.

**3. Part 1 dependencies.** **M-4 is the direct one and this is its clearest
case.** c3 asks whether B's telemetry survives B's own runaway camera — that is
**precisely the intra-UE LCP split**, and Part 1 found the sim serves the camera
**first** (it is the only flow with a token bucket) with a bucket **2×** the
deployed size. **The sim is therefore running the HARDER version of c3 and
passing it**, which makes this pass conservative — the one place in the audit
where a fidelity gap makes a result *stronger*, and it should be stated that way
rather than as a defect. c2 is a rate-limiting question and is **insensitive** to
M-6/M-9 (ratios ~2.0, insensitive to tolerance out to 1.5).

**4. Inert here.** M-9/M-6 barely bite (the failure is intra-UE, not
inter-UE-ordering); the UL floor; padding/truncated BSR; PBR on A's and B's
telemetry (both 0).

**5. Flag state.** `g7.json`, N=8, aggressor at **2.1× MFBR**, `load_mult 1.0`,
both columns, MFBR **8 Mbps configured** (not inert here).

**6. Provenance.** 2026-09-07 07:41/07:44, clean.

**VERDICT: c1 and c3 are DEPLOYMENT-REPRESENTATIVE and conservative** (M-4 makes
the sim's version harder). **c2's verdict is representative but its scenario is
one point on the wrong side of the knee** — sweep downward, as P3-2 said. **G7
is the only guarantee in the set whose verdict Part 1 does not threaten.**

### G8 — "robots of equal entitlement get equal service"

**1. Can the scenario produce the failure?** **Yes, and harder than P2-1
found.**

**2. Unscored parts — P2-1 scored G8's second half on `core` ONLY. It is also
carried on `sensor_dense`, and there it is worse.**

| clause part | artefact | PF | Reservation | TwoTier |
|---|---|---|---|---|
| Jain ≥ 0.90 (scored) | `core` | 10/10 | 9/10 | 7/10 |
| **epochs ≥ 1 s = 0** | `core` | 10/10 | **3/10** (longest **10.0 s**) | **7/10** (longest 4.18 s) |
| Jain ≥ 0.90 (scored) | `sensor_dense` | 10/10 | 0/10 | 9/10 |
| **epochs ≥ 1 s = 0 (NEW)** | **`sensor_dense`** | **10/10** | **0/10** | **4/10** |
| **`n_starved` = 0 (NEW)** | `sensor_dense` | 10/10 | **7/10** (max 2 of 30 flows) | 10/10 |
| **`n_never_granted` = 0 (NEW)** | `sensor_dense` | 10/10 | **7/10** | 10/10 |

**On the full clause, `sensor_dense` G8 is PF 10/10 · Reservation 0/10 ·
TwoTier 4/10** — TwoTier drops from 9/10, and Reservation was already 0/10.
Every one of these goes to **10/10 with the attach flag.**

**3. Part 1 dependencies.** **M-9 and M-6, both, opposed, and this is the row
where the opposition is sharpest.** A 10.0 s starvation epoch on a 10 s run
requires 100 consecutive 100 ms windows of exclusion, which **M-9's rescue
forbids**; and **M-6's cap** concentrates service on the top 4 ranked UEs, which
is the mechanism that *produces* such epochs. **Verdict, not margin, in both
directions.** **M-4** matters less (Jain is per-UE).

**4. Inert here.** On `sensor_dense`, **MFBR is 0 on all 30 flows** (P2-4), so
two-tier's MFBR-dependent protections are inert **on this cell specifically**;
PBR 0 on all 30 → LCP round 1 never runs at all (single flow per UE, so LCP is
degenerate anyway); padding/truncated BSR; the UL floor.

**5. Flag state.** `core.json` (N=8) and `sensor_dense.json` (30 UEs, 20 k
slots), both columns, no stagger, defaults otherwise.

**6. Provenance.** 2026-09-07, clean.

**VERDICT: NOT deployment-representative, and it is the row most exposed.**
Needs **M-9 AND M-6 built together.** Until then the published G8 row is wrong
on its own clause (P2-1) *and* the corrected figure is measured on a gate
narrower than deployed.

### G9 — "a robot joins or re-joins quickly, even on a busy cell"

**1. Can the scenario produce the failure?** **Partly, and there is a recorded
history of it not doing so** — CLAUDE.md's sixth empty-selection instance is
G9's own GT-6.3, where the scripted fade was **half the length of `t310`**, no
RLF was ever declared, **zero join events occurred, and M18/M19 reported instant
recovery.** Every number was correct for events that did not happen. The count
assertion added afterwards was itself degenerate (3.8 of 10 warm restarts, 1.0
of 5 cold cycles recorded; **0 of 50 cold attaches COMPLETED**).

**2. Unscored parts.** **0 of 4** (P2-1): warm p95 ≤ 1 s, attach ≤ 15 s,
post-RLF ≤ 10 s, neighbours unaffected. Bounds *are* stated; the artefact stores
**per-arm medians across runs** (`m18_p95_median`), so no success rate can be
formed. **A run is needed for all four**, and per the CLAUDE.md rule it must
assert the expected count **and** `n_never_completed`.

**3. Part 1 dependencies.** **The whole of P1-1/M-13: there is no RA
procedure**, so *"full attach-to-streaming ≤ 15 s"* is a bound on a procedure
that does not exist. **M-9** (a re-joining UE is exactly the estimate-free case
the 100 ms rescue covers), **M-2** (`rach_recovery_ms = 400` is unreachable from
`run()`), the control-plane row (no RRC messages, no SRB traffic).
**Verdict — there is nothing to move yet.**

**4. Inert here.** `JoinConfig.app_restart_*` and `pdu_session_*` — **0 slots in
every G9 result** (CLAUDE.md's dead-mechanism table); `RlfDetectorConfig`,
hardcoded in the driver and unreachable from `run()`; five driver counters
dropped by `RunRecord.from_summary`.

**5. Flag state.** `sweeps/rerun-2026-09-06/g9.json`, attach OFF, no attach
column (`g9_campaign.py` takes no such argument).

**6. Provenance.** 2026-09-06, before the audit fixes.

**VERDICT: NO NUMBER, and the largest build behind it.** Needs **RA + SRB
(Part 1's Part-4 item)** before G9 means anything; **M-9** and the join
mechanisms wired to `run()` before a re-join number does.

### G10 — "the cell hosts a stated fleet size"

**1. Can the scenario produce the failure?** **Yes, but too coarsely** (P3-1):
every arm goes 10/10 → 0–2/10 between N=8 and N=16, so the boundary is
unresolved in a 2× gap.

**2. Unscored parts.** The clause is *"largest N with **G1–G8** all-pass in 5/5
runs"*; the artefact carries the **GBR contract (M07) only** — the scorecard says
so in `claim_about`. So this is **1 of 8 sub-clauses**, the narrowest
substitution in the set. `g10_attach.json` also carries **`M08_fraction`,
`n_never_granted`, `never_granted`, `served_at_slot_1`,
`last_first_grant_slot`** — all unscored, all directly about the lock-out.
Forming the real clause needs the per-N runs to emit G1/G3/G5/G8's statistics,
i.e. **a run**.

**3. Part 1 dependencies.** **M-6 first and hardest** — the deployed cap binds
*more* as N grows, and N is this clause's own axis; at N=16 Reservation exceeds
it on **87.4 %** of UL slots. **M-9** opposes. **P1-1** (RA takes PRB/CCE before
data, and its cost is load-dependent while the sim's `overhead_factor = 0.85` is
not). **Verdict, decisively** — the admissible-N boundary is an upper bound
under P1-1 and M-6, and a lower bound under M-9.

**4. Inert here.** MFBR (`g10_rerun.py`'s own docstring records that configuring
it *"reversed three"* results); the UL floor; padding/truncated BSR; PBR on
everything but video.

**5. Flag state.** N ∈ {2, 4, 8, 16} × 10 seeds, 20 k slots, both columns.
**Note `g10_rerun.py` passes no `attach_seed_slots` at all**; the column split
comes from `g10_admissible`/consolidation, and P3-1's own table is the
authority.

**6. Provenance.** 2026-09-07 07:41/07:44, clean.

**VERDICT: NOT deployment-representative.** Needs **M-6, M-9 and P1-1's control-
plane resource cost** — and it is scoring 1 of its 8 sub-clauses regardless.

### G11 — "the guarantees hold for a whole shift"

**1. Can the scenario produce the failure?** **No — 10/10 with ~100× margin
over 7.2 M slots.** P3-2 marks it *"already at its axis; do not re-run."*

**2. Unscored parts.** **1 of 3** (P2-1) and the two unscored ones are declared
not-computable for structural reasons: **C3 CoV(p98) ≤ 15 %** is computed
*across* runs (one result, not n); **C4 identical PASS/FAIL** is *satisfied by
construction* (every run reports 0 failing windows) — **a check that could not
have failed**, which is CLAUDE.md's own third fault shape and is correctly
labelled as such. **C2 drift**: counters never wired; **6 of the C's 9
skip-reasons cannot exist here.**

**3. Part 1 dependencies.** All of them, weakly — a soak inherits every other
row's fidelity. **Margin, not verdict**, at 100×.

**4. Inert here.** The G11 drift detector (CLAUDE.md: built, tested, merged,
never wired); the UL floor; padding/truncated BSR; MFBR outside video.

**5. Flag state.** `sweeps/rerun-2026-09-06/g11_c1_soak.json`, attach **OFF**,
**and its "with attach" column is the same file** (see Q6).

**6. Provenance.** 2026-09-06 09:02, before the audit fixes; ledger checked by
P2-4 and clean (no flag was flipped against the same `--out`).

**VERDICT: representative as far as it goes, which is C1 only.** No Part 1 item
has to be built first; **C3 and C4 need a redesign, not a run.**

### G12 — "under overload, degradation follows the safety order"

**1. Can the scenario produce the failure the clause names?** **No for the
ordering half, and the module says so itself.** GT-7.3's ramp is *"+10 % steps
of the measured ceiling to 145 %"*, i.e. ×1.0 → **×3.3**. `sim/scenarios/g12.py`
records the measurement: within that range **only 5QI 2 breaches on every arm**,
so *"the order there is a ONE-ELEMENT list"*. The campaign extends to ×8.0 to
find a breach at all (5QI 4 first breaches at ×4.0 PF/TwoTier, **×6.0**
Reservation). **So the first-violation order cannot be tested inside the
guarantee's own specified ramp.** Clause 4 (never starve telemetry while a lower
class is served) **can** be, and is what is scored.

**2. Unscored parts.** **1 of 2** (P2-1): the ordering half is unscored *and*
untestable in-range as above. Clause 4 is scored, with the specification gap
recorded honestly (`tau` for "still has throughput" is not stated in the plan;
verdict robust for tau ∈ [0.01, 8] Mbps because the arms separate by ~2,800×).

**3. Part 1 dependencies.** **M-9 is a direct threat to clause 4's headline
result.** PF violates 20/20 by *"keeping 8.6 Mbps of background moving while
telemetry dies"* — and telemetry dying is a **candidacy** outcome, exactly what
the deployed 100 ms rescue prevents. **Verdict, and the direction is toward
PF.** **M-6** binds hardest at the ramp top, where every UE has backlog. **M-4**
bites here for the reason stated above: at the ramp top the TB is contended and
the sim's round-1 inversion (video ahead of telemetry) is at its most
consequential — **against telemetry, which is clause 4's subject.**

**4. Inert here.** The UL floor; padding/truncated BSR; PBR on telemetry and
background.

**5. Flag state.** `sweeps/g12-rescore-2026-09-06/g12.json`, 2 compositions × 10
seeds, RAMP ×1.0…×8.0, attach **OFF**, **"with attach" column is the same
file** (Q6). `tau = 1 Mbps`.

**6. Provenance — checked, and the scored artefact is clean; a NEIGHBOURING one
is not obviously so.** `g12_campaign.py` was one of the four `RunLedger` callers
the 08:13 fix touched, and this artefact (18:31) predates it. The scored
directory `g12-rescore-2026-09-06` **shows no bank line in its log at all** — it
ran its 720 runs fresh. **The adjacent `g12-fixed-2026-09-06` did not:** its log
line 16 reads *"g12.runs.jsonl: 120 run(s) banked for this configuration;
0 ramps still to run"* — **that artefact was produced entirely from banked
runs, under the pre-fix hand-listed key.** It is not what the scorecard reads,
and its `g12.log` is untracked in git. **Recorded so nobody reaches for the
wrong directory**, since the two differ by 1,686 bytes in a 410 MB ledger and
are otherwise indistinguishable by inspection.

**VERDICT: clause 4 is NOT deployment-representative — M-9 threatens its
headline.** The ordering half is **untestable in its own specified ramp** and
needs a scenario decision, not a fidelity build.

---

# THE OUTPUT THAT MATTERS — is this number deployment-representative?

**Old results are retired, not re-interpreted.** This table is the input to
that decision: what must be **built** before a fresh run produces a number
worth publishing.

| guarantee | current number | representative? | **must be built first** | scenario work also needed |
|---|---|---|---|---|
| **G1** | PF 10/10 · Res 10/10 · **TT 7/10** | **NO** | **M-1** (DL trace), **M-6** (DL cap), **M-2** (UL k2 — the same size as TwoTier's 2–4 ms miss) | a **DL-loaded** scenario; GT-1.1's saturating 5QI-9 DL does not exist |
| **G2** | 10/10 all arms (UL); **DL 10/10, newly scored** | **NO — scenario, not fidelity** | nothing; 25× margin absorbs M-2/M-4/M-6 | **GT-1.2 built**: saturation both directions, simultaneous STOPs, GT-7.2's 50 storms/run |
| **G3** parts 1–2 | 10/10 all arms | **YES, and conservatively** — M-9 and M-6 both push toward failure and it does not occur | — | resolution above N=8 to find where it does |
| **G3** part 3 | = G1's clause: **TT 7/10** | **NO** — inherits G1 | as G1 | as G1 |
| **G4** | **no number** | n/a | **M-2 (structural here, not marginal)**, M-9 | decouple silence length from payload; GT-2.3 buckets {1, 10, 60 s} |
| **G5** | PF 10/10 · **Res 3/10** · **TT 6/10** | **NO** | **M-9 AND M-6 together**, **M-4's BSD** (video's bucket is 2× oversized, flattering this row) | per-2 s-window goodput must be recorded |
| **G6** | **no number** | n/a | M-6, M-9, **M-4** (background has PBR 0 here, kBps8 deployed) | **paired unperturbed baseline**; a **DL** background flow (GT-4.2 is P0 and unbuildable today) |
| **G7 c1 + c3** | 10/10 all arms | **YES, and conservatively** — M-4 makes the sim's intra-UE split harsher than deployed, so the pass is a lower bound | — | — |
| **G7 c2** | PF 1/10 · Res 0/10 · TT 0/10 | **YES for the verdict** (insensitive to M-6/M-9; ratios ~2.0) | — | sweep **downward** from 2.1× to find where clipping starts |
| **G8** | `core`: PF 10/10 · Res 9/10 · TT 7/10 · **full clause: 10/3/7**; **`sensor_dense` full clause: 10/0/4 (NEW)** | **NO — the most exposed row in the set** | **M-9 AND M-6 together** | fleet size × `snr_spread_db` |
| **G9** | **no number** | n/a | **RA + SRB (the Part-4 build)**, M-9, `RlfDetectorConfig`/`JoinConfig` reachable from `run()` | GT-6.3's fade must outlast **t310 = 2,000 ms**; assert expected count **and** `n_never_completed` |
| **G10** | PF 30/40 · Res 23/40 · TT 26/40 (per-N: 8 / 4 / 4 — **SUPERSEDED 2026-09-09: PF 12 / Reservation 6 / TwoTier 7**) | **NO** | **M-6 (binds harder as N grows — N is this clause's axis)**, M-9, **P1-1's load-dependent control-plane cost** | N ∈ {10, 12}; and it scores **1 of 8** sub-clauses |

> **SUPERSEDED AGAIN 2026-09-09 — G10's boundary is PF 12 / Reservation 6 / TwoTier 7.** The banner below (6 / 6 / 5, itself a correction of 8 / 4 / 4) is ALSO withdrawn: it was measured while the 5QI-2 camera offered 3.8788 Mbps against its own 4.0000 Mbps GFBR, so the camera's CONTRACT bound the boundary rather than the cell's capacity (`docs/gbr-offered-shortfall-2026-09-08.md`). **Re-measured on current code 2026-09-09** — `n_ues ∈ {2,4,5,6,7,8,10,12,16}`, 10 seeds per point, cap 4, RA + SRB, `sweeps/g1-stress/g10_remeasure_cap4.json` — **PF 12 / Reservation 6 / TwoTier 7, reproducing the 2026-09-08 figure cell for cell, and NO arm is non-monotone.** Reservation did not move because its boundary was capacity-bound and therefore real. `docs/g1-stress-experiment-2026-09-09.md` §2.
>
> **SUPERSEDED 2026-09-07 — G10's boundary is PF 6 / Reservation 6 / TwoTier 5, not 8 / 4 / 4.** The old figure came from a sweep of `n_ues ∈ {2, 4, 8, 16}`, which put every arm's boundary inside an unresolved 2× gap. Re-swept on `{2, 4, 5, 6, 7, 8, 10, 12, 16}` with 10 seeds inside each point, at BOTH cap values, the boundaries are **6 / 6 / 5** — the arms are **near-identical, not 2× apart**. **PF is NON-MONOTONE** (9/10 at N=7, back to 10/10 at N=8, 9/10 at N=12); per the standing rule its boundary is the last passing point before the first failure, **6**, and the non-monotonicity is reported rather than smoothed. **A fleet sized on 8 is over-provisioned by ~30 %.** `docs/axis-table-2026-09-07.md` §2.
| **G11 C1** | 10/10 all arms | **YES as far as C1 goes** | — | **C3 and C4 need a redesign, not a run** (C4 cannot fail) |
| **G12 c4** | **PF 0/20** · Res 20/20 · TT 20/20 | **NO — M-9 threatens the headline** | **M-9** (telemetry starvation is a candidacy outcome), M-6, M-4 | the ordering half is **untestable in GT-7.3's own ramp** — a scenario decision |

**Three rows survive Part 1 intact: G3 parts 1–2, G7 c1/c3, G7 c2.** Two of the
three survive *because* the fidelity gap makes the simulator's version of the
test **harder** than the deployed one, which is worth saying explicitly — those
passes are lower bounds, not coincidences.

**Six rows need M-6 and M-9 built TOGETHER before their verdict means
anything: G5, G8, G10, G12 c4, and (via M-6's DL half) G1 and G2's DL column.**

# FINDINGS, RANKED

| # | finding | touches | invalidates |
|---|---|---|---|
| **1** | **G8's second half was never scored on `sensor_dense` either, and there it is worse.** Full clause: **PF 10/10 · Reservation 0/10 · TwoTier 4/10** (from 10/10 · 0/10 · 9/10). `n_starved` and `n_never_granted` are also carried and unscored (Reservation 7/10 on both) | **G8's second cell** | P2-1 scored G8's second half on `core` only. **TwoTier drops 9/10 → 4/10 on `sensor_dense`.** Everything clears with the attach flag |
| **2** | **G11's and G12's "with attach" column is the without-attach artefact.** `_nested()` hardcodes paths outside `SEV_DIR`, so `--attach`'s `replace()` is a no-op; neither campaign takes an attach argument | **2 of 12 rows, both columns** | The published table shows them identical in both columns, which reads as *"the flag does not affect them"*. **No with-attach run of either exists.** This is defect #31 read a **third** time, by its own documented symptom |
| **3** | **G2's artefact carries the DOWNLINK STOP column and the scorecard scores only the uplink one** — `DL_stop_p98_ms`, 2 DL stop flows, **10/10 on every arm, both columns, 0 starved**. GT-1.2's STOP is a **downlink** datagram | **G2's interpretation** | Same shape as P2-2's G1 finding, except here **the right column was already in the file**. G2 goes from 1 of 3 parts to **2 of 3** at zero cost |
| **4** | **G7 has THREE parts, not two, and the third is in the artefact and PASSES.** GT-4.3: *"B's other flows (its own telemetry!) still within SLO"* — **10/10 on every arm**, as do `A_camera_p98` and `A_telemetry_p98` | **G7's completeness** | No verdict moves, but P2-1's enumeration was against the guarantee-table line and **missed a part the GT spec states**. And the pass is **conservative**: M-4 makes the sim's intra-UE split harsher than deployed |
| **5** | **The simulator inverts intra-UE priority inside every UL transport block.** Exactly one flow in any built scenario has a non-zero PBR (5QI 2 video, 4 Mbps); telemetry, the DL command and background are all **0**, so LCP round 1 serves **video ahead of higher-priority telemetry**. Deployed config gives every non-GBR LC **kBps8** and halves video's bucket (BSD ms50, not ms100) | **every UL latency margin on the protected instrument** | Margin, not verdict, **at this load** — telemetry's `gap_p50` is 98.5 ms against its own 100 ms generation period, i.e. served on arrival. It becomes a verdict effect in the crumb regime and at G12's ramp top, **against telemetry, which is G12 c4's subject** |
| **6** | **The ten scored artefacts predate the ledger-key fix by 25 minutes** (07:38–07:51 vs `fe5e2f4` at 08:13). **They are clean** — separate `--out` dirs, and the columns are verified **different**, not assumed so | **P2-4's provenance claim** | P2-4's *"after the ledger-key fix"* described `rerun-2026-09-06`, not the directory the scorecard now reads. Conclusion unchanged; **the reasoning that supported it was wrong** |
| **7** | **G12's first-violation ordering is untestable inside its own specified ramp.** GT-7.3 says ×1.0 → ×3.3 (145 % of ceiling); within that only 5QI 2 breaches on every arm, so the order is a **one-element list**. The campaign extends to ×8.0 to find any breach | **G12's unscored half** | Not a defect in the campaign — `sim/scenarios/g12.py` measured and documented it. It means the ordering half needs a **specification decision**, not a run |
| **8** | **G1's downlink link is the idle link GT-1.1 says measures nothing.** Every 5QI-9 flow in every built scenario is uplink; only **160–214 slots per run** carry any DL grant | **G1, G6 (GT-4.2 is P0), G2's DL half** | The scenario cannot produce a DL failure, so P2-2's *"the command flow is passing comfortably"* is true but unearned — there is nothing for it to lose to |
| **9** | **Five of twelve guarantees are scored from an older sweep that was never regenerated after the audit fixes** (G4, G6, G9 from `rerun-2026-09-06`; G11, G12 from 09-06 dirs). And **`g12-fixed-2026-09-06` was built entirely from 120 banked runs under the pre-fix key** — not the scored directory, flagged so nobody reaches for it | evidence-base coherence | The seven scored rows and the five unscored ones are not from the same evidence base, and the table presents them as one |

**Nothing found here makes the rest of the audit unsound.** Finding #2 comes
closest — it invalidates two of the table's twenty-four cells — but it removes a
claim rather than corrupting one, and the without-attach half of both rows
stands.

---

**PART 3 CONTINUES IN `docs/mac-fidelity-audit-part3-2026-09-07.md`** — the
sweep specification for the fresh run. **Note it corrects this part's G6 entry:
the paired baseline DOES exist and G6 is scoreable today.**
