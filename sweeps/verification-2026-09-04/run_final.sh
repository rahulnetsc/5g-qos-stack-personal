set -e
cd /home/smart/projects/5g-qos-stack-personal
V=sweeps/verification-2026-09-04
# G6's control compares against stage 1's STORED rows, which were measured on
# OLD code -- so a FAILING control here is the expected result and is itself a
# measurement of how much the code moved. Run with the real stage-1 root so it
# can fire at all.
# Symlink, not a copy -- stage1_rows.csv is already committed and a
# duplicate in the verification tree would be a second copy of a
# tracked artefact.
mkdir -p $V/stage1 && ln -sf ../../wp9/stage1/stage1_rows.csv $V/stage1/
echo "=== G6 n=40, control able to fire ==="
uv run python scripts/g6_seed_extension.py --workers 16 --root $V 2>&1 | tail -30 || true
echo
echo "=== G12 -- full campaign, all cells ==="
timeout 7200 uv run python scripts/g12_campaign.py --seeds 10 --perm-seeds 5 \
    --workers 16 --out $V/g12.json 2>&1 | tail -25 || echo "(g12 did not complete)"
