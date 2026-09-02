# G9 re-verification — the evidence for §34.5a

These re-ran the G9 campaign's exact configuration to check §34.5's
overlap mechanism, and refuted it. Kept in the repo tree rather than a
session scratchpad (`docs/HANDOVER-new-machine.md` §5.2's recorded failure
mode) because they are the evidence base for a **verdict change** on G9's
row, not throwaway analysis.

| file | what it establishes |
|---|---|
| `verify_cold.py` | per arm × `paired_seeds(10)`: cold events **recorded** vs attaches **completed**. Result: PF 50/50, Reservation 50/50, **TwoTier 10 events / 0 completed**. Derives the scheduled count from the schedule itself (`sum(JoinEvent.kind == "power_on")`), never restated |
| `verify_warm.py`, `verify_warm_others.py` | the warm counterpart — TwoTier 38 events / 29 completed, reproducing the committed campaign's `events/run = 3.8` bit-for-bit, which is how the re-run is known to be the same configuration |
| `trace.py` | the scheduler spy: wraps `allocate()` and counts UL grants to the joiner. TwoTier 122 grants, **all at slots 1–1997, none at ≥ 2000**; PF 823 after the handshake instant |
| `diag.py` | per-flow dump — `ue1_qfi70` with 64 bytes dropped to PDB, and `bytes_reported > 0` on 1,296 slots, which rules out the masking/BSR path |
| `cold_all.json` | the raw per-run rows behind the cold table |

Run from the repo root under `uv run`. They import `sim/` directly and need
no sweep artefacts, so they reproduce anywhere the repo does.

**Not established by any of these:** *why* TwoTier stops granting the
joiner after re-attach. The `reset_ue(scope="full")` / Tier-1 re-solve
hypothesis is a lead and needs its own trace before it is written down.
