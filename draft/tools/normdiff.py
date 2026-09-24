#!/usr/bin/env python3
"""normdiff.py — the normative diff of the draft between a git ref and the
working tree: every RFC 2119 sentence added, removed or changed.

Why: the draft XML is canonical and hand-edited, and an XML diff is a poor way
to see a change in meaning. A reviewer reads this instead. CI writes it to the
job summary on every pull request. A change in meaning then also needs its
schemas/ and fixtures/ counterpart (WORKFLOWS.md), and check_coverage.py makes
the new sentence's classification a decision.

    normdiff.py [BASE]      BASE is a git ref; default origin/main

If BASE predates the canonical XML (draft/draft-amap.xml), the committed
rendering at dist/draft-amap-00.xml is used instead, so the diff can span the
switch. Informational: always exits 0 unless git itself fails.

Stdlib only.
"""
from __future__ import annotations

import difflib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normative  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
CANDIDATES = ("draft/draft-amap.xml", "dist/draft-amap-00.xml")


def at_ref(ref: str) -> tuple[str, str]:
    for path in CANDIDATES:
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{path}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return path, r.stdout
    sys.exit(f"normdiff: neither {' nor '.join(CANDIDATES)} exists at {ref}")


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else "origin/main"
    base_path, base_xml = at_ref(base)
    head_xml = (REPO / "draft" / "draft-amap.xml").read_text(encoding="utf-8")
    old = normative.extract(base_xml)
    new = normative.extract(head_xml)
    old_ids = {normative.sentence_id(s): (a, s) for a, s in old}
    new_ids = {normative.sentence_id(s): (a, s) for a, s in new}
    removed = [old_ids[i] for i in old_ids if i not in new_ids]
    added = [new_ids[i] for i in new_ids if i not in old_ids]

    # pair a removed and an added sentence as "changed" when they are close
    changed, used = [], set()
    for ra, rs in removed:
        best, score = None, 0.0
        for k, (aa, as_) in enumerate(added):
            if k in used:
                continue
            r = difflib.SequenceMatcher(None, rs, as_).ratio()
            if r > score:
                best, score = k, r
        if best is not None and score >= 0.6:
            used.add(best)
            changed.append((ra, rs, added[best][0], added[best][1]))
    changed_old = {rs for _, rs, _, _ in changed}
    removed = [(a, s) for a, s in removed if s not in changed_old]
    added = [x for k, x in enumerate(added) if k not in used]

    print(f"## Normative diff: {base} ({base_path}) → working tree\n")
    if not (added or removed or changed):
        print("No normative sentence was added, removed or changed.")
        return 0
    print(f"{len(added)} added, {len(removed)} removed, {len(changed)} changed. "
          "A change in meaning needs its schemas/ and fixtures/ counterpart, and "
          "every new or reworded sentence needs a class in draft/coverage.toml.\n")
    if added:
        print("### Added\n")
        for a, s in added:
            print(f"- `{a}`: {s}")
        print()
    if removed:
        print("### Removed\n")
        for a, s in removed:
            print(f"- `{a}`: {s}")
        print()
    if changed:
        print("### Changed\n")
        for oa, os_, na, ns in changed:
            print(f"- `{oa}` → `{na}`\n  - before: {os_}\n  - after:  {ns}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
