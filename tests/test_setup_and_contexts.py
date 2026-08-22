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
    fairplay.config["auto_retry_max_attempts"] = 9
    assert first["session_guid"] == second["session_guid"]
    assert first["operation_guid"] != second["operation_guid"]
    assert first["config"]["auto_retry_max_attempts"] == 5


def test_registry(monkeypatch, tmp_path):
    calls = []
    fairplay.process["registry_path"] = None
    monkeypatch.setattr(fairplay.machineroot, "get", lambda key: calls.append(key) or str(tmp_path))
    fairplay.setup()
    first = fairplay.process["registry_path"]
    fairplay.setup()
    assert calls == ["fair-play"]
    assert first == fairplay.process["registry_path"]
    assert first == tmp_path / "claims"


def test_checks():
    assert fairplay._type_checks(3, ["!int"]) == []
    assert fairplay._type_checks(True, ["!int"]) == ["!int"]
    assert fairplay._type_checks(3.0, ["!float"]) == []
    assert fairplay._type_checks(math.inf, ["!finite"]) == ["!finite"]
    assert fairplay._type_checks(0, ["!<=0"]) == ["!<=0"]
    assert fairplay._type_checks(8, ["!<9"]) == ["!<9"]
