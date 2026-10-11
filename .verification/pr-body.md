## What problem does this solve?

An explicit cross-profile launch can run Claude with the caller's inherited
account and config directory, consuming the wrong quota while recording the
requested storage profile. Fixes #2632.

## Why this change

The explicit profile boundary already captures the caller's profile. When the
requested profile differs from a nonempty caller profile, remove the inherited
account and Claude config override so the selected profile's configuration wins.
Explicit --account is still resolved afterward. Same-profile, no-flag and
unknown caller-profile cases preserve their existing precedence.

Preserve the original values and their presence for inheritedEnviron, so a
wrapped statusLine command receives its original profile/account environment.
No dependencies, workflows or changelog edits belong to the upstream diff.

## User impact

Cross-profile creation no longer charges the caller's Claude account. Explicit
account overrides and same-profile launches retain their behavior; user statusLine
scripts keep their inherited variables, including absent versus empty values.

## Evidence

Affected revision: 036915808f43363ca9d54e77ce1fc0706b82029c.
Initial baseline: https://github.com/jaideeppyne/agent-deck/actions/runs/38143598381.

    agent-deck -p work launch ... --cmd claude --no-wait --json
    profile: work
    CHILD_CONFIG_DIR: /work/home/.claude-it
    PERSISTED_ACCOUNT: 'it'
    ORACLE: cross-profile launch inherited caller account

The original binary was run offline with fresh HOME/XDG and private tmux; only
the external paid tool was replaced by a shim recording its actual environment.
The regression fails on the baseline for both launched config dir and persisted
account, while explicit-account and same-profile controls pass. Fixed binary,
full sandboxed suite and before/after startup timings are being verified before
publication. No host Go tests, real Claude login or paid model invocation.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** unsure (Codex)

**Prompt / session log (optional):** Synthetic fixtures and compact validation
receipts are public in the fork; no personal human review is claimed.

## What actually bothered you

The issue author expected: "The child runs on ~/.claude-work, because that is
what profile work is configured to use." (Formatting normalized from the issue.)

My human asked: "next make 5-6 more strong contributions on projects which has
very high frequency of merges in the world". I selected this existing reported
bug, not claiming my human personally encountered it.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container: final verification pending
- [ ] If this touches a hot path (list, status, session output, startup, tmux layer): before/after timing evidence included
- [x] CHANGELOG.md untouched (entries are added at landing)
- [x] AI-assisted? Disclosed above, with validation evidence, and I can answer questions about the code
- [ ] "Allow edits from maintainers" is enabled: to be enabled at publication

<!-- gate:ai=authored model=unsure intent=yes -->
