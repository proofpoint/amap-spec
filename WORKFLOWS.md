# WORKFLOWS.md — how changes reach the contract

Two kinds of change reach this repository, from opposite ends, and the rules are
not symmetric. This file states which direction a change is travelling, what is
canonical while it travels, and which tool refuses to let it travel silently.

```
   implementations               schemas/ + fixtures/              draft/draft-amap.xml
   (a dozen workspaces)   -->    the machine-checkable rules  <-->  the canonical prose,
                          (A)                                  (B)  hand-edited by the
                                                                    standards editor
```

**The contract is `draft/draft-amap.xml` + `schemas/` + `fixtures/`.** Since
2026-09-24 the Internet-Draft XML is the canonical normative prose. It is
hand-edited, rendered to `dist/`, and generated from nothing. `schemas/` and
`fixtures/` stay canonical for what a machine can check. `spec/contract.md` is
**frozen**: kept as the record of the text the draft was reconciled against,
never edited (its header maps its sections to the draft's). The peer-origin
profile, `spec/peer-origin.md`, is **not** frozen: it is v3.1.0 DRAFT, the
Internet-Draft carries only its schema, and it stays the canonical prose for
the peer lane until it leaves DRAFT.

The draft never contains hand-copied JSON. Every schema, listed fixture and
illustrative example it shows is written into it from the file on disk by
`draft/tools/sync_sources.py` (`make -C draft sync`), which rewrites only those
blocks and leaves every other byte to the editor.

**(A) Rules-first.** A capability changes in an implementation. It becomes
real in `schemas/` + `fixtures/` first, with the prose carried into the draft
in the same change.
**(B) Editor-first.** A standards edit lands in the draft. It is canonical the
moment it lands; if it changes meaning, `schemas/` and `fixtures/` must be
brought up to it, and the implementations after that.

---

## A. Rules-first: a capability changes

Used when an implementation needs a new field, a new obligation, a new
vocabulary value, or a tightened rule.

1. **The change starts here, not in the implementation.** A PR against
   `schemas/` + `fixtures/`, and the draft's prose, *before* either side
   builds it. No runtime and no connector may invent a wire field locally.
2. **Add the fixtures in the same change.** A field with no fixture is a
   field no implementer can prove they handle. `python3 fixtures/validate.py`
   must stay green.
3. **Write the prose into `draft/draft-amap.xml`.** An implementer who can't
   write IETF prose opens the PR with the schema and fixture change plus an
   issue describing the obligation, and the editor writes the text. The prose
   is the editor's; the rules are the PR's.
4. **Sync and re-render.** `make -C draft sync` if a schema, listed fixture or
   example changed, then `make -C draft`; commit the source, the rewritten XML
   and `dist/` together.
5. **Classify each new normative sentence** in `draft/coverage.toml`: which
   fixtures exercise it, or why none can (operational, informative).
6. **Record it in the draft's Change Log.**

**What catches you:**
- `sync_sources.py`: a schema or listed fixture changed and the draft's copy of
  it didn't, or it has no block in the draft at all.
- `check_coverage.py`: a new MUST with no classification.

**Working across many repositories.** Implementations propose; they do not
decide. An implementation workspace that needs a contract change opens it
against this repo. The reason is mechanical, not procedural: the fixtures are
how a second implementation proves conformance without the first being
present, so a change that exists only in one workspace is a change nobody
else can implement against.

## B. Editor-first: a standards edit

Used when the standards editor edits `draft/draft-amap.xml` directly: wording,
structure, RFC conventions, or a normative change an IETF reviewer asked for.

**Those edits are canonical.** The draft is the document going to the IETF,
and a change made there is the change. Do not revert, reword or re-derive it.

1. **Take the edit as given.**
2. **Classify it.** Presentation-only (wording, section order, references,
   boilerplate) needs nothing further. Anything that changes *meaning*
   continues below.
3. **Follow it into `schemas/` and `fixtures/`** if the shape or the
   acceptance rules moved. A normative change with no fixture is not done.
4. **Classify the new or reworded sentences** in `draft/coverage.toml`.
5. **Ripple it to the implementations.** This is the expensive step and the
   easy one to skip: a tightened obligation can make a conforming runtime
   non-conforming. Note it in the Change Log so both sides upgrade
   deliberately.
6. **Re-render and commit** `dist/`.

**What catches you:**
- `check_coverage.py`: every RFC 2119 sentence in the protocol sections
  (3–10 and the peer directory) needs a class in `draft/coverage.toml`. A new
  sentence, or a reworded one (rewording changes its key), fails the build
  until someone decides what covers it.
- `normdiff.py` (`make -C draft normdiff BASE=<ref>`; CI writes it to the job
  summary of every PR): the added, removed and changed normative sentences.
  **This is what the reviewer reads**, instead of the XML diff.

---

## Mechanics — branch, commit, review, render

Both directions end in "a PR", and this is what that means in practice.

**Branch off `main`.** Name it for the change, not the author or the date —
`peer-origin-profile`, `stable-connector-id`. `origin` is
`github.com/proofpoint/amap-spec` and is the only writable copy;
`git push -u origin <branch>` on a new branch, plain `git push` thereafter.

*The repository moved from internal GitHub Enterprise to github.com on
2026-09-17, after counsel approved publication. The GHE copy is archived and
read-only. If you have an old clone, re-point it:*
`git remote set-url origin https://github.com/proofpoint/amap-spec.git`.
*Prefer `git remote set-url` over `git remote rename` here — renaming
rewrites `.git/packed-refs` wholesale, which fails on some shared mounts.*

**Which GitHub account.** `proofpoint` is a regular github.com organization.
Enterprise-managed accounts — the internal ones, recognisable by an
enterprise suffix — **cannot access it at all**, and the failure is a `404`
on the *username*, indistinguishable from "no such repo" or "no permission".
If you hold both kinds of account, use the regular one here. This is also why
the repository lives on public github.com rather than internally: the
standards contact who edits the draft is not on the enterprise instance, and
the two namespaces cannot collaborate.

**One change per commit, and say why rather than what.** The diff already
says what moved. The message is where the reasoning goes — what was wrong,
what the alternative was, what it cost. `git log` in this repo is a design
record and several commits here are the only place a decision is written
down. Keep the subject under ~72 characters and lowercase after the prefix
(`draft:`, `dist:`, `spec:`) where one applies.

**Record a correction rather than rewriting history.** The version history's
house style (the draft's Change Log, and the frozen `spec/contract.md` §7
before it) is to leave a wrong bullet standing and attach a **Correction** to
it. What shipped is a fact, and a version history that
quietly edits itself is worth less than one that admits a mistake. This
applies to commit messages too: a follow-up commit that says "the previous
commit's reasoning was wrong, here is why" beats an amend.

**Run the gates before you ask anyone to look.** `make -C draft` is the
whole set: the JSON-block sync check, the render check, the coverage check and
the fixture gate.
A green run is the minimum for review, not evidence the change is right;
what a green run does *not* prove is listed at the end of this file and in
`fixtures/validate.py`'s NOT-CHECKED docstring.

**Rebuild `dist/` in the same commit as the source change.** The committed
`.xml` (a copy of the canonical source) and `.txt` are reviewable artifacts,
so a PR whose source and rendering disagree is a PR nobody can read. `git status` clean after
`make -C draft` is the check: it means the rendering you committed is the
one the build produces.

**Review is a human reading the normative diff**, not a green check. For a
rules-first change that means the schema and fixture diff plus the new prose;
for an editor-first change it means `normdiff.py`'s output. The tooling exists
to make that review cheaper and to catch what a reader would miss, not to
replace it.

**Cutting a version means telling the consumers.** `CONSUMERS.md` registers
who is downstream, what each pins, and how to reach them. A version is not cut
until every row has been told what changed and what to re-check. This is a
step, not a courtesy: three downstream implementations were found in one week
building against versions this seam had already moved past, every one surfaced
by luck, and none was detectable from either end. Writing a changelog is not
telling anyone.

**`CONTRIBUTING.md` stays thin.** It points here; it does not restate this
file. The IPR terms for outside contributions are a counsel question, not an
editorial one.

## Who owns what

| | owner | the other side |
|---|---|---|
| Normative prose: obligations, conformance classes, semantics | `draft/draft-amap.xml` (the editor) | `schemas/` + `fixtures/` must agree |
| Wire shapes, open/closed, patterns | `schemas/` | the draft shows them, synced from disk |
| What must pass and fail | `fixtures/` + `validate.py` | the draft shows the ones in `draft/fixtures.toml` |
| Draft prose, section order, RFC conventions, IETF apparatus | the draft, outright | — |
| Front matter, `ipr`, author, draft name, date | the draft | counsel gates apply — `draft/README.md` |
| Peer-lane prose (DRAFT profile) | `spec/peer-origin.md` | the draft carries only its schema |
| Which normative sentences are covered by what | `draft/coverage.toml` | enforced by `check_coverage.py` |

## The checks, and what each proves

```sh
make -C draft          # build dist/ and run every gate
make -C draft normdiff BASE=origin/main
```

- `tools/sync_sources.py`: every JSON block in the draft equals its file on
  disk, every block maps to a file, and every schema and listed fixture has a
  block. The last check matters because a missing block is the omission a
  comparison can't see: it is how the missing directory schema was found.
- `tools/check_render.py`: the same equality re-derived from the XML, plus the
  roster counts, the pinned draft name, and no host paths or personal
  identifiers.
- `tools/check_coverage.py`: every normative sentence in the protocol sections
  is classified. The 128 sentences present at the switch are recorded as an
  unclassified baseline; working it down is the backlog.
- `tools/normdiff.py`: the normative diff, for the reviewer.
- `fixtures/validate.py`: the conformance gate itself.

**What none of them prove.** They see RFC 2119 sentences, so normative content
phrased without a keyword is invisible to them. A classification is only as
good as the person who made it: `check_coverage.py` insists a decision was
made, not that it was right. And none of them can tell a deliberate edit from
an accident. They only insist that someone looked. Treat them as a floor. The
review is still the review.

*Why this file exists: a reconstruction of two draft sections once dropped 69
sentences, including a `MUST NOT` and an anti-traversal obligation, while the
build, the render check, byte-identical reproducibility and the fixture gate all
stayed green. Nothing mechanical noticed, because nothing was checking the
normative content at all. The coverage gate and the normative diff are this
repository's answer now that the draft is the source.*
