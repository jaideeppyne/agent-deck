"""Run frozen tests against unchanged source in a disposable build container."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

OLD = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
TEST_SOURCE = "6cf8eecc4b191c6b3a542ca9b7020d2381acd673"
TEST = "cmd/agent-deck/mcp_proxy_lifetime_test.go"
ROOT = pathlib.Path("/tmp/src")
PROOF = pathlib.Path("/proof")
fixture = subprocess.check_output(["git", "show", TEST_SOURCE + ":" + TEST], cwd=ROOT)
subprocess.run(["git", "worktree", "add", "/tmp/source-old", OLD], cwd=ROOT, check=True)
source = pathlib.Path("/tmp/source-old")
(source / TEST).write_bytes(fixture)
subprocess.run(["go", "vet", "./..."], cwd=source, check=True)
subprocess.run(["go", "build", "-o", "/proof/agent-deck-old", "./cmd/agent-deck"], cwd=source, check=True)
environment = dict(os.environ, AGENTDECK_TEST_CLI_BIN="/proof/agent-deck-old")
folder = PROOF / "regression-old"
folder.mkdir()
command = ["go", "test", "-v", "-race", "-count=1", "-run", "^TestMCPProxy", "./cmd/agent-deck"]
started = time.monotonic()
with (folder / "output.log").open("wb") as output:
    result = subprocess.run(command, cwd=source, env=environment, stdout=output,
                            stderr=subprocess.STDOUT, timeout=180)
log = (folder / "output.log").read_text()
print(log, flush=True)
assert result.returncode == 1
for invalid in ["[build failed]", "DATA RACE", "panic:", "cleanup did not finish", "parent fixture did not exit"]:
    assert invalid not in log, "invalid setup/control: " + invalid
for mode in ["connected", "dial-backoff", "backend-disconnected"]:
    assert "--- FAIL: TestMCPProxyStdinEOF/" + mode in log
assert "proxy still alive after stdin EOF" in log
assert "--- FAIL: TestMCPProxyParentExitWithOpenStdin" in log
assert "proxy kept backend open after parent exit with stdin open" in log
assert "--- PASS: TestMCPProxyBidirectionalFlow" in log
receipt = {
    "command": command, "source_revision": OLD, "test_revision": TEST_SOURCE,
    "exit_code": 1, "timed_out": False, "duration_seconds": round(time.monotonic() - started, 3),
    "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    "fixtures": {TEST: hashlib.sha256(fixture).hexdigest()},
    "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
    "oracle_matched": True,
    "oracle_evidence": "Three stdin EOF states leave client alive; parent-exit test leaves backend open with stdin deliberately held open.",
}
(folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
control = ["go", "test", "-tags=integration", "-race", "-v", "-count=3", "-run",
           "^TestSocketProxy_NoZombie_OnProcessExit$", "./internal/mcppool"]
with (PROOF / "pool-natural-exit-control.log").open("wb") as output:
    checked = subprocess.run(control, cwd=source, stdout=output, stderr=subprocess.STDOUT, timeout=180)
print((PROOF / "pool-natural-exit-control.log").read_text(), flush=True)
assert checked.returncode == 0, "current pool natural-exit reaper control failed"
