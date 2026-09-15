#!/usr/bin/env bash
# The ten-guarantee campaign on the DEPLOYED cell (numerology 1, 106 PRB,
# DDSUU 6/2/6 -- docs/deployed-cell-2026-09-15.md), five arms, and EVERY
# guarantee also with configured grants on: restricted (+CG) and
# descriptor-driven (+CGt). A copy of sweeps/cell-2026-09-15/run_campaign.sh
# (never edit a running script; change a copy -- the runbook's rule), extended
# on 2026-09-16 so the CG set covers all ten guarantees, not four: the
# decision was "product + CG" for every arm (CLAUDE.md, README section 8), and
# the six runners that lacked the +CG plumbing gained it that day.
#
# Same runners, same seeds (10 per point, seed-base 0), same axes; horizons in
# seconds derived from the cell's numerology by the runners. Each runner is
# internally parallel (all cores but one) and banks its own artefact; this
# script only sequences the steps and records timing.
#
# Launch DETACHED (a multi-hour campaign must not die with a session):
#   OUT=sweeps/cell-2026-09-16-linux setsid nohup bash sweeps/cell-2026-09-16-linux/run_campaign.sh > /dev/null 2>&1 &
# OUT must hold no earlier artefacts, or the runners RESUME from the banked
# rows they find there (regime_sweep.RunLedger) instead of running fresh.
#
# Step order: per guarantee, the plain arms then the CG arms, most
# informative guarantees first (G3, G5, G7, G10 are where CG was measured to
# matter; G1/G2 are downlink and CG reaches them only through the uplink).
# Artefact paths for G3/G5/G7/G10 are the ones report_tables_cg.py already
# reads; the other six get cg/<g>_cg.json with both CG suffixes in one file.
set -u
export PATH="$HOME/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/../.." || exit 1
OUT=${OUT:-sweeps/cell-2026-09-16-linux}
mkdir -p "$OUT/aligned" "$OUT/cg"
W=${WORKERS:-$(( $(nproc 2>/dev/null || echo 24) - 1 ))}
ARMS="PF,Reservation,TwoTier,ProtoRRageD2,ConfigSched"
CG="PF+CG,Reservation+CG,TwoTier+CG,ProtoRRageD2+CG,ConfigSched+CG"
CGT="PF+CGt,Reservation+CGt,TwoTier+CGt,ProtoRRageD2+CGt,ConfigSched+CGt"
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
echo "campaign start $(date '+%F %T')  workers=$W  H5=$H5  HEAD=$(git rev-parse --short HEAD)  OUT=$OUT  ARMS=$ARMS  CG=on" | tee -a "$LOG"

# --- G3: heartbeat under a neighbour's flood
step g3      uv run python scripts/g3_stress.py --arms "$ARMS" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g3.json"
step g3_cg   uv run python scripts/g3_stress.py --arms "$CG"  --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/cg/g3_cg.json"
step g3_cgt  uv run python scripts/g3_stress.py --arms "$CGT" --parts A --fixed-n 6 --caps 4 --seeds 10 --workers "$W" --out "$OUT/cg/g3_cgt.json"
# --- G5: video freshness and completeness
step g5      uv run python scripts/g5_video.py --arms "$ARMS" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/aligned/g5.json"
step g5_cg   uv run python scripts/g5_video.py --arms "$CG"  --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/cg/g5_cg.json"
step g5_cgt  uv run python scripts/g5_video.py --arms "$CGT" --parts A,B,C --seeds 10 --workers "$W" --out "$OUT/cg/g5_cgt.json"
# --- G7: one misbehaving robot
step g7      uv run python scripts/g7_aggressor.py --arms "$ARMS" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g7.json"
step g7_cg   uv run python scripts/g7_aggressor.py --arms "$CG,$CGT" --n-ues 8 --horizon "$H5" --seeds 10 --max-sched-ues 4 --workers "$W" --out "$OUT/cg/g7.json"
# --- G10: admissible fleet
step g10     uv run python scripts/g5_consolidation.py --arms "$ARMS" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/aligned/g10.json"
step g10_cg  uv run python scripts/g5_consolidation.py --arms "$CG,$CGT" --n-ues 2,4,5,6,7,8,10,12,16 --seeds 10 --horizon "$H5" --random-access --max-sched-ues 4 --workers "$W" --out "$OUT/cg/g10.json"
# --- G1: teleop responsiveness (downlink instrument)
step g1      uv run python scripts/g1_stress.py --arms "$ARMS" --fixed-n 6 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g1.json"
step g1_cg   uv run python scripts/g1_stress.py --arms "$CG,$CGT" --fixed-n 6 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/cg/g1_cg.json"
# --- G2: emergency STOP (downlink instrument)
step g2      uv run python scripts/g2_stress.py --arms "$ARMS" --fixed-n 12 --fixed-stop 2 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/aligned/g2.json"
step g2_cg   uv run python scripts/g2_stress.py --arms "$CG,$CGT" --fixed-n 12 --fixed-stop 2 --caps 4,2 --seeds 10 --workers "$W" --out "$OUT/cg/g2_cg.json"
# --- G6: background traffic isolation
step g6      uv run python scripts/g6_isolation.py --arms "$ARMS" --seeds 10 --workers "$W" --out "$OUT/aligned/g6.json"
step g6_cg   uv run python scripts/g6_isolation.py --arms "$CG,$CGT" --seeds 10 --workers "$W" --out "$OUT/cg/g6_cg.json"
# --- G4: post-silence resume (the runner takes no --arms: every arm, plain / +CG / +CGt, in one artefact)
step g4      uv run python scripts/g4_postsilence.py --workers "$W" --out "$OUT/aligned/g4.json"
# --- G9: join / re-join / RLF recovery
if [ -n "$G9_OCC" ]; then
  step g9    uv run python scripts/g9_stress.py --arms "$ARMS" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --occupancy "$G9_OCC" --workers "$W" --out "$OUT/aligned/g9.json"
  step g9_cg uv run python scripts/g9_stress.py --arms "$CG,$CGT" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --occupancy "$G9_OCC" --workers "$W" --out "$OUT/cg/g9_cg.json"
else
  step g9    uv run python scripts/g9_stress.py --arms "$ARMS" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --workers "$W" --out "$OUT/aligned/g9.json"
  step g9_cg uv run python scripts/g9_stress.py --arms "$CG,$CGT" --cases warm,cold,rlf --seeds 10 --cap 4 --rejoin-seed off,on --workers "$W" --out "$OUT/cg/g9_cg.json"
fi
# --- G12: ordered degradation under overload
step g12     uv run python scripts/g12_stress.py --arms "$ARMS" --cap 4 --seeds 10 --workers "$W" --out "$OUT/aligned/g12.json"
step g12_cg  uv run python scripts/g12_stress.py --arms "$CG,$CGT" --cap 4 --seeds 10 --workers "$W" --out "$OUT/cg/g12_cg.json"
echo "campaign end $(date '+%F %T')" | tee -a "$LOG"
