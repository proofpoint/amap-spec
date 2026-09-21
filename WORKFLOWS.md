# WORKFLOWS.md — how changes reach the spec, and how they reach the draft

Two people change this repository, from opposite ends, and the rules are not
symmetric. This file states which direction a change is travelling, what is
canonical while it travels, and which tool refuses to let it travel silently.

```
   implementations                  spec/ + schemas/ + fixtures/                draft/draft-amap.mkd
   (a dozen workspaces)      <-->   the normative contract              <-->    the Internet-Draft
                             (A)                                        (B)
```

**(A) Spec-first.** A capability changes in an implementation; `spec/` is
where it becomes real; the draft is re-rendered to match.
**(B) Draft-first.** A standards edit lands in the draft; it is canonical the
moment it lands; `spec/` must be brought up to it, and the implementations
after that.

The invariant that makes both safe: **`spec/` + `schemas/` + `fixtures/` is
the single normative contract.** Neither workflow changes that. What differs
is which end a change *enters* from — and in direction B, `spec/` is the
thing that must move, not the thing that wins.

---

## A. Spec-first — a capability changes

Used when an implementation needs a new field, a new obligation, a new
vocabulary value, or a tightened rule.

1. **The change starts here, not in the implementation.** A PR against
   `spec/contract.md` + `schemas/` + `fixtures/`, *before* either side builds
   it. No runtime and no connector may invent a wire field locally. This is
   CLAUDE.md's existing propagation rule and it is not new.
2. **Add the fixtures in the same change.** A field with no fixture is a
   field no implementer can prove they handle. `python3 fixtures/validate.py`
   must stay green.
3. **Record it in §7's version history.** House style is to leave a wrong
   bullet standing and attach a Correction; what shipped is a fact.
4. **Carry it into the draft.** Edit the corresponding section of
   `draft/draft-amap.mkd`. `make -C draft check` will tell you if you missed
   something.
5. **Re-render and commit** `dist/draft-amap-00.{xml,txt}`.

**What catches you:** `check_prose.py`, forward direction. Every RFC 2119
sentence in `spec/` must be covered by a sentence in the draft, or listed in
`draft/prose-exceptions.toml` with a reason. Add an obligation to `spec/` and
forget the draft, and `make -C draft check` fails naming the exact sentence.

**Working across many repositories.** Implementations propose; they do not
decide. An implementation workspace that needs a contract change opens it
against this repo. The reason is mechanical, not procedural: the fixtures are
how a second implementation proves conformance without the first being
present, so a change that exists only in one workspace is a change nobody
else can implement against.

## B. Draft-first — a standards edit

Used when the standards contact edits `draft/draft-amap.mkd` directly:
wording, structure, RFC conventions, or a normative change an IETF reviewer
asked for.

**Those edits are canonical.** The draft is the document going to the IETF,
and a change made there is the change. Do not "fix" the draft to match
`spec/` — that is backwards, and it silently discards standards review.

1. **Take the edit as given.** Do not revert, reword, or re-derive it from
   `spec/`.
2. **Classify it.** Presentation-only (wording, section order, references,
   boilerplate) needs nothing further — the draft owns its own prose.
   Anything that changes *meaning* continues below.
3. **Promote it into `spec/`.** Update `spec/contract.md` (or
   `spec/peer-origin.md`) so the contract says what the draft now says.
4. **Follow it into `schemas/` and `fixtures/`** if the shape or the
   acceptance rules moved. A normative change with no fixture is not done.
5. **Ripple it to the implementations.** This is the expensive step and the
   easy one to skip: a tightened obligation can make a conforming runtime
   non-conforming. Note it in §7's version history so both sides upgrade
   deliberately.
6. **Re-render and commit** the `dist/` artifacts.

**What catches you:** `check_prose.py`, reverse direction. A normative
sentence in a spec-rendering section of the draft (§3–§10) with no
counterpart in `spec/` fails the build, naming the sentence and pointing
here. The IETF apparatus the draft owns outright — Introduction, Terminology,
Security Considerations, IANA, the appendices — is not checked in this
direction, because that content has no `spec/` counterpart by design.

`draft/draft-only-baseline.toml` records the draft-only sentences that
existed when the check was introduced. **It is a snapshot, not an
allowlist.** Adding to it is how this mechanism gets defeated: a new entry
means the check fired and someone baselined the finding instead of deciding
it. Working the list down — promoting each into `spec/`, or rewording the
draft to match — is real progress.

---

## Mechanics — branch, commit, review, render

Both directions say "a PR against `spec/` + `schemas/` + `fixtures/`" and
neither has said what that means in practice. It means this.

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

**Record a correction rather than rewriting history.** `spec/contract.md`
§7's house style is to leave a wrong bullet standing and attach a
**Correction** to it. What shipped is a fact, and a version history that
quietly edits itself is worth less than one that admits a mistake. This
applies to commit messages too: a follow-up commit that says "the previous
commit's reasoning was wrong, here is why" beats an amend.

**Run the gates before you ask anyone to look.** `make -C draft` is the
whole set — the render check, both prose directions, and the fixture gate.
A green run is the minimum for review, not evidence the change is right;
what a green run does *not* prove is listed at the end of this file and in
`fixtures/validate.py`'s NOT-CHECKED docstring.

**Rebuild `dist/` in the same commit as the source change.** The committed
`.xml` and `.txt` are reviewable artifacts, so a PR whose source and
rendering disagree is a PR nobody can read. `git status` clean after
`make -C draft` is the check: it means the rendering you committed is the
one the build produces.

**Review is a human reading the normative diff**, not a green check. For a
spec-first change that means `spec/` plus the fixtures; for a draft-first
change it means the draft sections that moved. The tooling exists to make
that review cheaper and to catch what a reader would miss, not to replace
it.

**Cutting a version means telling the consumers.** `CONSUMERS.md` registers
who is downstream, what each pins, and how to reach them. A version is not cut
until every row has been told what changed and what to re-check. This is a
step, not a courtesy: three downstream implementations were found in one week
building against versions this seam had already moved past, every one surfaced
by luck, and none was detectable from either end. Writing a changelog is not
telling anyone.

**When the hold lifts.** A public repository needs a `CONTRIBUTING.md` —
GitHub surfaces it on every PR — and it should be *thin*: a pointer to this
file, plus the IPR and DCO terms for outside contributions, which is a
counsel question and not an editorial one. Do not write it before then, and
do not let it restate this file when you do.

## Who owns what

| | owner | the other side |
|---|---|---|
| Wire shapes, obligations, vocabularies | `spec/` + `schemas/` + `fixtures/` | the draft renders them |
| Conformance classes and what they require | `spec/` | the draft renders them |
| Draft prose, section order, RFC conventions | `draft/draft-amap.mkd` | `spec/` does not track them |
| Introduction, Terminology, Security Considerations, IANA | the draft, outright | no `spec/` counterpart exists |
| Front matter, `ipr`, author, draft name, date | the draft | counsel gates apply — `draft/README.md` |
| Which fixtures appear inline | `draft/fixtures.toml` | the files on disk decide what they *say* |

## The checks, and what each direction proves

```sh
make -C draft check
```

- `tools/check_render.py` — every JSON block in the rendering equals its file
  on disk. Proves the *generated* half cannot drift.
- `tools/check_prose.py` — both directions of the *hand-written* half.
  Forward: no spec obligation is missing from the draft. Reverse: no draft
  obligation is missing from `spec/`.
- `fixtures/validate.py` — the conformance gate itself.

**What none of them prove.** `check_prose.py` matches vocabulary, not
meaning: a sentence reworded to say the opposite while keeping its words
still passes. It only sees RFC 2119 sentences, so normative content phrased
without a keyword is invisible to it. And the reverse direction loses
sensitivity on SHORT sentences built from common protocol words — a terse
four-word obligation sharing two words with any unrelated `spec/` sentence
clears the threshold. Measured, not assumed: an invented "A Connector MUST
verify the lozenge before rotation" slips through, while a longer or more
distinctive one is caught. It is a net, not a sieve. And it cannot tell a deliberate edit
from an accident — it only insists that one of you looked. Treat it as a
floor. The review is still the review.

*Why this file exists: a reconstruction of two draft sections once dropped 69
sentences — including a `MUST NOT` and an anti-traversal obligation — while
the build, the render check, byte-identical reproducibility and the fixture
gate all stayed green. Nothing mechanical noticed, because nothing was
checking this relationship at all.*
