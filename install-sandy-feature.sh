#!/usr/bin/env bash
# Install THIS repository as the sandy feature `amap-spec`.
#
#   ./install-sandy-feature.sh              symlink $SANDY_HOME/features/amap-spec -> this checkout
#   ./install-sandy-feature.sh --uninstall  remove it
#   ./install-sandy-feature.sh --dry-run    print the plan and stop
#
# The symlink is the whole mechanism, and it is why the mounts are LIVE. A
# manifest mount's `from` is validated segment by segment ([A-Za-z0-9._-]+, no
# leading dot, no `..`, never absolute), so it cannot reference anything outside
# the feature directory. Making the checkout BE the feature directory is what
# puts spec/, schemas/ and fixtures/ inside it without copying them.
#
# A feature directory is privileged by construction of where it lives
# ($SANDY_HOME is unreachable from any repository), so there is no approval
# prompt and no tier -- which is exactly why installing one is a deliberate act
# with its own script.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd -P)"
NAME="amap-spec"
SANDY_HOME="${SANDY_HOME:-$HOME/.sandy}"
DEST="$SANDY_HOME/features/$NAME"
DRY=0; ACTION="install"

for a in "$@"; do
    case "$a" in
        --uninstall) ACTION="uninstall" ;;
        --dry-run)   DRY=1 ;;
        -h|--help)   sed -n '2,6p' "$0"; exit 0 ;;
        *) echo "install: unknown argument '$a'" >&2; exit 1 ;;
    esac
done

say() { printf '%s\n' "$*"; }
die() { printf 'install: %s\n' "$*" >&2; exit 1; }

if [ "$ACTION" = uninstall ]; then
    say "plan: rm -rf $DEST   (removes the symlink only; this checkout is untouched)"
    [ "$DRY" = 1 ] && exit 0
    rm -rf "$DEST"
    say "removed. Selected sandboxes lose the mounts at their next launch."
    exit 0
fi

# --- preflight ------------------------------------------------------------
# A manifest sandy cannot read IN FULL takes the whole launch down, and not only
# for amap-* sandboxes: _sandy_fm_apply refuses on the first bad manifest and
# sandy exits 1. So these are hard refusals, not warnings.
command -v sandy >/dev/null 2>&1 || die "sandy is not on PATH."

JSONQ=""
command -v jq   >/dev/null 2>&1 && JSONQ=jq
[ -n "$JSONQ" ] || { command -v node >/dev/null 2>&1 && JSONQ=node; }
[ -n "$JSONQ" ] || die "this host has neither jq nor node; sandy cannot read a feature manifest at all (strict parse or refuse), so installing one would break every launch."

# Gate on CAPABILITY, never on a version number: a stripped X.Y.Z-dev compares
# equal to X.Y.Z, so a `>= 2.1.0` test is satisfied by every commit on that dev
# line including ones predating agent_args.
if [ "$JSONQ" = jq ]; then
    has_aa="$(sandy --print-schema | jq -r '
        (.manifest.top_level_keys // []) | index("agent_args") | if . == null then "no" else "yes" end')"
else
    has_aa="$(sandy --print-schema | node -e '
        let s=""; process.stdin.on("data",d=>s+=d).on("end",()=>{
          let k=[]; try { k=(JSON.parse(s).manifest||{}).top_level_keys||[] } catch(e) {}
          process.stdout.write(k.indexOf("agent_args")===-1?"no":"yes") })')"
fi
[ "$has_aa" = yes ] || die "this sandy does not publish 'agent_args' in manifest.top_level_keys (needs 2.1.0+).
      Installing feature.json here would make EVERY launch on this host fail
      with 'unknown top-level key: agent_args'. Upgrade sandy first."

# Every declared mount source must exist HERE. Sandy warns by name for a missing
# source and carries on -- but agent_args is emitted even when the mount is
# skipped, so a missing CONFORMANCE.md would still hand claude an
# --append-system-prompt-file naming a path that is not in the container.
missing=""
for m in spec schemas fixtures CONFORMANCE.md; do
    [ -e "$HERE/$m" ] || missing="$missing $m"
done
[ -z "$missing" ] || die "this directory is missing:$missing
      install-sandy-feature.sh must sit at the ROOT of the amap-spec checkout, beside
      spec/, schemas/ and fixtures/. Found: $HERE"

# --- install --------------------------------------------------------------
say "plan:"
say "  feature name : $NAME"
say "  destination  : $DEST  ->  $HERE   (symlink)"
say "  applies to   : sandboxes matching 'amap-*', except this one, every agent"
say "  live mounts  : spec/ schemas/ fixtures/ CONFORMANCE.md  ->  ~/.amap-spec/<same>  (ro)"
say "  claude args  : --append-system-prompt-file /home/sandy/.amap-spec/CONFORMANCE.md"
[ "$DRY" = 1 ] && exit 0

if [ -L "$DEST" ]; then
    rm -f "$DEST"
elif [ -e "$DEST" ]; then
    die "$DEST already exists and is a real directory, not a symlink.
      Something else is installed under that feature name. Move it aside first."
fi
mkdir -p "$SANDY_HOME/features"
ln -s "$HERE" "$DEST"

# Sandy writes its selection record INTO the feature directory -- which is now
# this working tree. Untracked files in a spec repo are noise at best and get
# committed by accident at worst, so say so by name rather than leaving it to
# be discovered in a `git status`.
if git -C "$HERE" rev-parse --git-dir >/dev/null 2>&1; then
    if ! git -C "$HERE" check-ignore -q selected.json 2>/dev/null; then
        say ""
        say "NOTE: sandy writes its selection record into the feature directory, which is"
        say "      now this checkout. Add to .gitignore:"
        say ""
        say "        /.selected/"
        say "        /selected.json"
        say "        /selected.json.tmp.*"
    fi
fi

say ""
say "installed. Selection is evaluated at each LAUNCH, so a running amap-* session"
say "does not pick the feature up until it is relaunched. Once it has:"
say ""
say "  sandy --print-state | jq '.sandboxes[] | {name, agent_args}'"
say "      populated = applied and by which feature; {} = none applied;"
say "      the field ABSENT = a sandy too old to answer."
say "  cat $DEST/selected.json"
say "      who was selected, and the reason for everyone who was not."
say ""
say "The mounts themselves are live: once a sandbox has launched with them, an"
say "edit to spec/ here is visible in that container immediately. CONFORMANCE.md"
say "is the exception -- see SANDY-FEATURE.md."
