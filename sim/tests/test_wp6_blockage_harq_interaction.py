"""WP6 commit 4: the acceptance-criterion demo -- does two-state Markov
blockage (sim/blockage.py, commit 2) interact with HARQ retry (WP5) the
way docs/wp6-plan.md sec 4 prediction #2 claims, and is that claim
actually falsifiable rather than true-by-construction?

**The mechanism, traced through the actual code before writing this test,
then corrected once against an empirical result that didn't match the
first version of that trace -- both steps recorded here, not just the
final answer.**

Trace: ``Allocation.snr_used_db`` (the SNR the scheduler saw when it
picked a TB's MCS) is frozen at ORIGINAL grant time and reused, unchanged,
across every retry of that same TB (``sim/harq.py::HarqProcess.
snr_used_db``, set once in ``allocate()``, read by every
``draw_harq_outcome`` call in ``sim/driver.py``'s retry loop). So a fresh
grant issued while ALREADY blocked gets its MCS threshold matched to the
current (degraded) reported SNR -- no mismatch, baseline BLER. The
mismatch that drives failure needs a threshold committed before true SNR
dropped, then evaluated against true SNR after it dropped.

**First version of this trace was wrong about how often that occurs, and
the empirical run below is what corrected it.** With ``cqi_delay_slots=0``
(the driver's bare default), that mismatch requires the rare coincidence
of a TB being specifically mid-RETRY (already failed once, awaiting its
next attempt) at the exact slot a blockage transition fires -- everything
granted fresh during an already-blocked window is correctly matched from
the start. Measured directly (not assumed): at ``cqi_delay_slots=0``,
long-blockage ``bytes_harq_lost`` across 7 seeds ranged 0-6193, WITH
overlap against the no-blockage baseline's 0-1000 range on several seeds
-- not a reliable signal.

**With ``cqi_delay_slots=8`` (the value ``scripts/scheduler_study.py::
CQI_DELAY_SLOTS`` uses -- CLAUDE.md's own note that this, not the bare
0 default, is what every real study in this branch actually runs with),
the effect becomes dramatic and reliable.** CQI delay means
``get_reported_snr_db()`` lags true SNR by 8 slots -- so for roughly the
first 8 slots after a blockage transition, EVERY fresh grant (not just a
coincidental mid-retry one) gets a threshold matched to the still-stale,
pre-blockage-good report while its own attempt (and any retries, all
reusing that same frozen threshold) are drawn against the now-degraded
true SNR. This turns a rare per-episode coincidence into a per-episode
near-certainty, and is why the demo below uses ``cqi_delay_slots=8``
rather than the isolated-mechanism ``0`` this file's own earlier draft
used -- CQI delay turned out to be necessary for a reliable demonstration,
not an avoidable confound. Recorded as a correction, not silently fixed.

**Measured, across 7 fixed seeds, at cqi_delay_slots=8
(sim/tests/test_wp6_blockage_harq_interaction.py's own numbers, not
estimated):**

| seed | no blockage | short (4 slots) | long (600 slots) |
|---|---|---|---|
| 1 | 0 | 200 | 12137 |
| 2 | 800 | 800 | 8970 |
| 3 | 400 | 0 | 21514 |
| 4 | 0 | 0 | 6816 |
| 5 | 0 | 0 | 5600 |
| 6 | 0 | 0 | 5200 |
| 7 | 400 | 400 | 10997 |

No-blockage and short-blockage never exceed 800 bytes; long blockage
never drops below 5200 -- a clean, non-overlapping separation across
every seed tried, not a cherry-picked one. Against WP5's own reported
baseline (``bytes_harq_lost`` nonzero on only 6 of 510 flow-records
across the FULL 22-scenario/3-study regression corpus, most of those
6 in the low hundreds of bytes -- docs/wp5-plan.md commit 4b) -- this
single demo flow's long-blockage arm alone produces more HARQ-loss bytes
than that entire corpus combined, from one mechanism, in one flow.

**Design, to isolate the mechanism:**
- Single UE, single dense DL flow (``traffic_kind="deterministic"``,
  period well below the retry cycle) so a fresh grant (the thing that
  actually matters, per the corrected trace above) is issued often enough
  to have many chances to land in the post-transition mismatch window.
- ``coherence_slots=2`` (fast AR(1) convergence) so true SNR actually
  reaches the new (blocked) mean within a slot or two of the Markov
  transition.
- ``pdb_ms`` generous (5000ms) so PDB-clock expiry (a different loss path,
  sim/buffer.py::expire()) never fires during the horizon -- any loss
  observed is attributable to HARQ retry-cap exhaustion specifically
  (``bytes_harq_lost``/``buffers.discard_harq_loss``), not competing with
  the other discard mechanism (``bytes_dropped_pdb``).
- RoundRobin (docs/wp6-plan.md sec 4 design note): avoids PF's per-UE
  ``_r_avg`` cross-direction coupling and TwoTier's SPS backlog-pooling
  finding (README sec8) -- neither is relevant to what's being isolated
  here, and RoundRobin's own ``snr_used_db=channel.get_reported_snr_db(..)``
  (sim/baselines/round_robin.py) is exactly the mechanism this test needs.
- Short and long arms use DIFFERENT ``mean_unblocked_slots`` so both
  produce roughly the same number of blockage episodes (~15) over the
  same horizon (matching episode count, not duty cycle) -- otherwise a
  higher episode count on the short arm could produce more losses even if
  each individual episode is less likely to cause one, confounding
  "duration" with "frequency."

**IMPORTANT correction to this file's own metric choice, found while
writing it:** the first version of this test checked
``summary["harq_exhausted_count"]`` and observed 0 in every arm, which
looked like a refutation. That counter is HARQ POOL exhaustion (no free
process slot, ``sim/harq.py::HarqProcessPool`` returning None,
``sim/driver.py``'s main allocation loop) -- an entirely different thing
from RETRY-CAP exhaustion (``harq_round_max`` attempts all failed,
``buffers.discard_harq_loss`` -> ``bytes_harq_lost``, CLAUDE.md's own
"the retry budget before a TB is abandoned (residual loss,
bytes_harq_lost)"). This scenario's single flow never has more than 1-2
processes contending for its 8-deep DL pool, so pool exhaustion staying 0
in every arm is expected and uninformative either way -- the real signal
was always in ``bytes_harq_lost``, checked here instead.

**What would REFUTE the duration hypothesis, stated explicitly per the
sign-off's request:** if the long arm were not reliably, non-overlappingly
separated from the short arm and the no-blockage baseline -- e.g. if long
sometimes landed inside the 0-800 range short/baseline occupy, or short
sometimes landed in the thousands -- that would refute "duration relative
to the retry cycle" as the mechanism. It would not have been enough for
long to average higher than short; the claim under test is that they
occupy genuinely different regimes, and the 7-seed table above is what
was checked against that bar, not against "long > short on average."

Not added to scripts/regression_corpus.py's 22-record corpus (see
docs/wp6-plan.md sec 4's "stays outside the corpus" decision) -- this is
a multi-configuration hypothesis test by design (the whole point is
comparing short vs long), not a fixed single-run snapshot the corpus
format is for, and its own construction (single UE, extreme blockage
parameters chosen to make the mechanism legible, a non-default
cqi_delay_slots) isn't meant to stand in as a durable regression baseline
the way factory_robots_scenario etc. are.
"""

from sim.baselines.round_robin import RoundRobin
from sim.config import BlockageConfig, CarrierConfig, FlowConfig, ScenarioConfig, UEConfig
from sim.driver import run

HORIZON_SLOTS = 15_000
TARGET_CYCLE_SLOTS = 1_000  # unblocked + blocked, chosen so both arms get ~15 episodes
SHORT_BLOCKED_SLOTS = 4  # docs/wp6-plan.md commit 2: verified below the ~8-slot UL retry cycle
LONG_BLOCKED_SLOTS = 600  # commit 2's own default; p5g-sim-plan.md's "hundreds of ms"
CQI_DELAY_SLOTS = 8  # scripts/scheduler_study.py::CQI_DELAY_SLOTS -- see module docstring
SEEDS = (1, 2, 3, 4, 5, 6, 7)  # the exact 7 seeds this file's own docstring table reports

# Thresholds set from the measured table in this module's own docstring:
# no-blockage/short never exceeded 800; long never dropped below 5200.
# Margins below are comfortable, not tight, against those measured extremes.
AMBIENT_MAX_HARQ_LOST = 1000
LONG_MIN_HARQ_LOST = 4000
LONG_MIN_MULTIPLE_OF_AMBIENT = 4


def _build_scenario(blockage: BlockageConfig | None, seed: int) -> ScenarioConfig:
    ue = UEConfig(
        ue_id=1,
        mean_snr_db=20.0,
        coherence_slots=2,
        blockage=blockage,
    )
    flow = FlowConfig(
        ue_id=1,
        qfi=9,
        direction="DL",
        flow_class="PF",
        pdb_ms=5000.0,  # generous: isolate HARQ-exhaustion loss from PDB-expiry loss
        traffic_kind="deterministic",
        traffic_params={"period_ms": 1.0, "bytes_per_period": 200},
    )
    return ScenarioConfig(
        name="wp6_blockage_harq_demo",
        horizon_slots=HORIZON_SLOTS,
        carrier=CarrierConfig(bandwidth_hz=30_000_000, numerology=1),
        ues=[ue],
        flows=[flow],
        seed=seed,
    )


def _bytes_harq_lost(blockage: BlockageConfig | None, seed: int, cqi_delay_slots: int) -> int:
    summary = run(
        _build_scenario(blockage, seed), RoundRobin(), cqi_delay_slots=cqi_delay_slots
    )
    return summary["flows"]["ue1_qfi9"]["bytes_harq_lost"]


def _short_config() -> BlockageConfig:
    return BlockageConfig(
        mean_unblocked_slots=TARGET_CYCLE_SLOTS - SHORT_BLOCKED_SLOTS,
        mean_blocked_slots=SHORT_BLOCKED_SLOTS,
        blocked_extra_loss_db=17.5,
    )


def _long_config() -> BlockageConfig:
    return BlockageConfig(
        mean_unblocked_slots=TARGET_CYCLE_SLOTS - LONG_BLOCKED_SLOTS,
        mean_blocked_slots=LONG_BLOCKED_SLOTS,
        blocked_extra_loss_db=17.5,
    )


def test_pure_retry_freeze_without_cqi_delay_is_too_unreliable_to_demonstrate():
    """Records the corrected finding from this file's own docstring: at
    cqi_delay_slots=0, the mismatch mechanism still exists (it can fire)
    but isn't a reliable signal -- long-blockage bytes_harq_lost can land
    at 0, the same as the no-blockage baseline, purely from which seed is
    used. This is why the other tests below use cqi_delay_slots=8, and
    this test exists so that fact stays checked rather than just claimed
    in prose."""
    long_config = _long_config()
    results = [_bytes_harq_lost(long_config, seed, cqi_delay_slots=0) for seed in SEEDS]
    assert any(r == 0 for r in results), (
        "expected at least one seed where cqi_delay_slots=0's long-blockage "
        "bytes_harq_lost is 0 -- if this no longer happens, the 'CQI delay "
        "is necessary for a reliable demonstration' finding above needs "
        "re-checking, not silently dropping this test"
    )


def test_no_blockage_and_short_blockage_stay_at_ambient_harq_loss():
    """mean_blocked_slots=4 is well below the DL retry cycle -- most
    mismatched TBs should recover on a later attempt once the brief dip
    ends, per this file's own mechanism analysis, staying in the same
    range as having no blockage mechanism at all."""
    short_config = _short_config()
    for seed in SEEDS:
        baseline = _bytes_harq_lost(None, seed, cqi_delay_slots=CQI_DELAY_SLOTS)
        short = _bytes_harq_lost(short_config, seed, cqi_delay_slots=CQI_DELAY_SLOTS)
        assert baseline <= AMBIENT_MAX_HARQ_LOST, f"seed={seed}: baseline={baseline}"
        assert short <= AMBIENT_MAX_HARQ_LOST, f"seed={seed}: short={short}"


def test_long_blockage_spikes_harq_loss_far_above_short_every_seed():
    """The falsifiable claim: not that long averages higher than short,
    but that the two occupy genuinely separate, non-overlapping regimes
    on EVERY seed tried -- see this module's docstring table and its
    explicit refutation criterion."""
    short_config = _short_config()
    long_config = _long_config()
    for seed in SEEDS:
        short = _bytes_harq_lost(short_config, seed, cqi_delay_slots=CQI_DELAY_SLOTS)
        long = _bytes_harq_lost(long_config, seed, cqi_delay_slots=CQI_DELAY_SLOTS)
        assert long >= LONG_MIN_HARQ_LOST, f"seed={seed}: long={long}"
        assert long >= LONG_MIN_MULTIPLE_OF_AMBIENT * max(1, short), (
            f"seed={seed}: long={long}, short={short}"
        )
