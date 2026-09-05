"""Does scaling the Tier-1 objective move any DELIVERED result?

NOTHING IS LANDED. This monkeypatches `scheduler.tier1.linprog` in-process
to scale `c` by K before the solve, runs the regression corpus, and diffs
against the stored baseline. Scaling by K > 0 is argmax-invariant, so a
clean --check means the scaling changes no answer; a dirty one means the
corpus was pinning a solver path, which is the thing to find out.
"""
import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO/"scripts"))
import numpy as np
import scheduler.tier1 as T1

K = float(sys.argv[1]) if len(sys.argv) > 1 else 1e3
_orig = T1.linprog
def scaled(c, **kw):
    return _orig(np.asarray(c, float)*K, **kw)
T1.linprog = scaled
print(f"Tier-1 objective scaled by K={K:g} (argmax-invariant). Running corpus --check.")

import regression_corpus as RC
sys.argv = ["regression_corpus.py", "--check"]
rc = RC.main()
print("exit:", rc)
