#!/usr/bin/env bash
# install-macos-brew.sh — install the draft toolchain on macOS with Homebrew.
#
#   ./draft/tools/install-macos-brew.sh            install and verify
#   ./draft/tools/install-macos-brew.sh --pdf      also weasyprint, for `make pdf`
#   ./draft/tools/install-macos-brew.sh --dry-run  print the plan and stop
#
# OPTIONAL AND NON-AUTHORITATIVE. This repository states its toolchain
# requirement and does not install it — preflight.sh checks the ARTIFACT, never
# the mechanism, so that a host may provide these however it likes (a container
# layer, nix, a system package, this script). Nothing in draft/Makefile depends
# on this file, and it must stay that way: the moment a build target needs it,
# the requirement has silently become "have Homebrew", which is a much larger
# claim than "have kramdown-rfc 1.7.43".
#
# What it does NOT do: edit your shell profile. It tells you the two lines to
# add and why, because a script that rewrites a dotfile is harder to undo than
# one that prints a line you can read first.
#
# Requirement, per draft/tools/preflight.sh:
#   Ruby >= 3.1 · kramdown-rfc == 1.7.43 · xml2rfc == 3.34.1 · Python >= 3.11
#   weasyprint == 63.1 only for the opt-in `make pdf` / `make formats` targets.
set -euo pipefail

KRAMDOWN_VERSION=1.7.43
XML2RFC_VERSION=3.34.1
WEASYPRINT_VERSION=63.1

WANT_PDF=0; DRY=0
for a in "$@"; do
  case "$a" in
    --pdf)     WANT_PDF=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "install: unknown argument '$a'" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
ok()   { printf '   ok    %s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then printf '   would: %s\n' "$*"; else printf '   ...   %s\n' "$*"; eval "$@"; fi; }
die()  { printf '\ninstall: %s\n' "$*" >&2; exit 1; }

# --- preconditions --------------------------------------------------------
step "preconditions"
[ "$(uname -s)" = Darwin ] || die "this script is macOS-only. On Linux use your package manager;
      the requirement is the same and preflight.sh states it."
command -v brew >/dev/null 2>&1 || die "Homebrew is not on PATH. Install it from https://brew.sh,
      or provide the toolchain any other way — this repo does not care how."
ok "macOS, Homebrew at $(command -v brew)"

# --- brew formulae --------------------------------------------------------
# macOS ships Ruby 2.6 and (via the Xcode CLT) Python 3.9. Both are too old:
# kramdown-rfc needs >= 3.1, and check_prose/gen_appendices need tomllib, which
# arrived in 3.11. So both come from brew regardless of what `ruby -v` says now.
step "brew formulae"
for f in ruby python@3.12 pipx; do
  if brew list --formula "$f" >/dev/null 2>&1; then ok "$f already installed"
  else run "brew install $f"; fi
done
if [ "$WANT_PDF" = 1 ]; then
  # weasyprint links against these at runtime; without them it imports and then
  # fails at render time, which is a worse error than a missing binary.
  for f in pango cairo gdk-pixbuf libffi; do
    if brew list --formula "$f" >/dev/null 2>&1; then ok "$f already installed"
    else run "brew install $f"; fi
  done
fi

# --- PATH -----------------------------------------------------------------
# Homebrew's ruby is KEG-ONLY: it is deliberately not symlinked into
# /opt/homebrew/bin, so `ruby` still resolves to the 2.6 in /usr/bin until the
# keg's bin directory is ahead of it. The gem bin directory is separate again,
# and it is where `kramdown-rfc` itself lands.
step "PATH"
RUBY_PREFIX="$(brew --prefix ruby 2>/dev/null || true)"
[ -n "$RUBY_PREFIX" ] || die "brew could not report a ruby prefix; is the formula installed?"
export PATH="$RUBY_PREFIX/bin:$PATH"
GEM_BIN="$(gem environment gemdir 2>/dev/null)/bin"
export PATH="$GEM_BIN:$PATH"
ok "using ruby $(ruby -v | cut -d' ' -f2) from $RUBY_PREFIX"

PROFILE_LINES="export PATH=\"$RUBY_PREFIX/bin:\$PATH\"
export PATH=\"$GEM_BIN:\$PATH\""

# --- gems and pipx --------------------------------------------------------
# EXACT versions, not minimums. kramdown-rfc's output is version-sensitive and
# dist/ is committed, so a different renderer produces a diff that looks like a
# content change and is not. preflight.sh enforces the same two pins.
step "kramdown-rfc $KRAMDOWN_VERSION"
if gem list -i kramdown-rfc -v "$KRAMDOWN_VERSION" >/dev/null 2>&1; then
  ok "already installed"
else
  run "gem install kramdown-rfc -v $KRAMDOWN_VERSION"
fi

# pipx rather than `pip install`: brew's python is externally managed (PEP 668),
# so a plain pip either refuses outright or succeeds into a user site-packages
# that is not on PATH — and the second failure is the bad one, because it looks
# like it worked.
step "xml2rfc $XML2RFC_VERSION"
if command -v xml2rfc >/dev/null 2>&1 && xml2rfc --version 2>&1 | grep -q "$XML2RFC_VERSION"; then
  ok "already installed"
else
  run "pipx install 'xml2rfc==$XML2RFC_VERSION'"
fi

if [ "$WANT_PDF" = 1 ]; then
  step "weasyprint $WEASYPRINT_VERSION (for the opt-in pdf target)"
  if command -v weasyprint >/dev/null 2>&1 && weasyprint --version 2>&1 | grep -q "$WEASYPRINT_VERSION"; then
    ok "already installed"
  else
    run "pipx install 'weasyprint==$WEASYPRINT_VERSION'"
  fi
fi

run "pipx ensurepath >/dev/null 2>&1 || true"

# --- verify with the repo's own check, not this script's opinion ----------
step "verify"
if [ "$DRY" = 1 ]; then
  say "   would: bash draft/tools/preflight.sh"
else
  REPO="$(cd "$(dirname "$0")/../.." && pwd -P)"
  if bash "$REPO/draft/tools/preflight.sh"; then
    ok "preflight passes"
  else
    say ""
    say "preflight did not pass. If it reports something 'not found on PATH' that"
    say "this script just installed, it is almost certainly the PATH: the exports"
    say "below are set inside this script and do not survive it."
  fi
fi

cat <<EOF

ADD THESE TO YOUR SHELL PROFILE (~/.zshrc), then open a new shell:

$PROFILE_LINES

Homebrew's ruby is keg-only, so without the first line \`ruby\` stays the 2.6
that ships with macOS; without the second, \`kramdown-rfc\` is installed but not
on PATH. pipx puts xml2rfc on PATH itself, via \`pipx ensurepath\`.

Then, from the repo root:

    bash draft/tools/preflight.sh     # the authority on whether this worked
    make -C draft                     # build .xml and .txt, run the three gates
    make -C draft reproducible        # two builds, byte-compared
$([ "$WANT_PDF" = 1 ] && printf '    make -C draft formats             # adds .html and .pdf\n')
A build does not need your Ruby to match anyone else's. draft/Makefile strips
the interpreter patch version from kramdown-rfc's generator comment, which is
what lets two machines with the same pinned tools produce byte-identical output.
The two PINS are what must match; the Ruby under them need not.
EOF
