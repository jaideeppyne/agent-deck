"""Fork-only paired regression/build evidence; run inside disposable Docker."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

OLD = "0bf12b8be4b1fcd7d3ef14b82b2cc13845074b15"
FIXED = "0df60596e4120a832336b361e166d7f624443225"
TEST_SOURCE = "a6cc82bd4944dd6bbe4fc9053019b389b3c8c2fa"
ROOT = pathlib.Path("/tmp/src")
PROOF = pathlib.Path("/proof")
FIXTURES = pathlib.Path("/fixtures")
TEST = "cmd/agent-deck/socket_wait_peer_test.go"
COMMAND = ["go", "test", "-v", "-count=1", "-run", "^TestSessionSendSocketWait(PeerReply|HelpDescribesSharedBudget)$|^TestSocketWaitTranscriptPollDeadline$", "./cmd/agent-deck", "./internal/session"]


def checked(args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


fixtures = {path: subprocess.check_output(["git", "show", TEST_SOURCE + ":" + path], cwd=ROOT)
            for path in [TEST, "internal/session/socket_wait_deadline_test.go"]}
script_digest = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
for label, revision in (("old", OLD), ("fixed", FIXED)):
    tree = pathlib.Path("/tmp") / ("source-" + label)
    checked(["git", "worktree", "add", str(tree), revision], ROOT)
    if label == "old":
        for path, fixture in fixtures.items():
            (tree / path).write_bytes(fixture)
    for path, fixture in fixtures.items():
        assert (tree / path).read_bytes() == fixture, "source fixture drift"
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
    modes = ("idle", "fast", "dropped", "busy", "partial", "next-turn", "short-fast", "short-partial", "late-turn")
    if label == "old":
        assert result.returncode == 1 and "timeout waiting for completion" in log
        assert "socket wait exceeded its shared 300ms budget" in log
        for mode in modes:
            verdict = "FAIL" if mode in ("next-turn", "short-fast", "short-partial", "late-turn") else "PASS"
            assert f"--- {verdict}: TestSessionSendSocketWaitPeerReply/{mode}" in log
        assert "--- FAIL: TestSessionSendSocketWaitHelpDescribesSharedBudget" in log
        for phase in ["observed-turn", "turn-response"]:
            assert "--- FAIL: TestSocketWaitTranscriptPollDeadline/" + phase in log
        evidence = "Original five modes pass; later active turn, sub-second waits, obsolete help and both transcript poll deadlines fail behaviorally."
    else:
        assert result.returncode == 0
        for mode in modes:
            assert f"--- PASS: TestSessionSendSocketWaitPeerReply/{mode}" in log
        assert "--- PASS: TestSessionSendSocketWaitHelpDescribesSharedBudget" in log
        assert "--- PASS: TestSocketWaitTranscriptPollDeadline" in log
        evidence = "All nine real-CLI modes, help and both transcript poll deadlines PASS; fixed guard/refusal assertions unchanged."
    receipt = {
        "command": COMMAND, "source_revision": revision,
        "exit_code": result.returncode, "timed_out": False,
        "duration_seconds": round(time.monotonic() - start, 3),
        "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
        "script_sha256": script_digest,
        "fixtures": {path: hashlib.sha256(fixture).hexdigest() for path, fixture in fixtures.items()},
        "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
        "oracle_matched": True, "oracle_evidence": evidence,
    }
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

with (PROOF / "source-guards.log").open("wb") as output:
    subprocess.run(["go", "test", "-race", "-v", "-count=3", "-run",
                    "^Test(AwaitObservedTurn|ObservedTurn|SocketWaitObservedReply|SocketWaitTranscriptPollDeadline|Issue1978|Issue2089|Issue2399)",
                    "./internal/session", "./cmd/agent-deck"],
                   cwd="/tmp/source-fixed", stdout=output, stderr=subprocess.STDOUT,
                   timeout=600, check=True)
