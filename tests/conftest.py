from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import fairplay


def pytest_addoption(parser):
    parser.addoption("--fairplay-implementation", choices=("full", "chuck"), default="full")


def pytest_runtest_setup(item):
    if item.config.getoption("--fairplay-implementation") == "chuck" and item.path.name != "test_protocol.py":
        pytest.skip("This test covers full-version validation or result machinery.")


class TestClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 22, tzinfo=timezone.utc)
        self.elapsed = 0.0

    def now(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.elapsed += seconds

    def advance(self, seconds: float) -> None:
        self.sleep(seconds)


@pytest.fixture(autouse=True)
def _reset_fairplay_for_every_test(monkeypatch: pytest.MonkeyPatch, tmp_path):
    fairplay.process.clear()
    fairplay.process.update({
        "session_guid": None,
        "contention_window_seconds": 5,
        "registry_path": tmp_path / "claims",
    })
    fairplay.config.clear()
    fairplay.config.update({
        "minimum_reup_seconds": 1,
        "auto_retry_max_attempts": 5,
        "auto_retry_wait_interval_ms": 100,
        "block_timeout_seconds": 10,
    })


@pytest.fixture
def test_clock(monkeypatch: pytest.MonkeyPatch) -> TestClock:
    clock = TestClock()
    monkeypatch.setattr(fairplay, "_now", clock.now)
    monkeypatch.setattr(fairplay, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    return clock


@pytest.fixture
def test_implementation(request, monkeypatch):
    if request.config.getoption("--fairplay-implementation") == "full":
        return fairplay
    from fairplay import chuck_moore

    tmp_path = request.getfixturevalue("tmp_path")
    monkeypatch.setattr(chuck_moore.machineroot, "get", lambda key: str(tmp_path))
    chuck_moore.process.clear()
    chuck_moore.process.update({
        "session_guid": None,
        "registry_path": tmp_path / "claims",
        "contention_window_seconds": 0,
    })
    return chuck_moore
