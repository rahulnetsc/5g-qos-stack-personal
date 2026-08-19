# IA-P5G — Guarantee Validation Suite
## Private-5G factory automation, multi-asset MEC deployment

**Purpose:** validate the *service guarantees* a factory client would buy,
not the internal mechanisms of the scheduler. Every test below answers a
question a customer or safety assessor would actually ask, and produces a
number that can go on a specification sheet.

**Companion to:** `IA_P5G_Scheduler_Benchmark_Suite.md` (mechanism
characterisation). That suite asks *why* the scheduler behaves as it does;
this one asks *what can we promise*. Run mechanism tests to debug, run these
to certify.

---

# Part 1 — What the system is (as I understand it)

## 1.1 Topology

```
   robots (UGV / UAV)  ──5G UL──►  gNB ──►  MEC  ──WebSocket/WebRTC──►  operator UIs
                       ◄─5G DL──                                        (1 master, N viewers)
```

Every byte crosses the 5G air interface exactly once, between robot and MEC.
Operators never talk to a robot directly — a command takes two hops
(UI → MEC → robot), and only the second hop is ours. The UI leg is wired
LAN/WAN and outside scheduler scope, but it is *inside* the client's
end-to-end budget, so our numbers must be reported as a *component* of the
customer-visible latency, never as the whole thing.

## 1.2 Assets and their traffic shapes

| Asset | Video | Telemetry | Commands | Extra |
|---|---|---|---|---|
| **UGV** | RTP/H264 over UDP, **pushed** by robot | msgpack, aggregated | `cmd_vel` (drive) | lidar (msgpack, high rate) |
| **UAV** | RTSP, **pulled** by MEC | MAVLink parsed | gimbal, arm, flight mode | — |

These are genuinely different traffic shapes and that matters. RTP push is
UL-dominant and bursty at frame boundaries. RTSP pull carries a TCP control
channel, so the UAV video has a **DL component and a closed loop** — a
scheduler that delays the DL leg throttles the UL video by back-pressure.
That is a failure mode the UGV path simply cannot exhibit.

## 1.3 Stream categories → bearers

The architecture allocates ports by category specifically so that "one
quality-of-service rule can target a whole class". The MECSTACKQOS profile
implements that:

| Category | Port range | 5QI | UL GBR / MBR | PDB | Carries |
|---|---|---|---|---|---|
| handshake | 9000–9001 | 2 | 2 / 2 Mbps | 150 ms | session establishment |
| telemetry **+ inbound** | 14550 | 1 | 5 / 5 Mbps | 100 ms | status **up**, commands **down** |
| data_stream (lidar) | 21000–21999 | 8 | 10 / 10 Mbps | 300 ms | point clouds |
| data_stream (video) | 22000–23999 | 3 | 20 / 30 Mbps | 50 ms | H264/H265 camera feeds |
| default | anything else | 9 | non-GBR | — | IT traffic, updates, logs |

**Three architectural facts that drive every test below:**

**(a) Telemetry and commands share one bidirectional port per asset.** One
flow rule therefore governs *both* the robot's status uplink and the
operator's command downlink. This is elegant — but it also means UL and DL
on the control loop compete for the same bearer treatment, and a test that
only measures UL is measuring half the safety path.

**(b) Liveness is inferred from continuing telemetry.** If telemetry stops,
the MEC declares the session lost and the robot must re-handshake. So the
scheduler can cause a **false disconnect** purely by delaying telemetry past
the liveness timeout — no packet loss required. On a UGV that triggers the
disconnect failsafe: *the robot stops on the factory floor*. This is the
single most client-visible failure the scheduler can produce, and nothing in
our testing to date would have detected it.

**(c) The AI stage is a safety function.** Human detection (YOLO) runs on
every camera feed. In a factory that is a person-in-path interlock, and the
5G network sits on two legs of that safety chain: the UL video that carries
the evidence, and the DL command that carries the stop.

## 1.4 What this means for testing

The previous suites measured **per-packet latency of one probe flow**. A
factory client does not buy per-packet latency. They buy:

- a *worst case*, not a percentile — safety arguments cannot be made on p99
- *availability over time*, not latency in a 15-second window
- *behaviour under fault*, not behaviour when everything works
- *guarantees that hold with the whole fleet running*, not one probe UE

---

# Part 2 — The guarantees

Framed in TS 22.104 vocabulary, because that is what an industrial customer
and their safety assessor will use.

| ID | Guarantee | Client phrasing |
|---|---|---|
| **G1** | Safety reaction time | "If a person steps in front of an AGV, how long until it stops — worst case?" |
| **G2** | Command determinism | "Is teleoperation smooth and predictable, or does it lurch?" |
| **G3** | Service availability / survival time | "Will the system ever falsely declare a robot offline and stop it?" |
| **G4** | Video service quality | "Can my operator see N cameras without freezes?" |
| **G5** | Capacity | "How many robots per cell, with all of the above still true?" |
| **G6** | Fault containment | "If one robot misbehaves, are the others affected?" |
| **G7** | Graceful degradation | "When you run out of capacity, what breaks first?" |
| **G8** | Recovery time | "After interference or a dropped link, how fast is service restored?" |
| **G9** | Coexistence | "Can I run firmware updates and file transfers on the same network?" |
| **G10** | Sustained availability | "Does it hold up over an 8-hour shift?" |

**Key definitions (TS 22.104):**

- **Survival time** — the time an application may continue without an
  expected message before the service is deemed unavailable.
- **Communication service availability** — the service is *unavailable* when
  transfer time exceeds (max end-to-end latency + survival time). Availability
  is the fraction of time it is not unavailable. This is a combination of
  latency, reliability and survival time — not a latency percentile.
- **Transfer interval** — time between consecutive application transfers
  (for us: the telemetry heartbeat period, the video frame period).

The practical consequence: **a burst of consecutive misses matters far more
than the same number of misses scattered randomly.** Ten isolated late
telemetry packets is a non-event. Ten *consecutive* late packets past the
survival time is an outage, and on a UGV it is a robot stopping. Every KPI
below is therefore expressed as a *consecutive-miss* or *worst-case-gap*
statistic, not an average.

---

# Part 3 — Test cases

Each: the client question, what happens functionally, the setup, the
measurement, and the pass criterion.

---

## T1 — Safety reaction time (G1) · **highest priority**

**Client question:** *"A worker steps into an AGV's path. How long, worst
case, from them being visible to the vehicle stopping?"*

**Functional narrative.** The AGV's forward camera captures a frame
containing a person. That frame travels UL to the MEC, is decoded, YOLO
detects a human, the MEC issues a stop, and the stop travels DL to the AGV
which brakes. The 5G network owns two legs — UL video and DL command — and a
safety case needs a defensible bound on both.

**Setup.** 2 UGVs + 1 UAV, all streaming video and telemetry, network at
representative load (T5's admissible N minus one). One UGV is the subject.

**Measurement — decompose, don't just measure end to end.** Four timestamps:

| Leg | From → to | Owner |
|---|---|---|
| L1 | frame captured → last packet of frame at MEC | **scheduler (UL)** |
| L2 | frame complete → detection produced | MEC compute |
| L3 | detection → stop command queued | MEC logic |
| L4 | stop queued → command received at robot | **scheduler (DL)** |

Report L1 and L4 as the network contribution and L1+L2+L3+L4 as the system
reaction time. Decomposition matters because if the client's budget is
missed, you must be able to say whether to buy more radio or a faster GPU.

**Instrumentation.** Embed a capture timestamp in the RTP extension header or
in a test-pattern overlay; timestamp the stop command at both ends. A
synthetic "detection trigger" injected on the video port is acceptable for
network characterisation and avoids depending on YOLO's variability.

**KPI.** **Absolute maximum** of (L1 + L4) over ≥ 10,000 events, plus the
full distribution. Also report L1 and L4 maxima separately.

**Pass criterion.** Set by the client's risk assessment. Report the measured
maximum and the load at which it was measured. A typical AGV target is
100–300 ms total reaction; the network share should be a stated fraction.

**Why maximum, not p99.** A safety argument cannot be built on a percentile.
"1% of the time the robot takes longer than X to stop" is not a sentence you
can put in front of a safety assessor.

---

## T2 — Command determinism under load (G2)

**Client question:** *"Does teleoperation feel responsive and consistent when
the whole fleet is running?"*

**Functional narrative.** An operator drives a UGV with a joystick. Commands
flow at a fixed rate down the shared telemetry/command bearer while status
flows up the same bearer. Humans tolerate constant latency far better than
variable latency — a lurching robot is worse than a uniformly slightly-late
one.

**Setup.** 2+ assets. Subject UGV under continuous `cmd_vel` at its real
command rate (typically 10–50 Hz). Other assets at full video + telemetry.

**Measurement.** DL command latency per packet; UL telemetry latency per
packet; **both on the same bearer, simultaneously**. This is the test that
the shared-port architecture demands and that no previous run has done.

**KPI.**
- DL command: p50, p99, max, and **jitter as p99 − p50** (not stddev)
- UL telemetry: same
- **Correlation between the two directions** — do UL and DL degrade together?

**Pass criterion.** p99 − p50 < 20 ms on the command direction; no command
gap exceeding 2× the command interval.

**Why it matters.** If UL and DL degrade together on the shared bearer, a
loaded uplink makes the robot both blind *and* unresponsive at the same
moment. That correlation is a genuine safety concern and it is invisible if
you only ever measure one direction.

---

## T3 — Survival time and false-disconnect (G3) · **highest priority**

**Client question:** *"Will the system ever decide a robot is offline when it
isn't — and stop it?"*

**Functional narrative.** The MEC infers liveness from continuing telemetry.
If the scheduler delays telemetry past the MEC's liveness timeout, the
session is torn down, the UGV disconnect failsafe fires and the robot stops.
No packets were lost; the network simply delivered them late. To the client
this is a spurious production halt with no obvious cause.

**Setup.** 2+ assets at increasing load, up to and past the capacity knee.
Instrument the MEC's liveness timer.

**Step 0 — record the liveness timeout.** Read it from the MEC config. This
is the survival time. Everything below is relative to it.

**Measurement.** For each asset's telemetry stream, the distribution of
**consecutive-gap duration** — the longest interval between successive
*delivered* telemetry messages. Not per-packet latency; the gap.

**KPI.**
- max consecutive gap, per asset, per load point
- **margin ratio** = liveness timeout / max gap observed
- count of actual session losses (must be zero)
- availability = fraction of time gap < survival time

**Pass criterion.** Margin ratio ≥ 3 at admissible N. Zero false
disconnects across the full soak (T11).

**Why it is nearly the most important test here.** It converts a latency
distribution into a **binary, client-visible outcome**. And it is a guarantee
that can be stated cleanly: *"no false disconnect at up to N assets, verified
over an 8-hour run with 3× timing margin."* That sentence sells.

---

## T4 — Video service quality (G4)

**Client question:** *"Can my operator watch N camera feeds without freezes?"*

**Functional narrative.** Operators need situational awareness. A video frame
is only useful when *complete* — one lost or late packet ruins the whole
frame. And the MEC drops all but the latest frame for AI, so a backlog
manifests as stale detections rather than delay.

**Setup.** All assets streaming their real camera configuration. Sweep
resolution/bitrate.

**Measurement — frame-level, not packet-level.** A frame is delivered when
its last packet arrives. Group by RTP timestamp.

**KPI.**
- frame completion latency: p50, p99, max
- **frame delivery ratio** — complete frames / frames sent
- **freeze events** — gaps > 2 frame intervals, count and duration
- effective fps at the MEC vs fps at the camera

**Pass criterion.** ≥ 99% frame delivery ratio; zero freezes > 500 ms;
effective fps within 5% of source.

**Why per-packet latency is the wrong KPI here.** A 1080p30 I-frame is
40–60 packets. If 59 arrive in 10 ms and one arrives at 200 ms, per-packet
p99 looks excellent and the operator sees a stutter. Only the frame-level
statistic reflects what the human perceives.

---

## T5 — Fleet capacity (G5) · **the headline number**

**Client question:** *"How many robots can I run on one cell?"*

**Functional narrative.** The commercial question. Everything else is a
qualifier on this number.

**Setup.** Add assets one at a time, each with the full realistic profile
(video + telemetry + lidar for UGVs; video + MAVLink for UAVs). N = 1, 2, 3,
4 … as hardware allows.

**Measurement.** At each N, run T1, T2, T3 and T4 concurrently.

**KPI. Admissible N** = the largest N at which **every** asset simultaneously
satisfies G1–G4, in 5 of 5 repetitions.

**Report the binding constraint.** At N+1, state *which* guarantee failed
first and by how much. "We support 6 AGVs; at 7 the video freeze budget is
exceeded while control is still within spec" is a far more useful and more
credible statement than a bare number, and it tells the client exactly what
to buy to go further.

---

## T6 — Fault containment / noisy neighbour (G6)

**Client question:** *"If one robot goes wrong, does it take the others with
it?"*

**Functional narrative.** Real failure modes: a camera's rate control fails
and it streams at 3× nominal; a lidar driver bugs out and floods; a robot
retransmits a backlog after a brief RF outage. Any of these can push one
asset far above its contracted rate.

**Setup.** N assets at admissible N. One asset is the aggressor.

**Aggressor variants:**

| Variant | What the aggressor does | Tests |
|---|---|---|
| T6a | video at 3× nominal bitrate | MBR enforcement on 5QI3 |
| T6b | lidar flood at 5× | MBR enforcement on 5QI8 |
| T6c | burst of best-effort at line rate | non-GBR containment |
| T6d | telemetry at 10× rate | control-bearer abuse |
| T6e | recovery burst after 2 s RF outage | backlog drain containment |

**KPI.** For every **non-aggressor** asset: G1–G4 must hold unchanged.
Measure the delta against the no-aggressor baseline.

**Pass criterion.** Non-aggressor guarantee metrics degrade by < 10%. The
aggressor itself may be throttled — that is correct behaviour.

**Why it matters commercially.** This is the difference between "a shared
network" and "a network I can put a safety function on". Without T6 the
client must assume every robot is a single point of failure for the fleet.

---

## T7 — Graceful degradation (G7)

**Client question:** *"When you run out of capacity, what gives?"*

**Functional narrative.** Overload is inevitable — someone adds a robot,
someone raises a camera's bitrate. The client needs to know the failure is
*ordered and predictable*, and that the ordering is the one they would have
chosen.

**Required degradation order** (best → worst thing to lose):

```
1. best-effort / IT traffic     (should vanish first)
2. lidar                        (5QI8, PDB 300 ms)
3. video quality                (5QI3 — degrade, don't freeze)
4. telemetry / commands         (5QI1 — must NEVER degrade)
```

**Setup.** Start at admissible N, then push load past the knee in steps —
add assets, or raise video bitrate 10% per step.

**Measurement.** At each step record throughput and KPI attainment **per
traffic class**.

**KPI.** The *order* in which classes miss their targets, and whether
telemetry ever degrades before video is fully starved.

**Pass criterion.** Strict ordering observed. Telemetry/command KPIs hold
until every lower class is fully starved.

**Failure interpretation.** If telemetry degrades while video is still
flowing, QoS differentiation is not working where it matters most — and that
is a finding worth more than any latency number, because it invalidates the
whole priority argument.

---

## T8 — Recovery time (G8)

**Client question:** *"A forklift parks in front of an antenna for two
seconds. What happens, and how fast does it come back?"*

**Functional narrative.** Factories have moving metal. Brief RF outages are
normal, not exceptional. What matters is whether the system recovers cleanly
or enters a degraded state that persists.

**Setup.** N assets. Induce a controlled outage on one: RF shield, attenuator
step, or a physical obstruction.

**Outage durations:** 100 ms, 500 ms, 2 s, 10 s (spanning below liveness
timeout, above it, and into re-handshake territory).

**Measurement.**
- time to first delivered telemetry after outage ends
- time to full KPI restoration (all guarantees back in spec)
- whether a re-handshake occurred
- whether *other* assets were disturbed during the outage or recovery
- backlog drain behaviour — does the recovering asset's burst hurt others?

**Pass criterion.** Recovery to full KPI within 2× the outage duration, or
within 5 s, whichever is greater. No collateral impact on other assets.

**Note.** This directly tests the persistent-backlog effect we already know
about, where contention leaves a slowly-decaying state that survives the
event. Here it becomes a client-visible number rather than a testbed quirk.

---

## T9 — Mixed asset types (G5 qualifier)

**Client question:** *"Can drones and ground vehicles share the same
network?"*

**Functional narrative.** UGVs push RTP/UDP video; UAVs are pulled over RTSP,
which carries a TCP control channel and therefore a **DL dependency inside
the video path**. If the scheduler delays that DL leg, TCP back-pressure
throttles the UAV's uplink video — a coupling that simply does not exist for
UGVs.

**Setup.** 1 UGV + 1 UAV minimum; 2+2 preferred. Identical load otherwise.

**Measurement.** All of G1–G4, per asset type. Specifically: UAV video
throughput vs DL latency on its RTSP control channel.

**KPI.** Whether UAV video degrades non-linearly as DL load rises — the
signature of TCP back-pressure rather than plain scheduling delay.

**Why include it.** It is the only test here where a DL scheduling problem
manifests as a UL throughput problem. Diagnosing that from the UL numbers
alone would be near-impossible.

---

## T10 — Coexistence with IT traffic (G9)

**Client question:** *"Can I run firmware updates, log uploads and camera
recording pulls on the same network?"*

**Functional narrative.** A real factory does not have a dedicated robot
network. Maintenance traffic, OTA updates, historian uploads all share it.
They are non-GBR and should be invisible to control — but only if
classification and non-GBR containment actually work.

**Setup.** N assets at admissible N, plus a bulk transfer on the default
bearer (5QI9): a sustained TCP file transfer, both UL and DL.

**Measurement.** G1–G4 with and without the bulk flow; plus bulk throughput
(it should get whatever is left, and should not be zero — starving it
completely is also a failure).

**Pass criterion.** Guarantee metrics unchanged within 5%. Bulk flow achieves
non-zero throughput and adapts.

**Also verify classification.** Confirm from `[QOS-DUMP]` that the bulk flow
actually landed on 5QI9 and not on a GBR bearer through a filter mistake.
A misclassified bulk flow would silently invalidate every other test.

---

## T11 — Sustained availability / soak (G10)

**Client question:** *"Does it hold up for a full shift?"*

**Functional narrative.** Everything above is minutes long. Clients run
8-hour shifts. Slow leaks, counter wraps, thermal drift, accumulating state
and rare coincidences only appear over hours.

**Setup.** Admissible N assets, realistic profile, **8 hours minimum**.

**Measurement.** Continuous logging of every G1–G4 metric, bucketed per
minute.

**KPI.**
- **Communication service availability** per TS 22.104: fraction of transfer
  intervals where the message arrived within (max latency + survival time)
- count and timing of every excursion
- drift — do metrics degrade monotonically over hours?
- correlation of excursions with known events (frame wrap at 1024, Tier-1
  solve, window flush, re-handshake)

**Pass criterion.** Availability ≥ 99.9% on control bearers (target 99.99%
if the client's safety case needs it). Zero unexplained excursions. No
monotonic drift.

**This is the test that produces the number on the datasheet.** Everything
else establishes that the system *can* meet the guarantees; this establishes
that it *keeps* meeting them.

---

## T12 — Control authority handover (G2 qualifier)

**Client question:** *"What happens when control passes between operators, or
the master's link drops?"*

**Functional narrative.** The MEC enforces one master, many viewers. If the
master disconnects, UGVs are told to stop and UAVs hold. That stop command is
safety-relevant and travels on the same bearer as everything else.

**Setup.** N assets, one under active control, multiple viewer UIs connected.

**Scenarios.** Clean handover between operators; abrupt master disconnect;
master link degraded but not dropped (the ambiguous case).

**Measurement.** Latency of the resulting stop/hold command; command
continuity across handover; whether any interval exists with no valid
controller and a moving robot.

**Pass criterion.** Stop command delivered within the T1 bound. No control
gap during clean handover.

---

# Part 4 — Test matrix

| ID | Guarantee | Assets | Duration | Priority | Blocked by |
|---|---|---|---|---|---|
| T3 | survival time / false disconnect | 2+ | 30 min | **P0** | liveness timeout value |
| T1 | safety reaction time | 3 | 30 min | **P0** | frame timestamping |
| T5 | fleet capacity | 1→N | 2 h | **P0** | T1–T4 |
| T2 | command determinism | 2+ | 20 min | P1 | bidirectional probe |
| T4 | video quality | 2+ | 20 min | P1 | frame-level analyser |
| T7 | graceful degradation | 2+ | 1 h | P1 | per-class accounting |
| T6 | fault containment | 3 | 1 h | P1 | aggressor harness |
| T10 | IT coexistence | 2+ | 30 min | P2 | — |
| T8 | recovery | 2+ | 1 h | P2 | RF shield / attenuator |
| T9 | mixed asset types | 2+2 | 30 min | P2 | UAV availability |
| T12 | control handover | 2+ | 20 min | P2 | multi-UI setup |
| T11 | soak | N | 8 h | **P0** (final) | all others |

**Arms:** two-tier (floor ON) · original scheduler. Add two-tier floor-OFF
only for UL-heavy families — the floor is a UL-only mechanism, so a floor-OFF
arm on a DL test is a wasted rebuild.

---

# Part 5 — Instrumentation required

The existing harness (`qos_ab.py`) measures one unidirectional UDP flow. It
cannot express most of the KPIs above. Needed:

| Capability | Why | Effort |
|---|---|---|
| **Bidirectional probe on one port** | T2 — the shared telemetry/command bearer is the architecture's central design choice and is currently untested | small — extend `qos_ab.py` to echo |
| **Frame-level video analyser** | T4, T1 — group packets by RTP timestamp, report frame completion and freezes | medium |
| **Consecutive-gap statistics** | T3 — the survival-time KPI is a gap, not a percentile | small |
| **Per-class throughput accounting** | T7 — degradation order needs per-5QI accounting at the MEC | small |
| **Aggressor harness** | T6 — scripted misbehaviour per variant | small |
| **Long-run bucketed logger** | T11 — per-minute KPI buckets over 8 h without gigabyte logs | medium |
| **MEC-side event log** | T3, T8, T12 — session lost, re-handshake, master change, with timestamps correlatable to gNB logs | small, MEC-side |

**Also fix before a large campaign:**
1. `floor_crumb_run` is zeroed before the log line prints it — the most
   diagnostic field always reads 0.
2. `LOG_D` is suppressed at the current level, so the PHR-cap line can never
   appear. Promote it to `LOG_I` under `IA_P5G_TELEMETRY`.
3. No PHR MAC CE has ever been received in any capture. Power-limited
   behaviour is currently invisible, which makes T5 and T8 partly
   uninterpretable.

---

# Part 6 — The deliverable: a guarantee sheet

The output of this campaign is one page a salesperson or safety assessor can
use:

```
IA-P5G private 5G — validated service guarantees
Configuration: <band, bandwidth, TDD pattern, gNB build, scheduler arm>
Fleet:         N × UGV, M × UAV, MECSTACKQOS profile

G1  Safety reaction, network share      max __ ms   (measured over __ events)
G2  Command jitter (p99 − p50)          __ ms
G3  Telemetry gap, worst case           __ ms   (survival time __ ms, margin __×)
    False disconnects                   __       (target: 0)
G4  Video frame delivery                __ %    freezes > 500 ms: __
G5  Admissible fleet size               __ assets
    Binding constraint at N+1           <which guarantee failed>
G6  Non-aggressor degradation           < __ %
G7  Degradation order verified          yes / no
G8  Recovery after 2 s outage           __ s
G9  With IT traffic present             guarantees held: yes / no
G10 Availability over 8 h               __ %   excursions: __
```

Every row traceable to a test, a date and a raw dataset.

---

# Part 7 — Sequencing

**Phase 0 — enablement (2 days).** Read out the MEC liveness timeout. Build
the bidirectional probe and the consecutive-gap analyser. Fix the three
instrumentation defects. Confirm classification via `[QOS-DUMP]`.

**Phase 1 — the two guarantees that can fail silently (2 days).** T3 then T1.
Both are P0, both are safety-adjacent, and neither has ever been measured.
T3 in particular may already be failing in every run to date — we have simply
never looked at consecutive telemetry gaps.

**Phase 2 — capacity (3 days).** T2, T4, then T5.

**Phase 3 — robustness (3 days).** T7, T6, T10, T8, T9, T12.

**Phase 4 — certification (1 day + 8 h).** T11 soak at admissible N minus
one, both scheduler arms.

---

# Part 8 — Open questions for the team

1. **What is the MEC's liveness timeout?** T3 cannot be scored without it,
   and it is the single most important number in this document.
2. Is there a bearer for `special` commands (release, sprayer)? They are
   safety-relevant and do not appear in the MECSTACKQOS flow rules — they may
   be falling to default 5QI9.
3. Does the UGV disconnect failsafe stop the robot immediately, or ramp down?
   Affects the T1 budget.
4. What are the real camera configurations (resolution, fps, bitrate, GOP)?
   T4's targets depend on them.
5. Real telemetry rate and command rate per asset type? T2 and T3 depend on
   the transfer interval.
6. How many UGVs and UAVs can be powered and positioned simultaneously? Caps
   the achievable N in T5.
7. Does the client have a stated safety reaction budget? If so, T1's pass
   criterion is given rather than discovered.
