#!/usr/bin/env python3
"""gen_appendices.py — compile draft/fixtures.toml + fixtures/ + schemas/ into
kramdown-rfc fragments under draft/build/.

This is the load-bearing piece of the draft build: every JSON document that
appears in the rendered Internet-Draft is either included verbatim from a file
on disk (the six schemas, via a direct {::include-fold...} in the hand
source) or generated HERE from fixtures/ — never hand-copied into the .mkd.
draft/check_render.py is the other half of that proof: it re-derives the same
comparison from the rendered XML and fails the build if the two disagree.

Stdlib only (Python 3.13's tomllib). No dependency on kramdown-rfc or
xml2rfc: this step runs before either is invoked.

Usage: python3 draft/gen_appendices.py [--repo REPO] [--out draft/build]
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


def load_validator(repo: Path):
    """Import fixtures/validate.py as a module named `validate`, the same
    module the fixture gate itself runs. We import it rather than
    reimplementing any part of it, so a change to the gate's meaning cannot
    silently drift from what this compiler asserts."""
    sys.path.insert(0, str(repo / "fixtures"))
    import validate  # type: ignore
    return validate


def fence(path_rel_to_repo: str, anchor_src: str, title: str) -> str:
    basename = Path(path_rel_to_repo).name
    return (
        "~~~ json\n"
        f"{{::include-fold69hardleft4dry {path_rel_to_repo}}}\n"
        "~~~\n"
        f'{{: #{anchor_src} title="{path_rel_to_repo}" sourcecode-name="{basename}"}}\n'
    )


def _wrap_for_artwork(line: str, width: int = 69, indent: str = "  ") -> list[str]:
    """Wrap one gate error line so it renders inside a plain-text xml2rfc
    artwork block without a 'too long line' warning. Cosmetic only — the
    wrapped text still reads as the same sentence, just folded by hand
    rather than by RFC 8792 (which applies to JSON, not free text)."""
    if len(line) <= width:
        return [line]
    words = line.split(" ")
    out: list[str] = []
    cur = ""
    for w in words:
        cand = (cur + " " + w) if cur else w
        if len(cand) > width and cur:
            out.append(cur)
            cur = indent + w
        else:
            cur = cand
    if cur:
        out.append(cur)
    return out


def render_fixture_block(entry: dict, validate_mod, with_heading: bool = True) -> str:
    file_rel = entry["file"]
    anchor = entry["anchor"]
    title = entry["title"]
    pins = entry["pins"]
    is_invalid = file_rel.startswith("invalid/")

    if with_heading:
        lines = [f"## {title} {{#{anchor}}}", "", pins, ""]
    else:
        # placement="body": no heading — this fragment is included inline
        # into hand prose (e.g. Section 9), and must not introduce its own
        # numbered subsection.
        lines = [pins, ""]

    if is_invalid:
        why_fails = entry["why_fails"]
        lines += [why_fails, ""]

    if is_invalid:
        # Recompute the gate's own errors so the reason shown here cannot
        # drift from fixtures/validate.py's actual behavior.
        doc = json.loads((validate_mod.HERE / file_rel).read_text())
        errs = validate_mod.check_document(Path(file_rel).name, doc)
        if not errs:
            raise SystemExit(
                f"gen_appendices: fixture '{file_rel}' is listed under invalid/ "
                f"in fixtures.toml but the gate reports it VALID (no errors). "
                f"fixtures.toml is out of sync with fixtures/validate.py."
            )
        lines.append("The conformance gate's own errors for this document:")
        lines.append("")
        lines.append("~~~ text")
        for err in errs:
            lines.extend(_wrap_for_artwork(err))
        lines.append("~~~")
        lines.append("")
    else:
        doc = json.loads((validate_mod.HERE / file_rel).read_text())
        errs = validate_mod.check_document(Path(file_rel).name, doc)
        if errs:
            raise SystemExit(
                f"gen_appendices: fixture '{file_rel}' is listed under valid/ "
                f"in fixtures.toml but the gate reports errors: {errs}. "
                f"fixtures.toml is out of sync with fixtures/validate.py."
            )

    lines.append(fence(f"fixtures/{file_rel}", f"{anchor}-src", title))
    return "\n".join(lines) + "\n"


def gen_fixtures(repo: Path, out: Path, cfg: dict, validate_mod) -> None:
    fixtures = cfg.get("fixture", [])
    policy = cfg.get("policy", {})
    min_inline = policy.get("min_inline", 0)
    max_inline = policy.get("max_inline", 10**9)

    if not (min_inline <= len(fixtures) <= max_inline):
        raise SystemExit(
            f"gen_appendices: fixtures.toml lists {len(fixtures)} fixtures, "
            f"outside the configured [policy] band [{min_inline}, {max_inline}]."
        )

    anchors_seen: set[str] = set()
    appendix_parts: list[str] = []

    for entry in fixtures:
        file_rel = entry["file"]
        if not (file_rel.startswith("valid/") or file_rel.startswith("invalid/")):
            raise SystemExit(
                f"gen_appendices: fixture 'file' must start with 'valid/' or "
                f"'invalid/', got: {file_rel!r}"
            )
        if not (repo / "fixtures" / file_rel).exists():
            raise SystemExit(f"gen_appendices: fixture file not found: fixtures/{file_rel}")
        anchor = entry["anchor"]
        if anchor in anchors_seen:
            raise SystemExit(f"gen_appendices: duplicate fixture anchor: {anchor}")
        anchors_seen.add(anchor)
        if file_rel.startswith("invalid/") and not entry.get("why_fails", "").strip():
            raise SystemExit(
                f"gen_appendices: invalid fixture '{file_rel}' has no non-empty "
                f"'why_fails' in fixtures.toml — a negative fixture is meaningless "
                f"inline without its reason."
            )

        placement = entry.get("placement", "appendix")
        block = render_fixture_block(entry, validate_mod, with_heading=(placement != "body"))
        if placement == "appendix":
            appendix_parts.append(block)
        elif placement == "body":
            (out / f"fixture-{anchor}.mkd").write_text(block, encoding="utf-8")
        else:
            raise SystemExit(f"gen_appendices: unknown placement {placement!r} for {anchor}")

    (out / "appendix-fixtures.mkd").write_text(
        "\n".join(appendix_parts), encoding="utf-8"
    )


def gen_roster(repo: Path, out: Path, validate_mod) -> None:
    valid = sorted((repo / "fixtures" / "valid").glob("*.json"))
    invalid = sorted((repo / "fixtures" / "invalid").glob("*.json"))
    total = len(valid) + len(invalid)

    rows = ["| fixture | schema |", "|---|---|"]
    for sub, files in (("valid", valid), ("invalid", invalid)):
        for f in files:
            schema_fn = None
            for prefix, fn in validate_mod.SCHEMA_FOR_PREFIX.items():
                if f.name.startswith(prefix):
                    schema_fn = fn
                    break
            if schema_fn is None:
                raise SystemExit(
                    f"gen_appendices: fixture 'fixtures/{sub}/{f.name}' matches no "
                    f"prefix in validate.SCHEMA_FOR_PREFIX — the same rule the gate "
                    f"applies would also reject it."
                )
            rows.append(f"| `{sub}/{f.name}` | `{schema_fn}` |")

    text = (
        f"At this document version the suite contains **{total} fixtures — "
        f"{len(valid)} valid and {len(invalid)} invalid**.\n\n"
        + "\n".join(rows)
        + "\n"
    )
    (out / "appendix-h-roster.mkd").write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    repo = Path(args.repo) if args.repo else Path(__file__).resolve().parent.parent.parent
    out = Path(args.out) if args.out else repo / "draft" / "build"
    out.mkdir(parents=True, exist_ok=True)

    cfg = tomllib.loads((repo / "draft" / "fixtures.toml").read_text())
    validate_mod = load_validator(repo)

    gen_fixtures(repo, out, cfg, validate_mod)
    gen_roster(repo, out, validate_mod)

    print(f"gen_appendices: wrote fragments to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
