## What problem does this solve?

Fixes #2640. Socket-delivered Claude peer prompts are wrapped, so exact typed
prompt identity cannot be bound and `session send --wait --json` times out despite
a completed reply. Busy socket waits also return no JSON result.

## Why this change

Use a new observed transcript turn only for idle socket waits, without parsing
an undocumented envelope or claiming acknowledgment. The pre-send cursor (or
NotBefore for a newly found transcript), UUID, sidechain, complete-record and
truncation guards remain. Exact tmux and stream prompt binding is unchanged.
Busy/probe-failed waits return their single unverified JSON result before any
transcript lookup. Partial replies are errors, not completed responses.
Socket completion reads the selected turn's end record directly rather than
pane-global status, which may already describe a later turn. Both transcript
polling sleeps are capped at the remaining deadline. Help describes the full
shared --timeout observation/reply budget; exact tmux binding stays intact.

## User impact

An idle socket wait can return fresh completed output as `observed_not_correlated`,
with `verified`, `submitted` and `acknowledged` all false. No turn or no completed
reply fails within the existing shared budget; no stale fallback or resend.
This does not make socket output correlated or fix socket streaming.

## Evidence

The affected CLI was reproduced on 0369158 in isolated Linux Docker, receiving
the real socket frame and a durable wrapped peer reply, yet exiting1 with
`turn identity not established`. Corrected baseline run38181423504 preserved
the expected idle/fast and busy JSON failures; dropped-message refusal passed.
An earlier run38181072745 used invalid fixture config and is not defect proof.

Published source0bf12b8 passed full run38197086039, but subsequent review found
back-to-back traffic starvation and completion sleeps exceeding short budgets.
Tests-first runs38200081687/38200229129 independently demonstrated the actual
selected complete reply timing out while a later turn was active, all original
five modes passing, four new CLI modes failing, obsolete help and transcript
poll deadlines failing behaviorally. These are not compilation failures.

This verification pairs published0bf12b8 with candidate0df6059, freezing the
nine-mode CLI fixture and reproduction inputs for both builds. It creates four
receipts, checks source guards under `-race -count=3`, and runs the full contributor
self-check and official five-stage Docker runner. Results must be independently
inspected before publishing this draft body. Only the external paid Claude is
synthetic: launch, tmux, socket resolver, send and transcript reader are real.
This is not a live macOS Claude or Slack integration test.

Run38191099260 passed the paired targeted tests, source guards and actual-CLI
oracles, but failed both full suites: the new fixture did not publish its socket
record when other tests had already started the shared tmux server. The fixture
now uses a private tmux server directory per case, with helper stderr captured
for diagnosis. Both sides and all full gates must be rerun on this exact fixture;
the failed full run is not treated as success. That run also reported an existing
storage-watcher TempDir cleanup failure, not claimed fixed by this change.

The same runner records paired startup smoke timings (3 warmups,25 samples) and
actual send durations, not a general performance claim. The broad self-check
revert may warn about new helper/API symbols; the independently executable CLI
regression is the behavioral red/green proof, not a compilation failure.

491 changed lines implement one wait contract and cover its end-to-end fixture,
freshness/safety guards and shared budget. The fixture and refusal controls are
inseparable proof for the behavior change, not a separately shippable feature.
The review update is part of this same PR, not a new artificially split PR.
No dependency, changelog or workflow changes enter the upstream PR.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** unsure (Codex)

## What actually bothered you

My human asked: "next make 5-6 more strong contributions on projects which has
very high frequency of merges in the world". I selected the existing reported
socket-wait failure to improve a real workflow, not a bug personally encountered
by my human. No personal review or usage is implied.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container: run `.github/skills/agent-deck-contributor/scripts/self-check.sh`, which prints the Docker command (never `go test` on your host)
- [ ] If this touches a hot path (list, status, session output, startup, tmux layer): before/after timing evidence included
- [x] CHANGELOG.md untouched (entries are added at landing)
- [x] AI-assisted? Disclosed above, with validation evidence, and I can answer questions about the code
- [ ] "Allow edits from maintainers" is enabled

<!-- gate:ai=authored model=unsure intent=yes -->
