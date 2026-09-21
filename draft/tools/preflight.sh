#!/usr/bin/env bash
# draft/preflight.sh — verify the draft toolchain ARTIFACT, never the
# mechanism. This repository states the requirement (Ruby >= 3.1,
# kramdown-rfc == 1.7.43, xml2rfc == 3.34.1, Python >= 3.11) and does not
# install it; how a host meets it is that host's business (draft/README.md,
# "Toolchain requirement"). Every build target in draft/Makefile depends on
# this, so "command not found" can never be the first thing a user sees.
#
# Collects every failure before exiting, so the operator sees the whole
# picture in one run rather than fixing one thing at a time.
set -u

need() { command -v "$1" >/dev/null 2>&1; }

fail=0

need ruby         || { echo "preflight: ruby not found on PATH"; fail=1; }
need kramdown-rfc || { echo "preflight: kramdown-rfc not found on PATH"; fail=1; }
need xml2rfc      || { echo "preflight: xml2rfc not found on PATH"; fail=1; }
need python3      || { echo "preflight: python3 not found on PATH"; fail=1; }

if [ "$fail" = 0 ]; then
  v=$(kramdown-rfc --version 2>&1 | tr -d '\n')
  case "$v" in
    *1.7.43*) ;;
    *) echo "preflight: kramdown-rfc is '$v', need 1.7.43"; fail=1 ;;
  esac

  v=$(xml2rfc --version 2>&1 | tr -d '\n')
  case "$v" in
    *3.34.1*) ;;
    *) echo "preflight: xml2rfc is '$v', need 3.34.1"; fail=1 ;;
  esac

  python3 -c 'import tomllib' 2>/dev/null || {
    echo "preflight: python3 >= 3.11 (tomllib) required"
    fail=1
  }

  need kdrfc && echo "preflight: note: kdrfc is installed; the Makefile never calls it (it can upload to author-tools.ietf.org)"
fi

if [ "$fail" != 0 ]; then
  cat <<'EOF'

The draft toolchain is missing or wrong (see lines above). It is NOT
installed by this repository, which states the requirement and leaves the
mechanism to the machine. Required:

  Ruby >= 3.1
  kramdown-rfc 1.7.43      gem install kramdown-rfc -v 1.7.43
  xml2rfc 3.34.1           pip install xml2rfc==3.34.1
  Python >= 3.11
  weasyprint 63.1          pip install weasyprint==63.1   (only for `make pdf`)

See draft/README.md, "Toolchain requirement".

If this machine provides the toolchain through a container image, a VM, or
any other layer, the usual cause is that the layer did not take effect --
check that it was actually rebuilt, then re-run `make -C draft preflight`.

Nothing was built.
EOF
  exit 2
fi

echo "preflight: ok  $(ruby -v | cut -d' ' -f1-2)  kramdown-rfc 1.7.43  xml2rfc 3.34.1"
