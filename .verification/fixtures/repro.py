"""Actual CLI socket-wait reproduction; only external Claude is synthetic."""
import json
import os
import pathlib
import shlex
import statistics
import subprocess
import sys
import time

binary = sys.argv[1]
home = pathlib.Path(os.environ["HOME"])
config = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "agent-deck"
config.mkdir(parents=True)
(config / "config.toml").write_text("[claude]\nsend_transport = 'auto'\n")
shimdir = home / "bin"
shimdir.mkdir()
shim = shimdir / "claude"
shim.write_text('#!/bin/sh\nexec "$SOCKET_WAIT_TEST_BINARY" -test.run=^TestSocketWaitClaudeFixture$ -- "$@"\n')
shim.chmod(0o700)
os.environ.update(PATH=str(shimdir) + os.pathsep + os.environ["PATH"],
                  SOCKET_WAIT_TEST_BINARY="/fixtures/claude-helper",
                  SOCKET_WAIT_FIXTURE="idle", AGENT_DECK_TASK6_HELPER_PROCESS="1",
                  AGENTDECK_PROFILE="socket-repro", AGENTDECK_SKIP_UPDATE_CHECK="1")


def run(*args):
    started = time.monotonic()
    result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=25)
    print("COMMAND:", shlex.join(["agent-deck", *args]), flush=True)
    print("DURATION_SECONDS:", round(time.monotonic() - started, 3), flush=True)
    print("EXIT:", result.returncode, flush=True)
    print("STDOUT:", result.stdout, flush=True)
    print("STDERR:", result.stderr, flush=True)
    return result


code = 2
try:
    samples = []
    for index in range(28):
        started = time.perf_counter()
        version = subprocess.run([binary, "version"], capture_output=True, timeout=10)
        if version.returncode:
            raise RuntimeError("startup timing setup failed")
        if index >= 3:
            samples.append((time.perf_counter() - started) * 1000)
    print("STARTUP_TIMING:", json.dumps({"warmups": 3, "samples": 25,
          "median_ms": round(statistics.median(samples), 3),
          "note": "single-runner version smoke timing, not general performance"}), flush=True)
    launch = run("launch", str(home), "--title", "socket-repro", "--cmd", "claude",
                 "--no-parent", "--no-wait", "--no-assert-done", "--json")
    if launch.returncode:
        raise RuntimeError("fixture launch failed")
    deadline = time.monotonic() + 10
    while not (home / "socket-wait-ready").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("fixture socket record never became ready")
        time.sleep(0.02)
    result = run("session", "send", "socket-repro", "--no-tag", "--no-wait",
                 "--wait", "--timeout", "5s", "--json", "reply ok")
    frame = json.loads((home / "socket-wait-frame").read_text())
    if frame.get("type") != "user" or frame.get("message", {}).get("content") != "reply ok":
        raise RuntimeError("the fixture did not receive the actual socket message")
    transcripts = list((home / ".claude" / "projects").glob("*/*.jsonl"))
    rows = [json.loads(line) for path in transcripts for line in path.read_text().splitlines()]
    reply = any(row.get("uuid") == "peer-reply" for row in rows)
    wrapped = any(row.get("origin", {}).get("kind") == "peer" and row.get("isMeta") for row in rows)
    print("SOCKET_FRAME_RECEIVED:", True, flush=True)
    print("WRAPPED_PEER_TURN_AND_REPLY:", wrapped and reply, flush=True)
    if not wrapped or not reply:
        raise RuntimeError("fixture did not write the expected peer reply")
    payload = json.loads(result.stdout)
    if result.returncode == 1 and "turn identity not established" in payload.get("error", ""):
        print("ORACLE: socket wait rejected a completed wrapped peer reply", flush=True)
        code = 1
    elif (result.returncode == 0 and payload.get("content") == "PEER REPLY"
          and payload.get("transport") == "socket" and payload.get("verified") is False
          and payload.get("wait_outcome") == "observed_not_correlated"
          and payload.get("submitted") is False and payload.get("acknowledged") is False):
        print("ORACLE: socket wait returned the fresh peer reply without correlation claims", flush=True)
        code = 0
    else:
        raise RuntimeError("unexpected outcome; neither defect nor healthy oracle")
finally:
    run("session", "stop", "socket-repro")
raise SystemExit(code)
