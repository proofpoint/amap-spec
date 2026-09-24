#!/usr/bin/env python3
"""check_coverage.py — every normative sentence in the protocol sections of the
draft must be classified in draft/coverage.toml.

Why: the draft XML is hand-edited and canonical. An editor can add a MUST in
one keystroke, and nothing about the XML says whether any implementation or
fixture has caught up. This gate makes that a decision instead of an accident.
Every RFC 2119 sentence in the protocol sections (anchors sec-3 through sec-10,
plus the Peer Directory and the Fleet Roster; normative.in_coverage_scope) needs an entry, keyed by a hash of its text, with
one of these classes:

  fixture       exercised by the listed fixtures (each must exist on disk)
  operational   a filesystem or policy obligation no document validator can
                see (the NOT-CHECKED list in fixtures/validate.py); `note` says
                which one
  informative   carries a keyword but asks nothing checkable of an implementer;
                `note` says why
  unclassified  not yet decided. This is the migration baseline: the sentences
                present when the XML became canonical, recorded but not yet
                reasoned about. Working it down is real progress; adding to it
                is not.

The gate fails on:
  - a normative sentence with no entry (new, or reworded: rewording changes
    the hash, so the sentence is reviewed again);
  - an entry whose sentence no longer exists (stale; delete or re-key it);
  - class "fixture" naming a fixture that does not exist, or none at all;
  - class "operational" or "informative" with no note;
  - an unclassified entry added after the baseline (unclassified entries must
    carry baseline = true).

    check_coverage.py            run the gate
    check_coverage.py --emit     print TOML stubs for sentences with no entry

Stdlib only.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normative  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "draft" / "draft-amap.xml"
COVERAGE = REPO / "draft" / "coverage.toml"
CLASSES = {"fixture", "operational", "informative", "unclassified"}


def toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def stub(section: str, sentence: str, baseline: bool = False) -> str:
    lines = [
        "[[sentence]]",
        f"id = {toml_str(normative.sentence_id(sentence))}",
        f"section = {toml_str(section)}",
        'class = "unclassified"',
    ]
    if baseline:
        lines.append("baseline = true")
    lines.append(f"text = {toml_str(sentence)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    sentences = [(a, s) for a, s in normative.extract(SRC.read_text(encoding="utf-8"))
                 if normative.in_coverage_scope(a)]
    current = {normative.sentence_id(s): (a, s) for a, s in sentences}
    entries = tomllib.loads(COVERAGE.read_text(encoding="utf-8")).get("sentence", []) \
        if COVERAGE.exists() else []
    by_id = {e["id"]: e for e in entries}

    if "--emit" in argv:
        for sid, (a, s) in current.items():
            if sid not in by_id:
                print(stub(a, s))
        return 0

    errors = []
    for sid, (a, s) in current.items():
        if sid not in by_id:
            errors.append(f"UNCLASSIFIED ({a}): {s[:150]}")
    for e in entries:
        sid, cls = e.get("id"), e.get("class")
        if sid not in current:
            errors.append(f"STALE entry {sid} ({e.get('section')}): the sentence is gone or reworded")
            continue
        if cls not in CLASSES:
            errors.append(f"{sid}: unknown class {cls!r}")
        elif cls == "fixture":
            fx = e.get("fixtures") or []
            if not fx:
                errors.append(f"{sid}: class fixture lists no fixtures")
            for f in fx:
                if not (REPO / "fixtures" / f).exists():
                    errors.append(f"{sid}: fixture {f} does not exist")
        elif cls in ("operational", "informative") and not e.get("note"):
            errors.append(f"{sid}: class {cls} needs a note saying why")
        elif cls == "unclassified" and not e.get("baseline"):
            errors.append(f"{sid}: new entries must be classified; unclassified is the migration baseline only")

    counts = {c: sum(1 for e in entries if e.get("class") == c and e.get("id") in current)
              for c in sorted(CLASSES)}
    for msg in errors:
        print("  FAIL:", msg)
    summary = ", ".join(f"{n} {c}" for c, n in counts.items())
    print(f"check_coverage: {len(current)} normative sentences in scope: {summary}")
    if errors:
        print("check_coverage: FAILED. Classify new sentences in draft/coverage.toml "
              "(`python3 draft/tools/check_coverage.py --emit` prints stubs).")
        return 1
    print("check_coverage: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
