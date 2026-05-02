from dataclasses import dataclass

from .config import CarrierConfig, TDDConfig


@dataclass
class SlotGrid:
    slot_index: int
    direction: str  # 'D', 'S', 'U'
    dl_symbols: int
    ul_symbols: int
    prb_count: int
    pdcch_cce_budget: int


SYMBOLS_PER_SLOT = 14


class ResourceGrid:
    def __init__(self, carrier: CarrierConfig, tdd: TDDConfig):
        self.carrier = carrier
        self.tdd = tdd
        self.slot_duration_s = 0.001 / (2 ** carrier.numerology)
        self.prb_count = self._compute_prb_count()
        self.pattern = tdd.pattern

    def _compute_prb_count(self) -> int:
        scs_hz = 15_000 * (2 ** self.carrier.numerology)
        rb_hz = 12 * scs_hz
        # Crude: ignore guard bands. Good enough for comparative work.
        return int(self.carrier.bandwidth_hz / rb_hz)

    def slot_grid(self, slot_index: int) -> SlotGrid:
        kind = self.pattern[slot_index % len(self.pattern)]
        if kind == "D":
            dl, ul = SYMBOLS_PER_SLOT, 0
            cce = 48
        elif kind == "U":
            dl, ul = 0, SYMBOLS_PER_SLOT
            # U-slots have no PDCCH but UL grants are issued in earlier
            # D-slots. We amortize: give the U-slot a CCE budget so the
            # simulator's per-slot allocation cap reflects the rate at which
            # UL grants can flow.
            cce = 32
        else:  # S-slot
            dl_s, _guard_s, ul_s = self.tdd.s_slot_split
            dl, ul = dl_s, ul_s
            cce = 16
        oh = self.carrier.overhead_factor
        return SlotGrid(
            slot_index=slot_index,
            direction=kind,
            dl_symbols=int(dl * oh),
            ul_symbols=int(ul * oh),
            prb_count=self.prb_count,
            pdcch_cce_budget=cce,
        )
