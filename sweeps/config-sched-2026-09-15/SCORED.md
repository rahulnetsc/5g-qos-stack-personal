# ConfigSched first measurement — scored (2026-09-15, after the artefact was read)

Artefact: `g3_probe.runs.jsonl` (ConfigSched, G3 part A, N ∈ {4 … 24}, cap 4,
seeds 0..2 of the campaign's ten, deployed cell, HEAD `993dfc7` = `1f5d105`
plus the prototype). Control: `sweeps/cell-2026-09-15/aligned/g3.runs.jsonl`
on the same three seeds. Tables: `compare_g3.py`. Two extra single runs
(seed 1826701614, N = 10 and N = 24) read the scheduler counters the G3
runner does not bank; their output is quoted in §2.

## 1. Expectations (`EXPECTATIONS.md`), scored

| | expectation | verdict | the number |
|---|---|---|---|
| E1 | telemetry part 1 passes every seed at N ≤ 16 | **HIT** | 3/3 at every N ≤ 16; worst silence ≤ 326 ms |
| E2 | head silence within 20 % of TwoTier's | **MISS** | median ratio 0.65 (range 0.07–7.1). Wrong premise: the head is attach + SR + *first ranking*, not the SR path alone, so an arm with no rank shortens it; at N ≤ 10 ConfigSched's head is 4.5–22 ms against TwoTier's 11.5–104.5. At N ≥ 12 every arm's head is 100–500 ms (24 attaches at t = 0) |
| E3a | telemetry part 1 at N = 24 | **MISS** | 0/3 — but see §2: Asset A's telemetry is 100/100 on every seed; the loss is the flood robot's own heartbeat (33–49 of 100 delivered, silences 730–967 ms) |
| E3b | `floors_unmet > 0` at N = 24 | UNSCORABLE from the artefact; **confirmed by the single run**: 10 500 over 1 000 re-solves = 10.5 camera floors unmet per window |
| E4 | part 3 no better than the other arms at N ≥ 12 | **MISS** at N = 24 only (2/3 vs 0/3) and it is the dropped-message artefact — p98 94.0 over 45 delivered messages; not a real gain |
| E5 | protected UL below PF's at N ≤ 8 | **MISS** | identical to PF's (16.1 / 24.2 / 28.2 / 32.2): below saturation every arm delivers the offered protected load, so the expectation could only have separated arms above N = 10. Above it: ConfigSched 41.3–42.6, PF 43.8–44.1, Proto 40.1–43.2 |

Two hits of six if E3b is counted, one of five if not. The misses are all
mis-specified expectations rather than surprises about the mechanism, except
E3a, which is the finding.

## 2. What the artefact says that the expectations did not ask

**Asset A's heartbeat is served as designed at every fleet size.** On the
instrument robot (`ue1_qfi1`) ConfigSched delivers 100/100 messages on every
seed at every N, with p98 31–37 ms at N = 24 (Proto 19.5 ms, PF 94.0 ms with
93/100 on the same seed). The rank is gone and the flood cannot demote it.

**The loss is the flood robot's own heartbeat, and it is worse than on any
other arm.** At N = 24, `ue24_qfi1` delivers 33–49 of 100 messages
(15–20 kB expired at the PDB), with silences of 730–967 ms; Proto delivers
95/100 with a 294 ms worst silence on the same seed, PF 94/100. Part 3 on
the flood robot is at the 99.5 ms expiry ceiling on every arm (the
intra-UE LCP/PBR effect the previous campaign already located there); what
ConfigSched adds is the *drop volume*.

The counters say why. At N = 24 the arm's own visit clock reports the
telemetry visits on time (`visits_late_qfi1 = 2` of ~2 400 stamped), so by
its own accounting nothing is wrong — while half the messages expire. Three
things line up:

1. **The visit interval equals the message period and the PDB.** The floor
   is `n_i ≥ ceil(W / PDB_i)` = one visit per 100 ms for a 100 ms message
   with a 100 ms PDB. A visit that lands just before an arrival serves
   nothing, is stamped anyway (service is attributed to the UE's due flows
   in planned order), and the message then waits the full interval — at
   which point it is at its deadline. Phase between visits and arrivals
   decides delivery. Visible at N = 10 too: `ue10_qfi1` p98 = 99.5 ms on
   all three seeds with ≤ 2 messages short, so the message is being served
   *at* the deadline, not lost — yet.
2. **Nothing else serves the flood robot.** Its flood is non-GBR with no
   share (leftover only, and at N = 24 there is no leftover); its camera
   floor is one of the ~10.5 per window that do not fit, and floors are
   placed in `(priority, PDB, ue_id)` order, so the highest `ue_id` — the
   flood robot — is the one whose camera floor is dropped. The telemetry
   visit is therefore its only grant, once per 100 ms. Asset A, whose
   camera visits (4 per window, ~15 kB) carry its heartbeat in the LCP's
   first round every 25 ms, never sees the problem.
3. **The gNB cannot see the miss.** The stamp is the gNB's attribution;
   the UE's LCP decides what a TB carries. What the gNB *could* read is
   the BSR that rides on the grant: if the telemetry LCG still reports
   bytes after the visit, the visit did not serve it. The prototype does
   not read it.

**Camera floors at N = 24: 96 Mbps offered against a 60.5 Mbps raw
uplink**, so `floors_unmet` is the honest report and no scheduler can meet
them; `rate_budget_bound` on 998–1 000 of 1 000 re-solves at both N = 10
and N = 24 says the PRB budget binds at every window from N = 10 (the
best-effort fillers and the flood always demand more than the cell).

## 3. What follows for the design (handoff §8b)

- **A visit-interval floor of PDB is not a deadline guarantee for a source
  whose period equals its PDB.** The interval has to leave the message
  time to be served: `n_i ≥ ceil(W / (PDB_i − period_i))` when the period
  is declared (the `+CGt` descriptor already carries it), or `ceil(2W /
  PDB_i)` when it is not — one more 300 B visit per heartbeat per window,
  which costs a cap slot and no PRBs.
- **A stamped visit must be confirmed, not attributed.** The per-LCG BSR
  after the grant is gNB-visible; a visit whose LCG still reports backlog
  should not advance the clock.
- **The floor tie-break decides who loses under overload, and `ue_id` is
  not a QoS quantity.** Under `floors_unmet > 0` the arm should drop the
  *largest* floors first or share the shortfall; dropping by declaration
  order is the same shape as the C's `connected_ue_list` victim.

None of this is built; the prototype stays as measured so the next change
is one fidelity change with this artefact as its before.
