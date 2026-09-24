#!/usr/bin/env python3
"""sync_sources.py — keep the JSON blocks in the hand-edited Internet-Draft
(draft/draft-amap.xml, the canonical source) byte-identical to the files on disk.

Why this exists: once the draft XML is the canonical, hand-edited source, the
JSON it shows (schemas, fixtures, illustrative examples) must still come from
schemas/, fixtures/ and draft/examples/, never be hand-copied. xml2rfc's own
<sourcecode src=...> can't do this. xml2rfc 3.34.1 crashes on any non-ASCII
UTF-8 in a src file, and it does no RFC 8792 folding, while our schemas carry
"§" and "—" and lines up to 326 characters. So this script folds each file
exactly as kramdown-rfc's include-fold69hardleft4dry does, and rewrites only
the CDATA body of the matching <sourcecode>, textually, leaving every other
byte of the hand-edited XML untouched.

    sync_sources.py [XML]            check: list blocks that differ from disk (exit 1 if any)
    sync_sources.py [XML] --write    rewrite the differing blocks in place

XML defaults to draft/draft-amap.xml. `make -C draft sync` runs --write;
`make -C draft check` runs the check. A json block whose anchor maps to no file
fails the check, and so does a file (schema or fixture) with no block in the
draft: a missing block is exactly the omission a comparison cannot see.

Stdlib only.
"""
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

FOLD_MSG = "NOTE: '\\' line wrapping per RFC 8792"
RE_IDENT = re.compile(r"\A[A-Za-z0-9_]\Z")


def fold8792_1(s, columns=69, left_indent=4, dry=True, hard=True):
    """Port of kramdown-rfc 1.7.43 rfc8792.rb fold8792_1, specialised to
    fold69hardleft4dry (indent_type=:left, spaces=4, dry, hard). Indexing is
    by character, as in Ruby."""
    if "\t" in s:
        raise ValueError("HT in text to be folded")
    lines = [l.rstrip("\r\n") for l in s.splitlines(keepends=True)]
    did_fold = False
    ix = 0
    while ix < len(lines):
        li = lines[ix]
        col = columns
        if len(li) <= col:                    # li[col].nil?
            if li.endswith("\\"):
                lines[ix:ix + 1] = [li + "\\", ""]
                ix += 1
            ix += 1
            continue
        did_fold = True
        min_indent = left_indent
        col -= 1                              # space for "\"
        while col < len(li) and li[col] == " ":
            col -= 1
        if col <= min_indent:
            raise ValueError(f"cannot fold to {columns} cols: {li!r}")
        if not hard and RE_IDENT.match(li[col]):
            pass  # hard mode: identifiers may be split (unused here)
        rest = li[col:]
        indent = left_indent
        if indent > 0:
            rest = " " * indent + rest
        lines[ix:ix + 1] = [li[:col] + "\\", rest]
        ix += 1
    if not did_fold:
        return s
    msg = FOLD_MSG  # dry: no "====" decoration
    lines[0:0] = [msg, ""]
    return "".join(x + "\n" for x in lines)


def trim_empty_lines_around(s):
    return re.sub(r"(\r?\n)*\Z", "", re.sub(r"\A(\r?\n)*", "", s))


def fix_unterminated_line(s):
    return s if s.endswith("\n") or s == "" else s + "\n"


def render_block(path: Path) -> str:
    """What kramdown-rfc puts inside <![CDATA[ ... ]]> for an included file."""
    s = path.read_text(encoding="utf-8")
    return "\n" + fix_unterminated_line(fold8792_1(trim_empty_lines_around(s)))


def source_map(repo: Path) -> dict:
    """anchor -> file on disk. Schemas by name, fixtures from fixtures.toml,
    illustrative examples from draft/examples/."""
    m = {}
    for f in sorted((repo / "schemas").glob("*.schema.json")):
        m["schema-" + f.name[: -len(".schema.json")]] = f
    toml = tomllib.loads((repo / "draft" / "fixtures.toml").read_text())
    for fx in toml.get("fixture", []):
        m[fx["anchor"] + "-src"] = repo / "fixtures" / fx["file"]
    for f in sorted((repo / "draft" / "examples").glob("*.json")):
        m["ex-" + f.stem] = f
    return m


BLOCK = re.compile(
    r'(<figure\b[^>]*\banchor="(?P<anchor>[^"]+)"[^>]*>(?:(?!</figure>).)*?'
    r'<sourcecode\b[^>]*\btype="json"[^>]*><!\[CDATA\[)(?P<body>.*?)(\]\]></sourcecode>)',
    re.S)


def main():
    global REPO
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    xml_path = Path(args[0]) if args else REPO / "draft" / "draft-amap.xml"
    write = "--write" in sys.argv
    REPO = Path(next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--repo=")), REPO))
    srcmap = source_map(REPO)
    text = xml_path.read_text(encoding="utf-8")
    seen, diffs, unknown = set(), [], []

    def fix(m):
        anchor = m.group("anchor")
        path = srcmap.get(anchor)
        if path is None:
            unknown.append(anchor)
            return m.group(0)
        seen.add(anchor)
        want = render_block(path)
        if m.group("body") != want:
            diffs.append(anchor)
            return m.group(1) + want + m.group(4)
        return m.group(0)

    new = BLOCK.sub(fix, text)
    missing = sorted(set(a for a in srcmap if not a.startswith("ex-")) - seen)
    for a in unknown:
        print(f"UNMAPPED json block: {a}")
    for a in diffs:
        print(f"DIFFERS from disk: {a}")
    for a in missing:
        print(f"NOT IN DRAFT: {a}")
    print(f"{len(seen)} json blocks mapped to files, {len(diffs)} differ, "
          f"{len(unknown)} unmapped, {len(missing)} expected but absent")
    if write and diffs:
        xml_path.write_text(new, encoding="utf-8")
        print(f"rewrote {len(diffs)} block(s) in {xml_path}")
    sys.exit(1 if (diffs and not write) or unknown or missing else 0)


if __name__ == "__main__":
    main()
