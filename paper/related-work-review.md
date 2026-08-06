# Recent literature review

Search conducted 2026-08-06 to close the gap flagged in [README.md](README.md):
the draft's citations traced the foundational lineage (Kelly, Neely, Stolyar,
Tassiulas) and the classic QoS schedulers, but engaged with nothing from the
last few years.

**Method and its limits.** Web search over arXiv plus general search, then
each candidate's abstract page fetched to verify title, authors, date and
venue before citing. Six papers were verified this way and are now in
`refs.bib`; nothing is cited from a search snippet alone. This is *not* a
systematic review — no database query protocol, no coverage guarantee, and
paywalled venues (IEEE Xplore, ACM DL) were not searched directly. Treat it
as "enough to not look ignorant of the field", not as exhaustive.

One concrete reason verification mattered: Kela et al. was retitled between
its arXiv v1 ("Towards Practical Deep Schedulers for Allocating Cellular
Radio Resources") and its current version. Citing from the search snippet
would have produced a wrong title.

---

## What was found

### 1. The closest contemporary — industrial 5G QoS scheduling

**Kleinberger, Gundall, Schotten, "FLEX: Joint UL/DL and QoS-Aware
Scheduling for Dynamic TDD in Industrial 5G and Beyond"**, arXiv:2603.20971,
March 2026.

Directly adjacent: industrial 5G, QoS-aware, TDD, evaluated in ns-3 /
5G-LENA rather than on hardware. FLEX dynamically adjusts the UL/DL split in
flexible TDD slots while enforcing QoS priorities, and adds DL buffer-state
estimation to stop high-priority DL traffic starving.

**Why it helps rather than threatens us.** FLEX varies the TDD *pattern*;
we hold it static (an explicit non-goal) and vary what happens *within* the
per-direction budget. The two are complementary — a deployment could run
both. It also independently corroborates the premise that industrial traffic
asymmetry defeats stock schedulers. Worth citing in §III where we fix the
TDD pattern, as the thing we deliberately do not do.

### 2. Configured grants — independent corroboration

**Larrañaga, Lucas-Estañ, Lagén, Ali, Martinez, Gozálvez, "An open-source
implementation and validation of 5G NR Configured Grant for URLLC in ns-3
5G LENA: a scheduling case study in Industry 4.0 scenarios"**, *Journal of
Network and Computer Applications*, vol. 215, 2023, art. 103638.
(arXiv:2606.18763 is a later posting; cite the journal.)

The most useful find. An independent open-source CG implementation, in a
different simulator, evaluated on Industry 4.0 scenarios — and it reaches
the same conclusion we do in §VI-B, that CG scheduling policy dominates
latency for time-critical industrial traffic.

**This materially strengthens §VI-B.** Our strongest practical result is
that configured grants are structurally decisive; having an independent
group reach a compatible conclusion in a different simulator is exactly the
corroboration a reviewer will look for. It also slightly *weakens* our
novelty claim on that point, which we should absorb honestly: our
contribution there is the *double bypass* (PDCCH **and** BSR round-trip)
and the self-gating viability floor, not the observation that CG helps.

### 3. Learning-based scheduling — the dominant recent thread

**Yan, Lu, Zeng, Hou, "Near-Real-Time Resource Slicing for QoS Optimization
in 5G O-RAN using Deep Reinforcement Learning" (xSlice)**, *IEEE
Transactions on Networking*, vol. 34, pp. 1596–1611, 2026.
(arXiv:2509.14343.)

An xApp on the near-RT RIC doing online DRL over MAC-layer resource
allocation, formulated as regret minimisation over throughput, latency and
reliability. Notably evaluated **on a real O-RAN testbed with 10
smartphones**, not in simulation — which is a standard our paper does not
currently meet.

**Kela, Liu, Valcarce, "From Simulation to Practice: Generalizable Deep
Reinforcement Learning for Cellular Schedulers"**, arXiv:2411.08529,
November 2024.

Argues practical deep schedulers for real-time 5G do not yet exist, and
names the obstacles: real-time execution cost, 3GPP compliance, poor
generalisation across bandwidth / MIMO / traffic configurations, and the
complexity-performance trade-off.

**Why this pairing is the most useful thing in the search.** It gives us a
defensible positioning we currently lack. The recent field has moved heavily
to DRL; we are proposing something deliberately *not* learned. Kela et al.
is an argument from inside that literature for why deployability is hard,
and it supports our line that an interpretable convex program with a
one-number fairness dial is a reasonable answer for a deployment that must
be certified and reasoned about. We should make that argument explicitly
rather than leaving the omission of DRL unexplained — a reviewer will
otherwise ask why there is no learned baseline.

### 4. Two-timescale decomposition — our pattern is not novel

**He, Ren, Zhou, Mumtaz, Al-Rubaye, Tsourdos, Dobre, "Two-timescale
Resource Allocation for Automated Networks in IIoT"**, arXiv:2203.12900,
March 2022.

Lyapunov optimisation on the slow timescale, ADMM plus price-based matching
on the fast one, for IIoT with hybrid energy supply. Different objective
from ours, same decomposition logic: split by the granularity at which the
underlying quantities vary.

**This confirms the framing already in the draft** — "our contribution is
not the pattern but its concrete instantiation." Good that we said so; now
we can cite evidence rather than assert it.

### 5. OAI and private-5G testbeds — for §VII

**Villa et al., "X5G: An Open, Programmable, Multi-vendor, End-to-end,
Private 5G O-RAN Testbed with NVIDIA ARC and OpenAirInterface"**, *IEEE
Transactions on Mobile Computing*, 2024 (DOI 10.1109/TMC.2025.3580764;
arXiv:2406.15935).

An 8-node private 5G O-RAN testbed combining NVIDIA ARC-OTA, OAI and a
near-RT RIC. Not a scheduling paper, so it does not belong in related work
on scheduling — but it is the obvious reference point for §VII's
experimental setup once that section is written, and for justifying OAI as
the integration target.

---

## What the search did *not* find, and what that means

**No direct prior art for the knapsack diagnosis.** I searched specifically
for prior work framing soft-GBR-penalty scheduling as a fractional knapsack
with a vertex optimum, and found none. That is reassuring for §IV-C but it
is not proof of novelty: my search did not cover paywalled venues directly,
and this is exactly the kind of result that could sit as a lemma inside a
paper about something else.

**But the weaker version of the claim is established.** Search results state
plainly that utility-maximising schedulers "tend to allocate more time to
users with higher average SNR" and therefore do not guarantee fairness
across heterogeneous channels. This is *consistent with the correction we
already had to make* — the log utility is itself SE-favouring — and it means
§IV-C must be careful to claim only the sharp part:

- **Known:** utility maximisation favours high-SNR users.
- **Ours:** the *soft GBR penalty* makes the program a fractional knapsack
  whose optimum is a **vertex**, so the worst flow goes to exactly zero
  rather than merely being under-served — and no reweighting of that penalty
  can prevent it, because reweighting only selects a different vertex.

That distinction is worth stating explicitly in the paper. Claiming the
general "utility maximisation is unfair to the cell edge" as novel would be
wrong and would invite a reviewer to dismiss the whole contribution.

**Also seen but not cited:** PF-with-GBR variants (PFGBR) and the standard
device of giving GBR flows a utility with a steep slope below the guaranteed
rate and a shallow one above. This is prior art for "encode the contract in
the utility shape" and is arguably an alternative to our hard floor worth
one sentence of discussion — a piecewise-linear utility is another way to
avoid the vertex. I did not verify a citable reference for it, so it is
noted here rather than added to the paper.

---

## Applied to the draft

`refs.bib` gained six verified entries. §II was restructured from four
subsections to six, adding *Learning-based schedulers* and *Industrial and
private 5G*, and §IV-C now separates the known claim from ours.

**Cost: about a quarter page**, which comes out of §VII's budget. See
README.md for the revised space accounting.

## Still worth doing

- A proper database search (IEEE Xplore, ACM DL, Scopus) before submission.
  This was web search; it is not a substitute.
- Check whether any recent work does interpretable/convex scheduling with
  contract guarantees, as a counterpoint to the DRL thread. Nothing surfaced,
  but the search was not aimed at it.
- Find a citable reference for the piecewise-linear GBR utility, and add a
  sentence contrasting it with the hard floor.
