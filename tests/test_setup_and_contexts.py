from __future__ import annotations

import uuid
import math

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


def test_checks():
    assert fairplay._type_checks(3, ["!int"]) == []
    assert fairplay._type_checks(True, ["!int"]) == ["!int"]
    assert fairplay._type_checks(3.0, ["!float"]) == []
    assert fairplay._type_checks(math.inf, ["!finite"]) == ["!finite"]
    assert fairplay._type_checks(0, ["!<=0"]) == ["!<=0"]
    assert fairplay._type_checks(8, ["!<9"]) == ["!<9"]
