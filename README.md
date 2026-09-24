# Agent Mailbox Access Protocol (AMAP)

A versioned wire contract for sandboxed AI agents to participate in email
workflows through a trusted runtime that **does not trust the agent or its
connector**.

AMAP separates **participation in a workflow** from **authority to act**. It is
carried over a filesystem namespace and is deliberately independent of either
implementation: a trusted mail runtime implements one half, an untrusted
per-agent connector implements the other, and the two can be built by different
people and versioned independently.

**Current version: 3.1.0 (DRAFT)** (wire `contract_version` `"2"` - the contract's
own SemVer and the wire major track different things as of 3.0.0; see
the draft's Versioning and Conformance section, 11).
Conformance gate: **89 fixtures**, 0 unexpected.

## Motivation

**Agents need to participate in existing workflows, not just acquire
mailboxes.** Email carries requests, decisions, approvals, exceptions, and
handoffs between people and systems. It is a component of many enterprise
workflows and, in some cases, their entire backbone. That includes both defined
processes and ad hoc collaboration.

As agents are introduced into these workflows, people and agents need to work
alongside one another without moving every interaction to a new platform.
Participation must remain subject to the organization's security, information
handling, compliance, and approval requirements. The goal is useful automation
without delegating control of those requirements to the agent.

This extends beyond a single organization. A buyer's agent might request a
delivery update from a supplier's employee. The supplier could later introduce
its own agent for routine replies, while people continue to approve exceptions
and changes to commercial commitments. This is an illustrative adoption path:
human-to-agent and agent-to-agent interaction can coexist in the same business
relationship.

**Email allows participation to evolve independently on each side.** A
counterparty receiving ordinary email need not implement AMAP or adopt the same
agent platform. An organization can introduce an agent into an approved email
workflow while its counterparty continues to use people. The intended adoption
advantage is less coordination between organizations, not the elimination of
identity, authorization, or operational requirements.

AMAP is an effort to define a shared boundary for this emerging use case before
incompatible, deployment-specific interfaces become entrenched. It does not
presume widespread cross-company agent adoption or settled requirements. A
versioned contract and shared conformance artifacts provide a basis for
independent implementation, security review, and learning from deployment
experience.

## The problem

An agent is an untrusted process: it can be prompt-injected, buggy, or
compromised. Connecting it to an existing workflow does not make its decisions
trustworthy. Email access introduces three related risks:

- **Inbound** mail can carry untrusted content and prompt-injection attempts
  into the agent's reasoning.
- **Outbound** mail can disclose information or misuse a sending identity.
- **Credentials** available to the agent can be leaked or abused.

The important boundary is not whether the agent can compose a message. It is
whether it can authorize that message, choose the identity under which it is
sent, or bypass policy. Those decisions need to remain outside the agent and
the connector acting on its behalf.

Deployment-specific integrations can enforce such a boundary, but without a
shared contract, independent runtimes and connectors have no common interface
or conformance baseline. AMAP specifies that interface without requiring the
two implementations to share code, ownership, or release cycles.

## The approach

Interpose a **trusted runtime** that holds mail credentials, controls the
sending identity, and applies policy. The **untrusted agent and connector**
interact with it through a filesystem namespace containing inbound deliveries,
outbound requests, and results.

An outbound submission is an inert request file, not an authorization to send.
The runtime validates the request and decides whether anything is sent, to
whom, and how. Where policy requires human review, the request remains subject
to that review rather than becoming an agent-authorized action.

> **The invariant:** enforcement of the runtime's mail-authority boundary does
> not depend on the agent or connector behaving correctly. A request file
> cannot, by itself, grant permission to send, change the sending identity, or
> bypass runtime policy.

The filesystem namespace gives that boundary a concrete enforcement mechanism:
access to inbound content can be read-only, while outbound submissions are
untrusted data for the runtime to validate. The security boundary depends on
correct isolation, filesystem access controls, and runtime enforcement, not on
the mere fact that a request is stored in a file.

A compromised agent can still submit requests that policy permits. AMAP does
not establish that their content or business purpose is correct, nor does it
make all delivered content safe. The contract separates authority from agent
behavior; deployments remain responsible for the policies and controls under
which actions are allowed.

## What AMAP is not

- **Not a mail transport.** It neither defines nor replaces SMTP or IMAP, and
  composes with provider-side infrastructure rather than displacing it. The
  AMAP interface is between a runtime and its agent connector, not between
  the mail systems of two companies.
- **Not an agent-to-agent RPC.** It is not a replacement for direct
  agent-interaction protocols such as A2A. AMAP governs an agent's access to
  email; it does not define a remote task-execution protocol. Email-based
  workflows and direct agent integrations can be used alongside one another.
- **Not a policy language.** What a runtime's policy *decides* is out of scope;
  the wire defines the request and verdict shapes.
- **Not an automatic trust relationship.** An external agent remains an
  external counterparty. AMAP support does not, by itself, grant access to
  information or authority to make business commitments.
- **Not a compliance guarantee.** The interface is intended to support
  policy-governed participation. Compliance depends on the applicable
  requirements, runtime implementation, deployment configuration, and
  operating practices.

## Layout

```
draft/draft-amap.xml  the normative prose, as an IETF Internet-Draft - actors,
                      invariant, directory layout, message shapes, correlation,
                      versioning; hand-edited, and the source of dist/
schemas/              JSON Schema (2020-12) for each message
fixtures/             golden valid + invalid artifacts, and the validator
dist/                 the draft rendered: draft-amap-00.txt to read, .xml to submit
spec/contract.md      FROZEN - the prose the draft was reconciled against
spec/peer-origin.md   the peer-origin profile (DRAFT), canonical for the peer lane
```

The Internet-Draft (`draft/draft-amap.xml`), together with `schemas/` and
`fixtures/`, is the normative contract. Read it as `dist/draft-amap-00.txt`.
The JSON the draft shows is written into it from `schemas/` and `fixtures/`,
never copied by hand, and the build fails if the two ever differ.

Run the conformance gate - no counterpart, no network, no dependencies:

```
python3 fixtures/validate.py
```

## How changes reach the spec

Changes enter from two ends - implementations propose against `schemas/` and
`fixtures/`, and the Internet-Draft is hand-edited by a standards editor whose
edits are canonical. The two directions have different rules, and `make -C
draft` enforces both. See [WORKFLOWS.md](WORKFLOWS.md).

## How conformance works

**The fixtures are the other side.** A connector proves conformance by passing
them; a runtime proves it the same way. Neither needs the other present, which
is what makes independent implementation practical.

Two rules govern change:

- **A capability change starts here** - a PR against `schemas/` +
  `fixtures/` + the draft's prose, *before* either side builds it. Neither a runtime
  nor a connector may invent a wire field locally.
- **Additive changes imply a minor bump; breaking a fixture implies a major
  bump**, taken deliberately by both sides. A version mismatch fails closed; it never
  silently mis-parses. As of 3.0.0 this splits into two axes - see the draft's section 11:
  the *wire* major (`contract_version`) tracks envelope-shape compatibility,
  while the contract's own SemVer tracks the fuller set of obligations on
  both sides.

Some obligations are behavioral rather than wire-shaped - for example, that a
connector must not require write access to the inbound tree. Those sit outside
the fixture gate by construction, and the draft's Conformance section (11.3)
names the operational check for each. `fixtures/validate.py`'s docstring lists what a green run does *not* prove.

## Status

Implemented on both sides and exercised end to end: sandboxed agents exchange
mail over this contract, including attachments whose size and digest the
runtime verifies itself. A reference runtime implementation exists
separately, deliberately minimal - it carries no mail stack of its own, so
the obligations this contract places on a runtime are visible without one
around them.

The contract remains a draft. Review and implementation experience are welcome,
particularly on the trust boundary, independently enforced obligations, and
interoperability between separately developed runtimes and connectors.

The version history is the draft's Change Log; the history before 2026-09-24
is in the frozen `spec/contract.md`, section 7.

## Contributing

A capability change lands as `schemas/` + `fixtures/` + the draft's prose in one change,
**before** either implementation builds it - a schema change without a fixture
is the one PR that cannot be merged, because the fixtures *are* the other side.
[CONTRIBUTING.md](CONTRIBUTING.md) explains that and the traps that are
invisible from outside: schema selection by filename prefix, the JSON Schema
keywords `fixtures/validate.py` silently ignores, and why `dist/` is
regenerated rather than edited.

For a security problem - including a clause that cannot be satisfied securely,
or two that contradict each other - see [SECURITY.md](SECURITY.md) and please
do not open a public issue. Participation is covered by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache 2.0 - see [LICENSE](LICENSE).
