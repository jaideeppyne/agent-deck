"""Offline cross-profile launch reproduction; the paid tool is replaced only."""
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
home.mkdir(parents=True, exist_ok=True)
config_dir = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "agent-deck"
config_dir.mkdir(parents=True, exist_ok=True)
(config_dir / "config.toml").write_text(
    '[profiles.it.claude]\nconfig_dir = "~/.claude-it"\n'
    '[profiles.work.claude]\nconfig_dir = "~/.claude-work"\n')
for account in ("it", "work"):
    (home / (".claude-" + account)).mkdir()
shim_dir = home / "bin"
shim_dir.mkdir()
marker = home / "child-config-dir"
secure_marker = home / "child-secure-dir"
shim = shim_dir / "claude"
shim.write_text(
    '#!/bin/sh\nif [ "$1" = "--version" ]; then echo 2.0.0; exit 0; fi\n'
    'printf "%s" "$CLAUDE_SECURESTORAGE_CONFIG_DIR" > ' + shlex.quote(str(secure_marker)) + '\n' +
    'printf "%s" "$CLAUDE_CONFIG_DIR" > ' + shlex.quote(str(marker)) +
    '\nexec sleep 60\n')
shim.chmod(0o700)
os.environ.update(
    AGENTDECK_PROFILE="it", AGENTDECK_ACCOUNT="it",
    CLAUDE_CONFIG_DIR=str(home / ".claude-it"),
    CLAUDE_SECURESTORAGE_CONFIG_DIR=str(home / ".claude-it"),
    AGENTDECK_SKIP_UPDATE_CHECK="1",
    PATH=str(shim_dir) + os.pathsep + os.environ["PATH"])


def run(*args):
    result = subprocess.run([binary, "-p", "work", *args],
                            capture_output=True, text=True, timeout=20)
    print("COMMAND:", shlex.join(["agent-deck", "-p", "work", *args]), flush=True)
    print("EXIT:", result.returncode, flush=True)
    print("STDOUT:", result.stdout, flush=True)
    print("STDERR:", result.stderr, flush=True)
    return result


try:
    samples = []
    for index in range(28):
        started = time.perf_counter()
        version = subprocess.run([binary, "-p", "work", "version"],
                                 capture_output=True, text=True, timeout=10)
        if version.returncode != 0:
            raise RuntimeError("startup timing command failed")
        if index >= 3:
            samples.append((time.perf_counter() - started) * 1000)
    print("STARTUP_TIMING:", json.dumps({
        "command": "agent-deck -p work version", "warmups": 3, "samples": 25,
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3), "max_ms": round(max(samples), 3),
        "note": "single-runner smoke timing, not a general performance claim"}), flush=True)
    launch = run("launch", str(home), "--title", "cross-profile-repro",
                 "--cmd", "claude", "--no-parent", "--no-wait",
                 "--no-assert-done", "--json")
    if launch.returncode != 0:
        raise RuntimeError("launch failed; not the account-selection oracle")
    deadline = time.monotonic() + 10
    child_dir = ""
    while time.monotonic() < deadline:
        if marker.exists():
            child_dir = marker.read_text()
            if child_dir:
                break
        time.sleep(0.02)
    show = run("session", "show", "cross-profile-repro", "--json")
    if show.returncode != 0 or not child_dir:
        raise RuntimeError("no child environment or persisted session")
    state = json.loads(show.stdout)
    if state.get("profile") != "work":
        raise RuntimeError("fixture did not select target storage profile")
    account = state.get("account", "")
    secure_dir = secure_marker.read_text()
    print("CHILD_CONFIG_DIR:", child_dir, flush=True)
    print("CHILD_SECURESTORAGE_CONFIG_DIR:", repr(secure_dir), flush=True)
    print("PERSISTED_ACCOUNT:", repr(account), flush=True)
    if child_dir == str(home / ".claude-work") and account == "" and secure_dir == str(home / ".claude-it"):
        print("ORACLE: caller secure-storage selector leaked across profiles", flush=True)
        code = 1
    elif child_dir == str(home / ".claude-work") and account == "" and secure_dir == "":
        print("ORACLE: cross-profile launch used only target profile selectors", flush=True)
        code = 0
    else:
        raise RuntimeError("unexpected selection; not a proven red or green oracle")
finally:
    run("session", "stop", "cross-profile-repro")
raise SystemExit(code)
