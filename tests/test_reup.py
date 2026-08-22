from __future__ import annotations

import fairplay


def test_reup(test_clock):
    fairplay.process["contention_window_seconds"] = 0
    fairplay.setup()
    ctxt = fairplay.new_context()
    fairplay.intend_claims(ctxt, [(fairplay.FILE, "renew.txt")])
    fairplay.make_claims(ctxt, 3)
    prior = ctxt["published_claims"][0]["claim_guid"]
    test_clock.advance(1.1)
    result = fairplay.check_competitors(ctxt, 2, ["re-up"])
    assert result["status"] == fairplay.OK
    assert result["reup_performed"]
    assert result["replacement_claims_created"][0]["claim_guid"] != prior
