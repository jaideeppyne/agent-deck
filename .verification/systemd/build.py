"""Tests-first baseline; only run in the disposable build container."""
import hashlib
import json
import pathlib
import subprocess
import time

SOURCE = "0aaa19408cd64b7f7a9a9f95b8af0b811bde54d4"
BASE = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
root = pathlib.Path("/tmp/src")
proof = pathlib.Path("/proof")
subprocess.run(["git", "worktree", "add", "/tmp/source", SOURCE], cwd=root, check=True)
subprocess.run(["go", "vet", "./..."], cwd="/tmp/source", check=True)
subprocess.run(["go", "build", "-o", "/proof/agent-deck-old", "./cmd/agent-deck"], cwd="/tmp/source", check=True)
command = ["go", "test", "-v", "-count=1", "-run", "^TestSystemdInstall", "./internal/session"]
start = time.monotonic()
with (proof / "regression-old.log").open("wb") as output:
    result = subprocess.run(command, cwd="/tmp/source", stdout=output, stderr=subprocess.STDOUT, timeout=180)
log = (proof / "regression-old.log").read_text()
print(log, flush=True)
assert result.returncode == 1 and "log directory must exist before service activation" in log
assert "expected actionable log directory creation error" in log
assert "--- PASS: TestSystemdInstallPreservesActivationError" in log
assert "[build failed]" not in log and "DATA RACE" not in log
receipt = {
    "command": command, "source_revision": BASE, "test_revision": SOURCE,
    "exit_code": result.returncode, "timed_out": False,
    "duration_seconds": round(time.monotonic() - start, 3),
    "output_sha256": hashlib.sha256((proof / "regression-old.log").read_bytes()).hexdigest(),
    "oracle_matched": True,
    "oracle_evidence": "Log creation/blocked-file tests fail behaviorally; pre-existing activation error controls pass.",
}
(proof / "regression-old.json").write_text(json.dumps(receipt, indent=2) + "\n")
