# IA-P5G Service Guarantee Test Plan — Private-5G Factory Automation (Multi-Asset MEC Fleet)

> **Audience:** the test team executing this campaign, and (in summarised form, §9) the client evaluating the technology.
> **System under test:** the IA-P5G two-tier QoS scheduler (gNB, `twotier-phase2`), carrying **Boundary-A traffic** of the MEC Aggregation System (robots ↔ MEC) in a private-5G factory deployment.
> **Companion documents:** `02_System_Architecture.docx` (MEC system, asset types), `IA_P5G_Scheduler_Benchmark_Suite.md` (mechanism characterisation — the *diagnostic* layer beneath this plan, see §10).

---

## 0. What this plan is — and how it differs from the characterisation suite

The earlier benchmark suite answers an **engineer's** question: *which scheduler mechanism works, where, and why does it break?* It sweeps abstract asymmetry axes and produces a KPI map.

This plan answers the **client's** question: *if I put my robot fleet on this network, what am I promised?* Every test here is the validation of one **service guarantee** — a statement a factory operator would actually ask for before committing production to this technology, phrased in their terms:

- *"A stop command always reaches every ground robot within its deadline."*
- *"The network will never make a healthy robot look dead."*
- *"Operators and the AI always have fresh video, even when someone pushes a firmware update."*
- *"One misbehaving robot cannot take down the fleet."*
- *"When the cell is genuinely overloaded, video degrades before safety — never the reverse."*

Every test uses **two or more assets** (per the testing team's architecture: UGVs and UAVs behind one MEC), because in a factory the guarantee only matters *in the presence of the rest of the fleet*. The classic GBR-vs-non-GBR isolation tests are retained (family GT-4) but they are one family among seven, not the frame of the whole campaign.

**Output of this campaign:** a filled-in **Guarantee Sheet** (§9) — for each guarantee, the measured bound, the confidence it was demonstrated at, the load conditions it held under, and the environment (rfsim vs real RF) it was demonstrated in.

---

## 1. The deployment under test — what actually rides the 5G link

From the architecture document, the MEC aggregates many 5G-connected robots (UGVs and UAVs). Two protocol boundaries exist; **only Boundary A (asset ↔ MEC) traverses the 5G air interface**. Boundary B (MEC ↔ operator UI, WebSocket/WebRTC) is on the wired side and out of scope here.

Boundary-A traffic per asset, and why each stream's delivery is *functionally* critical:

| # | Stream (dir) | Transport / model | Functional consequence of failure |
|---|---|---|---|
| T1 | **Telemetry / heartbeat (UL)** | msgpack (UGV) or MAVLink (UAV); low-rate periodic; shares one bidirectional port with inbound commands | **Liveness.** The MEC declares the session lost when telemetry stops → asset shown offline, re-handshake forced. A scheduling stall here is a **false failsafe**: ground robots are told to stop; UAVs fall to autopilot failsafe. Network-induced production halt. |
| T2 | **Commands (DL)** | cmd_vel (UGV drive), gimbal / flight-mode / arm (UAV), and the disconnect-safety **STOP**; same port as T1 (NAT-safe return path) | **Safety and controllability.** Late cmd_vel = sluggish/unsafe teleop. Late or lost STOP after master disconnect = uncontrolled ground robot. This is the guarantee a safety review asks about first. |
| T3 | **Camera video (UL)** | RTP/H264 push (UGV), RTSP-pulled (UAV); one port per feed; frame = PDU set | **Perception.** Feeds both the operator's view and YOLO inference. The MEC is **latest-frame-only**: a late frame is *discarded*, so freshness and frame completeness are the KPIs — raw throughput alone proves nothing. |
| T4 | **Lidar / bulk sensor (UL)** | msgpack sweeps, bursty, one port per feed | Situational awareness; heavy class deliberately port-isolated from T1/T2 in the MEC design — the network must honour the same isolation. |
| T5 | **Handshake (UL/DL)** | UDP :9000 capability sheet + port-assignment reply; also re-handshake after liveness loss | **Fleet elasticity.** Governs how fast an asset joins, and how fast it *recovers* after an outage. |
| T6 | **Best-effort (both)** | logs, mission data, firmware updates | Must never impair T1–T5; must still make progress eventually. |

Two architecture facts shape the whole plan:

1. **Liveness is inferred from traffic.** There is no separate keep-alive channel; the *scheduler itself* is in the liveness loop. The known BSR-desync / candidacy-loss failure mode of the UL path is therefore not a performance nuisance here — it is a **false-failsafe generator**, and GT-2 exists to bound it.
2. **Latest-frame-only AI.** The correct video KPIs are PDU-set completeness within deadline and frame *age* at the MEC, per the 3GPP XR convention — not sustained Mbps.

---

## 2. Asset ↔ testbed mapping

Current testbed: 2 OAI rfsim UEs (containers `oai-ue1`/`oai-ue2` on the ROG laptop) against the gNB + free5GC on the core PC; direct GbE; TDL_C channel model available. Real-RF A/B run planned.

| MEC role | Asset A (UE1, IMSI …2166, 10.60.0.10) | Asset B (UE2, IMSI …2167, 10.60.0.11) | 5QI (PDB / PER) | Harness role → server 5-tuple |
|---|---|---|---|---|
| T1 telemetry (UL) + T2 commands (DL) | UGV-A heartbeat + cmd_vel | UGV-B / UAV-B heartbeat + commands | **5QI 1** (100 ms / 10⁻²) | `sensor` → `.151:9002` / `.154:9002` |
| T3 camera (UL) | UGV-A front camera | UGV-B front camera | **5QI 2** (150 ms / 10⁻³) | `camera` → `.150:9001` / `.153:9001` |
| T4 lidar / second feed (UL) | UGV-A lidar | UGV-B lidar | **5QI 4** (300 ms / 10⁻⁶) | `streaming` → `.152:9003` / `.155:9003` |
| T6 best-effort | firmware/logs | firmware/logs | **5QI 9** (non-GBR) | `bg` → `.160:9004` |

T2 (DL commands) rides the T1 5-tuple in the reverse direction, exactly as the MEC's shared telemetry/inbound port does — DL classification onto the 5QI 1 bearer follows from the same server-side filter.

### 2.1 Right-sized QoS profile (**required change before the campaign**)

The current provisioning is flat 5 Mbps GBR on all three flows — flagged in the session handoff as the biggest gap versus the research question, and it breaks this campaign twice over: (a) a heartbeat with a 5 Mbps GFBR is never meaningfully "within GFBR", so 3GPP PDB conformance semantics don't attach; (b) 2 UEs × 3 × 5 Mbps = 30 Mbps committed almost certainly exceeds the (unre-measured) UL ceiling, so the committed portfolio is infeasible before the first test runs.

Proposed `factory_fleet` provisioning profile (add to `PROFILES` in `p5g_subscriber_provision.py`; values to confirm against GT-3.2's ceiling measurement):

| Flow | GFBR | MFBR | Offered (nominal) |
|---|---|---|---|
| sensor / telemetry (5QI 1) | 0.5 Mbps | 2 Mbps | 10 Hz × 300 B ≈ 24 kbps (UGV) / MAVLink ≈ 10–30 kbps (UAV) |
| camera (5QI 2) | 4 Mbps | 8 Mbps | XR model, 30 fps, mean 4 Mbps |
| streaming / lidar (5QI 4) | 3 Mbps | 6 Mbps | 10 Hz sweeps, bursty, mean 3 Mbps |
| bg (5QI 9) | 0 | 100 Mbps | saturating |

Committed sum: 7.5 Mbps/asset, 15 Mbps cell-wide — inside the ~12 Mbps historically-known floor only marginally, which is precisely why **GT-3.2 doubles as the post-clamp-fix ceiling re-measurement** and gates the final numbers.

> ⚠ **Latent regression to re-check after right-sizing (F8e from the characterisation suite):** the UL floor's arming has historically depended on GBR over-provisioning keeping the deficit pinned. With right-sized GFBRs, verify in GT-2.2 logs that `[P5G-UL-FLOOR]` still arms and fires. If it does not, that is a P0 finding before anything else runs.

### 2.2 Traffic models (reused from the characterisation suite, mapped to roles)

- **M1 CBR** — telemetry instrument: 10 Hz × 300 B (UGV) or MAVLink cadence (1 Hz HEARTBEAT + 4–10 Hz streams). *Keep identical across all tests so latency numbers stay comparable.*
- **M1-DL** — command instrument: 20 Hz × 100 B cmd_vel while "driving"; single-datagram STOP / mode-change events on trigger. *(Requires the DL-sender harness extension — prerequisite P5, §6.)*
- **M4 XR** — camera: 30 fps, truncated-Gaussian frame size (σ ≈ 10.5 %, clip 50–150 %), ±4 ms jitter, one frame = one PDU set.
- **M3 on-off** — lidar: 10 Hz sweep bursts, 50 % duty.
- **M5 full buffer** — best-effort load source only, never a KPI subject.

---

## 3. The guarantee catalogue (client-language SLOs)

Numbers marked ▷ are **proposed defaults** to be ratified with the client; the test machinery is unchanged whatever the number becomes. `T_live` = the MEC's liveness timeout (not stated in the architecture doc — **confirm with the MEC team**; ▷ assume 2 s).

| ID | Guarantee (as the client would state it) | Normative KPI |
|---|---|---|
| **G1** | Every drive command reaches the robot in time to feel responsive. | cmd_vel one-way p98 ≤ RAN PDB (▷ 95 ms of the 100 ms 5QI-1 budget, §5); p99.9 reported. |
| **G2** | A STOP always lands, on every ground robot, fast — even at worst-case load. | 100 % of STOP events ≤ ▷ 100 ms across all trials; demonstrated miss-rate bound stated per §5.3. |
| **G3** | The network never makes a healthy robot look dead. | Max telemetry inter-arrival gap at MEC ≤ ▷ T_live/4 (500 ms); zero gaps ≥ T_live over the full campaign; p98 ≤ PDB. |
| **G4** | After a robot goes quiet (waypoint pause), its next message still arrives promptly. | First-packet-after-silence one-way p99 ≤ ▷ 300 ms for silence gaps of 1 s / 5 s / 60 s. |
| **G5** | Operators and the AI always see fresh, complete video. | ≥ 99 % of PDU sets complete within PDB; frame age at MEC p95 ≤ ▷ 2 frame periods (67 ms); per-feed goodput ≥ GFBR in every 2 s window. |
| **G6** | Background traffic (logs, firmware) can never impair the fleet. | With saturating 5QI-9 load added (either direction), every G1/G3/G5 statistic stays within its bound and shifts by ≤ ▷ +20 % relative. |
| **G7** | One misbehaving robot cannot take down the others. | With Asset B's camera offered ≥ 2× MFBR, Asset A's G1/G3/G5 unchanged within ε; B's excess clipped at MFBR. |
| **G8** | Robots of equal entitlement get equal service — continuously, not just on average. | Per-1 s Jain ≥ ▷ 0.9 per role across assets; zero starvation epochs ≥ 1 s. |
| **G9** | A robot joins (or re-joins after an outage) quickly, even on a busy cell. | Warm app re-handshake p95 ≤ ▷ 1 s; full attach-to-streaming ≤ ▷ 15 s; post-RLF time-to-SLO ≤ ▷ 10 s; neighbours unaffected throughout. |
| **G10** | The cell hosts a stated fleet size with all of the above intact. | Admissible N: largest asset count with G1–G8 all-pass in 5/5 runs. |
| **G11** | The guarantees hold for a whole shift, and reproduce run after run. | Every 60 s window of a ≥ 30 min soak passes; across repeats, CoV(p98) ≤ ▷ 15 % and PASS/FAIL is consistent. |
| **G12** | When the cell is genuinely overloaded, degradation follows the safety order. | First-violation order under a load ramp is exactly: 5QI 9 → 5QI 4 (lidar) → 5QI 2 (camera) → *never* 5QI 1 (telemetry/commands) while any lower class still has throughput. |

---

## 4. Test design principles

1. **≥ 2 assets in every test.** Even where the mechanism under stress is intra-asset (e.g. a UGV's own camera vs its own heartbeat), the second asset runs its nominal committed profile — both to make the scenario realistic and to observe collateral damage for free.
2. **Score the worst asset, never the mean.** The characteristic failure of priority scheduling is starving one contender while the other looks perfect.
3. **Three arms where attribution matters** (P0 tests): two-tier floor-ON (the product), two-tier floor-OFF (`-DIA_P5G_UL_FLOOR_ENABLE=0`), original scheduler (baseline). P1/P2 tests may run product-arm only, adding arms on failure. The baseline arm is what converts a measurement into the comparative claim (*"guarantee held where the stock scheduler did not"*).
4. **A guarantee is a bound plus a confidence, or it is marketing.** §5.3 fixes the sample-size arithmetic; every Guarantee-Sheet row states both.
5. **Environment honesty.** rfsim (~0.45× realtime, OWD floor ≈ 3.0–3.8 ms) is valid for *logic, regression, ordering, and relative* claims; **certifiable latency numbers come from the real-RF runs**. Every test carries an `Env` tag: `SIM` (rfsim sufficient), `RF` (real RF required for the certifiable number), `SIM→RF` (develop in sim, certify on RF).

---

## 5. Normative KPI definitions

**GBR conformance (5QI 1/2/4).** Per TS 23.501 §5.7.3.4: while the flow stays within GFBR, 98 % of packets shall not exceed the PDB. Conformance statistic is **p98 < PDB** — report p50/p95/p98/p99/p99.9/max, PASS/FAIL on p98. (Client-facing guarantees G2/G4 deliberately use stricter percentiles than 3GPP conformance; both are reported.)

**RAN budget split.** Subtract the core-network component from the PDB. Measured floor OWD is ~3.0–3.8 ms end-to-end; state the assumed split (▷ RAN budget = PDB − 5 ms) in every report.

**Frame / PDU-set KPI (camera, lidar sweeps).** 3GPP XR convention: an asset's feed is *satisfied* if ≥ 99 % of its PDU sets arrive **complete** within the set delay budget; partial frames count as failed. Additionally report **frame age at MEC** (recv_ts − frame-generation ts), because latest-frame-only inference makes age the operationally binding quantity.

**Liveness KPI.** Distribution of telemetry inter-arrival gaps at the MEC-side receiver; headline numbers are max gap and count of gaps exceeding {T_live/4, T_live/2, T_live}. This is the survival-time framing: consecutive-loss tolerance, not average latency.

**Fairness.** Jain's index computed **per 1 s window** per role across assets (aggregate-Jain over a whole run is known to mask 5 s bang-bang oscillation — per-second Jain 0.743 has been observed while aggregate read 0.9977).

### 5.3 Statistical validity (rule of three)

To demonstrate a miss-rate ≤ ε at 95 % confidence with zero observed misses, you need **n ≥ 3/ε** samples. Consequences, so run durations are not guessed:

| Claim | Min zero-miss samples | At 10 Hz telemetry | At 30 fps video | Event trials (STOP) |
|---|---|---|---|---|
| ≤ 10⁻² (5QI 1 PER class) | 300 | 30 s | 10 s | 300 trials |
| ≤ 10⁻³ | 3 000 | 5 min | 100 s | impractical per-run → aggregate across campaign |
| ≤ 10⁻⁴ | 30 000 | 50 min | 17 min | — |
| ≤ 10⁻⁶ (5QI 4 PER) | 3 × 10⁶ | — | — | — |

Practical policy: per-run durations below give ≥ 10⁻³-class evidence for periodic flows; **event guarantees (G2, G4) accumulate trials across the whole campaign** and the Guarantee Sheet states the honestly demonstrable bound (e.g. *"0 misses in 1 240 STOP trials → miss-rate ≤ 2.4 × 10⁻³ at 95 % confidence"*). The 5QI-4 10⁻⁶ PER is **not** claimable in feasible run time; state the demonstrated bound instead.

---

## 6. Prerequisites and gates (nothing runs before these)

**P1 — GT-0 path-liveness smoke test (permanent regression gate).** For *every* provisioned 5-tuple on *both* assets: send 100 sequenced datagrams, confirm ≥ 99 delivered at the N6-side server with correct role attribution. This exists because of the known **5QI-4 video blackhole** (RAN delivers — BSR drained, BLER 0 — but zero packets reach N6; fault localised to gNB SDAP/GTP-U or UPF PDR/FAR for QFI 3). GT-3/GT-5/GT-7 are **blocked** for any tuple failing GT-0; GT-1/GT-2/GT-4 sub-tests not involving the blackholed tuple may proceed. GT-0 also catches the previously-observed cross-UE filter collision class (byte-identical subscriber rules).

**P2 — Instrumentation defects** (both known): snapshot `floor_crumb_run` *before* the `[P5G-UL-FLOOR] FIRED` log resets it; promote the PHR-cap line from `LOG_D` to `LOG_I` under `IA_P5G_TELEMETRY`.

**P3 — Harness defects:** sanity flow must not contaminate the main CSV sequence space; `IDLE_EXIT` lengthened to survive saturation drains; per-second Jain added to `p5g_analyze.py`.

**P4 — Provisioning:** `factory_fleet` right-sized profile (§2.1) applied to both subscribers (delete-and-recreate, per the free5GC webconsole rule); floor-arming re-verified (§2.1 warning).

**P5 — DL command sender:** harness support for MEC-side → UE small-packet CBR and triggered events on the sensor 5-tuple, with the same seq/ts header so `p5g_analyze.py` works unchanged in DL.

**P6 — Every-run checklist:** `chronyc tracking` recorded on both boxes (OWD is meaningless without it); gNB at `-DIA_P5G_TELEMETRY=3`; clean restart of gNB + all UE containers between contention runs (contention leaves slowly-decaying backlog); multi-asset probe-window overlap ≥ 90 % or the run is discarded; packet sizes recorded (TBS quantisation makes size a hidden axis).

---

## 7. Test families

Format per test: **Guarantee · Functional view · Assets & load · Procedure · KPIs / pass · Env · Duration · Tie-ins.**

---

### GT-1 — Command & Safety Delivery (DL) — validates G1, G2

The family a safety review reads first. DL is also the estimation-free direction (the gNB reads its own RLC buffers — no BSR/SR path), so this family additionally certifies the *algorithm* independent of the UL estimation pathology.

**GT-1.1 Teleop responsiveness under fleet load** — *"Driving a robot feels immediate while the rest of the fleet works."*
Functional view: binds the operator-in-the-loop experience; a p98 breach here is a robot that lurches.
Assets/load: Asset A driven (M1-DL cmd_vel 20 Hz on 5QI 1 DL) **and** uplinking camera at nominal; Asset B runs full committed profile UL **plus** saturating 5QI-9 DL (firmware pull) so the DL link is genuinely loaded — an idle DL link measures nothing.
Procedure: 10 min steady state, 3 arms.
KPIs/pass: cmd_vel one-way p98 ≤ RAN PDB; p99.9 and max reported; zero command gaps ≥ 200 ms.
Env: SIM→RF. Duration: 10 min × 3 arms × 5 runs.
Tie-ins: characterisation F0/F3a in DL.

**GT-1.2 Emergency-stop under worst case** — *"Master disconnects; every ground robot stops in time."*
Functional view: the disconnect-safety path in the architecture (master drop ⇒ STOP to all ground assets) is the single highest-consequence packet in the system. Two assets receive STOP **simultaneously**, so this also exercises same-slot DL contention for the two highest-priority packets in the cell.
Assets/load: both assets at full committed profile; cell saturated both directions with 5QI-9 (worst legal case). Trigger: scripted master-disconnect → simultaneous STOP datagrams to A and B.
Procedure: 30 trials/run, ≥ 10 runs, randomised trigger phase within the frame; trials accumulate across the campaign per §5.3.
KPIs/pass: 100 % of STOPs ≤ 100 ms one-way at both assets in every trial; per-trial worst asset recorded; final Guarantee-Sheet row states the demonstrated miss-rate bound.
Env: **RF** for the certifiable number (SIM for regression). Duration: ~5 min/run.
Tie-ins: floor tie-break logic is UL-side, but the simultaneous-event pattern here is the DL mirror of GT-7.2.

**GT-1.3 Sporadic command after silence (UAV mode/arm/gimbal)** — *"An occasional command is as fast as a continuous stream."*
Functional view: UAV operation is command-sparse; proves the DL path has no warm-up penalty and that DRX/scheduling gaps don't tax first packets.
Assets/load: Asset B (UAV role) receives isolated single commands after DL-command silences of {1 s, 10 s, 60 s}; Asset A streams full profile throughout; background 5QI-9 DL active.
KPIs/pass: first-command one-way p99 ≤ 150 ms per silence bucket; no bucket-dependent degradation trend.
Env: SIM→RF. Duration: 100 trials/bucket.

---

### GT-2 — Liveness & Session Continuity (UL) — validates G3, G4

The family this scheduler's known failure mode makes existential. The MEC infers liveness from telemetry; the documented BSR-desync → candidacy-loss → stall chain, if it recurs, does not cost milliseconds — it **stops robots** (false failsafe) and forces re-handshakes. The v2.1 service-interval floor is the mechanism on trial.

**GT-2.1 Heartbeat vs own camera (intra-asset)** — *"A robot's own video can never squeeze out its own heartbeat."*
Functional view: targets the known intra-UE strict LCP preemption (no `prioritisedBitRate` configured → video starves until higher-priority buffer is exactly zero — and the concern here is the reverse ordering under UE-side LCP when grants are scarce). The client hears: "your camera-equipped robot stays visibly alive."
Assets/load: Asset A telemetry (M1) + camera at MFBR (deliberately over-driven); Asset B nominal committed profile (second asset present, collateral observed).
KPIs/pass: A's telemetry max gap ≤ 500 ms, zero gaps ≥ T_live, p98 ≤ PDB; **and** B's SLOs unaffected (ε per G6).
Env: SIM→RF. Duration: 10 min × 3 arms.
Tie-ins: known issue "intra-UE strict preemption"; if this fails, the fix is UE-side `prioritisedBitRate` configuration, not the gNB scheduler — the arms disambiguate.

**GT-2.2 Heartbeat vs neighbour's flood (the required GBR-vs-non-GBR, UL)** — *"Someone else's bulk upload cannot kill your liveness."*
Functional view: the canonical isolation claim, restated as a liveness guarantee.
Assets/load: Asset A full committed profile (telemetry is the instrument); Asset B saturating 5QI-9 UL (`bg` role) *plus* its own committed telemetry (so B is a real asset, not a pure aggressor).
KPIs/pass: A **and** B telemetry gap/latency KPIs per G3; bg receives residual only; verify `[P5G-UL-FLOOR]` arming under the right-sized profile (§2.1 warning) and count fires.
Env: SIM→RF. Duration: 10 min × 3 arms × 5 runs. **P0.**
Tie-ins: this is the direct hardware validation of the v2.1 floor / candidacy-loss fix; floor-OFF arm attributes the delta.

**GT-2.3 Silence-and-resume (patrol pause)** — *"A robot that pauses at a waypoint doesn't go dark when it moves again."*
Functional view: robots idle; the first packet after silence is exactly where the SR-fragility and desync class lives. Sweeping the gap around the floor's 2 s arming horizon deliberately probes both regimes: gap < 2 s (floor armed — the floor must catch a would-be stall) and gap > 2 s (floor disarmed by design — the raw SR/RACH path must carry it alone).
Assets/load: Asset A telemetry pauses for {1 s, 5 s, 60 s} then resumes at 10 Hz; Asset B full profile + bg saturation throughout (worst case for A's re-entry).
KPIs/pass: first-packet one-way p99 ≤ 300 ms per gap bucket; time-to-steady (p98 back within PDB) ≤ 1 s; per-bucket results reported separately — a pass at 1 s and fail at 60 s is a *finding about the SR path*, not noise.
Env: **RF** essential (SR fragility does not manifest in rfsim). 100 cycles/bucket.
Tie-ins: floor arming-window semantics; characterisation F8b; the deferred counter-decay fix — if bursty false-firing appears in these logs, that is the trigger to un-defer it.

---

### GT-3 — Video & Perception Service — validates G5

**Gated by GT-0** (the 5QI-4 N6 blackhole must be resolved for end-to-end scoring; air-interface-level scoring may proceed meanwhile with the gap explicitly annotated).

**GT-3.1 Single-feed frame guarantee under contention** — *"One camera's frames arrive complete, on time, and fresh."*
Functional view: converts "video works" into the three numbers the MEC design actually consumes: set completeness (decoder), deadline (operator), age (latest-frame-only AI).
Assets/load: Asset A camera at nominal (M4, 30 fps, 4 Mbps) — instrument; Asset B lidar (M3) + bg UL saturation — load.
KPIs/pass: ≥ 99 % PDU sets complete ≤ 150 ms; goodput ≥ GFBR in every 2 s window; frame age p95 ≤ 67 ms; A and B telemetry unharmed.
Env: SIM→RF. 10 min × 3 arms.

**GT-3.2 Full aggregation load (committed portfolio) — and the ceiling re-measurement** — *"Every feed of every robot, simultaneously."*
Functional view: the MEC's entire purpose is multi-feed aggregation; this is the smallest test that proves the committed portfolio is *jointly* feasible. It **is** the pending post-clamp-fix cell-ceiling re-measurement: step all GBR offered rates up together until the first flow's 2 s-window GFBR check fails; that knee is the certified ceiling, and the `factory_fleet` GFBRs (§2.1) are ratified or revised against it.
Assets/load: both assets, all committed flows (2 × camera + 2 × lidar + 2 × telemetry) at nominal, then stepped ×1.0 → ×1.5 in 0.1 steps, 60 s/step; no bg.
KPIs/pass: at ×1.0, every feed satisfies GT-3.1 KPIs simultaneously and every flow ≥ GFBR in every window. Deliverable: the knee point and per-flow headroom table.
Env: SIM for shape, **RF** for the certified ceiling. **P0.**

**GT-3.3 Cell-edge asset (channel asymmetry)** — *"The robot in the far corner of the factory still sees — and doesn't drag the others down."*
Functional view: factories have RF-hostile corners; clients ask what degrades and whether it is contained.
Assets/load: Asset B behind TDL_C with reduced SNR (channelmod step; on RF, physical attenuation/placement); Asset A nominal. Both full profile. Confirm the asymmetry is real via `[P5G-UL-GRANT] mcs=` distributions before trusting anything.
KPIs/pass: B's feed satisfaction vs SNR (characterisation curve, no fixed pass); **hard pass criterion:** A's full SLO set unchanged within ε while B degrades — cross-asset containment under channel asymmetry.
Env: SIM (TDL_C) → RF. 
Tie-ins: PHR is known-inert (`ph0` never received in 168 MB of logs) — record `ph0`; if still absent, annotate that power-limited behaviour is invisible and file the PHR fix as a finding.

---

### GT-4 — Isolation & Non-interference — validates G6, G7 (the required GBR-vs-non-GBR family, both directions, plus GBR-on-GBR)

**GT-4.1 Non-GBR flood, UL** — covered concretely by GT-2.2 (telemetry instrument) and GT-3.1 (video instrument); scored here as the G6 delta-statistic: every protected KPI shifts ≤ +20 % relative and stays within bound; bg gets residual only.

**GT-4.2 Non-GBR flood, DL** — *"A firmware push to one robot cannot blunt another robot's controls."*
Assets/load: saturating DL 5QI-9 to Asset B (firmware window) while Asset A is actively teleoperated (GT-1.1 instrument).
KPIs/pass: A's cmd_vel KPIs unchanged within ε; firmware still progresses (record completion time for a fixed 500 MB image — clients ask how long updates take *with* the fleet live).
Env: SIM→RF. **P0** (with GT-2.2, these two are the mandatory classic pair).

**GT-4.3 GBR-on-GBR containment (misbehaving asset)** — *"One misconfigured robot cannot take down the fleet."*
Functional view: the realistic fault is not malice but a mis-set encoder bitrate. The guarantee a multi-vendor fleet operator needs: entitlement is a ceiling, not a suggestion.
Assets/load: Asset B camera offered at 2× MFBR (encoder fault injection); Asset A full nominal profile.
KPIs/pass: A entirely within SLO; B's camera delivered ≤ MFBR + tolerance (excess clipped/queued at B, not exported to A); B's *other* flows (its own telemetry!) still within SLO — the containment must also hold inside the misbehaving asset.
Env: SIM→RF.

---

### GT-5 — Fleet Fairness & Scale — validates G8, G10

**GT-5.1 Equal robots, equal service — continuously** — *"Two identical robots; neither ever starves, not even for a second."*
Functional view: targets the documented ~5 s bang-bang oscillation (per-second Jain ≈ 0.743 during contention while aggregate Jain read 0.9977). An operator watching two dashboards sees one robot freeze for seconds at a time — aggregate fairness is invisible to them; per-second fairness is what they experience. This test is the **acceptance gate** for the proportional-sharing fix.
Assets/load: symmetric full profiles on both assets, offered jointly above the measured ceiling (from GT-3.2) so contention is real.
KPIs/pass: per-1 s Jain ≥ 0.9 for each role pair; zero windows where either asset's telemetry gap ≥ 1 s; per-window GFBR check on both.
Env: SIM→RF. **P0.** Expected initial result: FAIL — that is the point; the row tracks the fix.

**GT-5.2 Admissible fleet size** — *"How many robots does one cell honestly host?"*
Functional view: the headline procurement number.
Assets/load: fix the per-asset `factory_fleet` profile; sweep N = 1 → 2 (today) → 3 → 4 (when the testbed allows); until then, use the flow-scaling proxy (additional camera+telemetry pairs per UE) with the proxy status stated on the sheet.
KPIs/pass: admissible N = largest N with G1/G3/G5/G8 all-pass in **5/5** runs, scored on the worst asset.
Env: SIM proxy now, **RF** for the certified N. **P0 deliverable.**

---

### GT-6 — Join, Loss & Recovery — validates G9

**GT-6.1 Warm re-join under load** — *"An app restart on a busy cell, and the robot is back in a second."*
Assets/load: Asset B's client processes restart (app-level handshake on UDP :9000 → port re-assignment → streams resume; PDU session stays up) while Asset A runs full profile + bg saturation.
KPIs/pass: handshake round-trip p95 ≤ 1 s; all B streams back within SLO ≤ 3 s; A unperturbed throughout.
Env: SIM→RF. 50 cycles.

**GT-6.2 Cold attach-and-join under load** — *"Powering on a new robot mid-shift just works."*
Assets/load: Asset B container cold-started (RACH → attach → PDU sessions → handshake → streams) against a loaded cell (Asset A full profile + bg).
KPIs/pass: end-to-end power-on-to-streaming time recorded (▷ ≤ 15 s target); zero impact on A; no residual pathologies (ghost RNTIs, stale deficit/VQ state) in gNB logs after 10 consecutive cycles.
Env: SIM→RF. Tie-ins: characterisation F8a.

**GT-6.3 Deep fade / RLF and return** — *"A robot drives through a dead zone; it comes back cleanly, and nobody else notices."*
Functional view: the recovery half of liveness. The MEC will (correctly) declare the session lost; the guarantee is bounded, clean *restoration* — and strict containment: one asset's RLF storm must not perturb the other.
Assets/load: scripted fade on Asset B (channelmod SNR drop below sync for 10 s; on RF, physical obstruction) mid-stream; Asset A full profile throughout.
KPIs/pass: time from RF-restore to all-B-SLOs-green ≤ 10 s including re-establishment and re-handshake; A's KPIs flat through B's entire event; gNB state clean (floor/VQ/deficit reset correctness across re-establishment).
Env: SIM (scripted, repeatable) → RF (opportunistic). Tie-ins: F8d; the active RLF/OWD investigation — runs of this test are its data source.

---

### GT-7 — Endurance, Bursts & Overload — validates G11, G12 (+ G2 mass-event)

**GT-7.1 Production-shift soak (flagship)** — *"A full shift with everything on, and every minute of it within spec."*
Assets/load: both assets full `factory_fleet` profile; scripted realism: teleop cmd_vel duty-cycled on A, waypoint pauses on B (GT-2.3 pattern), a firmware window at T+10 min (GT-4.2 pattern), one STOP drill at T+20 min (GT-1.2 pattern). ≥ 30 min (rfsim) / ≥ 60 min (RF).
KPIs/pass: every 60 s window passes G1/G3/G5/G8; internals stable across the run — floor-fire rate, `%min_rb` crumb rate, skip-reason counters from `[P5G-UL-SUMMARY]` show no monotonic drift (leak detector).
Env: SIM→RF. **P0** — this run, on real RF, is the client demo.

**GT-7.2 Event storm** — *"Every robot alarms at once; every alarm gets through."*
Functional view: correlated events (line fault → all assets emit event telemetry; master drop → simultaneous STOPs) are exactly when a per-UE argmax scheduler is most tempted to serialise badly. This is also the designed-in stress for the floor's **silence-based tie-break** on simultaneous fires.
Assets/load: both assets emit event bursts (5 × 300 B) within the same 10 ms window on 5QI 1 UL, cell saturated; simultaneously the DL STOP pair of GT-1.2. 50 storms/run.
KPIs/pass: 100 % of event packets and STOPs ≤ deadline on the worst asset; logs show orderly consecutive floor fires (tie-break exercised, no collision/thrash).
Env: SIM→RF.

**GT-7.3 Overload degradation ordering** — *"When the cell truly runs out, safety is the last thing standing."*
Functional view: no honest system claims infinite capacity; the client-grade claim is *ordered* degradation. This also documents system behaviour beyond the GT-3.2 ceiling, which a deployment engineer needs for capacity planning.
Assets/load: both assets nominal; ramp aggregate offered load in +10 % steps of the measured ceiling, 60 s/step, to 145 %.
KPIs/pass: first-violation order per §3 G12, strictly: 5QI 9 exhausted → 5QI 4 degrades → 5QI 2 degrades → 5QI 1 (telemetry + commands) intact until nothing lower-class remains; any inversion (e.g. telemetry gap grows while bg still moves bytes) is a FAIL regardless of absolute numbers.
Env: SIM→RF. **P0.**

**GT-7.4 Repeatability** — *"The numbers are the numbers, every time."*
Procedure: 5–10 repeats of a 10 min GT-7.1 slice, clean restarts between.
KPIs/pass: CoV(p98) ≤ 15 % per instrument flow; identical PASS/FAIL verdicts across repeats; any bimodality investigated before the Guarantee Sheet is signed.
Env: matches whichever environment the sheet certifies.

---

## 8. Test matrix

| Test | Guarantee | Assets | Dir | Env | Arms | Priority | Known-issue tie-in |
|---|---|---|---|---|---|---|---|
| GT-0 path liveness | gate | A+B, all tuples | UL | SIM+RF | 1 | **P0 gate** | 5QI-4 N6 blackhole; filter collision |
| GT-1.1 teleop cmd | G1 | A instr, B load | DL | SIM→RF | 3 | P0 | DL never load-tested properly before |
| GT-1.2 e-stop | G2 | A+B simultaneous | DL | RF | 3 | **P0** | — |
| GT-1.3 sporadic cmd | G1 | B instr, A load | DL | SIM→RF | 1 | P1 | — |
| GT-2.1 heartbeat vs own camera | G3 | A instr, B nominal | UL | SIM→RF | 3 | P1 | intra-UE LCP preemption |
| GT-2.2 heartbeat vs flood | G3 | A instr, B aggressor | UL | SIM→RF | 3 | **P0** | floor v2.1 validation; F8e arming |
| GT-2.3 silence-resume | G4 | A instr, B load | UL | **RF** | 3 | **P0** | SR fragility; floor 2 s horizon; counter-decay |
| GT-3.1 single feed | G5 | A instr, B load | UL | SIM→RF | 3 | P1 | blackhole gate |
| GT-3.2 portfolio + ceiling | G5 | A+B all flows | UL | RF | 1 | **P0** | pending ceiling re-measure |
| GT-3.3 cell-edge | G5/G6 | B degraded, A nominal | UL | SIM→RF | 1 | P2 | PHR inert (`ph0`) |
| GT-4.2 DL flood | G6 | A instr, B sink | DL | SIM→RF | 3 | **P0** | — |
| GT-4.3 misbehaving asset | G7 | B fault, A instr | UL | SIM→RF | 1 | P1 | MFBR clamp path |
| GT-5.1 per-second fairness | G8 | A+B symmetric | UL | SIM→RF | 3 | **P0** | bang-bang oscillation (expected FAIL) |
| GT-5.2 admissible N | G10 | N sweep | UL+DL | RF | 1 | **P0** | PDCCH/crumb bottleneck at high N |
| GT-6.1 warm re-join | G9 | B rejoin, A load | both | SIM→RF | 1 | P1 | — |
| GT-6.2 cold attach | G9 | B attach, A load | both | SIM→RF | 1 | P2 | F8a ghost state |
| GT-6.3 RLF recovery | G9 | B fade, A nominal | both | SIM→RF | 1 | P1 | RLF/OWD investigation; F8d |
| GT-7.1 shift soak | G11 | A+B full script | both | SIM→RF | 1(+baseline once) | **P0** | drift/leak detection |
| GT-7.2 event storm | G2/G3 | A+B synchronized | both | SIM→RF | 3 | P1 | floor silence tie-break |
| GT-7.3 degradation order | G12 | A+B ramp | UL+DL | SIM→RF | 3 | **P0** | — |
| GT-7.4 repeatability | G11 | A+B | both | as certified | 1 | P1 | — |

Suggested execution order: GT-0 → GT-3.2 (ceiling; everything else needs it) → GT-2.2 / GT-4.2 (the mandatory isolation pair) → GT-1.x → GT-2.3 (first RF window) → GT-5.1 → GT-7.3 → remaining P1/P2 → GT-7.1 soak → GT-5.2 → GT-7.4 sign-off.

---

## 9. The Guarantee Sheet (client-facing roll-up)

One row per guarantee; this is the artefact the client reads. Template:

```
Guarantee | Plain-language statement | Bound demonstrated | Confidence (n, method §5.3) |
Load conditions it held under | Environment (rfsim / real RF) | Arms (vs baseline delta) |
Caveats / exclusions | Evidencing tests & run IDs
```

Rules: never state a bound tighter than §5.3 permits; always state the environment; always state the PDB split assumption; where a guarantee is *conditional* (e.g. G3 holds only for silence gaps < 2 s pending the SR-path result), the condition goes in the statement itself, not a footnote. A guarantee row with an honest condition is credible; a clean row that hides one is a liability.

---

## 10. Traceability to the characterisation suite (what to do when a GT fails)

The two documents are layers: this plan detects *that* a guarantee fails; the characterisation suite localises *why*. Standing mapping:

| GT failure | Drill down with | Likely mechanism |
|---|---|---|
| GT-1.x (DL) | F0 DL, F3a | pure algorithm (no estimation path in DL) |
| GT-2.2 / GT-2.3 | F0 UL delta, F8b/F8e | BSR desync / candidacy / floor arming / SR path |
| GT-3.1 frame misses | F4 (burst), W6 (XR aliasing vs 100 ms Tier-1 period) | VQ catch-up horizon; non-integer periodicity |
| GT-3.2 ceiling shortfall | F2 | LP reallocation inert; demand inputs |
| GT-3.3 | F5, W5 | SE multiplier; PHR inert |
| GT-5.1 | F1/F2 + per-window analysis | deficit window cap; bang-bang arbitration |
| GT-5.2 plateau | W7/W8 | no admission control; PDCCH/crumb DCI burn |
| GT-7.3 inversion | F3a/F3c | priority term vs deficit path ordering |

And forward: the §12 mechanism catalogue of the characterisation suite (CG Type 1 + LCP restrictions foremost) remains the roadmap for whichever GT rows come back red — a Configured Grant on the 5QI-1 bearer structurally removes the entire GT-2 failure class (no SR, no BSR, no estimate to desync) and is the expected first feature ask if GT-2.3's long-gap buckets fail on real RF.

---

## 11. Open items to confirm before execution

1. **`T_live`** — the MEC's actual liveness timeout and the safe-margin policy (G3's ▷ 500 ms assumes 2 s). Ask the MEC team; it calibrates GT-2 pass lines.
2. **Client SLO ratification** — every ▷ value in §3.
3. **UAV asset realism** — whether UE2 emulates MAVLink cadence (recommended for GT-1.3/GT-2 realism) or both assets run the UGV profile in round one.
4. **DL sender harness (P5)** — owner and ETA; GT-1/GT-4.2/GT-7 depend on it.
5. **5QI-4 blackhole status** — if resolved since the last handoff, GT-0 simply confirms; if not, its debug procedure is the campaign's first task.
6. **Real-RF window** — GT-2.3, GT-1.2, GT-3.2 and the certified GT-5.2 N need it; sequence the campaign so SIM-phase results are frozen before the window opens.
7. **Repetition counts** — defaults are 5 runs (P0) / 3 runs (P1+), 5/5 for admissible-N; confirm.
