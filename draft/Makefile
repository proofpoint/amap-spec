# draft/Makefile — build the Internet-Draft rendering of amap-spec.
#
# Plain `kramdown-rfc` and `xml2rfc` from PATH — no toolchain path baked in
# here, no reference to how a host provides them (draft/README.md, "Toolchain
# requirement"; draft/tools/preflight.sh checks the artifact, never the mechanism).
# Every build target depends on `preflight` so a bare "command not found" (or
# a wrong version) can never be a user's first, unexplained error.
#
# Every recipe cds to $(REPO) because kramdown-rfc's {::include} directives
# resolve relative to the current working directory, not the source file —
# so this works the same whether invoked as `make -C draft` or `make` from
# the repo root.
REPO := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

NAME := draft-amap-00
SRC  := $(REPO)/draft/draft-amap.mkd
OUT  := $(REPO)/dist/$(NAME)
FIXTURES_TOML := $(REPO)/draft/fixtures.toml

export KRAMDOWN_NO_SOURCE   := 1
export KRAMDOWN_OFFLINE     := 1
export KRAMDOWN_REFCACHEDIR := $(REPO)/draft/bib

X2R := xml2rfc --v3 --no-network

.PHONY: all preflight gen refs check prose reproducible diff clean html pdf formats

all: preflight $(OUT).xml $(OUT).txt check

preflight:
	bash $(REPO)/draft/tools/preflight.sh

gen: preflight
	cd $(REPO) && python3 draft/tools/gen_appendices.py

# The output directory is owned by this build, so the build creates it. It
# used to exist only because tracked files happened to live in it — a rename
# that removed the last one took the directory with it and the build then
# failed on a missing path.
$(dir $(OUT)):
	mkdir -p $@

# kramdown-rfc stamps the INTERPRETER patch version into its generator comment
# ("... version 1.7.43 (Ruby 3.3.8)"), so identical pinned tools on two machines
# still produce different bytes. That is metadata about the build host, not
# content, and it made the committed artifacts un-diffable across machines —
# caught by CI on its first run, against a Ruby that differed only in patch
# level. The version of kramdown-rfc itself is kept: that one IS pinned and
# does affect the output. Pinning Ruby exactly everywhere would be the other
# fix, and a worse one — it ages badly and breaks on the next distro update,
# which is the same reason the Debian packages are not pinned.
$(OUT).xml: preflight gen $(SRC) $(FIXTURES_TOML) | $(dir $(OUT))
	cd $(REPO) && kramdown-rfc --v3 $(SRC) \
	  | sed -E 's/(version [0-9.]+) \(Ruby [0-9.]+\)/\1/' > $(OUT).xml.tmp \
	  && mv $(OUT).xml.tmp $(OUT).xml

$(OUT).txt: $(OUT).xml
	cd $(REPO) && $(X2R) --text $(OUT).xml -o $(OUT).txt

# Neither .html nor .pdf is part of the default `all` target. The rule is
# that `all` builds exactly the two artifacts that are committed (.xml and
# .txt); everything derivable-but-gitignored is on demand. Keeping .pdf out
# is what stops weasyprint, pango and the Noto fonts from becoming mandatory
# for every check run — a CI job that verifies JSON blocks and prose coverage
# has no business needing a PDF stack. `make -C draft formats` builds the
# full set in one command when you actually want it.
# PDF is opt-in, like html: it needs weasyprint and the Noto fonts, which are
# the bulk of the container image layer. Never part of the default target, and
# never a submission format — IETF takes XML and renders the rest itself.
formats: $(OUT).txt $(OUT).html $(OUT).pdf

pdf: $(OUT).pdf

$(OUT).pdf: $(OUT).xml
	cd $(REPO) && $(X2R) --pdf $(OUT).xml -o $(OUT).pdf

html: $(OUT).html

$(OUT).html: $(OUT).xml
	cd $(REPO) && $(X2R) --html $(OUT).xml -o $(OUT).html

check: $(OUT).xml
	cd $(REPO) && python3 draft/tools/check_render.py $(OUT).xml
	cd $(REPO) && python3 draft/tools/check_prose.py
	cd $(REPO) && python3 fixtures/validate.py | tail -1

# Prose coverage on its own, without a rebuild. Needs no toolchain — it reads
# spec/ and the .mkd source, never the rendered XML — so it is the one check
# that works in a container the image layer has not reached yet.
prose:
	cd $(REPO) && python3 draft/tools/check_prose.py

# Populates draft/bib/ from bib.ietf.org. The only target that touches the
# network at kramdown-rfc render time (an explicit, one-time bibxml cache
# fetch); normal builds set KRAMDOWN_OFFLINE=1 and fail loudly on a miss.
refs: preflight
	cd $(REPO) && KRAMDOWN_OFFLINE= kramdown-rfc --v3 $(SRC) > /dev/null
	@echo "draft/bib/ populated; git add draft/bib to commit the cache."

reproducible: preflight
	@set -e; d1=$$(mktemp -d); d2=$$(mktemp -d); \
	cd $(REPO) && python3 draft/tools/gen_appendices.py && \
	kramdown-rfc --v3 $(SRC) > $$d1/out.xml && \
	python3 draft/tools/gen_appendices.py && \
	kramdown-rfc --v3 $(SRC) > $$d2/out.xml && \
	$(X2R) --text $$d1/out.xml -o $$d1/out.txt && \
	$(X2R) --text $$d2/out.xml -o $$d2/out.txt && \
	cmp $$d1/out.xml $$d2/out.xml && cmp $$d1/out.txt $$d2/out.txt && \
	echo "reproducible: identical" && rm -rf $$d1 $$d2

# Local diff against a hand-written xml2rfc v3 XML: normalise both with
# --prep, strip prepTime/<?line?>/generated-by, diff -u; also render both to
# .txt and diff those. This never uploads anything (Author Tools' web diff is
# a separate, human decision under the publication hold).
diff: preflight
	@test -n "$(OTHER)" || { echo "usage: make -C draft diff OTHER=/path/to/theirs.xml" >&2; exit 2; }
	@set -e; \
	a=$$(mktemp); b=$$(mktemp); \
	$(X2R) --prep $(OUT).xml -o $$a.prepped.xml >/dev/null 2>&1 || cp $(OUT).xml $$a.prepped.xml; \
	$(X2R) --prep $(OTHER) -o $$b.prepped.xml >/dev/null 2>&1 || cp $(OTHER) $$b.prepped.xml; \
	sed -E 's/ prepTime="[^"]*"//; /<\?line [0-9]+\?>/d; /generated by kramdown-rfc/d' $$a.prepped.xml > $$a.norm.xml; \
	sed -E 's/ prepTime="[^"]*"//; /<\?line [0-9]+\?>/d; /generated by kramdown-rfc/d' $$b.prepped.xml > $$b.norm.xml; \
	diff -u $$a.norm.xml $$b.norm.xml || true; \
	$(X2R) --text $$a.prepped.xml -o $$a.txt >/dev/null 2>&1; \
	$(X2R) --text $$b.prepped.xml -o $$b.txt >/dev/null 2>&1; \
	diff -u $$a.txt $$b.txt || true; \
	rm -f $$a $$b $$a.prepped.xml $$b.prepped.xml $$a.norm.xml $$b.norm.xml $$a.txt $$b.txt

clean:
	rm -rf $(REPO)/draft/build $(OUT).xml.tmp
