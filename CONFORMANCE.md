# amap-spec conformance

This workspace implements a component of the **amap** fleet. The authoritative
specification is mounted read-only in this container at:

```
~/.amap-spec/
  dist/draft-amap-00.txt  THE NORMATIVE PROSE: the AMAP Internet-Draft, rendered.
                          Cite it by section number.
  schemas/                JSON Schema documents the spec's artifacts must validate against
  fixtures/               canonical example artifacts, valid and invalid
  spec/peer-origin.md     the peer-origin profile (DRAFT): still normative for the
                          peer lane, which the draft covers only by its schema
  spec/contract.md        FROZEN history: the text the draft replaced. Not authoritative.
  CONFORMANCE.md          this file
```

**Since 2026-09-24 the Internet-Draft is the specification's prose.** It is
hand-edited as `draft/draft-amap.xml` in the amap-spec repository and rendered to
`dist/`. `spec/contract.md` is frozen: it says so in its first lines, and its
header maps each of its old sections to the draft's. Do not conform to it, or
cite it, as current. Where it and the draft differ, the draft is right.

These are **live bind mounts of the amap-spec checkout on the host**, read-only.
They are not a snapshot: a change the operator renders appears here immediately,
with no relaunch. You cannot edit them, and you should not try to — spec changes
are made in the `amap-spec` repository.

Because the mount is live, it has no version stamp. The spec you are reading is
whatever the operator's checkout holds at this moment, which may include
uncommitted work. When a conformance claim needs to name a version, ask for it
rather than inventing one.

## What is expected of you

**Read the spec before changing behaviour that the spec governs.** Do not work
from memory of what amap "usually" does, and do not infer a rule from other
code in this workspace — other code may itself be non-conformant. The draft at
`~/.amap-spec/dist/draft-amap-00.txt`, with `schemas/` and `fixtures/`, is the
only authority here, plus `spec/peer-origin.md` for the peer lane.

**When you touch a spec-governed surface, verify conformance rather than
asserting it.** In order of strength:

1. Validate the artifact against the matching document in `~/.amap-spec/schemas/`
   — with a real validator, not by eye.
2. Diff the behaviour against the matching example in `~/.amap-spec/fixtures/`,
   including the *invalid* fixtures: a component that accepts an invalid fixture
   is non-conformant even when every valid one passes.
3. Quote the normative sentence from the draft (or, for the peer lane,
   `spec/peer-origin.md`) that your change satisfies, with its section number.

**Report the conformance status you actually established.** If you validated,
say so and name the schema. If you did not, say that instead — "conforms to the
spec" with nothing behind it is the failure this mount exists to prevent.

**Where this workspace and the spec disagree, the spec wins — but say so rather
than silently rewriting.** A genuine conflict is one of three things and they
need different handling, so name which one you believe it is:

- this workspace is non-conformant → fix the workspace;
- the spec is wrong or out of date → do not edit the mount; raise it, and say
  what the spec says versus what reality requires;
- the spec does not cover the case → say it is unspecified. Do not present an
  invented rule as a spec requirement.

**A missing mount is not permission to proceed.** If
`~/.amap-spec/dist/draft-amap-00.txt` is absent, the feature is not installed,
the operator's checkout has moved, or this sandbox launched before the `dist`
mount existed and needs a relaunch. Say so and stop, rather than falling back to
the frozen `spec/contract.md` or guessing at the spec's content.
