# amap-spec — the volume contract, v3.1.0 DRAFT

The wire contract between a **trusted mail runtime** (credentialed,
agent-agnostic) and a per-agent **connector** (untrusted, credential-free).
This is the IDL both sides depend on; it is owned by neither.

> **Scope.** This document specifies the **wire mechanics plus the obligations
> a conforming runtime or connector must meet** — and deliberately nothing
> else. Runtime *mechanism* (how identity is minted, how senders are verified,
> the task-keying algorithm, what policy decides) is out of scope, as is
> connector *capability semantics* (push shapes, reply and threading behavior).
> The wire fixes the vocabulary; it never fixes the computation. Field shapes
> below match what the reference implementations emit; see §8 for what is
> required versus optional.

> **Authority.** This file, together with `schemas/` and `fixtures/`, is the
> normative contract. `dist/draft-amap-00.xml` is a
> standalone rendering generated from it; where the two disagree, this file
> and the fixture gate (`fixtures/validate.py`) govern, and the rendering is
> regenerated from this file — never patched independently.

## 1. Actors and the invariant

| Actor | Trust | Holds | Reaches |
|---|---|---|---|
| **Runtime** (container) | trusted | mail-send creds, agent identity, policy, of-record | the mail provider, the volume |
| **Connector** (per agent) | semi-trusted (agent-side) | nothing credentialed | its own namespace on the volume; its agent's I/O |
| **Agent** | **untrusted** | only what the connector surfaces | the connector; its sandbox |

**Invariant (load-bearing).** No security property may depend on the agent or
connector behaving. Enforcement is entirely runtime-side. A compromised agent or
connector can at most write a well-formed request the runtime then refuses. The
contract grants nothing on its own — which is why the channel is a
runtime-owned **filesystem namespace**, not an API/queue/RPC the agent could
call: a file drop carries no capability.

**Vocabulary (non-normative): runtime vs. router.** This document's actor is
the **runtime**, and it uses that word throughout. Implementations in this
family call a conforming runtime a *router*; the term is theirs, not this
document's. It marks what those implementations add on top of the seam —
recipient policy, the two lanes, the reply ledger, delivery-status notices —
none of which this contract specifies. A router is a runtime; nothing here
requires a runtime to be a router.

## 2. Directory layout (per agent)

The runtime owns the tree and mounts each agent's namespace into that agent's
sandbox. A connector has access **only** within its own `<agent-id>/`, and
only to the paths below. Within that namespace, write access may be narrower
still: the `inbound/` subtree is runtime-owned and MAY be mounted read-only
(v2.2.0) — see the obligations below.

The volume root's own name is a **deployment choice, not part of this
contract** — nothing derives from it and no implementation may depend on it.
`<volume-root>/` below stands for whatever a deployment calls it.

```
<volume-root>/
  <agent-id>/
    outbound/
      req-<id>.json            # agent → runtime: a submit request (agent writes)
      req-<id>.attachments/    # agent → runtime: sidecar bytes, ordinals 0 1 2 … (agent writes)
      results/<id>.json        # runtime → agent: verdict for req <id> (runtime writes)
      processed/req-<id>.json  # runtime: consumed requests (archive)
      ext/<name>/              # connector-owned side channel a runtime MAY read by out-of-band agreement; no shape specified here (v3.1.0 DRAFT, §2)
    inbound/
      notices/notice-<id>.json # runtime → agent: a delivered-mail event (runtime writes)
      notices/<notice-id>.attachments/  # runtime → agent: bytes the runtime asserts clean, ordinals 0 1 2 … (runtime writes; v2.3.0, §5)
      notices/processed/       # OPTIONAL — connector archive convention, writable-inbound deployments only (v2.2.0)
      messages/notice-<id>.json # runtime → agent: full delivered message incl. body_text (runtime writes; v2.1.0, §5)
      cursor.json              # runtime: inbound poll cursor (runtime-owned)
    peer/                      # PROFILE (v3.1.0 DRAFT, spec/peer-origin.md): same layout, conventions and sidecar rules as inbound/; runtime writes; MAY be read-only
      notices/notice-<id>.json
      notices/<notice-id>.attachments/
      messages/notice-<id>.json
    audit/
      log.jsonl                # runtime: append-only per-agent action log (runtime writes)
    directory.json             # runtime → agent: which peers this agent may address (runtime writes; v3.1.0 DRAFT, §10) — OPTIONAL
```

**Obligations:**
- **`<agent-id>` is runtime-assigned, never self-declared.** Attribution is *the
  namespace a file arrived in*, not any `agent_id` field inside it (that field is
  a cross-check only, never the source of truth).
- **Isolation is structural:** a connector scoped to `<agent-id>/` cannot read
  another agent's drafts or notices.
- **All writes are atomic** (`.tmp` + `os.replace`); readers ignore `*.tmp`.
- **Single writer, single drainer (v3.0.0).** At any moment a namespace has
  exactly one connector instance writing `outbound/` and exactly one runtime
  instance draining it. Every concurrency-sensitive rule in this contract —
  `.tmp` + `os.replace` atomicity, the commit sentinel below, `req_id`
  derivation from `max(pending, processed, results)+1` (§3) — is sound only
  under that assumption and provides no mutual exclusion of its own. Each
  side MUST ensure single-instance operation over a namespace by a mechanism
  outside the seam (e.g. an OS-level lock held for the process lifetime); a
  runtime MUST NOT run two concurrent drains of one namespace and a connector
  MUST NOT run two concurrent writers into one. Behavior under violation is
  unspecified: duplicated delivery, clobbered published requests, and false
  verdicts are all reachable.
- **Filename ids are the authority for paths.** An identifier taken from a file's
  *contents* (e.g. a `req_id` in the body) MUST NOT determine a write path — the
  runtime derives ids from the validated filename, on a restricted charset.
  **Write-side path discipline (v3.0.0), stated with the same precision as
  the read-side rule immediately below:** every write, `os.replace`,
  directory-create, or archive move into or within a namespace MUST satisfy
  all three of the following, **conjunctively** — each closes a distinct gap
  the other two leave open, and none is sufficient alone:
  - **(a) Full parent-chain pinning.** The write resolves its full parent
    chain through pinned directory descriptors from the namespace root
    (`openat`/`mkdirat`/`renameat` off a descriptor the runtime opened once
    per namespace, never by re-resolving a path string for the act itself).
    A path-based containment check followed by a path-based act (`open`,
    `os.replace`, `mkdir`) is a race, not a check: the parent directory the
    check inspected and the parent directory the act touches are not
    guaranteed to be the same object, because the agent can swap a parent
    directory for a symlink in between. Per-component `O_NOFOLLOW` on the
    *final* path component alone does not close this gap — it constrains
    only the last component, not a swapped parent — and
    `os.replace`/`mkdir` have no `O_NOFOLLOW`-equivalent at all, so a bare
    "no-symlink-follow writes" requirement is not sufficient on its own.
  - **(b) No-follow while building the chain.** Each directory component
    that goes into that parent chain MUST itself have been opened
    `O_NOFOLLOW|O_DIRECTORY` at the moment it was added to the pinned
    chain — a descriptor only counts as "pinned" if the open that produced
    it refused to follow a symlink at that step. (a) without this is
    equally insufficient, the symmetric gap to the one (a) itself closes:
    nothing stops the runtime from *acquiring* a "pinned" descriptor by
    following an agent-planted symlink in the first place — e.g. the agent
    replaces a namespace subdirectory with a symlink before the runtime's
    once-per-namespace open, or before a later re-open after a restart —
    and a descriptor obtained that way is pinned to the wrong object, so
    every write built off it inherits the redirection regardless of how
    faithfully (a) is followed from there.
  - **(c) Non-following final component.** The final path component MUST
    NOT be followed if a symlink exists at that name: the open MUST carry
    `O_NOFOLLOW` and MUST fail closed on `ELOOP` rather than writing
    through whatever the name currently resolves to. Two cases differ in
    what else they require, and both are covered:
    - **A newly-created file** — the `.tmp` sibling this contract's
      atomicity rule (above) already requires, and any sidecar blob — MUST
      additionally be created `O_EXCL` (`O_WRONLY|O_CREAT|O_EXCL`, never
      `O_TRUNC` in place of `O_EXCL`), failing closed on `EEXIST`.
    - **An append-mode or directory-create write that has no `.tmp`
      sibling** — `audit/log.jsonl` is the case in this contract — cannot
      use `O_EXCL`, since the target legitimately already exists. It MUST
      instead open `O_NOFOLLOW|O_APPEND|O_NONBLOCK` (or `mkdirat` with the
      parent pinned per (b)), **MUST NOT block on a special file**, and MUST
      verify through the resulting descriptor (`fstat`, never a pre-open
      `stat`) that the object is a regular file it may append to; it SHOULD
      refuse a target whose link count exceeds 1. The non-blocking open is
      load-bearing and is not a performance concern: `O_NOFOLLOW` does not
      apply to a FIFO — a FIFO is not a symlink — and opening one for
      writing blocks until a reader appears, so without `O_NONBLOCK` the
      `fstat` is never reached and an agent that plants a FIFO at this name
      stalls the drain indefinitely. Branch 1's `O_EXCL` refuses that case
      on its own; branch 2 has no `O_EXCL` to lean on and MUST state it. Requiring `O_EXCL` here would forbid appending to
      an existing log at all; requiring nothing here would leave the one
      write this contract names that has no `.tmp` sibling unprotected.

    Why the whole of (c) is required, in both branches: an agent that
    pre-plants a symlink at a filename the runtime is about to write —
    `req_id` is agent-chosen, and every runtime-written filename in the
    layout tree above (`results/<id>.json`, the `.tmp` sibling of
    `processed/req-<id>.json`, `inbound/notices/notice-<id>.json`,
    `inbound/messages/notice-<id>.json`, `audit/log.jsonl`) is reachable to
    an agent that can predict or observe it — otherwise gets its bytes
    written through that symlink with the runtime's own privileges, even
    though the parent chain that reached the containing directory was
    itself correctly pinned under (a) and (b).

  This governs every runtime-side write named in the layout tree above —
  `results/<id>.json`, `processed/req-<id>.json`, `inbound/notices/...`,
  `inbound/messages/...` — not only the initial consumption of an
  agent-authored artifact. *(Obligation from a confirmed exploit in an early
  implementation: trusting a file's own contents, rather than its validated
  filename, to name a write path; any runtime must uphold it.)*
- **Read discipline is the same rule, applied to reads (v3.0.0).** When the
  runtime opens any path the agent can influence — every `req-<id>.json`,
  every sidecar ordinal, and (in a deployment that leaves `inbound/`
  writable) anything it later reads back from there — it MUST open without
  following symbolic links at any component (per-component `O_NOFOLLOW`, or
  an equivalently pinned directory-descriptor walk from the namespace root,
  matching the write-side rule above), MUST NOT block on a special file
  (non-blocking open), MUST verify the opened object is a regular file via
  the open descriptor (`fstat`/`S_ISREG` — never a pre-open `stat`, which is
  a race), SHOULD refuse a file whose link count exceeds 1, and MUST enforce
  a deployment-configured per-file size cap (bounded read) and per-request
  sidecar count cap. `too_large` in the result vocabulary (§4) presumes this
  cap: enforcing one is an obligation, not an option. A connector's one
  agent-influenceable read path — `notice_id → inbound/messages/notice-<id>.json`
  — MUST be built only from a pattern-validated `notice_id` (schemas pin the
  pattern) and MUST confine resolution to the connector's own `inbound/`
  tree (§5).
- **Sidecar blobs are named by runtime-assigned 0-based ordinals, equal to the
  descriptor array index — the sole binding authority.** Nothing else names a
  blob; `filename` is display-only and is never a path.
- **Commit sentinel.** All sidecar bytes are written (`.tmp` sibling, then
  `os.replace`) **before** `req-<id>.json`; the JSON's presence is the only
  publish signal. The runtime verifies every referenced ordinal exists and
  re-verifies size+sha before acting on the request — against the snapshot it
  took at ingest (below), never against the live path.
- **Inbound sidecar dirs are keyed on the runtime-minted `notice-id`**, never
  the provider `message.id` (the provider id is external and not
  charset-safe — using one as a path component was a confirmed exploit path
  in an early implementation). The same rule extends to the body artifact introduced in
  v2.1.0 (§5): `inbound/messages/notice-<id>.json`, keyed on `notice-id`,
  never `message.id`. **Inbound bytes are published only at
  `inbound/notices/<notice-id>.attachments/<index>` (v3.0.0)** — the single
  sidecar directory named in the layout tree above — and both the deliver
  notice's and the inbound message's `content_ref` resolve there; there is no
  second, message-specific sidecar directory (a prior revision's prose in
  this bullet claimed one; that was a self-contradiction against the layout
  tree and against §5, and is corrected here).
- **Runtime-private staging lives OUTSIDE the mounted volume** — a path the
  agent's mount cannot reach at all.
- **Ingest-by-copy (v3.0.0).** Before validating, evaluating policy on, or
  composing from any agent-authored artifact — `req-<id>.json` and every
  sidecar ordinal — the runtime MUST copy the bytes into runtime-private
  staging (above) and MUST act only on that private copy. All checks —
  schema validation, recipient policy, size and `sha256` verification — and
  all message composition MUST run over the snapshot, and the runtime MUST
  NOT re-read any agent-writable path after a decision that depends on its
  content: verify-then-use against the live path is a race, not a check. The
  connector's "MUST NOT delete or rewrite a published request" (§2 deletion
  table) is thereby restored to a pure well-formedness obligation: a runtime
  MAY treat an observed post-publish change as malformed, but no safety
  property depends on the connector honoring immutability — which is what
  §1's invariant requires. (This governs properties protecting the runtime,
  other agents, and the outside world; obligations that protect an agent
  *from its own inbox* — untrusted-content handling — are necessarily
  connector-implemented and are stated as such, not as a safety property the
  runtime relies on the connector for.)
- **Byte-absence is the gate.** The runtime MUST NOT place non-clean bytes in
  the agent namespace; `content_ref` is the runtime's access grant, present
  only for bytes it has published as clean (§5).
- **Inbound is runtime-owned; read-only is a valid posture (v2.2.0).** The
  `inbound/` tree is runtime-owned end to end. A runtime MAY expose it to the
  sandbox read-only (e.g. a read-only mount — the mechanism that actually
  makes a delivered notice unforgeable, since file permission bits do not
  bind a same-uid agent, which can `chmod` its way past them). A connector
  MUST NOT require write access anywhere under `inbound/`: it MUST start,
  relay notices, and resolve bodies when every write, rename, or
  directory-create under `inbound/` fails. `inbound/notices/processed/` is
  OPTIONAL — a conventional archive location a connector MAY use only where a
  deployment leaves inbound writable; nothing on either side may depend on
  its existence or contents.
- **The namespace root is runtime-owned for runtime-written files (v3.1.0
  DRAFT).** `inbound/` and `peer/` are not the only places a runtime writes
  into an agent's namespace: `directory.json` (§10) sits at the root, beside
  the lanes rather than inside one, because it describes the agent's
  addressable world across both and a lane-scoped home would oblige a
  delegation-only deployment to materialise a mail tree it does not otherwise
  need. A runtime MAY expose runtime-written files at the namespace root
  read-only, by the same mechanism it already uses for `inbound/` and `peer/`,
  and a connector MUST NOT require write access to any of them. This extends
  an existing posture rather than adding a new one; it does not make the whole
  namespace root runtime-owned, since `outbound/` lives under it and is
  agent-written by design.
- **Consumption-tracking is connector-private (v2.2.0).** How a connector
  records which notices it has already relayed to its agent is
  connector-private state, outside this contract. Such state lives in the
  connector's own storage outside this volume, or in connector-owned paths
  under `outbound/` not enumerated above — which MUST NOT use the `req-`
  prefix, reserved for submit-requests and their sidecars, so that a
  runtime's scan of the drop-box never encounters connector-private state.
  Either way the runtime neither reads nor relies on it. (A seam-visible
  consumption signal is deliberately not specified at v2.2.0 — see
  Appendix A.)
- **Tree rules (v3.1.0 DRAFT).** Every runtime-owned inbound-class tree is an
  **origin class**: a consumer derives the class of a document from the tree
  it was read from and never from any member of the document. `notice_id`
  uniqueness is per tree, and where a tree has more than one writer each
  MUST mint so that cross-writer collision is negligible (≥128 bits under
  the §7 charset, or a writer-specific prefix); a consumer keying state
  across trees MUST include the tree in the key. `content_ref` resolves only
  within the `notices/` directory of the tree the enclosing document was
  read from. Write authority per tree is distinct and MUST be structurally
  enforced — never configuration the writer reads. `inbound/` is the one
  tree this document defines; a profile MAY define others
  (`spec/peer-origin.md` defines `peer/`).
- **Outbound extension space (v3.1.0 DRAFT).** `outbound/ext/<name>/` is a
  connector-owned side channel, one directory per `<name>`, that a runtime
  MAY read by out-of-band agreement. **`<name>` is a stable connector id:
  the connector chooses it once, and it MUST NOT change when the
  connector's repository, package, or deployment is renamed or moved. A
  runtime that reads the directory MUST treat `<name>` as opaque — it is an
  identifier, never a name to be parsed, resolved, or matched against a
  repository or path.** This
  contract specifies no shape for anything under it; it lies outside the
  `req-` prefix the runtime scans (the rule immediately above), and nothing
  security-relevant may be built on it. Its first use is a connector's
  per-notice **outcome** file, written by the receiving agent's own uid and
  therefore forgeable by construction. An outcome is a statement by the
  receiving side about what it did with a notice; a party MUST NOT treat an
  outcome as proof of delivery or of non-delivery, and the runtime's own
  delivery record is authoritative over it. There is deliberately no inbound
  extension space: an inbound tree is a runtime assertion about origin, and
  a connector cannot know what a vendor-named assertion means.

### Deletion rights (v2.2.0)

AMAP previously said nothing about who may delete an artifact, in either
direction — which is why `outbound/results/`, `outbound/processed/`, and (had
the notices/processed/ move stayed mandatory) the inbound archive all grow
without bound. This table names it. It is **permissive**: a party exercising a
right it already effectively had (e.g. a runtime deleting from its own
runtime-owned tree) changes nothing about what conformant behavior looks like
today.

| Artifact | Written by | May be deleted by | Basis |
|---|---|---|---|
| `outbound/req-<id>.json` (pending) + `req-<id>.attachments/` | connector | runtime | consumption (the existing move to `processed/`, or deletion once the result is written). The connector MUST NOT delete or rewrite a published request — the JSON's presence is the commit signal (above); un-publishing is unspecified. |
| `outbound/processed/req-<id>.json` | runtime | runtime at will; connector after reading the matching result | runtime's own archive. **Caveat:** §3 derives `req_id` from `max(pending, processed, results)+1`; a connector that deletes here (or in `results/`) MUST preserve `req_id` monotonicity by other durable means (e.g. its own counter). Correspondingly, a runtime MUST NOT rely on `processed/` contents as durable state (e.g. for dedup) — the connector may delete there; the runtime's own record lives outside the seam. |
| `outbound/results/<id>.json` | runtime | connector, once read; runtime by retention | no seam signal tells the runtime a connector has read a verdict, so runtime-side deletion SHOULD be age-based and generous — a result deleted before it is read is a lost verdict. |
| `inbound/notices/notice-<id>.json`, `inbound/messages/notice-<id>.json`, and their `.attachments/` sidecar dirs | runtime | runtime only. (Where a deployment leaves inbound writable, the connector MAY move/delete per the optional `processed/` convention above, but MUST NOT depend on the ability.) | runtime retention policy. Absent a seam-visible consumption signal (none at v2.2.0, Appendix A), retention MUST be conservative/age-based; a connector already tolerates disappearance of these artifacts — a read against a missing one returns "not resolved" (§5). |
| `peer/notices/notice-<id>.json`, `peer/messages/notice-<id>.json`, and their `.attachments/` sidecar dirs (v3.1.0 DRAFT, `spec/peer-origin.md`) | runtime | runtime only | identical to the inbound row above. |
| `inbound/cursor.json` | runtime | runtime | internal state. |
| `audit/log.jsonl` | runtime | runtime (rotation) | never the connector. |
| `identity.json` | runtime/provisioner | runtime/provisioner | consumers already tolerate its absence (§9). |

## 3. Outbound — submit request (agent → runtime)

The agent's only outbound action is dropping an inert request file. It carries no
send capability; the runtime enforces policy before anything leaves.

```json
{
  "contract_version": "2",
  "req_id": "00000001",
  "agent_id": "<assigned>",
  "ts": "2026-07-20T04:10:56Z",
  "in_reply_to": "<notice-id or message-id>",
  "draft": {
    "to": ["addr"],
    "cc": [],
    "subject": "",
    "body_text": "",
    "reply_to_message_id": null,
    "attachments": [
      { "filename": "report.pdf", "media_type": "application/pdf",
        "size_bytes": 48213, "sha256": "9f2c…" }
    ]
  }
}
```

**Obligations:**
- `req_id` is **monotonic per namespace**, never reused across the drop-box's
  life (derive from `max(pending, processed, results)+1`). Reuse collides
  message-ids and triggers provider-side idempotency dedup.
- `agent_id`, if present, MUST match the namespace; the runtime rejects a
  mismatch. It is never the attribution source (§2).
- `in_reply_to` (optional) correlates this request with prior inbound work; it
  carries either a runtime-minted `notice_id` or a mail message identifier. It
  is a **hint from an untrusted party** and MUST NOT by itself widen what the
  request is permitted to do — same posture §6 fixes for `task_id`.
- The runtime derives the RFC822 message identity and the From/Reply-To itself
  (identity is runtime-owned); the agent does **not** choose its sending identity.
- `draft.subject` and `draft.body_text` are required and MAY be empty strings.
  `body_text` is **plain text**; this document defines no alternative body
  representation at this version.
- The agent's chosen `draft.to`/`cc` are **not** inherently trusted: recipient
  policy (allowlist / task-counterpart binding) is a runtime decision. A
  populated allowlist + a fresh recipient is an exfil surface the runtime, not
  the connector, must close.
- **Recipient syntax and header-injection discipline (v3.0.0).** Each
  `draft.to`/`cc` element is exactly one bare addr-spec — no display name,
  address list, quoted local part, comment, IP literal, or folding
  whitespace (schemas pin the pattern; deliberately narrower than RFC 5322,
  because those excluded forms are exactly what makes allowlist evaluation
  non-mechanical — EAI/SMTPUTF8 addresses are out of scope at this version,
  extensible later). The runtime MUST reject (top-level `rejected`) a
  request whose recipient entries do not parse under this profile, MUST
  evaluate recipient policy over exactly the recipient set it will transmit
  to, and MUST NOT transmit to any address not present in `draft.to`/`cc`.
  Separately, the runtime MUST NOT allow any agent-authored string
  (`subject`, recipient entries, attachment `filename`, attachment
  `media_type`, `draft.reply_to_message_id`, `in_reply_to`, `agent_id`, `ts`,
  `body_text` where it abuts headers) to introduce a header boundary in the
  composed message: CR, LF, and NUL MUST be rejected or stripped before
  composition even where schema validation was bypassed upstream — the
  schema-level control-character patterns on `subject`, `filename`,
  `media_type`, `reply_to_message_id`, `in_reply_to`, `agent_id`, and `ts`
  are the first line of defense, not the only one. The first two of that
  list, `reply_to_message_id` and `media_type`, matter precisely because
  they are composed directly into a header (`In-Reply-To:` and a MIME part's
  `Content-Type:` respectively) rather than into a body or a display field —
  an earlier revision's schema pattern coverage stopped at `subject`
  and `filename` and missed exactly these two composition sites.
- **`draft.attachments[]`** (optional) is an array of descriptors: `filename`,
  `media_type`, `size_bytes`, `sha256` — **`size_bytes` and `sha256` are
  REQUIRED on every descriptor**, computed by the connector over the
  **decoded** bytes it wrote, `sha256` lowercase hex. There is **no outbound
  `content_ref`**: the runtime re-derives each sidecar's path from `req-<id>`
  plus the descriptor's array index (the sole binding authority) — an
  agent-supplied path string would be pure disagreement/attack surface, so it
  is dropped from the schema entirely (`additionalProperties:false` rejects
  it). `attachments: []` is valid and is equivalent to the field being absent;
  the sidecar dir MUST then be absent. `sha256` here is an integrity/dedupe
  aid, **not an outbound trust boundary** — the agent controls both the bytes
  and the hash, so a mismatch only catches corruption, not a hostile agent.

## 4. Outbound — result (runtime → agent)

```json
{
  "contract_version": "2",
  "req_id": "00000001",
  "outcome": "accepted",
  "detail": null,
  "reason_code": "allowlisted",
  "ts": "2026-08-09T19:14:00Z",
  "recipients": ["addr"],
  "message_id": "<...@...>",
  "job_id": "<provider job id or null>",
  "attestation": {
    "form": "self-stamp",
    "token": "selfstamp.v1.<...>",
    "claims": { "agent": "...", "acts_for": "...", "issued_at": "..." }
  },
  "attachments": [
    { "index": 0, "outcome": "accepted", "detail": null }
  ]
}
```

**Obligations:**
- **The runtime writes exactly one result per submit request it consumes**
  (v3.0.0) — a request the runtime never consumes gets no result, and no seam
  signal distinguishes "not yet" from "never."
- `outcome ∈ {accepted, queued_for_human, rejected}`.
- Any policy miss (allowlist, rate, DLP-hold, halt) ⇒ `queued_for_human` —
  **never** a silent send, **never** a silent drop.
- `accepted` = the provider accepted for relay; downstream delivery/quarantine is
  out of the runtime's hands (surfaced later via inbound DSN if any).
- `reason_code` (optional, machine-readable): records *which policy path*
  authorized or refused; human text stays in `detail`. A runtime **SHOULD**
  set a reason on every result, success included. Suggested extensible
  vocabulary: `recipient_bound`, `allowlisted`, `no_verified_counterparty`,
  `recipient_not_allowlisted`, `dlp_hold`, `no_screener`, `halted`,
  `rate_limited`, `unsupported_contract_version` — extensible; the schema
  does not enum-lock it. `unsupported_contract_version` is the code a runtime
  sets on the `rejected` result it writes for a version-refused submit-request
  (§7's version-check-ordering rule) — the outbound half of that rule; the
  inbound half (a version-refused notice) has no result document to carry a
  code on and is logged-only. Because it is extensible, two consumer obligations
  follow (v2.2.0): a consumer **MUST** tolerate a `reason_code` it does not
  recognize — treating it as opaque, never as an error — and a consumer
  **MUST NOT** infer the `outcome` from it. `outcome` is the sole
  authoritative verdict; `reason_code` only explains which path produced it,
  and a runtime may add codes at any time without a contract change.
- `attestation` (optional): the identity stamp the runtime applied to the
  outbound message; `form ∈ {self-stamp, verifiable}` distinguishes a
  non-stranger-verifiable self-stamp from a verifiable attestation; a
  connector *surfaces* it, never verifies it (runtime concern).
- `ts` (optional): ISO-8601, runtime-set, of-record time of the verdict.
- **`attachments[]`** (optional) carries one diagnostic entry per submitted
  attachment: `{ index, outcome: accepted|dlp_held|rejected_type|too_large,
  detail }`. `index` MUST equal the entry's own position in the array —
  contiguous, unique, `0` through `n-1` exactly once; array position is the
  binding authority for attachments in both directions (§2). This constraint
  is not expressible in JSON Schema and is enforced by the conformance gate
  as a named post-check, not by the schema. **Two paths,
  never conflated:** a malformed attachment (size/sha mismatch, missing/extra
  sidecar, duplicate index) is **not** a policy decision — it fails the whole
  request with top-level `rejected`. A policy hold (DLP/type-disallow/size-cap,
  including today's no-screener-fail-closed) is `queued_for_human`.
  Per-attachment outcomes are diagnostic detail under **one** governing
  top-level outcome — they never license a partial-send.

## 5. Inbound — deliver-notice (runtime → agent)

The runtime writes one notice per **delivered** (not quarantined) message.
Quarantined/unverified mail produces **no notice** (logged runtime-side, never
seen by the agent). The notice is a *pointer + summary*; the body is fetched on
demand by the connector's read surface and is **untrusted content**.

```json
{
  "contract_version": "2",
  "notice_id": "...",
  "ts": "...",
  "kind": "deliver",
  "message": {
    "id": "<provider message id>",
    "from": "Name <addr>",
    "subject": "",
    "preview": "",
    "mailbox": "inbox",
    "task_id": "<runtime-minted; see §6>",
    "thread_id": "<provider/RFC thread id>",
    "in_reply_to": "<RFC822 Message-ID>",
    "references": ["<...>"],
    "sender_standing": "known",
    "provenance": "external",
    "verdict": { "auth": "dmarc-pass", "screen": "clean", "entitlement": "..." },
    "attachments": [
      { "filename": "invoice.pdf", "media_type": "application/pdf",
        "size_bytes": 12345, "disposition": "unscanned" }
    ]
  }
}
```

**Obligations:**
- A connector relays only `deliver` notices. **Drop rule (v3.0.0):** it
  MUST drop, not surface, a notice that fails **either** of two independent
  checks — schema validation, and the `content_ref` index/prefix binding
  defined later in this section — treating a failure of either one alone as
  sufficient grounds to drop. **This is not a pure closure over schema
  validation**, despite this section describing it that way in an earlier
  revision: the second check binds two fields of the same document (a
  descriptor's `content_ref` against the enclosing document's own
  `notice_id` and the descriptor's own array position) against each other,
  which is not expressible in the JSON Schema vocabulary this contract's
  schemas use, so it cannot be folded into "fails schema validation" no
  matter how the schema is phrased — it is a second, independent condition,
  not a special case of the first. See the correction below for what this
  replaces.
  1. **Schema failure.** The notice fails validation against
     `schemas/deliver-notice.schema.json` for **any reason other than an
     unrecognized member** — this single formulation covers
     `kind != "deliver"`, a missing required member, an enum violation on a
     closed vocabulary, a pattern violation (including a traversal/charset
     violation in `notice_id`, or a shape violation in `content_ref`'s own
     pattern), a conditional (`allOf`/`if`-`then`) violation, and a type
     violation alike, with no need to enumerate schema-failure categories
     separately. **An unrecognized member is never grounds for a drop**
     (v3.0.0, §7) — that is the failure mode this release closes, and it is
     the one carve-out from "fails schema validation" above.
  2. **The `content_ref` index/prefix binding.** A notice can pass check 1
     — every field individually well-shaped — and still carry an attachment
     descriptor whose `content_ref` does not equal
     `f"{notice_id}.attachments/{i}"` for its own 0-based array position
     `i` (below): a mismatched trailing index, or a leading `notice_id`
     prefix pointing into a *different* notice's sidecar directory. A
     connector MUST run this check independently of schema validation and
     drop the notice on failure exactly as it would a schema failure —
     enforced by the conformance gate as a named post-check
     (`fixtures/validate.py`'s `_check_content_ref_index_binding`), not by
     the schema, and pinned by
     `invalid/notice-attachment-ref-index-mismatch.json`, which is
     schema-valid on its own (zero errors from the gate's `validate()`) and
     fails only this check.

  A **version refusal** (absent or non-matching `contract_version` major)
  is explicitly **not** part of this drop path: it is handled first and
  separately, by §7's version-check-ordering rule, as a distinct logged
  outcome — a connector checks the version before it ever reaches schema
  validation, so a version-refused notice never falls into this rule at
  all. This two-condition rule is exact against the fixture set: it is what
  every `invalid/notice-*` fixture other than `notice-version-1` tests
  (§7.1) — ten of the eleven others fail check 1 (schema validation);
  `notice-attachment-ref-index-mismatch` is the one exception, passing
  check 1 outright and failing check 2 alone. **Correction:** an earlier
  revision of this bullet, and of §7.1, described the whole drop rule as a
  pure "closure over schema validation" and claimed it was "exact against
  the fixture set" and "exactly the set of the other nine
  `invalid/notice-*` fixtures" — both statements were refuted by this
  release's own `invalid/notice-attachment-ref-index-mismatch.json`
  fixture, which the two sections' own drop rule (as literally written,
  schema-only) did not actually require a connector to drop. The rule
  above is the fix: two named conditions, not one, stated as such in both
  places.
- Required message fields: `id, from, subject, preview, mailbox`. The rest are
  enrichment (see §8).
- `sender_standing ∈ {known, agent-tier, first-contact, read-only, ...}` — an
  **open, advisory vocabulary**: how the values are *computed* is runtime
  policy, out of scope here, and the wire only fixes today's known vocabulary
  so a connector can tell the agent "stranger / agent / needs sign-off." A
  connector MUST tolerate a value outside this list, treating it as opaque —
  never grounds to drop the notice (v3.0.0; see the tolerance-for-values rule
  in §7) — and a runtime may add a value as a MINOR change.
- `message.provenance ∈ {external, internal, ...}` (optional) classifies the
  message source so a runtime can route provenance-labelled screening.
  Advisory metadata — like `verdict`, never a license for the agent to obey
  body content. Also an **open, advisory vocabulary** (v3.0.0): a connector
  MUST tolerate a value outside this list, treating it as opaque, and MUST
  NOT drop the notice on its account; a runtime may add a value as a MINOR
  change.
- `verdict` carries the upstream auth/screen/entitlement result the runtime
  consumed; a connector treats it as advisory metadata, never as license for the
  agent to obey body content.
- **The untrusted-content posture covers every sender-originated string in
  the notice and the spooled message** (v3.0.0) — `message.from`, `subject`,
  `preview`, `body_text`, `references`, attachment `filename`/`media_type`,
  and the inbound-message `from`/`to`/`cc`/`subject` — not only the fields
  called out individually below. `message.from` gets the explicit sentence
  the others already have: its display-name half is chosen freely by the
  sender (`"security@yourbank.example <attacker@evil.example>"` is a legal
  value), it MUST NOT be used for any trust decision or rendered to a human
  or agent as verified identity, and verified sender identity is only ever
  what the runtime summarizes into `sender_standing`/`verdict` — never the
  `from` string itself. (The one exception in the protocol is the
  peer-origin profile's `message.from` on a `peer` notice, which the runtime
  asserts — `spec/peer-origin.md` §3. It never applies to a `deliver`
  notice.)
- **`message.attachments[]`** (optional) is the shared descriptor
  (`filename`, `media_type`, `size_bytes`) plus `disposition ∈ {clean,
  stripped, quarantined, unscanned}`. `disposition` is **the runtime's
  assertion, not a scanner verdict**. On what basis a runtime asserts `clean`
  is deliberately unspecified — a screening pipeline's pass in one deployment,
  a closed operator-supervised topology in another; that is runtime policy,
  out of scope for the wire, the same posture `sender_standing` takes above
  (the wire fixes the vocabulary, never the computation). The runtime is
  trusted by construction (§1); the load-bearing invariant is that the
  *agent* is not. The counterpart obligation is equally plain: **a runtime
  that cannot make the determination MUST NOT assert `clean`** — it emits
  `unscanned` (or `stripped`/`quarantined` where it made that decision) and
  publishes no bytes. A runtime MAY publish an attachment's bytes at
  `notices/<notice-id>.attachments/<index>` **only** for a descriptor it
  asserts `disposition == "clean"`, and only then MAY it emit `content_ref`
  (a path of the form `<notice-id>.attachments/<index>`) and `sha256`.
  **`content_ref`'s leading `notice_id` prefix MUST equal the enclosing
  document's own `notice_id`, and its trailing `<index>` MUST equal the
  descriptor's own 0-based array index (v3.0.0)** — the array index remains
  the sole binding authority (§2), and a consumer that resolves bytes MUST
  derive the path from the enclosing `notice_id` and the index, never trust
  the `content_ref` string's own text as the path (a descriptor could
  otherwise point into another notice's sidecar directory). This is a
  wire-shaped, document-level obligation and is enforced by the conformance
  gate as a named post-check (`fixtures/validate.py`'s
  `_check_content_ref_index_binding`; see
  `invalid/notice-attachment-ref-index-mismatch.json`), the same way the
  result-side `attachments[i].index == i` binding is. `content_ref` is the
  runtime's access grant for published clean bytes; exposing `sha256` on a
  withheld item would be a confirmation oracle for no integrity value, so it
  stays clean-gated too. Byte-absence remains the gate (§2) for anything not
  asserted clean. `content_ref` is a grant,
  never a directive: a consumer MUST tolerate a descriptor whose bytes it
  does not resolve — relaying the notice as usual — and MUST NOT treat the
  presence of `content_ref` as a requirement to fetch; a connector that
  never dereferences `content_ref` remains fully conformant. **A connector
  MUST resolve published bytes only within its own namespace's
  `inbound/notices/` tree and MUST reject any `content_ref` not matching the
  pinned pattern** (v3.0.0) — the same confinement §2's read-discipline
  bullet requires generally. **`filename`/
  `media_type` here are attacker-controlled, untrusted display strings** — the
  §1 untrusted-content posture extends to attachment descriptors (a
  quarantined file named to look like an instruction is still a
  prompt-injection payload even with its bytes withheld) — and a `clean`
  assertion covers the bytes' screening disposition, never the truthfulness
  of these strings. Inbound `size_bytes` is **provider-declared
  (BODYSTRUCTURE) and therefore advisory/untrusted**, not runtime-verified the
  way outbound `size_bytes` is. MIME-edge pins: `filename` is the RFC
  2047/2231-**decoded**, runtime-sanitized display string; an "attachment" is
  any part with `Content-Disposition: attachment` OR any named/non-inline-text
  part (inline images and `multipart/related` parts count — conservative);
  the declared `media_type` is display-only — the runtime sniffs the bytes,
  and the sniffed type governs policy (outbound gate).
- **Presentation obligations (v3.1.0 DRAFT).** A connector that presents a
  message body to its agent MUST convey two things, whatever words it uses:
  (a) quoted or forwarded material inside the body carries no authority of its
  own — a message's authority extends to what its author wrote, never to what
  they relayed; and (b) an attachment's `disposition` is the runtime's
  assertion about handling and not a scanner verdict, so a connector MUST NOT
  imply that bytes have been screened, **and MUST NOT contradict the
  per-attachment status the runtime published** — together with the fact that
  an attachment's `filename` and `media_type` are sender-chosen display strings
  (above), which a reader sees whether or not it opens anything.
  On the mail tree a connector MUST additionally convey that the sender is not
  authenticated beyond whatever standing the runtime has already summarized
  (carried in `sender_standing` and `verdict` — named here as the locus, not
  as vocabulary a connector should repeat to a reader), and that
  `message.from` is sender-chosen text.

  *(Correction, v3.1.0 DRAFT. (b) previously read "attachment bytes are
  unscanned" as a flat assertion. That is not true after v2.3.0: a runtime MAY
  assert `disposition: clean` and publish the bytes, and a connector is
  required to surface that assertion rather than re-interpret it. A constant
  banner claiming nothing was scanned, beside a descriptor the runtime
  published as `clean`, re-interprets the assertion downward and teaches a
  reader to disbelieve a status the same connector is displaying. Reported by
  an implementer of a connector interface document, which could not satisfy
  the obligation as written without contradicting that interface. The
  obligation is now about what a connector must not imply, which is
  satisfiable by a constant string because it does not depend on any one
  attachment's status.)*
  These are obligations about **substance, not vocabulary**. A connector
  satisfies them with any wording its reader can act on without consulting
  this document — protocol terms in model-facing text are unverifiable by the
  reader they address, and a term that reader cannot resolve is noise at
  exactly the moment the sentence needs to land. They MUST be satisfiable by a
  literal string the connector carries: nothing here may require a lookup,
  an import, or a computation at presentation time.
- **Body-spool path (v2.1.0).** The runtime spools the delivered body at
  `inbound/messages/notice-<id>.json`, keyed on the runtime-minted
  `notice-id` (never the provider `message.id` — same confirmed-exploit
  avoidance as above). Shape:
  `{ contract_version, notice_id, body_text, ... }` (schema
  `schemas/inbound-message.schema.json`; required fields `contract_version,
  notice_id, body_text`; the rest — `id, date, from, to, cc, subject,
  attachments[]` — is enrichment, see §8). The connector's read surface
  resolves `notice-id → body` from this artifact only, never from a
  provider fetch; the body is **untrusted content**, same posture as the
  rest of `message`. Enforcement-by-absence extends here: a body the
  runtime withholds (screening/quarantine, or the message was never
  delivered) is simply not spooled, and a read against a missing artifact
  returns "not resolved" — there is no other signal and no fallback fetch.
  The same "not resolved" response also covers an artifact the runtime later
  removes under its own retention policy (§2, "Deletion rights") — from the
  connector's side, retired and never-spooled are indistinguishable, and
  both are already-specified behavior.

## 6. Task correlation — obligations on `task_id`

The runtime mints and owns `task_id`; the connector only reads it to correlate a
notice with prior work. The wire fixes these **security obligations** on it (the
minting/thread-resolution *algorithm* is runtime policy, out of scope here):

- `task_id` MUST be **unguessable and runtime-minted** (e.g. an HMAC over the
  thread root) — **never** a sequential/guessable value, and **never** a
  capability an inbound sender can assert. *(A guessable/sequential `task_id`
  was a confirmed exploit path in an early implementation.)*
- Matching a `task_id`, by itself, MUST NOT grant a message entry into that task.
  Authoritative correlation is header-threading **plus** per-message verified
  sender identity; a `+subaddress`/header token is an inbound *hint* only, never
  authoritative (attacker-controllable, and stripped by many gateways).
- Threading grants **correlation, not trust**: a message that threads onto a
  known task is still identity-verified per message; it does not inherit the
  task's standing.

## 7. Versioning and conformance

- **`contract_version`** is a major-version string. A consumer that reads a
  **higher major** than it speaks MUST **fail closed** (refuse to process),
  never silently mis-parse.
- **Version-check ordering (v3.0.0).** A consumer implements the version
  check by reading `contract_version` **before** any schema validation,
  comparing majors as non-negative decimal integers. An absent or lower
  major, or a higher major, is a **version refusal** (fail closed) — a
  distinct, logged outcome, never folded into the malformed-document drop
  path (§5). Checking the version first is what makes fail-closed
  implementable at all: a validator that runs schema checks first cannot
  distinguish "wrong version" from "malformed," and a strict schema would
  reject a future-major document for the wrong reason. This rule is about
  *inbound* artifacts a connector consumes (§5), which have no wire
  mechanism to carry a distinct outcome back to the runtime. It does not
  reach the *outbound* direction: a runtime version-refusing a submit-request
  MAY — and, per §7.1, MUST for `invalid/request-version-absent.json` — carry
  that refusal on the ordinary request-rejection path (§4), a top-level
  `rejected` result with `reason_code: "unsupported_contract_version"`. That
  is still a distinct, legible outcome, not a fold into the malformed-request
  case: `reason_code` is exactly the wire's mechanism for saying *why* a
  `rejected` fired, and a connector MUST already tolerate a `reason_code` it
  does not otherwise interpret (§4). A runtime has no equivalent wire
  document to write for a version-refused *notice* it never emits — hence
  the asymmetry: logged-only inbound, `rejected` outbound.
- **Wire `contract_version` is now `"2"` (MAJOR bump from `"1"`, when
  attachment support was added).** *(As of v3.0.0 this bullet is historical: at the time of the
  "1"→"2" transition, every top-level schema and every nested object except
  `verdict` and `attestation.claims` was `additionalProperties:false` — see
  the v3.0.0 bullet below for the standing rule as of this version.)* Nearly
  every schema in this repo was `additionalProperties:false`, so
  adding a field is not a safe additive change the way it would be under a
  permissive envelope: a strict major-1 validator rejects the **whole
  document**, not just the new field. Inbound, that is **silent total message
  loss** (an attachment-bearing email vanishes instead of degrading);
  outbound, it is an accidental schema error, not a designed refusal. There is
  no wire signal to gate on while `contract_version` stays `"1"` — the new
  field is invisible to anything that would need to react to it. **Therefore
  this is a MAJOR bump, not a minor one.** A major-1 consumer that receives a
  `"2"` document now hits fail-closed **by version** — a legible, designed
  refusal — and both sides upgrade deliberately, instead of an unrelated
  unknown-field rejection standing in for a version check it was never meant
  to be. Explicitly deleted: any framing that `additionalProperties:false`
  rejection **is** the version boundary — that conflates two different axes
  (schema strictness vs. protocol version) and produces catastrophic behavior
  (whole-document loss) where a version check should produce a legible
  refusal instead.
- **At major 2, `contract_version` is REQUIRED** on submit-request,
  deliver-notice, and result (schema `const: "2"`). A v2 consumer **MUST
  refuse** any protocol artifact whose `contract_version` is absent or names a
  lower major — there is no compatibility mode. (`binding-record` is the one
  exception: it stays optional end-to-end — see §9 — because the file itself
  is optional and informational, not a protocol artifact a consumer must
  parse to function.)
- **SemVer for the contract:** additive, backward-compatible field ⇒ minor bump;
  any change that breaks an existing fixture ⇒ major bump, taken deliberately by
  both sides.
- **v2.1.0 was additive: a MINOR bump.** It adds one new
  *optional* spooled artifact (`inbound/messages/notice-<id>.json`, §5) and
  its schema (`inbound-message.schema.json`), plus one new *optional* field —
  `message.provenance ∈ {external, internal}` on the deliver-notice (§5) —
  for provenance-labelled screening; and three new *optional* fields on the
  result (§4) — `reason_code` (machine-readable policy-path marker),
  `attestation` (the runtime's self-stamp/verifiable identity stamp on the
  outbound message), and `ts` (of-record verdict time); no existing schema
  gained a required field, no existing fixture changed shape, and wire
  `contract_version` stays `"2"` — v2.1.0 is a documentation/layout + schema
  addition on top of major 2, not a new wire major. A v2.0.0 connector that
  never looks for the new artifacts or fields continues to work unmodified; a
  v2.0.0 runtime that never writes them produces exactly today's behavior
  (body read returns "not resolved"; notice carries no `provenance`; result
  carries no `reason_code`/`attestation`/`ts`).
  **Correction (v3.0.0):** this bullet's "additive: a MINOR bump" claim was
  unsound as written. Against a strictly-validating v2.0.0 connector — every
  schema at that version was `additionalProperties:false` at every level —
  a notice carrying the new `provenance` member failed schema validation as
  a **whole document** and was silently dropped: exactly the failure §7
  cites below as the reason attachments required a MAJOR bump in the
  "1"→"2" transition, reintroduced here as a minor. v3.0.0 repairs the
  versioning model (below) rather than relabeling this history; the bullet
  above is left as originally written because it is what shipped, not
  because it was correct.
- **v2.2.0 was permissive: a MINOR bump.** No wire field, no
  schema change, no fixture changed or added — wire `contract_version` stays
  `"2"`. It (a) declares read-only inbound a valid runtime posture and makes
  `inbound/notices/processed/` OPTIONAL, (b) obliges a connector not to
  require inbound write access (consumption-recording becomes
  connector-private), and (c) names deletion rights per artifact class (§2)
  — which also states two constraints attached to those rights: a connector
  MUST NOT delete or rewrite a published request (a restatement of §2's
  commit sentinel), and a connector exercising its new deletion rights MUST
  preserve `req_id` monotonicity by other durable means. No reference
  implementation does either thing today. It also pins three
  previously-implicit `reason_code` rules (§4): the recommendation to set one
  on every result becomes a keyworded SHOULD, and a consumer MUST tolerate an
  unrecognized code and MUST NOT infer `outcome` from it — all three were
  already the only reading consistent with an extensible, non-enum-locked
  field, so no conformant consumer changes behavior.
  A v2.1.0 runtime that mounts inbound writable, and a connector that keeps
  archiving to `processed/` there, remain conformant unmodified. A connector
  that today *crashes* on a read-only inbound was already broken against any
  runtime enforcing inbound integrity; under v2.2.0 that is a tracked
  **implementation conformance gap** (same framing §8 already uses for
  missing `contract_version` emission), not a fixture break.
- **v2.3.0 is permissive: a MINOR bump — prose only.** (Bullets here are
  historical and are written in the past tense; the current document version
  is the one in the title, so no bullet needs re-editing when the next one
  lands.) No
  schema rule and no fixture changed or added; wire `contract_version` stays
  `"2"`. It resolves an inconsistency this document has carried since v2.0.0:
  `fixtures/valid/notice-attachment-clean-ref.json` — a notice whose
  descriptor carries `disposition:"clean"` with `content_ref` + `sha256` —
  sat in the **valid** set as a deliberately forward-valid shape, and this
  section names the fixtures as the conformance authority, while §2/§5 prose
  forbade any runtime from producing it ("this release … never
  `content_ref`"). The gate blessed what the prose forbade. v2.3.0 sides with
  the fixtures: the release-scoped byte embargo is dropped, and §5 now states
  the standing rule — a runtime MAY publish bytes and emit
  `content_ref`/`sha256` only for a descriptor it asserts `clean`, and a
  runtime that cannot make that determination MUST NOT assert `clean`. The
  substantive clarification: `disposition` is the runtime's **assertion**,
  its basis deliberately unspecified (runtime policy, not wire) — the old
  prose presumed a scanner, which is what made byte-access read as a deferred
  capability rather than a policy decision whose wire shape major 2 already
  carried. Nothing is tightened: a runtime that keeps emitting descriptors
  only remains conformant unmodified, and the one consumer rule now pinned
  (§5: tolerate an unresolved `content_ref`; never treat its presence as a
  fetch obligation) is the only reading §8 ever admitted for an optional
  field — the same move v2.2.0 made for `reason_code`. Outbound is unchanged:
  there is still no outbound `content_ref` (§3), and
  `request-attachment-content-ref`, `notice-attachment-ref-not-clean`, and
  `notice-attachment-traversal-ref` stay invalid.
- **v3.0.0 is a MAJOR bump — direction-aware tolerance (members AND values),
  and six closed safety/discipline holes; wire `contract_version` stays
  `"2"`.** Judged against this section's own rule (*"any change that breaks
  an existing fixture ⇒ major bump"*): `invalid/notice-extra-field.json`
  moves to the valid set (`valid/notice-unknown-member.json`) — a fixture
  break, full stop — `invalid/message-withheld-body-present.json` is deleted
  because it becomes schema-valid under the relaxed envelope, and
  `invalid/notice-bad-provenance.json` moves to
  `valid/notice-provenance-unrecognized-value.json` under the value-tolerance
  extension below. The submit-request recipient/subject/filename/header-field
  tightening shrinks the valid document class for connectors emitting
  display-name recipients or control characters (no shipped fixture broke,
  but the class did), and the `notice_id` charset tightening (Item 4, below)
  shrinks the valid identifier class for a runtime minting ids outside the
  new pattern (also no shipped fixture broke, since no fixture pinned the
  old, unconstrained shape — but real deployments can mint such ids; see
  below). And Items 2, 4, and 5 below add runtime MUSTs that a
  strictly-compliant v2.x runtime does not meet. "Permissive minor" would be
  dishonest — this release exists to add obligations, and both reference
  implementations are non-conformant against it by design (they carry
  exactly the bugs these rules close). **Why the wire major does not move:**
  the wire major exists to force a legible fail-closed refusal when the
  *whole document* a counterpart already accepts would otherwise be silently
  misread or silently dropped — the catastrophic, undetectable failure mode
  a version bump exists to convert into a designed refusal. This release
  does **not** claim producer bytes are unchanged — they are not, on both
  sides named above — but neither narrowing is that failure mode: each
  travels a designed, legible, per-artifact refusal path this section has
  always sanctioned, not a whole-document rejection triggered by an
  unrelated field. The submit-request tightening yields a per-request
  `rejected` result (§4); the `notice_id` tightening yields a per-notice
  connector-side drop (§5's drop rule, check 1) — a real cost,
  disclosed below, but a narrow and legible one, not silent total loss.
  Bumping the wire to `"3"` would instead force every v2 counterpart on
  **both** sides to refuse **all** traffic outright, including all the
  traffic the tolerance rule below newly protects — inflicting exactly the
  catastrophic, undisclosed mail loss this release exists to repair, to fix
  incompatibilities that already have narrower, disclosed failure paths.
  **Standing rule (new for this repo): the wire major tracks whole-document
  acceptance compatibility; the contract's own SemVer tracks the fuller set
  of obligations, including narrower, disclosed producer-side tightenings
  that do not rise to that level.** The two are allowed to diverge, and this
  release is why.
  - **The versioning model's silent-loss mandate, closed — for members.**
    The rule is direction-aware. **Runtime-authored artifacts —
    deliver-notice, inbound-message, result — consumers MUST ignore members
    they do not recognize, at every level of the document, and MUST NOT
    reject, drop, or fail the artifact on their account.** Strictness on
    this direction defended nothing (the producer is trusted by
    construction; in the one posture where an attacker can author a notice —
    writable inbound — it can author a fully schema-valid one, so
    strictness here was never a defense) and its failure mode was silent mail loss. Emitting
    an unknown member remains a **producer** non-conformance: a runtime
    MUST NOT emit members undefined at the contract version it claims.
    **The submit-request envelope stays closed**
    (`additionalProperties:false`, unchanged, every level): there, closure
    is doing real security work (it is what bars an outbound `content_ref`
    and any smuggled member), the validator is the trusted runtime, and a
    refusal is a *legible, per-request* `rejected` result — never silent
    loss. A runtime MUST reject a request carrying unrecognized members.
    Consequently: adding an optional field to a runtime-authored artifact is
    genuinely additive (MINOR); adding any field to the submit-request is a
    MAJOR change. `verdict`'s already-open-object tolerance (§5) is no
    longer "the only place in the protocol where that is so" — that framing
    is retired; it is now one instance of the general v3.0.0 rule. Schemas:
    `additionalProperties: false` is removed from
    `deliver-notice.schema.json`, `inbound-message.schema.json`, and
    `result.schema.json` at every level (top level, `message`,
    attachment-descriptor items, `attestation`); the `allOf` clean-gating
    conditionals are orthogonal and stay. `submit-request.schema.json` and
    `binding-record.schema.json` are unchanged on this axis — the latter's
    closure is an anti-secret-leak lint (the `imap_password` fixture), not a
    compatibility surface, so it stays closed for a different reason than
    submit-request does.
  - **...and for values.** The tolerance rule extends to enum *values*, not
    only members. An optional, explicitly advisory enum on a
    runtime-authored artifact — `message.sender_standing` and
    `message.provenance` (§5) — is scoped the same way: a consumer MUST
    tolerate a value it does not recognize, treating it as opaque (or as the
    field being absent), and MUST NOT reject, drop, or fail the artifact on
    that account; a runtime MAY add a value to either vocabulary as a MINOR
    change. This closes the same failure mode one indirection over: without
    it, a runtime adding a fifth `sender_standing` or a third `provenance`
    value would silently lose every notice carrying it, against every
    connector still validating the old enum — identical to the member case
    above, just at the value level. This is **not** a universal loosening of
    every enum: `kind`, `outcome` (top-level on `result`, and per-attachment
    in both `result.attachments[]` and the notice/message attachment
    descriptor's `disposition`) stay **closed, enum-locked vocabularies** —
    `kind` and `outcome` gate which processing path a document takes at all,
    and `disposition` gates byte publication (§5), so a new value in any of
    these is a behavioral fork a consumer cannot safely treat as opaque, and
    introducing one is a MAJOR change, unlike `sender_standing`/`provenance`.
    Schemas: the `enum` constraint is removed from `message.sender_standing`
    and `message.provenance` in `deliver-notice.schema.json`; `kind`,
    `outcome`, and `disposition` are unchanged. Fixture:
    `invalid/notice-bad-provenance.json` moves to
    `valid/notice-provenance-unrecognized-value.json` — it tested exactly
    this now-tolerated case.
  - **Ingest-by-copy (Item 2)** — §2, new bullet — closes the safety property
    that sat on the untrusted side: a runtime must validate, evaluate policy
    on, and compose from a private staged copy, never the live agent-writable
    path.
  - **Address syntax and header-injection discipline (Item 3)** — §3, new
    bullet, plus schema patterns on `draft.to`/`cc`, `draft.subject`,
    `draft.attachments[].filename`, `draft.attachments[].media_type`,
    `draft.reply_to_message_id`, `in_reply_to`, `agent_id`, and `ts` — closes
    the missing outbound-reach constraint, including on the two fields
    composed directly into headers (`reply_to_message_id` →
    `In-Reply-To:`, `media_type` → a MIME part's `Content-Type:`) that an
    earlier revision's narrower schema coverage missed.
  - **Path discipline, write- and read-side both (Item 4)** — §2: the
    write-side rule ("Filename ids are the authority for paths") is now
    **conjunctive**, and the pinned-directory-descriptor walk
    (`openat`/`mkdirat`/`renameat` off a descriptor pinned per namespace,
    each component opened `O_NOFOLLOW|O_DIRECTORY` while the chain is built)
    is **ADDED TO** — not substituted for — the exclusive-create/
    no-symlink-follow discipline the write-side rule already required at
    v2.3.0: the final `.tmp` component must still be created `O_EXCL` and
    never followed. **Correction:** a prior revision of this bullet said the
    old exclusive-create/no-symlink-follow requirement was "strengthened…
    to" the descriptor walk, i.e. replaced by it — that revision deleted the
    v2.3.0 clause outright rather than adding the new requirement alongside
    it, which was a **regression**, not a strengthening: a parent chain
    pinned by descriptor is silent about the final `.tmp` filename itself,
    so dropping exclusive-create there let an agent that pre-plants a
    symlink at a predictable `.tmp` name (e.g. `results/<id>.json.tmp`) have
    the runtime write through it. Both halves are required together — a
    pinned parent chain the runtime never verified it acquired
    symlink-free, and a final-component write with no exclusivity check, are
    two independent gaps, and closing one does not close the other. A new
    read-side bullet applies the equivalent discipline to every
    agent-influenceable read. All three needed the stronger statement:
    a path-based containment check followed by a path-based act is a
    parent-directory-swap race whichever direction it runs, and a "pinned"
    descriptor is only as trustworthy as the open that produced it. Plus a
    `notice_id` charset pattern (`deliver-notice.schema.json`,
    `inbound-message.schema.json`,
    `^[A-Za-z0-9_][A-Za-z0-9_.-]*(?!\n)$`) so every
    legal `notice_id` is also a legal `content_ref` prefix. **Disclosed
    cost:** prior to this version `notice_id` was unconstrained
    (`{"type":"string","minLength":1}`). A runtime minting ids outside the
    new pattern — an ISO-8601 timestamp (`:`), standard base64 (`+`, `/`,
    `=`), a URN (`:`), or any id containing those or other punctuation — now
    emits deliver-notices and inbound-messages that fail schema validation
    on a **pattern violation on a required member**, not an unrecognized
    one: per §5's drop rule check 1 (above), a v3.0.0 connector
    drops such a notice. **Migration: a runtime whose existing `notice_id`
    minting scheme falls outside `^[A-Za-z0-9_][A-Za-z0-9_.-]*(?!\n)$` MUST
    re-mint ids under the new charset (e.g. base64url without padding, or
    lowercase hex) before any connector it talks to upgrades its schema
    validation to v3.0.0** — the failure is silent on both sides otherwise
    (the connector drops the notice with no signal; the runtime gets no
    feedback that its ids are being rejected).
  - **Single writer, single drainer (Item 5)** — §2, new bullet — states the
    concurrency assumption every atomicity/commit-sentinel/`req_id` rule in
    this document already depended on but never named.
  - **`message.from` named untrusted (Item 6)** — §5 — extends the
    already-explicit untrusted-content sentence to the field most likely to
    be rendered to a human or used for a trust judgement.
  - **Document authority (Item 7)** — the header of this file now states
    that `spec/` + `schemas/` + `fixtures/` are normative and `dist/` is a
    generated, non-authoritative rendering; the conformance-classes text
    below is ported in from `dist/` (adapted for the tolerance rule above)
    so demoting `dist/` deletes nothing; and the §2 sidecar-directory
    self-contradiction (a stray claim of a second, message-specific sidecar
    dir) is corrected to match the layout tree and §5.
  - **Fixture accounting:** 21 valid + 37 invalid = 58 fixtures (up from 44).
    `notice-extra-field.json` → `valid/notice-unknown-member.json` (moved,
    and extended with an unrecognized member inside `message` too);
    `valid/result-unknown-member.json` and `valid/message-unknown-member.json`
    added (pin tolerance on the other two runtime-authored artifacts);
    `invalid/message-withheld-body-present.json` deleted (schema-valid now;
    its name always over-claimed what `additionalProperties` alone tested);
    `invalid/notice-bad-provenance.json` →
    `valid/notice-provenance-unrecognized-value.json` (moved, per the
    value-tolerance extension above);
    `invalid/request-extra-field.json` added (pins the closed side of the
    asymmetry, previously untested at the top level);
    `invalid/request-recipient-display-name.json`,
    `invalid/request-subject-crlf.json`,
    `invalid/request-attachment-filename-crlf.json`, and
    `invalid/request-reply-id-crlf.json` added (Item 3);
    `invalid/notice-traversal-noticeid.json` added (Item 4's `notice_id`
    rider); `invalid/notice-attachment-ref-index-mismatch.json` added (pins
    the `content_ref` index/prefix binding named in §5, enforced by
    `fixtures/validate.py`'s `_check_content_ref_index_binding` post-check —
    and, per the drop-rule correction in §5 and §7.1, this fixture is the
    one `invalid/notice-*` case that is schema-valid on its own and fails
    only that post-check, not schema validation). **Trailing-newline
    closure:** every pattern in this repo anchored with a trailing `$`
    admitted one trailing `\n` under a permissive (non-ECMA-262) regex
    engine — Python `re`, Java, and .NET all treat `$` as matching before a
    single trailing newline by default, unlike the ECMA-262 dialect JSON
    Schema specifies. Every schema pattern ending in `$` now ends in
    `(?!\n)$` instead (`submit-request.schema.json`,
    `deliver-notice.schema.json`, `inbound-message.schema.json` — the
    control-character patterns from Item 3, the address pattern, both
    `sha256` patterns, and the `notice_id`/`content_ref` patterns from Item
    4 alike), which is portable ECMA-262 syntax and closes the gap in
    the schemas themselves rather than in this gate's validator — so an
    implementer's own permissive engine (Python `re`, .NET) rejects what
    ours does. Two caveats, stated rather than glossed. Java's
    `Matcher.find` treats `$` the same permissive way and honours the
    lookahead, so it is covered. But **lookahead-less engines cannot
    compile these patterns at all**: RE2 (Go's `regexp`), Rust's `regex`
    crate, and POSIX ERE reject `(?!` outright, so the three schemas
    carrying the guard fail to load rather than validating loosely. Those
    engines already treat `$` as strict end-of-string and never had the
    gap, so an implementer on one of them MUST strip the lookahead — not
    add a check outside the pattern, which would be both unnecessary and
    not what breaks. The failure is loud (a compile error, never silent
    acceptance), but it is a portability cost this guard imposes and is
    recorded here rather than discovered. Six fixtures pin the
    specific trailing-newline case, distinct from the existing CRLF
    fixtures (which embed `\r\n` and were already rejected even under a
    permissive engine, so they never covered this):
    `invalid/request-subject-trailing-newline.json`,
    `invalid/request-recipient-trailing-newline.json`,
    `invalid/request-attachment-media-type-trailing-newline.json`,
    `invalid/request-reqid-trailing-newline.json`,
    `invalid/notice-notice-id-trailing-newline.json`, and
    `invalid/notice-attachment-content-ref-trailing-newline.json`.
- **v3.1.0 (DRAFT, uncommitted) is additive: a MINOR bump; wire
  `contract_version` stays `"2"`.** It carries the peer-origin profile
  (`schemas/peer-notice.schema.json`, the `peer-*` fixtures, and
  `spec/peer-origin.md`) and, in core, the tree rules and the `outbound/ext/<name>/`
  extension-space convention (§2) with one normative clarification adjacent
  to it: an outcome written there is a claim by the receiving side, never
  proof of delivery or non-delivery, and the runtime's own delivery record
  is authoritative over it. No existing schema rule or fixture changed.
- **v3.1.0 (2026-09-15): the protocol is AMAP; the schema `$id` authority is
  `amap-spec`.** The protocol formerly called AMP ("Agent Mailbox Protocol")
  is renamed AMAP ("Agent Mailbox Access Protocol") because AMP collides with
  the IETF DTN working group's adopted `draft-ietf-dtn-amp`; this repository
  moves from `agent-mailbox-protocol` to `amap-spec` with it. The six schema
  `$id` values move from `https://agent-mailbox-protocol/schemas/…` to
  `https://amap-spec/schemas/…`. Nothing on the wire changes shape: no
  document carries the protocol's name as a field, and `$id` is an identifier
  the gate never dereferences. Implementations that mirror the runtime's
  address spell its local part `amap.router` from this version (the fixtures
  do); the IETF draft filename under `dist/` is a separate, counsel-facing
  decision and is not renamed here.
- **Peer directory (`directory.json`) added — v3.1.0 DRAFT.** A runtime MAY
  publish a per-instance projection of the authorisation graph at the agent's
  namespace root (§10), so a connector can learn which peers it may address
  without the host rendering a snapshot onto an agent-writable mount that goes
  stale whenever the fleet changes. Requested by a deployment whose conformance
  harness had caught an agent reading such a snapshot as a PREDICTION of what
  the runtime would do. That is a category error rather than a staleness bug —
  a fresher file only makes the wrong reading right more often — so the artifact
  is specified as advisory and never authoritative, and a runtime is forbidden
  to read it back as authorisation, which is the clause that stops it decaying
  into an allowlist the agent can see. Additive: new optional artifact, new
  schema, seven fixtures, no existing schema or fixture changed, wire
  `contract_version` stays `"2"`. The namespace root gains a runtime-owned
  posture for runtime-written files (§2) — the file sits beside the lanes
  rather than inside one, because it spans both and a lane-scoped home would
  oblige a delegation-only deployment to materialise a mail tree it does not
  need.
- **`outbound/ext/<name>/`'s `<name>` is pinned as a stable connector id
  (v3.1.0 DRAFT).** As first drafted, `<name>` was "a connector or
  deployment name", which pinned nothing and permitted the connector's
  repository name. That is how a repository name leaks into a wire-visible
  path: rename the repository and either the path moves — breaking the
  out-of-band agreement the directory exists to carry — or it stays and now
  contradicts its own source. The bullet in §2 now requires the id to be
  chosen once, to survive a repository or deployment rename, and to be
  opaque to the runtime that reads it. The first id is `claude-code`,
  chosen by the reference Claude Code connector. This is a tightening of
  prose that was never mechanically checkable: `outbound/ext/` is a
  directory convention with no schema and no fixture — like
  `inbound/notices/processed/` (§2) — so the wording is the whole control,
  and no fixture moves (75 valid+invalid, 0 unexpected, unchanged by this
  edit).
- **A capability change starts here** — a PR against this repo adding fields +
  fixtures — *before* either implementation builds it. Neither a runtime nor
  a connector may invent a wire field locally.
- **Conformance = the fixtures, for wire-shaped obligations.** `fixtures/`
  holds golden artifacts; a producer or consumer proves conformance by
  passing them (`fixtures/validate.py`) with **no counterpart present**. The
  fixtures *are* the other side. Not every obligation in this document is
  wire-shaped: a *behavioral* obligation — one about how an implementation
  acts against a filesystem, rather than about the shape of a document — lies
  outside the fixture gate by construction and is checked operationally
  instead (§7.1's read-only-inbound check below is the prescribed example;
  `fixtures/validate.py`'s NOT-CHECKED docstring lists every obligation of
  this kind, including the ingest-by-copy, read-side open discipline, and
  single-writer/single-drainer rules v3.0.0 adds).

### 7.1. Conformance classes (v3.0.0)

This document defines two conformance classes. An implementation MAY claim
both. Claiming either without the corresponding fixture run, and without the
prescribed operational check for that class's behavioral obligations, is not
conformance. The peer-origin profile (`spec/peer-origin.md` §8) defines two
further sub-classes, *runtime + peer-origin* and *connector + peer-origin*,
each requiring the corresponding class here plus the profile's fixtures and
operational checks.

**Runtime conformance class.** An implementation claiming runtime conformance:
- MUST produce deliver-notice documents valid against
  `schemas/deliver-notice.schema.json` and result documents valid against
  `schemas/result.schema.json`, MAY produce inbound-message documents, which
  when produced MUST be valid against `schemas/inbound-message.schema.json`,
  and MAY produce a binding record valid against
  `schemas/binding-record.schema.json`.
- MUST consume submit-request documents: it MUST accept every
  `valid/request-*` fixture and MUST reject every `invalid/request-*`
  fixture.
- MUST demonstrate its producing side by confirming that its own emitted
  notices, results, and inbound messages satisfy the same schemas the
  suite's `valid/notice-*`, `valid/result-*`, and `valid/message-*` fixtures
  satisfy (**including** `valid/notice-unknown-member.json`,
  `valid/result-unknown-member.json`, and `valid/message-unknown-member.json`
  — a runtime MUST NOT itself emit unrecognized members, but its *parser*,
  exercised by those fixtures, is what a Connector conformance run depends
  on it never having to special-case), and that any binding record it writes
  satisfies the `valid/identity-*` shape.
- MUST uphold the filesystem and policy obligations of §§2–6 that no
  document validator can observe. These are listed explicitly in
  `fixtures/validate.py`'s NOT-CHECKED docstring as what a green fixture run
  does **not** prove, and they are obligations of the class regardless —
  write-side path discipline (the conjunctive parent-chain-pinning +
  no-follow-while-building + non-following-final-component rule), ingest-by-copy,
  read-side open discipline, and single-writer/single-drainer chief among the
  ones this version adds.

**Connector conformance class.** An implementation claiming connector
conformance:
- MUST produce submit-request documents valid against
  `schemas/submit-request.schema.json`, and MUST NOT emit an outbound
  `content_ref` (§3).
- MUST consume deliver-notice, inbound-message, and result documents: it
  MUST accept every `valid/notice-*`, `valid/message-*`, and `valid/result-*`
  fixture — **including those carrying unrecognized members or unrecognized
  advisory-enum values** (v3.0.0) — and MUST reject (drop, not surface)
  every `invalid/notice-*` fixture **except `notice-version-1`**, which it
  MUST instead refuse via the distinct version-refusal path (§7) — never
  folded into this drop path, and never surfaced to the agent either. §5's
  drop rule is **two independent conditions, not a pure closure over
  schema validation**: "fails schema validation for any reason other than
  an unrecognized member" (check 1) covers ten of the eleven other
  `invalid/notice-*` fixtures — missing-required-member, wrong-`kind`,
  enum, pattern, and conditional violations alike; the eleventh,
  `notice-attachment-ref-index-mismatch`, is schema-valid on its own (zero
  errors from the gate's `validate()`) and is caught only by the
  `content_ref` index/prefix binding (check 2, §5), a named post-check the
  schema cannot express. A connector conformance claim requires running
  both checks — schema validation alone does not close this set. Accepting
  `valid/notice-attachment-clean-ref` — a descriptor asserted `clean` and
  carrying `content_ref` and `sha256` — is part of this obligation, and
  acceptance means relaying the notice, not fetching the bytes: a connector
  that never dereferences `content_ref` satisfies it (§5).
- MUST return "not resolved" for a body whose inbound message is absent, and
  MUST NOT attempt any fallback fetch (§5).
- MUST tolerate a binding record that is absent, and MUST NOT crash or
  otherwise misbehave on one that is hostile or malformed (§9).
- MUST NOT require write access anywhere under `inbound/`, demonstrated by
  the operational check below rather than by a fixture (§2).
- MUST demonstrate its producing side by confirming that its own emitted
  requests satisfy the same schema the suite's `valid/request-*` fixtures
  satisfy, and MUST uphold the write-ordering, atomicity, and read-discipline
  obligations of §2, which the fixtures cannot check.

**Read-only inbound tolerance — the prescribed operational check (§2).** Run
the connector against an inbound tree it cannot write — a genuinely
read-only mount, not merely cleared permission bits, since a same-uid agent
can change a mode it owns — and confirm that it starts, relays every pending
notice, resolves bodies, and submits outbound requests, without requiring
any write under `inbound/` to succeed.

## 8. Required vs. optional (v3.0.0)

At v2.0.0, `contract_version` moves from optional-but-recommended to
**required** on every protocol artifact (submit-request, deliver-notice,
result) — see §7. The rest of this table still reflects what the reference
implementations emit today; the specified-but-unbuilt enrichment stays
optional. Tightening any of *those* to required is a future major bump,
tracked against the implementations — not asserted here as built.
v2.1.0 adds the **inbound-message** row (§5); it is itself an OPTIONAL
artifact (a runtime may not spool it yet, per §7). Profile artifacts are
tabulated in the profile (`spec/peer-origin.md` §9), not here.

| Artifact | Required (v2.0.0) | Optional (specified; may be absent) |
|---|---|---|
| **deliver-notice** | `contract_version, notice_id, ts, kind, message{id,from,subject,preview,mailbox}` | `message.{task_id, thread_id, in_reply_to, references, sender_standing, verdict, provenance}`, `message.attachments[]` (items require `filename, media_type, size_bytes, disposition`; `sha256`/`content_ref` optional, gated to `disposition=="clean"`) |
| **submit-request** | `contract_version, req_id, draft{to, subject, body_text}` | `agent_id, ts, in_reply_to, draft.{cc, reply_to_message_id}`, `draft.attachments[]` (items require `filename, media_type, size_bytes, sha256`) |
| **result** | `contract_version, req_id, outcome` | `detail, reason_code, ts, recipients, message_id, job_id, attestation` (requires `form`; `token`/`claims` optional), `attachments[]` (items require `index, outcome`) |
| **binding-record** (`identity.json`, §9) | *(the file itself is OPTIONAL — see §9)* if present: `agent_id, address, provisioned_ts` | `label`; `contract_version` (optional — if present, pinned `const "2"`, §9) |
| **directory** (`directory.json`, §10, v3.1.0 DRAFT) | *(the file itself is OPTIONAL — see §10)* if present: `router, written_at, delegate_to, mail_to` | `contract_version` (optional — if present, pinned `const "2"`, §10) |
| **inbound-message** (`notice-<id>.json`, §5, v2.1.0) | *(the file itself is OPTIONAL — see §5/§7)* if present: `contract_version, notice_id, body_text` | `id, date, from, to, cc, subject`, `attachments[]` (same descriptor rules as deliver-notice) |

`inbound/notices/processed/` is an OPTIONAL **directory convention** (v2.2.0,
§2), not a protocol artifact — it carries no schema and no fixture exists or
is needed for it.

At v2, emission of `contract_version` on the three protocol artifacts is
**mandatory**; any reference writer not yet emitting it is a tracked
**implementation conformance gap**, not a property of this spec.
`binding-record`'s `contract_version` stays optional (§9) but, if present,
is pinned to `"2"`.

## 9. Binding record (`identity.json`)

Written by the runtime/provisioner at the **volume root** (`<volume-root>/identity.json`
— a sibling of `<agent-id>/`, not inside it), naming which mailbox this volume
is bound to. Schema: `schemas/binding-record.schema.json`.

```json
{
  "contract_version": "2",
  "agent_id": "agent-research",
  "address": "agent@example.org",
  "provisioned_ts": "2026-07-20T04:10:56Z"
}
```

**Obligations:**
- **Informational, not authoritative.** The volume is an agent-writable
  filesystem, so a compromised agent can edit or delete this file at will.
  Attribution and policy stay keyed on runtime-side config (§2) — this record
  grants nothing and is never consulted for enforcement.
- **Consumers MUST tolerate its absence** and **MUST treat its contents as
  untrusted data**: a malformed, oversized, or hostile file must never crash a
  reader or otherwise affect protocol behavior.
- Its jobs are narrow, by design: operator sanity (a human confirming which
  mailbox a volume is bound to), a pre-start conflict check for whatever wrote
  it (catching e.g. one agent's secrets pointed at another agent's volume),
  and letting a connector surface the agent's own address back to the agent.
- **The file is OPTIONAL on the wire** (§8) — nothing in this contract requires
  a runtime to write it or a connector to read it; both sides must work
  correctly with it absent.

## 10. Peer directory (`directory.json`) — v3.1.0 DRAFT

A runtime **MAY** publish, at the agent's **namespace root**
(`<agent-id>/directory.json`, beside `inbound/`, `peer/`, `outbound/` and
`audit/`), a per-instance projection of the authorisation graph naming which
peers this agent may address. Schema: `schemas/directory.schema.json`.

```json
{
  "contract_version": "2",
  "router": "amap.router@fleet.example",
  "written_at": "2026-09-18T12:00:00Z",
  "delegate_to": ["bravo@fleet.example", "charlie@fleet.example"],
  "mail_to": []
}
```

**Obligations:**

- **Advisory, never authoritative.** The directory is the runtime's most
  recent word about the graph. It grants nothing. A consumer **MUST NOT**
  treat an address's presence as a prediction that a submit to it will be
  accepted, nor its absence as a prediction of refusal: authorisation is
  evaluated by the runtime at submit time, against state this file never
  claimed to mirror, and the result (§4) is the only thing that reports what
  actually happened. *(This is the defect the artifact exists to close, and it
  is not a staleness problem: a consumer that reads the directory as a
  prediction is wrong even when the file is perfectly current, and a fresher
  file only makes that wrong reading right more often.)*
- **A runtime MUST NOT read `directory.json` back, for any purpose.** It is
  write-only from the runtime's side. The graph is derived from policy; the
  file is a projection of the graph; nothing derives the graph from the file.
  Enforcement stays the runtime's own check against its graph, on every
  message.

  *The prohibition is on the direction, not the purpose, and that is
  deliberate. An earlier wording forbade reading it back "as authorisation",
  which is a statement about intent — and every way this rots has innocent
  intent: as an optimisation ("not in the list, do not attempt"), as a cache
  (read the projection at startup rather than recompute), as recovery (rebuild
  the graph from the projections after losing state), or as a cross-check
  (reconcile the graph against what was published). None is "treating it as
  authorisation" by its author's lights; every one makes the file
  load-bearing, and the last two turn a projection into a source. A projection
  that can be read back becomes a cache; a cache becomes a record; a record
  that disagrees with policy wins by accident on the day policy is slow to
  load. The producer is the only party who could ever close that loop, so the
  producer half is absolute.*
- **Per-instance projection, never a shared file.** Each agent's directory
  carries only the edges that agent is party to. A fleet-wide file would show
  every agent every edge, defeating the purpose of an explicit graph.
- **It MUST NOT carry who may address THIS agent.** That set is an allowlist
  in all but name and is withheld by construction. It MUST NOT carry the
  agent's own address either: attribution is the namespace a file arrived in
  (§2), and an agent that learns its own address from a file it reads has been
  handed a claim, not an identity.
- `router` is the publishing runtime's own address and **MUST NOT** appear in
  either list. Every address is one bare addr-spec under the §3 profile.
- **Both lists are always present**, and empty when that lane is closed for
  this agent — `mail_to: []` is the normal case for a delegation-only
  deployment. Absent and empty MUST NOT be conflated.
- **Written whole and atomically** (`.tmp` + `os.replace`, §2) on any change to
  the graph or the instance set. A runtime MUST NOT publish a newly-adopted
  instance's address to others before it has itself adopted that instance, so
  that no agent is told it may address something the runtime cannot yet route
  to.
- **A runtime that publishes the directory MUST ensure the agent can read
  it**, and SHOULD expose it read-only. Publishing to a path the agent's
  namespace does not expose is not conformant: the write succeeds, the file is
  correct, and no agent can read it — a failure that reports nothing on either
  side. Publishing is optional (above); a runtime that cannot make the file
  readable MUST NOT publish it, because an unreadable directory is
  indistinguishable from an absent one to a consumer and worse than an absent
  one to an operator, who has a file on disk that looks like it is working.

  *The trap is specific and follows from the location. `directory.json`
  deliberately belongs to no lane, which is what keeps a delegation-only
  deployment from having to materialise a mail tree — and is exactly what puts
  it outside an exposure built lane by lane. A deployment that exposes
  `inbound/` and `outbound/` individually exposes the file nowhere. §2's
  namespace-root posture is what makes the file reachable: the namespace root
  exposed read-only for runtime-written files, with the agent-written
  `outbound/` over it. Reported by `amap-router-local` against a real mount
  set, before the publish step was switched on.*

  *One consequence to state rather than leave implied, because a later reader
  is likely to get it wrong: for a deployment that cannot make the file
  readable, **not publishing is a correct terminal state, not a deferred
  one.** Publishing is optional; a runtime that never publishes is fully
  conformant and is not carrying an unfinished feature. Someone finding the
  publish step unimplemented should not "finish" it without first
  re-establishing that the file would be readable.*

- **`written_at` is the only staleness signal a consumer gets.** It is an
  honest marker, not a freshness guarantee.
- **The file MAY be absent** — before first adoption, on a runtime that does
  not implement this section, or after a failed write. A consumer MUST tolerate
  absence exactly as it tolerates a missing `identity.json` (§9).
- **A runtime that cannot write it keeps routing.** The directory is advisory,
  so a failed write loses a convenience, not the ability to enforce; failing
  closed would convert an advisory artifact into a dependency. The runtime
  **MUST** log the failure. The agent's only signal remains `written_at` going
  stale.
- **Where the consumer is an agent rather than a parser, these become
  obligations to convey.** A connector that surfaces the directory to its agent
  instead of interpreting it satisfies the obligations above by stating them,
  under §5's substance-not-vocabulary rule: the agent is the party forming a
  belief, so the connector MUST convey that an address's presence is not a
  prediction of acceptance, that the file may be absent, that an empty list and
  an absent list differ, and that `written_at` is the only staleness signal
  there is. **A connector with no directory parser does not thereby satisfy
  them vacuously.** *(Reported by an implementation whose only directory
  consumer is its agent: every obligation above was expressible, and none was
  satisfiable as code, because there was no code to satisfy it. Obligations
  written for a parser are met by having no parser, which is the opposite of
  what they intend.)*
- **`contract_version` is OPTIONAL here**, and pinned to `"2"` when present —
  the same treatment `binding-record` gets (§7), and for the same reason: the
  file is optional and informational, not a protocol artifact a consumer must
  parse to function.

## Appendix A (non-normative): a seam-visible "handled" signal — deferred

This appendix is **not-yet-specified**: it records the reasoning behind a gap
left open at v2.2.0, not a normative addition. Nothing below is a directory,
field, or artifact a conforming implementation may rely on.

**The gap.** Making inbound consumption-tracking connector-private (§2) closes
the writability conflict but leaves a knowledge/capability split unbridged:
only the connector knows a notice has been relayed to its agent; on a
read-only inbound, only the runtime can delete anything. Neither side alone
can turn "consumed" into "reclaimed."

**A sketch, not a spec.** One shape that would bridge it: a connector-written,
zero-byte marker per acknowledged notice —

```
outbound/acks/notice-<id>        # sketch only — not part of this contract
```

— written into `outbound/`, where the connector already has write access in
every posture. A runtime could then delete the acked
`inbound/notices/notice-<id>.json` and `inbound/messages/notice-<id>.json`,
and finally the marker itself. This is presented purely as a sketch: **no
normative directory and no wire field are introduced by this appendix.**

**Why a connector-forgeable signal would be acceptable here.** A GC signal is
a resource decision, not a security decision. An agent that falsely claims
consumption loses only its own unread mail; one that never claims consumption
only bloats its own inbox. Neither crosses a trust boundary that matters, and
neither touches any record of the exchange the runtime keeps on its own side.
That is why this differs from every other "the agent writes it, so it can't be
trusted" case in this contract — but it is a distinction a future spec change
would need to state explicitly, not assume.

**Why a high-water mark can't substitute.** §6 requires `task_id` be
unguessable and never sequential, and nothing in this contract orders notice
ids, so no single "processed through N" cursor is expressible. Any
consumption signal has to be a *set* of ids, or time-ordered — and
time-ordering would require the consumer to process strictly in delivery
order, which nothing today requires.

**The lifecycle this would enable, and its boundaries.** A reliable "is this
one done?" answer is the watermark a real retention lifecycle promotes
against — cycling a working set, rolling handled traffic into
period-compacted archives, then expiring or tiering to cold storage. Three
boundaries would need to hold if this is ever specified:
- **The seam is not the record.** Any runtime that needs an
  exchange-of-record already keeps one outside the seam, tamper-evident. Seam
  retention is about the agent's access to its own history, not durability of
  evidence — conflating the two produces an archive that satisfies neither.
- **An agent-writable archive is never evidence.** A compacted archive living
  under `outbound/` (agent-writable in every posture) can be rewritten by the
  agent it belongs to. Anything meant to be relied on has to be runtime-written
  or kept out of the seam entirely.
- **It must not grow the read surface.** AMAP's read today is a point lookup
  (notice-id → body). "Search my archive" is a materially larger capability —
  decompression, indexing, query — for a deliberately dumb, credential-free
  relay to take on. If archives are ever agent-exposed, that likely belongs
  behind a runtime-served surface, not the file-drop seam.

**Why this is deferred rather than specified now.** Per §7, a capability
starts here once a second implementation independently wants it, with fields
and fixtures proposed together. At v2.2.0 exactly one reference connector
carries a private workaround for the underlying problem (a
writability-probing three-mode fallback — move / ledger / in-memory); there
is no second data point yet to generalize from, and specifying now would
freeze one side's convention as the seam's answer.

**One honesty note for a future implementer.** The sketch's own GC step is not
atomic: if a runtime crashes between deleting the notice artifacts and
deleting the ack marker, the marker is orphaned pointing at a notice that no
longer exists. Any real design needs idempotent GC (a missing target is not
an error) — recorded here so it isn't rediscovered from scratch.
