"""Tests-only review baseline; disposable Docker, no production modification."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

OLD = "0bf12b8be4b1fcd7d3ef14b82b2cc13845074b15"
TEST_SOURCE = "284e2e91df68c1a10d5694dd0f33fe9e0c639f91"
ROOT = pathlib.Path("/tmp/src")
PROOF = pathlib.Path("/proof")
TEST = "cmd/agent-deck/socket_wait_peer_test.go"
fixture = subprocess.check_output(["git", "show", TEST_SOURCE + ":" + TEST], cwd=ROOT)
subprocess.run(["git", "worktree", "add", "/tmp/source-old", OLD], cwd=ROOT, check=True)
source = pathlib.Path("/tmp/source-old")
(source / TEST).write_bytes(fixture)
subprocess.run(["go", "vet", "./..."], cwd=source, check=True)
subprocess.run(["go", "build", "-o", "/proof/agent-deck-old", "./cmd/agent-deck"], cwd=source, check=True)
subprocess.run(["go", "test", "-c", "-o", "/fixtures/claude-helper", "./cmd/agent-deck"], cwd=source, check=True)
folder = PROOF / "regression-old"
folder.mkdir()
command = ["go", "test", "-v", "-count=1", "-run", "^TestSessionSendSocketWait(PeerReply|HelpDescribesSharedBudget)$", "./cmd/agent-deck"]
start = time.monotonic()
with (folder / "output.log").open("wb") as output:
    result = subprocess.run(command, cwd=source, stdout=output, stderr=subprocess.STDOUT, timeout=180)
log = (folder / "output.log").read_text()
print(log, flush=True)
assert result.returncode == 1
for error in ["fixture launch failed", "did not publish", "did not receive", "[build failed]", "DATA RACE"]:
    assert error not in log, "invalid harness: " + error
for mode in ["idle", "fast", "dropped", "busy", "partial"]:
    assert "--- PASS: TestSessionSendSocketWaitPeerReply/" + mode in log
for mode in ["next-turn", "short-fast", "short-partial", "late-turn"]:
    assert "--- FAIL: TestSessionSendSocketWaitPeerReply/" + mode in log
assert "--- FAIL: TestSessionSendSocketWaitHelpDescribesSharedBudget" in log
receipt = {
    "command": command, "source_revision": OLD, "test_revision": TEST_SOURCE,
    "exit_code": 1, "timed_out": False, "duration_seconds": round(time.monotonic() - start, 3),
    "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
    "script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
    "fixtures": {TEST: hashlib.sha256(fixture).hexdigest()},
    "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
    "oracle_matched": True,
    "oracle_evidence": "Original five modes pass; later active turn, sub-second waits and obsolete help fail behaviorally.",
}
(folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
