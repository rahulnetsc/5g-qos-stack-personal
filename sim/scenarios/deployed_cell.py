"""The deployed cell -- the ONE source every guarantee scenario takes its radio from.

Values are transcribed from `docs/conf/gnbx310.conf`, the OAI gNB
configuration in deployment (2026-09-15; `docs/deployed-cell-2026-09-15.md`
records what each establishes and the two discrepancies with earlier
assumptions). Before this module the builders each carried `_NUMEROLOGY = 2`,
`_TDD_PATTERN = "DSUUU"` and a `SLOT_S = 0.00025` of their own -- a cell that
was never the deployed one -- and every slot count was a literal that
silently encoded that numerology.

    numerology 1  -> 30 kHz, 0.5 ms slots, 20 slots per frame
    106 PRB       -> `dl_carrierBandwidth = 106` (40 MHz at 30 kHz; set
                     explicitly because `ResourceGrid`'s bandwidth formula
                     ignores guard bands and would give 111)
    DDSUU / 2.5 ms-> `dl_UL_TransmissionPeriodicity = 5` (ms2p5 by the
                     conf's own enum table), 2 DL slots, 2 UL slots, special
                     slot 6 DL / 2 gap / 6 UL symbols

Slot counts are DERIVED here from milliseconds (`slots`), never written as
literals in a builder or runner: a literal is a claim about the numerology,
and the claim was wrong for two days of results.

Must not import the driver or any scheduler; `sim.config` only.
"""
from __future__ import annotations

from ..config import CarrierConfig, TDDConfig

__all__ = ["NUMEROLOGY", "BANDWIDTH_HZ", "PRB_COUNT", "TDD_PATTERN", "S_SLOT_SPLIT",
           "SLOT_S", "SLOTS_PER_FRAME", "slots", "carrier", "tdd"]

NUMEROLOGY: int = 1
BANDWIDTH_HZ: int = 40_000_000
PRB_COUNT: int = 106
TDD_PATTERN: str = "DDSUU"
S_SLOT_SPLIT: tuple[int, int, int] = (6, 2, 6)
SLOT_S: float = 0.001 / (2 ** NUMEROLOGY)
SLOTS_PER_FRAME: int = 10 * (2 ** NUMEROLOGY)


def slots(ms: float) -> int:
    """Whole slots for a duration in milliseconds at this cell's numerology,
    rounded to nearest, never below one."""
    return max(1, int(round(ms / 1000.0 / SLOT_S)))


def carrier() -> CarrierConfig:
    return CarrierConfig(bandwidth_hz=BANDWIDTH_HZ, numerology=NUMEROLOGY, prb_count=PRB_COUNT)


def tdd() -> TDDConfig:
    return TDDConfig(pattern=TDD_PATTERN, s_slot_split=S_SLOT_SPLIT)
