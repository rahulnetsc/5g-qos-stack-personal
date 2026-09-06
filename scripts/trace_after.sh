#!/usr/bin/env bash
# Runs the mechanism traces AFTER the orchestrator finishes.
# Sequential by construction: the soak's 10 workers at ~2 GB each must not
# share the machine with anything, so this waits rather than overlapping.
set -u
cd "$(dirname "$0")/.."
OUT=sweeps/rerun-2026-09-06
PARENT=$1
while kill -0 "$PARENT" 2>/dev/null; do sleep 20; done
echo "=== [$(date +%H:%M:%S)] orchestrator $PARENT gone; starting traces" >&2
t0=$(date +%s)
uv run python scripts/trace_cells.py \
  --cells g7,attach,attach_control,g5_residual \
  --arms PF,Reservation,TwoTier --seeds 10 --identity --workers 10 \
  --out $OUT/traces.json > $OUT/traces.log 2>&1
rc=$?
el=$(( $(date +%s) - t0 ))
python3 -c "
import json,os,sys
with open(sys.argv[1],'a') as f:
    f.write(json.dumps({'campaign':'mechanism_traces','artefact':sys.argv[2],
                        'rc':int(sys.argv[3]),'elapsed_s':int(sys.argv[4])})+'\n')
    f.flush(); os.fsync(f.fileno())
" $OUT/ledger.jsonl $OUT/traces.json $rc $el
echo "=== [$(date +%H:%M:%S)] traces rc=$rc ${el}s" >&2
