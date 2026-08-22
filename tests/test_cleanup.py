from __future__ import annotations

import json

import fairplay


def test_cleanup(test_clock):
    fairplay.setup()
    registry = fairplay.process["registry_path"]
    claim_guid = "00000000-0000-4000-8000-000000000010"
    (registry / f"{claim_guid}.json").write_text(json.dumps({
        "claim_guid": claim_guid,
        "session_guid": "00000000-0000-4000-8000-000000000011",
        "expires_at": "2026-08-21T00:00:00Z",
        "targets": [{"scope": fairplay.FILE, "path": "old.txt"}],
    }), encoding="utf-8")
    ctxt = fairplay.new_context()
    result = fairplay.cleanup(ctxt)
    assert result["files_removed"] == 1
    assert not list(registry.glob("*.json"))
