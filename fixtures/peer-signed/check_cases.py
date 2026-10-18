#!/usr/bin/env python3
"""Check the signed peer-statement and control cases (peer-origin §5). Stdlib only.

    python3 fixtures/peer-signed/check_cases.py

fixtures/validate.py runs this after the schema fixtures. It checks:

1. ed25519_ref.py against the RFC 8032 §7.1 vectors, and every NEGATIVE
   vector against §5.7's verification policy, so the cases are never verified
   by an Ed25519 that is itself wrong or lax. Vectors marked `reject_at:
   config` are a separate gate from verification: the key loader refuses them.
2. Each MIME case in mime/: the raw message, reduced by §5.2's selection rule
   to a candidate, equals the declared candidate. The reduction here is a
   byte-exact splitter: a leaf's octets are its transmitted part body after
   transfer decoding, never a re-serialisation.
3. Each case in cases/: a sequence of steps (candidates and events) run
   against a fresh receiver built from the named receiver file, with every
   step's declared outcome, cause, published fields and control notice. A
   case with `config_error` expects the receiver to refuse its configuration.

The receiver files (receiver.json, receiver-host-a.json) configure the
receiver a case runs against. Their `windows` keys are §5.5's windows, in
seconds: `ts_future_s` is F, `ts_past_s` is P, and `retain_s` is how long a
`done` record is kept, measured like P (a record is pruned once H > ts +
max(P, retain_s)). The receiver files set `retain_s` equal to P, the minimum
§5.5 allows, and the cases that probe the retention boundary
(seq-clock-rollback, seq-window-widened, seq-replay-after-retention,
seq-resign-after-retention) assume that minimum. A receiver that retains
records longer, as §5.5 permits, reaches a different but conforming outcome
at those steps, and maps them by its own retention.

This is a fixture self-check, not a runtime. It holds no real key, reads no
mail and writes nothing. The `Receiver` below models only the state §5.5
makes normative (the replay store with its reservation, decision and done
states, the floor and high-water clock, the pending control notices, the
retained candidate in intake); an implementation proves itself by reaching
every step's `expect` by its own code. The evaluation order is §5.3's.
"""
from __future__ import annotations

import base64
import binascii
import copy
import email.parser
import email.policy
import hashlib
import json
import quopri
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ed25519_ref  # noqa: E402

STATEMENT, CONTROL, MSGID = "amap-peer-statement", "amap-peer-control", "message-id"
MAX_FIELD_OCTETS = 12288
MAX_STATEMENT_BYTES = 8192
MAX_F = 900
KEY_ID = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
B64U = re.compile(r"\A[A-Za-z0-9_-]+\Z")
TS_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
MSGID_RE = re.compile(r"\A<([^<>@\s]+)@([^<>@\s]+)>\Z")


class Outcome(Exception):
    def __init__(self, outcome, cause=None, **extra):
        self.result = {"outcome": outcome}
        if cause:
            self.result["cause"] = cause
        self.result.update(extra)


class ConfigError(Exception):
    """§5.7: the receiver refuses to load this configuration."""


def _ts(s: str) -> float:
    if not TS_RE.match(s):
        raise ValueError(s)
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def _addr(a: str) -> str:
    """Local part exact, domain ASCII case-insensitive (§5.2)."""
    local, _, dom = a.rpartition("@")
    return f"{local}@{dom.lower()}"


def _dom(a: str) -> str:
    return a.rpartition("@")[2].lower()


def _b64u(s: str) -> bytes:
    if not B64U.match(s) or len(s) % 4 == 1:
        raise ValueError("not unpadded base64url")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _strict_json(sb: bytes):
    """§5.3 check 5(a): UTF-8, no BOM, no repeated member, lexical integers
    only, no non-JSON constant, no unpaired surrogate in any string."""
    def pairs(ps):
        out = {}
        for k, v in ps:
            if k in out:
                raise ValueError("repeated member")
            out[k] = v
        return out

    def bad(_):
        raise ValueError("fraction, exponent or non-JSON constant")

    text = sb.decode("utf-8")
    if text.startswith("﻿"):
        raise ValueError("BOM")
    doc = json.loads(text, object_pairs_hook=pairs, parse_float=bad, parse_constant=bad)

    def walk(x):
        if isinstance(x, str):
            x.encode("utf-8")  # raises on an unpaired surrogate
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(k)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(doc)
    return doc


def parse_field(value):
    """§5.3 check 1: the literal field value; remove SP, HTAB, CR, LF; then
    exactly k, s and b. An admitting component's marker (oversize, invalid)
    is a failure that still counts as one field."""
    if isinstance(value, dict):
        raise Outcome("mail", "header_size" if value.get("oversize") else "header_encoding")
    if any(ord(c) > 0x7F for c in value):
        raise Outcome("mail", "header_encoding")
    compact = re.sub(r"[ \t\r\n]", "", value)
    tags = {}
    for part in compact.split(";"):
        m = re.match(r"\A([a-z])=(.*)\Z", part, re.S)
        if not m or m.group(1) in tags:
            raise Outcome("mail", "header_encoding")
        tags[m.group(1)] = m.group(2)
    if set(tags) != {"k", "s", "b"} or not KEY_ID.match(tags["k"]):
        raise Outcome("mail", "header_encoding")
    try:
        sb, sig = _b64u(tags["s"]), _b64u(tags["b"])
    except ValueError:
        raise Outcome("mail", "header_encoding")
    if len(sig) != 64 or len(sb) > MAX_STATEMENT_BYTES:
        raise Outcome("mail", "header_encoding")
    return tags["k"], sb, sig


def body_text(body) -> str:
    """§5.2: strict utf-8 or us-ascii, then CRLF pairs -> LF. No body leaf
    is the empty body."""
    if body is None:
        return ""
    raw = base64.b64decode(body["octets_b64"], validate=True)
    cs = (body.get("charset") or "us-ascii").lower()
    try:
        if cs == "utf-8":
            text = raw.decode("utf-8")
        elif cs == "us-ascii":
            text = raw.decode("ascii")
        else:
            raise ValueError(cs)
    except ValueError:
        raise Outcome("mail", "body_charset")
    return text.replace("\r\n", "\n")


def _control_for(outcome, cause, peer, st, policy_code=None):
    ctl = {"outcome": {"mail": "demoted", "drop": "dropped", "refuse": "refused"}[outcome],
           "cause": cause, "to": peer["runtime"], "about": st["id"]}
    if policy_code:
        ctl["policy_code"] = policy_code
    return ctl


class Receiver:
    def __init__(self, cfg: dict, schemas: dict, validate):
        self.cfg = cfg
        self.schemas, self.validate = schemas, validate
        self.now = _ts(cfg["now"])
        self.high = self.now                        # persisted high-water clock H
        self.floor = _ts(cfg["store"]["floor"]) if cfg["store"].get("floor") else None
        self.closed = False                         # peer admission closed (H lost, §5.5)
        self.records = {}                           # (peer, id) -> record
        self.placed = set()                         # notice ids durably in peer/
        self.held = []                              # candidates held while closed
        self.since_seen = {}                        # (peer, from) -> last sender_since
        self.reported_about = set()                 # issued ids already given a failure notice
        seen = set()                                # §5.7: key_id unique across ALL peers
        for p in cfg["peers"]:
            for k in p["keys"]:
                if k["key_id"] in seen:
                    raise ConfigError("duplicate_key_id")
                seen.add(k["key_id"])
                nb, na = k.get("not_before"), k.get("not_after")
                if nb and na and _ts(nb) > _ts(na):
                    raise ConfigError("inverted_validity")
                try:
                    ed25519_ref.load_public_key(bytes.fromhex(k["public_key"]))
                except ValueError as e:
                    raise ConfigError("key_small_order" if "small" in str(e) else "key_not_canonical")
        self._windows_history = [(self.now, cfg["windows"]["ts_future_s"])]

    # ---- time and store ----------------------------------------------------
    @property
    def P(self):
        return self.cfg["windows"]["ts_past_s"]

    @property
    def F(self):
        return self.cfg["windows"]["ts_future_s"]

    def fmax(self):
        return max(f for _, f in self._windows_history)

    def set_now(self, ts):
        self.now = _ts(ts)
        self.high = max(self.high, self.now)
        self.prune()

    def prune(self):
        keep = max(self.P, self.cfg["windows"]["retain_s"])
        for key, r in list(self.records.items()):
            if r["state"] == "done" and self.high > r["ts"] + keep:
                del self.records[key]

    def lower_bound(self):
        lb = self.high - self.P
        return max(lb, self.floor) if self.floor is not None else lb

    def lose_store(self, at, h_lost=False, f_history_lost=False):
        """Store lost or incompletely restored: coverage restarts at `at`.
        §5.5: the floor excludes every ts that could already have been
        accepted: strictly greater than max(C, H at loss) + Fmax. If H is
        lost too, no trustworthy bound exists and admission closes. Losing H
        does not by itself lose the F history; `f_history_lost` says it was
        lost too, and Fmax then falls back to 900, the largest F allowed."""
        self.set_now(at)
        self.records = {}
        if f_history_lost:
            self._windows_history = [(self.now, MAX_F)]
        if h_lost:
            self.high = self.now
            self.closed = True
            return
        self.floor = max(self.floor or 0, max(self.now, self.high) + self.fmax() + 1)

    def set_bound(self, bound):
        """An operator-supplied bound B >= the largest receiver time before the
        loss. Reopens admission; held candidates are evaluated in order."""
        b = _ts(bound)
        self.high = max(self.high, b)
        self.floor = max(self.floor or 0, b + self.fmax() + 1)
        self.closed = False
        held, self.held = self.held, []
        return [self.receive(c, None) for c in held]

    def set_windows(self, **w):
        old_lb = self.lower_bound()
        self.cfg["windows"].update(w)
        self._windows_history.append((self.now, self.cfg["windows"]["ts_future_s"]))
        if self.lower_bound() < old_lb:             # widening P never re-admits
            self.floor = max(self.floor or old_lb, old_lb)

    def set_edges(self, edges):
        self.cfg["edges"] = edges

    def recover(self):
        """Restart after a crash (§5.5): every record that is not done is
        finished exactly once, by resuming its RECORDED disposition. An
        undecided reservation is decided now, under the current
        configuration; a decided placement is placed if absent; a decided
        refusal or drop is never published, and its pending control notice
        goes out."""
        out = []
        for key, r in sorted(self.records.items()):
            if r["state"] == "done":
                continue
            if r.get("kind") == "control":
                res = {"id": key[1], "outcome": "control", "notify": r["notify"]}
                r["state"] = "done"
                out.append(res)
                continue
            if r["state"] == "reserved":
                self.decide(r)
            res = self.effect(r, None, recovering=True)
            out.append({"id": key[1], **res})
        return out

    def find_key(self, k):
        for p in self.cfg["peers"]:
            for kk in p["keys"]:
                if kk["key_id"] == k:
                    return p, kk
        return None, None

    def key_valid(self, kk):
        nb, na = kk.get("not_before"), kk.get("not_after")
        return not ((nb and self.now < _ts(nb)) or (na and self.now > _ts(na)))

    def digest_known(self, d):
        return any(r["digest"] == d for r in self.records.values())

    # ---- a candidate -------------------------------------------------------
    def receive(self, cand: dict, crash: str | None = None) -> dict:
        names = [n.lower() for n, _ in cand["fields"]]
        try:
            if CONTROL in names:
                return self.receive_control(cand, crash)
            return self.receive_statement(cand, crash)
        except Outcome as o:
            return o.result

    def _authenticate(self, cand, field_name, schema_name, fail):
        values = [v for n, v in cand["fields"] if n.lower() == field_name]
        other = STATEMENT if field_name == CONTROL else CONTROL
        if not values:
            raise Outcome(fail, "no_statement")
        if len(values) > 1 or any(n.lower() == other for n, _ in cand["fields"]):
            raise Outcome(fail, "header_count")        # markers keep multiplicity
        try:
            k, sb, sig = parse_field(values[0])
        except Outcome as o:
            raise Outcome(fail, o.result["cause"])
        digest = hashlib.sha256(sb).hexdigest()
        if self.digest_known(digest):                # check 2: a retained statement
            raise Outcome("drop", "duplicate")
        peer, kk = self.find_key(k)
        if kk is None:
            raise Outcome(fail, "unknown_key")
        if not self.key_valid(kk):
            raise Outcome(fail, "key_validity")
        if not ed25519_ref.verify(bytes.fromhex(kk["public_key"]), sb, sig):
            raise Outcome(fail, "signature")
        # From here the candidate is signed by a currently valid configured key.
        try:
            st = _strict_json(sb)
        except (ValueError, UnicodeError):
            raise Outcome(fail, "statement_json")
        if self.validate(st, self.schemas[schema_name]):
            raise Outcome(fail, "statement_schema")
        if st["key_id"] != k:
            raise Outcome(fail, "key_id_mismatch")
        return peer, st, digest

    def receive_statement(self, cand, crash):
        peer, st, digest = self._authenticate(cand, STATEMENT, "statement", "mail")

        def fail(outcome, cause, **extra):
            ctl = _control_for(outcome, cause, peer, st, extra.get("policy_code"))
            return Outcome(outcome, cause, control=ctl, **extra)

        # check 5(b): values the schema cannot express
        try:
            ts = _ts(st["ts"])
            if "sender_since" in st and _ts(st["sender_since"]) > ts:
                raise ValueError("sender_since after ts")
            ex = st.get("sender_exposure")
            if ex:
                ws, we = _ts(ex["window_start"]), _ts(ex["window_end"])
                if ws > we:
                    raise ValueError("window order")
                last = ex.get("last_external_delivery_ts")
                if ex["external_mail_delivered"] != (last is not None):
                    raise ValueError("last delivery iff true")
                if last is not None and not ws <= _ts(last) <= we:
                    raise ValueError("last delivery outside window")
        except ValueError:
            raise fail("mail", "statement_value")
        if _dom(st["from"]) not in [d.lower() for d in peer["domains"]]:   # check 6
            raise fail("mail", "key_domain")
        if self.closed:                                                      # check 7, no bound
            self.held.append(cand)
            raise Outcome("held", "admission_closed")
        if not (self.lower_bound() <= ts <= self.now + self.F):              # check 7
            raise fail("mail", "ts_window")
        if ex and _addr(ex["asserted_by"]) != _addr(peer["runtime"]):      # check 8
            raise fail("mail", "exposure_signer")

        # binding: bytes the verifier holds itself (checks 9-11)
        try:
            text = body_text(cand.get("body"))
        except Outcome:
            raise fail("mail", "body_charset")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != st["body_sha256"]:
            raise fail("mail", "body_digest")
        blobs = [base64.b64decode(a["octets_b64"], validate=True) for a in cand["attachments"]]
        if len(blobs) != len(st["attachments"]):
            raise fail("mail", "attachment_count")
        for blob, a in zip(blobs, st["attachments"]):
            if hashlib.sha256(blob).hexdigest() != a["sha256"] or len(blob) != a["size_bytes"]:
                raise fail("mail", "attachment_digest")
        mids = [v for n, v in cand["fields"] if n.lower() == MSGID]
        m = (MSGID_RE.match(re.sub(r"\r\n(?=[ \t])", "", mids[0]).strip(" \t"))
             if len(mids) == 1 and isinstance(mids[0], str) else None)
        if not m or m.group(1) != st["id"] or m.group(2).lower() != _dom(st["from"]):
            raise fail("mail", "message_id")

        # check 12, reservation: the durable record, scoped to (configured runtime, id)
        key = (peer["name"], st["id"])
        if key in self.records:
            raise fail("drop", "duplicate")
        self._mint = getattr(self, "_mint", 0) + 1       # a fresh notice_id per reservation
        rec = {"state": "reserved", "digest": digest, "ts": ts, "notice_id": f"n{self._mint}-{st['id']}",
               "peer": peer, "st": st, "text": text, "decision": None, "control": None}
        self.records[key] = rec
        if crash == "after_reserve":
            return {"outcome": "crashed"}
        self.decide(rec)
        if crash == "after_decide":
            return {"outcome": "crashed"}
        return self.effect(rec, crash)

    def decide(self, rec):
        """Routing, correlation, permission and policy, under the CURRENT
        configuration. The decision is persisted before any effect."""
        st, peer = rec["st"], rec["peer"]

        def terminal(outcome, cause, policy_code=None):
            d = {"outcome": outcome, "cause": cause}
            if policy_code:
                d["policy_code"] = policy_code
            rec["decision"] = d
            rec["control"] = "pending"           # a control notice is owed (§5.8)
            rec["state"] = "decided"

        frm, to = _addr(st["from"]), _addr(st["to"])
        if to not in [_addr(h) for h in self.cfg["hosted"]]:
            return terminal("drop", "misrouted")
        edge = [frm, to] in [[_addr(a), _addr(b)] for a, b in self.cfg["edges"]]
        if "in_reply_to" in st:
            hit = [r for r in self.cfg["ledger"]
                   if r["id"] == st["in_reply_to"] and _addr(r["local"]) == to
                   and _addr(r["remote"]) == frm and self.now <= _ts(r["expires"])]
            if not hit:
                return terminal("refuse", "unresolved_reply")
            if hit[0]["direction"] != "issued" and not edge:
                return terminal("refuse", "no_edge")
        elif not edge:
            return terminal("refuse", "no_edge")
        age = self.cfg.get("min_sender_age_s")      # an OPTIONAL deployment policy (§5.9)
        if age is not None:
            if "sender_since" not in st:
                return terminal("refuse", "policy", "sender_age_unknown")
            since = _ts(st["sender_since"])
            seen = self.since_seen.get((peer["name"], frm))
            if seen is not None and since < seen:   # claims an older enrolment than before
                return terminal("refuse", "policy", "sender_since_inconsistent")
            self.since_seen[(peer["name"], frm)] = since
            if self.now - since < age:
                return terminal("refuse", "policy", "quarantined")
        rec["decision"] = {"outcome": "peer"}
        rec["state"] = "decided"

    def effect(self, rec, crash, recovering=False):
        """Carry out a persisted decision exactly once."""
        d, st = rec["decision"], rec["st"]
        if d["outcome"] == "peer":
            if rec["notice_id"] in self.placed:
                rec["state"] = "done"
                return {"outcome": "already_placed"}
            self.placed.add(rec["notice_id"])
            if crash == "after_place":
                return {"outcome": "crashed"}
            rec["state"] = "done"
            if recovering:
                return {"outcome": "peer"}
            pub = {"id": st["id"], "from": st["from"], "subject": st["subject"],
                   "body_text": rec["text"],
                   "attachments": [{k: a[k] for k in ("filename", "media_type", "size_bytes", "sha256")}
                                   for a in st["attachments"]]}
            for opt in ("in_reply_to", "sender_exposure"):
                if opt in st:
                    pub[opt] = st[opt]
            return {"outcome": "peer", "publish": pub}
        res = dict(d)
        if rec["control"] == "pending":
            res["control"] = _control_for(d["outcome"], d["cause"], rec["peer"], st, d.get("policy_code"))
            rec["control"] = "sent"                 # durably queued, then the record is done
        rec["state"] = "done"
        return res

    def receive_control(self, cand, crash):
        """§5.8: every failure is a drop; nothing is ever placed or mailed.
        The agent's failure notice is owed once the record is reserved, and
        the record is done only when that notice is durable."""
        peer, st, digest = self._authenticate(cand, CONTROL, "control", "drop")
        if _addr(st["from"]) != _addr(peer["runtime"]):
            raise Outcome("drop", "control_signer")
        if _addr(st["to"]) != _addr(self.cfg["self"]["runtime"]):
            raise Outcome("drop", "misrouted")
        try:
            cts = _ts(st["ts"])
        except ValueError:
            raise Outcome("drop", "statement_value")
        if not (self.lower_bound() <= cts <= self.now + self.F):
            raise Outcome("drop", "ts_window")
        key = (peer["name"], st["id"])
        if key in self.records:
            raise Outcome("drop", "duplicate")
        hit = [r for r in self.cfg["ledger"] if r["id"] == st["about"] and r["direction"] == "issued"
               and _dom(r["remote"]) in [d.lower() for d in peer["domains"]]]
        if not hit:
            raise Outcome("drop", "unknown_about")
        if st["about"] in self.reported_about:      # one failure notice per issued message
            raise Outcome("drop", "duplicate_about")
        notify = {"agent": hit[0]["local"], "about": st["about"],
                  "outcome": st["outcome"], "cause": st["cause"]}
        if "policy_code" in st:
            notify["policy_code"] = st["policy_code"]
        self.records[key] = {"state": "reserved", "kind": "control", "digest": digest, "ts": cts,
                             "notice_id": None, "notify": notify}
        self.reported_about.add(st["about"])
        if crash == "after_reserve":
            return {"outcome": "crashed"}
        self.records[key]["state"] = "done"
        return {"outcome": "control", "notify": notify}


# ---- MIME selection rule (§5.2), used only to check mime/ -------------------

_HDR = email.parser.BytesParser(policy=email.policy.compat32)


def _split(raw: bytes):
    """Header block and body, at the first blank line (CRLF or LF)."""
    i, j = raw.find(b"\r\n\r\n"), raw.find(b"\n\n")
    cands = [(i, 4) for i in [i] if i >= 0] + [(j, 2) for j in [j] if j >= 0]
    if not cands:
        return raw, b""
    pos, n = min(cands)
    return raw[:pos], raw[pos + n:]


def _headers(block: bytes):
    return _HDR.parsebytes(block + b"\r\n")


def _transfer_decode(data: bytes, cte: str) -> bytes:
    cte = (cte or "7bit").strip().lower()
    if cte == "base64":
        return binascii.a2b_base64(re.sub(rb"[ \t\r\n]", b"", data))
    if cte == "quoted-printable":
        return quopri.decodestring(data)
    return data                                      # 7bit, 8bit, binary: as transmitted


def _leaves(raw: bytes, out: list):
    hdr_block, body = _split(raw)
    h = _headers(hdr_block)
    if h.get_content_maintype() == "multipart":      # descend into multipart/* only
        b = h.get_param("boundary")
        if b is None:
            out.append((h, body))
            return
        delim = re.escape(b"--" + b.encode("ascii"))
        marks = list(re.finditer(rb"(?:\A|\r?\n)" + delim + rb"(--)?[ \t]*(?:\r?\n|\Z)", body))
        for m, nxt in zip(marks, marks[1:]):
            if m.group(1):                           # close delimiter: epilogue follows
                break
            _leaves(body[m.end():nxt.start()], out)  # part ends before the CRLF of the next delimiter
        return
    out.append((h, body))                            # message/rfc822 is a leaf: its part body


def mime_candidate(raw: bytes) -> dict:
    hdr_block, _ = _split(raw)
    top = _headers(hdr_block)
    leaves: list = []
    _leaves(raw, leaves)
    body, atts = None, []
    for h, octets in leaves:
        disp = (h.get_content_disposition() or "").lower()
        decoded = _transfer_decode(octets, h.get("Content-Transfer-Encoding"))
        if body is None and h.get_content_type() == "text/plain" and disp != "attachment":
            body = (h, decoded)
        else:
            atts.append(decoded)
    fields = []
    wanted = {"message-id": "Message-ID", "amap-peer-statement": "AMAP-Peer-Statement",
              "amap-peer-control": "AMAP-Peer-Control"}
    for raw_name, v in top.items():                  # one pass, in MESSAGE order (§5.2)
        name = wanted.get(raw_name.lower())
        if name is None:
            continue
        # a field body the admitting component cannot carry as ASCII text is
        # an explicit marker, keeping its identity, multiplicity and position (§5.2)
        if not isinstance(v, str) or any(ord(c) > 0x7F for c in v):
            fields.append([name, {"invalid": "non_ascii"}])   # compat32 yields a Header object
        elif len(v.encode("ascii")) > MAX_FIELD_OCTETS:
            fields.append([name, {"oversize": True}])
        else:
            fields.append([name, v])
    return {
        "fields": fields,
        "body": None if body is None else {
            "charset": body[0].get_param("charset"),
            "octets_b64": base64.b64encode(body[1]).decode("ascii")},
        "attachments": [{"octets_b64": base64.b64encode(a).decode("ascii")} for a in atts],
    }


# ---- driver -----------------------------------------------------------------

def patched(cfg: dict, patch: dict | None) -> dict:
    cfg = copy.deepcopy(cfg)
    for k, v in (patch or {}).items():
        if k == "key_validity":
            for p in cfg["peers"]:
                for key in p["keys"]:
                    key.update(v.get(key["key_id"], {}))
        else:
            cfg[k] = v
    return cfg


def run_case(doc, schemas, validate) -> list[str]:
    cfg = json.loads((HERE / doc.get("receiver", "receiver.json")).read_text())
    try:
        rx = Receiver(patched(cfg, doc.get("receiver_patch")), schemas, validate)
    except ConfigError as e:
        if doc.get("config_error") == str(e):
            return []
        return [f"configuration refused ({e}), case expected {doc.get('config_error')!r}"]
    if "config_error" in doc:
        return [f"configuration loaded, case expected refusal {doc['config_error']!r}"]
    errs = []
    for i, step in enumerate(doc["steps"]):
        if "now" in step:
            rx.set_now(step["now"])
        ev = step.get("event")
        if ev is None:
            got = rx.receive(step["candidate"], step.get("crash"))
        elif ev == "recover":
            got = {"recovered": rx.recover()}
        elif ev == "restart":
            got = {}
        elif ev == "lose_store":
            rx.lose_store(step["at"], step.get("h_lost", False), step.get("f_history_lost", False))
            got = {}
        elif ev == "set_bound":
            got = {"released": rx.set_bound(step["bound"])}
        elif ev == "set_windows":
            rx.set_windows(**step["windows"])
            got = {}
        elif ev == "set_edges":
            rx.set_edges(step["edges"])
            got = {}
        elif ev == "set_key":
            for p in rx.cfg["peers"]:
                for kk in p["keys"]:
                    kk.update(step["keys"].get(kk["key_id"], {}))
            got = {}
        elif ev == "remove_key":
            for p in rx.cfg["peers"]:
                p["keys"] = [kk for kk in p["keys"] if kk["key_id"] != step["key_id"]]
            got = {}
        else:
            raise SystemExit(f"unknown event {ev}")
        want = step.get("expect", {})
        if got != want:
            errs.append(f"step {i}: expected {want}, got {got}")
    return errs


def check_vectors() -> list[str]:
    V = json.loads((HERE / "rfc8032-vectors.json").read_text())
    errs = []
    for v in V["vectors"]:
        sk, pk = bytes.fromhex(v["secret_key"]), bytes.fromhex(v["public_key"])
        msg, sig = bytes.fromhex(v["message"]), bytes.fromhex(v["signature"])
        if ed25519_ref.public_key(sk) != pk or ed25519_ref.sign(sk, msg) != sig \
                or not ed25519_ref.verify(pk, msg, sig) or ed25519_ref.verify(pk, msg + b"\0", sig):
            errs.append(f"{v['name']}: ed25519_ref disagrees with RFC 8032")
    for v in V["negative"]:
        pk, msg, sig = (bytes.fromhex(v[x]) for x in ("public_key", "message", "signature"))
        try:
            ed25519_ref.load_public_key(pk)
            loaded = True
        except ValueError:
            loaded = False
        if v["reject_at"] == "config" and loaded:
            errs.append(f"negative {v['name']}: key loaded, policy says refuse it at configuration")
        if v["reject_at"] == "verify" and (not loaded or ed25519_ref.verify(pk, msg, sig)):
            errs.append(f"negative {v['name']}: not rejected by verification")
    return errs


def main(quiet: bool = False) -> int:
    sys.path.insert(0, str(HERE.parent))
    from validate import validate  # the gate's own schema subset

    sdir = HERE.parent.parent / "schemas"
    schemas = {"statement": json.loads((sdir / "peer-statement.schema.json").read_text()),
               "control": json.loads((sdir / "peer-control.schema.json").read_text())}
    failures = check_vectors()
    vec_ok = not failures
    mimes = sorted((HERE / "mime").glob("*.json"))
    for f in mimes:
        doc = json.loads(f.read_text())
        got = mime_candidate((HERE / "mime" / doc["eml"]).read_bytes())
        if got != doc["candidate"]:
            failures.append(f"mime/{f.name}: candidate differs: {got}")
        elif not quiet:
            print(f"  ok   peer-signed/mime/{f.name}")
    cases = sorted((HERE / "cases").glob("*.json"))
    for f in cases:
        errs = run_case(json.loads(f.read_text()), schemas, validate)
        failures += [f"{f.name}: {e}" for e in errs]
        if not quiet:
            print(f"  {'ok ' if not errs else 'BAD'}  peer-signed/cases/{f.name}")
    print(f"\n{len(cases)} signed peer cases and {len(mimes)} MIME cases checked, RFC 8032 "
          f"vectors {'ok' if vec_ok else 'FAILED'}, {len(failures)} unexpected.")
    for x in failures:
        print("  FAIL:", x)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
