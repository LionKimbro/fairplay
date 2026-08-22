from __future__ import annotations

import fairplay


def test_competition(test_clock):
    fairplay.process["contention_window_seconds"] = 0
    fairplay.setup()
    first = fairplay.new_context()
    fairplay.intend_claims(first, [(fairplay.FILE, "shared.txt")])
    fairplay.make_claims(first, 30)
    second = fairplay.new_context()
    second["session_guid"] = "00000000-0000-4000-8000-000000000001"
    fairplay.intend_claims(second, [(fairplay.TREE, ".")])
    fairplay.make_claims(second, 30)
    result = fairplay.check_competitors(first, 1)
    assert result["status"] == fairplay.COMPETING_CLAIM
    assert result["competing_claims"][0]["remaining_seconds"] == 30
