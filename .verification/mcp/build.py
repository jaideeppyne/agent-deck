"""Frozen paired client-lifetime regression; remote disposable Docker only."""
import hashlib
import json
import os
import pathlib
import subprocess
import time

BASE = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
FIXED = "e4d53b07234d7826c4d670747624d7988544f2c6"
TESTS = "a99fcdab974525e530265060bd4379b152285536"
ROOT = pathlib.Path("/tmp/src")
PROOF = pathlib.Path("/proof")
paths = ["cmd/agent-deck/mcp_proxy_lifetime_test.go", "internal/mcppool/respawn_dedup_test.go"]
fixtures = {p: subprocess.check_output(["git", "show", TESTS + ":" + p], cwd=ROOT) for p in paths}
hashes = {p: hashlib.sha256(data).hexdigest() for p, data in fixtures.items()}
script_hash = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
command = ["go", "test", "-v", "-race", "-count=1", "-run", "^TestMCPProxy", "./cmd/agent-deck"]

for label, revision, expected in [("old", BASE, 1), ("fixed", FIXED, 0)]:
    source = pathlib.Path("/tmp/source-" + label)
    subprocess.run(["git", "worktree", "add", str(source), revision], cwd=ROOT, check=True)
    for path, data in fixtures.items():
        if label == "old":
            (source / path).write_bytes(data)
        assert hashlib.sha256((source / path).read_bytes()).hexdigest() == hashes[path]
    subprocess.run(["go", "vet", "./..."], cwd=source, check=True)
    binary = PROOF / ("agent-deck-" + label)
    subprocess.run(["go", "build", "-o", str(binary), "./cmd/agent-deck"], cwd=source, check=True)
    env = dict(os.environ, AGENTDECK_TEST_CLI_BIN=str(binary))
    folder = PROOF / ("regression-" + label)
    folder.mkdir()
    started = time.monotonic()
    with (folder / "output.log").open("wb") as output:
        result = subprocess.run(command, cwd=source, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=180)
    log = (folder / "output.log").read_text()
    print(log, flush=True)
    assert result.returncode == expected
    for invalid in ["[build failed]", "DATA RACE", "panic:", "cleanup did not finish",
                    "parent fixture did not exit", "fixture did not exercise", "fixture stdin writer did not stop"]:
        assert invalid not in log, "invalid setup/control: " + invalid
    assert "--- PASS: TestMCPProxyBidirectionalFlow" in log
    if label == "old":
        for mode in ["connected", "dial-backoff", "backend-disconnected"]:
            assert "--- FAIL: TestMCPProxyStdinEOF/" + mode in log
        for mode in ["dial-backoff", "blocked-backend"]:
            assert "--- FAIL: TestMCPProxyEOFWithInputBackpressure/" + mode in log
        assert "--- FAIL: TestMCPProxyEOFWithOutputBackpressure" in log
        assert "--- FAIL: TestMCPProxyReconnectKeepsInput" in log
        assert "proxy still alive after stdin EOF" in log
        assert "proxy kept backend open after parent exit with stdin open" in log
        evidence = "Healthy traffic passes; EOF/backpressure, parent lifetime and reconnect input regressions fail behaviorally."
    else:
        assert "--- FAIL:" not in log
        for test in ["StdinEOF", "EOFWithInputBackpressure", "EOFWithOutputBackpressure",
                     "ReconnectKeepsInput", "ParentExitWithOpenStdin"]:
            assert "--- PASS: TestMCPProxy" + test in log
        evidence = "Same frozen real-CLI tests pass for healthy flow, reconnect, parent death and EOF with both input/output pressure."
    receipt = {
        "command": command, "source_revision": revision, "test_revision": TESTS,
        "exit_code": result.returncode, "timed_out": False,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output_sha256": hashlib.sha256((folder / "output.log").read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "script_sha256": script_hash, "fixtures": hashes,
        "experiment": {"image_id": os.environ["PROOF_IMAGE_ID"], "timeout_seconds": 180},
        "oracle_matched": True, "oracle_evidence": evidence,
    }
    (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")

env = dict(os.environ, AGENTDECK_TEST_CLI_BIN=str(PROOF / "agent-deck-fixed"))
guards = [
    (["go", "test", "-v", "-race", "-count=3", "-run", "^TestMCPProxy", "./cmd/agent-deck"], "source-guards.log"),
    (["go", "test", "-tags=integration", "-race", "-v", "-count=3", "-run",
      "^TestSocketProxy_NoZombie_OnProcessExit$|^TestPool_RestartLoop_ProducesOneChild$", "./internal/mcppool"], "pool-reaper-control.log"),
]
for cmd, name in guards:
    with (PROOF / name).open("wb") as output:
        result = subprocess.run(cmd, cwd="/tmp/source-fixed", env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=300)
    print((PROOF / name).read_text(), flush=True)
    assert result.returncode == 0, name

with (PROOF / "cross-build.log").open("wb") as output:
    for target in ["darwin", "linux"]:
        cross_env = dict(os.environ, GOOS=target, GOARCH="arm64", CGO_ENABLED="0")
        subprocess.run(["go", "build", "-o", "/tmp/agent-deck-" + target, "./cmd/agent-deck"],
                       cwd="/tmp/source-fixed", env=cross_env, stdout=output,
                       stderr=subprocess.STDOUT, check=True, timeout=300)
        output.write(("PASS cross-build " + target + "/arm64\n").encode())
