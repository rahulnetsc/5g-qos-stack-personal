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
    max_sched_ues_override: int | None = None

    @property
    def max_sched_ues(self) -> int:
        """M-6 -- the deployed per-slot UE-count cap, DERIVED from the grid.

        Both deployed schedulers cap how many UEs are scheduled per slot per
        direction **before any CCE search**
        (`gNB_scheduler_dlsch.c:1019-1023`, `gNB_scheduler_ulsch.c:3017-3021`):

            max_sched_ues = bw / (average_agg_level * NR_NB_REG_PER_CCE)
            max_sched_ues = min(max_sched_ues, MAX_DCI_CORESET)

        with `average_agg_level = 4` (a fixed literal in the C, not a computed
        aggregation level), `NR_NB_REG_PER_CCE = 6`, `MAX_DCI_CORESET = 8`, and
        `bw` the carrier bandwidth **in PRBs**. At the deployment's N_RB 106
        this is **4**.

        **Derived from `prb_count`, never written as a literal 4**, so a
        bandwidth change cannot silently invalidate it -- CLAUDE.md's
        restated-count rule.

        **And this resolves the `average_agg_level` known issue**: the real
        code does not use the aggregation level to PRICE a grant, it uses a
        fixed 4 to derive a UE-COUNT CAP. "Model it fixed or SNR-dependent" was
        the wrong question.
        """
        if self.max_sched_ues_override is not None:
            return self.max_sched_ues_override
        return max(1, min(self.prb_count // (4 * 6), 8))


SYMBOLS_PER_SLOT = 14


class ResourceGrid:
    def __init__(self, carrier: CarrierConfig, tdd: TDDConfig,
                 max_sched_ues_override: int | None = None):
        self.carrier = carrier
        self.tdd = tdd
        #: M-6 fidelity knob, DEFAULT None = derive from this carrier's PRB
        #: count. Set only to answer "what would the DEPLOYMENT's cap do here"
        #: -- the deployment runs N_RB 106 (cap 4) while this repo's parametric
        #: cell is 55 PRB (cap 2), so the faithful FORMULA yields a harsher
        #: VALUE than the deployed system's. Never a default; every run states
        #: which value it used.
        self.max_sched_ues_override = max_sched_ues_override
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
            max_sched_ues_override=self.max_sched_ues_override,
        )
