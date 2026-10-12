## What problem does this solve?

Addresses the orphan MCP proxy client portion of #2649: stdin EOF reconnects instead of exiting, parent death with inherited stdin leaves clients running, and backend reconnects can leave competing stdin readers.

## Why this change

Use one bounded stdin reader across socket generations, cancellable dial/backoff, and a client-lifetime context. Detect parent PID changes and pipe hangup even when input is backpressured; close connections on cancellation. Retain backend reconnects without replaying partially written requests or killing shared pool servers. No new dependency: `x/sys/unix` already exists. The fallback relies on reader EOF and parent changes outside Linux/macOS.

The 506 changed lines primarily contain an actual subprocess/socket fixture and lifetime/reconnect/backpressure regression matrix. Splitting those tests from their small lifecycle implementation would leave this behavior unguarded; there is no unrelated pool refactor. The existing reaper is only tested, not changed.

## User impact

Client stdin closing or its parent exiting ends that proxy. Backend disconnects with a live client still reconnect. EOF means terminal client shutdown, not guaranteed draining of queued requests/responses. This does not claim a measured memory reduction or a fix to every historical zombie report.

## Evidence

Tests-first baseline run38271154874 on unchanged main8d0f1fe: healthy traffic passes; three EOF states, three backpressure cases and parent death leave clients alive; reconnect loses request1. Current pool reaper passes natural-exit and five-restart controls, repeated three times. Actual isolated CLI reconnects nine times in one second after EOF. An earlier parent fixture used too-short helper-exit allowance under race runtime; it was corrected before this valid baseline, without weakening the proxy deadline.

Paired fixed four receipts, race repeats, cross-builds, full contributor self-check and official five-stage Docker CI are still pending. Do not publish until independently inspected. The same actual-CLI fixture on both revisions also records startup-to-first-reply and 25 ping roundtrip timings after five warmups; this is a small smoke measurement, not a throughput or macOS performance claim. The built-in revert check may warn because reverting the new helper files makes the program fail to compile; frozen tests overlay unchanged compilable main for behavioral red evidence instead. Linux runtime evidence only; Darwin arm64 cross-build does not establish macOS runtime behavior. All Go execution is in remote disposable Docker.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** GPT-5-based Codex; exact runtime identifier unsure.

## What actually bothered you

The human asked: "next make 5-6 more strong contributions on projects which has very high frequency of merges in the world". This contribution addresses an existing report, not a claim that the author personally encountered or independently reviewed the bug.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container
- [ ] If this touches a hot path: before/after timing evidence included
- [x] CHANGELOG.md untouched
- [x] AI-assisted? Disclosed above, with validation evidence
- [ ] "Allow edits from maintainers" is enabled

<!-- gate:ai=authored model=unsure intent=yes -->
