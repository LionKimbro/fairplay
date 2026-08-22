from __future__ import annotations

import uuid

import pytest

import fairplay


def test_setup():
    first = fairplay.setup()
    second = fairplay.setup()
    assert first["status"] == fairplay.OK
    assert first["session_guid"] == second["session_guid"]
    assert str(uuid.UUID(first["session_guid"])) == first["session_guid"]


def test_contexts():
    with pytest.raises(fairplay.FairPlaySetupRequiredError):
        fairplay.new_context()
    fairplay.setup()
    first = fairplay.new_context()
    second = fairplay.new_context()
    fairplay.config["retry_max_attempts"] = 9
    assert first["session_guid"] == second["session_guid"]
    assert first["operation_guid"] != second["operation_guid"]
    assert first["config"]["retry_max_attempts"] == 5
