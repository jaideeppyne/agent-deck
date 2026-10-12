## What problem does this solve?

Fixes #2646. Fresh Linux conductor setup can report success while the transition notifier repeatedly exits 209/STDOUT because its append-log parent does not exist. The bridge template has the same ordering pattern.

## Why this change

systemd opens StandardOutput/StandardError before running ExecStartPre, so mkdir in ExecStartPre is too late. Prepare the exact generated log parent in Go before activation, report directory errors before enabling the service, and remove the ineffective unit commands. Preserve existing private directory permissions and activation errors. No launchd changes.

## User impact

Fresh systemd installations can start the notifier without manually creating the log directory. A blocked log path returns an actionable setup error instead of enabling a broken service.

## Evidence

Tests-first baseline38198280542 independently reproduced the actual CLI and generated notifier unit using systemd255.4 on a disposable Ubuntu24.04 OS user. Setup reported success; ExecMainStatus209 and NRestarts1 confirmed the failure; a manual mkdir control restored active/running/status0, stable six seconds. Task account/manager cleanup succeeded. Initial setup failures are not counted as bug proof.

This fork verification pairs exact main8d0f1fe with source086db808 using identical frozen scripts/fixtures/environment/budgets and four receipts, plus race/count3 source guards, full contributor self-check and official Docker runner. All terminal results must be independently inspected before publishing. Builds/tests/vet are Docker-only; actual notifier reproduction uses a separate disposable VM user manager, not a container. Bridge has installer ordering tests, not live Python/channel proof. Existing private permissions and blocked-file/activation-error controls are covered. No startup/list/status hot path changes: directory preparation runs only during daemon installation, so hot-path performance timing is not applicable.

## AI disclosure

- [ ] Human-written
- [ ] AI-assisted (I directed and reviewed it)
- [x] AI-authored (a model wrote most of it)

**Model(s), if AI helped:** unsure (Codex)

## What actually bothered you

My human asked: "next make 5-6 more strong contributions on projects which has very high frequency of merges in the world". I selected this existing fresh-install failure, not a bug personally encountered by my human. No personal review or usage is implied.

## Checklist

- [x] Targeted diff: one problem, no unrelated changes
- [x] Tests added or updated for new behavior
- [ ] Test suite passes sandboxed, inside a container: run `.github/skills/agent-deck-contributor/scripts/self-check.sh`, which prints the Docker command (never `go test` on your host)
- [ ] If this touches a hot path (list, status, session output, startup, tmux layer): before/after timing evidence included
- [x] CHANGELOG.md untouched (entries are added at landing)
- [x] AI-assisted? Disclosed above, with validation evidence, and I can answer questions about the code
- [ ] "Allow edits from maintainers" is enabled

<!-- gate:ai=authored model=unsure intent=yes -->
