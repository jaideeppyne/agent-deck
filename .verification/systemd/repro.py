"""Real CLI and generated unit in a task-owned disposable Linux user manager."""
import hashlib
import json
import os
import pathlib
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import time

UNIT = "agent-deck-transition-notifier.service"
root = pathlib.Path(tempfile.mkdtemp(prefix="ad2646-"))
root.chmod(0o755)
name = "ad2646-" + root.name.removeprefix("ad2646-")
home = root / "home"
binary = root / "agent-deck"
source_binary = pathlib.Path(sys.argv[1]).resolve()
proof = pathlib.Path(sys.argv[2]).resolve()
source_revision = sys.argv[3]
vm_image = os.environ["PROOF_VM_IMAGE"]
proof.mkdir(parents=True, exist_ok=True)
shutil.copy2(source_binary, binary)
binary.chmod(0o755)
lines = []
created = False
lingering = False
uid = None
started = time.monotonic()
verdict = 2


def run(args, check=True, timeout=30):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        lines.append("TIMED_OUT: " + " ".join(map(str, args)) + "\n" + stdout + stderr)
        raise
    result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    lines.append("$ " + " ".join(map(str, args)) + "\n" + result.stdout + f"exit={result.returncode}\n")
    if result.stderr:
        lines.append("stderr: " + result.stderr + "\n")
    if check and result.returncode:
        raise RuntimeError(f"setup/command failure: {args[0]} exit={result.returncode}")
    return result


def user(args, check=True):
    env = ["PATH=" + str(root) + ":/usr/bin:/bin", "HOME=" + str(home),
           "USER=" + name, "LOGNAME=" + name, "XDG_RUNTIME_DIR=/run/user/" + str(uid),
           "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/" + str(uid) + "/bus",
           "AGENTDECK_SKIP_UPDATE_CHECK=1", "LC_ALL=C.UTF-8"]
    return run(["sudo", "runuser", "-u", name, "--", "env", "-i", *env, *map(str, args)], check)


def status():
    result = user(["systemctl", "--user", "show", UNIT, "--property=ActiveState,SubState,ExecMainStatus,NRestarts"])
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def healthy():
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = status()
        if current.get("ActiveState") == "active" and current.get("SubState") == "running" and current.get("ExecMainStatus") == "0":
            time.sleep(6)
            again = status()
            return again.get("ActiveState") == "active" and again.get("SubState") == "running" and again.get("ExecMainStatus") == "0"
        time.sleep(0.3)
    return False


try:
    run(["systemctl", "--version"])
    run(["sudo", "useradd", "--no-log-init", "--no-create-home", "--no-user-group", "--gid", "users",
         "--key", "CREATE_MAIL_SPOOL=no", "--key", "SUB_UID_COUNT=0", "--key", "SUB_GID_COUNT=0",
         "--home-dir", str(home), "--shell", "/bin/sh", name])
    created = True
    uid = int(run(["id", "-u", name]).stdout.strip())
    home.mkdir(mode=0o700)
    os.chown(home, uid, pwd.getpwnam(name).pw_gid)
    run(["sudo", "loginctl", "enable-linger", name])
    lingering = True
    run(["sudo", "systemctl", "start", f"user@{uid}.service"])
    deadline = time.monotonic() + 15
    while not pathlib.Path(f"/run/user/{uid}/bus").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("disposable user bus did not become available")
        time.sleep(0.2)
    log_dir = home / ".local/share/agent-deck/logs"
    assert not log_dir.exists(), "fixture must start without log directory"
    command = [binary, "conductor", "setup", "probe", "--description", "isolated systemd reproduction", "--no-heartbeat", "--json"]
    setup = user(command)
    data = json.loads(setup.stdout)
    assert data["success"] is True and data.get("notifier_daemon"), "notifier installation did not complete"
    unit = user(["systemctl", "--user", "cat", UNIT]).stdout
    assert "StandardOutput=append:" + str(log_dir / "transition-notifier.log") in unit
    if log_dir.is_dir() and healthy():
        lines.append("ORACLE: actual CLI created log directory and generated notifier remains active\n")
        verdict = 0
    else:
        deadline = time.monotonic() + 15
        observed = None
        while time.monotonic() < deadline:
            current = status()
            if current.get("ExecMainStatus") == "209" and int(current.get("NRestarts", "0")) >= 1:
                observed = current
                break
            time.sleep(0.3)
        user(["journalctl", "--user", "-u", UNIT, "--no-pager", "-n", "30"], check=False)
        if log_dir.exists() or not observed or 'ExecStartPre=-/bin/mkdir -p "' not in unit:
            raise RuntimeError("expected missing-log-dir209 restart signature not observed")
        user(["mkdir", "-p", log_dir])
        user(["systemctl", "--user", "reset-failed", UNIT])
        user(["systemctl", "--user", "restart", UNIT])
        if not healthy():
            raise RuntimeError("manual mkdir control did not restore healthy notifier")
        lines.append("ORACLE: setup reported success; missing log directory caused209/STDOUT and repeated restarts; manual mkdir control restored active notifier\n")
        verdict = 1
except Exception as error:
    lines.append("HARNESS_ERROR: " + repr(error) + "\n")
    verdict = 2
finally:
    try:
        # Account creation can partially succeed before its subprocess fails.
        try:
            account = pwd.getpwnam(name)
        except KeyError:
            account = None
        if account is not None:
            if account.pw_dir != str(home):
                raise RuntimeError("refusing cleanup of an unrelated account")
            created = True
            uid = account.pw_uid
        if uid is not None:
            user(["systemctl", "--user", "disable", "--now", UNIT], check=False)
            run(["sudo", "systemctl", "stop", f"user@{uid}.service"])
        if lingering:
            run(["sudo", "loginctl", "disable-linger", name])
        if created:
            run(["sudo", "userdel", "--remove", name])
            if run(["id", name], check=False).returncode == 0:
                raise RuntimeError("disposable user survived cleanup")
        shutil.rmtree(root)
    except Exception as error:
        lines.append("CLEANUP_ERROR: " + repr(error) + "\n")
        verdict = 2
    output = "".join(lines)
    print(output, flush=True)
    (proof / "output.log").write_text(output)
    receipt = {
        "command": ["python3", ".verification/systemd/repro.py", "agent-deck", "receipt"],
        "exit_code": verdict, "timed_out": "TIMED_OUT:" in output,
        "source_revision": source_revision,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output_sha256": hashlib.sha256((proof / "output.log").read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(source_binary.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
        "experiment": {"image_id": vm_image, "platform": "disposable GitHub Ubuntu VM user manager", "timeout_seconds": 120},
        "fixtures": {"setup": hashlib.sha256(b"fresh OS user without skeleton/mail/subids, private empty HOME, no log directory, no remote channels, heartbeat disabled").hexdigest()},
        "oracle_matched": verdict in (0, 1),
        "oracle_evidence": next((line.strip() for line in lines if line.startswith("ORACLE:")), ""),
    }
    (proof / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
sys.exit(verdict)
