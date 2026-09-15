#!/usr/bin/env bash
# One ConfigSched2 increment measured on the 2026-09-16 campaign's own steps,
# seeds and flags, for ONE arm, into its own directory. The campaign's
# ConfigSched artefacts (sweeps/cell-2026-09-16-linux/) are the "before";
# sweeps/cs2-increments/compare.py prints the two side by side.
#
#   INC=inc1 ARM=ConfigSched2 setsid nohup bash sweeps/cs2-increments/run_increment.sh > /dev/null 2>&1 &
#
# OUT (sweeps/cs2-increments/$INC) must hold no earlier artefacts for this
# increment, or the runners RESUME from the ledgers they find there.
# G4 is not run per increment: its runner takes no --arms and would re-run
# every arm; it is measured once per accepted increment by hand if needed.
set -u
export PATH="$HOME/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/../.." || exit 1
INC=${INC:?set INC=incN}
ARM=${ARM:-ConfigSched2}
OUT=sweeps/cs2-increments/$INC
mkdir -p "$OUT/aligned"
W=${WORKERS:-$(( $(nproc 2>/dev/null || echo 24) - 1 ))}
H5=$(uv run python -c "from sim.scenarios import deployed_cell as c; print(c.slots(5000))")
LOG="$OUT/campaign.log"
step() {
  local name=$1; shift
  echo "=== $name  start $(date '+%F %T')" | tee -a "$LOG"
  local t0=$SECONDS
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  echo "=== $name  end   $(date '+%F %T')  rc=$rc  $((SECONDS - t0))s" | tee -a "$LOG"
}
echo "increment $INC start $(date '+%F %T')  arm=$ARM  workers=$W  HEAD=$(git rev-parse --short HEAD)" | tee -a "$LOG"
step g3  uv run python scripts/g3_stress.py --arms "$ARM" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g3.json"
step g7  uv run python scripts/g7_aggressor.py --arms "$ARM" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g7.json"
step g10 uv run python scripts/g5_consolidation.py --arms "$ARM" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g10.json"
step g2  uv run python scripts/g2_stress.py --arms "$ARM" --fixed-n 12 --fixed-stop 2 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g2.json"
step g1  uv run python scripts/g1_stress.py --arms "$ARM" --fixed-n 6 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g1.json"
step g5  uv run python scripts/g5_video.py --arms "$ARM" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/aligned/g5.json"
step g6  uv run python scripts/g6_isolation.py --arms "$ARM" --seeds 10 --workers "$W" --out "$OUT/aligned/g6.json"
step g9  uv run python scripts/g9_stress.py --arms "$ARM" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --workers "$W" --out "$OUT/aligned/g9.json"
step g12 uv run python scripts/g12_stress.py --arms "$ARM" --cap 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g12.json"
echo "increment $INC end $(date '+%F %T')" | tee -a "$LOG"
