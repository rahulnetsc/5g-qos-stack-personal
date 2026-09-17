#!/usr/bin/env bash
# Completes the SEVEN-ARM footing. The 2026-09-16 campaign ran five arms +CG
# (PF/Reservation/TwoTier/ProtoRRageD2/ConfigSched); the ConfigSched2 family
# was measured only as single-arm increments against its own baseline, so no
# cross-arm table existed for G1/G2/G3/G5/G6/G10/G12. This runs exactly the
# campaign's invocations for the two missing arms into a fresh directory.
# G9 is already done (g9_groupF_2026-09-17.json) and G4's runner takes every
# arm in one artefact, so neither is repeated here.
set -u
export PATH="$HOME/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
cd "$(dirname "$0")/../.." || exit 1
OUT=${OUT:-sweeps/cs2-increments/sevenarm-2026-09-17}
mkdir -p "$OUT"
W=${WORKERS:-20}
A2="ConfigSched2+CG,ConfigSched2X7+CG"
H5=$(uv run python -c "from sim.scenarios import deployed_cell as c; print(c.slots(5000))")
LOG="$OUT/campaign.log"
step() { local name=$1; shift
  echo "=== $name start $(date '+%F %T')" | tee -a "$LOG"
  local t0=$SECONDS; "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  echo "=== $name end   $(date '+%F %T')  rc=$rc  $((SECONDS-t0))s" | tee -a "$LOG"; }
echo "sevenarm start $(date '+%F %T') workers=$W H5=$H5 HEAD=$(git rev-parse --short HEAD) ARMS=$A2" | tee -a "$LOG"
step g3  uv run python scripts/g3_stress.py       --arms "$A2" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/g3.json"
step g5  uv run python scripts/g5_video.py        --arms "$A2" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/g5.json"
step g7  uv run python scripts/g7_aggressor.py    --arms "$A2" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/g7.json"
step g10 uv run python scripts/g5_consolidation.py --arms "$A2" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/g10.json"
step g1  uv run python scripts/g1_stress.py       --arms "$A2" --fixed-n 6 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/g1.json"
step g2  uv run python scripts/g2_stress.py       --arms "$A2" --fixed-n 12 --fixed-stop 2 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/g2.json"
step g6  uv run python scripts/g6_isolation.py    --arms "$A2" --seeds 10 --workers "$W" --out "$OUT/g6.json"
step g12 uv run python scripts/g12_stress.py      --arms "$A2" --cap 4 --seeds 10 --workers "$W" --out "$OUT/g12.json"
echo "sevenarm done $(date '+%F %T')" | tee -a "$LOG"
