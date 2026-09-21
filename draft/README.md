# draft/ — the Internet-Draft rendering of amap-spec

## 0. Layout

```
draft-amap.mkd          the Internet-Draft source — this is the file you edit
fixtures.toml           which fixtures appear inline, and why (data, not code)
prose-exceptions.toml   which spec obligations the draft knowingly omits, and why
examples/               the four illustrative JSON shapes (hand-written)
bib/                    committed bibxml cache — FETCHED, never hand-edited;
                        `make refs` repopulates it from bib.ietf.org
Makefile                the entry point: `make -C draft`
tools/                  the build machinery; nothing here is authored content
build/                  generated fragments (gitignored)
```

Everything above `Makefile` is hand-authored and belongs in review; everything
below it is machinery or output. `bib/` is the odd one — committed, but a cache
rather than content, so a build needs no network.

## 1. What this is

This directory builds `dist/draft-amap-00.{xml,txt}` — and, on demand,
`.html` and `.pdf` — an xml2rfc v3 rendering of the AMAP contract, produced
with [kramdown-rfc](https://github.com/cabo/kramdown-rfc) from a
hand-maintained `.mkd` source plus schemas and fixtures pulled in mechanically
from `schemas/` and `fixtures/`. It does not replace `spec/contract.md`, which
stays the normative source; this is a *rendering* of it in Internet-Draft
structure, built and checked so that it cannot silently drift from what
`spec/` and `fixtures/` actually say.

**Hand-maintained:** the YAML front matter and the prose of `draft-amap.mkd`.
Every normative sentence in it traces to `spec/`, and `tools/check_prose.py`
enforces that: it requires a draft sentence covering every RFC 2119 sentence
in `spec/`, or an entry in `prose-exceptions.toml` saying why not. An
obligation cannot quietly vanish from the draft.

**Generated, never typed:** every JSON document in the rendering — the six
schemas (Appendices A–F, pulled in directly by
`{::include-fold69hardleft4dry schemas/<name>}`), and the inline fixtures and
their roster (Appendix G, Appendix H, produced by `tools/gen_appendices.py`
from `fixtures.toml` plus `fixtures/`). `fixtures.toml` decides *which*
fixtures are shown; the files on disk decide *what* they say.
`gen_appendices.py` imports `fixtures/validate.py` — the same module the
conformance gate runs — and asserts each selected fixture's expected outcome
still holds, so a fixture whose meaning changes breaks this build rather than
silently going stale. `tools/check_render.py` is the other half of that proof,
run after the render: it walks the built XML, unfolds every JSON
`<sourcecode>` block per RFC 8792, and confirms it is byte-identical (modulo
the fold and a trailing newline) to the file on disk the include directive
named. The hand-authored illustrative shapes under `examples/` are anchored
`ex-*` and exempted from the disk comparison, but must still parse as JSON and
validate against their schemas.

## 2. Toolchain requirement

This repository states the *requirement*, not the mechanism — the same posture
the conformance gate already takes. How a given machine provides these is its
own business; `tools/preflight.sh` checks the artifact, never how it got there.

| requirement | pinned | needed for |
|---|---|---|
| Ruby | any Ruby ≥ 3.1 | kramdown-rfc |
| kramdown-rfc | **1.7.43** exactly | `.mkd` → `.xml` |
| xml2rfc | **3.34.1** exactly | `.xml` → `.txt`, `.html`, `.pdf` |
| Python | ≥ 3.11 (`tomllib`) | the three checkers |
| weasyprint | **63.1** | `make pdf` only |

Every build target depends on `preflight`, so a missing or wrong-versioned
tool is never a bare "command not found." Run it directly with
`make -C draft preflight`.

**Ruby's patch version does not need to match across machines**, but only
because the build normalises for it. kramdown-rfc stamps the interpreter
version into its generator comment, so two machines with identical pinned
tools would otherwise emit different bytes and the committed artifacts would
be un-diffable. The Makefile strips that one field; kramdown-rfc's own
version is kept, since it is pinned and does affect the output. This was
found by CI on its first run, not by reasoning — `make reproducible` builds
twice on one machine and cannot see it.

Installing them is a one-liner per tool — `gem install kramdown-rfc -v 1.7.43`,
`pip install xml2rfc==3.34.1 weasyprint==63.1` — plus a system Ruby and, for
PDF only, pango and the Noto fonts that weasyprint needs. There is
deliberately no `Gemfile`/`Gemfile.lock` and no `requirements.txt` here:
either would advertise an install path the build does not take, and the pins
above are the single source of truth.

**Known-good transitive gem set for kramdown-rfc 1.7.43** (recorded for the
record, not enforced — kramdown-rfc's own `~>` ranges pin these, and every one
is pure Ruby, so no native build is needed): kramdown 2.4.0,
kramdown-parser-gfm 1.1.0, kramdown-rfc2629 1.7.43, base64 0.3.0,
connection_pool 3.0.2, differ 0.1.2, json_pure 2.8.1, net-http-persistent
4.0.8, ostruct 0.6.3, rexml 3.4.4, unicode-blocks 1.11.0, unicode-name 1.14.0,
unicode-scripts 1.12.0, unicode-types 1.11.0. If drift ever shows up in
`make -C draft reproducible` across machines, the remedy is a `Gemfile.lock`
in `draft/`, not a change to this design.


**A macOS convenience, which is not the requirement.**
`draft/tools/install-macos-brew.sh` installs the four pins with Homebrew
(`--pdf` adds weasyprint and its runtime libraries; `--dry-run` prints the
plan). It is optional and non-authoritative, and nothing in `draft/Makefile`
depends on it — that separation is the point. The moment a build target needs
an installer, the stated requirement has quietly become "have Homebrew", which
is a far larger claim than "have kramdown-rfc 1.7.43", and it takes the choice
of mechanism away from the host. The script ends by running `preflight.sh` and
defers to its verdict: the script installs, preflight decides.

It does not edit your shell profile. Homebrew's ruby is keg-only and its gem
bin directory is separate again, so two `PATH` lines are needed; the script
prints them rather than writing them, because a printed line can be read before
it is run and a rewritten dotfile cannot.

## 3. Build, check, diff

```sh
make -C draft preflight  # toolchain artifact check only
make -C draft            # xml + txt + check   (the default)
make -C draft check      # the three checkers, no rebuild
make -C draft html       # .html on demand (not in the default target)
make -C draft pdf        # .pdf on demand (needs weasyprint)
make -C draft formats    # txt + html + pdf in one command
make -C draft reproducible   # build twice, cmp the outputs
make -C draft refs       # (rare) repopulate bib/ from bib.ietf.org
make -C draft diff OTHER=/path/to/theirs.xml   # local diff, never uploads
```

The default target builds exactly the two artifacts that are committed — the
`.xml` and the `.txt`. `.html` and `.pdf` are derivable and gitignored, so
they are on demand; `formats` builds the full set in one command. Keeping
`.pdf` off the default path is deliberate: it is what stops weasyprint and
its font stack from becoming mandatory for every check run, which matters
most for a future CI job that needs to verify the draft, not print it.

`bib/` is already committed, so a clean checkout needs only the toolchain and
`make -C draft`. `refs` exists for adding a new reference, and is the one
target that touches the network.

`check` runs three gates, and all three must pass:

- `tools/check_render.py` — every JSON block in the XML equals its file on
  disk; the Appendix H roster counts match; `docName` is pinned; no host
  paths or personal identifiers; no network-fetch entities; no broken
  references.
- `tools/check_prose.py` — every RFC 2119 sentence in `spec/` is covered by
  the draft or listed in `prose-exceptions.toml` with a reason.
- `fixtures/validate.py` — the conformance gate itself, unchanged.

Every recipe `cd`s to the repo root before invoking `kramdown-rfc`, because
its `{::include}` directives resolve against the current working directory,
not the source file's location — so the build works the same whether you run
`make -C draft` or `make` from the repo root.

**Fixture selection is not final.** `fixtures.toml` currently inlines 9 of the
75 fixtures: five carried over from the earlier hand-maintained rendering,
plus one demonstrating the OPEN envelope, one the CLOSED envelope, one the
peer-origin cross-lock, and the Binding Record shown inline in its own section
(`#sec-9` in the source). The count and membership may change after a
standards review; that is a one-line edit to the TOML, never a code change.

## 4. The hold

This repo is under a standing publication hold pending patent counsel
(CLAUDE.md). **The build in this directory must never transmit anything.**

- `kramdown-rfc` and `xml2rfc` are invoked directly, never through `kdrfc` —
  `kdrfc` silently POSTs the XML to `https://author-tools.ietf.org/api/render/`
  when it cannot exec a local `xml2rfc` (`kdrfc-processor.rb:124-131`).
- `xml2rfc` is always called with `--no-network`.
- `kramdown-rfc` is always called with `KRAMDOWN_OFFLINE=1`, except the one
  explicit `make -C draft refs` target that populates `bib/` (a network *read*
  from bib.ietf.org, committed afterward so no later build needs it).
- `make -C draft diff` normalizes and diffs two renderings **locally**; it
  never uploads anything. Whether to use IETF Author Tools' web diff is the
  document owner's call, under the hold, and nothing here does it.

A full build has been verified to succeed with all outbound network blocked.

## 5. What is committed, and what is not

- **Committed:** `dist/draft-amap-00.xml` and `.txt` (small, diffable,
  reviewable in a PR); `bib/*.xml` (the bibxml cache).
- **Gitignored:** `dist/draft-amap-00.html` and `.pdf` (both derivable, both
  large — built on demand) and `draft/build/` (generated intermediates).
- **Never touched by this build:** `spec/`, `schemas/`, `fixtures/*.json`,
  and `fixtures/validate.py`.

## 6. Counsel gates before this draft may be submitted anywhere

**Counsel approved publication on 2026-09-17** — this repository, the local
router, and the Claude Code connector, plus taking AMAP to the IETF. Other
Proofpoint products are explicitly out of scope and remain unpublished.

Approved to publish is not the same as ready to submit. **Two** values in the
front matter are still open, and both are binding legal statements rather than
editorial choices:

- **`ipr:`** — currently `none`, which emits no boilerplate and asserts
  nothing. It is a deliberate non-answer. The real value (`trust200902` and
  its more restrictive variants) selects the copyright grant made to the IETF
  Trust under BCP 78. A draft intended for eventual working-group adoption
  normally needs the full grant, because a working group must be able to
  modify the text — so this choice can constrain the document's future.
- **`submissiontype:`** — currently `independent`. The alternative is the
  IETF stream, which interacts with the choice above.

Separately and independently, **BCP 79 (RFC 8179) imposes a patent-disclosure
obligation** on contributors: patents or applications known to be potentially
essential to the technology must be disclosed to the IETF. That obligation is
not satisfied by choosing an `ipr` value, and the original hold on this work
was described as "pending patent counsel" — so it is the question most likely
to matter here. It is being put to counsel.

Settled:

- **Author affiliation is included** (`Proofpoint, Inc.`), per the approval.
- **The draft name** (`draft-amap-00`) should still be confirmed against
  datatracker before submission — the last rename happened because the old
  acronym collided with an adopted working-group draft.
- **The date is pinned literally** (not derived from git) and must be bumped
  by hand when the content changes meaningfully — an Internet-Draft's date is
  a meaningful, deliberate signal, not a build artifact.

None of this directory's tooling uploads, submits, or posts anything (see
"The hold" above), so building here carries no publication risk by itself.
Treat the render as a diffable local artifact until the two open values above
are answered.

### `ipr` — SETTLED 2026-09-21: `trust200902`

Proposed by the standards contact in a chat with counsel and agreed without
disagreement. It is the least restrictive of the four variants: the full BCP 78
grant. `noModificationTrust200902`, `noDerivativesTrust200902` and
`pre5378Trust200902` were considered and rejected for a concrete reason — the
derivative-works grant is what allows a working group to ADOPT AND EDIT the
draft, so withholding it would make the document unadoptable and defeat the
point of taking it to the IETF.

**Setting it changed the rendered document substantively.** Under `ipr: none`
xml2rfc emitted no boilerplate. Under a real value it emits the true "Status of
This Memo" (*"This Internet-Draft is submitted in full conformance with the
provisions of BCP 78 and BCP 79"*), a Copyright Notice assigning to the IETF
Trust, an expiry date, and an `Internet-Draft` page header — and it collided
with our hand-written note of the same name, which had to be renamed to
`note_About_This_Draft`. **The document now asserts it is an Internet-Draft
submitted under BCP 78/79. Nothing has been submitted anywhere.** That gap
closes when it is filed, and not before.

### `email:` for the second author — ask, never infer

`T. Adams` was added to the author block on the operator's instruction. The
`email:` line is commented out because an RFC author block publishes a working
address permanently and is the contact of record for IPR correspondence under
BCP 78/79. Deriving it from a colleague's address pattern would put a guessed
address on a rights document. Supply the address the author states, or delete
the commented line if they prefer none.

Adding a co-author is itself a rights act, not an editorial one: each listed
author makes the BCP 78/79 disclosure commitments. Worth confirming with counsel
in the same pass that settles `ipr` and `submissiontype` rather than separately.
