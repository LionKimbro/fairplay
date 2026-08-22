from __future__ import annotations


def test_block(test_implementation):
    test_implementation.process["contention_window_seconds"] = 0
    test_implementation.setup()
    ctxt = test_implementation.new_context()
    test_implementation.intend_claims(ctxt, [(test_implementation.FILE, "block.txt")])
    result = test_implementation.make_claims(ctxt, 30, ["block"])
    assert _status(result) == test_implementation.OK


def test_withdraw(test_implementation):
    test_implementation.process["contention_window_seconds"] = 0
    test_implementation.setup()
    first = test_implementation.new_context()
    test_implementation.intend_claims(first, [(test_implementation.FILE, "keep.txt")])
    test_implementation.make_claims(first, 30)
    test_implementation.intend_claims(first, [(test_implementation.FILE, "contested.txt")])
    second = test_implementation.new_context()
    second["session_guid"] = "00000000-0000-4000-8000-000000000002"
    test_implementation.intend_claims(second, [(test_implementation.FILE, "contested.txt")])
    test_implementation.make_claims(second, 30)
    result = test_implementation.make_claims(first, 30, ["block", "auto-withdraw"])
    assert _status(result) == test_implementation.COMPETING_CLAIM
    assert len(first["published_claims"]) == 1
    assert first["published_claims"][0]["claim_file"].endswith(".json")
    if isinstance(result, dict):
        assert "claims_auto_withdrawn" not in result


def _status(result):
    return result["status"] if isinstance(result, dict) else result
