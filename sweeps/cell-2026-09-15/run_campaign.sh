#!/usr/bin/env bash
# The ten-guarantee campaign plus the CG set on the DEPLOYED cell
# (numerology 1, 106 PRB, DDSUU 6/2/6 -- docs/deployed-cell-2026-09-15.md),
# re-measuring docs/results-aligned-2026-09-14.md and docs/results-cg-2026-09-14.md.
# Same runners, same seeds (10 per point, seed-base 0), same axes; horizons are
# the same seconds as before (10 s / 5 s), which the runners now derive from the
# cell's numerology. Each runner is internally parallel (23 workers) and banks
# its own artefact; this script only sequences them and records timing.
#
# Launch detached (CLAUDE.md: a multi-hour campaign must not die with a session):
#   powershell -Command "Start-Process -WindowStyle Hidden bash -ArgumentList '-lc','cd \"<repo>\" && bash sweeps/cell-2026-09-15/run_campaign.sh'"
set -u
export PATH="$HOME/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/../.." || exit 1
OUT=sweeps/cell-2026-09-15
mkdir -p "$OUT/aligned" "$OUT/cg"
W=${WORKERS:-23}
ARMS="PF,Reservation,TwoTier,ProtoRRageD2"
CG="PF+CG,Reservation+CG,TwoTier+CG,ProtoRRageD2+CG"
CGT="PF+CGt,Reservation+CGt,TwoTier+CGt,ProtoRRageD2+CGt"
H5=$(uv run python -c "from sim.scenarios import deployed_cell as c; print(c.slots(5000))")
G9_OCC="${G9_OCCUPANCY:-}"
LOG="$OUT/campaign.log"
step() {  # name, then the command
  local name=$1; shift
  echo "=== $name  start $(date '+%F %T')" | tee -a "$LOG"
  local t0=$SECONDS
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  echo "=== $name  end   $(date '+%F %T')  rc=$rc  $((SECONDS - t0))s" | tee -a "$LOG"
}
echo "campaign start $(date '+%F %T')  workers=$W  H5=$H5  HEAD=$(git rev-parse --short HEAD)" | tee -a "$LOG"

step g3   uv run python scripts/g3_stress.py --arms "$ARMS" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g3.json"
step g5   uv run python scripts/g5_video.py --arms "$ARMS" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/aligned/g5.json"
step g1   uv run python scripts/g1_stress.py --arms "$ARMS" --fixed-n 6 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g1.json"
step g2   uv run python scripts/g2_stress.py --arms "$ARMS" --fixed-n 12 --fixed-stop 2 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g2.json"
step g4   uv run python scripts/g4_postsilence.py --workers "$W" --out "$OUT/aligned/g4.json"
step g6   uv run python scripts/g6_isolation.py --arms "$ARMS" --seeds 10 --workers "$W" --out "$OUT/aligned/g6.json"
step g7   uv run python scripts/g7_aggressor.py --arms "$ARMS" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g7.json"
step g10  uv run python scripts/g5_consolidation.py --arms "$ARMS" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g10.json"
if [ -n "$G9_OCC" ]; then
  step g9   uv run python scripts/g9_stress.py --arms "$ARMS" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --occupancy "$G9_OCC" --workers "$W" --out "$OUT/aligned/g9.json"
else
  step g9   uv run python scripts/g9_stress.py --arms "$ARMS" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --workers "$W" --out "$OUT/aligned/g9.json"
fi
step g12  uv run python scripts/g12_stress.py --arms "$ARMS" --cap 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g12.json"

# --- configured grants: restricted (+CG) and descriptor-driven (+CGt)
step g3_cg   uv run python scripts/g3_stress.py --arms "$CG"  --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/cg/g3_cg.json"
step g3_cgt  uv run python scripts/g3_stress.py --arms "$CGT" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/cg/g3_cgt.json"
step g5_cg   uv run python scripts/g5_video.py --arms "$CG"  --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/cg/g5_cg.json"
step g5_cgt  uv run python scripts/g5_video.py --arms "$CGT" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/cg/g5_cgt.json"
step g7_cg   uv run python scripts/g7_aggressor.py --arms "$CG,$CGT" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/cg/g7.json"
step g10_cg  uv run python scripts/g5_consolidation.py --arms "$CG,$CGT" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/cg/g10.json"
echo "campaign end $(date '+%F %T')" | tee -a "$LOG"
