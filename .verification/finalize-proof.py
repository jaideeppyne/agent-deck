"""Check declared binary oracles and construct the paired evidence manifest."""
import json
import pathlib

root = pathlib.Path("proof")
oracles = {
    "old": "ORACLE: later active turn starved the selected complete socket reply",
    "fixed": "ORACLE: selected complete socket reply returned despite later active turn without correlation claims",
}
for label, oracle in oracles.items():
    folder = root / ("repro-" + label)
    log = (folder / "output.log").read_text()
    assert oracle in log and "SOCKET_FRAME_RECEIVED: True" in log and "WRAPPED_PEER_TURN_AND_REPLY: True" in log
    assert "LATER_TURN_STARTED: True" in log
    path = folder / "receipt.json"
    receipt = json.loads(path.read_text())
    assert receipt["exit_code"] == (1 if label == "old" else 0) and not receipt["timed_out"]
    receipt.update(oracle_matched=True, oracle_evidence=oracle)
    path.write_text(json.dumps(receipt, indent=2) + "\n")
manifest = {
    "schema_version": 1, "candidate_id": "agent-deck-2640", "status": "fixed",
    "issue": "https://github.com/asheshgoplani/agent-deck/issues/2640",
    "oracle": "Selected complete peer reply exists, but a later active turn starves the old pane-global completion wait; fixed CLI returns only the selected reply explicitly uncorrelated. Setup failures are not defect evidence.",
    "affected_revision": "0bf12b8be4b1fcd7d3ef14b82b2cc13845074b15",
    "fixed_revision": "0df60596e4120a832336b361e166d7f624443225",
    "reproduction": {"script": ".verification/repro.sh", "fixtures": "fixtures/",
                     "old_receipt": "repro-old/receipt.json", "fixed_receipt": "repro-fixed/receipt.json"},
    "regression": {"test": "TestSessionSendSocketWaitPeerReply",
                   "old_receipt": "regression-old/receipt.json", "fixed_receipt": "regression-fixed/receipt.json"},
    "limits": ["Only the external paid Claude process is synthetic; all CLI launch/send/socket/transcript operations are real.",
               "Linux Docker evidence, not a live macOS Claude session or Slack integration test.",
               "Observed UUID is a fresh transcript boundary, never proof that this socket message caused that turn.",
               "Full self-check and official Docker stages must be independently inspected before publication."]
}
(root / "result.json").write_text(json.dumps(manifest, indent=2) + "\n")
