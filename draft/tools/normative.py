"""normative.py — extract the normative sentences from the draft XML.

Shared by check_coverage.py (which requires every normative sentence to be
classified) and normdiff.py (which reports normative sentences added, removed
or changed between two versions of the draft).

A normative sentence is one carrying an RFC 2119 / RFC 8174 keyword in
capitals. The Conventions boilerplate that *quotes* the keywords is excluded.
Text inside <sourcecode>, <artwork> and <figure> is never read, and a sentence
is attributed to the innermost <section> whose anchor contains it.

Works on the canonical v3 source and on the legacy v2 rendering in dist/, so a
normative diff can span the switch between the two. Stdlib only.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

KEYWORDS = re.compile(
    r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|NOT RECOMMENDED|"
    r"RECOMMENDED|REQUIRED|MAY|OPTIONAL)\b")
BOILERPLATE = re.compile(r'"MUST"|"REQUIRED"|BCP ?14')
SKIP = {"sourcecode", "artwork", "figure", "name", "references", "reference"}
BLOCK = {"t", "li", "dd", "dt", "td", "th", "c", "blockquote", "aside"}  # c: v2 table cell
SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z*\"`(\[])")


def _tag(e: ET.Element) -> str:
    return e.tag.split("}")[-1]


def _text(e: ET.Element) -> str:
    """All text under e, skipping code and figures, whitespace collapsed."""
    out = []

    def walk(n):
        if _tag(n) in SKIP:
            if n.tail:
                out.append(n.tail)
            return
        if n.text:
            out.append(n.text)
        for c in n:
            walk(c)
            # tails are appended by the child walk only for skipped nodes
            if _tag(c) not in SKIP and c.tail:
                out.append(c.tail)

    walk(e)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def sentence_id(sentence: str) -> str:
    norm = re.sub(r"\s+", " ", sentence).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def extract(xml_text: str) -> list[tuple[str, str]]:
    """[(section_anchor, sentence)] in document order, normative only."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    found: list[tuple[str, str]] = []

    def visit(node, section):
        tag = _tag(node)
        if tag in SKIP:
            return
        if tag == "section":
            section = node.get("anchor", section)
        if tag in BLOCK:
            # a block may nest others (li > t); read only the innermost
            if not any(_tag(c) in BLOCK for c in node.iter() if c is not node):
                for s in SPLIT.split(_text(node)):
                    s = s.strip()
                    if KEYWORDS.search(s) and not BOILERPLATE.search(s):
                        found.append((section, s))
                return
        for c in node:
            visit(c, section)

    middle = [e for e in root.iter() if _tag(e) in ("middle", "back")]
    for part in middle:
        visit(part, "")
    return found


def in_coverage_scope(anchor: str) -> bool:
    """The sections that render the protocol: 3-10, the peer directory and the
    fleet roster.
    Introduction, Terminology, Security Considerations, IANA and the
    appendices are the draft's own apparatus and are not held to fixtures."""
    m = re.match(r"sec-(\d+)", anchor)
    if m:
        return 3 <= int(m.group(1)) <= 10
    return anchor in ("sec-directory", "sec-roster")
