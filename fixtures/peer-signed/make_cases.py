#!/usr/bin/env python3
"""Regenerate cases/*.json and mime/*, the signed peer cases (peer-origin §5).

    python3 fixtures/peer-signed/make_cases.py

A case is a sequence of steps run against a fresh receiver (receiver.json
unless the case names receiver-host-a.json). A step is either a candidate (as
§5.2 pins it: the field bodies of the AMAP-Peer-Statement, AMAP-Peer-Control
and Message-ID fields, the selected body leaf's transfer-decoded octets and
charset label, and every other leaf's transfer-decoded octets, in order) or
an event (recover, lose_store, set_bound, set_windows, set_edges, set_key,
remove_key, a clock change), each with what the receiver MUST report. A case
with `config_error` has no steps: the receiver MUST refuse its configuration.

Single-step cases break exactly one rule unless their name starts with
`multi-`, where the point is §5.4's precedence between several failures.

Signing uses the published RFC 8032 §7.1 test keys through ed25519_ref.py.
Ed25519 is deterministic, so a rerun reproduces the committed files byte for
byte; check_cases.py (run by fixtures/validate.py) verifies them on its own.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ed25519_ref  # noqa: E402

_VECTORS = json.loads((HERE / "rfc8032-vectors.json").read_text())["vectors"]
SECRETS = {v["key_id"]: bytes.fromhex(v["secret_key"]) for v in _VECTORS}
PUB = {v["key_id"]: v["public_key"] for v in _VECTORS}

A, A2, B = "host-a.fleet.example", "host-b.fleet.example", "host-c.fleet.example"
PLANNER, REVIEWER_A = f"planner@{A}", f"reviewer@{A}"
BUILDER, REVIEWER_C = f"builder@{B}", f"reviewer@{B}"
BODY = "Please run the conformance suite on main and report the result.\n"
LOG = b"conformance suite: all checks passed\n"
NOW = "2026-10-09T15:10:00Z"
ISSUED = "c3a9e0d47f1b4e2a8d6c5b0a9f8e7d61"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sbytes(st) -> bytes:
    return json.dumps(st, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


_n = [0]


def nid() -> str:
    _n[0] += 1
    return b64u(hashlib.sha256(f"case-id-{_n[0]}".encode()).digest()[:16])


def stmt(**kw) -> dict:
    st = {"v": 1, "key_id": "test1", "kind": "peer", "id": nid(), "from": PLANNER, "to": BUILDER,
          "ts": "2026-10-09T15:00:00Z", "subject": "Run the conformance suite",
          "body_sha256": sha(BODY.encode()), "attachments": []}
    st.update({k.rstrip("_"): v for k, v in kw.items()})
    return st


def field(key_id, sb, sig) -> str:
    return f" k={key_id}; s={b64u(sb)}; b={b64u(sig)}"


def cand(st, *, raw=None, sign_key=None, header=None, body=None, charset="utf-8",
         atts=(), mid=None, extra=(), name="AMAP-Peer-Statement"):
    """A candidate for statement `st`. `raw` replaces the signed bytes;
    `header` the field body (False: no field); `body` the body octets
    (None: BODY; False: no body leaf)."""
    sb = raw if raw is not None else sbytes(st)
    sig = ed25519_ref.sign(SECRETS[sign_key or st["key_id"]], sb)
    hv = field(st["key_id"], sb, sig) if header is None else header
    dom = st["from"].rpartition("@")[2]
    fields = [["Message-ID", mid if mid is not None else f" <{st['id']}@{dom}>"]]
    if hv is not False:
        fields.append([name, hv])
    fields += [list(x) for x in extra]
    if body is False:
        b = None
    else:
        octets = BODY.encode() if body is None else body
        b = {"charset": charset, "octets_b64": b64(octets)}
    return {"fields": fields, "body": b, "attachments": [{"octets_b64": b64(a)} for a in atts]}


def pub(st, text=BODY):
    m = {"id": st["id"], "from": st["from"], "subject": st["subject"], "body_text": text,
         "attachments": [{k: a[k] for k in ("filename", "media_type", "size_bytes", "sha256")}
                         for a in st["attachments"]]}
    for opt in ("in_reply_to", "sender_exposure"):
        if opt in st:
            m[opt] = st[opt]
    return m


def peer(st, text=BODY):
    return {"outcome": "peer", "publish": pub(st, text)}


def ctl(outcome, cause, st, runtime="amap.router@host-a.fleet.example", code=None):
    c = {"outcome": {"mail": "demoted", "drop": "dropped", "refuse": "refused"}[outcome],
         "cause": cause, "to": runtime, "about": st["id"]}
    if code:
        c["policy_code"] = code
    r = {"outcome": outcome, "cause": cause, "control": c}
    if code:
        r["policy_code"] = code
    return r


def pre(outcome, cause):
    """A failure before authentication: no control notice."""
    return {"outcome": outcome, "cause": cause}


CASES = []


def case(name, description, steps, receiver=None, patch=None, config_error=None):
    doc = {"description": description}
    if receiver:
        doc["receiver"] = receiver
    if patch:
        doc["receiver_patch"] = patch
    if config_error:
        doc["config_error"] = config_error
    doc["steps"] = steps
    CASES.append((name, doc))


def rec(st, outcome, cause, runtime="amap.router@host-a.fleet.example", code=None):
    """What recovery reports for a record it finishes as a refusal or drop."""
    return {"id": st["id"], **ctl(outcome, cause, st, runtime=runtime, code=code)}


def one(name, description, c, expect, **kw):
    case(name, description, [{"candidate": c, "expect": expect}], **kw)


ATT = {"sha256": sha(LOG), "size_bytes": len(LOG), "filename": "gate.log", "media_type": "text/plain"}


def build():
    # ---------------------------------------------------------------- placed
    st = stmt()
    one("peer-task-minimal", "A fresh task from host-a, signed with test1, along a declared edge.",
        cand(st), peer(st))
    st = stmt(key_id="test2")
    one("peer-task-second-key", "The same sender with its second concurrent key (rotation).",
        cand(st), peer(st))
    st = stmt(from_=f"planner@{A2}", key_id="test3")
    c = cand(st)
    hv = c["fields"][1][1]
    c["fields"][1] = ["amap-peer-statement", hv[:40] + "\r\n " + hv[40:90] + "\r\n\t" + hv[90:]]
    one("peer-folded-header",
        "A second peer (host-b, test3). Lower-case field name; the field body folded with CRLF+SP and "
        "CRLF+HTAB inside a base64url run. All whitespace is removed before decoding.", c, peer(st))
    st = stmt(sender_exposure={"asserted_by": "amap.router@host-a.fleet.example",
                               "external_mail_delivered": True, "window_start": "2026-10-08T15:00:00Z",
                               "window_end": "2026-10-09T15:00:00Z",
                               "last_external_delivery_ts": "2026-10-09T09:12:00Z"})
    one("peer-exposure", "sender_exposure asserted by the signing runtime's configured address; "
        "published from the statement only (§6).", cand(st), peer(st))
    st = stmt(sender_since="2026-09-30T08:00:00Z")
    one("peer-sender-since", "sender_since present and no deployment policy configured: it is carried "
        "and does not change treatment.", cand(st), peer(st))

    # ------------------------------------------------- replies and the ledger
    body = b"Reviewed; log attached.\n"
    st = stmt(from_=REVIEWER_A, in_reply_to=ISSUED, subject="Re: Review the gate output",
              attachments=[ATT], body_sha256=sha(body))
    one("reply-valid", "A reply to a peer message this runtime issued from builder to reviewer@host-a: "
        "the record binds local=builder and remote=reviewer@host-a, so the reverse edge is permitted "
        "with no declared edge.", cand(st, body=body, atts=[LOG]), peer(st, body.decode()))
    st = stmt(in_reply_to="Q2hhaW5TdGVwVHdvMDAwMDAy", subject="Re: Re: the plan")
    one("reply-to-reply", "planner@host-a answers builder's reply (an id this runtime issued to planner, "
        "itself answering planner's task): resolves with the participants bound.", cand(st), peer(st))
    st = stmt(in_reply_to="Q2hhaW5TdGVwT25lMDAwMDAx", subject="Following up")
    one("reply-follow-up-with-edge", "planner@host-a follows up its own task (a record this runtime "
        "PLACED, same direction). Correlation resolves; it is not a reverse edge, so the declared edge "
        "planner -> builder is what permits it.", cand(st), peer(st))
    st = stmt(in_reply_to="UGxhY2VkTm9FZGdlMDAwMDA0", to=REVIEWER_C, subject="Following up")
    one("refuse-follow-up-no-edge", "A same-direction follow-up to reviewer@host-c resolves, but there "
        "is no edge planner -> reviewer@host-c and the record is not one this runtime issued.",
        cand(st), ctl("refuse", "no_edge", st))
    st = stmt(from_=REVIEWER_A, in_reply_to=ISSUED, to=REVIEWER_C, subject="Re: x")
    one("refuse-reply-wrong-local-recipient", "The record's local participant is builder; this reply "
        "is addressed to reviewer@host-c.", cand(st), ctl("refuse", "unresolved_reply", st))
    st = stmt(from_=f"other@{A}", in_reply_to=ISSUED, subject="Re: x")
    one("refuse-reply-wrong-remote-agent", "Another agent on host-a presents the id it observed.",
        cand(st), ctl("refuse", "unresolved_reply", st))
    st = stmt(from_=f"reviewer@{A2}", key_id="test3", in_reply_to=ISSUED, subject="Re: x")
    one("refuse-reply-wrong-remote-host", "An agent on host-b, signed by host-b, presents host-a's id.",
        cand(st), ctl("refuse", "unresolved_reply", st, runtime="amap.router@host-b.fleet.example"))
    st = stmt(from_=REVIEWER_A, in_reply_to="RXhwaXJlZFJlY29yZDAwMDAz", subject="Re: x")
    one("refuse-reply-expired", "The right participants, but the record's reply window ended at 15:00.",
        cand(st), ctl("refuse", "unresolved_reply", st))
    st = stmt(in_reply_to="m-2026-10-09-0001", subject="Re: your mail")
    one("refuse-reply-to-mail-id", "in_reply_to names a notice in this runtime's MAIL tree. Only the "
        "peer ledger resolves a peer reply.", cand(st), ctl("refuse", "unresolved_reply", st))
    st = stmt(in_reply_to="ffffffffffffffffffffffffffffffff", subject="Re: something")
    one("refuse-unresolved-reply", "in_reply_to names nothing in the ledger (§4's residual case).",
        cand(st), ctl("refuse", "unresolved_reply", st))
    st = stmt(from_=f"planner@{A2}", key_id="test3", to=REVIEWER_C)
    one("refuse-no-edge", "A verified fresh task with no edge planner@host-b -> reviewer@host-c.",
        cand(st), ctl("refuse", "no_edge", st, runtime="amap.router@host-b.fleet.example"))

    # ----------------------------------------- optional deployment policy (§5.9)
    pol = {"min_sender_age_s": 86400}
    st = stmt(sender_since="2026-10-09T00:00:00Z")
    one("refuse-policy-quarantined", "A deployment requiring a 24 h sender age (§5.9, optional): "
        "sender_since is 15 h ago.", cand(st), ctl("refuse", "policy", st, code="quarantined"), patch=pol)
    st = stmt()
    one("refuse-policy-sender-age-unknown", "The same policy; sender_since absent means not asserted, "
        "never 'old enough'.", cand(st), ctl("refuse", "policy", st, code="sender_age_unknown"), patch=pol)
    st = stmt(sender_since="2026-09-30T08:00:00Z")
    one("peer-policy-sender-age-ok", "The same policy; sender_since nine days ago.", cand(st), peer(st),
        patch=pol)

    # -------------------------------------------- header and field (pre-auth)
    st = stmt()
    one("mail-no-statement", "No statement field: ordinary mail, nothing logged as a verification "
        "failure, no control notice.", cand(st, header=False), pre("mail", "no_statement"))
    c = cand(st)
    c["fields"].append(c["fields"][1])
    one("mail-two-headers", "Two identical statement fields: a failure.", c, pre("mail", "header_count"))
    c = cand(st)
    c["fields"].append(["AMAP-Peer-Statement", {"invalid": "non_ascii"}])
    one("mail-two-headers-one-invalid", "A valid statement field plus a second one the admitting "
        "component could not carry as ASCII text, so it carried an explicit invalid marker. The marker "
        "keeps the field's multiplicity: two fields is a failure, and the valid one is never selected.",
        c, pre("mail", "header_count"))
    sb = sbytes(st)
    sig = ed25519_ref.sign(SECRETS["test1"], sb)
    one("mail-header-padding", "base64url with '=' padding.",
        cand(st, header=f" k=test1; s={b64u(sb)}=; b={b64u(sig)}"), pre("mail", "header_encoding"))
    one("mail-header-unknown-tag", "A tag other than k, s and b.",
        cand(st, header=field("test1", sb, sig) + "; x=1"), pre("mail", "header_encoding"))
    one("mail-header-k-pattern", "k is not a key_id (it is validated before any lookup or log).",
        cand(st, header=f" k=../../etc; s={b64u(sb)}; b={b64u(sig)}"), pre("mail", "header_encoding"))
    one("mail-header-non-ascii", "A non-ASCII octet in the field body.",
        cand(st, header=field("test1", sb, sig) + "é"), pre("mail", "header_encoding"))
    one("mail-signature-length", "b decodes to 63 bytes.",
        cand(st, header=field("test1", sb, sig[:63])), pre("mail", "header_encoding"))
    c = cand(st)
    c["fields"][1][1] = {"oversize": True}
    one("mail-header-oversize", "The admitting component carried an oversize marker (the field body "
        "exceeded 12288 octets); it never truncates.", c, pre("mail", "header_size"))

    # ------------------------------------------------- key and signature (pre-auth)
    st = stmt(key_id="test9")
    one("mail-unknown-key", "k=test9 names no configured key.", cand(st, sign_key="test1"),
        pre("mail", "unknown_key"))
    st = stmt()
    one("mail-key-expired", "test1's not_after (inclusive) is before now.", cand(st),
        pre("mail", "key_validity"), patch={"key_validity": {"test1": {"not_after": "2026-10-09T15:09:59Z"}}})
    st = stmt()
    one("peer-key-not-after-inclusive", "now equals test1's not_after: still valid (inclusive).",
        cand(st), peer(st), patch={"key_validity": {"test1": {"not_after": NOW}}})
    st = stmt()
    sb = sbytes(st)
    sig = ed25519_ref.sign(SECRETS["test1"], sb)
    bad = sb.replace(b"conformance suite", b"conformance suitE")
    one("mail-signature-invalid", "The statement was altered after signing.",
        cand(st, header=field("test1", bad, sig)), pre("mail", "signature"))

    # --------------------------------------------- the statement (authenticated)
    st = stmt(key_id="test2")
    sb = sbytes(st)
    one("mail-key-id-mismatch", "Signed with test1 and k=test1, but the statement says test2.",
        cand(st, header=field("test1", sb, ed25519_ref.sign(SECRETS["test1"], sb))),
        pre("mail", "key_id_mismatch"))
    st = stmt()
    dup = sbytes(st)[:-1] + b',"to":"reviewer@host-c.fleet.example"}'
    one("mail-statement-duplicate-member", "`to` appears twice in validly signed bytes.",
        cand(st, raw=dup), pre("mail", "statement_json"))
    st = stmt()
    one("mail-statement-float-v", "v is the token 1.0: a JSON Schema validator may call it an integer, "
        "but the statement's numbers are lexical integers.",
        cand(st, raw=sbytes(st).replace(b'"v":1,', b'"v":1.0,')), pre("mail", "statement_json"))
    st = stmt(subject="Run the suite")
    one("mail-statement-surrogate", "The subject contains the escape \\ud800, an unpaired surrogate.",
        cand(st, raw=sbytes(st).replace(b"Run the suite", b"Run the suite \\ud800")),
        pre("mail", "statement_json"))
    st = stmt(priority="high")
    one("mail-statement-schema", "A member the closed v1 schema does not define.", cand(st),
        pre("mail", "statement_schema"))
    st = stmt(ts="2026-02-30T15:00:00Z")
    one("mail-statement-ts-not-a-date", "ts matches the pattern but 30 February is not an instant.",
        cand(st), ctl("mail", "statement_value", st))
    st = stmt(sender_since="2026-10-09T15:00:01Z")
    one("mail-statement-sender-since-after-ts", "sender_since is later than ts.", cand(st),
        ctl("mail", "statement_value", st))
    ex = {"asserted_by": "amap.router@host-a.fleet.example", "external_mail_delivered": False,
          "window_start": "2026-10-08T15:00:00Z", "window_end": "2026-10-09T15:00:00Z"}
    st = stmt(sender_exposure=dict(ex, last_external_delivery_ts="2026-10-09T09:00:00Z"))
    one("mail-exposure-last-with-false", "last_external_delivery_ts with external_mail_delivered false.",
        cand(st), ctl("mail", "statement_value", st))
    st = stmt(sender_exposure=dict(ex, window_start="2026-10-09T16:00:00Z"))
    one("mail-exposure-window-inverted", "window_start after window_end.", cand(st),
        ctl("mail", "statement_value", st))
    st = stmt(sender_exposure=dict(ex, external_mail_delivered=True,
                                   last_external_delivery_ts="2026-10-07T09:00:00Z"))
    one("mail-exposure-last-outside-window", "The last delivery lies before the assessed window.",
        cand(st), ctl("mail", "statement_value", st))
    st = stmt(key_id="test3")
    one("mail-key-domain", "test3 is host-b's key; `from` is in host-a's domain.", cand(st),
        ctl("mail", "key_domain", st, runtime="amap.router@host-b.fleet.example"))
    st = stmt(sender_exposure=dict(ex, asserted_by="amap.router@host-b.fleet.example"))
    one("mail-exposure-signer", "asserted_by names host-b's runtime; host-a signed.", cand(st),
        ctl("mail", "exposure_signer", st))
    st = stmt(sender_exposure=dict(ex, asserted_by="someone@host-a.fleet.example"))
    one("mail-exposure-signer-not-runtime", "asserted_by is in the signer's domain but is not its "
        "configured runtime address.", cand(st), ctl("mail", "exposure_signer", st))

    # ------------------------------------------------------------ windows
    st = stmt(ts="2026-10-09T14:05:00Z")
    one("mail-ts-old", "ts 65 minutes before now; P is 60.", cand(st), ctl("mail", "ts_window", st))
    st = stmt(ts="2026-10-09T15:20:00Z")
    one("mail-ts-future", "ts 10 minutes after now; F is 5.", cand(st), ctl("mail", "ts_window", st))
    st = stmt(ts="2026-10-09T14:10:00Z")
    one("peer-ts-lower-bound-inclusive", "ts exactly now - P.", cand(st), peer(st))
    st = stmt(ts="2026-10-09T15:15:00Z")
    one("peer-ts-upper-bound-inclusive", "ts exactly now + F.", cand(st), peer(st))
    st = stmt(ts="2026-10-09T14:09:59Z")
    one("mail-ts-lower-bound-minus-one", "ts one second before now - P.", cand(st),
        ctl("mail", "ts_window", st))

    # ------------------------------------------------------- binding to bytes
    st = stmt()
    one("mail-body-digest", "A relay appended a footer.",
        cand(st, body=(BODY + "-- \nSent via the fleet hub\n").encode()), ctl("mail", "body_digest", st))
    st = stmt()
    one("peer-body-crlf", "The selected leaf decodes to CRLF line breaks (quoted-printable in "
        "transit). The verifier replaces each CRLF pair with LF, as the sender did before hashing.",
        cand(st, body=BODY.replace("\n", "\r\n").encode()), peer(st))
    txt = "line one\rstill line one\nline two  \n.leading dot\n"
    st = stmt(body_sha256=sha(txt.encode()))
    one("peer-body-bare-cr-and-spaces", "A bare CR, trailing spaces and a leading dot are content: "
        "only CRLF pairs are normalised.", cand(st, body=txt.encode()), peer(st, txt))
    txt = "Résumé attached.\n"
    st = stmt(body_sha256=sha(txt.encode()))
    one("peer-body-charset-label-case", "charset label UTF-8 in upper case.",
        cand(st, body=txt.encode(), charset="UTF-8"), peer(st, txt))
    st = stmt()
    one("peer-body-no-charset-ascii", "No charset parameter: us-ascii, and the octets are ASCII.",
        cand(st, charset=None), peer(st))
    st = stmt(body_sha256=sha(txt.encode()))
    one("mail-body-latin1", "charset=iso-8859-1: only utf-8 and us-ascii are allowed.",
        cand(st, body=txt.encode("latin-1"), charset="iso-8859-1"), ctl("mail", "body_charset", st))
    st = stmt(body_sha256=sha(txt.encode()))
    one("mail-body-invalid-utf8", "charset=utf-8, but the octets are Latin-1 (invalid UTF-8).",
        cand(st, body=txt.encode("latin-1")), ctl("mail", "body_charset", st))
    st = stmt(body_sha256=sha(txt.encode()))
    one("mail-body-ascii-label-high-octet", "No charset (us-ascii) but the octets are UTF-8.",
        cand(st, body=txt.encode(), charset=None), ctl("mail", "body_charset", st))
    st = stmt(body_sha256=sha(b""))
    one("peer-body-absent", "No body leaf at all: the empty body, whose digest the sender signed.",
        cand(st, body=False), peer(st, ""))
    st = stmt(attachments=[ATT])
    one("mail-attachment-count", "One attachment signed; none carried.", cand(st),
        ctl("mail", "attachment_count", st))
    st = stmt(attachments=[ATT])
    one("mail-attachment-digest", "The attachment's bytes changed.",
        cand(st, atts=[LOG.replace(b"all", b"ALL")]), ctl("mail", "attachment_digest", st))
    st = stmt()
    one("mail-message-id", "Message-ID decodes to another id.",
        cand(st, mid=f" <AAAAAAAAAAAAAAAAAAAAAA@{A}>"), ctl("mail", "message_id", st))
    st = stmt()
    one("mail-message-id-case", "The id in Message-ID differs from the statement's only in case. The "
        "id is opaque and compared exactly.", cand(st, mid=f" <{st['id'].swapcase()}@{A}>"),
        ctl("mail", "message_id", st))
    st = stmt()
    one("peer-message-id-domain-case", "Only the domain is compared case-insensitively.",
        cand(st, mid=f" <{st['id']}@HOST-A.Fleet.Example>"), peer(st))
    st = stmt()
    one("mail-message-id-wrong-domain", "The Message-ID domain is not the sender's.",
        cand(st, mid=f" <{st['id']}@{A2}>"), ctl("mail", "message_id", st))
    st = stmt()
    c = cand(st)
    c["fields"].insert(0, ["Message-ID", f" <{st['id']}@{A}>"])
    one("mail-message-id-twice", "Two Message-ID fields.", c, ctl("mail", "message_id", st))
    st = stmt()
    one("peer-message-id-folded", "The Message-ID field body folded onto a continuation line.",
        cand(st, mid=f"\r\n <{st['id']}@{A}>"), peer(st))

    # ---------------------------------------------------------- routing
    st = stmt(to=f"builder@host-d.fleet.example")
    one("drop-misrouted", "Authentic and bound, but `to` is not hosted here.", cand(st),
        ctl("drop", "misrouted", st))

    # ------------------------------------------------- sequences: replay
    st = stmt()
    c = cand(st)
    case("seq-duplicate-exact", "The same message delivered twice (or replayed): the second copy "
         "matches a retained record by statement digest and is dropped before any other check. No "
         "control notice for an exact replay.",
         [{"candidate": c, "expect": peer(st)},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    st2 = dict(st, ts="2026-10-09T15:05:00Z")
    case("seq-resend-same-id", "A sending runtime whose hand-off was ambiguous resends the SAME id, "
         "re-signed with a new ts. The first copy arrived, so the resend is dropped as a duplicate, "
         "and the control notice tells the sender. Effective idempotence within the retention only.",
         [{"candidate": cand(st), "expect": peer(st)},
          {"candidate": cand(st2), "expect": ctl("drop", "duplicate", st2)}])
    st = stmt()
    case("seq-integrity-failure-then-intact", "A copy with a mangled body arrives first and is "
         "demoted; it records nothing, so the intact copy is still placed.",
         [{"candidate": cand(st, body=(BODY + "footer\n").encode()), "expect": ctl("mail", "body_digest", st)},
          {"candidate": cand(st), "expect": peer(st)}])
    st = stmt()
    c = cand(st)
    case("seq-crash-after-reserve", "Crash between reservation and placement. Recovery places it "
         "exactly once; a later copy is a duplicate. A concurrent second copy arriving while the first "
         "is reserved is in the same state, and is dropped.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"candidate": c, "expect": pre("drop", "duplicate")},
          {"event": "recover", "expect": {"recovered": [{"id": st["id"], "outcome": "peer"}]}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    c = cand(st)
    case("seq-crash-after-place", "Crash after the notice is durably placed but before the record is "
         "marked done. Recovery finds the placed notice and does not place it again.",
         [{"candidate": c, "crash": "after_place", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [{"id": st["id"], "outcome": "already_placed"}]}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    c = cand(st)
    case("seq-clean-restart", "A restart with the store intact: the record survives.",
         [{"candidate": c, "expect": peer(st)}, {"event": "restart", "expect": {}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    c = cand(st)
    case("multi-duplicate-key-expired", "A known statement replayed after its key expired: dropped as "
         "a duplicate, not demoted for key validity.",
         [{"candidate": c, "expect": peer(st)},
          {"event": "set_key", "keys": {"test1": {"not_after": "2026-10-09T15:10:00Z"}}, "expect": {}},
          {"now": "2026-10-09T15:20:00Z", "candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    c = cand(st)
    case("multi-duplicate-key-removed", "A known statement replayed after its key was removed from "
         "the configuration (retired or revoked): still dropped. Retiring a key never erases replay "
         "evidence.",
         [{"candidate": c, "expect": peer(st)},
          {"event": "remove_key", "key_id": "test1", "expect": {}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt()
    case("multi-duplicate-body-modified", "A known statement replayed with a modified body: dropped "
         "as a duplicate (the statement digest matches) rather than demoted for the body.",
         [{"candidate": cand(st), "expect": peer(st)},
          {"candidate": cand(st, body=b"something else\n"), "expect": pre("drop", "duplicate")}])
    st = stmt()
    c = cand(st)
    case("multi-duplicate-ts-expired-retained", "This receiver retains records for 2 h (retain_s; "
         "MAY exceed P). A known statement replayed after its ts left the window is still dropped.",
         [{"candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T16:30:00Z", "candidate": c, "expect": pre("drop", "duplicate")}],
         patch={"windows": {"ts_past_s": 3600, "ts_future_s": 300, "retain_s": 7200}})
    st = stmt()
    c = cand(st)
    case("seq-replay-after-retention", "With retention equal to P, a replay after ts + P finds no "
         "record and fails the window: demoted, never placed. No exactly-once claim beyond retention.",
         [{"candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T16:00:01Z", "candidate": c, "expect": ctl("mail", "ts_window", st)}])

    # ------------------------------------------------- sequences: recovery
    st = stmt(ts="2026-10-09T15:04:00Z")
    c = cand(st)
    st2 = stmt(ts="2026-10-09T15:07:00Z")
    case("seq-store-loss-future-skew", "At 15:00 the receiver accepts ts 15:04 (within F). "
         "It loses its store; coverage restarts at C = 15:01, so the floor is max(C, H) + F + 1 s = "
         "15:06:01. The replay at 15:02 is below the floor: demoted, not placed a second time. A new "
         "statement at 15:07 is placed.",
         [{"now": "2026-10-09T15:00:00Z", "candidate": c, "expect": peer(st)},
          {"event": "lose_store", "at": "2026-10-09T15:01:00Z", "expect": {}},
          {"now": "2026-10-09T15:02:00Z", "candidate": c, "expect": ctl("mail", "ts_window", st)},
          {"now": "2026-10-09T15:07:00Z", "candidate": cand(st2), "expect": peer(st2)}],
         patch={"now": "2026-10-09T15:00:00Z"})
    st = stmt(ts="2026-10-09T15:06:00Z")
    st2 = stmt(ts="2026-10-09T15:06:01Z")
    case("seq-store-loss-floor-boundary", "The floor is STRICTLY above max(C, H) + F: with C = H = 15:01 "
         "and F = 300, ts 15:06:00 could already have been accepted before the loss and is demoted; "
         "15:06:01 is the first admissible instant.",
         [{"event": "lose_store", "at": "2026-10-09T15:01:00Z", "expect": {}},
          {"now": "2026-10-09T15:06:00Z", "candidate": cand(st), "expect": ctl("mail", "ts_window", st)},
          {"candidate": cand(st2), "expect": peer(st2)}],
         patch={"now": "2026-10-09T15:00:00Z"})
    st = stmt(ts="2026-10-09T15:05:00Z")
    c = cand(st)
    st2 = stmt(ts="2026-10-09T15:05:01Z")
    case("seq-store-loss-at-equality", "At 15:00 the receiver accepts ts 15:05, exactly "
         "now + F. It loses the store while its clock still reads 15:00. An inclusive floor of C + F "
         "would re-admit that statement; the floor is C + F + 1 s = 15:05:01, so the replay is demoted "
         "and a statement at 15:05:01 is placed.",
         [{"now": "2026-10-09T15:00:00Z", "candidate": c, "expect": peer(st)},
          {"event": "lose_store", "at": "2026-10-09T15:00:00Z", "expect": {}},
          {"candidate": c, "expect": ctl("mail", "ts_window", st)},
          {"now": "2026-10-09T15:01:00Z", "candidate": cand(st2), "expect": peer(st2)}],
         patch={"now": "2026-10-09T15:00:00Z"})
    st = stmt(ts="2026-10-09T15:00:00Z")
    c = cand(st)
    case("seq-store-loss-after-rollback", "Accepted at 15:00. The clock steps back to 14:50 "
         "and the store is lost there; H (15:00) survives. The floor uses max(C, H), so it is 15:00 + F + "
         "1 s = 15:05:01, not 14:55, and the replay at 15:01 is demoted.",
         [{"now": "2026-10-09T15:00:00Z", "candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T14:50:00Z", "event": "lose_store", "at": "2026-10-09T14:50:00Z", "expect": {}},
          {"now": "2026-10-09T15:01:00Z", "candidate": c, "expect": ctl("mail", "ts_window", st)}],
         patch={"now": "2026-10-09T15:00:00Z"})
    st = dict(stmt(ts="2026-10-09T15:15:00Z"), id="Um9sbGJhY2tMYXJnZXJGMDAx")   # fixed ids: adding
    st2 = dict(stmt(ts="2026-10-09T15:15:01Z"), id="Um9sbGJhY2tMYXJnZXJGMDAy")  # this case in r4
    _n[0] -= 2                                                                  # leaves other ids unchanged
    c = cand(st)
    case("seq-store-loss-rollback-larger-f", "F is 300 at 14:00 and raised to 900 at "
         "15:00, when ts 15:15 (now + F) is accepted. The clock steps back to 14:00, F returns to 300, "
         "and the store is lost there with H (15:00) intact. Fmax comes from all retained F history "
         "(900), not from the interval before C (300): the floor is 15:00 + 900 + 1 s = 15:15:01, so "
         "the replay at 15:10 is demoted, and a statement at 15:15:01 is placed.",
         [{"now": "2026-10-09T15:00:00Z", "event": "set_windows",
           "windows": {"ts_past_s": 3600, "ts_future_s": 900, "retain_s": 3600}, "expect": {}},
          {"candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T14:00:00Z", "event": "set_windows",
           "windows": {"ts_past_s": 3600, "ts_future_s": 300, "retain_s": 3600}, "expect": {}},
          {"event": "lose_store", "at": "2026-10-09T14:00:00Z", "expect": {}},
          {"now": "2026-10-09T15:10:00Z", "candidate": c, "expect": ctl("mail", "ts_window", st)},
          {"now": "2026-10-09T15:11:00Z", "candidate": cand(st2), "expect": peer(st2)}],
         patch={"now": "2026-10-09T14:00:00Z"})
    st = stmt(ts="2026-10-09T15:00:00Z")
    c = cand(st)
    st2 = stmt(ts="2026-10-09T15:15:01Z")
    case("seq-store-loss-h-lost", "The store AND the high-water clock H are lost: no trustworthy bound "
         "exists, so peer admission closes. A candidate reaching check 7 is held in intake, not demoted. "
         "The operator records a bound B = 15:10 (at or after the largest receiver time before the "
         "loss); the floor becomes B + F + 1 s = 15:15:01, admission reopens, and the held candidate is "
         "evaluated in order: its ts 15:00 is below the floor, so it is demoted. A statement at "
         "15:15:01 is then placed.",
         [{"now": "2026-10-09T15:00:00Z", "candidate": c, "expect": peer(st)},
          {"event": "lose_store", "at": "2026-10-09T15:01:00Z", "h_lost": True, "expect": {}},
          {"now": "2026-10-09T15:02:00Z", "candidate": c, "expect": {"outcome": "held", "cause": "admission_closed"}},
          {"event": "set_bound", "bound": "2026-10-09T15:10:00Z",
           "expect": {"released": [ctl("mail", "ts_window", st)]}},
          {"now": "2026-10-09T15:12:00Z", "candidate": cand(st2), "expect": peer(st2)}],
         patch={"now": "2026-10-09T15:00:00Z"})
    st = stmt()
    c = cand(st)
    case("seq-clock-rollback", "Placed at 15:10; the clock reaches 16:05 and the record is pruned "
         "(16:05 > ts + P). The clock then steps back to 15:50, where ts would look fresh. The lower "
         "bound uses the persisted high-water time, so the replay is demoted, not placed.",
         [{"candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T16:05:00Z", "event": "restart", "expect": {}},
          {"now": "2026-10-09T15:50:00Z", "candidate": c, "expect": ctl("mail", "ts_window", st)}])
    st = stmt()
    c = cand(st)
    case("seq-window-widened", "Placed at 15:10; at 16:05 the record is pruned; the operator then "
         "raises P to 2 h. The lower bound never moves below what it was at the change, so the old "
         "statement stays outside the window.",
         [{"candidate": c, "expect": peer(st)},
          {"now": "2026-10-09T16:05:00Z", "event": "set_windows",
           "windows": {"ts_past_s": 7200, "ts_future_s": 300, "retain_s": 7200}, "expect": {}},
          {"now": "2026-10-09T16:06:00Z", "candidate": c, "expect": ctl("mail", "ts_window", st)}])

    # ------------------------------------------ sequences: dispositions
    RB = "amap.router@host-b.fleet.example"
    st = stmt(from_=f"planner@{A2}", key_id="test3", to=REVIEWER_C)
    c = cand(st)
    case("seq-crash-after-reserve-no-edge", "A verified task with NO edge crashes after "
         "reservation, before the decision. Recovery decides the undecided reservation under the "
         "current configuration and refuses it; it never places it. The control notice goes out once, "
         "on recovery. A replay is a known statement.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [rec(st, "refuse", "no_edge", runtime=RB)]}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt(to="builder@host-d.fleet.example")
    c = cand(st)
    case("seq-crash-after-reserve-misrouted", "A misrouted candidate crashes after "
         "reservation. Recovery drops it; nothing is placed.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [rec(st, "drop", "misrouted")]}}])
    st = stmt(sender_since="2026-10-09T00:00:00Z")
    c = cand(st)
    case("seq-crash-after-reserve-quarantined", "A candidate a deployment policy will "
         "refuse (sender age 15 h, 24 h required) crashes after reservation. Recovery refuses it with "
         "the policy code; nothing is placed.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [rec(st, "refuse", "policy", code="quarantined")]}}],
         patch={"min_sender_age_s": 86400})
    st = stmt(in_reply_to="ffffffffffffffffffffffffffffffff", subject="Re: something")
    c = cand(st)
    case("seq-crash-after-reserve-unresolved-reply", "An unresolvable reply crashes after "
         "reservation. Recovery refuses it; nothing is placed.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [rec(st, "refuse", "unresolved_reply")]}}])
    st = stmt()
    c = cand(st)
    case("seq-crash-after-reserve-edge-removed", "An undecided reservation is decided at recovery "
         "under the configuration in force THEN: the edge planner -> builder was removed while the "
         "receiver was down, so a task that would have been placed is refused.",
         [{"candidate": c, "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "set_edges", "edges": [[f"planner@{A2}", BUILDER]], "expect": {}},
          {"event": "recover", "expect": {"recovered": [rec(st, "refuse", "no_edge")]}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])
    st = stmt(from_=f"planner@{A2}", key_id="test3", to=REVIEWER_C)
    c = cand(st)
    st2 = dict(st, ts="2026-10-09T15:05:00Z")
    case("seq-crash-after-decide-refuse", "The refusal is decided and persisted, then the receiver "
         "crashes before the control notice is durably queued. Recovery resumes the recorded "
         "disposition: it sends the pending notice once and never publishes. A later re-signed copy of "
         "the same id is a check-12 duplicate.",
         [{"candidate": c, "crash": "after_decide", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [rec(st, "refuse", "no_edge", runtime=RB)]}},
          {"candidate": cand(st2), "expect": ctl("drop", "duplicate", st2, runtime=RB)}])
    st = stmt()
    c = cand(st)
    case("seq-crash-after-decide-place", "The placement is decided and persisted, then the receiver "
         "crashes before the notice is written. Recovery places it exactly once.",
         [{"candidate": c, "crash": "after_decide", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [{"id": st["id"], "outcome": "peer"}]}},
          {"candidate": c, "expect": pre("drop", "duplicate")}])

    # ------------------------------------------ re-signing beyond retention
    st = stmt(ts="2026-10-09T15:00:00Z")
    st2 = dict(st, ts="2026-10-09T16:00:00Z")
    case("seq-resign-after-retention", "THE FINITE-RETENTION CONSEQUENCE, pinned: with retention equal "
         "to P, the record is pruned at 16:00:01. A resend of the same id re-signed with a fresh ts "
         "then finds no record and is PLACED AGAIN. The profile's MAY to resend is therefore "
         "idempotent only within retention; a deployment that cannot accept this forbids re-signing "
         "(§5.5).",
         [{"candidate": cand(st), "expect": peer(st)},
          {"now": "2026-10-09T16:00:01Z", "candidate": cand(st2), "expect": peer(st2)}])

    # ------------------------------------------ sender_since continuity
    pol = {"min_sender_age_s": 86400}
    st = stmt(sender_since="2026-09-30T08:00:00Z")
    st2 = stmt(sender_since="2026-09-01T08:00:00Z")
    st3 = stmt(sender_since="2026-10-09T00:00:00Z")
    case("seq-sender-since-inconsistent", "A receiver that enforces a sender age remembers the last "
         "sender_since it saw per (runtime, from). A later statement asserting an EARLIER value claims "
         "an older enrolment than before: inconsistent, refused. A LATER value is a new enrolment of "
         "the identity, so its age starts again and it is quarantined.",
         [{"candidate": cand(st), "expect": peer(st)},
          {"candidate": cand(st2), "expect": ctl("refuse", "policy", st2, code="sender_since_inconsistent")},
          {"candidate": cand(st3), "expect": ctl("refuse", "policy", st3, code="quarantined")}],
         patch=pol)

    # ------------------------------------------ configuration refusals (§5.7)
    HA = {"name": "host-a", "runtime": "amap.router@host-a.fleet.example", "domains": [A],
          "keys": [{"key_id": "test1", "public_key": PUB["test1"]}, {"key_id": "test2", "public_key": PUB["test2"]}]}
    HB = {"name": "host-b", "runtime": "amap.router@host-b.fleet.example", "domains": [A2],
          "keys": [{"key_id": "test3", "public_key": PUB["test3"]}]}
    case("config-duplicate-key-id-across-peers", "key_id test1 configured for two different peers: "
         "the receiver selects by k alone, so uniqueness is across ALL peers, and the configuration is "
         "refused at load.", [],
         patch={"peers": [HA, dict(HB, keys=[{"key_id": "test1", "public_key": PUB["test3"]}])]},
         config_error="duplicate_key_id")
    case("config-inverted-validity", "A key whose not_before is after its not_after: refused at load.", [],
         patch={"peers": [dict(HA, keys=[{"key_id": "test1", "public_key": PUB["test1"],
                                          "not_before": "2026-10-09T15:20:00Z",
                                          "not_after": "2026-10-09T15:00:00Z"}]), HB]},
         config_error="inverted_validity")
    case("config-key-non-canonical", "A public key that is not a canonical encoding of a curve point "
         "(y = p + 1): refused at load, a SEPARATE gate from verification. A bare Ed25519 backend may "
         "construct it; the key loader must not.", [],
         patch={"peers": [dict(HA, keys=[{"key_id": "test1",
                                          "public_key": "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f"}]), HB]},
         config_error="key_not_canonical")
    case("config-key-small-order", "A small-order public key (the identity): refused at load. With "
         "R = identity and S = 0 the bare equation would accept any message under it.", [],
         patch={"peers": [dict(HA, keys=[{"key_id": "test1",
                                          "public_key": "0100000000000000000000000000000000000000000000000000000000000000"}]), HB]},
         config_error="key_small_order")

    # ------------------------------------------------------- control notices (§5.8)
    RA = "receiver-host-a.json"
    about = "4f0c9a2e7b1d4c83a6e5f2b9d0c17e48"

    def cstmt(**kw):
        c = {"v": 1, "key_id": "test3", "kind": "control", "id": nid(),
             "from": "amap.router@host-c.fleet.example", "to": "amap.router@host-a.fleet.example",
             "ts": "2026-10-09T15:10:05Z", "about": about, "outcome": "refused", "cause": "no_edge"}
        c.update(kw)
        return c

    def ccand(c, **kw):
        sb = sbytes(c)
        sig = ed25519_ref.sign(SECRETS[kw.get("sign_key", c["key_id"])], sb)
        hv = kw.get("header", field(c["key_id"], sb, sig))
        return {"fields": [["Message-ID", f" <{c['id']}@host-c.fleet.example>"],
                           [kw.get("name", "AMAP-Peer-Control"), hv]],
                "body": None, "attachments": []}

    c = cstmt()
    accepted = {"outcome": "control", "notify": {"agent": PLANNER, "about": about,
                                                 "outcome": "refused", "cause": "no_edge"}}
    one("control-accepted", "host-c tells host-a that planner's task was refused (no edge). host-a "
        "gives planner a runtime-authored failure notice in inbound/ (§4's DSN analogue); nothing is "
        "placed in peer/.", ccand(c), accepted, receiver=RA)
    c = cstmt(outcome="refused", cause="policy", policy_code="quarantined")
    one("control-accepted-policy", "A deployment refusal with its policy code.", ccand(c),
        {"outcome": "control", "notify": {"agent": PLANNER, "about": about, "outcome": "refused",
                                          "cause": "policy", "policy_code": "quarantined"}}, receiver=RA)
    c = cstmt()
    case("control-replay", "The same control notice twice: the second is a duplicate.",
         [{"candidate": ccand(c), "expect": accepted},
          {"candidate": ccand(c), "expect": pre("drop", "duplicate")}], receiver=RA)
    c = cstmt()
    case("seq-control-crash-before-agent-notice", "The control notice is verified and its "
         "record reserved, then the receiver crashes before the agent's failure notice is durable. The "
         "record is not done, so recovery writes the failure notice once; a replay is a duplicate.",
         [{"candidate": ccand(c), "crash": "after_reserve", "expect": {"outcome": "crashed"}},
          {"event": "recover", "expect": {"recovered": [{"id": c["id"], "outcome": "control",
                                                        "notify": accepted["notify"]}]}},
          {"candidate": ccand(c), "expect": pre("drop", "duplicate")}], receiver=RA)
    c = cstmt()
    c2 = cstmt(outcome="dropped", cause="duplicate")
    case("control-duplicate-about", "Two control notices with different ids about the SAME issued "
         "message: the issuing agent gets at most one failure notice per message, so the second is "
         "dropped. (A dropped/duplicate report proves a prior reservation exists, whose disposition "
         "may have been placement; it does not prove the task failed.)",
         [{"candidate": ccand(c), "expect": accepted},
          {"candidate": ccand(c2), "expect": pre("drop", "duplicate_about")}], receiver=RA)
    c = cstmt()
    sb = sbytes(c)
    one("control-bad-signature", "Altered after signing: dropped, never mailed.",
        ccand(c, header=field("test3", sb.replace(b"no_edge", b"no_edgf"),
                              ed25519_ref.sign(SECRETS["test3"], sb))), pre("drop", "signature"),
        receiver=RA)
    c = cstmt(from_="builder@host-c.fleet.example")
    c["from"] = c.pop("from_")
    one("control-from-not-runtime", "Signed by host-c's key, but `from` is an agent, not host-c's "
        "configured runtime address.", ccand(c), pre("drop", "control_signer"), receiver=RA)
    c = cstmt(about="AAAAAAAAAAAAAAAAAAAAAA")
    one("control-about-unknown", "`about` names nothing this runtime issued.", ccand(c),
        pre("drop", "unknown_about"), receiver=RA)
    c = cstmt(about="SXNzdWVkVG9Ib3N0QjAwMDAw")
    one("control-about-other-host", "`about` names a message this runtime issued to host-b; host-c "
        "may not report on it.", ccand(c), pre("drop", "unknown_about"), receiver=RA)
    c = cstmt()
    one("control-in-statement-field", "A control notice carried in AMAP-Peer-Statement: it fails the "
        "peer-statement schema (kind) and is treated as a failed statement, without a control notice "
        "in return, so control traffic cannot loop.", ccand(c, name="AMAP-Peer-Statement"),
        pre("mail", "statement_schema"), receiver=RA)
    st = stmt(from_="builder@host-c.fleet.example", to=PLANNER, key_id="test3")
    sb = sbytes(st)
    one("control-field-carrying-statement", "A peer statement carried in AMAP-Peer-Control: it fails "
        "the control schema and is dropped.",
        {"fields": [["Message-ID", f" <{st['id']}@host-c.fleet.example>"],
                    ["AMAP-Peer-Control", field("test3", sb, ed25519_ref.sign(SECRETS["test3"], sb))]],
         "body": None, "attachments": []},
        pre("drop", "statement_schema"), receiver=RA)
    c = cstmt()
    cc = ccand(c)
    st = stmt()
    cc["fields"].append(["AMAP-Peer-Statement", cand(st)["fields"][1][1]])
    one("control-and-statement-together", "A message carrying both fields is neither: dropped.",
        cc, pre("drop", "header_count"), receiver=RA)


MIME = []


def mime(name, description, raw: bytes, candidate):
    MIME.append((name, description, raw, candidate))


def build_mime():
    st = stmt()
    sb = sbytes(st)
    hv = field("test1", sb, ed25519_ref.sign(SECRETS["test1"], sb)).strip()
    folded = hv[:60] + "\r\n " + hv[60:]
    head = (f"From: {PLANNER}\r\nTo: {BUILDER}\r\nSubject: Run the conformance suite\r\n"
            f"Message-ID: <{st['id']}@{A}>\r\nAMAP-Peer-Statement: {folded}\r\nMIME-Version: 1.0\r\n")
    fields = [["Message-ID", f"<{st['id']}@{A}>"], ["AMAP-Peer-Statement", folded]]
    log64 = b64(LOG)

    mime("single-text-plain-qp", "A single text/plain part, quoted-printable, CRLF line breaks. The "
         "candidate's body octets keep the CRLF; the verifier normalises.",
         (head + "Content-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\n"
          "Please run the conformance suite on main and report the re=\r\nsult.\r\n").encode(),
         {"fields": fields, "body": {"charset": "utf-8", "octets_b64": b64(BODY.replace("\n", "\r\n").encode())},
          "attachments": []})
    mixed = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
             "--b1\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
             + b64(BODY.encode()) + "\r\n"
             "--b1\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=gate.log\r\n"
             "Content-Transfer-Encoding: base64\r\n\r\n" + log64 + "\r\n--b1--\r\n").encode()
    mime("mixed-text-and-attachment", "The recommended shape: multipart/mixed[text/plain, attachment].",
         mixed, {"fields": fields, "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())},
                 "attachments": [{"octets_b64": log64}]})
    html = b"<p>Please run the suite.</p>\n"
    alt = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
           '--b1\r\nContent-Type: multipart/alternative; boundary="b2"\r\n\r\n'
           "--b2\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           + b64(BODY.encode()) + "\r\n"
           "--b2\r\nContent-Type: text/html; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           + b64(html) + "\r\n--b2--\r\n"
           "--b1\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=gate.log\r\n"
           "Content-Transfer-Encoding: base64\r\n\r\n" + log64 + "\r\n--b1--\r\n").encode()
    mime("alternative-inside-mixed", "multipart/alternative inside mixed: the first non-attachment "
         "text/plain leaf, depth-first, is the body; the text/html leaf is an attachment (so a sender "
         "that signed only gate.log fails the attachment count, as intended).",
         alt, {"fields": fields, "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())},
               "attachments": [{"octets_b64": b64(html)}, {"octets_b64": log64}]})
    att_first = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
                 "--b1\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename=gate.log\r\n"
                 "Content-Transfer-Encoding: base64\r\n\r\n" + log64 + "\r\n"
                 "--b1\r\nContent-Type: text/plain; charset=us-ascii\r\nContent-Disposition: inline\r\n\r\n"
                 + BODY.replace("\n", "\r\n") + "--b1--\r\n").encode()
    mime("attachment-text-first", "A text/plain leaf with disposition attachment is never the body; "
         "the next text/plain leaf is, even though it comes second. It is 7bit, so the CRLF before the "
         "closing boundary belongs to the boundary (RFC 2046 §5.1.1) and the octets lack a final line "
         "break: one reason a sender SHOULD use base64.",
         att_first, {"fields": fields,
                     "body": {"charset": "us-ascii",
                              "octets_b64": b64(BODY.replace("\n", "\r\n").encode()[:-2])},
                     "attachments": [{"octets_b64": log64}]})
    only_att = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
                "--b1\r\nContent-Type: application/octet-stream\r\nContent-Transfer-Encoding: base64\r\n\r\n"
                + log64 + "\r\n--b1--\r\n").encode()
    mime("no-text-leaf", "No text/plain leaf: no body (the empty body); the only leaf is an attachment.",
         only_att, {"fields": fields, "body": None, "attachments": [{"octets_b64": log64}]})
    inner = (b"From: builder@host-c.fleet.example\r\nTo: planner@host-a.fleet.example\r\n"
             b"Subject: the original request\r\nMessage-ID: <orig-1@host-c.fleet.example>\r\n\r\n"
             b"Original body, line one.\r\nLine two.\r\n")
    nested = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
              "--b1\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
              + b64(BODY.encode()) + "\r\n"
              "--b1\r\nContent-Type: message/rfc822\r\nContent-Disposition: attachment\r\n\r\n").encode() \
        + inner + b"\r\n--b1--\r\n"
    mime("nested-message-rfc822", "A message/rfc822 attachment is a leaf whose octets are its "
         "part body AS TRANSMITTED (7bit, CRLF line breaks intact). Re-serialising the nested message "
         "changes its bytes and its digest; the candidate carries the raw slice, which ends before "
         "the CRLF that belongs to the next boundary.",
         nested, {"fields": fields, "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())},
                  "attachments": [{"octets_b64": b64(inner)}]})
    csv = b"name,result\r\nvalidate.py,ok=89\r\ncheck_cases.py,ok"   # the final CRLF is the boundary's
    qp = (head + 'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
          "--b1\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
          + b64(BODY.encode()) + "\r\n"
          "--b1\r\nContent-Type: text/csv\r\nContent-Disposition: attachment; filename=gate.csv\r\n"
          "Content-Transfer-Encoding: quoted-printable\r\n\r\n"
          "name,result\r\nvalidate.py,ok=3D89\r\ncheck_=\r\ncases.py,ok\r\n--b1--\r\n").encode()
    mime("attachment-qp-crlf", "A quoted-printable attachment with a soft line break and an encoded "
         "'=': the leaf's octets are the transfer-DECODED bytes, hard CRLF line breaks preserved, and "
         "the CRLF before the closing boundary excluded (RFC 2046 §5.1.1); the sender signed exactly these.",
         qp, {"fields": fields, "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())},
              "attachments": [{"octets_b64": b64(csv)}]})
    two = (f"From: {PLANNER}\r\nTo: {BUILDER}\r\nSubject: Run the conformance suite\r\n"
           f"Message-ID: <{st['id']}@{A}>\r\nAMAP-Peer-Statement: {folded}\r\n").encode() \
        + b"AMAP-Peer-Statement: k=test1; s=\xc3\xa9; b=AAAA\r\n" \
        + ("MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           + b64(BODY.encode()) + "\r\n").encode()
    inter = (f"From: {PLANNER}\r\nTo: {BUILDER}\r\nSubject: Run the conformance suite\r\n"
             f"AMAP-Peer-Statement: {folded}\r\nMessage-ID: <{st['id']}@{A}>\r\n").encode() \
        + b"AMAP-Peer-Statement: k=test1; s=\xc3\xa9; b=AAAA\r\n" \
        + ("MIME-Version: 1.0\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n"
           + b64(BODY.encode()) + "\r\n").encode()
    mime("interleaved-fields-message-order", "The fields arrive as Statement, "
         "Message-ID, invalid Statement. The candidate keeps MESSAGE order, one traversal of the "
         "header, never grouped by name, with the invalid marker in its own position.",
         inter, {"fields": [["AMAP-Peer-Statement", folded], ["Message-ID", f"<{st['id']}@{A}>"],
                            ["AMAP-Peer-Statement", {"invalid": "non_ascii"}]],
                 "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())}, "attachments": []})
    mime("second-statement-field-non-ascii", "A second AMAP-Peer-Statement field whose body is "
         "not ASCII. The admitting component MUST NOT drop it (that would leave one valid field): it "
         "carries an explicit invalid marker in the field's position, so the verifier still counts two "
         "fields and fails the candidate.",
         two, {"fields": fields + [["AMAP-Peer-Statement", {"invalid": "non_ascii"}]],
               "body": {"charset": "utf-8", "octets_b64": b64(BODY.encode())}, "attachments": []})


def main() -> int:
    build()
    out = HERE / "cases"
    out.mkdir(exist_ok=True)
    names = set()
    for name, doc in CASES:
        names.add(name + ".json")
        (out / f"{name}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    for stale in out.glob("*.json"):
        if stale.name not in names:
            stale.unlink()
    _n[0] = 10_000
    build_mime()
    mdir = HERE / "mime"
    mdir.mkdir(exist_ok=True)
    keep = set()
    for name, description, raw, candidate in MIME:
        (mdir / f"{name}.eml").write_bytes(raw)
        (mdir / f"{name}.json").write_text(json.dumps(
            {"description": description, "eml": f"{name}.eml", "candidate": candidate},
            indent=2, ensure_ascii=False) + "\n")
        keep |= {f"{name}.eml", f"{name}.json"}
    for stale in mdir.iterdir():
        if stale.name not in keep:
            stale.unlink()
    print(f"wrote {len(CASES)} cases and {len(MIME)} MIME cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
