# The AMMP website

The source of the explainer site, published with GitHub Pages from `docs/`
on `main`.

## Layout

| Path | What it is |
|---|---|
| `site/src/*.html` | Page bodies. Line 1 of each is `<!-- title: … \| description: … -->` |
| `site/assets/` | The stylesheet (light and dark), the nav script, the logo mark, and the validator scripts |
| `site/build_site.py` | Wraps each page in the shared header, navigation and footer, copies `assets/` and the repository's `schemas/`, writes `docs/`, and checks every internal link. Standard library only |
| `site/tools/` | The validator's helpers: embedding the schemas, and a Node test that runs every fixture through the browser validator |
| `docs/` | **Generated.** The deployable site: relative links, no build step, and it also works opened from disk. Never edit it by hand |

## Build

```sh
python3 site/build_site.py           # writes docs/, fails on a broken link
python3 site/build_site.py --check   # fails if docs/ differs from what site/ builds
```

Commit `site/` and the rebuilt `docs/` together.

The counts on the pages are filled in from the repository at build time:
`{{FIXTURES}}`, `{{FIXTURES_VALID}}`, `{{FIXTURES_INVALID}}`, and
`{{DOC_TYPES}}` (the number of schemas). Adding a fixture or a schema
changes the site the next time it is built, so nobody has to remember to edit
a number.

**After changing a schema,** regenerate the validator's embedded copy and prove
it still agrees with the gate:

```sh
node site/tools/gen_validator_schemas.mjs
node site/tools/test_validator.mjs   # every fixture; must print AGREE
```

## Content rules

- A neutral project voice. Proofpoint is credited as AMMP's originator, and
  nothing else: no product names, no commercial positioning.
- The protocol is AMMP, the Agent Mediated Messaging Protocol (renamed from
  AMAP on 2026-10-18). The repositories keep their `amap-` names and the
  `AMAP-Peer-*` header fields keep theirs; never rename those in prose.
- The draft is an individual Internet-Draft, posted 2026-10-22. Say "posted",
  link the Datatracker, and never say adopted, in a working group, or an IETF
  standard.
- "The AMMP specification", never a bare "contract".
- Hypotheses are labelled as hypotheses, and specified behaviour as
  specified.
- Cite the specification by section **name** (for example "§ Inbound"),
  never by rendered number or commit hash. Rendered numbers move whenever
  the Internet-Draft gains a section. The peer-origin profile is a section
  of the Internet-Draft, so its subsections are cited by name too ("§ The
  Peer Tree"); the frozen `spec/peer-origin.md`'s numbers are not cited.
- Name only what is public. The site describes the public repositories and
  nothing else.
