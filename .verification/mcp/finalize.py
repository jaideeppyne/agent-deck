"""Check evidence integrity; a human-independent oracle review still follows."""
import hashlib
import json
import pathlib

BASE = "8d0f1fe1506dec1405d774c42c178291d1b20f40"
FIXED = "a03e89a291d8337adc4f9d7e34b30144e67e3ca9"
proof = pathlib.Path("proof")
for kind in ["repro", "regression"]:
    receipts = []
    for label, revision, expected in [("old", BASE, 1), ("fixed", FIXED, 0)]:
        folder = proof / (kind + "-" + label)
        receipt = json.loads((folder / "receipt.json").read_text())
        output = (folder / "output.log").read_bytes()
        assert receipt["exit_code"] == expected and not receipt["timed_out"]
        assert receipt["output_sha256"] == hashlib.sha256(output).hexdigest()
        if kind == "repro":
            observed = json.loads(output.decode().splitlines()[0])
            assert observed["healthy_exchange"] and observed["stdin_closed"]
            assert observed["alive_after_eof"] == (label == "old")
            if label == "old":
                assert observed["reconnects_after_eof"] > 0
            else:
                assert observed["exit_code"] == 0 and observed["reconnects_after_eof"] == 0
            receipt.update(source_revision=revision, oracle_matched=True,
                           oracle_evidence="Healthy actual CLI exchange, then stdin closes: " +
                           ("client stays alive and reconnects." if label == "old" else "client exits zero without reconnecting."))
            (folder / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        assert receipt["source_revision"] == revision
        assert receipt["oracle_matched"] and receipt["oracle_evidence"]
        receipts.append(receipt)
    for key in ["experiment", "fixtures", "script_sha256"]:
        assert receipts[0][key] == receipts[1][key], (kind, key)
report = {
    "schema_version": 1, "candidate_id": "agent-deck-2649", "status": "fixed",
    "issue": "https://github.com/asheshgoplani/agent-deck/issues/2649",
    "oracle": "Client remains alive/reconnects after stdin EOF; fixed client exits. Frozen CLI tests also cover parent death, reconnect input, and input/output pressure.",
    "affected_revision": BASE, "fixed_revision": FIXED,
    "reproduction": {"script": ".verification/mcp/repro.sh", "fixtures": ".verification/mcp/fixtures", "old_receipt": "repro-old/receipt.json", "fixed_receipt": "repro-fixed/receipt.json"},
    "regression": {"test": "TestMCPProxy", "old_receipt": "regression-old/receipt.json", "fixed_receipt": "regression-fixed/receipt.json"},
    "limits": ["Linux runtime proof; macOS cross-build is not macOS runtime validation.",
               "Parent identity changes after startup are observed; pre-startup adoption is not covered.",
               "Pool natural-exit/restart controls pass; no pool zombie fix or memory reduction claimed.",
               "EOF terminates the client, not a guarantee of draining queued requests or responses.",
               "Independent full-gate and receipt inspection is required before publication."],
}
(proof / "result.json").write_text(json.dumps(report, indent=2) + "\n")
