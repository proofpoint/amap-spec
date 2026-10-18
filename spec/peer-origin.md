# amap-spec — peer-origin profile, v3.1.0 DRAFT

> **FROZEN, 2026-10-18. Superseded by the Internet-Draft
> [`draft/draft-amap.xml`](../draft/draft-amap.xml), section "The Peer-Origin
> Profile (Optional)".** The draft is now the canonical prose for the peer lane,
> as it already was for the core contract (`spec/contract.md`, frozen
> 2026-09-24). This file is kept unchanged below as the record of the text the
> draft's profile section was written from: section 5 revision s5-r4. **Do not
> edit it.** A change to the profile goes into the draft XML, and into
> `schemas/` and `fixtures/` if a shape or an acceptance rule moves
> (`WORKFLOWS.md`).
>
> The draft carries changes this file does not: the statement and control id
> grammar narrowed to `^[A-Za-z0-9_][A-Za-z0-9_-]*$` (this file's §5.1 accepts a
> leading `-`); canonical point decoding before the small-order check (§5.7);
> the 12288-octet limit counted on the field body as transmitted (§5.2); Fmax
> after the loss of H taken from retained F history if provable, else 900
> (§5.5); intake division an implementation choice (§5.10); and the delivery
> failure notice's runtime address spelled `amap.router` (this file's §4 says
> `amp.router`); and the revision label is gone, so an implementation names the
> draft revision it implements instead of an s5 revision. The draft's "Historical Background" appendix records them.
>
> Where each section went, by the draft's section names:
>
> | This file | Draft section (under "The Peer-Origin Profile (Optional)") |
> |---|---|
> | §0 Scope | Scope; the RPC line is also in Non-goals |
> | §1 The `peer` tree | The Peer Tree |
> | §2 Origin class follows the tree | Origin Class Follows the Tree |
> | §3 Addressing | Addressing |
> | §4 Correlation and results | Correlation and Replies |
> | §5 Cross-host: signed peer traffic | Peer Traffic Between Hosts |
> | §5.1–§5.10 | The Statement; Carriage, and the Candidate the Verifier Sees; Verification; Outcomes; The Replay Store, Windows and Recovery; Correlation and Edges Between Hosts; Keys; Control Notices; Optional: Sender Age, and Deployment Admission Policy; The Intake Location |
> | §6 `sender_exposure` | Sender Exposure |
> | §7 Delivery outcomes, retention, deletion, presentation | Delivery Outcomes, Retention, Deletion and Presentation |
> | §8 Conformance | Versioning and Conformance: Conformance (the peer-origin sub-classes); the Conformance Suite appendix |
> | §9 Required vs. optional | Versioning and Conformance: Required versus optional |

An **optional profile** of the volume contract (`spec/contract.md`, "core").
It gives same-principal agent-to-agent traffic its own inbound tree, `peer/`,
and states what that tree asserts, who may write it, how peers are addressed,
how a result is correlated to the request it answers, and how peer traffic is
carried and verified between hosts. A deployment that implements it is bound
by every MUST below; a deployment that does not is unaffected — no core
schema or fixture changes, and wire `contract_version` stays `"2"`.

Normative language follows core: MUST / MUST NOT / SHOULD / MAY. Where this
file and core disagree, core wins and this file has a bug. Section numbers
below are the ones `schemas/peer-notice.schema.json` and
`fixtures/validate.py` cite.

Status: drafted 2026-09-15 from the profile rulings of 2026-09-02/03, against
`schemas/peer-notice.schema.json` and the `peer-*` fixtures as they stood on
`main` at that date. v3.1.0 stays DRAFT.

---

## 0. Scope, and the line it does not cross

**Why a profile and not core.** AMAP is a mailbox contract and says it is not
agent-to-agent RPC. Peer origin is wanted by one connector today and is not
needed by any mail-only deployment. So: optional, normative for those who
implement it, invisible to those who do not.

**Why not vendor space.** Nothing on this wire names a harness. The runtime
half — routing on a declared edge, signing, the intake location, stamping
exposure — cannot be one connector's private convention without the runtime
ceasing to be agent-agnostic, and the normative rule the profile exists to
state (origin class follows the tree; write authority per tree) cannot be
stated about a tree the spec does not name.

**Name the tree for the assertion, not the use.** The tree is `peer/`, the
kind is `peer`. The tree says "authenticated same-principal peer origin";
what a connector does with that (delegation, review, notification) is the
connector's. Because kind and tree share a name, the second lock (§1) is
literally "kind equals tree name".

**The RPC line.** This profile adds an origin class and reuses mail threading
for correlation. It defines **no** call or return semantics, no method or
operation field, and no status vocabulary for the work itself: a result is
prose authored by an agent, with the posture of any peer content. A future
proposal that wants any of those is no longer mail and should be declined at
that point, not absorbed here.

**Core additions this profile relies on** (both generic, both in
`spec/contract.md` §2): the *tree rules* — every runtime-owned inbound-class
tree is an origin class, class is derived from the tree and never from a
member, `notice_id` uniqueness and `content_ref` confinement are per tree,
write authority per tree is distinct and structurally enforced; and the
*outbound extension space* `outbound/ext/<name>/`, the connector-owned side
channel where delivery outcomes live (§7). There is deliberately no inbound
extension space.

## 1. The `peer` tree

```
<agent-id>/
  outbound/                        # core, unchanged (ext/<name>/ is core §2)
  inbound/                         # core: mail
    notices/  messages/
  peer/                            # PROFILE — same layout, conventions and sidecar rules as inbound/
    notices/notice-<id>.json
    notices/<notice-id>.attachments/<i>
    messages/notice-<id>.json
  audit/
```

**1a. A sibling of `inbound/`, never a child.** Nesting the peer tree under
the mail tree would put the tree the mail deliverer must *not* write inside
the tree it must write, so the partition (§2) would have to be carved out of
a mount instead of being one. A sibling makes the write-authority rule
coincide with mount granularity. Every `inbound/` obligation in core extends
to `peer/` verbatim: runtime-owned; MAY be mounted read-only; a connector
MUST NOT require write access to it; deletion by the runtime only; retention
conservative and age-based.

**1b. Its own schema, so the change is additive.** Core §7 closes `kind` and
makes a new value MAJOR; that protects a consumer reading a document whose
`kind` it does not know. A `peer` notice appears only in a tree a core
consumer never reads, and `schemas/deliver-notice.schema.json` is
byte-identical to before, so the rule is satisfied by construction:

- `schemas/peer-notice.schema.json` is deliver-notice with `kind: "peer"`
  and `message.mailbox: "peer"` as constants, `message.from` pinned to a bare
  addr-spec (§3), `message.id` / `in_reply_to` / `references[]` pinned to the
  `notice_id` charset (§4), and the optional runtime-asserted
  `message.sender_exposure` (§6). Attachments are byte-identical to core §5.
- The body spool reuses `schemas/inbound-message.schema.json` unchanged.
- **The second lock.** A `deliver` document under `peer/notices/` fails the
  peer schema; a `peer` document under `inbound/notices/` fails the
  deliver-notice schema. Both are dropped under core §5's drop rule.
  Fixtures `invalid/peer-kind-deliver.json`, `invalid/peer-mailbox-inbox.json`
  and `invalid/notice-kind-peer.json` pin the three legs.

**1c. `notice_id` is per tree; the placer mints.** The component that
*places* a notice into a tree mints its `notice_id`. Where a tree has more
than one writer, each MUST mint so that cross-writer collision is negligible
(≥128 bits of entropy under the core §7 charset, or a writer-specific prefix).
A consumer that keys state across trees MUST include the tree in the key.
Same-host, a runtime MAY make `notice_id` equal the peer message id (§4);
cross-host they differ, because the receiving runtime mints `notice_id` and
`message.id` is the sender's. **A consumer MUST NOT assume they coincide.**

**1d. `content_ref` confinement is per tree.** Bytes resolve only within the
`notices/` directory of the tree the enclosing document was read from,
recomputed from that document's `notice_id` and the descriptor index. A peer
notice cannot point into the mail sidecar directory or vice versa.

**Advisory members.** `provenance` on a peer notice is redundant with the
tree and MAY be omitted; if present it is advisory and is never grounds to
derive or override origin class. `sender_standing`, if set, SHOULD be the
existing `agent-tier` value.

## 2. Origin class follows the tree, never a field

Core already carries three obligations of this type — behavioural, invisible
to a document validator, checked operationally: read-only inbound tolerance
(v2.2.0), single-writer / single-drainer (v3.0.0), ingest-by-copy (v3.0.0).
Write authority per tree is the fourth. Leaving it to deployments would make
the separate tree decorative: one writer choosing the tree by inspecting a
field is field-routing with one indirection. The *mechanism* (uid, mount set,
host boundary) is out of scope; the *property* is not, and the write probe is
the prescribed check.

**Reader side — connector obligations.**

> The tree a notice is read from is the runtime's sole assertion of its
> origin class: `inbound/` is mail; `peer/` is same-principal peer origin. A
> connector MUST derive the class from the tree and MUST NOT derive it, or
> override it, from any member of the document. `kind` MUST equal the tree
> name; a disagreement is dropped under core §5's drop rule. A connector that
> cannot establish which tree a document came from MUST treat it as mail.
>
> The peer tree asserts *authenticated origin* — a same-principal agent,
> reaching this namespace through a path restricted to authorised peer
> senders. It asserts nothing about the content: peer content is
> peer-authored and unscreened, and may paraphrase external mail (§6). What
> treatment a connector gives each class is connector semantics, out of
> scope; that it distinguishes classes only by tree is not.

This is the bucket core §2 already names: an obligation that protects an
agent from its own inbox is connector-implemented and stated as such, not a
safety property the runtime relies on. Core's §1 invariant is untouched.

**Writer side — runtime obligations.**

> **Write-authority partition.** Write authority over `peer/` MUST be
> distinct from write authority over `inbound/`. Any component that admits
> messages from a transport not restricted to authorised peer senders (the
> *admitting component*; a mail deliverer is the canonical case) MUST NOT
> hold write authority over `peer/`. The restriction MUST be structural —
> never configuration the component reads — and the prescribed operational
> check is a write attempt from inside the admitting component against
> `peer/`, which MUST fail. The rule is one-directional: a component holding
> peer write authority MAY write `inbound/` (the demotion branch, §5).
>
> A runtime MUST NOT write a notice into `peer/` on the basis of any claim
> the message makes about itself. It MAY write there only when the message
> arrived through a path whose write authority is already restricted to
> authorised peer senders, or when it carries a signature that verifies
> against a configured peer key (§5).
>
> **Verification placement.** Verification MUST be performed by a component
> holding peer write authority, receiving candidates through a location that
> is neither tree (§5's intake). The admitting component MUST NOT perform
> verification: a verdict computed by one component and acted on by another
> crosses a trust boundary as a field, and a field is what this rule exists
> to keep out of the decision; and the verifier processes hostile input, so
> it must be the component whose write authority the outcome concerns, not
> one that parses raw mail.

## 3. Addressing

**A peer address is a bare addr-spec** under the pattern core §3 already
pins for `draft.to` — same grammar, same exclusions, no display name. Local
part = the agent's name within its runtime; domain = the runtime's authority.
Same-host deployments with no mail MAY use a non-routable domain; cross-host
requires a routable one, because cross-host peer traffic is mail (§5).
Routable means deliverable by the mail system that carries the deployment's
peer traffic; it need not be resolvable in the public DNS, because peer keys
are configured, not looked up (§5). A peer domain MUST belong to exactly one
runtime among those configured as peers, so a deployment that may peer
across organisations should use domains it owns. Where
an agent has a bound mailbox (`identity.json`'s `address`) the deployment
SHOULD use it, so an agent has one identity on both lanes.

Why this and not opaque ids with a directory, or a URI scheme: cross-host
the transport address *is* an email address, and any other scheme needs a
mapping onto one plus someone to run the directory — the PKI-lite problem §5
refuses; with addr-spec the domain names the authority, and the peer-key
table is keyed by domain, which gives a signature something to bind. The
grammar, schema pattern and header-injection discipline already exist and
are mechanically evaluable.

**The sending side costs zero new wire shape.** A sending agent writes an
ordinary core §3 submit-request whose `draft.to` names the peer; the
runtime's recipient policy recognises a declared edge and routes it to the
peer tree rather than to mail. Existing result vocabulary, existing sidecar
attachments, existing reply key. Whether a recipient is a peer is runtime
policy, out of scope — like allowlists today.

**`message.from` on a peer notice is the one `from` in the protocol a
consumer may treat as authenticated origin.** Bare addr-spec, schema-pinned,
asserted by the runtime from the restricted write path or the verified
cross-host statement, never copied from sender text. This is the opposite of
core §5's rule for mail `from`, which core §5 now cross-references. A
connector's sender check keys on it; that is sound because the runtime
asserted it.

**A configured peer key vouches only for its own domain(s)** (§5). Without
this, one runtime's key could sign a message claiming an address in another
runtime's domain.

**One address resolves to exactly one namespace** (`<agent-id>/`). That is
already AMAP's model: one namespace, one connector instance, one agent.
Sessions are below the connector and the spec does not know what one is.

> A peer message is a single unit addressed to one agent. A connector MUST
> NOT cause it to be acted on more than once. A connector that cannot
> identify a single target MUST hold the notice, not fan it out, and SHOULD
> report the condition through its own side channel (§7).

"One agent, one live session; refuse when several" is a conformant
implementation, not the only one. Finer (a named session) is out of scope.
Coarser (a pool) is a runtime alias expanding to several addresses, each
resolving to one namespace — not an addressing change.

## 4. Correlation and results

**The peer message id.**

> The peer message id is minted by the sending runtime on accepting the
> submit. It MUST be globally unique and unguessable (at least 128 bits of
> entropy) and MUST be spelled under the `notice_id` charset
> (`^[A-Za-z0-9_][A-Za-z0-9_.-]*(?!\n)$`). It has exactly one spelling inside
> every AMAP document: `notice.message.id`, `notice.message.in_reply_to`,
> `notice.message.references[]`, `result.message_id` on a peer-routed result,
> and the reply key a sender submits all carry the bare id. When the id is
> carried in a mail header it is encoded as `<id@domain>`, `domain` being the
> sending runtime's authority; the encoding is applied on the way into the
> header and removed on the way out, and never appears in an AMAP document.

The two properties the reverse edge and every ledger depend on are
unguessability and one spelling end to end; "Message-ID-shaped" was a
transport detail of the mail hop and is not part of the wire. Bare 32-hex
fits; so does base64url without padding. Fixtures
`invalid/peer-message-id-encoded.json` and
`invalid/peer-in-reply-to-encoded.json` carry the encoded form and fail.
Nothing changes in `deliver-notice.schema.json`: a *mail* notice's
`in_reply_to` stays an RFC 5322 identifier.

**A result is a `peer` notice in the reverse direction, on the same tree,
correlated to the request.** Not a third kind or tree: the tree grants the
class, and a result deserves the class of the request it answers. There is
no `correlation_id`; the mail-threading triple already exists, and cross-host
it *is* RFC 5322 threading:

| field | on a peer notice |
|---|---|
| `notice.message.id` | the peer message id |
| `result.message_id` (sender's submit result) | MUST equal the peer message id, so the sender learns it from its own result; `reason_code` SHOULD be `peer_routed` so the sender can tell the lanes apart (open vocabulary, core §4) |
| `notice.message.in_reply_to` | REQUIRED on a result; equals the id being answered. A fresh task omits it |
| `notice.message.references[]` | multi-step threads, as in mail |
| submit `in_reply_to` / `draft.reply_to_message_id` | how a responder names the message it answers |

`task_id` stays an optional runtime-minted thread handle.

**Reverse edges.** The authorisation graph is directed; a result must flow
B→A when only A→B is declared. The runtime permits a reverse message when
the reply key names a peer message *it issued or placed* within a configured
window. That consults a field, but against state the runtime minted — the
posture core §6 takes for threading: correlation, not trust. Unguessable ids
keep this from being a forgeable capability. Several replies to one id
within the window, and reply-to-reply on the id the runtime issued for the
reply, are conformant; the profile does not fix the window's length, only
that it exists and is configured.

**Unresolved reply keys are refused, never stripped.**

> A reply key (`in_reply_to`, else `draft.reply_to_message_id`) that the
> runtime cannot resolve from its own ledger is `rejected`
> (`reason_code: unresolved_reply`). A runtime MUST NOT strip the key and
> route the message on `draft.to` as a fresh peer message. A resolved key
> whose reverse edge is not permitted (no declared edge, window expired) is
> likewise `rejected` (`peer_reply_window_expired` or the runtime's own
> code), never re-routed. **Invariant: a peer notice carries `in_reply_to`
> iff the placing runtime resolved it from its own ledger** — a peer message
> id it issued or placed.

The reason is the reason this profile exists: on the peer lane, a message the
sender meant as a result that the runtime quietly turned into a fresh task is
injected as a new instruction, which is worse than a rejection the sender can
act on by resubmitting without the key. The invariant is a MUST rather than a
permission because a connector may build policy on it — admitting a
*replier* it would not otherwise accept — and that is sound fleet-wide only
if every conformant runtime upholds it. Such a policy MUST NOT widen anything
else about the notice's treatment.

Cross-host residual case: the sending runtime already rejected an
unresolvable key at submit time, so a verified statement whose `in_reply_to`
the *receiving* runtime cannot resolve indicates a stale or forged capability
from a configured peer. The receiver MUST NOT place it in `peer/` with the
key, MUST NOT place it as a fresh peer task, MUST log the cause, and SHOULD
tell the sending runtime with a signed control notice (§5.8). The ledger
binds the participants, not just the id (§5.6). It is not demoted to mail
either: origin verified, only the correlation claim failed, and "route as
mail" would be a third silent transformation.

**Two things called "result", kept separate.** *Work result*: the
responder's content to the requester, above. *Delivery outcome*: mechanical,
connector → runtime (`delivered`, `held`, …). The second is not a peer
message; it is connector feedback and lives in `outbound/ext/<name>/` (§7).

**The DSN analogue.**

> A runtime that surfaces a terminal delivery failure to the sending agent
> SHOULD do so as a `deliver` notice in the sender's `inbound/` tree, with
> `message.from` the runtime's own address (`amp.router@<domain>` or
> equivalent), `in_reply_to` the peer message id, and a runtime-authored
> body only. It MUST NOT be placed in `peer/`, and it MUST NOT quote or
> forward any text from the receiving connector's outcome file.

The runtime is never an allowed peer sender, so this keeps it out of every
connector's peer policy; the mail tree's untrusted-content framing is the
right framing for "your message did not arrive"; and the outcome file is
receiver-authored text, so forwarding it would let one agent put prose in
front of another under the runtime's framing. A component holding peer write
authority writing `inbound/` is the one direction §2 permits. The peer id
appears in a mail-tree notice, but only to the sender who already holds it
from its result, so no capability is disclosed.

## 5. Cross-host: signed peer traffic

Cross-host peer traffic is mail. The sending runtime signs; per-agent keys
are not used. Same-host traffic needs no signature, because local write
permission is stronger, though a same-host runtime MAY sign for a uniform
code path without changing treatment. A receiving runtime places a cross-host
message in `peer/` only when every rule below holds. Otherwise it hands the
message to mail admission, drops it, or refuses it, as §5.4 says.

*Status: proposed, not yet reviewed by the editors. This is §5 revision
**s5-r4** (2026-10-10). It, `schemas/peer-statement.schema.json`,
`schemas/peer-control.schema.json` and `fixtures/peer-signed/` are one
revision. An implementation names the revision it implements.*

### 5.1 The statement

The sending runtime builds a *statement*, a small JSON object, signs its
exact bytes with Ed25519 (RFC 8032 §5.1), and ships the bytes and the
signature in one header field (§5.2). The receiver verifies the signature
over the bytes it received *before* parsing them. Nothing is ever
re-serialised: no canonicalisation is defined, and any serialisation the
sender chose is the one that is signed.

`schemas/peer-statement.schema.json` pins the statement, `v: 1`, CLOSED at
every level:

```
v, key_id, kind ("peer"), id, in_reply_to (optional), from, to, ts, subject,
body_sha256,                       # §5.2: the body the receiver will publish
attachments: [{sha256, size_bytes, filename, media_type}, ...],   # in leaf order
sender_exposure (optional),        # §6
sender_since (optional)            # §5.9
```

The statement is closed, unlike the runtime-authored notices (core §7),
because these are signed bytes another runtime acts on. A member the receiver
does not know is a member it cannot bind to what it publishes, and `v` is the
evolution path. The schema states the shapes. These rules, which JSON Schema
cannot express, are also part of the statement:

- **Formats.**
  - `ts`, `sender_since` and the `sender_exposure` timestamps are RFC 3339
    UTC in whole seconds with `Z`, and each MUST be a real instant.
  - Digests are SHA-256, lower-case hex.
  - Every number is a lexical integer: no fraction, no exponent, so `1.0`
    is not `1`.
  - No string contains an unpaired surrogate (RFC 8259 §8.2).
- **Ids.** A sending runtime MUST mint peer ids under `^[A-Za-z0-9_-]+$`
  (hex or base64url, at least 128 bits, §4), so that `<id@domain>` is a
  valid msg-id (RFC 5322 §3.6.4). The statement schema enforces this for
  `id` and `in_reply_to`. Same-host notices keep §4's wider charset.
- **`to`** is one address: a peer message is addressed to one agent (§3).
- **`sender_exposure`** obeys §6:
  - `window_start` ≤ `window_end`;
  - `last_external_delivery_ts` is present if and only if
    `external_mail_delivered` is `true`, and then lies within the window;
  - `asserted_by` is the signing runtime's configured runtime address
    (§5.7).
- **`sender_since`**, when present, is not later than `ts`.

### 5.2 Carriage, and the candidate the verifier sees

**The header field.**

```
AMAP-Peer-Statement: k=<key_id>; s=<statement>; b=<signature>
```

- **`s` and `b`.** `s` is the statement's bytes and `b` is the 64-byte
  signature over exactly those bytes. Each is base64url without padding
  (RFC 4648 §5).
- **`k`** is the statement's `key_id`, in the clear. The receiver verifies
  before it parses, so it must choose the key before it can read the
  statement. The signed `key_id` MUST equal `k`.
- **Field name.** It is matched case-insensitively. The sending runtime
  MUST emit exactly one such field.
- **Folding.** The sender MUST fold the field so that no line exceeds 998
  octets (RFC 5322 §2.1.1), and SHOULD fold at 78. It may insert folding
  whitespace anywhere, because the receiver removes all of it.
- **Size.** A statement MUST NOT exceed 8192 bytes. A sending runtime MUST
  NOT emit a larger one. It SHOULD refuse the submit instead, with a
  `rejected` result whose `reason_code` is `peer_statement_too_large`.
- **Threading headers.** The sending runtime MUST also set `Message-ID` to
  `<id@domain>`, where `domain` is the domain of `from`, and SHOULD set
  `In-Reply-To` and `References` to the encoded forms (§4). That way mail
  threads coherently, and a demoted message still threads as mail.

**The message shape.**
- A sending runtime SHOULD send either a single `text/plain` part or
  `multipart/mixed` holding one `text/plain` part followed by the
  attachments.
- The text part SHOULD be `charset=utf-8` with base64 transfer encoding, so
  that transport cannot rewrite it.
- The sender hashes the UTF-8 encoding of the body after replacing every
  CRLF pair with LF. Nothing else is normalised: a bare CR, a bare LF,
  trailing whitespace and a leading dot are all content.

**The selection rule.** The admitting component reduces a message to a
candidate, and the rule is the same at every receiver:
- **Leaves.** Walk the MIME tree depth-first, descending only into
  `multipart/*`. Every other part is a leaf, including `message/rfc822`,
  whose octets are its part body as transmitted.
- **Body.** The first leaf of type `text/plain` whose `Content-Disposition`
  is not `attachment` is the body.
- **Attachments.** Every other leaf, in walk order, is an attachment: a
  `text/html` alternative, an inline image, a second `text/plain`.
- **No body leaf** means the empty body.

A different structure is not forbidden. It is simply likely to fail the
attachment count or the body digest, and so to be demoted.

**The candidate** (the content §5.10's intake MUST hold; its layout is not
prescribed):
- **Field bodies.** The body of each `AMAP-Peer-Statement`,
  `AMAP-Peer-Control` and `Message-ID` field, in message order. The admitting
  component MAY unfold a field body or trim its surrounding whitespace, and
  MUST NOT otherwise alter it. A field body over 12288 octets is carried as
  an *oversize* marker, never truncated. A field body it cannot carry as
  ASCII text (a non-ASCII octet, an undecodable value) is carried as an
  *invalid* marker in the field's position. A marker keeps the field's
  identity and multiplicity: the admitting component MUST NOT drop a field,
  because dropping a second malformed statement field would leave one
  well-formed field, and the verifier would select it.
- **The body leaf**, if there is one: its transfer-decoded octets, and the
  value of its `charset` parameter, if any.
- **Each attachment leaf:** its transfer-decoded octets, in order.

The verifier, never the admitting component:
- decodes the body octets strictly. The charset label (case-insensitive)
  MUST be `utf-8` or `us-ascii`; an absent label means `us-ascii`. Any
  other label, or octets invalid in the label's charset, fail check 9;
- replaces CRLF pairs with LF;
- hashes what results, and that same text is what it publishes as
  `body_text`.

**What is published.** On placement, the receiver takes all of the
following from the verified statement, and never from headers:
- `message.id`, `in_reply_to` and `from`;
- `subject`;
- `sender_exposure`;
- the attachment descriptors' `filename`, `media_type`, `size_bytes` and
  `sha256`.

`to` selects the namespace. The receiver MUST NOT publish `references` from
headers. It MAY derive them from its own ledger (§5.6). Core §5's sniffing,
caps and `disposition` still apply to the attachment bytes.

**Comparisons.**
- **Addresses** (`from`, `to`, the edge graph, the ledger, runtime
  addresses) compare the local part exactly and the domain ASCII
  case-insensitively.
- **Ids** compare exactly, because they are opaque.
- **`Message-ID`.** After unfolding and trimming, it MUST be exactly
  `<` id `@` domain `>`, with the id equal to the statement's `id` and the
  domain equal to the domain of `from`.

**Logging.** A receiver MUST NOT log a raw header field value unescaped.
Fields are attacker-supplied, and `k` is validated against the `key_id`
pattern before it is used for anything.

### 5.3 Verification

The receiver applies these checks in this order. The first one that fails
decides the outcome (§5.4). Only a candidate that passes every one is
eligible for `peer/`.

1. **The field.**
   - Exactly one `AMAP-Peer-Statement` field (none: not a peer candidate,
     ordinary mail). A message that also carries an `AMAP-Peer-Control`
     field is dropped (§5.8).
   - The field body is ASCII and not oversize.
   - With every SP, HTAB, CR and LF removed, it is exactly the tags `k`,
     `s` and `b`, each once, in any order, separated by `;`.
   - `k` matches the `key_id` pattern.
   - `s` and `b` are unpadded base64url; `b` decodes to 64 bytes, and `s`
     to at most 8192.
2. **Known statement.** If SHA-256 of the statement bytes equals that of a
   statement the receiver has recorded and still retains (§5.5), the
   candidate is a duplicate. This check needs no key and holds whatever
   else has since changed: a timestamp now outside the window, a key since
   expired or removed, a body modified in transit.
3. **Key.** `k` names exactly one configured key, valid at the receiver's
   clock (not-before ≤ now ≤ not-after, inclusive).
4. **Signature.** It is valid for that key over the received bytes, under
   §5.7's verification policy.
5. **Statement.**
   - (a) The bytes are UTF-8 without a byte-order mark, and parse as JSON
     with no repeated member name and no non-JSON constant. They validate
     against the schema, and `key_id` equals `k`.
   - (b) Every rule of §5.1 that the schema cannot express holds.
6. **Key domain.** The domain of `from` is one of the domains configured for
   the runtime that owns the key. A key vouches only for its own runtime's
   domains (§3).
7. **Freshness.** `ts` lies within §5.5's window. While peer admission is
   closed (§5.5, no trustworthy bound) the window is undefined: the
   candidate is *held* in intake, undisposed, until admission reopens.
8. **Exposure asserter.** If `sender_exposure` is present, `asserted_by` is
   that runtime's configured runtime address.
9. **Body.** The body decodes under §5.2's charset rule, and its digest
   equals `body_sha256`. The verifier hashes bytes it holds itself, never a
   digest the admitting component computed.
10. **Attachments.** The count matches. Then, for each one in order,
    `sha256` and `size_bytes` match the octets.
11. **`Message-ID`.** Exactly one field, matching §5.2.
12. **Reservation.** No record exists for (the configured runtime that owns
    the key, `id`) (§5.5). The candidate is reserved, atomically.

A reserved candidate is then *decided*, and these are not verification
failures:
- if `to` is not hosted here, it is misrouted;
- if `in_reply_to` is present, it must resolve and be permitted (§5.6);
- otherwise the receiver's own graph must have the edge `from` → `to`
  (§5.6);
- any deployment admission policy is applied (§5.9);
- otherwise the decision is placement.

The decision is persisted on the record before it has any effect (§5.5).
Only a persisted placement decision is ever published; a persisted refusal
or drop is never published, whatever happens afterwards.

### 5.4 Outcomes

| outcome | when | control notice (§5.8) |
|---|---|---|
| `peer` | every check passes, and the message is routed and permitted | — |
| held | check 7 while peer admission is closed (§5.5): not disposed of yet | — |
| mail, no statement | no `AMAP-Peer-Statement` field | — |
| mail, demoted | a failure of check 1, 3, 4, 5, 6, 7, 8, 9, 10 or 11 | SHOULD, for 5(b) and 6–11 |
| drop: duplicate | check 2 (a known statement) or check 12 (a known `id`) | for check 12 only, SHOULD |
| drop: misrouted | `to` is not hosted here | SHOULD |
| refuse: unresolved reply | §5.6 | SHOULD |
| refuse: no edge | §5.6 | SHOULD |
| refuse: policy | a deployment admission policy (§5.9) | SHOULD, with `policy_code` |

**Mail, demoted.** Demotion is a classification, not a delivery.
- The candidate goes to ordinary mail admission and the deployment's lane
  policy. Where that policy gives the pair no mail lane, it is not
  delivered.
- The demoted notice MUST NOT carry `sender_exposure`, the statement or the
  signature. It carries the mail-admission verdict the admitting component
  attached.
- Mail admission MUST NOT treat an invalid statement as evidence of who sent
  the message.

**Drop and refuse.**
- A dropped or refused candidate is neither placed nor handed to mail
  admission.
- Every outcome other than `peer` and "no statement" MUST be logged with
  its cause.
- A refusal is not demoted, because the origin was verified and only an
  authorisation or correlation claim failed. Routing it as mail would be a
  silent transformation (§4).

**Who is told.** A control notice (§5.8) is sent only when every one of
these holds; a configured `k` alone is never enough:
- checks 1 to 5(a) passed, so the statement is authenticated by a currently
  valid configured key and well-formed enough to name. Before check 4 the
  sender is unauthenticated, so notifying the claimed sender is backscatter;
  between checks 4 and 5(a) the statement cannot be named;
- the candidate was not a check-2 duplicate (an exact retained statement:
  the first copy was already answered, and an on-path replay must not draw
  a second notice);
- the candidate is a statement, not a control notice (§5.8: nothing is ever
  sent about a control notice);
- the destination is the runtime address configured for the key's owner,
  never an address in the message.

A `dropped`/`duplicate` notice (check 12) tells the sender that a record
with that `id` already exists. That record's disposition may have been
placement or refusal: the notice proves a prior reservation, not that the
task failed. Whether the sending *agent* learns of an outcome is the sending
runtime's business (§5.8).

### 5.5 The replay store, windows and recovery

**Windows.** The receiver accepts `ts` when `lower ≤ ts ≤ now + F`, both
bounds inclusive, where `lower = max(H − P, floor)`:
- **F**, the clock skew: default 300 seconds; MUST NOT exceed 900.
- **P**, the past window: default 3600 seconds; MUST be at least 300 and at
  most 86400. A message that arrives later than P is demoted, which is
  legible. A longer P costs replay storage and a longer key retirement
  (§5.7).
- **H** is the latest receiver time ever observed, kept durably. The lower
  bound uses H, not the current clock, so a clock that steps backwards
  cannot re-admit a statement whose record has been pruned.
- **floor** is set only by recovery and by window changes, below.

**Records.** Replay identity is scoped to (configured runtime, `id`). The
runtime is the configured peer that owns the verifying key, so a key
rotation never resets it. Each record holds:
- the scope, `id` and `ts`;
- SHA-256 of the statement bytes;
- the `notice_id` minted at reservation;
- a state, `reserved`, `decided` or `done`;
- once decided, the **disposition**: placement, or a refusal or drop with
  its cause (and `policy_code`), and whether a control notice is still
  pending.

**Recording.**
- The receiver records a candidate at check 12, after every binding check
  has passed. A candidate that fails a binding check records nothing, so a
  mangled copy cannot suppress the intact one that follows.
- Misrouted and refused candidates are recorded too. Their replays are then
  dropped quietly instead of being re-evaluated each time.
- Control notices (§5.8) use the same store.

**Reservation, decision and effect.** Three durable steps, in order, each
atomic:
1. **Reserve.** Check 12 creates the `reserved` record, minting a fresh
   `notice_id`. The candidate stays in the intake location until the record
   is `done`. A reservation is undecided: it authorises nothing.
2. **Decide.** The receiver routes, correlates, permits and applies policy
   (§5.3), and persists the disposition on the record: state `decided`. A
   refusal or drop also marks its control notice pending.
3. **Effect.** For a placement, the notice is written under the minted
   `notice_id`; for a refusal or drop, the control notice is durably queued.
   Only then is the record `done`. Placement is idempotent: a notice that
   is already present is not written again.

- **Concurrent copies.** A copy that arrives while another copy is
  `reserved` or `decided` matches it at check 2 and is dropped.
- **Crash recovery.** On restart, the receiver finishes every record that
  is not `done`, exactly once, by resuming its *recorded* state. It never
  infers a disposition from the absence of a notice:
  - a `reserved` record is decided now, under the configuration in force at
    recovery (the receiver has no older one it can trust), then takes
    effect;
  - a `decided` placement is placed if the notice is absent, and marked
    `done` without placing it again if the notice is present;
  - a `decided` refusal or drop is never published. Its pending control
    notice is queued, once, and the record is marked `done`.
- The crash points an implementation MUST survive are: after reservation,
  after the decision, after a notice is placed, after a control notice is
  queued, and after a terminal refusal is recorded, including when the
  graph or policy changed while it was down.

**Retention.** The receiver MUST retain each `done` record while
`H ≤ ts + P`, and MAY retain it longer. It MUST NOT prune a record that is
not `done`.
- A known statement replayed after its retention has lapsed fails
  freshness, so it is demoted and never placed.
- Duplicate suppression is therefore effective only within retention. The
  profile does not promise exactly-once delivery, and an implementation
  MUST NOT claim it.

**Resending.** A sending runtime whose hand-off was ambiguous MAY resend
the same `id`, re-signed with a new `ts`:
- if the first copy arrived and is retained, the resend is dropped at
  check 12, and the control notice tells the sender so;
- if the first copy did not arrive, the resend is placed.

A sending runtime that resends MUST keep the same `id`, including across a
resend a human approved.

> **The finite-retention consequence.** This MAY is idempotent only within
> retention. Once the first copy's record has been pruned, a resend of the
> same `id` under a fresh `ts` finds no record and **is placed a second
> time** (`seq-resign-after-retention`). A deployment that cannot accept
> that MUST forbid re-signing in its own deployment profile and resend the
> original bytes only, which check 2 drops or freshness demotes. The MAY
> stays for portability, not as a recommendation.

**Recovery.** The store and H MUST survive a restart. Suppose the receiver
loses the store, or cannot show that a restored store is complete. The
barrier it must restore is this: no statement that could already have been
accepted under the lost coverage may be admitted again, including at the
boundary, under a clock that stepped back, and under the largest F that was
ever in effect.
- With H intact, it sets `floor` to one second after `max(C, H) + Fmax`,
  persisted before admission resumes: C is the moment from which it again
  holds complete evidence, H the high-water clock at the loss, and Fmax the
  largest F in effect at any point that could have admitted a statement
  still within the lost coverage, taken from retained F history (900 unless
  that history is provable). Fmax is never chosen from the wall-clock
  interval ending at C: after a clock rollback, that interval can miss a
  larger F in effect near H (`seq-store-loss-rollback-larger-f`). Retaining
  the maximum F ever configured is safe.
  Any statement accepted before the loss had `ts ≤ H + F ≤ max(C, H) + Fmax`,
  so none reaches the floor. The floor is strictly above that bound: an
  inclusive floor re-admits a statement accepted at exactly `now + F`
  (`seq-store-loss-at-equality`), and C alone re-admits one accepted before
  the clock stepped back (`seq-store-loss-after-rollback`).
- With H lost as well, no trustworthy bound exists, and the receiver MUST
  close peer admission: candidates reaching check 7 are held in intake, and
  nothing is placed or demoted on a window it cannot define. Admission
  reopens only when the operator records a bound B that is at or after the
  largest receiver time before the loss; the floor is then one second after
  `B + Fmax`, and the held candidates are evaluated in arrival order
  (`seq-store-loss-h-lost`). Current wall time is not a bound.

**Window changes.**
- Narrowing P or F takes effect at once.
- Widening P MUST NOT re-admit anything. The receiver sets the floor to the
  lower bound in effect at the moment of the change, and the window then
  widens only as records accumulate.

### 5.6 Correlation and edges

**The ledger.** A runtime keeps a record for every peer message it issued
cross-host or placed. Each record holds:
- the id;
- the local agent and the remote agent;
- the direction (`issued` or `placed`);
- an expiry, the configured reply window (§4).

The ledger is scoped to peer messages. A mail notice id never resolves.

**Resolution.** A verified statement carrying `in_reply_to` resolves only
if a record exists that meets all of these:
- the record's id equals `in_reply_to`;
- its local agent equals `to`;
- its remote agent equals `from`;
- it has not expired.

Possession of an id is not authority: another agent on the same host, or
any agent on another host, presenting an id it observed does not resolve.

**Permission.**
- A resolved reply to a record this runtime `issued` is a reverse message,
  and is permitted without an edge (§4).
- A resolved message against a record this runtime `placed` is a follow-up
  in the same direction, and needs the edge `from` → `to`.
- A statement without `in_reply_to` needs the edge.

**The receiver's own graph.** The edge is checked against the receiver's
own graph. The sending runtime checked its edge at submit (§3), but which
peers may task an agent is the receiving runtime's decision.
- If correlation fails, the outcome is refused, unresolved reply.
- If permission fails, the outcome is refused, no edge.
- Neither is demoted.

**At submit.** The sending runtime applies the same binding: a reply key
resolves only if the submitting agent is the record's local agent. It
SHOULD also refuse at submit a message it already knows the receiver will
refuse, such as a pair it knows has no edge or is held by policy, so that
the agent gets a result at once. The receiver remains the authority.

### 5.7 Keys

**Configuration.** The operator configures, at every receiver, each peer
runtime's:
- domain set;
- runtime address (`amap.router@<domain>` or equivalent);
- key set.

Trust anchors are configured, not discovered: no DNS publication,
directory or certificate chain (§3). A receiver MUST refuse to load a
configuration in which:
- a `key_id` occurs twice, across all peers (the receiver selects by `k`
  alone);
- a not-before is later than its not-after;
- a public key is not a canonical encoding of a curve point;
- a public key is of small order.

A sending runtime SHOULD make its key ids globally unique, for example from
a fingerprint of the public key.

These are **configuration-time** checks, a gate separate from verification.
A bare Ed25519 backend constructs and verifies under a small-order or
non-canonical key; the key loader, not the verifier, is what refuses it. An
implementation MUST demonstrate the refusal through its loader
(`config-key-small-order`, `config-key-non-canonical`,
`config-duplicate-key-id-across-peers`, `config-inverted-validity`), and
MUST NOT count passing the `reject_at: verify` vectors as covering it.

**Rotation.** A receiver MUST support at least two concurrent keys per
peer. The steps:
1. Add the new key at every receiver.
2. Switch the sender to it.
3. If the sender stops using the old key at time T, receivers keep the old
   key valid until at least T + F + P. A statement signed at T can carry
   `ts` up to T + F, and arrive up to P after that.

Validity is inclusive at both ends. **Revocation** is removing a key or
ending its validity. Replay records are scoped to the runtime, not the key,
so neither retiring nor revoking a key erases replay evidence (§5.5).

**The signing key** is a runtime credential (core §1). It MUST NOT be
readable from any agent namespace or by the admitting component. It MUST NOT
sign anything except this profile's statements and control notices, which
`kind` keeps apart.

**Verification policy.** Ed25519 per RFC 8032, with the cofactorless
equation [S]B = R + [k]A. A verifier MUST reject:
- S ≥ L;
- a non-canonical encoding of R or A;
- a key that failed the configuration checks above.

The profile requires nothing about how Ed25519 is computed. A vetted
library, a system binary or any other implementation conforms if it
produces these results. `fixtures/peer-signed/rfc8032-vectors.json` holds
RFC 8032 §7.1 TEST 1–3, and negative vectors marked `reject_at: verify` or
`reject_at: config`. An implementation MUST pass both through the backend it
ships.

### 5.8 Control notices

A receiving runtime tells a configured sending runtime what it did with a
statement it did not place, using a signed **control notice**.
`schemas/peer-control.schema.json` pins it, CLOSED, `v: 1`:

```
v, key_id, kind ("control"), id, from, to, ts, about, outcome, cause, policy_code (with cause "policy")
```

- **Form.**
  - It is carried in an `AMAP-Peer-Control` header field with §5.2's
    `k`/`s`/`b` grammar, signed with the same per-runtime key.
  - Its `kind` makes it impossible to read as a peer statement, and the
    reverse holds too.
  - It carries no free text. The cause vocabulary is closed, and the
    receiving runtime composes any words itself.
  - It travels as mail between runtime addresses.
- **When.** A receiver SHOULD send one for every outcome §5.4 marks, and
  only when §5.4's eligibility holds in full: never for a failure before
  check 5(b), never for a duplicate caught at check 2, never about a control
  notice, and never because a key was merely found. One notice per record:
  the pending notice is part of the record's disposition (§5.5), queued
  durably before the record is `done`, and sent at most once including
  across a crash. It MAY rate-limit; suppression MUST be logged.
- **`policy_code`** is deployment-defined. A receiving runtime renders a
  description it defines locally; an unknown token gets a generic one, and
  is never interpreted.
- **Addressing.** `from` is the receiver's own runtime address. `to` is the
  runtime address configured for the peer that owns the verifying key,
  never an address taken from the message. A control notice is never sent
  to a runtime that is not a configured peer.
- **Receiving one.** A runtime applies checks 1–5 of §5.3 with
  `AMAP-Peer-Control` and the control schema in place of the statement's.
  It then requires all of these:
  - `from` is the runtime address of the peer that owns the key;
  - `to` is its own runtime address;
  - `ts` is fresh (§5.5);
  - the notice's (runtime, `id`) is new;
  - `about` names a ledger record this runtime `issued` to an agent in the
    signer's domains.
- **What it does.** It gives the issuing agent a runtime-authored failure
  notice in `inbound/` (§4's DSN analogue), with no text from the control
  notice except the vocabulary values. The notice is owed the moment the
  record is reserved and the record is `done` only once the failure notice
  is durable; a crash in between is finished by recovery, once
  (`seq-control-crash-before-agent-notice`).
- **One per message.** An issued record receives at most one failure
  notice. A later control notice about the same `about`, under a different
  id, is dropped (`control-duplicate-about`). A `dropped`/`duplicate` report
  means a record for the message exists at the receiver, whose disposition
  may have been placement; it is not proof that the task failed.
- **Failures.** A control notice that fails any rule is dropped and logged:
  never placed, never handed to mail admission, never answered. A message
  carrying both fields is dropped.

### 5.9 Optional: sender age, and deployment admission policy

A deployment MAY refuse authenticated peer messages for reasons of its own,
such as a first-sight quarantine for a new sender, or a requirement that
every cross-host delegation carry `sender_exposure`. The refusal is
**refused, policy**, with a deployment-defined `policy_code`. The policies
themselves are deployment business, not this profile's.

Measuring a sender's age at the receiver, by first sight, makes every
agent's first delegation to each host fail. The optional signed member
`sender_since` exists to avoid that:
- It is when the sending runtime first enrolled the sending agent's
  identity, as that runtime defines identity, taken from its durable
  registry.
- It is a runtime assertion, covered by the signature, and never sender
  text.
- It has the format of `ts` (RFC 3339 UTC, whole seconds, `Z`) and is not
  later than `ts`. Skew is absorbed by the age itself: a receiver measures
  age as its own clock minus `sender_since`, so a few minutes of skew change
  nothing on a policy measured in hours.
- **Continuity.** The sending runtime MUST NOT reset it for a continuation
  of the same identity: a restart, a rebind, a re-creation or a key
  rotation keep the value. A new enrolment of the identity starts a new
  value. Which of the two a given event is, the sending runtime decides, and
  it MUST decide it the same way every time for that identity.
- **Consistency.** A receiver that enforces a sender-age policy MUST keep
  the last value it accepted per (runtime, `from`). A later statement that
  asserts an *earlier* value claims an older enrolment than the runtime
  previously asserted: it is inconsistent, and the receiver refuses it with
  its own `policy_code` (`sender_since_inconsistent` in the fixtures). A
  later value is a new enrolment, and the age starts again
  (`seq-sender-since-inconsistent`).

A receiver MAY enforce a minimum sender age from it. Absence means *not
asserted*, never "new" and never "old enough". A deployment that requires
it refuses its absence with its own `policy_code`.

### 5.10 The intake location

The intake location is REQUIRED as a structural property, with no
prescribed layout:

> A message admitted from a shared transport that presents as a peer or
> control candidate MUST be held, until disposed of, in a location that is
> neither `inbound/` nor `peer/`, writable by the admitting component,
> readable by the verifying component, and unreachable from any agent
> namespace. Candidates MUST be held as §5.2's candidate: the verifier never
> parses mail. The verifier MUST apply core §2's read discipline to
> candidates, since the admitting component is less trusted than the
> verifier. The verifier disposes of each candidate exactly once:
> - it places it in `peer/`, minting the `notice_id` at reservation (§5.5);
> - or it hands it to mail admission, which, if it delivers, places it in
>   `inbound/` under a `notice_id` minted there;
> - or it drops or refuses it, logging the cause.
>
> A candidate held while peer admission is closed (§5.5) is not yet
> disposed of; it stays here until admission reopens.

## 6. `sender_exposure` — a runtime assertion about the sender

Core's two-axis split applies: `disposition`, `verdict`, `sender_standing`
are runtime assertions; `from`, `subject`, `body_text` are sender claims. An
exposure record belongs on the assertion side. It records *delivery*, not
*reading*: the runtime can know it delivered external mail to the sender's
namespace; it cannot know what the sender did with it.

```json
"sender_exposure": {
  "asserted_by": "amp.router@fleet.example",
  "external_mail_delivered": true,
  "window_start": "2026-09-01T15:00:00Z",
  "window_end":   "2026-09-02T15:00:00Z",
  "last_external_delivery_ts": "2026-09-02T14:10:00Z",
  "derived_from": ["<notice-id in the sender's mail tree>"]
}
```

- **Placement.** A member of `message`, beside `sender_standing`,
  `provenance` and `verdict` — the runtime's assessments of the message live
  together. The schema requires `asserted_by` (a bare addr-spec naming the
  asserting runtime; cross-host, the signer), `external_mail_delivered`,
  `window_start`, `window_end`, and requires `last_external_delivery_ts` when
  the boolean is `true`; its absence when `false` is prose, not schema.
- **Shape.** A boolean over an explicit window plus the most recent
  timestamp. No count: a count asserts precision a delivery proxy lacks.
  `derived_from` is optional and present only where the runtime observed the
  derivation itself (the sender's reply key named a notice in its mail tree).
- **Absence means "not assessed", never "no exposure".** `false` asserted is
  a stronger statement than the member omitted: it says the runtime assessed
  the window and delivered no external mail. A runtime that is the only
  writer of a sender's mail tree and has written only same-principal agent
  mail and its own DSNs SHOULD assert `false`. Runtime-authored notices in
  the mail tree (the DSNs of §4) are not external mail and MUST NOT flip the
  boolean. Clamping `window_start` forward to the moment the runtime's
  assessment began (for example an instance's approval time after a reset)
  is the right way to keep the window on the wire equal to the span assessed.
- **Not sender-settable, by construction.** Same-host: the submit-request
  envelope is closed (core §7), so a request carrying it is `rejected` —
  stronger than stripping. Cross-host: taken only from the verified
  statement, and stripped on downgrade (§5). A runtime MUST NOT accept it
  from any sender.
- **Control use.** It MUST NOT drive routing or treatment (§2). Advisory,
  audit, covered by the signature.

**Sender-declared lineage is deliberately absent.** A field the sender
declares would ride the submit-request, whose envelope is closed — adding any
member there is MAJOR — and it works only when the sender is cooperative,
which is the case where it was least needed; a forgeable field also invites
readers to trust it. Most of its value is recovered without a field: when a
sender's reply key names a notice in its *mail* tree, the runtime knows which
external message the peer message derives from and records that as its own
observation (`derived_from`, and the audit log). If lineage returns, it
returns inside a deliberate submit-request major.

## 7. Delivery outcomes, retention, deletion, presentation

- **Delivery outcomes are not a profile artifact.** A connector that reports
  what it did with a notice (`delivered`, `held`, `refused`, …) writes that
  under core's `outbound/ext/<name>/`, in a shape agreed out of band with its
  runtime, and under the stable connector id core §2 requires — not a name
  derived from its repository, which a rename would invalidate. Core §2
  carries the one normative sentence: an outcome is a claim
  by the receiving side, never proof of delivery or non-delivery, and the
  runtime's own delivery record is authoritative over it. If a second
  connector wants outcomes, that is the trigger to lift a shape into this
  profile.
- **Retention — the record is the audit log, not the spool.** The runtime
  logs every peer notice it places (id, from, to, tree, exposure, signature
  verdict, demotion cause) to the per-agent `audit/log.jsonl` it owns, and
  to its own store of record. Spool retention for `peer/` follows the mail
  row of core's deletion table unchanged.
- **Deletion rights.** Core §2's table gains one row for `peer/` artifacts,
  identical to the inbound row: written by the runtime, deleted by the
  runtime only.
- **Presentation.** A connector presenting a peer body MUST meet core §5's
  presentation obligations, with one prohibition and one addition.

  It **MUST NOT** convey that the sender is unauthenticated. On this tree
  `message.from` is runtime-asserted from the restricted write path (§3) and
  is the one `from` in this protocol a consumer may treat as authenticated
  origin. Telling a reader otherwise contradicts the mechanism the tree exists
  to provide, and trains the wrong reflex about a channel whose whole premise
  is that the tree already answered that question.

  It **SHOULD** convey that an authenticated request is still bounded by what
  the receiving agent is authorised to do. A verified sender can ask for
  something the receiver may not perform, and a grant-shaped framing invites
  reading verified identity as having settled that question. It has not.

  It **SHOULD** convey that authenticated origin is not a content warranty:
  peer content is peer-authored and unscreened, and may paraphrase external
  mail (§6). Authenticated *who*; unverified *what*.

  None of this is an enforcement mechanism and no one should treat it as one.
  Enforcement on this tree is §2's write-authority partition and origin-follows-
  tree; presentation is what a connector states to a reader who can ignore it.
  The reason to get it right is not that it hardens anything — it is that the
  alternative asserts something false.

  **Correction (v3.1.0 DRAFT).** A prior revision of this bullet said only
  that a connector "MAY present peer bodies under the same untrusted-content
  framing it uses for mail". That was permission with no floor: it licensed
  the mail framing without saying what any framing had to preserve. A
  connector following it shipped the cautious option — which on this lane is
  the wrong one, in the specific direction of telling an agent not to act on
  work it was authorised to do. Permission without a floor selects for the
  safe-looking error.

## 8. Conformance

Two sub-classes, each requiring the corresponding core class (core §7.1)
plus the profile's fixtures and operational checks. Claiming either without
both is not conformance.

**Runtime + peer-origin.** In addition to the core runtime class, the
implementation:
- MUST produce peer notices valid against `schemas/peer-notice.schema.json`
  and MUST confirm its own emitted peer notices satisfy the same schema the
  `valid/peer-*` fixtures do;
- MUST refuse to emit, into `peer/`, any document that would fail that
  schema, and MUST NOT emit a `peer` document into `inbound/` (the second
  lock, §1b);
- MUST uphold the operational obligations of §2 (write-authority partition,
  proven by the write probe; verification placement), §3 (peer `from`
  runtime-asserted), §4 (reply key iff resolved; refuse-not-strip), §5
  (intake location; verifier hashes bytes itself) and §6 (exposure never
  sender-settable).

**Connector + peer-origin.** In addition to the core connector class, the
implementation:
- MUST accept every `valid/peer-*` fixture and MUST reject every
  `invalid/peer-*` fixture when read from `peer/notices/`, and MUST reject
  `invalid/notice-kind-peer.json` when read from `inbound/notices/`;
- MUST derive origin class from the tree alone (§2) and MUST act on a peer
  message at most once, holding rather than fanning out when it cannot
  identify a single target (§3);
- MUST tolerate unknown members on a peer notice (`valid/peer-unknown-member.json`;
  the envelope is OPEN per core §7).

**Fixtures** (`fixtures/`, checked by `fixtures/validate.py`, which maps the
`peer-` prefix to the peer schema and applies the `content_ref` post-check to
peer documents too):

| valid | invalid |
|---|---|
| `peer-minimal` | `peer-kind-deliver`, `peer-mailbox-inbox`, `notice-kind-peer` (§1b, the three legs of the second lock) |
| `peer-result` (`in_reply_to` + `references`) | `peer-from-display-name`, `peer-from-crlf` (§3) |
| `peer-exposure-false` (a same-host runtime's actual emission), `peer-exposure-true` | `peer-message-id-encoded`, `peer-in-reply-to-encoded` (§4) |
| `peer-attachment-clean-ref` | `peer-exposure-missing-asserted-by`, `peer-exposure-true-missing-last-ts` (§6) |
| `peer-unknown-member` | `peer-attachment-ref-index-mismatch` (post-check), `peer-notice-id-trailing-newline` |

**Statement and control fixtures** (§5 revision s5-r4, proposed; `statement-`
prefix for `schemas/peer-statement.schema.json`, `control-` for
`schemas/peer-control.schema.json`): see `fixtures/valid/` and
`fixtures/invalid/`. Each invalid fixture fails for exactly one reason.

**Signed cases** (§5 revision s5-r4, proposed; `fixtures/peer-signed/`, run by
`validate.py` through `peer-signed/check_cases.py`):
- `rfc8032-vectors.json`: RFC 8032 §7.1 TEST 1–3 and the negative vectors of
  §5.7, marked `reject_at: verify` or `reject_at: config` (two gates);
- `mime/`: raw messages and the candidate §5.2's selection rule makes of
  each, reduced by a byte-exact splitter (a leaf's octets are its part body
  as transmitted, transfer-decoded; markers for fields it cannot carry);
- `cases/`: sequences of candidates and events (crash at each §5.5 point,
  recovery, store loss with and without H, an operator bound, clock and
  window changes, edge and key changes), each step with the outcome, cause,
  published fields and control notice the receiver in `receiver.json` or
  `receiver-host-a.json` MUST reach. Single-step cases break exactly one
  rule; `multi-` cases pin §5.3's precedence; `seq-` cases pin state across
  steps; `config-` cases are configurations the receiver MUST refuse to
  load.

A runtime + peer-origin implementation that verifies cross-host traffic MUST
reach every step's `expect`, and MUST pass the vectors through the Ed25519
backend it ships. `check_cases.py` models only the state §5.5 makes
normative; it is a fixture self-check, not a runtime, and its pure-Python
Ed25519 is for the gate alone.

**Not checked by the gate, runtime-enforced only** — a green `validate.py`
says nothing about these; each has a prescribed operational check above: the
write-authority partition (§2), intake isolation (§5.10), verification
placement (§2), exposure not sender-settable (§6), `in_reply_to` iff resolved
(§4), at-most-once action (§3), the durability of the replay store, of H,
of each record's disposition and of pending control notices across restarts
(§5.5, §5.8), the closing of admission when H is lost (§5.5), and the
protection of the signing key (§5.7).

## 9. Required vs. optional (profile artifacts)

| Artifact | Required | Optional |
|---|---|---|
| `peer/notices/notice-<id>.json` | `contract_version`, `notice_id`, `ts`, `kind: "peer"`, `message.{id, from, subject, preview, mailbox: "peer"}` | `message.{in_reply_to (REQUIRED on a result by prose), references, task_id, thread_id, sender_standing, provenance, verdict, sender_exposure, attachments}` |
| `peer/messages/notice-<id>.json` | as core §5's inbound-message | as core §5 |
| `peer/notices/<notice-id>.attachments/<i>` | as core §5 | as core §5 |
| signed statement (cross-host, §5.1) | `v, key_id, kind, id, from, to, ts, subject, body_sha256, attachments` | `in_reply_to`, `sender_exposure`, `sender_since` |
| `AMAP-Peer-Statement` field (cross-host, §5.2) | exactly one; tags `k`, `s`, `b` | — |
| signed control notice (§5.8) | `v, key_id, kind, id, from, to, ts, about, outcome, cause` | `policy_code` (required with cause `policy`) |
| `AMAP-Peer-Control` field (§5.8) | exactly one; tags `k`, `s`, `b` | — |

Wire `contract_version` stays `"2"`; v3.1.0 is additive (MINOR) per core §7.
