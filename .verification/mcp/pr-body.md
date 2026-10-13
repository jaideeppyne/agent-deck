## What problem does this solve?

Addresses the MCP proxy client lifetime and reconnect-input portion of #2649. A closed client stdin should end its proxy, and a socket disconnect must not lose an input chunk whose write made no progress or forward a continuation whose prefix went to the previous connection.

## Why this change

One bounded 32 KiB stdin reader persists across socket generations. Cancellable dial/backoff and connection closure end the proxy on stdin EOF or a parent identity change. The reconnect state retains a zero-progress chunk at a request boundary, and skips an unfinished request through its next newline rather than replaying a suffix on a new connection. A chunk with positive write progress is conservatively dropped, not replayed.

The added fixture and state are part of this same lifecycle problem; splitting the regression matrix from the implementation would leave the fix unguarded. Diff-size warnings are expected and will be disclosed. The existing local Unix dial now uses DialContext; this is not a new external endpoint. No new dependencies or shared pool production changes.

## User impact

Backend reconnects retain wholly unsent input at newline request boundaries without delivering incomplete continuations as new requests. Input remains bounded. EOF ends the client, not a promise to drain queued requests or responses, and no measured memory reduction or blanket historical-zombie fix is claimed.

**Startup limitation:** parent identity is sampled inside the proxy. A parent exit after that snapshot is detected; a launching parent that exited before the snapshot and left the child with a stable reaper is not detected. Rejecting every PID-1 parent would also reject legitimate container launches. That review finding remains open pending a stronger launcher-identity contract; the existing parent-exit test does not cover pre-startup adoption.

## Evidence

Exact candidate: a03e89a291d8337adc4f9d7e34b30144e67e3ca9. This body is for fork validation, not a claim that the new full gates have already passed or that the public PR has been updated.

- Tests-first baseline38330171815 freezes0712fa8 over unchanged published e4. Nine behavioral failures across three repeated request-loss/continuation cases, six passing controls. A separate Unix half-close control proves a zero-byte write with the opposite output half still open. Artifact log hash independently verified.
- Candidate38330768422: all lifetime tests under race detection count3 pass; four new framing cases each pass three times. Exact source and artifact hashes independently checked. Darwin/Linux arm64 cross-builds pass, not macOS runtime evidence.
- That initial targeted job ran **no pool tests** because its command lacked integration tags. Corrected38331504618 explicitly requires both tagged natural-exit and restart controls; do not count the initial empty run as evidence.
- The full paired receipt experiment, native contributor self-check, and official five-stage Docker runner are being rerun on this exact source. Earlier e4 self-check failures and the official runner's built-in exit-status retry remain disclosed in the public PR; no clean-first-pass claim follows from them.
- Small timing samples in the public PR refer to e4, not this follow-up. The new paired actual-CLI fixture will record comparable startup and ping timings; no throughput or speedup claim.

All Go execution is in remote disposable Docker, not on the host. Tests use real CLI subprocesses, pipes and Unix sockets; no new helper weakens the EOF deadline.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** GPT-5-based Codex; exact runtime identifier unsure.

## What actually bothered you

The human asked: "next make 5-6 more strong contributions on projects which has very high frequency of merges in the world". This addresses an existing report and subsequent review feedback; it is not a claim that the human personally encountered or independently reviewed the bug.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container: awaiting the new full checks
- [ ] If this touches a hot path: new paired before/after timing evidence included
- [x] CHANGELOG.md untouched
- [x] AI-assisted? Disclosed above, with validation evidence
- [x] "Allow edits from maintainers" is enabled on the existing public PR

<!-- gate:ai=authored model=unsure intent=yes -->
