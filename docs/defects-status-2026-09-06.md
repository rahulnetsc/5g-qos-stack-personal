# Defects log — every entry classified, and the sweep class re-asked

**2026-09-06.** Written before any further analysis, because the analysis is
built on this code. Status verified **against the code**, not against the log.

---

## 1. Classification

**F** fixed · **D** deliberately not fixed, with the reason · **O** open and
unaddressed · **M** superseded by measurement

| # | what | status | published result depends on it? |
|---|---|---|---|
| 1–9 | the first correction batch | **F** | four were verdict-changing; all corrected |
| 10, 13, 15 | per-run memory budgets (1 GiB / 8 workers / 2 workers) | **M** | no — the 2026-09-06 re-run measured the real thing: **30/30 runs at W=10, guard not tripped**. These budget estimates are moot, not open |
| 11 | a doc claim that `--check` was blind | **F** | no |
| **12** | `hol_delay_samples_s` is a `list`, not `array("d")` | **O** | **no.** Cost: one commit, value-identical (`_percentile` sorts a copy). **Worth ~12 % of residual, not the 49 % first claimed** — it is not a lever, which is why it has not been taken |
| 14 | per-process watchdog at the wrong aggregation level | **F** | no — the aggregate guard is what made the soak safe |
| **16** | C2's drift counters never wired in | **O, partly UNBUILDABLE** | **no** — C2 is reported as not scoreable. Cost is not just wiring: **6 of the C's 9 skip-reason counters cannot exist here** (no beam model, no `do_sched`, no `transm_interrupt`), so the honest version is a *different, smaller* statistic than the C's |
| 17, 18 | memory-budget provenance; an over-shot correction | **F** | no |
| 19 | transfer manifest never checked | **F** | no |
| 20.1 / 21 | nine dead scripts | **F** (2 fixed, 7 deleted) | no |
| 20.2 | `transient_check.py` reimplemented the slot loop | **F** (deleted) | no |
| **20.3** | four guards that cannot fire against the failure they name | **O** | **no**, but this is the same family as §2 below |
| 20.4 | `wp9_gate.py` silently omitted an axis | **F** | it did — corrected |
| 20.5–20.8 | a fix applied at 1 of 5 sites; mean-of-ratios; the un-fixed sibling | **F** | corrected |
| **22** | a published row contradicted by its own source file; **the proposed check was never built** | **O** | the row was corrected. The *check* — "every quoted figure names its artefact and its n" — is unbuilt. **`docs/STATE.md`'s table now does this by hand**, which is the convention without the enforcement |
| 23 | scripted events pinned to absolute time | **F** (all four sites, plus `schedule_guard.py`) | it did — G9 |
| **24** | the per-LCG BSR array's cold-start deadlock | **D** | **yes — and deliberately.** It reproduces `update_ul_qos_priority` exactly (`gNB_scheduler_ulsch.c:41-70`). Fixing it would diverge from the C in the direction of being better, which defeats the port |
| **25** | Tier-1.5's floor gated on the condition whose absence defines the fault | **D** | **yes.** `ia_p5g_scheduler.c:2325`. Same reason as #24 — this is a **product finding**, not a port defect |
| 26 | `summary` carries live objects, so identical runs compare unequal | **F** | no — compare `RunRecord.to_dict()` |
| 27 | M07 under a staggered arrival measures the stagger | **F** (documented; the attach-path work uses M05/M08) | it did — G10's boundary |
| **28** | **`flow_key` omits direction — asserted loudly, NOT fixed at the schema** | **O** | **yes, historically: G12.** §3 |
| 29 | the population defect in a denominator (CCE) | **F** at source, plus two generalising rules | it did — the "loaded, not bound" reading |
| **30** | G12's collision | **F at the SCENARIO, not at the MODEL** | it did; re-scored. §3 |

**Open and unaddressed: #12, #16, #20.3, #22's check, #28, #30's model-level
half.** Two are deliberate (#24, #25) and must stay that way.

---

## 2. §3 — the two the user named, and they are one defect at three layers

`flow_key` is `f"ue{ue_id}_qfi{qfi}"` (`sim/run_record.py:26`) — and the same
direction-blind key is used **three times, independently**:

| layer | key | consequence of a collision |
|---|---|---|
| `sim/buffer.py:55` | `dict[tuple[int, int], BufferState]` | `register()` **overwrites** — two flows share one queue, one `is_ul` flag, one FIFO |
| `sim/metrics.py:16` | `dict[tuple[int, int], FlowMetrics]` | two flows' bytes accumulate into one metric |
| `sim/run_record.py:26` | `ue{N}_qfi{Q}` | one record survives (now: **raises**) |

**So #28's guard catches the reporting layer only.** The buffer and metrics
layers have no guard at all, and the buffer layer is where G12's damage
actually happened — the record loss was 0.02 % of the figure, the shared
queue was the whole effect.

### What a schema-level fix costs

**Mechanically:** add direction to the key at the three sites. Call sites
that already have the flow in hand (`(f.ue_id, f.qfi)` → `(f.ue_id, f.qfi,
f.direction)`) — 11 in `buffer.py`, 7 in `metrics.py`, 7 in `run_record.py`,
plus scheduler lookups (30 in `two_tier.py`, 9 in `reservation.py`, 2 each in
the baselines). **All of them already hold the `FlowConfig`**, so direction
is available without threading a new parameter.

**Corpus impact: ~480 keys renamed** (20 records × ~24 flows), and — the part
that makes this cheap — **value-neutral**. No corpus scenario collides
(`scenario(1..7)` are all clean in the new sweep), so renaming merges and
splits nothing. **The re-baseline is a pure rename, and that is checkable:**
compare the multiset of values before and after; it must be identical.

**DONE IN PART, 2026-09-06, AND MY COST ESTIMATE WAS WRONG.** The buffer
layer took direction cleanly (`register()` already had `is_ul`), and
`_resolve` now **raises** on an ambiguous `(ue_id, qfi)` — verified: a
colliding scenario now fails **from `BufferModel`**, before the reporting
layer sees it. `--check` is **clean, no re-capture needed**, because
`flow_key` was not touched.

**The metrics and record layers are NOT done, and the "~25 sites" figure was
too low.** Direction is not in scope at their call sites: `traffic.generate`
yields `(ue_id, qfi, bytes)`, the expire loop iterates `buffers.keys()`, and
several per-flow dicts are keyed on the pair. Threading direction through
means widening those interfaces too — a wider change than costed, and its own
commit.

**What the partial fix already achieves:** a collision **cannot be simulated
silently**. That was the whole of the damage in #30; the remaining rename is
clarity, not correctness. It converts "a
collision is caught at the reporting layer after the simulation has already
been wrong" into "a collision cannot be constructed". Nothing published
currently depends on it — because G12 was the only collision and it is fixed
at the scenario — but that is a statement about today's scenarios, which is
exactly the thing that changed twice.

---

## 3. THE CATEGORY QUESTION — what other sweeps enumerate a set they cannot reach

The flow-key answer was wrong **twice**, both times structurally: the sweep
enumerated **nullary builders** and the failure lived in the **parameter
space of a parameterised builder**. The class:

> **An enumerator that defines its domain by something it cannot itself
> construct.** It reports "zero" over the set it *can* reach and the reader
> hears "zero" over the set they *care about*.

**Audited. Four more instances, and one is worse than the flow-key sweep.**

### 3.1 `verify_claims.py` — the worst instance, and it is cited constantly

It enumerates **claims someone registered** and verifies each against its
artefact. Nothing enumerates **figures we publish**.

**Measured:** `config/published_claims.yml` holds **8 claims referencing 3
artefacts**. `docs/STATE.md`'s guarantee table cites **13 artefacts**. **Two
of the thirteen have any registered claim.**

So *"verify_claims --check: 8 as expected"* — quoted in nearly every commit
message this month, including mine — means **8 of 8 registered claims hold**,
over ~15 % of the artefacts behind the guarantee table. It **cannot fail on
an unregistered figure**, and unregistered is the default.

**This is #22's unbuilt check, seen from the other end**: #22 proposed
"every quoted figure names its artefact and its n". Without it there is no
enumerable set of published figures, so the coverage gap is not merely
unmeasured — it is **unmeasurable**.

**Cost to close:** the enumerable set has to come from somewhere. The cheapest
honest version is not automation but a **coverage assertion against the
guarantee table**: every artefact in `STATE.md`'s table must have ≥1 claim,
failing loudly otherwise. That is ~13 rows to write once and a test to keep
it true.

### 3.2 `parallel_audit.py` — sound within `scripts/`, and that is its domain

Enumerates `SCRIPTS.glob("*.py")` and derives the runner/parallel split from
each file's **AST**. **The gap is narrow and mostly closed by construction:**
it reads structure rather than a grep, and `ALLOW_SERIAL` requires a named
reason. What it cannot reach is a runner **outside `scripts/`**, or one that
reaches the driver through a call it cannot resolve statically. **No instance
found.** Recorded as audited-clean rather than assumed.

### 3.3 `code_state.py` — the same defect, already found and fixed once

`_reachable_from` is a **static** import walk. It missed `sim/baselines/pf.py`
for two campaigns because the walk stopped at the `scripts/` boundary — the
identical shape, found on 2026-09-06 by the verification step rather than by
the tests. **Fixed** (traverses `scripts/`, fails wide on an unresolvable
named entry). **Residual gap: dynamic imports**, which a static walk cannot
reach by definition. None in `sim/`/`scheduler/` today.

### 3.4 `regression_corpus._cases()` — 20 hand-built cases

Enumerates the configurations **studies 1–3 run**. It cannot reach a
configuration nobody wrote down, and `--check` is silent about them.
**Deliberate and correctly scoped** — it is a *regression* corpus, not a
coverage claim — but it belongs in this list because "`--check` is clean" is
routinely read as a statement about the simulator rather than about 20 cases.

### 3.5 `config/metric_panel.yml` — deliberate, and already guarded

The panel enumerates pre-registered metrics; a metric not on it is invisible.
**That is the point** (multiplicity control), and the panel already forbids
silent removal. Listed for completeness, not as a defect.

### The generalising rule

**Every sweep must assert its own coverage, in the same file, in terms of the
set the claim is about — not the set the sweep can build.**

`test_flow_key_collision_sweep.py` now does this (a builder with no case fails
the coverage test). **The other four do not**, and §3.1 is the one that
matters, because its output is quoted as evidence.

**And the cheap tell, stated so it can be applied without re-deriving this:**
when a sweep reports **zero**, ask *"zero over what?"* — and if the answer is
a set the sweep itself constructed, the number is about the sweep, not about
the repository.
