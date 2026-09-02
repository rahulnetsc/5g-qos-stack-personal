#!/usr/bin/env bash
# Copy docs/HANDOVER-new-machine.md §1.4's hand-copy manifest from a source
# host, and VERIFY it by identity rather than by count.
#
# WHY THIS EXISTS. The first real move copied none of items 1-3 and left
# item 4 as a partial that read like a success: ~/.claude/plans/ held 4
# files (the new host's own WP1/WP3/WP4-era plans), so it was non-empty and
# a cursory check passed. §1.4 now says the plans check must be a set
# difference, not a cardinality test; this script is that check, wired to
# the copy so the two cannot drift apart.
#
#   ./scripts/transfer_manifest.sh <ssh-host>            # PULL from host
#   ./scripts/transfer_manifest.sh <ssh-host> --verify   # verify only
#   ./scripts/transfer_manifest.sh <ssh-host> --push     # PUSH to host
#
# DIRECTION MATTERS, and on this pair it is not symmetric. The desktop's
# ~/.ssh/authorized_keys carries two keys commented "laptop" and its sshd
# listens; the laptop's does not carry the desktop's. So the laptop can ssh
# INTO the desktop and the desktop CANNOT ssh into the laptop -- a pull run
# on the desktop fails at authentication every time, no matter how the
# manifest is written. Run --push FROM THE LAPTOP instead:
#
#   # on the laptop, from its own checkout
#   ./scripts/transfer_manifest.sh smart@<desktop-ip> --push
#
# <ssh-host> is anything ssh(1) accepts -- an alias from ~/.ssh/config, or
# user@address. This script does no credential handling: if the host needs
# a password, ssh will prompt, and if it needs a key you do not have, it
# will fail loudly rather than half-copying.
set -uo pipefail

HOST="${1:-}"
MODE="${2:-copy}"
[ -z "$HOST" ] && { echo "usage: $0 <ssh-host> [--verify]" >&2; exit 2; }
[ "$MODE" = "--verify" ] && MODE=verify
[ "$MODE" = "--push" ] && MODE=push

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_REPO="${SRC_REPO:-projects/5g-qos-stack-personal}"   # path on the SOURCE host
PLANS="$HOME/.claude/plans"

ITEMS=(
  "sweeps/wp9/stage1/records.jsonl"
  "sweeps/wp9/stage4/records.jsonl"
  "sweeps/wp9/stage6_g6_n40_records.jsonl"
)

fail=0
say() { printf '%s\n' "$*"; }
ok()  { printf '  \033[32mPASS\033[0m  %s\n' "$*"; }
bad() { printf '  \033[31mFAIL\033[0m  %s\n' "$*"; fail=1; }

say "== source: $HOST:$SRC_REPO   destination: $REPO"
if ! ssh -o ConnectTimeout=10 "$HOST" true 2>/dev/null; then
  say "cannot reach $HOST over ssh (no key, wrong host, or password required)."
  say "Nothing was copied."
  say ""
  say "If you are on the DESKTOP trying to pull from the laptop, this will"
  say "never work: the trust is one-way (laptop -> desktop). Run the push"
  say "form from the laptop instead:"
  say "    ./scripts/transfer_manifest.sh smart@<desktop-ip> --push"
  exit 3
fi

# ---------- items 1-3: the .gitignore'd record files ----------
if [ "$MODE" = push ]; then
  say "== PUSHING items 1-3 (~2.6 G) to $HOST =="
  for rel in "${ITEMS[@]}"; do
    [ -f "$REPO/$rel" ] || { bad "source missing: $rel"; continue; }
    say "  -> $rel"
    ssh "$HOST" "mkdir -p '$SRC_REPO/$(dirname "$rel")'" || bad "mkdir failed: $rel"
    rsync -aP --info=progress2 "$REPO/$rel" "$HOST:$SRC_REPO/$rel" || bad "rsync failed: $rel"
  done
  say "== PUSHING item 4 (~/.claude/plans/) =="
  ssh "$HOST" "mkdir -p .claude/plans" || bad "mkdir failed: plans"
  rsync -a --ignore-existing "$PLANS/" "$HOST:.claude/plans/" || bad "rsync failed: plans"

  say ""
  say "== verifying the DESTINATION against this machine =="
  for rel in "${ITEMS[@]}"; do
    [ -f "$REPO/$rel" ] || continue
    want=$(stat -c%s "$REPO/$rel")
    got=$(ssh "$HOST" "stat -c%s '$SRC_REPO/$rel' 2>/dev/null" || echo "")
    if [ -z "$got" ]; then bad "$rel -- ABSENT on destination"
    elif [ "$want" = "$got" ]; then ok "$rel  ($(numfmt --to=iec "$got"))"
    else bad "$rel -- size mismatch: here $want, destination $got"; fi
  done
  # identity, not cardinality: every plan HERE must exist THERE
  missing=$(comm -23 <(ls "$PLANS" 2>/dev/null | sort) \
                     <(ssh "$HOST" "ls .claude/plans/ 2>/dev/null" | sort))
  if [ -z "$missing" ]; then
    ok "~/.claude/plans/ -- every plan on this machine is present on $HOST"
  else
    bad "~/.claude/plans/ -- MISSING on destination:"
    printf '          %s\n' $missing
  fi
  say ""
  [ "$fail" -eq 0 ] && say "MANIFEST COMPLETE (pushed)" || say "MANIFEST INCOMPLETE -- see FAIL lines above"
  exit "$fail"
fi

if [ "$MODE" = copy ]; then
  say "== copying items 1-3 (~2.6 G) =="
  for rel in "${ITEMS[@]}"; do
    mkdir -p "$REPO/$(dirname "$rel")"
    say "  -> $rel"
    # -P: resume a partial transfer rather than restarting 1.4 G
    rsync -aP --info=progress2 "$HOST:$SRC_REPO/$rel" "$REPO/$rel" || bad "rsync failed: $rel"
  done

  # ---------- item 4: plans, copied WITHOUT clobbering local history ----------
  say "== copying item 4 (~/.claude/plans/) =="
  mkdir -p "$PLANS"
  # --ignore-existing so this host's own earlier plans survive; the
  # verification below is a set difference, so a superset is fine and a
  # missing file is caught.
  rsync -a --ignore-existing "$HOST:.claude/plans/" "$PLANS/" || bad "rsync failed: plans"
fi

# ---------- verification: identity, not cardinality ----------
say ""
say "== verifying against the source =="

for rel in "${ITEMS[@]}"; do
  if [ ! -f "$REPO/$rel" ]; then bad "$rel -- ABSENT"; continue; fi
  want=$(ssh "$HOST" "cd '$SRC_REPO' && stat -c%s '$rel' 2>/dev/null" || echo "")
  got=$(stat -c%s "$REPO/$rel")
  if [ -z "$want" ]; then bad "$rel -- not present on source, cannot verify"
  elif [ "$want" = "$got" ]; then ok "$rel  ($(numfmt --to=iec "$got"))"
  else bad "$rel -- size mismatch: source $want, here $got"; fi
done

# The check §1.4 calls for: every source plan is present here. A SUPERSET is
# fine (this host has its own); a MISSING file is the failure.
missing=$(comm -23 \
  <(ssh "$HOST" "ls .claude/plans/ 2>/dev/null" | sort) \
  <(ls "$PLANS" 2>/dev/null | sort))
if [ -z "$missing" ]; then
  ok "~/.claude/plans/ -- every source plan present ($(ls "$PLANS" | wc -l) files here)"
else
  bad "~/.claude/plans/ -- MISSING from this host:"
  printf '          %s\n' $missing
fi

# ---------- item 5 is on-demand; report, do not copy ----------
say ""
if ssh "$HOST" "test -d Documents/artpark_projects/Oai_Ran_QoS_Supported_MultiDRB" 2>/dev/null; then
  say "note: manifest item 5 (full OAI checkout) EXISTS on the source and is"
  say "      not copied by this script -- it is needed on demand, not on"
  say "      arrival (§1.4). Copy it when a constant looks sourceless."
else
  say "note: manifest item 5 (full OAI checkout) not found on the source at"
  say "      the path CLAUDE.md cites. Locate it before the next port question."
fi

say ""
[ "$fail" -eq 0 ] && say "MANIFEST COMPLETE" || say "MANIFEST INCOMPLETE -- see FAIL lines above"
exit "$fail"
