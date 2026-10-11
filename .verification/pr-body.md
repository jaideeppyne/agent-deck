## What problem does this solve?

Accounts whose `projects` directories point to the same transcript store cannot
use `session switch-account`, even though the destination already has the exact
conversation. `session set ... account` also emits a needless migration warning.
Fixes #2639.

## Why this change

Recognize a shared, existing real projects directory only for a no-copy switch.
Read the exact recorded ID through its canonical root, retaining the prohibition
on symlinks below that root. Recheck the shared root and final bytes after stop;
if the accounts were rebound, refuse and restore the source lifecycle instead
of installing anything. Separate stores retain the original migration guards.

The current baseline already exits 1 on refusal; the CLI regression protects
that behavior rather than adding an unnecessary exit-code change. Normal account
mutation, storage CAS, journaling, rollback and restart remain in the existing
executor. No dependencies or workflows belong to the proposed upstream diff.

Review follow-up retains stale/missing-ID repair and ambiguity refusal before
the legacy shared-store no-op, and compares directory identity with os.SameFile
after stop to detect replacement at the same pathname. The 406-line diff is
mostly regression coverage for this one no-copy safety contract; splitting its
identity/symlink/rollback safeguards would leave an incomplete behavioral fix.

## User impact

Shared-store account changes avoid staging, replacing, archiving or copying
transcripts and sidechains. Existing project-key aliases retain their own bytes.
Different-store symlink migrations still fail with nonzero exit status. The
receipt identifies the conversation already present in the shared store.

## Evidence

Review follow-up source ce4c577 adds deterministic legacy identity-recheck tests
and real TUI/loopback-SSH coverage. The oversized diff is inseparable safety
coverage for the same no-copy account switch, not unrelated features. Splitting
these into separate contributions would leave the core fix without requested
guards; no artificial PR splitting. The internal legacy race is source-level
evidence, not a claimed external CLI race reproduction; the original account
switch still has separate real-binary paired receipts.

Baseline production revision: `036915808f43363ca9d54e77ce1fc0706b82029c`.
Initial isolated proof: https://github.com/jaideeppyne/agent-deck/actions/runs/38126087343.

```text
session switch-account ... work --no-restart --json
EXIT: 1
unsafe exact Claude source path: path component is a symlink: .../projects
TRANSCRIPT_UNCHANGED: True
ORACLE: shared-store refusal reproduced
```

Three positive regression cases fail on baseline; nested-symlink refusal and
different-store refusal controls pass. Additional tests cover final stop-flushed
bytes and rollback if both accounts are rebound during stop. The fixed binary,
full sandboxed suite and contributor self-check are being verified in a
fork-only Docker workflow before publication. No host Go tests were run.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** unsure (Codex)

**Prompt / session log (optional):** Not published; the technical receipts and
synthetic fixtures are public in the fork validation branch. No claim of personal
human review or actual Claude authentication is made.

## What actually bothered you

The issue author asked: "If the source and target project dirs resolve to the
same realpath, the conversation is already there: skip the copy and report
success, instead of refusing."

My human asked: "next make 5-6 more strong contributions on projects which has
very high frequency of merges in the world".
I selected this reported bug; I am not claiming my human encountered it personally.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container: final verification pending
- [ ] If this touches a hot path (list, status, session output, startup, tmux layer): before/after timing evidence included
- [x] CHANGELOG.md untouched (entries are added at landing)
- [x] AI-assisted? Disclosed above, with validation evidence, and I can answer questions about the code
- [ ] "Allow edits from maintainers" is enabled: to be enabled at publication

<!-- gate:ai=authored model=unsure intent=yes -->
