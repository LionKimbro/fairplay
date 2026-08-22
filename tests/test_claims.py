from __future__ import annotations

import json
from pathlib import Path

import fairplay


def test_claims(test_clock):
    fairplay.setup()
    ctxt = fairplay.new_context()
    fairplay.intend_claims(ctxt, [(fairplay.FILE, "example.txt")])
    result = fairplay.make_claims(ctxt, 30)
    claim_path = next(fairplay.process["registry_path"].glob("*.json"))
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    assert result["status"] == fairplay.WAIT
    assert claim_path.stem == claim["claim_guid"]
    assert claim["session_guid"] == ctxt["session_guid"]
    assert claim["targets"] == [{"scope": fairplay.FILE, "path": str(Path("example.txt").resolve()).lower()}]
