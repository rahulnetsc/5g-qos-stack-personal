#!/usr/bin/env bash
# G10's published artefact was produced by `g5_consolidation.py --attach-seed`,
# not by `g10_rerun.py` -- different grid, different mechanism (attach on).
# The orchestrator ran the wrong one, so the correct campaign is queued here,
# behind both the soak and the traces so nothing overlaps.
set -u
cd "$(dirname "$0")/.."
OUT=sweeps/rerun-2026-09-06
for p in "$@"; do
  while kill -0 "$p" 2>/dev/null; do sleep 20; done
done
t0=$(date +%s)
uv run python scripts/g5_consolidation.py --attach-seed --seeds 10 \
  --out $OUT/g10_attach.json --workers 10 > $OUT/g10_attach.log 2>&1
rc=$?
python3 -c "
import json,os,sys
with open(sys.argv[1],'a') as f:
    f.write(json.dumps({'campaign':'g10_attach','artefact':sys.argv[2],
                        'rc':int(sys.argv[3]),'elapsed_s':int(sys.argv[4])})+'\n')
    f.flush(); os.fsync(f.fileno())
" $OUT/ledger.jsonl $OUT/g10_attach.json $rc $(( $(date +%s) - t0 ))
echo "=== [$(date +%H:%M:%S)] g10_attach rc=$rc" >&2
