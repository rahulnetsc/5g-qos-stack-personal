# Handover and runbook: where the project stands on 2026-09-15, and how to start the five-arm campaign on a fresh Linux machine

Hand this file to a new session with "this is where we are; start the
run". §0 is the state, §1 onward is the procedure. The repository's own
`CLAUDE.md` and `README.md` are the standing rules and are authoritative;
this file only says what happened last and what to do next.

## 0. Where we are

**The project.** A Python MAC-layer simulator (`sim/`) evaluating four
schedulers against the factory guarantees G1–G12
(`docs/IA_P5G_Factory_Guarantee_Test_Plan.md`): PF, and faithful ports of
the two OAI branches (`scheduler/reservation.py`, `scheduler/two_tier.py`),
plus labelled divergence arms that say what a change would do. Every
comparison is within seed, every runner is parallel and banks each run to
a ledger, every count is derived, and nothing is a registered claim
unless `config/published_claims.yml` says so.

**What was decided and built this week, newest first** (each its own
commit on `feat/high-fidelity-sim`):

| commit | what |
|---|---|
| `f110d0f` `91a7e6a` `b1543df` `c8e00a2` | this runbook; `docs/results-cell-2026-09-15.md` opened on the deployed cell with G1, G3 and G5 from the four-arm Windows run; report scripts under `sweeps/cell-2026-09-15/` |
| `a1121cf` | the campaign script carries five arms (ConfigSched added), a fresh `OUT`, workers from `nproc`; every runner resolves the ConfigSched arm (smoke-run) |
| `eeee0c5` `fea8bce` | ConfigSched's first measurement, expectations registered first: G3 on three paired seeds (`sweeps/config-sched-2026-09-15/SCORED.md`) |
| `993dfc7` | **the configuration-based scheduler prototype** `sim/baselines/config_sched.py` (arm `ConfigSched`): Tier 1 plans (rate, visits) per 100 ms window by floors then max-min greedy; Tier 2 places by earliest due visit; crumbs do not stamp |
| `1f5d105` `4d3613d` | **the deployed cell is the cell**: `docs/conf/gnbx310.conf` → `sim/scenarios/deployed_cell.py` (numerology 1, 106 PRB, `DDSUU` 6/2/6); every builder and runner derives slot counts from milliseconds through it; the regression corpus stays on its own radio |
| `600de55` `837056c` | **Rel-16 is the compliance baseline** (the OAI gNB and the COTS UE are Rel-16): `docs/Rel 16/` editions, `docs/rel16-baseline-2026-09-15.md` with the clause delta; UE-side behaviour cites Rel-16 only |
| `970e082` `e3919c3` and before | configured grants, Type 2, three builds: per-config HARQ block and phase, per-channel masking, `+CGt` (period/phase from the declared traffic, conditional on a core that sends TSCAI) |

**What the measurements say so far** (deployed cell, four arms, Windows,
`docs/results-cell-2026-09-15.md`):

- The cell has 64 % of the uplink the scenarios used to have and 1.9× the
  downlink (60.5 / 60.5 Mbps raw at 20 dB against 94.2 / 31.4).
- G3 liveness verdicts unchanged: PF and ProtoRRageD2 pass every seed to
  N = 24, both faithful arms fail on service cadence; part 3 (p98 ≤ 95 ms)
  is now a capacity failure on every arm from N = 12.
- G5: admissible fleet PF 8, Reservation 7, TwoTier none, ProtoRRageD2 8;
  the Proto arm has no load knee to ×1.5 where PF knees at ×1.4.
- G1: 0 breaches of 1 280 on every arm; PF alone degrades with fleet size
  at cap 2.
- ConfigSched (three-seed G3 probe): the instrument robot's heartbeat is
  100/100 at every N with p98 31–37 ms at N = 24 — the rank is gone; the
  flood robot's own heartbeat loses half its messages at N = 24 because
  the visit interval equals the message period and the PDB, a visit is
  stamped by attribution, and camera floors are dropped by `ue_id` under
  overload. Three one-change fixes are named in
  `docs/config-scheduler-handoff.md` §8b.1 and are NOT built.

**Done 2026-09-16:** the full five-arm campaign with CG on for every
guarantee ran on Linux (21 steps, 4 h 01, `sweeps/cell-2026-09-16-linux/`,
running log `docs/campaign-cell-2026-09-16-linux.md`); every section of
`docs/results-cell-2026-09-15.md` is written; the four faithful arms are
byte-identical to the Windows run on G1/G3/G5. Two ConfigSched bugs were
fixed first (`65d45ae`, `f6aa911`); its v2 formulation is designed
(`docs/config-scheduler-handoff.md` §8c), not built.

**What is not done.** The
three ConfigSched fixes; an isolated timing of ConfigSched's Tier 1 and a
greedy-versus-LP exactness test on captured instances; the three-CG-per-
robot measurement (telemetry, monitoring, video floor); SR periodicity and
k1/k2 from the deployed OAI RRC source (the model assumes 10 slots); the
two-MIMO-layer question; G8; held-out seeds; the port-back design note.

**Standing rules that bite** (the rest are in `CLAUDE.md`): run everything
parallel on all cores but one; one fidelity change per commit with the
full suite and `regression_corpus.py --check`; register expectations
before reading an artefact and score misses as misses; derive every count;
label every divergence arm; Rel-16 for anything the UE must do; never edit
a running campaign script; never `pgrep -f` a script name from a loop.

---

Everything needed is on branch `feat/high-fidelity-sim`
at or after commit `f110d0f`. The campaign measures the ten guarantees
(G1, G2, G3, G4, G5, G6, G7, G9, G10, G12) on the deployed cell
(numerology 1, 106 PRB, `DDSUU` 6/2/6 — `docs/deployed-cell-2026-09-15.md`)
for five arms, then the configured-grant variants of each:

| arm | what it is |
|---|---|
| `PF` | proportional fair, contract-blind |
| `Reservation` | faithful port of the reservation branch |
| `TwoTier` | faithful port of the two-tier branch (`scheduler/two_tier.py`) |
| `ProtoRRageD2` | labelled divergence: two-tier with its UL Tier-2 replaced by slots-since-last-grant ordering |
| `ConfigSched` | labelled divergence: the configuration-based scheduler prototype (`sim/baselines/config_sched.py`, `docs/config-scheduler-handoff.md` §8b) |
| `+CG` / `+CGt` on each | restricted Type 2 configured grant on the heartbeat; `+CGt` takes period and phase from the declared traffic |

Nothing is registered as a claim; `docs/results-cell-2026-09-15.md` is
the document the results go into.

## 1. Set up (10 minutes)

```bash
# uv, if the machine does not have it
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

git clone https://github.com/rahulnetsc/5g-qos-stack-personal.git
cd 5g-qos-stack-personal
git checkout feat/high-fidelity-sim
uv sync
```

Check the tree runs before spending hours on it. The suite takes about
two minutes on 23 workers; the two `--deselect`s are failures that predate
this work (`test_verify_claims`, one `test_wp9_sweep_memory` case):

```bash
uv run --with pytest-xdist pytest sim/tests -n "$(( $(nproc) - 1 ))" -q -p no:cacheprovider \
  --deselect sim/tests/test_verify_claims.py \
  --deselect sim/tests/test_wp9_sweep_memory.py::test_scoring_variations_are_the_four_pre_registered_ones
uv run python scripts/parallel_audit.py --check
uv run python scripts/g3_stress.py --dry-run --arms PF,ConfigSched,ConfigSched+CG --parts A --fixed-n 6 --caps 4 --seeds 1
```

Expected: the suite green, the audit printing `none -- every script's
calls match`, and the dry-run listing its runs without error.

## 2. Launch (one command)

```bash
OUT=sweeps/cell-2026-09-16-linux setsid nohup bash sweeps/cell-2026-09-15/run_campaign.sh > /dev/null 2>&1 &
```

Three rules, each learned the hard way:

- **`OUT` must be a directory that does not exist yet.** The runners bank
  every finished run to a ledger (`*.runs.jsonl`) and RESUME from whatever
  they find under `OUT`; a reused directory is not a fresh run.
- **Do not edit `run_campaign.sh` while it is running.** Bash reads the
  script by byte offset as it goes; a patch mid-run killed the Windows
  campaign after its third step with a syntax error. Change a copy.
- **Launch detached** (`setsid nohup … &`, as above), never from a
  terminal or a Claude session that can be closed. The script itself is
  sequential; each step is internally parallel on `nproc - 1` workers
  (override with `WORKERS=n`).

Expected duration on a 24-thread machine: **4 to 5 hours** (the four-arm
Windows steps measured G3 759 s, G5 719 s, G1 1 198 s; the fifth arm costs
about what PF does; the CG set is the G3, G5, G7 and G10 runners twice
over). Fewer cores scale it up roughly linearly.

## 3. Monitor

```bash
cat sweeps/cell-2026-09-16-linux/campaign.log            # one start/end line per step, with rc and seconds
tail -c 300 sweeps/cell-2026-09-16-linux/g3.log            # the running step's progress counter
ls -la sweeps/cell-2026-09-16-linux/aligned sweeps/cell-2026-09-16-linux/cg
```

Steps, in order: `g3 g5 g1 g2 g4 g6 g7 g10 g9 g12`, then
`g3_cg g3_cgt g5_cg g5_cgt g7_cg g10_cg`. A step with `rc=` other than 0
in `campaign.log` failed; the script continues to the next step, so read
that step's `.log` and re-run it alone with the same `--out` (it resumes
from its ledger).

Liveness: `ps -ef | grep "[p]ython"` — spawn workers do not carry the
script name in their command line, so never `pgrep -f g3_stress` and never
wait in a loop that greps for its own pattern (`CLAUDE.md`).

## 4. After it finishes

Regenerate every table from the artefacts (the directory is the argument):

```bash
uv run python sweeps/cell-2026-09-15/report_tables.py    sweeps/cell-2026-09-16-linux
uv run python sweeps/cell-2026-09-15/report_tables_cg.py sweeps/cell-2026-09-16-linux
```

Commit the artefacts and logs (the `*.runs.jsonl` ledgers are gitignored
on purpose):

```bash
git add sweeps/cell-2026-09-16-linux/aligned/*.json sweeps/cell-2026-09-16-linux/cg/*.json sweeps/cell-2026-09-16-linux/*.log
git commit -m "Deployed-cell campaign, five arms, Linux run: artefacts"
git push origin feat/high-fidelity-sim
```

Then extend `docs/results-cell-2026-09-15.md`: its §0 states the
configuration, its §1, §3 and §5 (G1, G3, G5) hold the four-arm Windows
figures and gain the ConfigSched column, every other section is marked
*pending* and follows the previous document's shape
(`docs/results-aligned-2026-09-14.md`). The four faithful-arm columns
should reproduce the Windows figures exactly on the same seeds — the
comparison is a determinism check across platforms; a difference is a
finding, not noise.

## 5. What to expect from ConfigSched, registered before the run

From its three-seed G3 probe (`sweeps/config-sched-2026-09-15/SCORED.md`):

- On the instrument robot it delivers every heartbeat at every fleet size,
  p98 31–37 ms at N = 24. Expect G3 parts 1/1s/2 at 10/10 to N = 16.
- On the flood robot's own heartbeat at N = 24 it loses about half the
  messages (visit interval = message period = PDB; a visit stamped by
  attribution; camera floors dropped by `ue_id` under overload). Expect a
  part-1 failure at N = 24 and a poor G7 clause 3 on the aggressor's own
  telemetry.
- Its part 3 (p98 ≤ 95 ms) is at the expiry ceiling from N = 10 on the
  flood robot, for the same reason.
- G1/G2 (downlink) should look like the deadline-tier arms: due visits are
  placed before best-effort, so the STOP and `cmd_vel` are not demoted.
- G9: `reset_ue` clears a re-joined UE's visit clock; a joiner is due
  immediately, so cold attach should be PF-like, not TwoTier-like.

The three one-change fixes the probe motivated are NOT built
(`docs/config-scheduler-handoff.md` §8b.1): the run measures the prototype
as committed.

## 6. If something goes wrong

- A step dies with `ScheduleTooLongForHorizon`: the horizon flag is too
  short for that builder's schedule — the campaign script passes none for
  G9, do not add one.
- `check_for_orphans` refuses to start a pool: a previous pool's workers
  are alive; kill them by PID (the message lists them).
- Memory: at ~500 MB per worker the 23-worker steps peak near 11 GB; on a
  smaller machine set `WORKERS` accordingly.
- The whole thing was killed: relaunch with the same `OUT`; every runner
  resumes from its ledger and re-enters the banked rows into the artefact.
