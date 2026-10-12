"""Paired source regression and actual binaries; disposable Docker only."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import time

BASE = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
FIXED = "dd24fcbbce280313c7db9200ee2268f478fd1b18"
root = pathlib.Path("/tmp/src")
proof = pathlib.Path("/proof")
fixture = root / "internal/session/conductor_systemd_logs_test.go"
command = ["go", "test", "-v", "-count=1", "-run", "^TestSystemdInstall", "./internal/session"]
script_hash = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()

for label, revision, expected in [("old", BASE, 1), ("fixed", FIXED, 0)]:
    source = pathlib.Path("/tmp/source-" + label)
    subprocess.run(["git", "worktree", "add", str(source), revision], cwd=root, check=True)
    binary = proof / ("agent-deck-" + label)
    subprocess.run(["go", "build", "-o", str(binary), "./cmd/agent-deck"], cwd=source, check=True)
    if label == "old":
        shutil.copy2(fixture, source / "internal/session/conductor_systemd_logs_test.go")
    assert hashlib.sha256((source / "internal/session/conductor_systemd_logs_test.go").read_bytes()).hexdigest() == fixture_hash
    subprocess.run(["go", "vet", "./..."], cwd=source, check=True)
    output_dir = proof / ("regression-" + label)
    output_dir.mkdir()
    start = time.monotonic()
    with (output_dir / "output.log").open("wb") as output:
        result = subprocess.run(command, cwd=source, stdout=output, stderr=subprocess.STDOUT, timeout=180)
    log = (output_dir / "output.log").read_text()
    print(log, flush=True)
    assert result.returncode == expected, f"unexpected {label} regression exit"
    assert "[build failed]" not in log and "DATA RACE" not in log
    assert "--- PASS: TestSystemdInstallPreservesActivationError" in log
    if label == "old":
        assert "log directory must exist before service activation" in log
        assert "expected actionable log directory creation error" in log
        evidence = "Log creation/blocked-file tests fail behaviorally; existing activation-error controls pass."
    else:
        assert "--- FAIL:" not in log
        for test in ["CreatesLogDirectoryBeforeActivation", "RejectsLogFileBeforeActivation", "PreservesActivationError"]:
            assert "--- PASS: TestSystemdInstall" + test in log
        evidence = "All log-directory preparation, blocked-file refusal and activation-error controls pass."
    receipt = {
        "command": command, "source_revision": revision, "test_revision": FIXED,
        "exit_code": result.returncode, "timed_out": False,
        "duration_seconds": round(time.monotonic() - start, 3),
        "output_sha256": hashlib.sha256((output_dir / "output.log").read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "script_sha256": script_hash, "fixtures": {"source_test": fixture_hash},
        "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
        "oracle_matched": True, "oracle_evidence": evidence,
    }
    (output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

with (proof / "source-guards.log").open("wb") as output:
    result = subprocess.run(
        ["go", "test", "-v", "-race", "-count=3", "-run", "TestSystemdInstall|Test.*(Systemd|TransitionNotifier|BridgeDaemon)", "./internal/session"],
        cwd="/tmp/source-fixed", stdout=output, stderr=subprocess.STDOUT, timeout=300,
    )
print((proof / "source-guards.log").read_text(), flush=True)
assert result.returncode == 0, "source guards failed"
