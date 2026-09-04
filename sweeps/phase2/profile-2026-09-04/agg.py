"""Aggregate py-spy raw (folded) stacks: self time, inclusive time, and
attribution of every sample to the top-level pipeline phase it belongs to."""
import sys, collections, re

path = sys.argv[1]
total = 0
self_t = collections.Counter()
incl_t = collections.Counter()
phase_t = collections.Counter()
phase_self = collections.defaultdict(collections.Counter)

# The phase is decided by which harness function appears in the stack.
# Attribute by the harness call-site line in main(), which is unambiguous.
PHASE_FRAMES = [
    ("scenario_build", "main (profile_record.py:70)"),
    ("driver_run", "main (profile_record.py:75)"),
    ("from_summary", "main (profile_record.py:79)"),
    ("online_variations", "main (profile_record.py:88)"),
    ("persist", "main (profile_record.py:92)"),
    ("persist_write", "main (profile_record.py:96)"),
    ("m13_projection", "main (profile_record.py:100)"),
    ("panel_score", "main (profile_record.py:104)"),
    ("panel_score", "main (profile_record.py:105)"),
]

lines = open(path).read().splitlines()
for line in lines:
    if not line.strip():
        continue
    stack, _, cnt = line.rpartition(" ")
    n = int(cnt)
    total += n
    frames = stack.split(";")
    self_t[frames[-1]] += n
    for f in set(frames):
        incl_t[f] += n
    ph = "other"
    for name, needle in PHASE_FRAMES:
        if any(needle in f for f in frames):
            ph = name
            break
    phase_t[ph] += n
    phase_self[ph][frames[-1]] += n

print(f"total samples: {total}")
print("\n=== PHASE (inclusive, by stack membership) ===")
for ph, n in phase_t.most_common():
    print(f"  {100*n/total:6.2f}%  {n:6d}  {ph}")

print("\n=== TOP 40 BY SELF TIME ===")
for f, n in self_t.most_common(40):
    print(f"  {100*n/total:6.2f}%  {n:6d}  {f}")

print("\n=== TOP 45 BY INCLUSIVE TIME ===")
for f, n in incl_t.most_common(45):
    print(f"  {100*n/total:6.2f}%  {n:6d}  {f}")

for ph in ("driver_run", "online_variations", "panel_score", "persist", "other"):
    if not phase_self[ph]:
        continue
    print(f"\n=== SELF TIME WITHIN PHASE {ph} (top 20, % of whole run) ===")
    for f, n in phase_self[ph].most_common(20):
        print(f"  {100*n/total:6.2f}%  {n:6d}  {f}")
