# Two experiments, registered before either is built

**2026-09-05.** The re-join seed (G9) and the BSR-desync question, taken
together because they are the same mechanism approached from two ends. Under
`prediction-journal.md` form rule 4: each names its **statistic**, its
**level**, and its **falsifier**.

---

## PART 0 — the classification question, answered first

**Model C is a scenario-level treatment. The re-join seed is NOT — it is a
mechanism change, and it needs the divergence justification.**

The distinction is *what supplies the trigger*:

| | trigger | who decides when |
|---|---|---|
| **Model C** (`attach_seed_slots`) | a **caller-supplied slot map** | the scenario. The driver holds a hook; the schedule comes from outside |
| **the re-join seed** | an **internal FSM edge** in `sim/join.py` | the simulator, reacting to its own dynamics mid-run |

**So it is a mechanism change and "it fixes G9" is not a justification.**

**The justification that is available, and it is the same one Model C
already rests on:** real hardware grants during attach and re-establishment
— RACH msg3, then RRC signalling on SRB — and those grants carry BSRs which
populate `estimated_ul_buffer_per_lcg[]` through
`update_ul_qos_priority`'s ordinary path. **This simulator has no RA
procedure and no SRB traffic model** (`has_srb` is hardcoded `False`), so a
re-attaching UE never receives the grant hardware would always give it. The
seed models the *effect* of a grant the sim omits, not a new capability.

**Stated as a divergence would be stated:** this makes the sim behave
*more* like the deployed system, by supplying an input the deployed system
has and the sim lacks. It does **not** change any scheduler, any ranking, or
any ported constant. If it changed what a scheduler *does* with the array,
that would be a different argument and this one would not cover it.

## PART 0b — AND THE EDGE I NAMED IS THE WRONG ONE FOR THE FAILING CLAUSE

**Found before building, by reading `sim/driver.py:316-335` rather than
assuming.** The driver already reacts to `radio_connected_this_slot`, and
its own comment says: *"warm never reaches here at all (radio never
drops)."*

**GT-6.1's warm path is an APP RESTART, not a radio drop.** So seeding at
`radio_connected_this_slot` would not touch G9's failing clause at all.

**How the warm path reaches the same fault, which is a different door into
one room:** the app stops → the flow's backlog drains → a BSR fires with no
active LCG → `on_ul_grant` memsets `estimated_ul_buffer_per_lcg` and
`_assemble` returns early on `fmt == "none"`, leaving it **all zero** → the
app restarts and backlog returns → but the array stays zero until the next
BSR, which needs a grant, which needs a ranking that reads the zeroed array.

**So the correct edge is `app_connected_this_slot`** (`sim/join.py:518`),
and the radio edge is the right one for the *cold* and *reestablish* paths.
**Both are needed; naming only the radio edge would have produced a change
that provably could not fix the clause it was built for.**

---

## PART 1 — the re-join seed (G9)

**Treatment:** fire `BsrModel.seed_attach_bsr` at **both** join edges —
`app_connected_this_slot` and `radio_connected_this_slot` — off by default,
behind one flag.

| # | statistic | level | prediction | falsifier |
|---|---|---|---|---|
| **1** | `expected_event_count` vs recorded warm events, TwoTier | **the count**, per arm | **10 of 10 on every arm** — the guard passes and G9 becomes scoreable for the first time | any arm below 10 |
| **2** | joiner slots with `bytes_reported > 0` and all per-LCG estimates 0 | **the fraction** | **falls from 17.2 % to near 0** on the warm path | above 5 % |
| **3** | M18/M19/M21 p95 `by_path`, median over seeds | per-arm scalar | **scoreable, and non-zero** | **a p95 of exactly 0.0 is the failure signature, not a result** — and `n_never_completed` must be checked before quoting any of them |
| **4** | neighbour Δp98 (joiner on − off), paired bootstrap | interval vs zero | **contains zero** | excludes zero |

**Clause 4's caveat, carried from the registration that found it:** ΔM02 on
the neighbours is **saturated at zero** and cannot move, so its "interval
contains zero" is satisfied by construction. **Δp98 is the only sensitive
instrument and clause 4 rests on it alone.**

**Bit-identity condition:** with the flag off, every existing artefact and
`--check` must be unmoved.

---

## PART 2 — the BSR-desync question

**This is the one that decides whether any of it transfers.** Model C
answers *"does a successful attach clear the lock-out"* — yes, at every
fleet size. It does **not** answer *"can a Short or Truncated BSR put an
ALREADY-SERVED UE back into the fault"*, **and that is the route hardware
takes, because hardware always grants during attach.**

**The mechanism to test, named from the code:** `sim/bsr.py::_assemble`
memsets `estimated_ul_buffer_per_lcg` and then repopulates **only the LCGs
the chosen format reports**. A **Short** BSR reports exactly one LCG
(TS 38.321 §5.4.5). **So a UE with backlog on three LCGs that sends a Short
BSR has two of its three estimates zeroed** — and if the zeroed ones carry
its GBR bearer, `has_gbr` goes false and `pdb_ms` reverts to 9999 while real
backlog exists. `sim/bsr.py`'s own docstring already calls this *"a DESYNC
rather than a stale read"*.

| # | statistic | level | prediction | falsifier |
|---|---|---|---|---|
| **1** | slots where a **served** UE (≥1 prior grant) has `bytes_reported > 0` and all per-LCG estimates 0 | **count > 0?** | **YES, it occurs** — Short BSRs are frequent (~1,080 per UE per run measured earlier) | zero such slots on every UE and seed |
| **2** | of those, how many persist ≥ 1,000 slots | **the duration distribution** | **most are SHORT-LIVED** — the next BSR repopulates | a heavy tail of long episodes |
| **3** | `n_never_granted` under Model C **with** a desync-inducing load | **the count** | **0 — the fault is entered but not LATCHED**, because a served UE keeps winning grants long enough to re-report | any UE never granted again after a desync |

**The registered meaning of each outcome, fixed now:**

- **If clause 3 finds a latched UE:** the frequency **transfers**. The
  cold-start route is sim-specific but the desync route is not, and G5's and
  G10's numbers become estimates of a real operational risk rather than
  upper bounds.
- **If clause 3 finds none, but clause 1 confirms transient entry:** the
  mechanism is **real and reachable on hardware, but self-clearing**. G5's
  and G10's numbers stay **upper bounds**, and we can say precisely why: the
  fault needs an entry that prevents re-reporting, and only a never-served
  UE has one.
- **If clause 1 finds nothing at all:** the desync is unreachable at this
  load, and the honest statement is that the question was not answered —
  the precondition did not occur, which is this project's own recorded
  failure mode and must be reported as that rather than as a negative
  result.
