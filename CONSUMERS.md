# CONSUMERS.md — who is downstream of this seam, and what they pin

This register exists because three times in one week a downstream implementation
was found building against a version this seam had already moved past, and
**every one of them surfaced by luck.**

| # | what was stale | how long | how it surfaced |
|---|---|---|---|
| 1 | a connector interface document pinned the seam at v2.3.0, never cascaded v3.0.0 | unknown, ≥ weeks | a version number appeared in passing in an unrelated reply |
| 2 | an `amap-router-*` runtime published attachments to a path v3.0.0 deleted | ~1 year | it moved a document to another repo for unrelated reasons |
| 3 | the same repo's open question was labelled WAITING — "blocked on a fact nobody has yet" — while the fact sat in this repo | ~weeks | as above |

None was detectable from either end. A downstream repo cannot know this one
moved. This one had no idea they existed.

**The lesson is not "write the question down."** Instance 2 was documented
carefully, in the repo that raised it, for a year, and the documentation did
nothing to shorten the non-conformance. What closed it was the document reaching
the party who could answer it. In the words of the runtime that filed it: *a
question filed in the implementation that raised it is visible to everyone
except the party who can answer it.*

## The register

Maintained by hand, and therefore incomplete — see the honesty note below.

| consumer class | what it is | pins |
|---|---|---|
| `amap-router-*` | runtimes — the trusted, credentialed half of the seam | one tracks v3.1.0 DRAFT as of 2026-09-20; the rest unknown |
| `amap-connector-*` | connectors — the untrusted per-agent half | one tracks v3.1.0 DRAFT as of 2026-09-20; the rest unknown |
| `amap-adapter-*` | host adapters — consume the layout, not the documents | one tracks v3.1.0 DRAFT as of 2026-09-20; the rest unknown |
| a connector interface document | defines what a connector IS, upstream of any one implementation | **targets v3.1.0 DRAFT** (§5.2); older sections pinned v2.3.0 and are mid-cascade |
| a conformance harness | runs the fixture gate against implementations | unknown |

**Classes, not instances, and that is deliberate.** Naming individual
implementations here would publish a roster of deployments that are not
themselves published, and would go stale faster than the classes do — a
consumer is renamed or retired far more often than a *kind* of consumer
appears. The operator holds the instance-level register and the routes; this
file carries what a reader of the contract needs, which is that these three
classes exist, that they version-check independently, and that cutting a
version means telling them.

## The obligation this creates

**Cutting a version means telling this list.** Not "publishing a changelog" —
telling them, by whatever route reaches each one, with what changed and what to
re-check. (Routes are operational detail and are kept out of this file; the
operator holds them.) A version is not cut until that is done.

`WORKFLOWS.md` carries this as a step in the cut process rather than leaving it
here as a good intention, because a good intention is what produced the three
rows above.

## What this does not fix, stated plainly

- **The register is hand-maintained and will go stale**, which is the same class
  of failure it exists to catch. It converts "nobody knows who to tell" into
  "here is who to tell, and the list may be incomplete" — a real improvement and
  not a solution.
- **Most consumers have never been contacted about a version at all.** Each
  class above records that rather than omitting it, because an absent row looks
  like no consumer and a row marked *unknown* looks like work.
- **Nothing here detects staleness**; it only makes notification possible. A
  downstream repo that ignores a notice is exactly as stale as one that never
  got it. The detection half is a read-only mount of this repo's `spec/`,
  `schemas/` and `fixtures/` on each consumer, so that the contract is in front
  of the implementer rather than remembered. That half now exists — see
  `SANDY-FEATURE.md` — and it closes the *reading* gap, not the notification
  one: a mounted spec tells a consumer what the contract says today, and still
  does not tell them that it changed.
