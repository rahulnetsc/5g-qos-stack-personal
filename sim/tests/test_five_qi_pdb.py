"""FIVE_QI_PDB_MS -- the standardised 5QI -> PDB table (TS 23.501 5.7.4-1).

WHY THIS TABLE EXISTS. `priority_level` has always been 5QI-derived, but
`pdb_ms` was a bare 100.0 default with no table behind it -- so a device
profile's latency budgets were the AUTHOR'S OPINION rather than the QoS
class's definition. PDB is standardised per 5QI; it should be derived.

WHY IT IS OPT-IN. The regression corpus is frozen. Switching the default to
derivation would move every flow whose standardised PDB differs from 100 --
a 5QI-9 flow jumps 100 -> 300 ms -- and shift every record. So derivation
is requested with DERIVE_PDB_FROM_5QI, mirroring how `lcg == -1` already
resolves.
"""

import pytest

from scheduler.flow import (
    DERIVE_PDB_FROM_5QI,
    FIVE_QI_PDB_MS,
    FIVE_QI_PRIORITY,
    FlowConfig,
    pdb_for_5qi,
)

# Transcribed independently of the module, so a one-character edit to the
# table fails here rather than silently changing every derived flow.
EXPECTED = {
    1: 100.0, 2: 150.0, 3: 50.0, 4: 300.0,
    5: 100.0, 6: 300.0, 7: 100.0, 8: 300.0, 9: 300.0,
    79: 50.0, 80: 10.0,
    82: 10.0, 83: 10.0, 84: 30.0, 85: 5.0, 86: 5.0,
}


def test_table_matches_the_transcribed_values_exactly():
    assert FIVE_QI_PDB_MS == EXPECTED


@pytest.mark.parametrize("qfi,pdb", sorted(EXPECTED.items()))
def test_pdb_for_5qi(qfi, pdb):
    assert pdb_for_5qi(qfi) == pdb


def test_delay_critical_classes_are_the_tight_ones():
    """A sanity property that would catch a transposed table: the
    delay-critical GBR classes (82-86) must all be tighter than the
    conversational-voice budget, and 85/86 tightest of all."""
    assert all(FIVE_QI_PDB_MS[q] <= 30.0 for q in (82, 83, 84, 85, 86))
    assert FIVE_QI_PDB_MS[85] == FIVE_QI_PDB_MS[86] == 5.0
    assert FIVE_QI_PDB_MS[1] == 100.0


def test_priority_and_pdb_tables_cover_the_same_core_classes():
    """Corroboration recorded in the module docstring: the source's priority
    column matched this repo's independently transcribed FIVE_QI_PRIORITY.
    If someone adds a 5QI to one table only, that agreement silently ends."""
    core = {1, 2, 3, 4, 5, 6, 7, 8, 9, 82, 83, 84, 85}
    assert core <= set(FIVE_QI_PDB_MS)
    assert core <= set(FIVE_QI_PRIORITY)


def test_derivation_is_opt_in_and_the_default_is_unchanged():
    """The corpus-preserving property, asserted so nobody 'tidies' the
    default into derivation and moves every frozen record."""
    assert FlowConfig(ue_id=1, qfi=9, direction="UL").pdb_ms == 100.0
    assert FlowConfig(ue_id=1, qfi=82, direction="DL").pdb_ms == 100.0

    derived = FlowConfig(ue_id=1, qfi=9, direction="UL",
                         pdb_ms=DERIVE_PDB_FROM_5QI)
    assert derived.pdb_ms == 300.0
    tight = FlowConfig(ue_id=1, qfi=82, direction="DL",
                       pdb_ms=DERIVE_PDB_FROM_5QI)
    assert tight.pdb_ms == 10.0


def test_explicit_value_always_wins():
    f = FlowConfig(ue_id=1, qfi=82, direction="DL", pdb_ms=7.5)
    assert f.pdb_ms == 7.5


def test_unlisted_5qi_raises_rather_than_inventing_a_default():
    """A silent fallback would encode the author's opinion as the spec's --
    the exact failure the table exists to prevent."""
    with pytest.raises(ValueError, match="no standardised PDB"):
        pdb_for_5qi(999)
    with pytest.raises(ValueError, match="no standardised PDB"):
        FlowConfig(ue_id=1, qfi=999, direction="UL",
                   pdb_ms=DERIVE_PDB_FROM_5QI)
