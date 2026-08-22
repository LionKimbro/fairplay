from __future__ import annotations

import fairplay


def test_results(test_clock):
    fairplay.setup()
    ctxt = fairplay.new_context()
    result = fairplay.intend_claims(ctxt, [])
    assert result["timestamp"] == "2026-08-22T00:00:00.000000Z"
    assert ctxt["result"] is None
    result["timestamp"] = "override"
    assert ctxt["result"] is None
