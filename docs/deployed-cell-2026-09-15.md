# The deployed cell, from `docs/conf/gnbx310.conf` (2026-09-15)

**Status:** the gNB configuration currently in deployment, uploaded by the
user 2026-09-15 as a template (receive gain may be lower in the field).
It is the authority for the cell the guarantee scenarios model from this
date; the two discrepancies in §2 are recorded, not smoothed.

## 1. What the conf establishes

| parameter | conf | meaning |
|---|---|---|
| `dl_subcarrierSpacing` / `ul_subcarrierSpacing` | 1 | **numerology 1: 30 kHz, 0.5 ms slots**, 20 slots per frame |
| `dl_carrierBandwidth` / `ul_carrierBandwidth` | 106 | **106 PRB**, i.e. 40 MHz at 30 kHz |
| `dl_frequencyBand`, `absoluteFrequencySSB`, `dl_absoluteFrequencyPointA` | 78, 652800, 650784 | n78 TDD |
| `dl_UL_TransmissionPeriodicity` | 5 | **2.5 ms** — the file's own enum table reads `0=ms0p5, 1=ms0p625, 2=ms1, 3=ms1p25, 4=ms2, 5=ms2p5, 6=ms5, 7=ms10`; the trailing `# ms5` comment contradicts it and is wrong (2 + 1 + 2 slots fill exactly 2.5 ms at 30 kHz, not 5) |
| `nrofDownlinkSlots`, `nrofDownlinkSymbols`, `nrofUplinkSlots`, `nrofUplinkSymbols` | 2, 6, 2, 6 | **pattern `DDSUU`**, special slot 6 DL symbols, 2 gap, 6 UL symbols |
| `pdsch_AntennaPorts_XP`, `pusch_AntennaPorts`, `maxMIMO_layers` | 2, 2, 2 | two cross-polarised ports, **up to two MIMO layers** |
| `pusch_TargetSNRx10`, `pucch_TargetSNRx10` | 200, 250 | UL power-control targets 20 dB / 25 dB |
| `ul_bler_target_lower/upper` | 0.10 / 0.25 | the UL outer-loop link-adaptation band |
| `prach_ConfigurationIndex` | 159 | the RACH configuration `sim/random_access.py` ports |
| `ssb_periodicityServingCell` | 2 | 20 ms SSB |
| `max_rxgain` | 102 | may be lower in deployment (user) |
| `uess_agg_levels` | (0, 4, 2, 1, 0) | PDCCH candidates per aggregation level 1/2/4/8/16 in the UE-specific search space: 4 at AL2, 2 at AL4, 1 at AL8 -- the per-slot DCI budget behind the cap model, to be reconciled with `sim/resource.py`'s CCE budgets |
| `initialDLBWPcontrolResourceSetZero`, `initialDLBWPsearchSpaceZero` | 12, 0 | CORESET0 / search space 0 configuration index |
| `preambleTransMax`, `ra_ContentionResolutionTimer`, `powerRampingStep`, `preambleReceivedTargetPower`, `zeroCorrelationZoneConfig`, `ssb_perRACH_OccasionAndCB_PreamblesPerSSB` | 6, 7, 1, -90, 12, 15 | the RACH set `sim/random_access.py::RandomAccessConfig.deployed()` transcribes |
| `p0_NominalWithGrant`, `p0_nominal`, `pMax` | -90, -90, 23 | UL power control (dormant `sim/power.py`) |
| `uess_agg_levels`-adjacent: `max_pdschReferenceSignalPower` | -27 | RU power reference |
| SR periodicity, `min_grant_prb`, k1/k2 (`min_rxtxtime`) | absent | come from OAI's code defaults, not the conf; the SR value is being looked up in the deployed code base — until then the model keeps 10 slots, which is lawful at 30 kHz (`docs/rel16-baseline-2026-09-15.md` §4.2) |

## 2. Two discrepancies

1. **Three TDD patterns exist in this repo's history, and the scenarios used
   none of the deployed ones.** The guarantee scenarios run `DSUUU` at
   numerology 2 (0.25 ms slots, three uplink slots of five plus 9 of 14
   special-slot symbols: ~73 % uplink). The calibration log that produced
   the hardware numbers (`calibration-logs/twotier_startup_gnb.log`, lines
   29–40) ran `DDDDDDDSUU` every 5 ms at numerology 1 (7 DL, special 6/4/4,
   2 UL: ~24 % uplink). The conf now in deployment runs `DDSUU` every
   2.5 ms at numerology 1 (2 DL, special 6/2/6, 2 UL: ~49 % uplink). The
   uplink share the scenarios assumed is about 1.5× the deployed one, at
   twice the slot rate. **Decision (user, 2026-09-15): numerology 1 and the
   conf's pattern going forward**; the calibration comparisons (crumb
   fraction, RA timeline in `docs/builds-2026-09-08.md`) were made under
   the log's pattern and are read with that in mind.
2. **Two MIMO layers.** `scheduler/link.py` has no notion of layers, so
   the model's per-PRB capacity is single-layer. A good-SNR robot on the
   real cell can carry up to twice the bits per PRB. Recorded; deciding
   whether to model rank is its own commit.

## 3. What changes, what does not

- Changes (landed in the commit after this note): `sim/scenarios/deployed_cell.py` becomes the single source of
  the cell (numerology, bandwidth, pattern, special-slot split), every
  guarantee builder and `sim/parametric.py` take their carrier and TDD
  from it, and every slot count is derived from milliseconds through it.
- Does not change: `regression/baseline_studies_1_3.json` and the studies
  behind it. The corpus is the port's numeric pin, at numerology 1 and its
  own 30 MHz `DSUUU` radio; moving it would re-baseline without a fidelity
  gain for the guarantees. It stays as it is.
- Every guarantee result before this date (`docs/results-aligned-2026-09-14.md`,
  `docs/results-cg-2026-09-14.md`) was measured on the numerology-2 `DSUUU`
  cell and is superseded once the campaigns are re-run on this one.
