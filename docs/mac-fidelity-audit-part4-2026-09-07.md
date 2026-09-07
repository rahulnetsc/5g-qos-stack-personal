# Part 4 — the build plan: cost, sequence, and what each step unlocks

**2026-09-07.** Last of four. Companion to Parts 1–3
(`docs/mac-fidelity-audit-2026-09-07.md`,
`docs/mac-fidelity-audit-part2-2026-09-07.md`,
`docs/mac-fidelity-audit-part3-2026-09-07.md`) and to
`docs/system-audit-2026-09-07.md`.

**Nothing built, nothing run.** Part 4 was scoped to cost RA+SRB; Parts 1–3
grew the set to **seven builds and two configuration fixes** before any fresh
run means anything for deployment. All of it is costed and sequenced here.

---

## 0. PORT OR INVENTION — stated first, because it decides the fidelity argument

**A port keeps the fidelity argument. Anything invented here does not**, and
must carry its own justification and its own registered prediction.

| item | kind | citation / basis |
|---|---|---|
| **M-9** 100 ms `high_inactivity` rescue | **PORT** | `gNB_scheduler_ulsch.c:1735-1766` (`nr_UE_is_to_be_scheduled`), called by **both** deployed schedulers (`_ulsch.c:2155`, `ia_p5g_scheduler.c:2299`); `ulsch_max_frame_inactivity = 10` frames from `MACRLC_nr_paramdef.h:125` **and** the deployment `.conf` files |
| **M-6** 4-UE-per-slot cap | **PORT** | `gNB_scheduler_dlsch.c:1019-1023` (`max_sched_ues`) and `_ulsch.c:3017-3021` (`max_dci`); `MAX_DCI_CORESET = 8` (`nfapi_nr_interface_scf.h:803`), `NR_NB_REG_PER_CCE = 6`, **N_RB 106 at mu 1** (`calibration-logs/twotier_startup_gnb.log:45`) → **4** |
| **M-4** LCP inputs (BSD, PBR) | **PORT** | `nr_radio_config.c:3686-3775` (`get_DRB_RLC_BearerConfig`) — PBR enum ladder, non-GBR `kBps8`, BSD ms20/50/100/150 from PDB |
| **M-5** LCG renumber (`LCG = DRB ID`) | **PORT** | `nr_radio_config.c:3781-3785`; the comment `// LCG = DRB ID, LCID = DRB ID + 3` appears in **both** branches (`gNB_scheduler_ulsch.c:51-52`) |
| **M-2** UL k2 on first transmission | **PORT** (of a structure, not a constant) | The k2 mechanism is TS 38.214 / OAI's TDA-row lookup; **the constant has no single canonical value** — `sim/driver.py:66-77` already says so. So the *structure* is a port; **the value stays a swept parameter** |
| **RA + SRB** | **PORT** for the procedure, **INVENTED** for the traffic | `gNB_scheduler_RA.c:337-342`, `gNB_scheduler.c:225-252` give the procedure and its scheduling priority. **But no SRB traffic model exists in the deployed logs** — message sizes and cadence would be invented and must be declared as such |
| **M-1** DL rank trace | **INSTRUMENTATION** | Neither port nor invention — it records what the existing comparator already computes. Bit-identity is a property of the code (`scheduler/rank_trace.py`'s own contract) |
| **Scenario builds** (GT-1.2, GT-7.2, G4/G6/G9 axes) | **OURS**, from the test plan | `docs/IA_P5G_Factory_Guarantee_Test_Plan.md` GT-1.2, GT-7.2, GT-2.3, GT-4.2, GT-6.1/6.3. The plan is the client-facing spec, not the deployed C — these carry a **specification** argument, not a fidelity one |
| **CFG-1 / CFG-2** | **CONFIGURATION FIXES** | Not builds. Neither changes behaviour; both change what a run is configured to be |

**Four of the seven builds are ports with line-level citations. One (M-2) is a
structural port with a parameter that stays swept. One (M-1) is instrumentation.
The scenario builds and SRB's traffic model are ours and must say so on every
row they produce.**

---

## 1. THE TWO CONFIGURATION FIXES — prerequisites, not builds

### CFG-1 — `wp9_sweep.BASE` diverges from the builder's own defaults on exactly one key

**The defect.** `sim/parametric.py`'s `sweep_scenario` defaults
`mfbr_multiple = 2.0`. `scripts/wp9_sweep.py:48-62`'s hand-listed `BASE`
overrides it to **0.0**. Every other key in `BASE` matches the signature
exactly. So `sweep_scenario(seed=s)` — which `sim/parametric.py:18` calls *"the
base cell"* — and `wp9_sweep`'s `BASE` are **different cells**, and the
difference is invisible at every call site.

**Why it went unseen, and this is the transferable part.** The artefacts record
an axis value only when it is *off-base*: in `sweeps/wp9/stage1/stage1_rows.csv`,
**1,740 of 1,770 rows have `mfbr_multiple` blank** and 30 carry `2.0`. **A blank
means "the base value", so the effective configuration cannot be read off the
artefact at all — you have to know `BASE`.** That is the same shape as CLAUDE.md's
restated-count rule: a value carried in prose (here, in a hand-written dict)
drifts silently from the code it describes.

**Blast radius, measured.** `BASE` is imported by `g4_postsilence.py`,
`g6_seed_extension.py`, `wp9_part_c.py`, `analyse_stage6.py`. So **G4 and G6 run
at MFBR 0 while G1/G3/G5/G8/G10/G7 run at MFBR 8 Mbps** — two-tier's
MFBR-dependent protections are inert on one half of the evidence base and live
on the other, and no row says so.

**THE FIX AT THE CATEGORY, not the site.** Do **not** edit `mfbr_multiple: 0.0`
to `2.0`. **Derive `BASE` from `inspect.signature(sweep_scenario)`**, exactly as
`regime_sweep.invocation_config` derives the ledger key from the parsed
arguments rather than a hand-list (commit `fe5e2f4`'s own reasoning: *"THE FIX IS
DERIVATION, NOT A LONGER LIST. A flag added tomorrow is in the key without
anyone remembering it"*). Any deliberate divergence goes in an explicit
`BASE_OVERRIDES = {key: (value, reason)}`, on the `parallel_audit.ALLOW_SERIAL`
pattern — **divergence on purpose is fine; divergence silently is the finding.**

**HOW I KNOW NO OTHER BUILDER CARRIES IT.** An AST scan over `scripts/` and
`sim/` for every module-level dict literal whose keys overlap `sweep_scenario`'s
parameters by ≥ 3, comparing each literal against the signature default:

| dict | overlap | diverges on |
|---|---|---|
| **`wp9_sweep.BASE`** | 10 | **`mfbr_multiple = 0.0` (default 2.0) — the only one** |
| `wp9_sweep.EXCURSIONS` | 7 | every key, **by design** — it is the off-base axis list |
| `wp9_sweep.STAGE2_GRID` | 3 | by design — a grid |
| `wp9_sweep.STAGE3_Q2` | 4 | by design — a grid |

**One base-point dict exists in the repo and it has exactly one silent
divergence.** The scan is the check that should ship with the fix, derived from
the AST rather than from a grep written into prose — the
`scripts/parallel_audit.py` precedent, which exists for this reason.

**Cost:** `scripts/wp9_sweep.py` + one test. **No corpus impact** (the corpus
uses the named scenarios, not `sweep_scenario`). **~1 hour.** **But re-running
G4 and G6 under the corrected base is a re-measurement**, and their current
numbers should be marked as measured at MFBR 0 until it happens.

### CFG-2 — `snr_spread_db` — and a CORRECTION to Part 3's finding #8

**Part 3 finding #8 said `snr_spread_db` "has never been varied". That is wrong
and is corrected here.** It *was* varied, in the WP9 regime sweeps:

| artefact | rows at 0.0 (blank) | at 6.0 dB | at 12.0 dB |
|---|---|---|---|
| `sweeps/wp9/stage1/stage1_rows.csv` | 1,710 | 30 | 30 |
| `sweeps/wp9/part_c_rows.csv` | 360 | **180** | **180** |

**The corrected statement is narrower and still serious: `snr_spread_db = 0.0`
in every artefact the GUARANTEE SCORECARD reads** — `core`, `sensor_dense`,
`g10_attach`, `g7`, `g2_ul_stop`, `g11_c1_soak`, `g12`. Channel diversity has
coverage in the **regime map** and **zero coverage in the guarantee evidence
base**.

**What that means for every channel-diversity claim so far.** At spread 0 every
UE has the same mean SNR (`sweep_scenario`'s `_snr_for(i, n_ues, 0.0)`), so:

1. **PF has been evaluated with its distinguishing mechanism disabled.**
   Proportional-fair scheduling is *opportunistic* — it exploits the fact that
   different UEs' channels differ. With identical channels PF's metric reduces
   to `1 / average_rate`, i.e. **round-robin with memory**. Every sentence in
   this project comparing "PF" to the QoS arms is comparing them to a
   degenerate PF. **This is the single largest thing CFG-2 changes, and it is
   not a fidelity gap — it is a scenario choice that removed the baseline arm's
   reason for existing.**
2. **`scheduler/link.py::cce_aggregation_level`'s 4/8/16 branches have never
   executed** in a guarantee run (Part 1 measured the histogram: `{1, 2}` only),
   so PDCCH cost has no dynamic range — which is *why* Part 1 found the CCE
   budget never binds.
3. **GT-3.3 (*"Cell-edge asset — the robot in the far corner still sees, and
   doesn't drag the others down"*) has never been run at all.** Its hard pass
   criterion — *"A's full SLO set unchanged within ε while B degrades"* — is a
   containment claim under channel asymmetry, and there is no evidence for or
   against it.
4. **G8's fairness claim is the equal-channel case only.** Jain ≥ 0.9 among UEs
   with identical channels is the easy half of the clause; *"robots of equal
   entitlement"* in a factory means unequal channels, and the interesting
   question is whether a scheduler equalises **rate** or **airtime**.
5. **`sim/pathloss.py` / `sim/blockage.py` (WP6) remain unreached** — an
   `inf_scenario` excursion exists in `EXCURSIONS` but not in any guarantee cell.

**Cost:** zero to fix — it is an axis in Part 3's `sensor_dense` grid already.
**The cost is admitting the scope of what it invalidates**, which is item 1.

---

## 2. THE BUILDS — cost, system-wide change, unlocks, risk

Effort is in **engineer-days on this project's own demonstrated rate** (WP-Join
delivered a per-UE FSM plus a buffer view in one work package).

### B1 — M-1: DL rank trace *(instrumentation)*

| | |
|---|---|
| **Files** | `scripts/trace_cells.py` (one line: `LossPointTally("UL")` → run both directions), the collector aggregation, `scripts/trace_read.py` |
| **scheduler/ changes** | **none.** The hook already fires for both directions (`two_tier.py:1354`, `reservation.py:1362`); only the *sink* filters |
| **Corpus** | **none.** `rank_sink` is bit-identity-checked by construction (`rank_trace.py`'s contract: every value recorded is one the arm already computed) |
| **Effort** | **0.5 day** |
| **System-wide** | Nothing changes in any run. It makes the **downlink comparator observable for the first time** — today `has_gbr`/`pdb_ms` appear in no tally for TwoTier because they are DL-only terms and the DL stream was discarded |
| **Unlocks** | **G1** (its clause names a DL flow), **G2's DL half**. Also retires the Part 1 caveat that P1-4's dead-tier table is uplink-only |
| **Risk** | **Lowest in the set.** The realistic risk is the opposite of invalidation: it may show a DL tier that *does* fire, which would mean P1-4's *"both QoS arms rank on `coef → pdb_ms → has_gbr`"* was a statement about uplink only — already flagged in Part 1 |

### B2 — M-9: the 100 ms `high_inactivity` rescue *(port)*

| | |
|---|---|
| **Files** | `sim/ul_access.py` (a `last_ul_grant_slot` per UE and a floor in `sr_report_floor()`), `sim/driver.py` (pass `slot_index` to `on_ul_grant`) |
| **scheduler/ changes** | **NONE — and this is the design point.** The established pattern is that eligibility reaches a scheduler through `bytes_reported` (`UlAccessModel.sr_report_floor` already does exactly this for SR) and that radio-layer gating composes by wrapping `BufferView`, never by editing scheduler code (CLAUDE.md). A `do_sched`-only UE in the deployed C gets *"one min_rb CTRL grant"* (`ia_p5g_scheduler.c:585-590`), i.e. **a `min_rb`-sized crumb — which is what a report floor produces.** The port is faithful *and* fits the pattern |
| **Corpus** | **RE-BASELINE, certain.** It creates UL grants that do not exist today |
| **Effort** | **1–2 days** including the count-and-completion assertions |
| **System-wide** | **Every starved UE becomes a candidate every 100 ms, in every arm.** It is a *candidacy* rescue, not a ranking one — it does not change where a rescued UE sorts, so a UE that is a candidate and loses can still starve. It also raises the UL grant count, which perturbs `HarqProcessPool.due_this_slot()`'s shared insertion order and can therefore move **DL** numbers (CLAUDE.md's cross-direction invariant) — **expect DL drift and do not read it as a boundary leak** |
| **Unlocks** | **G3, G5, G8, G10, G12 c4** — with **M-6**, six of Part 2's rows |
| **Risk** | It may make the attach-seed flag inert. **That is a result, not a failure** — but it means the with/without-attach column, which currently moves 6 of 12 rows, may collapse, and every conclusion drawn from that column becomes a statement about a mechanism M-9 supersedes |

### B3 — M-6: the 4-UE-per-slot cap, both directions *(port)*

| | |
|---|---|
| **Files** | `sim/resource.py` (`SlotGrid.max_dci`, derived as `min(prb_count // (4 × 6), 8)` — **derived from the grid, never a literal 4**, per the restated-count rule), and the grant loop of **all five schedulers**: `scheduler/two_tier.py`, `scheduler/reservation.py`, `sim/baselines/{pf,round_robin,gradient}.py` |
| **scheduler/ changes** | **YES — five files, unavoidable, and faithful.** The deployed C passes `max_sched_ues` *into* the scheduler (`ia_p5g_pf_dl(mac, ..., max_sched_ues, ...)`), so it is a scheduler input by construction. Each arm already carries `cce_left`/`prbs_left` counters in the same loop; this is one more |
| **Corpus** | **RE-BASELINE, certain and large** |
| **Effort** | **2–3 days** — the code is small; the verification is not, because it must be shown to bind per arm |
| **System-wide** | **Caps TwoTier on 46–49 % of its UL slots, Reservation on 87.4 % at N=16, and PF on 0.0 %** (Part 1, measured). **It is not a haircut — it is arm-differential**, which is exactly why it cannot ride with M-9. Ranking becomes far more consequential than it is today, since a mid-ranked UE currently gets served anyway |
| **Unlocks** | **G10 first and hardest** (the cap binds harder as N grows and N is that clause's own axis), **G8, G5, G12**, and **G1/G2's DL columns** |
| **Risk** | **The highest-variance of the four ports.** It removes service from mid-ranked UEs, which is the same population M-9 rescues. **If they are bundled the diff is uninterpretable** — that is the whole reason for the one-fidelity-change-per-commit rule. It may also make the CCE budget bind for the first time, changing what `cce_aggregation_level` means |

### B4 — M-4: LCP inputs — BSD and PBR from the deployed config *(port)*

| | |
|---|---|
| **Files** | `scheduler/flow.py` only — `effective_pbr_bps()` (enum ladder, round **up**; `kBps8` for non-GBR) and a `bsd_for_pdb()` derivation replacing the flat `bsd_ms = 100.0` default |
| **scheduler/ changes** | **In `scheduler/`, but not in a scheduler.** `flow.py` is configuration, not algorithm; no comparator or grant loop is touched |
| **Corpus** | **RE-BASELINE, certain.** It changes the intra-TB split on every multi-flow UL UE |
| **Effort** | **1 day**, most of it transcribing two tables from `nr_radio_config.c` **against the source text, not from memory** (CLAUDE.md's spec-table rule) |
| **System-wide** | **Un-inverts intra-UE priority in every UL transport block.** Today exactly one flow in any scenario has a non-zero PBR (5QI-2 video at 4 Mbps), so LCP round 1 serves **video ahead of higher-priority telemetry** and round 2 mops up. After: every non-GBR LC holds a `kBps8` bucket and enters round 1 in priority order, and video's bucket **halves** (BSD ms50 at a 150 ms PDB, not ms100) |
| **Unlocks** | **G1, G2's UL half, G3, G5, G7.** Note it makes **G7 c1/c3 EASIER** — Part 2 found the sim is currently running the harder version and passing, so those passes are conservative and will stay passes |
| **Risk** | **It moves G5 against itself.** Video loses round-1 share twice over (a smaller bucket, and competition from telemetry), so G5's completeness numbers should fall — and G5 is already the row with the worst arm separation. **Register that prediction before the diff.** Also: the non-GBR PBR is a **comment/code mismatch in the deployed source** (comment says PBR=0, code assigns `kBps8`); porting the code is the standing rule, but flag it rather than reconcile it |

### B5 — M-2: SR → grant → PUSCH latency *(structural port; parameter stays swept)*

| | |
|---|---|
| **Files** | `sim/driver.py` — a pending-UL-grant queue so a grant decided at slot *n* is filled and drawn at *n+k2*. Touches the `ul_access.on_ul_grant` / `bsr.on_ul_grant` / `ue_lcp.fill` / `harq_pool.allocate` call ordering |
| **scheduler/ changes** | **none** |
| **Corpus** | **RE-BASELINE, certain and large** — it shifts every UL delivery in time |
| **Effort** | **3–4 days.** The largest of the four ports by code, because the driver's slot loop currently assumes grant-and-transmit are the same event, and four subsystems key off that |
| **System-wide** | Adds **1–2 ms per UL grant** at numerology 1. Deeper backlog at grant-sizing time, so **crumb fraction should move toward hardware's 48–52 %** — the standing open question in CLAUDE.md's known-issues. It also gives `sr_prohibit_ms`/`sr_trans_max`/`rach_recovery_ms`/`sr_report_floor_bytes` somewhere to matter; **wire all four through `run()` in the same commit**, since they are currently unreachable |
| **Unlocks** | **G4 structurally** (*"first packet after silence"* **is** this round trip, and the sim prices zero slots for it), **G2's UL half**, **G1's margin** — TwoTier's three G1 failures are 2–4 ms over a 95 ms bound, the same size as the omission |
| **Risk** | **It can flip G1 in either direction and that is the point.** TwoTier at 7/10 could become 4/10 (latency added) — the likely direction. It could also *improve* it, if deeper backlog produces better-sized grants; that would be a real finding about grant sizing. Register both |

### B6 — M-5: LCG renumber, `LCG = DRB ID` *(port; prerequisite of SRB)*

| | |
|---|---|
| **Files** | `scheduler/flow.py` (`FIVE_QI_LCG` → a DRB-ordinal assignment starting at **1**, `DEFAULT_LCG` 7 retained as the cap), plus any scenario that sets `lcg` explicitly |
| **scheduler/ changes** | configuration only |
| **Corpus** | **RE-BASELINE, certain.** `sensor_dense` currently puts every UL flow on **LCG 0**; `factory_robots` uses 1/5/6. Renumbering moves the per-LCG BSR arrays on both |
| **Effort** | **0.5–1 day** |
| **System-wide** | **Vacates LCG 0, which is the SRB group in the deployed system.** Nothing else changes semantically — the per-LCG arrays are the same data at different indices. But it **removes the trap** Part 1 M-5 identified: wiring `has_srb` to the C's own predicate (`estimated_ul_buffer_per_lcg[0] > 0`) while data occupies LCG 0 would classify every telemetry-backlogged UE as having SRB traffic and promote it to the top tier permanently |
| **Unlocks** | **nothing on its own.** It is a **prerequisite of SRB** and should land separately and early, precisely so the SRB commit's diff is about SRB |
| **Risk** | Low, and mechanical. The one real risk is doing it *inside* the SRB work package, where its corpus movement would be inseparable from SRB's |

### B7 — The scenario builds *(ours, from the test plan)*

| | |
|---|---|
| **Files** | `sim/fleet.py` (a DL background flow; the GT-1.2 simultaneous-STOP trigger; GT-7.2's 5 × 300 B storm burst), `sim/scenarios/` (G4 silence decoupled from payload), `scripts/g4_postsilence.py` (**bucket edges at 1 000 / 5 000 / 10 000 / 60 000 ms** — today's top bucket is `1000 → inf`, so a 1 s and a 60 s silence are indistinguishable), `scripts/g6_seed_extension.py` (`load_mult` levels replacing the `bg` boolean), `scripts/g9_campaign.py` (`period_slots` as an axis) |
| **scheduler/ changes** | **none** |
| **Corpus** | **none** — new scenarios; the corpus runs `factory_robots_scenario` and friends |
| **Effort** | **3–5 days** across five separable pieces, each landable alone |
| **System-wide** | **The DL background flow is the biggest single item here** and is not only G6's: every built scenario is uplink-only in its background, so **only 160–214 slots per run carry any DL grant**. Adding it makes the downlink a contended resource for the first time — which is what B1's DL trace and B3's DL cap need in order to measure anything |
| **Unlocks** | **G2** (GT-1.2 + GT-7.2), **G4** (axis + buckets), **G6** (rate axis + the DL half, which is marked **P0** in the plan), **G9's warm and post-RLF thirds** |
| **Risk** | **These carry a specification argument, not a fidelity one**, and the plan contradicts itself in at least one place (G4's buckets: {1, 5, 60 s} in the KPI line vs {1, 10, 60 s} in GT-2.3). **Run both rather than choosing silently**, and raise the contradiction with the plan's owner. The DL background flow also changes every existing DL number, so it must land as its own scenario, not as an edit to the existing mix |

### B8 — RA + SRB *(one work package; port for the procedure, invented for the traffic)*

| | |
|---|---|
| **Files** | a new `sim/random_access.py` (PRACH occasions and their resource reservation, preamble selection/collision/backoff, the RAR window, Msg3 + HARQ, contention resolution — **six mechanisms, each with its own XOR'd seed stream** per the standing rule), `sim/resource.py` (PRACH/PUCCH/SRS reservation ahead of data, mirroring `gNB_scheduler.c:225-252`), `sim/fleet.py` (SRB1/SRB2 traffic), `scheduler/flow.py` (SRB flows on LCG 0), `scheduler/reservation.py` + `two_tier.py` (`has_srb` no longer hardcoded `False`) |
| **scheduler/ changes** | **YES**, and they are the point |
| **Corpus** | **RE-BASELINE, and the largest** — it changes what every arm is ranking on |
| **Effort** | **one full work package (10–15 days)**, and that is a **lower bound**: Part 1's estimate, on this project's own delivery rate |
| **System-wide** | Three distinct changes at once. **(i) RA consumes PRB and PDCCH before the data schedulers run** — `nr_schedule_RA` writes the same `vrb_map_UL` the UL data scheduler allocates from — and its cost is **load-dependent**, unlike the flat `overhead_factor = 0.85`. **(ii) SRB makes a dead top tier live in BOTH QoS arms** — `has_srb` is decisive **0 times in 5.6 M UL adjacencies** today and is the **top** tier in both directions on Reservation. **(iii) It replaces the cold-start lock-out's simulator-specific frequency with a mechanism**, so `attach_seed_slots` can retire |
| **Unlocks** | **G9's attach third** (*"attach-to-streaming ≤ 15 s"* is a bound on a procedure that does not exist), and it retires Part 1's largest fidelity finding |
| **Risk** | **THE HIGHEST IN THE SET, and it should be stated as strongly as Part 1 stated it: it may invalidate more published results than any other single change.** The direction is knowable — SRB traffic *promotes* a UE above GBR, so the deployed Reservation is **less** purely QoS-ordered than the simulated one — but the magnitude is not. **Two additional risks specific to it:** the SRB traffic model is **invented** (no message sizes or cadence exist in the deployed logs), so every result it moves rests on a number we chose; and it must land **after B6**, or the `has_srb` predicate reads data as control |

---

## 3. THE SEQUENCE

**Ordering principle: unlocks per unit of risk, with every re-baseline isolated.**
Five steps carry a `--capture`. **Each `--capture` states its justification and
its registered prediction BEFORE the diff is looked at** — the standing
discipline, and the reason the corpus exists at all.

**Representativeness is tracked against Part 2's table.** Rows already
representative and unchanged throughout: **G3 parts 1–2, G7 c1/c3, G7 c2,
G11 C1** (5).

### Step 0 — the two configuration fixes · **~1 day · no corpus movement**

CFG-1 (derive `BASE`, add the AST check) and CFG-2 (record that
`snr_spread_db = 0.0` in the whole guarantee evidence base, and that **PF has
been evaluated with opportunism disabled**).

**After step 0:** no row becomes representative. **G4 and G6's existing numbers
get a caveat** (measured at MFBR 0), and every PF-vs-QoS comparison in the
project gets one (equal channels). **This is the cheapest step and it changes
how everything already published must be read.**

### Step 1 — B1 (M-1, DL rank trace) · **0.5 day · NO re-baseline**

**After step 1:** still no row flips, but **G1's clause becomes measurable on
the flow it names** for the first time, and P1-4's dead-tier result is either
confirmed for downlink or refuted. **Do this first because it is free and it
tells you whether B3's DL half matters.**

### Step 2 — B6 (M-5, LCG renumber) · **0.5–1 day · RE-BASELINE #1**

*Registered before the diff:* the per-LCG BSR arrays shift index on
`sensor_dense` (all flows 0 → 1) and `factory_robots` (1/5/6 → 1/2/3); scalar
`bytes_reported` and every scheduler-visible quantity should be **unchanged**,
because the arrays are the same data at different indices. **A movement in
anything but per-LCG-indexed quantities is a finding.**

**After step 2:** no row flips. **The SRB trap is removed** and B8 is unblocked.
Landed early and alone so its movement is never confused with SRB's.

### Step 3 — B4 (M-4, LCP inputs) · **1 day · RE-BASELINE #2**

*Registered before the diff:* G5's PDU-set completeness **falls** on every arm
(video's bucket halves and telemetry now competes in round 1); G1/G3's telemetry
p98 and max-gap **improve**; G7 c1/c3 **stay passing** (the change makes them
easier, and they pass today under the harder version).

**After step 3:** **no row becomes representative on its own** — M-4 is
necessary for G1/G2/G3/G5/G7 but not sufficient for any of them. It goes third
because it is cheap, self-contained, touches no scheduler algorithm, and its
prediction is falsifiable in three directions at once.

### Step 4 — B2 (M-9, the 100 ms rescue) · **1–2 days · RE-BASELINE #3**

*Registered before the diff:* G8's starvation epochs **collapse** — a 10.0 s
epoch requires 100 consecutive 100 ms exclusions, which the rescue forbids;
`n_never_granted` on `g10` at N=8 (median 1.0 on Reservation) goes to **0**;
G5's Reservation 3/10 and TwoTier 6/10 **rise sharply**; the **attach-seed flag
becomes inert or nearly so**; and **DL numbers drift** on some records via
`HarqProcessPool.due_this_slot()`'s shared insertion order, which is expected
and is not a boundary leak.

**After step 4 — the first big representativeness gain:**

| row | before | after |
|---|---|---|
| **G3 parts 1–2** | representative | representative, **and now for the right reason** — today they pass on a gate narrower than deployed |
| **G8** | not representative | **still not** — needs M-6, which opposes |
| **G5, G10, G12 c4** | not representative | **still not** — same reason |

**M-9 alone does not make any row representative**, because every row it touches
is also touched by M-6 in the opposite direction. **That is the honest reading
and it is why the two are sequenced adjacently rather than far apart.**

### Step 5 — B3 (M-6, the 4-UE cap) · **2–3 days · RE-BASELINE #4**

*Registered before the diff:* **TwoTier and Reservation move, PF does not** —
PF grants effectively one UL UE per slot already (`frac > 4` = **0.0 %**), so a
`max_dci = 4` cap is slack for it and binds on 46–49 % / 87.4 % of the other
two's UL slots. G10's admissible N **falls** on both QoS arms; G8's starvation
**partially returns** (the cap concentrates service on the top 4 ranks); the CCE
budget may **bind for the first time**.

**After step 5 — six rows become deployment-representative:**

| row | status |
|---|---|
| **G5** | **representative** (M-9 + M-6 + M-4 all landed) |
| **G8** | **representative** |
| **G10** | **representative** on the GBR sub-clause; the full G1–G8 clause needs the core grid |
| **G12 c4** | **representative** |
| **G1** | **representative for its UL statistic**; the DL flow still needs B7's DL background |
| **G2 UL** | **representative**; the DL half needs B7 |

**This is the point at which a fresh run is worth doing.** Nine of twelve rows
are either representative or have no number for scenario reasons alone.

### Step 6 — B5 (M-2, UL k2) · **3–4 days · RE-BASELINE #5**

*Registered before the diff:* every UL latency rises **1–2 ms**; **G1's TwoTier
7/10 moves — direction unknown and both are registered**; crumb fraction moves
**toward** hardware's 48–52 % from today's 4.96 %; G2's margins fall from ×19 to
roughly ×13 and stay passing.

**After step 6:** **G1 and G2's UL columns are fully representative**, and
**G4 becomes buildable** — until M-2 exists, a post-silence number measures a
round trip priced at zero.

### Step 7 — B7 (the scenario builds) · **3–5 days · no corpus movement**

Five separable pieces; the **DL background flow first**, because B1's trace and
B3's cap both need a contended downlink to measure anything.

**After step 7:** **G2 (both directions), G4, G6 and G9's warm/post-RLF thirds
become answerable.** Eleven of twelve rows now have a representative design.

### Step 8 — B8 (RA + SRB) · **10–15 days · RE-BASELINE #6, the largest**

*Registered before the diff:* `has_srb` becomes decisive on a **non-zero**
fraction of Reservation's adjacencies (today 0 of 5.6 M) — **and if it does
not, the SRB traffic model is wrong, not the mechanism**; Reservation's ordering
moves toward **less** purely-QoS; **G10's admissible N falls again** as RA takes
PRB and PDCCH before data; the attach-seed flag can be **retired**.

**After step 8:** **G9's attach third becomes answerable**, and Part 1's largest
fidelity finding is retired. **Last, deliberately** — largest, riskiest, and the
one most likely to invalidate results the earlier steps have just made
representative.

### The schedule

| step | item | days | re-baseline | rows representative after |
|---|---|---|---|---|
| 0 | CFG-1 + CFG-2 | 1 | — | 5 |
| 1 | M-1 DL trace | 0.5 | — | 5 |
| 2 | M-5 LCG renumber | 1 | **#1** | 5 |
| 3 | M-4 LCP inputs | 1 | **#2** | 5 |
| 4 | M-9 rescue | 2 | **#3** | 5 |
| 5 | **M-6 cap** | 3 | **#4** | **11** |
| 6 | M-2 UL k2 | 4 | **#5** | 11 (+G4 buildable) |
| 7 | scenario builds | 5 | — | 11 (+G2/G4/G6/G9 answerable) |
| 8 | RA + SRB | 15 | **#6** | 12 |
| | **total** | **~32 days** | **6** | |

**Six deliberate re-baselines, each isolated, each with a registered prediction
scored afterwards** — including the misses, per the standing rule that a
prediction exercise cited only when it is right is not one.

**The cliff is at step 5.** Steps 0–4 cost ~5.5 days and move the count from 5
to 5. Step 5 costs 3 more and moves it to 11. **That is not a reason to skip
0–4** — M-9 must precede M-6 for the diffs to be interpretable, and M-4/M-5 are
cheap prerequisites — but it does mean **partial progress is not usable before
step 5**, and the plan should be committed to through step 5 or not started.

---

## 4. THE FRESH RUN — Part 3's sweep, attached

Executed **after step 5** for the six rows it makes representative, and
**re-executed after step 8**. From `docs/mac-fidelity-audit-part3-2026-09-07.md`:

| grid | axis | points | wall @ W=12 |
|---|---|---|---|
| core | `committed_mult` 1.0→2.3 @0.1 × `n_ues` {4,6,8,10,12,16} | 16 | 14 min |
| `sensor_dense` | `n_ues` {20…50} × **`snr_spread_db` {0,6,12}** | 18 | 7.8 min |
| G7 | `offer_x_mfbr` 1.0→3.0 × aggressor count {1,2,4} | 21 | 8.2 min |
| G12 | `committed_mult` 1.0→2.5 @0.1 × 2 cells | 32 | 28 min |
| G2 | STOP count {1,2,4,8} × saturation {none, UL, UL+DL} | 12 | 2.5 min |
| G4 | silence {1,5,10,60 s} | 4 | 13–21 min |
| G6 | background rate {0,0.5,1,2,4} × direction {UL,DL} | 10 | 8.8 min |
| G9 | join period {3200…200} × `n_neighbours` {7,15} | 10 | 8.8 min |
| G11 | — | — | **do not re-run** |
| **total** | | **~123** | **≈ 95 min, ~3,900 runs** |

**Two corrections to that table from this part.** (i) `snr_spread_db` is not a
new axis — it exists and was swept in WP9's regime map; what is new is putting
it in a **guarantee** cell. (ii) Every cost is measured on **current** code and
is a **lower bound**: M-6 changes what each scheduler evaluates per slot, and
M-2 adds a pending-grant queue to the driver's hot loop.

**Result shape is unchanged from Part 3:** boundary = last passing point before
the first failure; seeds stay inside a point, never pooled; non-monotone
sequences reported, not smoothed; *"passes to at least X"* where an arm never
fails, which is a statement about the sweep.

---

# FINDINGS, RANKED

| # | finding | touches | consequence |
|---|---|---|---|
| **1** | **`snr_spread_db = 0.0` across the entire guarantee evidence base means PF has been evaluated with its distinguishing mechanism disabled.** With identical channels, proportional-fair reduces to round-robin-with-memory | **every PF-vs-QoS comparison in the project** | The baseline arm that converts a measurement into a comparative claim has been run without the opportunism that defines it. **This is a scenario choice, not a fidelity gap**, and it is the cheapest thing on this list to fix — it is already an axis in Part 3's grid |
| **2** | **`wp9_sweep.BASE` is the ONLY base-point dict in the repo that silently diverges from its builder's own defaults, on exactly one key** (`mfbr_multiple = 0.0` vs 2.0) — established by an AST scan over every module-level config dict in `scripts/` and `sim/` | **G4 and G6's whole evidence base** | Two-tier's MFBR-dependent protections are **inert on G4/G6 and live on G1/G3/G5/G7/G8/G10**, and no row says so. **The category fix is derivation from `inspect.signature`**, on the `invocation_config` precedent, with divergences in an explicit reasoned override map |
| **3** | **A blank axis value in a WP9 artefact means "the base value", so the effective configuration cannot be read off the artefact** — 1,740 of 1,770 stage-1 rows carry a blank `mfbr_multiple` | how every WP9 artefact is read | This is *why* CFG-1 went unseen for months, and it is the restated-count rule in a new place. Any re-analysis of a WP9 CSV must resolve blanks against `BASE` **as it was at the time**, not as it is now |
| **4** | **Part 3's finding #8 was wrong and is corrected here:** `snr_spread_db` **was** swept — 60 of 1,770 stage-1 rows, 360 of 720 part-C rows | Part 3's finding #8 | The corrected claim is narrower and still serious: coverage exists in the **regime map**, zero in the **guarantee evidence base**. Recorded because a finding stated too broadly is retracted at full cost later |
| **5** | **M-9 alone makes no row representative, and neither does M-6 alone.** Every row either touches is touched by the other in the opposite direction | **the sequence** | **Steps 0–4 cost ~5.5 days and move the representative count from 5 to 5. Step 5 costs 3 more and moves it to 11.** The plan should be committed to through step 5 or not started |
| **6** | **M-9 can be ported with ZERO scheduler changes**, through the established `BufferView`/`bytes_reported` pattern — and the port is faithful, because a `do_sched`-only UE in the deployed C receives *"one min_rb CTRL grant"*, which is what a report floor produces | M-9's cost | Drops M-9 from a five-file scheduler change to a two-file one. **M-6 cannot be done this way** — the deployed C passes `max_sched_ues` *into* the scheduler, so it is a scheduler input by construction, and five files change |
| **7** | **M-5 (LCG renumber) is a prerequisite of SRB and must land separately and early.** Done inside the SRB work package, its corpus movement would be inseparable from SRB's | the sequence, and B8's interpretability | It is 0.5–1 day and unlocks nothing on its own, which is exactly why it would otherwise be folded into B8 |
| **8** | **The DL background flow is the hidden dependency of three builds, not one.** B1's DL trace and B3's DL cap both need a contended downlink to measure anything, and today only **160–214 slots per run** carry a DL grant | B1, B3, B7, G6 | It is listed under G6 in the test plan (GT-4.2, marked **P0**), which is why it reads as one guarantee's scenario problem. **It should land first within B7** |
| **9** | **Four of the seven builds are ports with line-level citations; the SRB traffic model is invented and no deployed log constrains it** | the fidelity argument | Every result B8 moves rests partly on message sizes and cadences we chose. **That must be stated on the rows it produces**, and it is an argument for landing B8 with a before/after column rather than in place |

**Nothing in Part 4 makes the audit unsound.** Finding #4 retracts a Part 3
claim, narrowing it; finding #1 widens the consequence of the same
configuration fact from "an unswept axis" to "the baseline arm was degenerate",
which is the largest single reinterpretation the four parts produced and does
not depend on any build.
