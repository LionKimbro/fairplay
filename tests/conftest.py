from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import fairplay


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
    fairplay.process.update({"session_guid": None, "contention_window_seconds": 5})
    fairplay.config.clear()
    fairplay.config.update({
        "minimum_reup_seconds": 1,
        "auto_retry_max_attempts": 5,
        "auto_retry_wait_interval_ms": 100,
        "retry_max_attempts": 5,
        "retry_wait_interval_ms": 1000,
        "retry_jitter_ms": 250,
        "block_timeout_seconds": 10,
    })
    fairplay.g["registry_path"] = tmp_path / "claims"


@pytest.fixture
def test_clock(monkeypatch: pytest.MonkeyPatch) -> TestClock:
    clock = TestClock()
    monkeypatch.setattr(fairplay, "_now", clock.now)
    monkeypatch.setattr(fairplay, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep))
    return clock
