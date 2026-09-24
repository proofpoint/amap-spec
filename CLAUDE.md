# CLAUDE.md — amap-spec (THE SEAM; formerly agent-mailbox-protocol)

This repo is the **wire contract**, and nothing else. A trusted, credentialed
mail runtime implements one half; an untrusted per-agent connector implements
the other. The contract is **owned by neither**, which is the whole point: the
two sides are built by different people, versioned independently, and prove
conformance against the fixtures here rather than against each other.

**It is not an implementation.** No connector, no runtime, no transport. If you
are about to write code that *does* something with mail, you are in the wrong
repo. What lives here is the Internet-Draft (`draft/draft-amap.xml`, the
canonical prose), `schemas/`, `fixtures/`, the `dist/` renderings, the frozen
`spec/contract.md`, and the peer-origin profile `spec/peer-origin.md`.

**It is not a mail transport, not agent-to-agent RPC, and not a policy
language** — README's "What AMAP is not" says this normatively; keep it true.

## Posture — read before you publish anything

- **Proofpoint-owned. Counsel has APPROVED publication (2026-09-17)** of this
  spec repository, the local router, and the Claude Code connector, and
  approved taking AMAP to the IETF. The blanket "open-able is not open" hold
  that previously governed this repo no longer applies to it.
- **The hold still stands for every other Proofpoint product.** Only the
  three items above are approved. Do not treat this repo's approval as
  covering anything else, and do not publish, name, or allude to other
  products here — a sentence saying "X is not published" publishes X.
- **`LICENSE` (Apache 2.0) is now a real grant** for this repository. The
  relicense commit's "pending counsel approval" is satisfied as of the
  approval above. *(Prior revisions of this file said a permissive LICENSE in
  the tree was "a preparation for publication, not a grant of it" — true when
  written, superseded now.)*
- **Approved to publish is not the same as submitted.** The counsel gates are
  CLEAR (operator-confirmed 2026-09-24): `ipr="trust200902"` (settled
  2026-09-21, the full BCP 78 grant), `submissionType="independent"`, and an
  email for each author. The draft is **ready for submission and has not been
  submitted.** Any future change to those values, to the author list, or to a
  BCP 79 disclosure is a rights statement, not an editorial choice: do not
  make one on your own initiative. The history is in `draft/README.md` under
  "Counsel gates". Note the draft ASSERTS it is submitted under BCP 78/79,
  because a real `ipr` value generates that boilerplate. Nothing has been
  submitted anywhere, and submitting is the owner's decision, not an editorial
  one.
- Keep shipped text free of absolute host paths and personal identifiers.

## Version state (as of the peer-origin-profile merge to `main`)

| | |
|---|---|
| Contract version | **v3.1.0 DRAFT** (in the draft; also the frozen `spec/contract.md` title) |
| Wire `contract_version` | **`"2"`** — unchanged by 3.1.0, which is additive |
| `README.md` claims | **3.1.0 DRAFT, 89 fixtures** — matches the gate |
| Actual gate result | **89 fixtures, 0 unexpected** (34 valid + 55 invalid) |
| Canonical prose | `draft/draft-amap.xml`, hand-edited; `make -C draft` renders and gates |

The contract's own SemVer and the wire major are **two different axes** as of
3.0.0 (§7). Do not collapse them: "3.1.0" is the document; `"2"` is what goes
on the wire and what a consumer version-checks.

**The Internet-Draft XML is the canonical source (since 2026-09-24).**
`draft/draft-amap.xml` is xml2rfc v3, hand-edited by the standards editor, and
generated from nothing. It was converted from the last kramdown-rfc rendering
with a byte-identical text rendering, so nothing a reader sees changed. The
contract is now **`draft/draft-amap.xml` + `schemas/` + `fixtures/`**.
`spec/contract.md` is **FROZEN**: never edit it; its header maps its sections
to the draft's. `spec/peer-origin.md` is **not** frozen: the draft carries only
its schema, and it stays the canonical peer-lane prose until it leaves DRAFT.

The draft's JSON is never hand-copied. `draft/tools/sync_sources.py`
(`make -C draft sync`) writes each schema, listed fixture and example into its
`<sourcecode>` block, rewriting only that CDATA body and folding per RFC 8792.
xml2rfc's own `src=` can't do it: 3.34.1 crashes on non-ASCII UTF-8 in a src
file. Gates in `make -C draft`:
- a byte comparison: `dist/draft-amap-00.xml` must equal the source (never edit `dist/`);
- `sync_sources.py`: blocks equal disk, and no schema or listed fixture lacks a block;
- `check_render.py`: the same, plus roster counts, docName, no host paths;
- `check_coverage.py`: every RFC 2119 sentence in the protocol sections
  (Architecture through Versioning and Conformance, including the Peer
  Directory and the Fleet Roster) is classified in `draft/coverage.toml`;
- the fixture gate.

`normdiff.py` (`make -C draft normdiff BASE=<ref>`) lists the normative
sentences added, removed or changed; reviewers read that, not the XML diff. The
toolchain is xml2rfc 3.34.1 and Python ≥ 3.11 (weasyprint only for `pdf`);
kramdown-rfc and Ruby are gone. `draft/tools/preflight.sh` checks the artifact,
never the mechanism. **Never invoke `kdrfc`**: it POSTs the XML to
author-tools.ietf.org when it cannot exec a local xml2rfc.

**v3.1.0 is DRAFT.** It carries the peer-origin profile —
`spec/peer-origin.md` (the prose: tree, origin-class rule, addressing,
correlation, cross-host signing, `sender_exposure`, conformance sub-classes),
`schemas/peer-notice.schema.json` and the `peer-*` fixtures — and, in core
§2, the tree rules and the `outbound/ext/<name>/` convention. The profile
file was drafted 2026-09-15; `peer-notice.schema.json` and
`fixtures/validate.py` cite its section numbers. The schema descriptions and
the profile must agree — a disagreement is a finding, report it.

## Running the gate

```
python3 fixtures/validate.py
```

Stdlib only — no `jsonschema` dependency, no network, **no counterpart
present**. Exit 0 iff every `valid/` fixture passes and every `invalid/` one
fails. Verified: `89 fixtures checked, 0 unexpected.`

There is no pytest suite in this repo. (A `.pytest_cache/` directory exists; it
is a leftover, not a suite.)

`validate.py` implements a hand-rolled subset of JSON Schema 2020-12 —
`type, const, enum, minLength, pattern, minItems, minimum, items, required,
properties, additionalProperties, allOf`, and a single `if`/`then` (no `else`).
All of it is standard, so a full validator would agree; but **a schema keyword
outside that list will be silently ignored**. If you add one, extend the
validator in the same change or the fixture proves nothing.

Two rules are enforced as named Python post-checks rather than in schema,
because neither is expressible in JSON Schema:
- `_check_result_attachment_index_binding` — on a `result`, `attachments[i].index == i`.
- `_check_content_ref_index_binding` — on a `notice` or `message`, every
  `content_ref` must equal `f"{notice_id}.attachments/{i}"` for its own array
  position.

## How fixtures are organised

`fixtures/valid/` must pass; `fixtures/invalid/` must fail. **Schema is chosen
by filename prefix**, so the prefix is load-bearing — a misnamed fixture
validates against the wrong schema and passes for the wrong reason:

| prefix | schema |
|---|---|
| `notice-*` | `deliver-notice.schema.json` |
| `peer-*` | `peer-notice.schema.json` |
| `message-*` | `inbound-message.schema.json` |
| `request-*` | `submit-request.schema.json` |
| `result-*` | `result.schema.json` |
| `identity-*` | `binding-record.schema.json` |
| `directory-*` | `directory.schema.json` |
| `roster-*` | `roster.schema.json` |

Note the collision this map papers over: on disk, a runtime names both the
deliver-notice and the message spool `notice-<id>.json` from the same
`notice_id`. The prefix map has only one `notice-` entry. **Anything validating
real artifacts must pick the schema explicitly, never by filename** — the
conformance harness's `test_amp_conformance.py` documents exactly this trap.

## The open/closed asymmetry — the thing most likely to be misremembered

**As of v3.0.0, `deliver-notice.schema.json` is OPEN.** Its `message` object
does **not** carry `additionalProperties: false`, at any level. Neither do
`inbound-message` or `result`. Only these are closed:

- **`submit-request.schema.json` — CLOSED at every level.** Agent-authored: an
  unrecognized member must be a designed, legible `rejected`, never a silent drop.
- **`binding-record.schema.json` — CLOSED.** §7 is explicit that this closure is
  an *anti-secret-leak lint*, not a compatibility surface.

The rule is **direction, not taste**: runtime-authored documents are open
(a consumer MUST ignore members it does not recognize; emitting one is still
producer non-conformance), agent-authored documents are closed.

This was the opposite at v2.3.0, where nearly everything was
`additionalProperties: false`. v3.0.0 changed it deliberately, and §7 keeps the
v2.1.0 bullet standing with a **Correction** attached rather than rewriting
history — a strict v2.0.0 connector silently dropped whole notices when
`provenance` was added, which is the failure the open envelope exists to
prevent. **If you find yourself asserting the notice envelope is closed, you
are remembering v2.3.0.**

### The `to` trap — a real bug, and the schema will not catch it

`to` is a property of **`inbound-message.schema.json`** (the spooled message at
`inbound/messages/notice-<id>.json`), alongside `from`, `cc`, `date`, `subject`
and `body_text`.

**`to` is NOT a property of the deliver-notice's `message` object.** That object
declares exactly: `id`, `from`, `subject`, `preview`, `mailbox` (all required),
plus optional `task_id`, `thread_id`, `in_reply_to`, `references`,
`sender_standing`, `provenance`, `verdict`, `attachments`.

Code that reads `message.to` off a **notice** is reading a field that is not
there. And because the notice envelope is **open**, a runtime that wrongly
*emits* `message.to` on a notice **passes the gate**: the schema will not flag
it, `validate.py` will not flag it, and the mistake survives to the connector.
The recipient list lives on the **spool doc**, and resolving the body is the
only way to get it. Neither direction of this error is mechanically caught —
which is precisely why it belongs in this file.

## Two lanes, two trees

The peer-origin profile gives agent-to-agent traffic its **own tree** rather
than a flag on the mail tree:

- **mail** → `<agent-id>/inbound/notices/`, `kind: "deliver"`, `message.mailbox`
  free-form (`"inbox"` in the fixtures).
- **peer** → `<agent-id>/peer/notices/`, `kind: "peer"` (`const`),
  `message.mailbox: "peer"` (`const`).

The two schemas **cross-lock**, and this is the profile's second lock: a
`kind: "peer"` document found under `inbound/notices/` fails
`deliver-notice.schema.json`; a `kind: "deliver"` document found under
`peer/notices/` fails `peer-notice.schema.json`. Both are then dropped under
§5's drop rule. The invalid fixtures `notice-kind-peer.json`,
`peer-kind-deliver.json` and `peer-mailbox-inbox.json` pin all three legs.

§2's directory-layout block shows the `peer/` tree beside `inbound/`,
marked PROFILE; the profile's own §1 carries the same block with the
sidecar paths spelled out.

What the peer profile pins that mail does not:
- `message.from` is a **bare addr-spec** with no display name — the *one* `from`
  in the protocol a consumer may treat as authenticated origin, runtime-asserted
  from the restricted write path, never copied from sender text.
- `message.id` / `in_reply_to` / `references` are pinned to the `notice_id`
  charset — **bare on the wire**. The `<id@domain>` Message-ID encoding exists
  only inside a mail header and is decoded before it enters any AMAP document.
- `sender_exposure` is runtime-asserted and never sender-settable. **Its absence
  means NOT ASSESSED, never "no exposure",** and it MUST NOT drive routing.

### `provenance` — state this carefully

- On a **deliver-notice**, `provenance` sits on the **notice**, in
  `message.provenance`. It is optional, and an **open advisory vocabulary**
  (`external`, `internal`, …) — a connector MUST tolerate an unknown value as
  opaque and MUST NOT drop the notice over it. `inbound-message.schema.json`
  declares no `provenance` at all, so the labelling is a notice-level thing.
- On a **peer-notice**, the schema says `provenance` is "redundant with the tree
  … and **MAY be omitted**", and "never grounds to derive or override origin
  class". **It is not forbidden**, and the envelope is open, so it could not be
  forbidden by this schema as written. No invalid fixture rejects a peer notice
  carrying it. If absence is meant to be *required*, that is not what ships
  today, and pinning it would need a new `invalid/peer-*` fixture plus a schema
  change — do not assert the stronger claim until it exists.

Either way the operative rule is the same and is safe to rely on: **origin
class comes from the tree the notice arrived in, never from `provenance`.**

## Two workflows, and which direction a change is travelling

**Read `WORKFLOWS.md` before changing the draft, `schemas/` or `fixtures/`.**
Changes enter this repo from both ends and the rules are not symmetric.

- **Rules-first (A).** A capability changes in an implementation. It becomes
  real in `schemas/` + `fixtures/` FIRST, with the prose carried into
  `draft/draft-amap.xml` in the same change (by the editor if the proposer
  can't write it). Implementations propose; they never decide, and they
  never invent a wire field locally.
- **Editor-first (B).** The standards editor hand-edits `draft/draft-amap.xml`.
  **Those edits are canonical.** Do NOT revert them, reword them, or
  re-derive them from anything. Take the edit as given, then follow a change
  in meaning into `schemas/`/`fixtures/`, and onward to the implementations.

**`draft/coverage.toml` is the guard, and its baseline is not an allowlist.**
Every normative sentence in the protocol sections needs a class: fixture,
operational or informative. The 128 sentences present at the switch are
marked `baseline = true` and unclassified. Working that list down is real
progress. **Never add an unclassified entry** to silence a new-sentence
failure: give the sentence its real class, which is the point of the gate.

## How a change propagates to implementers

§7 makes this a hard sequence, and it is the repo's reason for existing:

1. **A capability change starts HERE** — a PR against `schemas/` +
   `fixtures/` + the draft's prose, *before* either side builds it. **Neither a runtime
   nor a connector may invent a wire field locally.**
2. **Additive ⇒ MINOR. Breaks an existing fixture ⇒ MAJOR**, taken deliberately
   by both sides. A version mismatch **fails closed**; it never silently
   mis-parses.
3. Add the fixtures in the same change. The fixtures *are* the other side — a
   field with no fixture is a field no implementer can prove they handle.
4. Record it in the draft's Change Log (the frozen `spec/contract.md` §7 holds
   the history before the switch). The house style is to **leave a wrong
   bullet standing and attach a Correction**, because what shipped is a fact;
   see the v2.1.0 bullet.
5. `dist/` is **generated, never patched**: `make -C draft` copies the source
   XML and renders the text.

**Version-check ordering (§7, v3.0.0)** — get this right in any consumer you
review: read `contract_version` **before** any schema validation, compare majors
as non-negative decimal integers. Absent, lower, or higher major is a **version
refusal** (fail closed), a distinct logged outcome, never folded into the
malformed-document drop path. Outbound, a runtime version-refusing a
submit-request answers on the ordinary rejection path: a `rejected` result with
`reason_code: "unsupported_contract_version"`. There is no equivalent wire
document for a notice a runtime never emits — hence the asymmetry: logged-only
inbound, `rejected` outbound.

## What a green gate does NOT prove

`fixtures/validate.py`'s NOT-CHECKED docstring is the authoritative list and is
worth reading in full before you claim conformance for anything. It covers
filesystem and policy invariants no document validator can see, including:
sidecar file existence and `size_bytes`/`sha256` matching real bytes; the
`filename` never-a-path invariant; runtime-private staging; write-ordering and
commit-sentinel atomicity; caps and allowlists; enforcement-by-absence for a
quarantined message; **connector tolerance of a read-only `inbound/` tree**;
ingest-by-copy; the three conjunctive legs of write-side path discipline;
read-side open discipline; and single-writer/single-drainer.

§7.1 defines two conformance classes (runtime, connector) and states plainly:
**claiming either without the fixture run AND the prescribed operational check
for that class's behavioral obligations is not conformance.**

## Known-wrong, unfixed (report, do not silently patch)

Nothing is currently known-wrong. Known-open items — deliberate, tracked, and
not defects:

- **`draft/coverage.toml` has a 128-sentence unclassified baseline.**
  Classifying each (fixture, operational, informative) is real progress.
- **The schema descriptions and `fixtures/validate.py` still cite
  `spec/contract.md` / `spec/peer-origin.md` section numbers.** They resolve,
  because the frozen file stays, but they should be remapped to the draft's
  sections in a reviewed change of their own: the schemas are normative files.
- **CI changes are proposed, not applied.** `.github/workflows/` is read-only
  from agent sessions, so a workflow change is handed to the operator to apply.
- **The `attestation` field name collides with IETF RATS usage** (RFC 9334):
  IETF reviewers will read "attestation" as remote attestation of platform
  state, not a sender-identity stamp. Clarifying it is an editor-first change
  to the draft.

Cleared 2026-09-24: the draft rendered six of the seven schemas; the
peer-directory schema is now in its own appendix (Peer-Directory Schema). The spec was reconciled into the draft
before being frozen: 8 spec sentences were deliberately left out, and 27
draft-only sentences were checked against the spec and schemas and found
consistent.

Cleared 2026-09-17 (recorded so nobody re-reports them): the draft is renamed
`draft-amap-00` — source, `docname`, and both outputs — so no artifact carries
the old protocol name; the five schema descriptions the AMAP rename missed
now read `amap-spec`; the legacy hand-maintained
`dist/agent-mailbox-protocol-draft-00.{md,pdf}` is removed and `draft/`
generates the rendering, so there is no hand-maintained copy left to drift;
`draft/` separates authored content from `tools/`. Every remaining "AMP"
string is a deliberate *formerly* clause where the old spelling is the
payload — leave those alone.

**Correction (2026-09-17).** A prior revision of this section claimed the
draft's filename "keeps the OLD protocol name (`draft-amap-00`) on purpose".
That sentence was self-contradictory: the slug replacement in the
draft-rename commit rewrote the old name *inside the sentence explaining that
the old name was kept*. The condition it described was fixed by that same
commit. Recorded
rather than silently deleted, per §7's house style — and as a warning that a
repo-wide rename can corrupt the very prose that documents the rename.

Cleared 2026-09-16: README's version and fixture count now match the contract
and the gate (3.1.0 DRAFT, 75); `spec/peer-origin.md` exists and §2's layout
names the `peer/` tree; the operator's then-uncommitted `dist/` and fixture
edits are committed. `HEAD` is what you run.

**Cite this repo by version and section, never by commit hash.** Every hash in
this tree was rewritten once already when the history was filtered for
publication, and a no-history release discards them a second time. A citation
that names a commit is a citation into a history that may not exist; one that
names what the commit DID survives both. This paragraph is what the rule looks
like applied to itself — it used to carry four hashes.
