# Agent Mailbox Access Protocol (AMAP)

A versioned wire contract that lets a sandboxed AI agent send and receive email
through a runtime that **does not trust it**.

**Naming.** AMAP was called AMP ("Agent Mailbox Protocol") until 2026-09-15;
it was renamed because AMP collides with the IETF DTN working group's adopted
`draft-ietf-dtn-amp`, and this repository moved from `agent-mailbox-protocol`
to `amap-spec` with it. Dated records keep the old name.

AMAP is carried over a filesystem namespace rather than an API, and is
deliberately **owned by neither side**: a trusted mail runtime implements one
half, an untrusted per-agent connector implements the other, and the two can be
built by different people and versioned independently.

**Current version: 3.1.0 (DRAFT)** (wire `contract_version` `"2"` — the contract's own
SemVer and the wire major track different things as of 3.0.0; see
`spec/contract.md` §7).
Conformance gate: **75 fixtures**, 0 unexpected.

## The problem

Agents increasingly need email — it is how work arrives, how results return,
and how they correspond with people and systems outside the sandbox. It is
federated, of-record, and human-inclusive in a way a closed agent-to-agent
channel is not.

But an agent is an untrusted process: it can be prompt-injected, buggy, or
compromised. Granting it email directly is dangerous on three axes:

- **inbound** mail is an untrusted-content and injection vector delivered
  straight into the agent's reasoning;
- **outbound** mail is a data-exfiltration and identity-impersonation vector;
- any **credential** it holds can be leaked or abused, and the agent has no
  verifiable identity of its own.

Handing the agent mailbox credentials or a send API makes it a *trusted*
participant — unacceptable precisely when it may be compromised. The usual
alternative is ad-hoc per-deployment glue, which yields no interoperable
contract and no shared conformance bar.

## The approach

Interpose a **trusted runtime** that holds every credential, the agent's
identity, and all policy. Let the **untrusted agent** interact only through a
channel that carries **no capability**: it writes an inert file; the runtime
decides what happens next.

> **The invariant:** no security property depends on the agent — or on the
> connector speaking for it — behaving correctly. A compromised agent can at
> most write a well-formed request the runtime then refuses.

That is why the medium is a file drop rather than an API, RPC, or queue. The
medium *is* the boundary.

## What AMAP is not

- **Not a mail transport.** It neither defines nor replaces SMTP or IMAP, and
  composes with provider-side infrastructure rather than displacing it.
- **Not an agent-to-agent RPC.**
- **Not a policy language.** What a runtime's policy *decides* is out of scope;
  the wire defines only the request and verdict shapes.

## Layout

```
spec/contract.md   the normative contract — actors, invariant, directory
                   layout, message shapes, correlation, versioning
schemas/           JSON Schema (2020-12) for each message
fixtures/          golden valid + invalid artifacts, and the validator
dist/              a standalone, IETF-flavored draft, generated from the above;
                   non-authoritative on conflict — regenerated, never patched
```

`spec/contract.md`, together with `schemas/` and `fixtures/`, is the
normative contract. `dist/` is a rendering generated from it for standalone
reading; where the two disagree, `spec/contract.md` and the fixture gate
govern.

Run the conformance gate — no counterpart, no network, no dependencies:

```
python3 fixtures/validate.py
```

## How changes reach the spec

Changes enter from two ends — implementations propose against `spec/`, and
the Internet-Draft is hand-edited by a standards contact whose edits are
canonical. The two directions have different rules, and both are enforced by
`make -C draft check`. See [WORKFLOWS.md](WORKFLOWS.md).

## How conformance works

**The fixtures are the other side.** A connector proves conformance by passing
them; a runtime proves it the same way. Neither needs the other present, which
is what makes independent implementation practical.

Two rules govern change:

- **A capability change starts here** — a PR against `spec/contract.md` +
  `schemas/` + `fixtures/`, *before* either side builds it. Neither a runtime
  nor a connector may invent a wire field locally.
- **Additive ⇒ minor bump. Breaks a fixture ⇒ major bump**, taken deliberately
  by both sides. A version mismatch fails closed; it never silently
  mis-parses. As of 3.0.0 this splits into two axes — see §7: the *wire*
  major (`contract_version`) tracks envelope-shape compatibility, while the
  contract's own SemVer tracks the fuller set of obligations on both sides.

Some obligations are behavioral rather than wire-shaped — for example, that a
connector must not require write access to the inbound tree. Those sit outside
the fixture gate by construction, and §7 names the operational check for each.
`fixtures/validate.py`'s docstring lists what a green run does *not* prove.

## Status

Implemented on both sides and exercised end to end: sandboxed agents exchange
mail over this contract, including attachments whose size and digest the
runtime verifies itself. A reference runtime implementation exists
separately, deliberately minimal — it carries no mail stack of its own, so
the obligations this contract places on a runtime are visible without one
around them.

The version history is in `spec/contract.md` §7.

## Contributing

A capability change lands as `spec/` + `schemas/` + `fixtures/` in one change,
**before** either implementation builds it — a schema change without a fixture
is the one PR that cannot be merged, because the fixtures *are* the other side.
[CONTRIBUTING.md](CONTRIBUTING.md) explains that and the traps that are
invisible from outside: schema selection by filename prefix, the JSON Schema
keywords `fixtures/validate.py` silently ignores, and why `dist/` is
regenerated rather than edited.

For a security problem — including a clause that cannot be satisfied securely,
or two that contradict each other — see [SECURITY.md](SECURITY.md) and please
do not open a public issue. Participation is covered by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache 2.0 — see [LICENSE](LICENSE).
