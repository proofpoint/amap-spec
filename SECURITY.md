# Security Policy

## Reporting a vulnerability

**Do not open a public issue for a security problem.**

Report it privately to:

> **resero-labs@proofpoint.com**

You may also use GitHub's private vulnerability reporting on this repository if
it is enabled.

Please include what you found, how to reproduce it, and which version of the
contract you were reading — `spec/contract.md` carries its own version in the
title, and the wire major is `contract_version` in every document.

## What counts as a vulnerability here

This repository is a **specification**, not an implementation. It contains no
running code beyond a stdlib validator and a documentation build. So the
interesting reports are about the contract itself:

- **A clause that cannot be satisfied securely**, or two clauses that force an
  implementer to choose between them. This has already happened more than once
  and each instance was a real defect.
- **An obligation with no conformance fixture.** A field with no fixture is a
  field no implementer can prove they handle, and the gap is invisible to a
  green gate.
- **A schema that permits what the prose forbids.** The prose and the schema
  disagreeing is a defect even when the prose is right, because the schema is
  what implementations actually validate against.
- **An attack the trust model does not account for** — particularly anything
  that lets an agent influence a routing or identity decision that the contract
  says belongs to the runtime.

If you have found a vulnerability in an *implementation* rather than in the
contract, please report it to that project.

## What the contract already assumes

Before reporting, it is worth knowing the model. The agent is **fully
untrusted**: its only outbound action is dropping an inert request file, and a
file drop carries no capability. The runtime decides whether anything is sent,
to whom, and how. Inbound content is data and never instruction. Origin is
determined by which tree a message arrived in, never by a field inside it.

`fixtures/validate.py`'s NOT-CHECKED docstring lists the filesystem and policy
obligations no document validator can see. A report that one of those is
unenforced by the gate is expected rather than surprising — but a report that
one of them is *unstated*, or stated in a way an implementer cannot satisfy, is
exactly what we want to hear.

## Disclosure

We will acknowledge a report, tell you whether we agree it is a defect, and
agree a disclosure timeline with you. Because this is a specification heading
for the IETF, a contract-level defect may need to be fixed in the draft as well
as here, and we will say so if that affects timing.
