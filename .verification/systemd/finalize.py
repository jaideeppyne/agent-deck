"""Check paired receipts before exposing them to the contributor self-check."""
import hashlib
import json
import pathlib

BASE = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
FIXED = "086db80842d618de2531f6ba1b7f0773942c3757"
proof = pathlib.Path("proof")
for kind in ["repro", "regression"]:
    receipts = []
    for label, revision, expected in [("old", BASE, 1), ("fixed", FIXED, 0)]:
        folder = proof / (kind + "-" + label)
        receipt = json.loads((folder / "receipt.json").read_text())
        output = (folder / "output.log").read_bytes()
        assert receipt["source_revision"] == revision
        assert receipt["exit_code"] == expected and not receipt["timed_out"]
        assert receipt["output_sha256"] == hashlib.sha256(output).hexdigest()
        assert receipt["oracle_matched"] and receipt["oracle_evidence"]
        assert b"HARNESS_ERROR:" not in output and b"CLEANUP_ERROR:" not in output
        receipts.append(receipt)
    for key in ["experiment", "fixtures", "script_sha256"]:
        assert receipts[0][key] == receipts[1][key], (kind, key)
report = {
    "schema_version": 1, "candidate_id": "agent-deck-2646", "status": "fixed",
    "issue": "https://github.com/asheshgoplani/agent-deck/issues/2646",
    "oracle": "Actual CLI setup reports success but systemd cannot open absent append-log parent (209/STDOUT and restart); manual mkdir restores healthy service. Fixed installer prepares parent before activation, remaining active without manual intervention.",
    "affected_revision": BASE, "fixed_revision": FIXED,
    "reproduction": {"script": ".verification/systemd/repro.py", "fixtures": "disposable OS user and fresh HOME", "old_receipt": "repro-old/receipt.json", "fixed_receipt": "repro-fixed/receipt.json"},
    "regression": {"test": "TestSystemdInstall", "old_receipt": "regression-old/receipt.json", "fixed_receipt": "regression-fixed/receipt.json"},
    "limits": ["Actual notifier proof uses a disposable GitHub Ubuntu VM user manager, not Docker.", "Bridge installer ordering is source-tested; no live bridge/channel integration claimed.", "Source tests, builds, vet and full gates run only in remote Docker.", "Independent receipt and full-gate inspection still required before publication."],
}
(proof / "result.json").write_text(json.dumps(report, indent=2) + "\n")
