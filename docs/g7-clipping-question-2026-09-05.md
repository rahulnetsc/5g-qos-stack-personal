# G7: does the deployed C clip at MFBR? — answered, and the recorded blocker is wrong

**2026-09-05. An hour's grep, as scoped. The answer reclassifies G7 from
"structurally out" to "measurable, needs a scenario".**

## What was recorded

`docs/phase2-results.md`: *"**G7 — NOT MEASURED, structurally out.** No MFBR
*enforcement* anywhere in `sim/`. Containment is observable; **clipping is
not**, and clipping is half the pass criterion."*

**Both halves of that are wrong.**

## 1. The C clips — three sites, both arms, both directions

| file | line | what |
|---|---|---|
| `ia_p5g_scheduler.c` | **2663-2665** | two-tier UL |
| `gNB_scheduler_ulsch.c` | **2248-2250** | reservation UL |
| `gNB_scheduler_dlsch.c` | **397-399** | DL, `gbr_dl_max` |

```c
int _max_burst = (int)(_c->gbr_ul_max / 8) / (_spf_ul * 100) * 2;
if (_max_burst < _obl * 2) _max_burst = _obl * 2;
if (_target > _max_burst) _target = _max_burst;
```

The DL site carries the C's own comment: *"cap at 2x per-slot MBR to prevent
cell monopolisation"*.

## 2. The port implements all three, faithfully

`scheduler/two_tier.py:1581-1585` (DL) and **1748-1752** (UL);
`scheduler/reservation.py:1109-1113`. Same arithmetic, same `obligation * 2`
floor, same order. **So "no MFBR enforcement anywhere in `sim/`" is false.**

## 3. BUT WHAT IS CLIPPED IS THE GBR TARGET, NOT DELIVERED BYTES

This is the part that matters, and it is why the row's *conclusion* was
half-right for the wrong reason. Immediately after the clamp
(`two_tier.py:1761-1763`):

```python
overflow = lcg_estimate - target
if overflow > 0:
    be_bytes += overflow
```

**Demand above the clamp is not dropped — it is re-classified as
best-effort and remains eligible for delivery.** The clamp bounds how much
of a flow is treated as *guaranteed*; it is a priority mechanism, not a rate
limiter. **Entitlement is a ceiling on the guarantee, not on throughput.**

## 4. What that means for G7

GT-4.3's pass criterion is: *"A entirely within SLO; **B's camera delivered
≤ MFBR + tolerance** (excess clipped/queued at B, not exported to A); B's
other flows still within SLO."*

**That is a statement about DELIVERED BYTES, and delivered bytes are
measurable today** — no mechanism is missing. The clamp's existence is not a
precondition for measuring G7; **whether the clamp is sufficient to hold
delivery at or below MFBR is precisely the question G7 asks.**

**So G7 is NOT structurally out. It is a SCENARIO gap.** What is missing:

- **an aggressor scenario** — Asset B's camera offered at **2× MFBR**
  (encoder fault injection), Asset A on a full nominal profile. **Confirmed
  absent**: no GT-4.3 scenario exists, and `FlowConfig.aggressor_multiplier`
  is consumed in `sim/traffic.py:168` but **never set outside tests** — a
  standing class-B member.
- **a three-part verdict**: A's SLO, B's camera delivered vs MFBR, and **B's
  own other flows' SLO** — the criterion explicitly requires containment to
  hold *inside* the misbehaving asset, which is easy to drop.

**Reclassified: scenario + metric, cost S–M, SCOREABLE ALONE.**

## 5. A caution about the likely outcome, stated so it is not a prediction

Because overflow becomes best-effort rather than being discarded, **there is
no mechanism in either the C or the port that bounds B's *delivered* rate at
MFBR** whenever spare capacity exists. If G7 is run, a FAIL on the middle
clause is the outcome the code structure points at. **That would be a
product finding — the deployed scheduler does not implement MFBR as a
delivery ceiling — not a simulator gap**, and it is the same shape as the
Tier-1.5 dead gate: read from the C's own source.

**It is registered here as a structural expectation, not scored**, because
no run has been made. Note also the `aggressor_multiplier` known issue: for
an `xr_video` flow it scales fragments *after* fragmentation and can exceed
`fragment_bytes` — for a camera aggressor, scale `traffic_params["avg_bytes"]`
instead.

## 6. Correction to the record

`docs/phase2-results.md`'s G7 row and `docs/build-inventory-2026-09-05.md`'s
item B1 both said the mechanism was absent and flagged a possible
divergence. **There is no divergence: the port matches the C at all three
sites.** Both are corrected. The inventory's B1 moves out of class B
(built-but-unreachable) into class D (a route not modelled) — **the
mechanism is reachable and reached; the scenario that would exercise it does
not exist.**
