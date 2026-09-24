# draft/ — the Internet-Draft, the canonical source of AMAP's prose

## 0. Layout

```
draft-amap.xml          THE SOURCE: xml2rfc v3 XML, hand-edited. The file you edit.
coverage.toml           the class of every normative sentence in sections 3-10
fixtures.toml           which fixtures the draft shows inline, and why (data)
examples/               the illustrative JSON shapes (hand-written)
bib/                    RFC <reference> entries, for adding a citation offline
Makefile                the entry point: `make -C draft`
tools/                  the build and gate machinery; nothing here is content
```

## 1. What this is

`draft-amap.xml` is the canonical normative prose of AMAP (since 2026-09-24).
Together with `schemas/` and `fixtures/`, it *is* the contract. It is not
generated from anything. The standards editor edits it directly, and a change
made there is the change (`WORKFLOWS.md`, "Editor-first").

`spec/contract.md` is frozen: the record of the text this draft was reconciled
against. Its header maps its old sections to the draft's. The peer-origin
profile, `spec/peer-origin.md`, is **not** frozen: it is v3.1.0 DRAFT, and this
draft carries only its schema (Appendix F).

The build renders `dist/draft-amap-00.xml` (a byte copy of the source) and
`dist/draft-amap-00.txt`, and on demand `.html` and `.pdf`.

## 2. What a tool writes, and what you write

**You write every byte**, except the body of each JSON `<sourcecode>` block.
Those are written from disk by `tools/sync_sources.py`:

| draft anchor | file |
|---|---|
| `schema-<name>` | `schemas/<name>.schema.json` |
| `<anchor>-src`, one per `fixtures.toml` entry | `fixtures/<file>` |
| `ex-<stem>` | `examples/<stem>.json` |

`make -C draft sync` rewrites any block that differs from its file. It edits
only the text between `<![CDATA[` and `]]>`, and only in blocks it maps,
folding long lines per RFC 8792 exactly as the old kramdown-rfc build did
(`fold69hardleft4dry`). So:

- **To change a schema, fixture or example:** edit the file, run `make sync`,
  and commit both.
- **To add a schema or a listed fixture:** add a `<figure anchor="…">` with an
  empty `<sourcecode type="json"><![CDATA[]]></sourcecode>` and run
  `make sync`. `make check` fails if a schema or listed fixture has no block.
- **Never paste JSON into the XML by hand.** The check fails on any difference.

Why not xml2rfc's own `<sourcecode src="…">`: xml2rfc 3.34.1 crashes on any
non-ASCII UTF-8 in a `src` file (the schemas carry `§` and `—`), and it does no
RFC 8792 folding (schema lines reach 326 characters).

## 3. Building, and the gates

```sh
make -C draft                 # render dist/ and run every gate
make -C draft sync            # rewrite JSON blocks from disk
make -C draft normdiff BASE=origin/main   # the normative diff, for review
make -C draft formats         # also .html and .pdf (pdf needs weasyprint)
make -C draft diff OTHER=theirs.xml       # local diff against another copy
make -C draft reproducible    # two text renders, byte-compared
```

`make -C draft` runs:

- `tools/sync_sources.py`: JSON blocks equal disk; every block maps to a
  file; every schema and listed fixture has a block.
- `tools/check_render.py`: the same equality re-derived from the XML, plus the
  fixture roster counts, the pinned `docName`, and no host paths or personal
  identifiers.
- `tools/check_coverage.py`: every RFC 2119 sentence in sections 3–10 and the
  peer directory has a class in `coverage.toml` (fixture, operational,
  informative). The 128 sentences present at the switch are an unclassified
  **baseline**; classify them as you review them, and never add a new
  unclassified entry. `--emit` prints stubs for new sentences.
- `fixtures/validate.py`: the conformance suite.

`tools/normdiff.py` is not a gate. It lists the normative sentences added,
removed or changed against a git ref, and CI writes it to every PR's summary.
It is what a reviewer reads instead of the XML diff.

### Toolchain requirement

| tool | version | used for |
|---|---|---|
| xml2rfc | **3.34.1** exactly | rendering `.txt`, `.html`, `.pdf` |
| Python | ≥ 3.11 | the gates (`tomllib`) |
| weasyprint | 63.1 | only `make pdf` / `make formats` |

The repository states the requirement and does not install it.
`tools/preflight.sh` checks the artifact, never the mechanism. On a Mac,
`tools/install-macos-brew.sh` is an optional helper. kramdown-rfc and Ruby are
no longer needed.

## 4. Never transmit anything

- `xml2rfc` is always called with `--no-network`, and never through `kdrfc`,
  which silently POSTs the XML to `https://author-tools.ietf.org/api/render/`
  when it cannot find a local `xml2rfc`.
- The build needs no network: every reference is inlined in the source, and
  `bib/` holds RFC `<reference>` entries to copy in when adding a citation.
- `make -C draft diff` compares renderings **locally**. Submitting, or using
  IETF Author Tools, is the document owner's decision, and nothing here does it.

## 5. What is committed, and what is not

- **Committed:** `draft-amap.xml` (the source), `dist/draft-amap-00.xml` (its
  copy) and `.txt`, `coverage.toml`, `fixtures.toml`, `examples/`, `bib/`.
- **Gitignored:** `dist/*.html` and `dist/*.pdf`.
- **Never written by the build:** `schemas/`, `fixtures/`, `spec/`.

## 6. Counsel gates before this draft may be submitted anywhere

**Counsel approved publication on 2026-09-17** — this repository, the local
router, and the Claude Code connector, plus taking AMAP to the IETF. Other
Proofpoint products are explicitly out of scope and remain unpublished.

**Status, 2026-09-24: the operator confirmed that counsel's gates are clear.**
The front matter carries `ipr="trust200902"` and `submissionType="independent"`,
and both authors' email addresses. The draft is ready for submission and **has
not been submitted.** The history of each gate is kept below, because each was
a binding legal statement rather than an editorial choice.

- **`ipr`**: settled 2026-09-21 as `trust200902` (below).
- **`submissionType`**: `independent` (the Independent Submissions Editor). The
  alternative is the IETF stream, via a working group, which the full BCP 78
  grant keeps possible.

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

None of this directory's tooling uploads, submits, or posts anything (see §4),
so building here carries no publication risk by itself.

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

### The second author's email — settled

`T. Adams` was added to the author block on the operator's instruction, and the
author block now carries an email address for each author. The rule that
governed it still holds for any future author: an RFC author block publishes a
working address permanently, as the contact of record for IPR correspondence
under BCP 78/79, so it is the address the author states, never one inferred from
a colleague's address pattern.

Adding a co-author is itself a rights act, not an editorial one: each listed
author makes the BCP 78/79 disclosure commitments. Worth confirming with counsel
in the same pass that settles `ipr` and `submissiontype` rather than separately.
