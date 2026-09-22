# Contributing to amap-spec

This repository is a **wire contract** and nothing else — `spec/contract.md`,
`schemas/`, `fixtures/`, and a generated `dist/` rendering. It is not a
connector, not a runtime, not a transport. If you are about to write code that
*does* something with mail, the change belongs in an implementation.

That makes contributing here different from contributing to a library, in one
way that costs people real work if nobody says it first:

> **A capability change lands as `spec/` + `schemas/` + `fixtures/` in one
> change, before either side builds it.**

A schema change without a fixture is the most common well-intentioned PR we
expect to receive, and it is the one we cannot merge. The reason is in §7 of the
contract: **the fixtures *are* the other side.** A field with no fixture is a
field no implementer can prove they handle, and an implementation that cannot
prove it handles a field will be asked to claim conformance it has not earned.

## Before you open a PR

Run the gate. It is stdlib-only, needs no network, and takes under a second:

```sh
python3 fixtures/validate.py
# 82 fixtures checked, 0 unexpected.
```

If you touched `spec/` or `draft/draft-amap.mkd`, also run the draft build —
see `draft/README.md` for the toolchain, and `draft/tools/install-macos-brew.sh`
if you are on a Mac:

```sh
make -C draft
```

That runs three gates: the fixture suite, a check that every JSON block in the
rendered draft equals a file on disk, and a check that every RFC 2119 sentence
in `spec/` is covered by the draft.

## The shape of a change

**Additive ⇒ MINOR. Breaks an existing fixture ⇒ MAJOR.** A major is taken
deliberately by both implementation sides, not unilaterally here. A version
mismatch must fail closed; it must never silently mis-parse.

**Fixtures go in the same change.** `fixtures/valid/` must pass and
`fixtures/invalid/` must fail. Note that the schema is chosen by **filename
prefix** — the prefix is load-bearing, and a misnamed fixture validates against
the wrong schema and passes for the wrong reason.

**`validate.py` implements a subset of JSON Schema 2020-12.** A keyword outside
that subset is *silently ignored*, so a fixture exercising one proves nothing.
If you add a keyword, extend the validator in the same change. The subset is
listed at the top of `fixtures/validate.py`.

**`dist/` is regenerated, never hand-edited.** If a diff to `dist/` is not the
output of `make -C draft`, it is wrong. On a conflict, `spec/contract.md` plus
the fixture gate govern; `dist/` is non-authoritative.

**Version history is recorded, not rewritten.** §7's house style is to leave a
wrong bullet standing and attach a *Correction*, because what shipped is a fact.
Please follow it rather than editing history into agreement with the present.

## Changes that travel the other way

Some changes arrive from the standards side — the Internet-Draft is hand-edited
and those edits are canonical. They are then promoted *into* `spec/`, and into
`schemas/`/`fixtures/` if the shape moved. `WORKFLOWS.md` describes both
directions and which rules apply to each. Read it before changing `spec/` or
`draft/draft-amap.mkd`.

## What a green gate does not prove

`fixtures/validate.py`'s NOT-CHECKED docstring is the authoritative list, and it
is worth reading before claiming conformance for anything. It covers the
filesystem and policy obligations no document validator can see: atomicity,
write ordering, path discipline, caps, allowlists, read-only-inbound tolerance,
single-writer/single-drainer. §7.1 states it plainly — claiming a conformance
class without the fixture run **and** the prescribed operational check for that
class is not conformance.

## Reporting a problem in the specification

A defect in the contract is more valuable than a defect in code, and harder to
see. If you have hit a clause you cannot satisfy, or two that contradict each
other, please open an issue saying **what the spec says versus what reality
required of you** — that framing has already produced several corrections here.

If you believe you have found a security problem, see `SECURITY.md` and do not
open a public issue.

## Licence

By contributing you agree that your contributions are licensed under the
Apache License 2.0, as in `LICENSE`.
