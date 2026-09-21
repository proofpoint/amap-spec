#!/usr/bin/env python3
"""check_prose.py — normative coverage gate for the Internet-Draft.

The problem this exists for: the draft's normative sections are a RENDERING
of spec/contract.md and spec/peer-origin.md, not a copy. Sentences are
legitimately reordered, reworded, and re-cast into IETF house style. So an
equality check is impossible and a byte diff is meaningless — but without
SOME gate, a normative obligation can vanish from the draft while every
other check stays green. That is not hypothetical: a reconstruction of
sections 7.1/7.2 once dropped 69 sentences (including a MUST NOT and an
anti-traversal obligation) while the build, check_render.py, byte-identical
reproducibility and the fixture gate all passed. Nothing mechanical noticed.

So this is a COVERAGE check, not an equality check:

  for every RFC 2119 sentence in spec/, require a sentence in the draft
  that carries the same keyword and substantially the same content words.

A miss is either a real omission or a deliberate one. Deliberate omissions
go in draft/prose-exceptions.toml with a reason, so every gap is a reviewed
decision rather than an accident. That file is the point of the design: it
converts "we think the draft covers the spec" into an explicit, diffable
list of everything it knowingly does not.

What this CANNOT do, stated plainly so nobody over-trusts it:
  - It matches content words, not meaning. A sentence reworded to say the
    opposite while keeping its vocabulary would still match.
  - It is one-directional. Text in the draft with no spec counterpart is
    NOT reported here (the draft legitimately adds apparatus: Introduction,
    Terminology, Security Considerations, IANA). Invented normative text is
    a human review question.
  - It only sees RFC 2119 sentences. Normative content phrased without a
    keyword is invisible to it.
  - Sensitivity falls off for SHORT sentences built from common protocol
    vocabulary. Coverage is |shared| / |spec sentence|, so a four-word
    draft-only obligation sharing two words with any unrelated spec sentence
    clears the threshold and passes. Measured: an invented
    "A Connector MUST verify the lozenge before rotation" is NOT caught,
    while a longer or more distinctive one is. The reverse direction is
    therefore a net, not a sieve — it reliably catches a substantive edit,
    and can miss a terse one.
It catches deletion and drift, which is what actually happened. Treat it as
a floor, not a proof.

Usage:  python3 draft/check_prose.py [--verbose] [--threshold 0.55]
Exit 0 if every spec obligation is covered or explicitly excepted.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SPEC_FILES = ("spec/contract.md", "spec/peer-origin.md")
DRAFT_FILE = "draft/draft-amap.mkd"
EXCEPTIONS_FILE = "draft/prose-exceptions.toml"
BASELINE_FILE = "draft/draft-only-baseline.toml"

# Draft sections that are a rendering of spec/. A normative sentence here with
# no spec counterpart is either Trent's edit (promote it to spec/) or drift.
# Everything else — Introduction, Terminology, Security Considerations, IANA,
# the appendices — is IETF apparatus the draft owns outright, and is not
# checked in the reverse direction.
SPEC_RENDERING_SECTIONS = frozenset(
    [f"sec-{i}" for i in range(3, 11)] + ["sec-directory"]
)

# Longest-first so "MUST NOT" wins over "MUST".
KEYWORDS = (
    "MUST NOT", "SHALL NOT", "SHOULD NOT", "NOT RECOMMENDED",
    "MUST", "SHALL", "SHOULD", "RECOMMENDED", "REQUIRED", "OPTIONAL", "MAY",
)
KEYWORD_RE = re.compile("|".join(re.escape(k) for k in KEYWORDS))

STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from by
with within without into onto over under is are was were be been being it its
as so such which what when where who whom whose any all each every both either
neither no not nor only own same too very can will just do does did done has have
had having here there other another more most less least own see also per via than
one two three second first single same other well rather instead because since
while whether though although however therefore thus hence about against between
across after before during until upon out up down off again further once
""".split())

# Tokens that are pure navigation or markup noise: dropping them stops a
# section renumbering from looking like a content change.
NOISE_RE = re.compile(
    r"^(?:section|sections|appendix|appendices|rfc|v\d[\w.]*|\d+(?:\.\d+)*|"
    r"[ivxlc]+|fig|figure|table|xref)$"
)


def strip_fences(text: str) -> str:
    """Blank out fenced code blocks; their contents are data, not prose.

    Blanked, not deleted. Deleting them shifts every subsequent line number,
    so a reported location no longer names a line in the file the reader will
    open — and worse, the reverse check maps an obligation to a section using
    marks taken from the UNSTRIPPED text, so the two disagree and obligations
    are attributed to whatever section happens to sit at the shifted offset.
    That was silently true until a new section landed far enough down the
    document for the drift to become visible.
    """
    out, in_fence = [], False
    for line in text.splitlines():
        if re.match(r"^\s*(?:```|~~~)", line):
            in_fence = not in_fence
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def strip_markup(text: str) -> str:
    text = re.sub(r"\{::[^}]*\}", " ", text)            # kramdown include directives
    text = re.sub(r"\{:[^}]*\}", " ", text)             # kramdown attribute lists
    text = re.sub(r"\{\{<?([^}]*)\}\}", r" \1 ", text)  # {{RFCnnnn}} xrefs
    text = re.sub(r"\[\]\(#[^)]*\)", " ", text)         # [](#anchor) auto-xrefs
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r" \1 ", text)
    text = re.sub(r"[`*_>|#]", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def sentences(text: str) -> list[tuple[int, str]]:
    """Split into (line_number, sentence). Paragraph-aware so wrapped lines rejoin."""
    lines = text.splitlines()
    result: list[tuple[int, str]] = []
    para: list[str] = []
    start = 1
    def flush() -> None:
        if not para:
            return
        joined = " ".join(para)
        # The lookahead must admit a sentence that opens with markup — `code`,
        # **bold**, _em_ — or long bullets never split and produce 50-token
        # signatures that cannot match anything.
        parts = re.split(
            r"(?<!e\.g)(?<!i\.e)(?<!cf)(?<!etc)(?<!\bNo)(?<![A-Z])\.\s+(?=[A-Z\"'(\[`*_])",
            joined,
        )
        for p in parts:
            p = p.strip()
            if p:
                result.append((start, p))
    # A new list item, heading, or table row starts a new unit. Without this,
    # consecutive bullets in spec/ merge into one pseudo-sentence that cannot
    # match anything in the draft, which reads as a false miss.
    boundary = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|#{1,6}\s|\|)")
    for i, line in enumerate(lines, 1):
        if not line.strip():
            flush()
            para, start = [], i + 1
        else:
            if boundary.match(line):
                flush()
                para, start = [], i
            if not para:
                start = i
            para.append(line.strip())
    flush()
    return result


def keyword_of(sentence: str) -> str | None:
    m = KEYWORD_RE.search(sentence)
    return m.group(0) if m else None


def signature(sentence: str) -> frozenset[str]:
    """Content-word signature: lowercase, markup-free, stopword-free, noise-free."""
    text = strip_markup(sentence).lower()
    text = re.sub(r"[^a-z0-9_./-]+", " ", text)
    tokens = set()
    for tok in text.split():
        tok = tok.strip("-./_")
        if not tok or tok in STOPWORDS or NOISE_RE.match(tok):
            continue
        if len(tok) < 3 and not tok.isdigit():
            continue
        tokens.add(tok)
    return frozenset(tokens)


def obligation_id(keyword: str, sig: frozenset[str]) -> str:
    """Stable id: survives reflow and renumbering, changes if wording changes.

    That instability is deliberate — a reworded obligation should fall out of
    the allowlist and be re-reviewed rather than stay silently excepted.
    """
    payload = keyword + "|" + " ".join(sorted(sig))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def coverage(spec_sig: frozenset[str], draft_sig: frozenset[str]) -> float:
    """How much of the SPEC sentence's vocabulary appears in the draft one.

    Deliberately asymmetric. Jaccard punishes the normal case: the draft
    routinely expands one spec sentence into a longer one with added IETF
    framing, which shrinks the union and drags a genuine match below any
    usable threshold. What we care about is whether the obligation's content
    survived, not whether the two sentences are the same size.
    """
    if not spec_sig:
        return 0.0
    return len(spec_sig & draft_sig) / len(spec_sig)


def section_index(text: str) -> list[tuple[int, str]]:
    """(line, anchor) for every top-level heading carrying a {#anchor}."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^# .*\{#((?:sec|app)-[\w-]+)\}", line)
        if m:
            out.append((i, m.group(1)))
    return out


def section_of(marks: list[tuple[int, str]], line: int) -> str:
    cur = "front"
    for ln, anchor in marks:
        if ln <= line:
            cur = anchor
        else:
            break
    return cur


def collect(path: Path) -> list[dict]:
    text = strip_fences(path.read_text(encoding="utf-8"))
    out = []
    for line, sent in sentences(text):
        kw = keyword_of(sent)
        if not kw:
            continue
        sig = signature(sent)
        if len(sig) < 3:  # too thin to match on; not a real obligation
            continue
        out.append({"line": line, "text": sent, "keyword": kw, "sig": sig})
    return out


def load_scope() -> dict[str, str]:
    """Spec files the draft deliberately does not carry at all.

    A whole-file decision is one reviewed line, not N allowlist entries. The
    peer-origin profile is the live case: the draft carries its schema as an
    appendix but none of its prose, because the profile is still DRAFT.
    """
    path = REPO / EXCEPTIONS_FILE
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = {}
    for entry in data.get("scope", []):
        name, reason = entry.get("spec"), entry.get("reason", "")
        if not name or not reason.strip():
            raise SystemExit(
                f"check_prose: {EXCEPTIONS_FILE}: every [[scope]] needs a "
                f"non-empty 'reason' (offending spec: {name!r})."
            )
        out[name] = reason
    return out


def load_baseline() -> dict[str, str]:
    """Draft-only obligations recorded when the reverse check was introduced."""
    path = REPO / BASELINE_FILE
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {e["id"]: e.get("text", "") for e in data.get("draft_only", []) if e.get("id")}


def load_exceptions() -> dict[str, str]:
    path = REPO / EXCEPTIONS_FILE
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    out = {}
    for entry in data.get("exception", []):
        oid, reason = entry.get("id"), entry.get("reason", "")
        if not oid or not reason.strip():
            raise SystemExit(
                f"check_prose: {EXCEPTIONS_FILE}: every exception needs a non-empty "
                f"'reason' (offending id: {oid!r}). An unexplained exception is an "
                f"accident with a rubber stamp."
            )
        out[oid] = reason
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # 0.40: with two-sentence windowing, faithful renderings cluster at or above
    # this. The draft legitimately drops repo-internal rationale (fixture names,
    # validator function names) that inflates a spec sentence's vocabulary, so a
    # stricter bar flags correct text. Anything below it was a real gap or real
    # noise on every case inspected when this was tuned.
    ap.add_argument("--threshold", type=float, default=0.40)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-reverse", action="store_true",
                    help="skip the draft->spec direction (Trent-edit detection)")
    ap.add_argument("--emit-baseline", action="store_true",
                    help="print TOML for every current draft-only obligation")
    ap.add_argument("--emit-exceptions", action="store_true",
                    help="print TOML stubs for every current miss, to seed the allowlist")
    args = ap.parse_args(argv)

    draft = collect(REPO / DRAFT_FILE)
    # Candidates are single draft sentences PLUS every adjacent pair. The draft
    # routinely splits one dense spec sentence into two shorter ones, which
    # halves the coverage score of a perfectly faithful rendering; a two-sentence
    # window restores it without loosening the threshold for anything else.
    candidates: list[dict] = list(draft)
    for a, b in zip(draft, draft[1:]):
        candidates.append({
            "keyword": a["keyword"],
            "sig": a["sig"] | b["sig"],
            "text": a["text"][:120] + " … " + b["text"][:120],
        })
        if b["keyword"] != a["keyword"]:
            candidates.append({
                "keyword": b["keyword"],
                "sig": a["sig"] | b["sig"],
                "text": a["text"][:120] + " … " + b["text"][:120],
            })
    by_keyword: dict[str, list[dict]] = {}
    for d in candidates:
        by_keyword.setdefault(d["keyword"], []).append(d)

    exceptions = load_exceptions()
    scope = load_scope()
    misses, used_exceptions, total, skipped = [], set(), 0, {}

    for spec_file in SPEC_FILES:
        if spec_file in scope:
            skipped[spec_file] = len(collect(REPO / spec_file))
            continue
        for ob in collect(REPO / spec_file):
            total += 1
            best, score = None, 0.0
            for cand in by_keyword.get(ob["keyword"], ()):
                s = coverage(ob["sig"], cand["sig"])
                if s > score:
                    best, score = cand, s
            if score >= args.threshold:
                if args.verbose:
                    print(f"  ok  {score:.2f}  {spec_file}:{ob['line']}  {ob['text'][:70]}")
                continue
            oid = obligation_id(ob["keyword"], ob["sig"])
            if oid in exceptions:
                used_exceptions.add(oid)
                if args.verbose:
                    print(f"  excepted  {oid}  {spec_file}:{ob['line']}  — {exceptions[oid]}")
                continue
            misses.append({
                "id": oid, "file": spec_file, "line": ob["line"],
                "keyword": ob["keyword"], "text": ob["text"],
                "best": score, "near": best["text"] if best else None,
            })

    # ---- reverse direction: draft obligations with no spec counterpart ----
    draft_text = (REPO / DRAFT_FILE).read_text(encoding="utf-8")
    marks = section_index(draft_text)
    spec_by_keyword: dict[str, list[dict]] = {}
    for spec_file in SPEC_FILES:
        if spec_file in scope:
            continue
        for ob in collect(REPO / spec_file):
            spec_by_keyword.setdefault(ob["keyword"], []).append(ob)

    baseline = load_baseline()
    draft_only, used_baseline = [], set()
    if not args.no_reverse:
        for d in draft:
            if section_of(marks, d["line"]) not in SPEC_RENDERING_SECTIONS:
                continue
            best = max(
                (coverage(d["sig"], x["sig"]) for x in spec_by_keyword.get(d["keyword"], ())),
                default=0.0,
            )
            if best >= args.threshold:
                continue
            oid = obligation_id(d["keyword"], d["sig"])
            if oid in baseline:
                used_baseline.add(oid)
                continue
            draft_only.append({"id": oid, "line": d["line"], "keyword": d["keyword"],
                               "text": d["text"], "section": section_of(marks, d["line"])})

    if args.emit_baseline:
        print("# Generated by check_prose.py --emit-baseline. See the header in")
        print(f"# {BASELINE_FILE} before editing by hand.\n")
        for m in draft_only:
            print("[[draft_only]]")
            print(f'id = "{m["id"]}"')
            print(f'# {m["section"]}, line {m["line"]}  ({m["keyword"]})')
            esc = m["text"][:240].replace("\\", "\\\\").replace('"', '\\"')
            print(f'text = "{esc}"\n')
        return 0

    stale = set(exceptions) - used_exceptions

    if args.emit_exceptions:
        for m in misses:
            print(f'[[exception]]\nid = "{m["id"]}"')
            print(f'# {m["file"]}:{m["line"]}  {m["keyword"]}')
            print(f'# {m["text"][:300]}')
            print('reason = "TODO — why the draft deliberately omits this"\n')
        return 0

    print(f"check_prose: {total} normative sentences in scope, "
          f"{len(draft)} in the draft, threshold {args.threshold}")
    for name, n in sorted(skipped.items()):
        print(f"  out of scope: {name} ({n} obligations) — {scope[name]}")

    for m in misses:
        print(f"\nFAIL: uncovered obligation  [{m['id']}]")
        print(f"  {m['file']}:{m['line']}  ({m['keyword']})")
        print(f"  {m['text'][:300]}")
        if m["near"]:
            print(f"  closest draft sentence ({m['best']:.2f}): {m['near'][:200]}")
        else:
            print(f"  no draft sentence carries {m['keyword']} at all")

    for oid in sorted(stale):
        print(f"\nFAIL: stale exception [{oid}] — {exceptions[oid]}")
        print("  Nothing in spec/ matches it any more. The obligation was reworded "
              "or removed; re-review and update or delete this entry.")

    for m in draft_only:
        print(f"\nFAIL: draft-only obligation  [{m['id']}]")
        print(f"  draft-amap.mkd:{m['line']}  ({m['section']}, {m['keyword']})")
        print(f"  {m['text'][:300]}")
        print("  No counterpart in spec/. If this is a deliberate edit to the")
        print("  draft, it is now canonical and MUST be promoted into spec/ —")
        print("  see WORKFLOWS.md, 'Draft-first'. Do not silently baseline it.")

    if misses or stale or draft_only:
        print(f"\ncheck_prose: FAILED — {len(misses)} uncovered, "
              f"{len(draft_only)} draft-only, {len(stale)} stale.")
        print("Either carry the obligation into the draft, or add it to "
              f"{EXCEPTIONS_FILE} with a reason "
              "(`--emit-exceptions` prints stubs).")
        return 1

    rev = "skipped" if args.no_reverse else f"{len(baseline)} baselined"
    print(f"check_prose: OK — spec->draft covered or excepted "
          f"({len(exceptions)} exception(s)); draft->spec {rev}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
