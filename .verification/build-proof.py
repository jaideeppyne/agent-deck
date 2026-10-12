"""Fork-only paired regression/build evidence; run inside disposable Docker."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

OLD = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
FIXED = "0bf12b8be4b1fcd7d3ef14b82b2cc13845074b15"
ROOT = pathlib.Path("/tmp/src")
PROOF = pathlib.Path("/proof")
FIXTURES = pathlib.Path("/fixtures")
TEST = "cmd/agent-deck/socket_wait_peer_test.go"
COMMAND = ["go", "test", "-v", "-count=1", "-run", "^TestSessionSendSocketWaitPeerReply$", "./cmd/agent-deck"]


def checked(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


fixture = subprocess.check_output(["git", "show", FIXED + ":" + TEST], cwd=ROOT)
script_digest = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
for label, revision in (("old", OLD), ("fixed", FIXED)):
    tree = pathlib.Path("/tmp") / ("source-" + label)
    checked(["git", "worktree", "add", str(tree), revision], ROOT)
    if label == "old":
        (tree / TEST).write_bytes(fixture)
    checked(["go", "vet", "./..."], tree)
    checked(["go", "build", "-o", str(PROOF / ("agent-deck-" + label)), "./cmd/agent-deck"], tree)
    if label == "old":
        checked(["go", "test", "-c", "-o", str(FIXTURES / "claude-helper"), "./cmd/agent-deck"], tree)
    folder = PROOF / ("regression-" + label)
    folder.mkdir()
    start = time.monotonic()
    with (folder / "output.log").open("wb") as output:
        result = subprocess.run(COMMAND, cwd=tree, stdout=output, stderr=subprocess.STDOUT, timeout=180)
    log = (folder / "output.log").read_text()
    print(log, flush=True)
    for error in ("fixture launch failed", "did not publish", "did not receive", "build failed", "DATA RACE"):
        if error in log:
            raise RuntimeError("invalid harness: " + error)
    modes = ("idle", "fast", "dropped", "busy", "partial")
    if label == "old":
        assert result.returncode == 1 and "turn identity not established" in log
        assert "socket --wait did not emit one JSON result" in log
        for mode in modes:
            verdict = "PASS" if mode in ("dropped", "partial") else "FAIL"
            assert f"--- {verdict}: TestSessionSendSocketWaitPeerReply/{mode}" in log
        evidence = "idle/fast: turn identity not established; busy: no JSON result; dropped/partial refusal PASS"
    else:
        assert result.returncode == 0
        for mode in modes:
            assert f"--- PASS: TestSessionSendSocketWaitPeerReply/{mode}" in log
        evidence = "idle/fast/dropped/busy/partial all PASS; real socket CLI output inspected separately"
    receipt = {
        "command": COMMAND, "source_revision": revision,
        "exit_code": result.returncode, "timed_out": False,
        "duration_seconds": round(time.monotonic() - start, 3),
        "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
        "script_sha256": script_digest,
        "fixtures": {TEST: hashlib.sha256(fixture).hexdigest()},
        "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
        "oracle_matched": True, "oracle_evidence": evidence,
    }
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

with (PROOF / "source-guards.log").open("wb") as output:
    subprocess.run(["go", "test", "-race", "-v", "-count=3", "-run",
                    "^Test(AwaitObservedTurn|ObservedTurn|SocketWaitObservedReply|Issue1978|Issue2089|Issue2399)",
                    "./internal/session", "./cmd/agent-deck"],
                   cwd="/tmp/source-fixed", stdout=output, stderr=subprocess.STDOUT,
                   timeout=600, check=True)
