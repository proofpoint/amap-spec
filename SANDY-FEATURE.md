# amap-spec as a sandy feature

**These files belong at the root of the `amap-spec` repository.** Dropped there
and installed, they mount this repository's `spec/`, `schemas/` and `fixtures/`
**read-only and live** into every sandbox whose slug starts with `amap-` (except
the spec's own), and append a conformance instruction to the Claude system
prompt there.

```
feature.json               the manifest -- the whole of what sandy reads
CONFORMANCE.md             appended to the claude system prompt
install-sandy-feature.sh   symlink $SANDY_HOME/features/amap-spec -> this checkout
SANDY-FEATURE.md           this file
```

Every added filename is namespaced for the same reason: amap-spec has a
`README.md` and may well want an `install.sh`, and neither of those is this.
`feature.json` and `CONFORMANCE.md` are the two that are not — `feature.json` is
the name sandy requires and cannot be changed, and `CONFORMANCE.md` is the one
the manifest and the mount table both point at, so renaming it is a two-line
change if the spec repo wants that name for itself.

```sh
cp feature.json CONFORMANCE.md install-sandy-feature.sh SANDY-FEATURE.md ~/dev/amap-spec/
cd ~/dev/amap-spec && ./install-sandy-feature.sh
# ... then relaunch any amap-* workspace
```

Requires **sandy 2.1.0+** (`agent_args`). `install-sandy-feature.sh` refuses below that — see
*Installing on too old a sandy is not a no-op*.

## Why the checkout itself is the feature directory

A manifest mount's `from` is validated segment by segment — `[A-Za-z0-9._-]+`,
no leading dot, no `..`, never absolute — so a manifest **cannot** point at a
path outside its own feature directory. The destination is computed by sandy,
never declared, and a computed root is only a root if its components cannot
escape it.

That leaves exactly two ways to get the spec inside the feature directory: copy
it in, or make the checkout *be* the feature directory. `install-sandy-feature.sh` does the
second, with one symlink:

```
$SANDY_HOME/features/amap-spec  ->  ~/dev/amap-spec
```

Sandy then resolves `from: "spec"` relative to whatever that turns out to be,
and the bind mount source is the working tree itself. **Nothing is copied and
there is no sync step.** An edit to `spec/` is visible inside a running
container immediately — verified: writing to the checkout changes what the
emitted mount source reads, same inode, no re-install.

The symlink sits in `$SANDY_HOME`, which no repository can reach, so the feature
stays privileged by construction of where it lives. It moves no *mount source*
outside the feature directory — that is a different thing, and a symlink inside
a mounted directory would defeat the `from` validation (string predicate, Docker
dereferences). Don't add one.

## Where it lands in the container

| mount `name` | container path |
|---|---|
| `spec` | `~/.amap-spec/spec` |
| `schemas` | `~/.amap-spec/schemas` |
| `fixtures` | `~/.amap-spec/fixtures` |
| `CONFORMANCE.md` | `~/.amap-spec/CONFORMANCE.md` |

The destination comes from the **`name`**, not the `from`: sandy maps `payload`
to `/opt/sandy/features/<feature>`, `.` to `~/.<feature>`, and anything else to
`~/.<feature>/<name>`. `<feature>` is the directory name under
`$SANDY_HOME/features/` — set by `install-sandy-feature.sh` — not `feature.name`, which sandy
never reads.

Four named mounts rather than one `.` mount of the whole repo: `.` would also
carry `.git` and everything else into every amap sandbox for no benefit, and
`.git` cannot be named as a `from` anyway (leading dot is rejected).

## What the manifest says, and why

| key | value | why |
|---|---|---|
| `sandboxes.include` | `["amap-*"]` | Matched case-folded against the **slug** (`<basename>-<sha8>`) *and* the workspace host path. `amap-adapter-example` yields slug `amap-adapter-example-<sha8>`, which matches; the path `/Users/you/dev/amap-adapter-example` does not, since the glob is anchored — so the slug does the work. |
| `sandboxes.exclude` | `["amap-spec-????????", "*/amap-spec"]` | The spec's own workspace. See *Excluding one sandbox* — the obvious spelling silently matches nothing. |
| `agents.include` | `["*"]` | Every agent gets the reference material. Only `claude` gets the injected prompt, because `--append-system-prompt-file` is Claude Code's flag. |
| `mounts` | four, `mode: "ro"` | `ro` is the default; it is spelled out because it is the security-relevant field. |
| `agent_args.claude` | `--append-system-prompt-file ~/.amap-spec/CONFORMANCE.md` | Stateless: nothing is written into any sandbox, and the file it names is on a `:ro` mount. |
| `feature` | prose | The one reserved top-level key sandy never interprets. |

Selection is **enrolment, default-deny**: an include must match in *both*
blocks, any exclude in either wins, and a sandbox that is not selected gets no
mount, no export and no args at all.

## Excluding one sandbox

Exclude beats include, unconditionally and regardless of order: sandy scans
every entry in both blocks and returns on the **first** matching exclude. So the
precedence is not the hard part. The pattern is.

A `sandboxes` pattern is a glob matched **anchored at both ends** against two
things — the slug (`amap-spec-a1b2c3d4`) and the canonical workspace host path
(`/Users/you/dev/amap-spec`). A bare `"amap-spec"` equals neither, so it matches
nothing, and **nothing tells you**: sandy warns by name for a mount source that
does not exist, but has no equivalent check for a pattern that selected zero
sandboxes. It reads as a working exclusion and is not one. Measured:

```
exclude: ["amap-spec"]
  MOUNTED   amap-spec-a1b2c3d4   /Users/you/dev/amap-spec        <- still mounted
```

Two anchors are used instead, either of which is sufficient:

| pattern | matches | why not something simpler |
|---|---|---|
| `amap-spec-????????` | the slug, exactly — `?` is one character and the hash is exactly 8 | `amap-spec-*` also swallows a future `amap-spec-tools`, `amap-spec-validator`, … |
| `*/amap-spec` | the workspace path, wherever the checkout lives | a second checkout at `~/work/amap-spec` gets a different hash but the same basename |

**Check it after the fact, do not assume it.** `selected.json` names every
sandbox that was *not* selected and which pattern excluded it — the one place a
no-op pattern becomes visible.

**Prose does not go in a selection block.** `sandboxes` and `agents` accept
`include` and `exclude` and nothing else; an unknown key refuses the whole
manifest, which fails **every** launch on the host. `feature` is the only key
that takes free-form documentation.

## Sandy writes into this repository

At every launch and every `--remove-sandbox`, sandy writes its selection record
into the feature directory — which is now the amap-spec working tree. Add to
`.gitignore`:

```
/.selected/
/selected.json
/selected.json.tmp.*
```

`install-sandy-feature.sh` checks and prints these if they are missing. That is the price of
the checkout being the feature directory; it buys the live mount.

## Installing on too old a sandy is not a no-op

`agent_args` arrived in sandy 2.1.0. On an older sandy it is an **unknown
top-level key**, and an unreadable manifest is refused *in full* — `sandy` then
exits 1 for **every** launch on that host, not just `amap-*` ones. So
`install-sandy-feature.sh` gates hard, and it gates on **capability, not version**:

```sh
sandy --print-schema | jq '.manifest.top_level_keys | index("agent_args")'
```

A version test would be wrong here: a stripped `X.Y.Z-dev` compares equal to
`X.Y.Z`, so `>= 2.1.0` is satisfied by every commit on the 2.1.0-dev line,
including ones predating the feature.

Backing out is `./install-sandy-feature.sh --uninstall` — it removes the symlink and touches
nothing else.

## A skipped mount does not withdraw the flag

Measured against sandy 2.2.0's own `_sandy_fm_apply`: a mount whose source is
absent is skipped with a named warning — and `agent_args` is **still emitted**.
A missing `CONFORMANCE.md` would therefore hand claude an
`--append-system-prompt-file` naming a container path that does not exist, in
every selected sandbox. `install-sandy-feature.sh` refuses to install unless all four mount
sources are present, which also catches being run from the wrong directory.

## Verifying it actually applied

```sh
sandy --print-state | jq '.sandboxes[] | {name, agent_args}'
```

Three states, and they do not collapse: the field **absent** means a sandy too
old to answer; `{}` means none applied; populated names the args *and the
feature that contributed them*. It reports the **last** launch, not the next.

```sh
cat "$SANDY_HOME/features/amap-spec/selected.json"
```

Note the caveat that file ships with: selection depends on the agents a launch
resolved to, so for a sandbox that is not running, the agent dimension is
*unknowable* rather than merely stale.

In-container: `ls ~/.amap-spec/`

## Three behaviours to expect

**The mounts are live; the prompt is not.** Editing `spec/`, `schemas/` or
`fixtures/` on the host is visible inside running containers immediately.
`CONFORMANCE.md` is different: it is read by Claude Code at startup, and
`--system-prompt-snapshot` defaults to `on`, so an appended system prompt is
recorded on the conversation's first request and replayed verbatim on resume
until compaction. Editing it reaches *new* conversations after a relaunch; a
resumed one keeps the old text. Removal is not immediate for the same reason.
The file is still mounted live, so an agent that re-reads `~/.amap-spec/CONFORMANCE.md`
sees the current text — the staleness is only in the injected copy.

**A live mount has no version stamp.** The spec in the container is whatever the
checkout holds right now, including uncommitted work. That is the trade for
liveness: a copy-based sync could stamp the commit, a bind mount cannot, and
`.git` is not mountable (leading dot). CONFORMANCE.md tells the agent to ask
rather than invent a version.

**Selection happens at launch, not continuously.** Installing the feature does
nothing for a session that is already running; relaunch it. The *contents* are
live thereafter, but enrolment is not.

**Non-claude sandboxes get the mounts without the instruction.** `agent_args` is
keyed by agent and there is no equivalent flag for gemini/codex/opencode/grok,
so a non-claude amap-* sandbox sees `~/.amap-spec/` and is never told to look.
If that matters, add an `agents.exclude` for those agents — they then get
nothing, which is at least honest.
