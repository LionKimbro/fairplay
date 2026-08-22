from __future__ import annotations

import fairplay
import pytest


def test_competition(test_clock):
    fairplay.process["contention_window_seconds"] = 0
    fairplay.setup()
    first = fairplay.new_context()
    fairplay.intend_claims(first, [(fairplay.FILE, "shared.txt")])
    fairplay.make_claims(first, 30)
    second = fairplay.new_context()
    second["session_guid"] = "00000000-0000-4000-8000-000000000001"
    fairplay.intend_claims(second, [(fairplay.TREE, ".")])
    result = fairplay.make_claims(second, 30)
    assert result["status"] == fairplay.COMPETING_CLAIM
    assert result["competing_claims"][0]["remaining_seconds"] == 30


def test_scans(monkeypatch, test_clock):
    fairplay.process["contention_window_seconds"] = 0
    fairplay.setup()
    first = fairplay.new_context()
    fairplay.intend_claims(first, [(fairplay.FILE, "shared.txt")])
    fairplay.make_claims(first, 30)
    second = fairplay.new_context()
    second["session_guid"] = "00000000-0000-4000-8000-000000000001"
    fairplay.intend_claims(second, [(fairplay.FILE, "shared.txt")])
    assert fairplay.make_claims(second, 30)["status"] == fairplay.COMPETING_CLAIM
    calls = []
    read_claim = fairplay._read_claim
    monkeypatch.setattr(fairplay, "_read_claim", lambda path: calls.append(path) or read_claim(path))
    fairplay.check_competitors(first, 1)
    assert len(calls) == 1


def test_flags(test_clock):
    fairplay.setup()
    ctxt = fairplay.new_context()
    with pytest.raises(ValueError):
        fairplay.check_competitors(ctxt, 0, ["block"])
