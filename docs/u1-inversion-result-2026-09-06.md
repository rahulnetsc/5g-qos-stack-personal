# U1 — the workload inversion: RESULT

**Registered** `docs/u1-inversion-registration.md` (closed map, before any
run). **Artefact** `sweeps/phase2/u1_trace.json`, n=10 paired seeds × 3 arms ×
2 workloads, 20,000 slots. **Probe** `scripts/u1_trace.py`.

## Verdict: registered outcome **O4**, reached by the mechanism gate A0b
## named — and the registered candidate **O1 is REFUTED**.

**The inversion is not a scheduler-ranking property. It is an intra-UE LCP
interaction, and the rank trace — the instrument this was pointed at — is
structurally the wrong instrument for it.** A0b caught that before a single
swap-test number was read, which is the only reason this did not become a
confident answer about the wrong layer.

---

## 1. Gate A0b — the loss is not in the sort

The worst protected flow's UE, against its own fleet:

| arm | workload | UE's UL bytes ÷ fleet median | byte-rank of 10 | flow p98 / PDB |
|---|---|---|---|---|
| PF | parametric | 0.969 | 2.0 | 59.0 / 100 |
| Reservation | parametric | 0.969 | 3.5 | 32.4 / 100 |
| **TwoTier** | parametric | **1.003** | **5.5** | **94.9 / 100** |

**TwoTier's worst UE receives 1.003× the fleet median and sits dead centre of
the fleet's own byte order.** It is not being starved by the sort. Its
protected flow is nonetheless at 94.9 ms against a 100 ms budget.

## 2. The discriminator — grants existed, and the flow was skipped

For the protected flow's own 5QI, counting **the UE's own grants that carried
it nothing**:

| arm | workload | skipped p50 | **skipped p98** | % of UE grants carrying it | flow p98 |
|---|---|---|---|---|---|
| PF | parametric | 30 | **38** | 3.81 % | 59.0 |
| Reservation | parametric | 122 | **202** | 1.04 % | 32.4 |
| **TwoTier** | parametric | **0** | **310** | 0.84 % | **94.9** |
| PF | `sensor_dense` | 0 | **0** | 99.79 % | 14.5 |
| Reservation | `sensor_dense` | 0 | **0** | 98.49 % | 14.5 |
| **TwoTier** | `sensor_dense` | 0 | **0** | 99.53 % | **11.25** |

**On the parametric mix the protected flow waits through 38 / 202 / 310
grants its own UE received.** Fewer than 4 % of the UE's grants carry it at
all. **On `sensor_dense` it waits through zero** — there is no sibling to
lose to, and ~99 % of grants carry it.

**Every arm delivers the protected flows** (delivery ratio 0.976–1.000). The
difference between arms is **when**, not whether — and "when" is decided
inside the UE, after the scheduler has already handed over the TB.

## 3. Why TwoTier specifically

TwoTier grants this UE **11,804** times against PF's **1,630** for the same
byte total — many small grants rather than few large ones. Its LCP therefore
has the **best median** (skipped p50 = 0, served immediately most of the time)
and the **worst tail** (skipped p98 = 310). **A p98 metric reads the tail**,
so the arm with the most opportunities to serve the flow scores worst on it.

## 4. What refutes the registered candidate

O1 was *"Tier-1's objective favours periodic flows over saturating ones."*
Three findings against it, and the first is structural:

1. **There are no saturating UEs to disfavour.** All 10 parametric UEs carry
   the identical mix (periodic + XR + saturating UL). The sort ranks UEs, so
   it cannot express a preference between flow kinds.
2. **The favoured/disfavoured UE receives the fleet-median byte share.**
3. **The loss is measured downstream of the sort**, in a component the
   scheduler cannot address — the gNB **cannot see a UE's intra-TB per-flow
   split** (standing invariant), so no scheduler change reaches it.

The swap test over `coef = (base_q + urg) · hyp_tbs_bytes` was therefore not
read as an answer to U1. It measures which factor decides the *sort*, and the
sort is not where this happens.

## 5. Does it transfer to hardware?

**The mechanism transfers; the magnitude is not established.**

**Transfers.** UE-side logical-channel prioritisation is a real 3GPP
mechanism (TS 38.321 §5.4.3.1 — `Bj` token buckets, PBR, BSD), not a
simulator construct, and the gNB's blindness to the split is a property of
the air interface, not of this model. A real gNB that grants a UE in many
small TBs rather than few large ones will likewise interact with that UE's
LCP, and a periodic control flow sharing a UE with a saturating flow will
likewise be deferred inside the TB.

**Does not transfer as measured.** The *size* of the deferral tail is a
function of this repo's LCP parameterisation (`sim/ue_lcp.py`) and of the
parametric mix's specific 0.3 %-of-bytes provisioning for 5QI 1. Neither has
been calibrated against hardware. **310 skipped grants is this simulator's
number, not a prediction about a deployment.**

**What hardware has that this does not:** nothing missing here — this is one
of the few results where the sim is not short of a mechanism. What is missing
is *calibration* of one it has.

## 6. The consequence for the campaign, stated plainly

**"TwoTier is worst by 3.5× on latency" attributes to the scheduler an effect
produced by a component that is not the scheduler.** The three arms are
being compared on a statistic whose between-arm variance is dominated, on
this workload, by how each arm's grant *pattern* interacts with a UE-side
mechanism identical across all three.

That does not make the number wrong — TwoTier really does produce that p98 on
that workload. It makes the **attribution** wrong, and the attribution is
what "is two-tier needed" turns on.

**It also explains the inversion without any appeal to Tier-1's objective:**
`sensor_dense` has one flow per UE, so there is no sibling, no deferral, and
TwoTier wins on the ranking properties it was built for.
