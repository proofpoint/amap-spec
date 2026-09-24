# draft/Makefile: build and check the Internet-Draft.
#
# draft/draft-amap.xml is the CANONICAL source: xml2rfc v3 XML, hand-edited by
# the standards editor. It is not generated from anything. The only part of it
# a tool writes is the body of each JSON <sourcecode> block, which
# draft/tools/sync_sources.py keeps byte-identical to schemas/, fixtures/ and
# draft/examples/ (`make sync`). Every other byte is the editor's.
#
# dist/ holds the committed renderings: a copy of the canonical XML and its
# plain-text rendering. `all` builds exactly those two, then runs every gate.
#
# Plain `xml2rfc` from PATH, and nothing else. kramdown-rfc and Ruby left the
# toolchain when the XML became canonical. draft/tools/preflight.sh checks the
# artifact, never the mechanism.
REPO := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

NAME := draft-amap-00
SRC  := $(REPO)/draft/draft-amap.xml
OUT  := $(REPO)/dist/$(NAME)

X2R := xml2rfc --v3 --no-network

.PHONY: all preflight sync check normdiff reproducible diff clean html pdf formats

all: preflight $(OUT).xml $(OUT).txt check

preflight:
	bash $(REPO)/draft/tools/preflight.sh

# Rewrite the JSON blocks in the canonical source from the files on disk. Run
# it after changing a schema, a fixture listed in fixtures.toml, or an example,
# and commit the source change and the rewritten XML together.
sync:
	cd $(REPO) && python3 draft/tools/sync_sources.py --write

$(dir $(OUT)):
	mkdir -p $@

# The committed .xml in dist/ is the canonical source, byte for byte. It is kept
# there so dist/ stays the one place a reader finds the submission artifacts.
#
# It is also the easiest file in the repository to edit by mistake: it looks
# exactly like the source. A direct edit there makes the copy newer than the
# source, so make treats it as up to date and leaves it alone; `check` then
# fails on the mismatch and says where the edit belongs. (A guard inside this
# recipe could never fire for that case: the recipe only runs when the source
# is the newer file.)
$(OUT).xml: $(SRC) | $(dir $(OUT))
	cp $(SRC) $(OUT).xml

$(OUT).txt: $(OUT).xml
	cd $(REPO) && $(X2R) --text $(OUT).xml -o $(OUT).txt

# Neither .html nor .pdf is part of `all`: `all` builds exactly the committed
# artifacts. PDF needs weasyprint and its fonts, which a verification run has
# no business requiring. IETF takes XML and renders the rest itself.
formats: $(OUT).txt $(OUT).html $(OUT).pdf

pdf: $(OUT).pdf

$(OUT).pdf: $(OUT).xml
	cd $(REPO) && $(X2R) --pdf $(OUT).xml -o $(OUT).pdf

html: $(OUT).html

$(OUT).html: $(OUT).xml
	cd $(REPO) && $(X2R) --html $(OUT).xml -o $(OUT).html

# The gates. Each one guards a different way the draft can drift:
#   sync_sources.py  a JSON block differs from its file, a block has no file, or
#                    a schema/fixture has no block (a missing block is the
#                    omission a comparison can't see)
#   check_render.py  the same equality re-derived from the XML, plus roster
#                    counts, the pinned docName, and no host paths or
#                    personal identifiers
#   check_coverage.py every normative sentence is classified: covered by a
#                    fixture, operational-only, or unclassified (baseline)
#   validate.py      the conformance suite itself
check: $(OUT).xml
	@cmp -s $(SRC) $(OUT).xml || { echo "check: dist/$(NAME).xml differs from draft/draft-amap.xml. dist/ is generated: edit draft/draft-amap.xml and run make." >&2; exit 1; }
	cd $(REPO) && python3 draft/tools/sync_sources.py
	cd $(REPO) && python3 draft/tools/check_render.py $(SRC)
	cd $(REPO) && python3 draft/tools/check_coverage.py
	cd $(REPO) && python3 fixtures/validate.py | tail -1

# The normative diff: every RFC 2119 sentence added, removed or changed
# between BASE (a git ref, default origin/main) and the working tree. CI posts
# it on every pull request. A reviewer reads this rather than the XML diff.
normdiff:
	cd $(REPO) && python3 draft/tools/normdiff.py $(or $(BASE),origin/main)

reproducible: preflight
	@set -e; d1=$$(mktemp -d); d2=$$(mktemp -d); \
	cd $(REPO) && \
	$(X2R) --text $(SRC) -o $$d1/out.txt && \
	$(X2R) --text $(SRC) -o $$d2/out.txt && \
	cmp $$d1/out.txt $$d2/out.txt && \
	echo "reproducible: identical" && rm -rf $$d1 $$d2

# Local diff against another xml2rfc v3 XML (for example a reviewer's copy):
# normalise both with --prep, strip prepTime and <?line?>, diff -u; also render
# both to text and diff those. Nothing is uploaded: never kdrfc, and never
# Author Tools from here.
diff: preflight
	@test -n "$(OTHER)" || { echo "usage: make -C draft diff OTHER=/path/to/theirs.xml" >&2; exit 2; }
	@set -e; \
	a=$$(mktemp); b=$$(mktemp); \
	$(X2R) --prep $(SRC) -o $$a.prepped.xml >/dev/null 2>&1 || cp $(SRC) $$a.prepped.xml; \
	$(X2R) --prep $(OTHER) -o $$b.prepped.xml >/dev/null 2>&1 || cp $(OTHER) $$b.prepped.xml; \
	sed -E 's/ prepTime="[^"]*"//; /<\?line [0-9]+\?>/d' $$a.prepped.xml > $$a.norm.xml; \
	sed -E 's/ prepTime="[^"]*"//; /<\?line [0-9]+\?>/d' $$b.prepped.xml > $$b.norm.xml; \
	diff -u $$a.norm.xml $$b.norm.xml || true; \
	$(X2R) --text $$a.prepped.xml -o $$a.txt >/dev/null 2>&1; \
	$(X2R) --text $$b.prepped.xml -o $$b.txt >/dev/null 2>&1; \
	diff -u $$a.txt $$b.txt || true; \
	rm -f $$a $$b $$a.prepped.xml $$b.prepped.xml $$a.norm.xml $$b.norm.xml $$a.txt $$b.txt

clean:
	rm -f $(OUT).html $(OUT).pdf
