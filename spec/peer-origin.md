# amap-spec — peer-origin profile, v3.1.0 DRAFT

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
requires a routable one, because cross-host peer traffic is mail (§5). Where
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
key, MUST NOT place it as a fresh peer task, MUST log the cause, and MAY tell
the sending runtime, runtime-to-runtime (signed). It is not demoted to mail
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

## 5. Cross-host: signed peer traffic and the intake location

Cross-host peer traffic is mail. The sending runtime signs; per-agent keys
are not used; failure to verify downgrades the message to mail; same-host
needs no signature (local write permission is stronger), though a same-host
runtime MAY sign for a uniform code path — treatment does not change.

**Canonicalisation — none; transmit the signed bytes.** The sender builds a
*statement* (small JSON), signs its exact bytes with Ed25519, and ships both
verbatim in one header, base64url, whitespace stripped before decode (DKIM's
folding posture). The receiver verifies the signature over the received
bytes *before parsing*, then checks the parsed statement against the message
it will publish. Nothing is ever re-serialised. Statement members (closed
set, `v: 1`):

```
v, key_id, kind ("peer"), id, in_reply_to (optional), from, to, ts, subject,
body_sha256,                       # over the UTF-8 body_text the receiver will publish
attachments: [{sha256, size_bytes, filename, media_type}, ...],   # by index
sender_exposure                    # §6; omitted if the sender's runtime made no assessment
```

The sending runtime MUST also set `Message-ID`, `In-Reply-To` and
`References` to the encoded forms (§4) so the mail side threads coherently
and a demoted candidate still threads as mail. The receiving runtime takes
`id` and `in_reply_to` from the verified statement, never from headers.

**Verification**, all of which MUST hold: (1) the signature is valid for
`key_id`; (2) `key_id` belongs to a configured peer whose domain set contains
`from`'s domain; (3) `to` is hosted here; (4) `ts` is within the configured
window; (5) `id` is not in the seen-id window, which MUST span at least the
timestamp window; (6) the body digest and every attachment digest match bytes
the **verifier hashes itself**, never digests the admitting component
computed; (7) the attachment count matches; (8) the `Message-ID` header
decodes to the statement's `id`. Any failure → mail. A statement that
verifies but whose `to` is not hosted here is dropped as misrouted, not
demoted.

**Key rotation.** `key_id` in the statement; a set of keys per peer domain,
each with optional not-before / not-after; a receiver MUST support at least
two concurrent keys per peer. Rotation: add at receivers, switch the sender,
retire after the timestamp window.

**Downgrade.** MUST log with cause. MUST NOT notify the *claimed* sender when
its domain is not a configured peer — that is backscatter. MAY notify a
configured peer runtime, runtime-to-runtime, signed. Whether the sending
*agent* is told is the sending runtime's policy; the natural signal is the
absence of a result within its window. The demoted `deliver` notice MUST NOT
carry `sender_exposure`, the statement, or the signature; it carries the
mail-admission verdict the admitting component attached to the candidate,
and ordinary mail admission still governs whether it is delivered at all.

**The intake location** — REQUIRED as a structural property, with no
prescribed layout:

> A message admitted from a shared transport that presents as a peer
> candidate MUST be held, until placed, in a location that is neither
> `inbound/` nor `peer/`, writable by the admitting component, readable by
> the verifying component, and unreachable from any agent namespace.
> Candidates MUST be in notice shape plus raw body and attachment bytes: the
> verifier never parses mail. The verifier MUST apply core §2's read
> discipline to candidates — the admitting component is less trusted than
> the verifier. The verifier places each candidate exactly once, into `peer/`
> on pass or `inbound/` on fail, minting the `notice_id` in either case (§1c).

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

**Not checked by the gate, runtime-enforced only** — a green `validate.py`
says nothing about these; each has a prescribed operational check above: the
write-authority partition (§2), intake isolation (§5), verification placement
(§2), exposure not sender-settable (§6), `in_reply_to` iff resolved (§4), and
at-most-once action (§3).

## 9. Required vs. optional (profile artifacts)

| Artifact | Required | Optional |
|---|---|---|
| `peer/notices/notice-<id>.json` | `contract_version`, `notice_id`, `ts`, `kind: "peer"`, `message.{id, from, subject, preview, mailbox: "peer"}` | `message.{in_reply_to (REQUIRED on a result by prose), references, task_id, thread_id, sender_standing, provenance, verdict, sender_exposure, attachments}` |
| `peer/messages/notice-<id>.json` | as core §5's inbound-message | as core §5 |
| `peer/notices/<notice-id>.attachments/<i>` | as core §5 | as core §5 |
| signed statement (cross-host, §5) | `v, key_id, kind, id, from, to, ts, subject, body_sha256, attachments` | `in_reply_to`, `sender_exposure` |

Wire `contract_version` stays `"2"`; v3.1.0 is additive (MINOR) per core §7.
