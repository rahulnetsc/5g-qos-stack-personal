#!/usr/bin/env bash
# Full guarantee re-run. docs/rerun-2026-09-06-registration.md.
#
# Strictly SEQUENTIAL: no two campaigns overlap, so the "never two campaigns
# at soak horizons" rule holds by construction rather than by care.
#
# Banks one fsynced JSONL line per completed campaign, so a kill loses at most
# the campaign in flight and the ledger says which.
set -u
cd "$(dirname "$0")/.."
OUT=sweeps/rerun-2026-09-06
LEDGER=$OUT/ledger.jsonl
mkdir -p "$OUT"
START=$(date +%s)
BUDGET_S=$((120*60))
W=12
WSOAK=10

bank() {  # name artefact rc elapsed
  python3 -c "
import json,os,sys
p=sys.argv[1]
with open(p,'a') as f:
    f.write(json.dumps({'campaign':sys.argv[2],'artefact':sys.argv[3],
                        'rc':int(sys.argv[4]),'elapsed_s':int(sys.argv[5])})+'\n')
    f.flush(); os.fsync(f.fileno())
" "$LEDGER" "$1" "$2" "$3" "$4"
}

run() {  # name artefact cmd...
  local name=$1; shift
  local art=$1; shift
  local t0=$(date +%s)
  echo "=== [$(date +%H:%M:%S)] START $name" >&2
  "$@" > "$OUT/$name.log" 2>&1
  local rc=$?
  local el=$(( $(date +%s) - t0 ))
  echo "=== [$(date +%H:%M:%S)] END   $name rc=$rc ${el}s" >&2
  bank "$name" "$art" "$rc" "$el"
}

run g1358_parametric $OUT/core.json \
  uv run python scripts/phase2_core.py --seeds 10 \
    --out $OUT/core.json --workers $W
run g138_sensor_dense $OUT/sensor_dense.json \
  uv run python scripts/sensor_dense_score.py --seeds 10 \
    --out $OUT/sensor_dense.json --workers $W
run g5_g10_consolidation $OUT/g5_consol.json \
  uv run python scripts/g5_consolidation.py --seeds 10 \
    --out $OUT/g5_consol.json --workers $W
run g10 $OUT/g10.json \
  uv run python scripts/g10_rerun.py --seeds 10 \
    --out $OUT/g10.json --workers $W
run g4 $OUT/g4.json \
  uv run python scripts/g4_postsilence.py --out $OUT/g4.json --workers $W
run g6 $OUT/g6 \
  uv run python scripts/g6_seed_extension.py --root $OUT/g6 --workers $W
run g7 $OUT/g7.json \
  uv run python scripts/g7_aggressor.py --seeds 10 \
    --out $OUT/g7.json --workers $W
run g7_load1.5 $OUT/g7_load1.5.json \
  uv run python scripts/g7_aggressor.py --seeds 4 --load-mult 1.5 \
    --out $OUT/g7_load1.5.json --workers $W
run g7_load2.5 $OUT/g7_load2.5.json \
  uv run python scripts/g7_aggressor.py --seeds 4 --load-mult 2.5 \
    --out $OUT/g7_load2.5.json --workers $W
run g9 $OUT/g9.json \
  uv run python scripts/g9_campaign.py --rejoin-seed --seeds 10 \
    --out $OUT/g9.json --workers $W
run g12 $OUT/g12.json \
  uv run python scripts/g12_campaign.py --seeds 10 --out $OUT/g12.json --workers $W
run g2 $OUT/g2_ul_stop.json \
  uv run python scripts/g2_ul_stop.py --seeds 10 \
    --out $OUT/g2_ul_stop.json --workers $W

# --- G11 C1: the pre-declared fallback, decided by the clock, not by taste.
ELAPSED=$(( $(date +%s) - START ))
if [ $ELAPSED -gt $((45*60)) ]; then
  C1_SEEDS=6
  echo "=== C1 REDUCED to 6 seeds: ${ELAPSED}s of budget already spent" >&2
else
  C1_SEEDS=10
fi
echo "{\"c1_seeds\":$C1_SEEDS,\"elapsed_before_c1_s\":$ELAPSED}" >> "$LEDGER"
run g11_c1_soak $OUT/g11_c1_soak.json \
  uv run python scripts/g11_campaign.py --seeds $C1_SEEDS \
    --workers $WSOAK --out $OUT/g11_c1_soak.json
run g11_c345 $OUT/g11_c345.json \
  uv run python scripts/g11_c345.py --artefact $OUT/g11_c1_soak.json \
    --json-out $OUT/g11_c345.json

echo "=== ALL DONE $(( $(date +%s) - START ))s" >&2
