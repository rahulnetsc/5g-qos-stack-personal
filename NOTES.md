# Working notes

Open issues, partial findings, and things to investigate next. Distinct
from [design-docs/](design-docs/) (what the architecture *should* be) and
[README.md](README.md) (what *works*). Append-only history of "we noticed
this but haven't acted on it yet."

---

## 2026-05-13 — Tier-1 LP behaviors surfaced by the 10-robot scenario

The uplink-heavy factory scenario in [configs/sim_config.yml](configs/sim_config.yml)
(24 flows: 10 robots with UL camera/LIDAR + DL control, 3 with extra PF
best-effort, 1 bidirectional TCP) exposes two TwoTier behaviors that
the prior 3-flow overload scenario didn't surface. Reproduce with
`make compare` and look at the "yaml" block.

### Headline numbers (per-flow delivery ratio)

| Flow | SNR | Class / target | RR | PF | Grad | TwoTier |
|---|---|---|---|---|---|---|
| ue1_qfi2 UL video | 22 | GBR 8M | 48% | 60% | 58% | **79%** ✓ |
| ue2_qfi2 UL video | 18 | GBR 8M | 37% | 44% | 49% | **71%** ✓ |
| ue3_qfi2 UL video | 20 | GBR 8M | 43% | 48% | 52% | **76%** ✓ |
| **ue4_qfi2 UL video** | **16** | GBR 8M | 37% | 40% | 47% | **8%** ⚠️ |
| ue5_qfi2 UL LIDAR | 24 | GBR 14M | 42% | 46% | 52% | **82%** ✓ |
| ue6_qfi2 UL LIDAR | 19 | GBR 14M | 29% | 31% | 42% | **86%** ✓ |
| **ue7_qfi2 UL LIDAR** | **14** | GBR 14M | 18% | 19% | 30% | **4%** ⚠️ |
| **ue8_qfi2 UL video + PF** | 21 | GBR 6M | 72% | 78% | 66% | **42%** ⚠️ |
| ue8_qfi9 UL best-effort | | PF | 73% | 67% | 34% | 37% |
| **ue9_qfi2 UL video + PF** | 17 | GBR 6M | 47% | 57% | 56% | **29%** ⚠️ |
| ue9_qfi9 UL best-effort | | PF | 49% | 46% | 24% | 17% |
| **ue10_qfi2 UL video + TCP** | 20 | GBR 6M | 58% | 73% | 63% | **42%** ⚠️ |
| All DL Delay control | | PDB 10ms | ~98% | 100% | 100% | 100% |

UL utilization saturates at 100% for PF / Grad / TwoTier (overload regime
as designed). DL is at 30–73% utilization (DL underloaded — Delay control
and TCP bulk all met).

### Finding 1 — Cell-edge starvation under soft GBR floors

UE 4 (16 dB SNR) and UE 7 (14 dB SNR) drop to 4–8% GBR delivery under
TwoTier vs 19–40% under plain PF. The higher-SNR UEs (1, 2, 3, 5, 6 at
18–24 dB) get 71–86% — *better* than PF.

The Tier-1 LP in [sim/tier1.py](sim/tier1.py) is trading cell-edge GBR
for system-wide log utility: each PRB given to UE 7 yields roughly 2 bits
per RE (SNR 14 dB → MCS staircase row at 13 dB threshold), versus ~4.5
bits per RE for UE 5 at 24 dB. Under utility maximization with *soft*
GBR floors, abandoning the expensive UEs lets more of the cheap ones'
GBR be met. Classic pathology of weighted-log objectives.

**Fix options to evaluate:**
- Hard GBR floors as inequality constraints — feasible-or-not, no
  graceful degradation. Could make the LP infeasible under deep overload.
- SNR-aware GBR weighting (down-weight cheap UEs so the LP sees them as
  less attractive to over-serve).
- Per-UE max-rate caps so high-SNR UEs can't absorb arbitrary capacity
  past their offered load (currently they can).
- Lexicographic / max-min on GBR before maximizing log utility — protects
  worst-case at the cost of total throughput.

### Finding 2 — Mixed-flow UE penalty (root cause unknown)

UEs that have GBR + at least one other flow on the same UE (UE 8, 9, 10)
get *worse* GBR delivery under TwoTier (29–42%) than under plain PF
(57–78%). Worse than doing nothing.

The PF best-effort flows on these same UEs *are* squeezed by TwoTier as
intended (37% / 17% vs PF's 67% / 46%). So the "sacrifice" behavior
works — but the GBR side of the same UE is also being squeezed, which
shouldn't happen.

**Hypotheses to test (in rough order of likelihood):**
- Tier-1 allocates a single per-UE-per-direction PRB budget across all
  the UE's flows, and the LP's split between GBR and PF on the same UE
  is wrong (favors PF in some regime).
- Tier-2 drift-plus-penalty weights on a flow are influenced by other
  flows on the same UE through some shared state.
- A bug in how per-flow `gfbr_bps` is read by the LP when multiple flows
  share a UE.

**How to investigate:** Add temporary logging in `sim/tier1.py` to dump
the per-flow target rates from the LP solution for UEs 8, 9, 10 and
compare against UEs 1, 2, 3 (single-flow UEs). If the LP is already
under-allocating GBR for the mixed-flow UEs, the bug is in Tier-1. If
Tier-1 says "give UE 8's GBR 6 Mbps" but Tier-2 only delivers 2.5 Mbps,
the bug is in Tier-2.

### Caveat on prior session's headline

The 2026-05-02 session reported "TwoTier delivers 97% of GFBR vs 57% for
PF" on an overload scenario. That scenario has 3 flows total (one GBR
UE, no SNR diversity, no mixed-flow UEs). The 10-robot scenario above
is a much harder test and TwoTier is a clear win on only 5 of the 10
GBR flows. Future claims should cite the 10-robot scenario, not just
the 3-flow overload.

### Where to start next session

1. Pick finding 2 first — root cause is small in scope and a clean win
   if it turns out to be a bug (vs design choice).
2. For finding 1, prototype hard-GBR-floors and see how the LP fails
   under deep overload. Compare against an SNR-aware weighting variant.
3. Each tweak: run `make compare` and check the yaml block. Lock in any
   improvements in this file (replace ⚠️ with ✓ once a finding is closed).
