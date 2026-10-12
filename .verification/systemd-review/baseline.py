"""Permissions regression on the actual published source, not old main."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

OLD = "086db80842d618de2531f6ba1b7f0773942c3757"
TEST_SOURCE = "f4780d047d7a5212584f0dbc5b6ce276b72f9305"
TEST = "internal/session/conductor_systemd_logs_test.go"
root = pathlib.Path("/tmp/src")
fixture = subprocess.check_output(["git", "show", TEST_SOURCE + ":" + TEST], cwd=root)
subprocess.run(["git", "worktree", "add", "/tmp/source-old", OLD], cwd=root, check=True)
source = pathlib.Path("/tmp/source-old")
(source / TEST).write_bytes(fixture)
subprocess.run(["go", "vet", "./..."], cwd=source, check=True)
subprocess.run(["go", "build", "-o", "/proof/agent-deck-old", "./cmd/agent-deck"], cwd=source, check=True)
folder = pathlib.Path("/proof/regression-old")
folder.mkdir()
command = ["go", "test", "-v", "-race", "-count=1", "-run", "^TestSystemdInstall", "./internal/session"]
started = time.monotonic()
with (folder / "output.log").open("wb") as output:
    result = subprocess.run(command, cwd=source, stdout=output, stderr=subprocess.STDOUT, timeout=300)
log = (folder / "output.log").read_text()
print(log, flush=True)
assert result.returncode == 1
assert log.count("new log directory must be owner-only, got 0755") == 5
assert "--- PASS: TestSystemdInstallCreatesLogDirectoryBeforeActivation/notifier/legacy" in log
assert "--- PASS: TestSystemdInstallCreatesLogDirectoryBeforeActivation/bridge/legacy" in log
assert "--- PASS: TestSystemdInstallRejectsLogFileBeforeActivation" in log
assert "--- PASS: TestSystemdInstallPreservesActivationError" in log
for invalid in ["[build failed]", "DATA RACE", "panic:", "activation not requested"]:
    assert invalid not in log
receipt = {
    "command": command, "source_revision": OLD, "test_revision": TEST_SOURCE,
    "exit_code": 1, "timed_out": False,
    "duration_seconds": round(time.monotonic() - started, 3),
    "script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    "fixtures": {TEST: hashlib.sha256(fixture).hexdigest()},
    "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
    "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 300},
    "oracle_matched": True,
    "oracle_evidence": "Five fresh log directories have0755; both existing0700 legacy directories and failure controls pass.",
}
(folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
