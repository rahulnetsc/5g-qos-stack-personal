# Is the declaration-order tie-break faithful to the deployed C?

**2026-09-08. Investigation only — nothing changed.** This decides what
G12's first-violation order means.

**Short answer: it is faithful in practice and not guaranteed in principle,
and it is NOT a port defect.** The C ties on the same terms we do, its
pre-sort order is the same convention as ours, and on the libc this
deployment builds against its `qsort` preserves input order for equal
elements — measured, not recalled. But the C standard does not require that,
so the deployed product's order at a tie is **libc behaviour, not a designed
property of the scheduler**. And ties are far from universal: at G12's
ramp origin **32 % of UL slots contain a tie**, under load **5-8 %**.

---

## 0. The search surface, named

Per the standing rule, every file searched, and why the answer would be in
one of them.

**Searched (C):** `oai-branches/two-tier/{ia_p5g_scheduler.c,
ia_p5g_scheduler.h, gNB_scheduler_ulsch.c, gNB_scheduler_dlsch.c,
gNB_scheduler.c, gNB_scheduler_primitives.c, nr_mac_common.c,
nr_ue_scheduler.c, nr_ue_procedures.c}`, the same nine under
`oai-branches/reservation/`, and **the full checkout's entire
`openair2/LAYER2/` tree** (`Oai_Ran_QoS_Supported_MultiDRB`).

**Which file would contain a tie-break if one existed, and how that was
established:** not by filename. A tie-break can only live at a *sort site*,
so the search was for **`qsort`** — what the mechanism *uses* — rather than
for a name like "tiebreak". That enumerates the candidate sites exhaustively:
`LAYER2/` contains **exactly six** scheduler-relevant `qsort` calls, and the
three that can order G12's flows are:

| site | file | sorts | comparator |
|---|---|---|---|
| inter-UE, UL | `ia_p5g_scheduler.c:2963` | `ia_p5g_ul_ue_t[]` | `ia_p5g_ul_cmp` |
| inter-UE, DL | `ia_p5g_scheduler.c:1609` | `ia_p5g_dl_ue_t[]` | `ia_p5g_dl_cmp` |
| intra-UE, DL LCP | `ia_p5g_scheduler.c:1990` | `lcp_cand_t[]` | `lcp_cmp` |

**This is the two-tier arm's own scheduler.** The reservation arm's
equivalents are `gNB_scheduler_ulsch.c:2345` / `_dlsch.c:847`, both
`qsort(UE_sched, numUE, sizeof(UEsched_t), comparator)`. A fourth site,
`gNB_scheduler_primitives.c:3993`, sorts each UE's **logical-channel list**
and matters for question 4.

## 1. Which sort, and is it stable?

**Every one of them is `qsort`.** The C standard does not require `qsort` to
be stable, so this cannot be settled by reading the source — only by
measuring the libc the deployment links.

**The libc is glibc 2.39** (`ldd --version` → *Ubuntu GLIBC 2.39-0ubuntu8.8*)
— this machine's, and the machine whose path the calibration log's own
`CMDLINE` points at.

Measured directly (`scratchpad/qsort_stable.c`, 64-byte records matching
`UEsched_t`'s size class), sweeping `n = 2 … 4096`, with two shapes: all
elements comparing equal, and two interleaved equal-key groups:

```
elem size 64 bytes
  n=2 … n=4096   all-equal: ORDER PRESERVED    two-groups: ORDER PRESERVED
```

**At every size, glibc 2.39's `qsort` preserved input order for equal
elements.** The deployed `numUE` is single-digit, well inside the range
tested.

**What this does and does not license.** It licenses "the C ties the way we
do, on this build". It does **not** license "the C is stable": glibc has
changed `qsort`'s algorithm across releases, the standard permits any order,
and a different libc or a future glibc may reorder. **So the deployed
product's tie order is an implementation detail it inherits, not a property
it specifies** — which is the honest thing to say about any result that
rests on it.

## 2. Can the C's comparators return 0?

**Yes — explicitly, in all three, and the code says so in the return
statement.**

```c
static int lcp_cmp(...)          { if (priority differs) …; if (q >) −1; if (q <) 1; return 0; }
static int ia_p5g_dl_cmp(...)    { has_gbr …; pdb_ms …; coef …;            return 0; }
static int ia_p5g_ul_cmp(...)    { sched_inactive …; floor …; coef …;      return 0; }
```

`ia_p5g_ul_cmp` returns 0 in **two** places: when both candidates are
control-plane (`if (pp->sched_inactive && qq->sched_inactive) return 0;`)
and when their composite `coef` is equal. **So genuine ties exist in the C
on exactly the terms our flows tie on. The confound is not ours alone.**

## 3. Does the C's key contain a term the port dropped?

**No. Both keys match term for term.**

| | C | port |
|---|---|---|
| UL | `sched_inactive` → `floor_fire` (tie-broken on `floor_sil`) → `coef` | `_UL_TERMS = ("sched_inactive", "floor_fire", "-floor_sil", "-coef")` |
| DL | `has_gbr` → `pdb_ms` → `coef` | `_DL_TERMS = ("has_gbr", "pdb_ms", "-coef")` |
| intra-UE DL | `lcp_cmp`: `priority` → `q` | `_dl_fill`: `sorted(key=(priority_level, −vq_dl, …))` |

**So a tie that reaches our sort would also have reached theirs.** Nothing
breaks it earlier in the C that we discarded — which rules out the "port
defect, and fixing it resolves G12" branch.

One asymmetry, and it is spec-correct rather than a gap: the port's
**uplink** intra-UE split (`sim/ue_lcp.py`) orders on `priority_level`
alone. That is the *UE-side* LCP of TS 38.321 §5.4.3.1, where the gNB has no
say, so there is no C counterpart to drop a term from.

## 4. What is the C's pre-sort order?

**Inter-UE: attach order, the same convention as ours.** `UE_sched` is built
by `UE_iterator` walking `UE_info.connected_ue_list`; `add_UE_to_list`
appends at the first free slot and `remove_UE_from_list` `memmove`s to
compact, so that list is arrival order. Our declaration order is the
scenario's UE/flow order — the same "who arrived first" convention.

**Intra-UE: NOT arbitrary — it is sorted, and it can tie too.** Every
`nr_mac_add_lcid` re-sorts the UE's whole `lc_config` array
(`gNB_scheduler_primitives.c:3979-3993`) with `cmp_lc_config`, which
compares **`priority` only** and **returns 0 on equal priority**. So the C's
per-UE channel order is: priority, then whatever `qsort` leaves — from an
insertion order that is bearer-setup order, i.e. the DRB ordinal. That is
the same quantity our LCG renumber established as the port's own ordinal
(M-5), so the two agree here as well.

## 5. Our side, measured: how often do flows actually tie?

`scratchpad/tie_rate2.py`, TwoTier, cap 4, G12's own scenario
(`build_g12_scenario(8, "mixed", …)`), 6 000 slots. A tie is counted only
where it can decide something: **two candidates ADJACENT in the sorted order
with an equal key.**

| ramp point | UL adjacent pairs tied | UL slots with ≥1 tie | DL pairs tied | DL slots with ≥1 tie |
|---|---|---|---|---|
| **×0.5** (ramp origin) | 2 302 / 11 978 = **19.2 %** | 1 535 / 4 800 = **32.0 %** | 117 / 235 = 49.8 % | 37 / 2 400 = 1.5 % |
| ×1.0 | 609 / 22 411 = **2.7 %** | 272 / 4 800 = **5.7 %** | 115 / 232 = 49.6 % | 37 / 2 400 = 1.5 % |
| ×2.0 | 1 094 / 23 019 = **4.8 %** | 406 / 4 800 = **8.5 %** | 114 / 228 = 50.0 % | 37 / 2 400 = 1.5 % |

**And the intra-UE split is never decided by position at all: 0 ties out of
21 788 (×0.5) and 34 973 (×2.0) adjacent pairs on `priority_level`.** G12's
5QI 2 and 5QI 4 carry different standardised priorities, so within a UE the
comparator always decides.

**Reading it.** Ties are **not** the common case under load — at the loads
where violations happen, 92-95 % of slots are decided entirely by the
comparator. But they are **common at the ramp origin**, where the cell is
light, many UEs have equal (often zero) composite `coef`, and a third of UL
slots contain a tie. **DL ties are frequent as a fraction (≈50 %) but rare
in absolute terms** — only 1.5 % of slots have two DL candidates at all.

## 6. What this implies for G12's design

**1. TwoTier's `[2, 4]` is not disqualified as "our sort's artefact".** The
C ties on the same terms, from the same input order, and on this libc breaks
them the same way. Reporting the order as a scheduler property is defensible
— *with* the caveat in §1 that the tie-break is inherited from libc rather
than specified.

**2. It is not a port defect either**, so the third possibility — that
fixing a dropped term would resolve G12 outright — is closed. §3.

**3. The permutation control must stay, and it is currently confounded.**
`permute_flows` changes the flow list, which moves **two** things at once:
the tie-break order *and* every first-flow-found-wins lookup that reads
`self._flows` (`has_gbr`, `pdb_ms`, the LCG-0 estimate). A first-violation
order that moves under permutation therefore does not tell you *which* of
the two caused it. **The clean control is a tie-break-only perturbation:**
hold the flow list fixed and break ties on a seeded pseudo-random key
instead of on position. If the order survives that, it is a comparator
property; if it does not, it is a position property — and no permutation is
needed to say so.

**4. Report the tie rate beside the order.** The numbers in §5 are what let
a reader judge how much of a reported order is comparator and how much is
list position, and they differ by a factor of six between the ramp origin
and the loaded points — so a single figure for "G12" would be misleading.
The origin is the *most* tie-prone point on the ramp, which matters because
it is also the clean-control point.

**5. One thing to check when G12 is designed, not assumed here:** whether
the flows whose order G12 reports are ever *adjacent* in a tie. §5 counts
all adjacent ties; it does not yet ask whether the tied pair is a
(5QI 2, 5QI 4) pair specifically. That is a one-run measurement and it
should gate the reporting decision.
