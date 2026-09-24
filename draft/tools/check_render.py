#!/usr/bin/env python3
"""check_render.py — post-build gate for the rendered Internet-Draft XML.

Proves that what actually lands in the draft XML (draft/draft-amap.xml, the
canonical source, and its copy dist/draft-amap-00.xml) still equals a
real file on disk, byte for byte (modulo RFC 8792 folding and a trailing
newline). Run after every build; `make -C draft check` wires it in.

Checks:
  1. Every <sourcecode type="json"> whose enclosing figure's anchor ends in
     "-src" is RFC-8792-unfolded and compared against the fixtures/ or
     schemas/ file its own anchor names (the fence directive baked the path
     into the caption: v3 <name>, or title= in the legacy v2 rendering). A figure anchored "ex-*" is a hand-written
     illustrative shape (not a fixture) and is exempted from the disk
     comparison, but its JSON must still parse.
  2. The Conformance Suite appendix (#app-h) roster sentence ("N fixtures — V valid and I invalid")
     matches the on-disk fixture counts.
  3. rfc/@docName is the pinned, unrenamed draft name (D9).
  4. No host path or the operator's personal email appears anywhere in the
     rendered XML.
  5. No SYSTEM "http entity exists (stand_alone held; nothing fetched at
     render time).
  6. No BROKEN REFERENCE placeholder exists. The old kramdown-rfc build
     silently substituted one for a missing bib/ file; the canonical XML
     inherited its references from that build, so the check stays as a guard
     against a placeholder surviving into, or being pasted back into, the
     hand-edited source.
  7. Every illustrative JSON shape in draft/examples/ (the "ex-*" figures
     exempted from check 1's disk comparison) still validates against its
     schema. The schema and the applicable named post-check are picked from
     an explicit map below, never inferred from the example's own filename —
     none of "deliver-notice.json", "inbound-message.json", "result.json",
     or "submit-request.json" carries the `notice-`/`message-`/`result-`
     prefix fixtures/validate.py's own dispatch keys on, and CLAUDE.md is
     explicit that picking a schema by filename for a real artifact is the
     wrong move.

Stdlib only.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# Generic personal-mail domain, deliberately not a specific address: a guard
# that contains the literal identifier it guards against is itself the leak,
# and it breaks under the very history rewrite that scrubs that identifier.
FORBIDDEN_SUBSTRINGS = ("/home/", "Users/", "@gmail.com")


def unfold(text: str) -> str:
    """Reverse kramdown-rfc's include-fold69hardleft4dry (RFC 8792 folding).
    xml2rfc's <sourcecode> CDATA always opens with a leading blank line.
    Folded output additionally starts with an informational NOTE line and a
    further blank line; continuation lines are then joined by deleting a
    backslash-newline plus the following run of leading whitespace."""
    lines = text.split("\n")
    idx = 0
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    if idx < len(lines) and lines[idx].lstrip().startswith("NOTE:"):
        idx += 1
        while idx < len(lines) and lines[idx].strip() == "":
            idx += 1
    text = "\n".join(lines[idx:])
    return re.sub(r"\\\n[ \t]*", "", text)


def check_sourcecode_blocks(root: ET.Element) -> list[str]:
    errors = []
    ns_strip = lambda tag: tag.split("}")[-1]
    for figure in root.iter():
        if ns_strip(figure.tag) != "figure":
            continue
        anchor = figure.get("anchor", "")
        sourcecodes = [c for c in figure.iter() if ns_strip(c.tag) == "sourcecode"]
        for sc in sourcecodes:
            if sc.get("type") != "json":
                continue
            raw = sc.text or ""
            unfolded = unfold(raw)
            try:
                json.loads(unfolded)
            except json.JSONDecodeError as e:
                errors.append(f"{anchor}: unfolded content is not valid JSON: {e}")
                continue
            if anchor.startswith("ex-"):
                continue  # illustrative, hand-written shape; not a fixture
            # The source path is the figure's caption: v3 carries it in a
            # <name> child, the legacy v2 rendering in a title= attribute.
            title = None
            for e in [figure] + list(figure.iter()):
                if ns_strip(e.tag) == "name" and (e.text or "").strip():
                    title = e.text.strip()
                    break
                if e.get("title"):
                    title = e.get("title")
                    break
            src_path = title or _guess_path_from_anchor(anchor)
            if src_path is None:
                errors.append(f"{anchor}: no caption naming a source file, and anchor "
                               f"doesn't start with 'ex-' to exempt it")
                continue
            disk_path = REPO / src_path
            if not disk_path.exists():
                errors.append(f"{anchor}: source file not found on disk: {src_path}")
                continue
            disk_text = disk_path.read_text(encoding="utf-8").strip("\n")
            if unfolded.strip("\n") != disk_text:
                errors.append(f"{anchor}: rendered JSON does not match {src_path}")
    return errors


def _guess_path_from_anchor(anchor: str) -> str | None:
    return None


def check_roster(xml_text: str) -> list[str]:
    errors = []
    # \D* (never a digit) between the counts, so it can't backtrack into an
    # adjacent number the way a bounded `.{0,3}` did (that ate one digit of
    # "27" here, off the em dash + digit ambiguity — caught by this fix).
    m = re.search(r"(\d+)\s+fixtures\D*(\d+)\s+valid and (\d+)\s+invalid", xml_text)
    if not m:
        errors.append("Conformance Suite appendix (#app-h) roster sentence not found in rendered XML")
        return errors
    total, valid, invalid = (int(x) for x in m.groups())
    disk_valid = len(list((REPO / "fixtures" / "valid").glob("*.json")))
    disk_invalid = len(list((REPO / "fixtures" / "invalid").glob("*.json")))
    if (total, valid, invalid) != (disk_valid + disk_invalid, disk_valid, disk_invalid):
        errors.append(
            f"roster sentence says {total}/{valid}/{invalid}, disk has "
            f"{disk_valid + disk_invalid}/{disk_valid}/{disk_invalid}"
        )
    return errors


def check_docname(root: ET.Element) -> list[str]:
    docname = root.get("docName", "")
    if docname != "draft-amap-00":
        return [f"rfc/@docName is {docname!r}, expected 'draft-amap-00'"]
    return []


def check_no_identifiers(xml_text: str) -> list[str]:
    errors = []
    for needle in FORBIDDEN_SUBSTRINGS:
        if needle in xml_text:
            errors.append(f"forbidden substring {needle!r} found in rendered XML")
    return errors


def check_no_system_entities(xml_text: str) -> list[str]:
    if 'SYSTEM "http' in xml_text:
        return ['SYSTEM "http entity found — stand_alone rendering should embed <reference> elements, never entities pointing at a network fetch']
    return []


EXAMPLES_DIR = REPO / "draft" / "examples"

# filename -> (schema filename, post-check kind). The post-check kind is our
# own explicit classification of what the document IS, not a string sniffed
# off its name; see the module docstring's check 7.
EXAMPLE_SCHEMAS = {
    "deliver-notice.json": ("deliver-notice.schema.json", "notice"),
    "inbound-message.json": ("inbound-message.schema.json", "message"),
    "result.json": ("result.schema.json", "result"),
    "submit-request.json": ("submit-request.schema.json", "request"),
    "directory.json": ("directory.schema.json", "directory"),
}


def check_examples() -> list[str]:
    if not EXAMPLES_DIR.is_dir():
        return []
    sys.path.insert(0, str(REPO / "fixtures"))
    import validate as validate_mod  # type: ignore

    errors = []
    seen = set()
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        seen.add(path.name)
        mapping = EXAMPLE_SCHEMAS.get(path.name)
        if mapping is None:
            errors.append(f"draft/examples/{path.name}: no entry in check_render.py's "
                           f"EXAMPLE_SCHEMAS map — add one rather than guessing a schema")
            continue
        schema_fn, kind = mapping
        doc = json.loads(path.read_text(encoding="utf-8"))
        schema = json.loads((validate_mod.SCHEMA_DIR / schema_fn).read_text())
        errs = validate_mod.validate(doc, schema)
        if kind == "result":
            errs += validate_mod._check_result_attachment_index_binding(doc)
        if kind in ("notice", "message"):
            errs += validate_mod._check_content_ref_index_binding(doc)
        for e in errs:
            errors.append(f"draft/examples/{path.name}: {e}")
    missing = set(EXAMPLE_SCHEMAS) - seen
    for name in sorted(missing):
        errors.append(f"EXAMPLE_SCHEMAS names draft/examples/{name} but the file is gone — "
                       f"stale map entry")
    return errors


def check_no_broken_references(xml_text: str) -> list[str]:
    """The former kramdown-rfc build silently substituted a placeholder <reference> whose
    title is this literal string when a bib/reference.*.xml file it needs is
    missing at build time (offline mode never fetches it instead). That
    placeholder is schema-valid XML and renders as a normal-looking, if
    useless, bibliography entry — the build's exit code stays 0 and this was
    the one class of breakage the mechanical checks below cannot see."""
    if "BROKEN REFERENCE" in xml_text:
        return ["a BROKEN REFERENCE placeholder is present in the draft XML; replace "
                "it with the real <reference> (draft/bib/ holds the RFC entries)"]
    return []


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} dist/draft-amap-00.xml", file=sys.stderr)
        return 2
    xml_path = Path(argv[1])
    xml_text = xml_path.read_text(encoding="utf-8")
    root = ET.fromstring(xml_text)

    errors: list[str] = []
    errors += check_sourcecode_blocks(root)
    errors += check_roster(xml_text)
    errors += check_docname(root)
    errors += check_no_identifiers(xml_text)
    errors += check_no_system_entities(xml_text)
    errors += check_no_broken_references(xml_text)
    errors += check_examples()

    n_checked = sum(
        1 for f in root.iter()
        if f.tag.split("}")[-1] == "figure"
        for c in f.iter() if c.tag.split("}")[-1] == "sourcecode" and c.get("type") == "json"
    )
    print(f"check_render: {n_checked} JSON sourcecode blocks inspected")

    if errors:
        print(f"check_render: {len(errors)} problem(s):")
        for e in errors:
            print(f"  FAIL: {e}")
        return 1

    print("check_render: OK — every fixture/schema JSON block matches disk; "
          "roster counts match; docName pinned; no host paths or personal "
          "identifiers; no network-fetch entities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
