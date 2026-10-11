"""Fork-only evidence capture; never part of the upstream contribution."""
import argparse
import hashlib
import json
import pathlib
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def regression(args):
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    command = ["go", "test", "-v", "-count=1", "-run",
               "TestSwitchSharedProjectsStore|TestMigrateSharedProjectsStore(IsNoOp|Identity)$|TestSessionSwitchAccount_SharedProjectsStore$|TestHomeSwitchAccountSharedProjectsStore$",
               "./internal/session", "./cmd/agent-deck", "./internal/ui"]
    tests = ["internal/session/shared_projects_store_test.go",
             "cmd/agent-deck/shared_projects_store_test.go",
             "internal/ui/shared_projects_store_test.go"]
    receipt = {"command": command, "script_sha256": digest(pathlib.Path(__file__)),
               "fixtures": {p: digest(pathlib.Path(p)) for p in tests},
               "experiment": {"image_id": args.image, "timeout_seconds": 180},
               "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()}
    with (out / "output.log").open("wb") as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            receipt.update(exit_code=result.returncode, timed_out=False)
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=None, timed_out=True)
    write(out / "receipt.json", receipt | {"output_sha256": digest(out / "output.log")})
    print((out / "output.log").read_text())
    return 2 if receipt["timed_out"] else receipt["exit_code"]


def finalize(args):
    root = pathlib.Path(args.out)
    checks = {
        "repro-old": (1, "ORACLE: shared-store refusal reproduced"),
        "repro-fixed": (0, "ORACLE: shared-store account switch succeeded without transcript changes"),
        "regression-old": (1, "already-shared store refused"),
        "regression-fixed": (0, "--- PASS: TestSessionSwitchAccount_SharedProjectsStore"),
    }
    for name, (expected, evidence) in checks.items():
        path = root / name / "receipt.json"
        receipt = json.loads(path.read_text())
        log = (path.parent / "output.log").read_text()
        if receipt["exit_code"] != expected or receipt["timed_out"] or evidence not in log:
            raise ValueError(f"unverified oracle: {name}")
        if receipt["output_sha256"] != digest(path.parent / "output.log"):
            raise ValueError(f"output digest mismatch: {name}")
        if name.startswith("regression") and "build failed" in log:
            raise ValueError(f"compilation failure is not a red test: {name}")
        write(path, receipt | {"oracle_matched": True, "oracle_evidence": evidence,
                              "oracle_review": "automated text check; independent AI inspection follows before publication"})
    write(root / "result.json", {
        "schema_version": 1, "candidate_id": "agent-deck-2639", "status": "fixed",
        "oracle": "Shared-store account switch succeeds without changing transcripts; separate-store symlink refusal remains nonzero.",
        "affected_revision": "036915808f43363ca9d54e77ce1fc0706b82029c",
        "fixed_revision": "207ab9705178fba8df20b89717f90ccb9a34f00e",
        "reproduction": {"old_receipt": "repro-old/receipt.json", "fixed_receipt": "repro-fixed/receipt.json"},
        "regression": {"test": "TestSessionSwitchAccount_SharedProjectsStore and session shared-store safety cases",
                       "old_receipt": "regression-old/receipt.json", "fixed_receipt": "regression-fixed/receipt.json"},
    })
    return 0


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("mode", choices=["regression", "finalize"])
parser.add_argument("--out", required=True)
parser.add_argument("--image")
args = parser.parse_args()
raise SystemExit(regression(args) if args.mode == "regression" else finalize(args))
